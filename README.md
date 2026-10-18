# LightPi OS 0.1

An Android-inspired, touch-friendly mobile interface on Raspberry Pi OS Lite (Debian 13 "trixie", 64-bit).

**Target:** Raspberry Pi 4B (1 GB) · HDMI display · 32 GB microSD

**Included:** lock screen (optional PIN) · home screen · Wi-Fi manager · file manager · settings ·
on-screen keyboard · web browser launcher (Chromium) · auto-start into LightPi

**Not included yet:** NAS/CasaOS app store and updates (planned for a later release).

## Get the image (easiest: GitHub Actions)

1. Create a new GitHub repository and upload everything in this folder (keep the `.github` folder).
2. Open the repo's **Actions** tab, pick **Build LightPi OS image**, click **Run workflow**.
   Set your Wi-Fi country, time zone and a password (default login is `lightpi` / `lightpi`).
3. Wait for the run to finish (about 1 to 2 hours on `ubuntu-latest`, about 20 to 30 minutes on `ubuntu-24.04-arm` for public repos).
4. Download the `LightPi-OS-0.1` artifact, unzip it, and you get `LightPi-OS-0.1.img.xz`.

## Or build on your own Linux PC

```bash
./build-local.sh          # needs git + docker, ~15 GB free
# optional: LIGHTPI_PASS=secret LIGHTPI_WIFI_COUNTRY=GB LIGHTPI_TZ=Europe/London ./build-local.sh
```
The image appears in `out/`.

## Flash it

1. Install **Raspberry Pi Imager**.
2. Choose Device: *Raspberry Pi 4*, OS: *Use custom* and pick the `.img.xz` file, Storage: your 32 GB card.
3. If Imager offers OS customisation, skip it (the image is already configured).
4. Put the card in the Pi, connect HDMI + USB keyboard/mouse, power on.
   The first boot expands the filesystem and then shows the LightPi lock screen.

## Using it

| Action | How |
| --- | --- |
| Unlock | Tap the lock screen (or enter your PIN if you set one) |
| Back / Home / Lock | The three buttons on the bottom bar |
| Connect Wi-Fi | Wi-Fi app, tap a network, enter the password with the on-screen keyboard |
| Browse the web | Browser app, type an address or search, tap Go. Close the Chromium window (or press `Super+Esc`) to return to LightPi |
| Set a PIN, reboot, shut down | Settings app |
| Console login | `Ctrl+Alt+F2` on a keyboard, or SSH to `lightpi.local` |

## Troubleshooting

* **Black screen / back to login prompt:** press `Ctrl+Alt+F2`, log in, and read `~/lightpi.log`.
* **Wrong login or Wi-Fi country:** rebuild with different workflow inputs.
* **Browser has no on-screen keyboard:** only LightPi's own text fields have one so far. Use a USB keyboard inside web pages for now.
* **Touchscreen:** USB HDMI touch screens work as a mouse. GPIO screens need their own driver (not covered in 0.1).

## Layout

```
lightpi-stage/                 pi-gen stage that turns Raspberry Pi OS Lite into LightPi
  00-install-packages/         apt packages (labwc, xwayland, python3-tk, chromium, fonts)
  01-lightpi/00-run.sh         installs the shell, autologin and compositor config
  01-lightpi/files/opt-lightpi/lightpi.py   the LightPi interface (Python + Tkinter)
.github/workflows/build-image.yml          cloud build
build-local.sh                 local Docker build
```
