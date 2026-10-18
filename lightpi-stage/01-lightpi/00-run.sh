#!/bin/bash -e
# LightPi stage: install the shell, compositor config and kiosk autologin.

USER_NAME="${FIRST_USER_NAME}"
HOME_DIR="${ROOTFS_DIR}/home/${USER_NAME}"

# --- LightPi shell ---------------------------------------------------------
install -d -m 755 "${ROOTFS_DIR}/opt/lightpi"
install -m 755 files/opt-lightpi/lightpi.py        "${ROOTFS_DIR}/opt/lightpi/lightpi.py"
install -m 755 files/opt-lightpi/start-lightpi.sh  "${ROOTFS_DIR}/opt/lightpi/start-lightpi.sh"

# --- per-user compositor + login config -------------------------------------
install -d -m 755 -o 1000 -g 1000 "${HOME_DIR}/.config" "${HOME_DIR}/.config/labwc"
install -m 644 -o 1000 -g 1000 files/labwc/rc.xml    "${HOME_DIR}/.config/labwc/rc.xml"
install -m 755 -o 1000 -g 1000 files/labwc/autostart "${HOME_DIR}/.config/labwc/autostart"
install -m 644 -o 1000 -g 1000 files/bash_profile    "${HOME_DIR}/.bash_profile"

# --- autologin on tty1 -------------------------------------------------------
install -d -m 755 "${ROOTFS_DIR}/etc/systemd/system/getty@tty1.service.d"
cat > "${ROOTFS_DIR}/etc/systemd/system/getty@tty1.service.d/autologin.conf" <<EOF_GETTY
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${USER_NAME} --noclear %I \$TERM
EOF_GETTY

on_chroot << EOF_CHROOT
systemctl set-default multi-user.target
systemctl enable getty@tty1.service
EOF_CHROOT
