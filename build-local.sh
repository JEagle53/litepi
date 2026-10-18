#!/usr/bin/env bash
# Build the LightPi OS image on your own Linux PC (x86-64 or ARM64) with Docker.
# Needs: git, docker (your user in the docker group, or run with sudo). ~15 GB free disk.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${HERE}/.pi-gen"

command -v docker >/dev/null || { echo "Docker is required: https://docs.docker.com/engine/install/"; exit 1; }

rm -rf "${WORK}"
git clone --depth 1 --branch arm64 https://github.com/RPi-Distro/pi-gen "${WORK}"

# Stage setup: our stage on top of Raspberry Pi OS Lite, export only the final image.
cp -r "${HERE}/lightpi-stage" "${WORK}/lightpi-stage"
chmod +x "${WORK}/lightpi-stage/prerun.sh" \
         "${WORK}/lightpi-stage/01-lightpi/00-run.sh" \
         "${WORK}/lightpi-stage/01-lightpi/files/opt-lightpi/start-lightpi.sh"
rm -f "${WORK}/stage2/EXPORT_IMAGE"      # don't also export the plain Lite image
touch "${WORK}/stage3/SKIP" "${WORK}/stage4/SKIP" "${WORK}/stage5/SKIP"
touch "${WORK}/stage4/SKIP_IMAGES" "${WORK}/stage5/SKIP_IMAGES"

cat > "${WORK}/config" <<CFG
IMG_NAME=LightPi-OS-0.1
RELEASE=trixie
PI_GEN_RELEASE="LightPi OS 0.1"
TARGET_HOSTNAME=${LIGHTPI_HOSTNAME:-lightpi}
FIRST_USER_NAME=${LIGHTPI_USER:-lightpi}
FIRST_USER_PASS=${LIGHTPI_PASS:-lightpi}
DISABLE_FIRST_BOOT_USER_RENAME=1
PASSWORDLESS_SUDO=1
ENABLE_SSH=1
ENABLE_CLOUD_INIT=0
WPA_COUNTRY=${LIGHTPI_WIFI_COUNTRY:-US}
TIMEZONE_DEFAULT=${LIGHTPI_TZ:-UTC}
KEYBOARD_KEYMAP=${LIGHTPI_KEYMAP:-us}
KEYBOARD_LAYOUT="${LIGHTPI_KEYBOARD_NAME:-English (US)}"
LOCALE_DEFAULT=en_US.UTF-8
STAGE_LIST="stage0 stage1 stage2 lightpi-stage"
DEPLOY_COMPRESSION=xz
CFG

cd "${WORK}"
./build-docker.sh

mkdir -p "${HERE}/out"
cp "${WORK}"/deploy/*.img.xz "${HERE}/out/"
echo
echo "Done. Flash this file with Raspberry Pi Imager (Use custom):"
ls -1 "${HERE}"/out/*.img.xz
