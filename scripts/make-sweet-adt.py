#!/usr/bin/env python3
"""Generate the standard Apple Device Tree (ADT) for Xiaomi Redmi Note 10 Pro (sweet / SM7150).

Implements the official UniXNU ADT tool contract used by payload.py and DarwinBoot:
  - SM7150 GICv3: Distributor 0x17a00000 (size 0x10000), Redistributor 0x17a60000 (size 0x100000)
  - Architectural counter / timebase: 19.2 MHz (19200000 Hz)
  - Virtual timer PPI: 19
  - Continuous-Splash GOP Framebuffer: 0x9c000000 (1080x2400 BGRA, stride 4320)
  - UFS 2.1 Host Controller: 0x01d84000 (size 0x3000)
  - 8 Kryo 470 cores: 6x Cortex-A55 (cores 0-5, Aff1 0x000..0x500) + 2x Cortex-A76 (cores 6-7, Aff1 0x600..0x700)
  - iPhone X (D22AP / 20H392) device identity for iOS 16 userland (SpringBoard, backboardd)
"""
from pathlib import Path
import argparse
import hashlib
import os
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]

# Memory and Base Addresses
DRAM_BASE = 0x80000000
HIGH_PHYS_BASE = 0x100000000
HIGH_MEM_SIZE = 0xfcc00000
SOC_BASE = 0x01000000

# GICv3 (SM7150 APSS)
GIC_DIST = 0x17a00000
GIC_DIST_SIZE = 0x10000
GIC_REDIST = 0x17a60000
GIC_REDIST_SIZE = 0x100000
VTIMER_INTID = 19
TIMEBASE = 19200000

# Continuous-Splash Framebuffer (ABL / UEFI)
FB_BASE = 0x9c000000
FB_SIZE = 0x1700000
FB_WIDTH = 1080
FB_HEIGHT = 2400
FB_STRIDE = 1080 * 4

# UFS Host Controller
UFS_BASE = 0x01d84000
UFS_SIZE = 0x3000

# Identities
SWEET_SYNTHETIC_ECID = 0x5357454554000001  # 'SWEET\0\1'
DEFAULT_CHIP_ID = 0x8015                   # Apple A11 Bionic (T8015)
BOOT_MANIFEST_HASH = hashlib.sha384(b'sweet boot manifest').digest()

# Optional path to cached d22ap.adt for importing genuine /product properties
D22AP_ADT_PATHS = [
    ROOT.parent / 'ios-sweet/research/ipsw-x/d22ap.adt',
    ROOT / 'assets/d22ap.adt',
]


def node(name, properties=(), children=()):
    """Encode an Apple Device Tree node in binary ADT format."""
    encoded_props = [('name', name.encode() + b'\0', 0)]
    for item in properties:
        if len(item) == 2:
            key, val = item
            flag = 0
        else:
            key, val, flag = item
        encoded_props.append((key, val, flag))

    result = bytearray(struct.pack('<II', len(encoded_props), len(children)))
    for key, val, flag in encoded_props:
        name_bytes = key.encode().ljust(32, b'\0')[:32]
        size_with_flag = len(val) | (flag << 31)
        result += name_bytes + struct.pack('<I', size_with_flag)
        result += val + b'\0' * (-len(val) & 3)

    for child in children:
        result += child
    return bytes(result)


def empty_nvram_proxy():
    """Build a volatile CHRP NVRAM bank for XNU IODTNVRAM support."""
    def header(bank_name, size):
        raw = bytearray(struct.pack('<BBH12s', 0x70, 0, size // 16, bank_name))
        checksum = sum(raw)
        while checksum > 255:
            checksum = (checksum & 255) + (checksum >> 8)
        raw[1] = checksum
        return raw

    image = bytearray(8192)
    image[:16] = header(b'nvram', 32)
    image[32:48] = header(b'common', 16 + 2048)
    free_at = 32 + 16 + 2048
    image[free_at:free_at + 16] = header(b'free', len(image) - free_at)
    struct.pack_into('<I', image, 16, zlib.adler32(image[20:]))
    return [
        ('nvram-bank-size', struct.pack('<I', len(image))),
        ('nvram-bank-count', struct.pack('<I', 1)),
        ('nvram-current-bank', struct.pack('<I', 0)),
        ('nvram-proxy-data', bytes(image)),
    ]


def load_d22ap_product():
    """Attempt to load real /product properties from d22ap.adt if present."""
    for path in D22AP_ADT_PATHS:
        if not path.is_file():
            continue
        try:
            buf = path.read_bytes()
            def parse_adt_node(b, off=0):
                nprops, nchildren = struct.unpack_from('<II', b, off)
                off += 8
                props = []
                for _ in range(nprops):
                    name = b[off:off + 32].split(b'\0')[0].decode()
                    size, = struct.unpack_from('<I', b, off + 32)
                    flags, ln = size >> 31, size & 0x7fffffff
                    props.append((name, flags, b[off + 36:off + 36 + ln]))
                    off += 36 + ((ln + 3) & ~3)
                ch_nodes = []
                for _ in range(nchildren):
                    child, off = parse_adt_node(b, off)
                    ch_nodes.append(child)
                return (props, ch_nodes), off

            (root_props, children), _ = parse_adt_node(buf)
            for cprops, _ in children:
                pdict = {k: v for k, f, v in cprops}
                if pdict.get('name') == b'product\0':
                    return [(k, v) for k, f, v in cprops if not f and k not in ('name', 'AAPL,phandle')]
        except Exception:
            continue
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'build/sweet/boot/kernel.macho.adt')
    parser.add_argument('--dram-size', type=lambda v: int(v, 0), default=None,
                        help='DRAM size in bytes (e.g. 0x80000000 or 0xfcc00000)')
    parser.add_argument('--owned-memory-size', type=lambda v: int(v, 0), default=None,
                        help='DarwinBoot contiguous memory window size')
    parser.add_argument('--root-match-volume-uuid', default=None,
                        help='Target root partition UUID for /chosen/root-matching')
    parser.add_argument('--unique-chip-id', type=lambda v: int(v, 16) if v else None, default=None,
                        help='Unique ECID (64-bit hex)')
    parser.add_argument('--chip-id', type=lambda v: int(v, 16) if v else None, default=None,
                        help='Apple Chip ID (e.g. 0x8015 for A11 Bionic)')
    parser.add_argument('--cpu-regs', default='0x000,0x100,0x200,0x300,0x400,0x500,0x600,0x700',
                        help='Comma-separated CPU MPIDR Aff1:Aff0 values (default: 8 cores of SM7150)')
    parser.add_argument('--psci-method', choices=['smc', 'hvc'], default='smc',
                        help='PSCI invocation method (smc for SM7150)')
    parser.add_argument('--packed-data-ramdisk', action='store_true',
                        help='Packed DBRDISK1 ramdisk handoff')
    parser.add_argument('--data-ramdisk', action='store_true',
                        help='Dense memory-map RAMDisk placeholder')
    parser.add_argument('--persistent-data', action='store_true',
                        help='Persistent Data volume without ephemeral-storage')
    parser.add_argument('--trust-cache', action='store_true',
                        help='TrustCache placeholder in /chosen/memory-map')
    parser.add_argument('--highmem', action='store_true', default=True,
                        help='Use high-memory DDR bank (base 0x100000000, default on sweet)')
    parser.add_argument('--no-highmem', dest='highmem', action='store_false',
                        help='Use low-memory DDR bank (base 0x80000000)')
    parser.add_argument('--text-fixup', action='append', default=[],
                        help='Kernel signed text fixup rules')
    parser.add_argument('--ipad-identity', action='store_true',
                        help='Compatibility flag (unused for sweet, which uses iPhone X identity)')

    args = parser.parse_args()

    unique_chip_id = args.unique_chip_id if args.unique_chip_id is not None else SWEET_SYNTHETIC_ECID
    chip_id = args.chip_id if args.chip_id is not None else DEFAULT_CHIP_ID

    dram_base = HIGH_PHYS_BASE if args.highmem else DRAM_BASE
    dram_size = HIGH_MEM_SIZE if args.highmem else (args.dram_size or DRAM_BASE)

    # CPU Nodes
    cpu_regs = [int(v, 0) for v in args.cpu_regs.split(',')]
    cpus = []
    for index, reg in enumerate(cpu_regs):
        is_gold = (index >= 6) or (reg >= 0x600)
        clock_freq = 2304000000 if is_gold else 1804800000
        cpu_props = [
            ('device_type', b'cpu\0'),
            ('compatible', b'qcom,kryo470\0ARM,v8\0'),
            ('reg', struct.pack('<I', reg)),
            ('cpu-id', struct.pack('<I', index)),
            ('cluster-id', struct.pack('<I', 0)),
            ('cluster-type', struct.pack('<I', 0)),
            ('die-cluster-id', struct.pack('<I', 0)),
            ('cluster-core-id', struct.pack('<I', index)),
            ('l2-cache-id', struct.pack('<I', index)),
            ('l3-cache-id', struct.pack('<I', 0)),
            ('state', b'running\0' if index == 0 else b'stopped\0'),
            ('timebase-frequency', struct.pack('<I', TIMEBASE)),
            ('clock-frequency', struct.pack('<I', clock_freq)),
            ('bus-frequency', struct.pack('<I', 100000000)),
            ('memory-frequency', struct.pack('<I', 1866000000)),
            ('peripheral-frequency', struct.pack('<I', TIMEBASE)),
            ('fixed-frequency', struct.pack('<I', TIMEBASE)),
        ]
        cpus.append(node(f'cpu{index}', cpu_props))

    # /chosen node
    chosen_props = [
        ('dram-base', struct.pack('<Q', dram_base)),
        ('dram-size', struct.pack('<Q', dram_size)),
        ('random-seed', os.urandom(64)),
        ('debug-enabled', struct.pack('<I', 1)),
        ('firmware-version', b'UniXNU-sweet-uefi\0'),
        ('system-firmware-version', b'UniXNU-sweet-uefi\0'),
        ('boot-manifest-hash', BOOT_MANIFEST_HASH),
        ('crypto-hash-method', b'sha2-384\0'),
        ('display-scale', struct.pack('<I', 3)),
        ('unique-chip-id', struct.pack('<Q', unique_chip_id)),
        ('chip-id', struct.pack('<I', chip_id)),
        ('certificate-production-status', struct.pack('<I', 0)),
        ('effective-production-status-ap', struct.pack('<I', 0)),
        ('certificate-security-mode', struct.pack('<I', 1)),
        ('effective-security-mode-sep', struct.pack('<I', 1)),
        ('osenvironment', b'main\0'),
        ('amfi-only-platform-code', struct.pack('<I', 1)),
        *empty_nvram_proxy(),
    ]

    if args.owned_memory_size:
        chosen_props.append(('darwinboot-memory-size', struct.pack('<Q', args.owned_memory_size)))

    if args.root_match_volume_uuid:
        matching_dict = (
            f'<dict><key>IOProviderClass</key><string>IOMedia</string>'
            f'<key>IOPropertyMatch</key><dict><key>UUID</key><string>'
            f'{args.root_match_volume_uuid.upper()}</string></dict></dict>\0'
        ).encode()
        chosen_props.append(('root-matching', matching_dict))

    if (args.data_ramdisk or args.packed_data_ramdisk) and not args.persistent_data:
        chosen_props.append(('ephemeral-storage', struct.pack('<I', 1)))

    if args.text_fixup:
        chosen_props.append(('text-fixups', b''.join(f.encode() + b'\0' for f in args.text_fixup)))

    # /chosen/memory-map
    mem_map_props = []
    if args.packed_data_ramdisk:
        mem_map_props.append(('PackedRAMDisk', bytes(16)))
    elif args.data_ramdisk:
        mem_map_props.append(('RAMDisk', bytes(16)))
    if args.trust_cache:
        mem_map_props.append(('TrustCache', bytes(16)))

    chosen_children = [
        node('memory-map', mem_map_props),
        # asmb: relaxed CSR policy allowing dyld to map shared cache without strict sealing
        node('asmb', [
            ('lp-sip0', struct.pack('<Q', 0x6f)),
            ('lp-sip1', struct.pack('<I', 1)),
        ]),
        node('manifest-properties'),
    ]

    # /arm-io node
    gic_node = node('gic', [
        ('compatible', b'arm,gic-v3\0'),
        ('interrupt-controller', b''),
        ('virtual-timer-intid', struct.pack('<I', VTIMER_INTID)),
        ('reg', struct.pack('<4Q',
                            GIC_DIST - SOC_BASE, GIC_DIST_SIZE,
                            GIC_REDIST - SOC_BASE, GIC_REDIST_SIZE)),
        ('redistributor-stride', struct.pack('<Q', 0x20000)),
    ])

    wdt_node = node('wdt', [('no-pmu', struct.pack('<I', 1))])

    disp_node = node('disp0', [
        ('device_type', b'display-subsystem\0'),
        ('compatible', b'sweet,display\0'),
        ('canvas-width', struct.pack('<I', 1125)),
        ('canvas-height', struct.pack('<I', 2436)),
    ])

    ufshc_node = node('ufshc', [
        ('compatible', b'qcom,sm7150-ufshc\0qcom,ufshc\0'),
        ('reg', struct.pack('<2Q', UFS_BASE - SOC_BASE, UFS_SIZE)),
    ])

    # Adreno 618 GPU Node
    gpu_node = node('kgsl_3d0', [
        ('compatible', b'qcom,adreno\0qcom,kgsl-3d0\0qcom,kgsl-3d\0'),
        ('device_type', b'gpu-core\0'),
        ('qcom,chipid', struct.pack('<I', 0x06010800)),
        ('reg', struct.pack('<4Q',
                            0x05000000 - SOC_BASE, 0x40000,
                            0x05090000 - SOC_BASE, 0x9000)),
    ])

    # GMU Node (GMU + PDC + PDC SEQ)
    gmu_node = node('gmu', [
        ('compatible', b'qcom,adreno-gmu\0qcom,gpu-gmu\0'),
        ('device_type', b'gmu\0'),
        ('reg', struct.pack('<6Q',
                            0x0506a000 - SOC_BASE, 0x31000,
                            0x0b290000 - SOC_BASE, 0x10000,
                            0x0b490000 - SOC_BASE, 0x10000)),
    ])

    # GPU SMMU Node
    smmu_node = node('smmu', [
        ('compatible', b'qcom,smmu-kgsl\0arm,smmu-v2\0qcom,smmu-v2\0'),
        ('device_type', b'iommu\0'),
        ('iommu-cells', struct.pack('<I', 1)),
        ('reg', struct.pack('<2Q',
                            0x05040000 - SOC_BASE, 0x10000)),
    ])

    arm_io_node = node('arm-io', [
        ('device_type', b'sweet-io\0'),
        ('compatible', b'sweet-io\0arm-io\0'),
        ('#address-cells', struct.pack('<I', 2)),
        ('#size-cells', struct.pack('<I', 2)),
        ('ranges', struct.pack('<3Q', 0, SOC_BASE, 0x100000000 - SOC_BASE)),
    ], [gic_node, wdt_node, disp_node, ufshc_node, gpu_node, gmu_node, smmu_node])

    # Continuous-Splash Framebuffer Node
    fbcon_node = node('sweet-fbcon', [
        ('reg', struct.pack('<2Q', FB_BASE, FB_SIZE)),
        ('width', struct.pack('<I', FB_WIDTH)),
        ('height', struct.pack('<I', FB_HEIGHT)),
        ('stride', struct.pack('<I', FB_STRIDE)),
    ])

    # Absolute UFS Host Node (read by sweet_ufs / NativeUfs)
    sweet_ufs_node = node('sweet-ufs', [
        ('compatible', b'qcom,ufshc\0'),
        ('reg', struct.pack('<2Q', UFS_BASE, UFS_SIZE)),
    ])

    # Physical Buttons
    buttons_node = node('buttons', [
        ('compatible', b'buttons\0'),
        ('device_type', b'buttons\0'),
        ('button-names', b'hold\0voldown\0volup\0'),
        ('home-button-type', struct.pack('<I', 2)),  # 2 = Home-button-less UI
        ('opposed-power-vol-buttons', struct.pack('<I', 1)),
    ])

    # /defaults
    defaults_node = node('defaults', [
        ('sleep-disabled', struct.pack('<I', 1)),
        ('no-effaceable-storage', struct.pack('<I', 1)),
        ('kern.maxvnodes', struct.pack('<I', 66560)),
    ])

    # /product node
    imported_product_props = load_d22ap_product()
    if imported_product_props:
        product_props = imported_product_props
    else:
        product_props = [
            ('product-name', b'iPhone X\0'),
            ('product-description', b'iPhone X\0'),
            ('model', b'xiaomi,sweet\0'),
            ('artwork-device-idiom', b'phone\0'),
            ('artwork-device-subtype', struct.pack('<I', 2436)),
            ('artwork-scale-factor', struct.pack('<I', 3)),
            ('artwork-display-gamut', b'sRGB\0'),
            ('thin-bezel', struct.pack('<I', 1)),
            ('compatible-device-fallback', b'iPhone9,1\0'),
        ]
    product_node = node('product', product_props)

    # Root Device Tree
    root_props = [
        ('compatible', b'D22AP\0iPhone10,3\0xiaomi,sweet\0qcom,sm7150\0AppleARM\0'),
        ('model', b'iPhone10,3\0'),
        ('target-type', b'D22\0'),
        ('target-sub-type', b'D22AP\0'),
        ('manufacturer', b'Apple Inc.\0'),
        ('#address-cells', struct.pack('<I', 2)),
        ('#size-cells', struct.pack('<I', 2)),
    ]

    root_children = [
        node('chosen', chosen_props, chosen_children),
        defaults_node,
        node('cpus', [
            ('#address-cells', struct.pack('<I', 1)),
            ('#size-cells', struct.pack('<I', 0)),
        ], cpus),
        node('psci', [
            ('compatible', b'arm,psci-1.0\0'),
            ('method', args.psci_method.encode() + b'\0'),
        ]),
        arm_io_node,
        fbcon_node,
        sweet_ufs_node,
        buttons_node,
        product_node,
    ]

    tree = node('device-tree', root_props, root_children)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(tree)
    print(f'sweet ADT generated: {len(tree)} bytes -> {args.output}')
    print(f'  DRAM: base {dram_base:#x}, size {dram_size:#x}')
    print(f'  Cores: {len(cpu_regs)} (affinity: {args.cpu_regs})')
    print(f'  Product: iPhone X (D22AP / 0x8015) for sweet (SM7150)')


if __name__ == '__main__':
    main()
