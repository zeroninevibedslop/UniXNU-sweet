#!/bin/bash
set -e
ESP_IMG="/mnt/ext_nvme/XNU_Sweet/UniXNU-sweet/build/firmware/sweet-esp.img"
PAYLOAD_DIR="/mnt/ext_nvme/XNU_Sweet/UniXNU-sweet/build/payload"

mkdir -p "$(dirname "$ESP_IMG")"
rm -f "$ESP_IMG"
truncate -s 26M "$ESP_IMG"

podman run --rm -v /mnt/ext_nvme/XNU_Sweet:/workspace docker.io/library/alpine:latest sh -c "
  apk add --no-cache dosfstools mtools >/dev/null 2>&1
  mkfs.fat -F 16 -n SWEETESP /workspace/UniXNU-sweet/build/firmware/sweet-esp.img
  mcopy -i /workspace/UniXNU-sweet/build/firmware/sweet-esp.img -s -Q /workspace/UniXNU-sweet/build/payload/* ::/
  echo '=== FAT16 ESP Content Listing ==='
  mdir -i /workspace/UniXNU-sweet/build/firmware/sweet-esp.img -s ::/
"

echo "Successfully built SWEETESP FAT16 image: $ESP_IMG ($(stat -c%s "$ESP_IMG") bytes)"
