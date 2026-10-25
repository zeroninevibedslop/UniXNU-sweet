#!/usr/bin/env python3
"""Package the sweet UniXNU line-flash boot image using Android bootimg v0.

Architecture:
- Kernel payload: Gzip(F11_UEFI.fd) + sweet.dtb
- Ramdisk payload: sweet-esp.img (FAT32 volume with SWEETESP label, UniXNU.efi,
                   DarwinBoot.efi, kernel.macho, kernel.macho.adt, and unixnu.toml)
- Boot parameters: Standard SM7150 ABL bootimg v0 geometry
                   (kernel_offset 0x8000, ramdisk_offset 0x1000000,
                    tags_offset 0x100, pagesize 4096)
"""

import gzip
import hashlib
from pathlib import Path
import struct
import sys

ROOT = Path('/mnt/ext_nvme/XNU_Sweet')
UEFI_ROOT = ROOT / 'sm7150-sweet-uefi'
SWEET_ROOT = ROOT / 'UniXNU-sweet'
FIRMWARE_DIR = SWEET_ROOT / 'build/firmware'

FD_PATH = UEFI_ROOT / 'Build/F11/DEBUG_GCC5/FV/F11_UEFI.fd'
DTB_PATH = UEFI_ROOT / 'sweet.dtb'
ESP_PATH = FIRMWARE_DIR / 'sweet-esp.img'
OUT_IMG = FIRMWARE_DIR / 'sweet_unixnu_boot.img'

PAGE_SIZE = 4096
KERNEL_ADDR = 0x8000
RAMDISK_ADDR = 0x1000000
SECOND_ADDR = 0xf00000
TAGS_ADDR = 0x100

def pad_bytes(data: bytes, page: int = PAGE_SIZE) -> bytes:
    remainder = len(data) % page
    if remainder == 0:
        return data
    return data + b'\x00' * (page - remainder)

def main():
    print("=== Packaging UniXNU Sweet Line-Flash Boot Image (v0) ===")
    
    if not FD_PATH.exists():
        sys.exit(f"Error: UEFI FD not found at {FD_PATH}")
    if not DTB_PATH.exists():
        sys.exit(f"Error: DTB not found at {DTB_PATH}")
    if not ESP_PATH.exists():
        sys.exit(f"Error: SWEETESP image not found at {ESP_PATH}")

    fd_bytes = FD_PATH.read_bytes()
    dtb_bytes = DTB_PATH.read_bytes()
    esp_bytes = ESP_PATH.read_bytes()

    print(f"[*] UEFI FD: {len(fd_bytes):,} bytes ({FD_PATH.name})")
    print(f"[*] ABL DTB: {len(dtb_bytes):,} bytes ({DTB_PATH.name})")
    print(f"[*] SWEETESP RamDisk: {len(esp_bytes):,} bytes ({ESP_PATH.name})")

    # Compress FD with gzip (mtime=0 for reproducible build)
    gz_bytes = gzip.compress(fd_bytes, compresslevel=9, mtime=0)
    kernel_payload = gz_bytes + dtb_bytes
    print(f"[*] Combined Kernel Payload: {len(kernel_payload):,} bytes (Gzip FD + DTB)")

    padded_kernel = pad_bytes(kernel_payload)
    padded_ramdisk = pad_bytes(esp_bytes)

    # Construct Android bootimg v0 header (1632 bytes in 1 page)
    magic = b'ANDROID!'
    kernel_size = len(kernel_payload)
    kernel_addr = KERNEL_ADDR
    ramdisk_size = len(esp_bytes)
    ramdisk_addr = RAMDISK_ADDR
    second_size = 0
    second_addr = SECOND_ADDR
    tags_addr = TAGS_ADDR
    page_size = PAGE_SIZE
    header_version = 0
    os_version = 0
    name = b''
    cmdline = b''
    id_bytes = b'\x00' * 32
    extra_cmdline = b''

    header = struct.pack(
        '<8s10I16s512s32s1024s',
        magic,
        kernel_size,
        kernel_addr,
        ramdisk_size,
        ramdisk_addr,
        second_size,
        second_addr,
        tags_addr,
        page_size,
        header_version,
        os_version,
        name,
        cmdline,
        id_bytes,
        extra_cmdline
    )
    padded_header = pad_bytes(header)

    total_image = padded_header + padded_kernel + padded_ramdisk
    OUT_IMG.write_bytes(total_image)

    out_size = len(total_image)
    print(f"\n[+] Successfully created: {OUT_IMG}")
    print(f"[+] Total Image Size: {out_size:,} bytes ({out_size / (1024*1024):.2f} MiB)")
    print(f"[+] SHA256: {hashlib.sha256(total_image).hexdigest()}")
    print("\nBoot verification command:")
    print(f"  fastboot boot {OUT_IMG}")

if __name__ == '__main__':
    main()
