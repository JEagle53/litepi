# LightPi OS

**An Android-inspired, touch-friendly interface for the Raspberry Pi 4.**
LightPi boots straight into a phone-style home screen. There is no desktop, just a lock screen, a launcher and a few essential apps. It is built on Raspberry Pi OS Lite (64-bit) and stays light enough for the 1 GB Pi 4.

> **Status: version 0.1, early release.** Built to run on a Raspberry Pi 4B (1 GB) with an HDMI or USB touchscreen and a 32 GB microSD card.

---

## What's inside

| App | What it does |
| --- | --- |
| **Lock screen** | Clock and date. Tap to unlock, or set a PIN in Settings. |
| **Home screen** | App icons, a big clock, and an Android-style Back / Home / Lock bar. |
| **Wi-Fi** | Scan networks, connect with a password, disconnect, turn Wi-Fi on or off. |
| **Files** | Browse folders, preview text files, delete files. |
| **Browser** | Type an address or a search and open it in Chromium. |
| **Settings** | Device info (IP, memory, storage, temperature), lock PIN, reboot, shut down. |
| **On-screen keyboard** | Appears whenever you tap a text field inside LightPi. |

**Not in 0.1:** app store and update server (planned), an on-screen keyboard inside Chromium, swipe gestures, and drivers for small GPIO screens.

---

## Get the image

The image is built in the cloud with GitHub Actions, so you don't need Linux.

1. Open the **Actions** tab of this repository.
2. Click **Build LightPi OS image** in the left sidebar, then **Run workflow**.
3. Fill in the form:
   - **password:** choose your own (the default is `lightpi`)
   - **wifi_country:** two letters, for example `GR`, `US`, `GB`
   - **timezone:** for example `Europe/Athens`
4. Click the green **Run workflow** button and wait (about 35 minutes in the last successful run).
5. When the run shows a green tick, scroll to **Artifacts** and download **LightPi-OS-0.1**.
6. Unzip it. The image file is inside.

You can also build on your own Linux PC with Docker by running `./build-local.sh`. The image appears in `out/`.

## Flash it

1. Install **Raspberry Pi Imager**.
2. Choose **Raspberry Pi 4** as the device, **Use custom** as the OS (pick the image file), and your microSD card.
3. If Imager offers OS customisation, choose **No**. The image is already configured.
4. Insert the card, connect the screen and a keyboard, and power on. The first boot takes a minute or two.

Default login for the console and SSH: user `lightpi` and the password you chose in the form.

---

## Using LightPi

| To do this | Do this |
| --- | --- |
| Unlock | Tap the lock screen, or enter your PIN |
| Go back / Home / Lock | Use the three buttons on the bottom bar |
| Connect to Wi-Fi | Wi-Fi app, tap a network, type the password |
| Leave the browser | Close the Chromium window, or press `Super+Esc` |
| Open a text console | `Ctrl+Alt+F2` on a keyboard |
| Reach it from another computer | `ssh lightpi@lightpi.local` |

## Troubleshooting

- **Text login instead of LightPi:** press `Ctrl+Alt+F2`, log in, and read `~/lightpi.log`.
- **Touch lands in the wrong place:** this is a screen mapping problem. Open an issue with your screen model.
- **Web pages need typing:** Chromium has no on-screen keyboard yet, so use a USB keyboard.
- **Build fails in Actions:** open the failed run, click the red step, and copy the last 20 lines of the log.

---

## Repository layout

```
.github/workflows/build-image.yml     cloud build (GitHub Actions)
build-local.sh                        local Docker build
lightpi-stage/                        pi-gen stage that turns Raspberry Pi OS Lite into LightPi
  00-install-packages/                packages: labwc, xwayland, python3-tk, chromium, fonts
  01-lightpi/00-run.sh                installs the shell, autologin and compositor config
  01-lightpi/files/opt-lightpi/       the LightPi interface (Python + Tkinter)
```

## Roadmap

- Chromium on-screen keyboard
- Support for more touchscreens
- App store and updates served from a home NAS
- Swipe gestures and a nicer UI toolkit

LightPi is a personal project and comes with no warranty. Raspberry Pi is a trademark of Raspberry Pi Ltd, and this project is not affiliated with it.
