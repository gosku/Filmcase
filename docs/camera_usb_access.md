# Camera USB Access on Linux

## Why the error occurs

When you connect a camera, Linux recognises it as a PTP/MTP device and GNOME's
`gvfs-gphoto2-volume-monitor` (or a similar daemon) automatically claims the USB
interface.  When this app then tries to open the same interface it gets
`[Errno 16] Resource busy`.

This page is written for the server-side transport, where the Django process
opens the device.  Everything on it applies equally when `CAMERA_TRANSPORT` is
`browser`: the browser needs the same permission on the same device, and loses
to the same daemon.  Substitute "your browser" for "this app" throughout.  See
[Pushing Recipes from the Browser](camera_webusb.md) for what browser mode adds
on top, which is a secure context and a Chromium browser.

There are two things to fix:

1. **Permissions** — your user account must be allowed to open the raw USB device
   without `sudo`.
2. **Auto-claim** — the GNOME volume monitor must be told not to grab Fujifilm
   cameras so this app can claim the interface instead.

---

## Step 1 — identify the device

```bash
lsusb | grep -i fuji
```

Example output:

```
Bus 003 Device 007: ID 04cb:0234 Fujifilm Corp. X-T5
```

Note the bus and device numbers (here `003` and `007`).

---

## Step 2 — add a udev rule (permanent fix)

Create a new rules file:

```bash
sudo nano /etc/udev/rules.d/70-fujifilm-camera.rules
```

Paste the following two lines:

```
# Grant read/write access to all Fujifilm cameras (vendor 04cb)
SUBSYSTEM=="usb", ATTRS{idVendor}=="04cb", MODE="0666", TAG+="uaccess"

# Prevent gvfs / gphoto2 from auto-claiming the interface
SUBSYSTEM=="usb", ATTRS{idVendor}=="04cb", ENV{ID_GPHOTO2}="0", ENV{GPHOTO2_DRIVER}=""
```

Reload and apply the rules:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb
```

Unplug the camera, wait a second, then reconnect it.

---

## Step 3 — disable the gvfs volume monitor (if the error persists)

Even with the udev rule in place, a running `gvfs-gphoto2-volume-monitor`
may have already spawned a `gvfsd-gphoto2` daemon that holds the interface.
Stop both:

```bash
systemctl --user stop gvfs-gphoto2-volume-monitor.service
pkill -x gvfsd-gphoto2 2>/dev/null; true
```

Then mask the monitor so it never starts again:

```bash
systemctl --user mask gvfs-gphoto2-volume-monitor.service
```

To re-enable it later (e.g. if you use another app that needs gphoto2):

```bash
systemctl --user unmask gvfs-gphoto2-volume-monitor.service
```

---

## Quick fix (without a udev rule)

If you just want to test right now without writing a udev rule:

```bash
# Find your bus/device numbers with lsusb, then:
sudo chmod a+rw /dev/bus/usb/<bus>/<device>
systemctl --user stop gvfs-gphoto2-volume-monitor.service 2>/dev/null; true
```

This resets on every reconnect, so the permanent udev rule is recommended for
regular use.

---

## Verify

```bash
python manage.py camera_info
```

You should see `Camera connected` without needing `sudo`.
