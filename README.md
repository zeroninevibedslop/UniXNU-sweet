# UniXNU-sweet: Xiaomi Redmi Note 10 Pro (sweet / SM7150) Device Repository

[![License](https://img.shields.io/badge/license-BSD--2--Clause--Patent-blue.svg)](LICENSE)
[![Target OS](https://img.shields.io/badge/Target%20OS-iOS%2016.7.16%20(20H392)-green.svg)](https://updates.cdn-apple.com)
[![SoC](https://img.shields.io/badge/SoC-Qualcomm%20SM7150%20(Snapdragon%20732G)-orange.svg)](https://www.qualcomm.com)

This repository provides the official [UniXNU](https://github.com/UniXNU/UniXNU) device support package (BSP) for the **Xiaomi Redmi Note 10 Pro** (codename `sweet` / Qualcomm Snapdragon 732G - SM7150).

It provides the complete hardware abstraction, Apple Device Tree (ADT) synthesis, kernel defconfig, and automated line-flash boot image generation to boot pure Apple **XNU (`xnu-8796.141.3`, Darwin 22)** and the **iOS 16 (iPhone X / `d22ap`)** userland on non-Apple ARM64 hardware without legacy shims.

---

## Hardware Specifications

| Subsystem | Specification / Implementation Details |
| :--- | :--- |
| **SoC** | Qualcomm Snapdragon 732G (SM7150-AC), Kryo 470 (2x Cortex-A76 Gold @ 2.3 GHz + 6x Cortex-A55 Silver @ 1.8 GHz) |
| **GPU** | Qualcomm Adreno 618 (A6xx family, 4 KiB SMMUv2, GMU / HFI power architecture) |
| **Storage** | UFS 2.1 (Qualcomm UFSHCI 2.1 controller @ `0x01d84000`) |
| **Display** | 6.67" Super AMOLED, 1080x2400 @ 60/120 Hz (Continuous-Splash GOP frame buffer @ `0x9c000000`) |
| **Touchscreen** | Goodix GT9896 (Yellowstone protocol over QUPv3 SE7 SPI @ `0x00a84000`) |
| **Power & PMIC** | Qualcomm PM6150 (PON Power / VolDown) + PM6150L (GPIO VolUp) |
| **Target Userland** | iOS 16.7.16 (Build `20H392`, Profile `d22ap` / iPhone X) |

---

## Current Status & Milestones

- [x] **Pure UEFI Line-Flash Boot Chain**:
  - Qualcomm ABL -> EDK2 UEFI (`sm7150-sweet-uefi`) -> `UniXNU.efi` (portrait display menu + volume/power key navigation) -> `DarwinBoot.efi` -> Mach-O XNU hand-off.
  - Implements **16 KiB ARM64 granule 32 MiB Level 2 block translation alignment** in `DarwinBoot` (`Kernel.Base & ~(SIZE_32MB - 1)`).
- [x] **Full iOS 16 Userspace Execution**:
  - XNU mounts the internal UFS root filesystem (`rd=ufsroot0`), runs `launchd`, and starts core daemons (`fairplayd`, `bluetoothd`, `xpcproxy`).
  - **`backboardd` and `SpringBoard` active**: Actively performing surface swaps on the 1080x2400 AMOLED display (`SWEET FB: swap 32 layer 0 surface 5 1080x2400 fmt 0x42475241`).
- [x] **Visual Text Console & Automatic GUI Muting**:
  - `sweet_early` and `sweet_fbcon` AMOLED text console operational during pre-kernel and early I/O.
  - `sweetfb_noconsole=1` automatically mutes glyph rendering upon the first GUI surface swap, preventing console overwrites.
- [x] **Live USB CDC-ECM Telemetry**:
  - Host enumerates `Sweet iOS (USB Ethernet)` (`192.168.7.1`).
  - Live kernel UDP telemetry streamed to host on port `5140`.
- [x] **Adreno 618 Hardware Power Verification (Milestones 1–17)**:
  - GCC / GPUCC clock gating (GPLL0/2, GMU RCG 200 MHz).
  - RPMh ARC CX / MX / GX voltage rail voting.
  - GMU firmware load to TCM (`a630_gmu.bin`), RSCC / PDC sequencer initialization, OOB BOOT_SLUMBER handshake, and SPTPRAC shader core clustering power-on.
- [ ] **GPU Hardware Acceleration (In Progress)**:
  - Integrating `sweet_gpu.c` A618 bring-up into `NativeAdreno` IOKit accelerator (`IOAcceleratorES`).
  - Mesa Turnip (Freedreno Vulkan) cross-compilation for Darwin KMD (`tu_knl_darwin.cc`).
  - NativeMetal userland plugin bundle (`NativeAdrenoMetal.bundle`).

---

## Repository Structure

```text
UniXNU-sweet/
├── board.toml                 # Board definition, partition geometry, LBA mappings, IPSW profile
├── configs/
│   └── sweet_defconfig        # Board-specific XNU kernel configuration fragments
├── dts/                       # Device tree sources and bindings
├── scripts/
│   ├── make-sweet-adt.py      # Apple Device Tree (ADT) synthesizer for Sweet
│   ├── build-esp-image.sh     # SWEETESP FAT16 ramdisk generator
│   └── package-sweet-unixnu.py# Android boot v2 line-flash image packager
└── README.md                  # Device documentation
```

---

## Building and Booting

### Prerequisites

- A Linux build host (x86_64 or aarch64).
- Python 3.10+ with standard modules.
- Android platform tools (`fastboot`).
- Pre-built `UniXNU.efi` and `DarwinBoot.efi` (from [UniXNU core](https://github.com/zeroninevibedslop/UniXNU)).

### 1. Generate the Apple Device Tree (ADT)

Synthesize the hardware device tree incorporating the correct GIC interrupt controller node, 10 MiB AMOLED framebuffer buffer, and 2 GiB memory window:

```bash
python3 scripts/make-sweet-adt.py --output build/sweet.adt
```

### 2. Generate the SWEETESP Ramdisk

Construct the FAT16 UEFI ESP ramdisk holding `UniXNU.efi`, `DarwinBoot.efi`, and `unixnu.toml`:

```bash
bash scripts/build-esp-image.sh
```

### 3. Package the Line-Flash Boot Image

Package the kernel Mach-O, UEFI loader, ESP ramdisk, and ADT into a single Android Boot v2 image:

```bash
python3 scripts/package-sweet-unixnu.py
```

Output image: `build/firmware/sweet_unixnu_boot.img`.

### 4. Boot via Fastboot

Place the device into Fastboot mode (Power + VolDown) and execute:

```bash
fastboot boot build/firmware/sweet_unixnu_boot.img
```

---

## Monitoring Live Diagnostics

When booted with `sweetusb=2`, the device exposes a USB CDC-ECM network interface on the host (`enp0s20f0u...`):

```bash
# Configure host IP
sudo ip addr add 192.168.7.1/24 dev <interface_name>
sudo ip link set <interface_name> up

# Listen to live kernel telemetry
socat -u udp-recv:5140,reuseaddr -
```

---

## Contributing & Attribution

- **Main Contributor**: [allshx2](https://github.com/allshx2)
- **Co-contributor**: Gemini
- **Upstream Framework**: [UniXNU](https://github.com/UniXNU) by Blu-Sharky

---

# Special Thanks
- Gemini 3.8 Flash


## License

This project is licensed under the **BSD-2-Clause-Patent** License. See the upstream [LICENSE](https://github.com/zeroninevibedslop/UniXNU/blob/main/LICENSE) for details.
