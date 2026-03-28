# ADR 001 — Camera bridge: PyUSB over raw PTP/USB

**Status**: Accepted
**Date**: 2026-03-21

---

## Context

This project reads film simulation recipes from image EXIF data and stores them. A natural next feature is writing a recipe back to a connected Fujifilm camera so a user can push a recipe directly onto the body without retyping every setting manually.

To do this, the application needs to communicate with the camera over USB. Three approaches were evaluated.

---

## Options considered

### Option A — Official Fujifilm Camera Control SDK (SDK13410)

Fujifilm distributes a proprietary SDK for tethered camera control. It ships pre-compiled shared libraries for Windows, macOS, and Linux (x64, ARMv7, ARMv8), so no C compilation is required on the developer's machine.

The SDK covers the recipe-relevant shooting parameters we care about: `SetFilmSimulationMode`, `SetGrainEffect`, `SetHighLightTone`, `SetShadowTone`, `SetNoiseReduction`, `SetClarityMode`, `SetColorChromeBlue`, `SetWhiteBalanceTune`, `SetDynamicRange`, `SetSharpness`, and others.

**Why we did not choose this option:**

1. **No custom program slot support.** Fujifilm cameras have C1–Cn custom program slots that let users store independent recipe configurations. The SDK has no API for writing to a specific slot — it can only write to the currently active shooting mode. This is the most important limitation: a user who wants to load recipe A into C1 and recipe B into C2 cannot do so through the SDK. Having investigated what PTP properties the camera exposes beyond the SDK's documented surface, we have evidence that the camera *does* accept writes to individual custom program slots via specific device properties — but those properties are not part of the SDK's public API.

2. **Requires tether/PC Priority mode.** The SDK requires the camera to be in "USB Tether Shooting" (PC Priority Mode). This is a different USB mode from the one used for recipe management, and it gives the connected computer control over shutter, focus, and other shooting functions that are unrelated to our use case.

3. **Complex deployment.** The Linux SDK is a `.tar.gz` containing `XAPI.so` and 20+ sibling `.so` files (`FF0000API.so` through `FF0022API.so`, `FTLPTP.so`, `FTLPTPIP.so`, `XSDK.DAT`) that all need to be present in the same directory. The macOS SDK is a `.zip` with bundle files. This is a deployment concern separate from Python packaging — it does not fit the `pip install -r requirements.txt` model.

4. **Proprietary licence.** The SDK cannot be redistributed beyond its stated terms, which constrains how the project can be distributed in the future.

### Option B — libfuji (C library via ctypes + compilation)

[petabyt/libfuji](https://github.com/petabyt/libfuji) is an open-source C library implementing the Fujifilm PTP protocol on top of `libpict` (camlib). It supports both USB and Wi-Fi connections and provides a higher-level API than raw PTP.

This was initially the chosen approach. A thin C "bridge" shared library (`fuji_bridge.c`) was designed to wrap libfuji and expose a flat API that Python's `ctypes` could load. The Python layer would never touch C code directly.

**Why we did not choose this option:**

1. **Requires C compilation on the developer's machine.** The build chain (`cmake`, `ninja`/`make`, `gcc`/`clang`, `libusb-1.0-dev`) differs by platform (Linux: `apt`, macOS: `brew` + Xcode Command Line Tools). This breaks the simplicity of the existing setup — a plain Python project where `pip install -r requirements.txt` is the only setup step.

2. **Submodule complexity.** libfuji itself depends on two git submodules (`libpict`/camlib and `fp`) that must be separately initialised before the build. This is a multi-step manual process that would need to be documented and maintained.

3. **Same custom slot coverage is achievable in Python.** The primary reason to reach for libfuji is its PTP/USB stack. But the PTP operations we need (`GetDevicePropValue`, `SetDevicePropValue`, `OpenSession`, `CloseSession`) are standard enough to implement directly in Python using PyUSB, keeping the custom-slot property codes alongside the standard ones.

### Option C — PyUSB (raw PTP/USB in Python) ✓ chosen

PyUSB is a Python library (`pip install pyusb`) that wraps `libusb`, the standard cross-platform USB library. It provides low-level USB bulk-transfer access from Python with no compilation step.

PTP (Picture Transfer Protocol, PIMA 15740:2000) is the protocol Fujifilm cameras use for computer communication. The operations we need — `OpenSession`, `CloseSession`, `GetDevicePropValue`, `SetDevicePropValue` — are straightforward to implement directly over USB bulk transfers. The entire implementation is approximately 250 lines of Python.

---

## Decision

Use **PyUSB** to implement raw PTP/USB communication.

The `PTPUSBDevice` class in `src/domain/camera/ptp_usb_device.py` sends and receives PTP packet frames over USB bulk endpoints, handling session lifecycle, integer property reads/writes, uint16 writes (for the slot cursor), and PTP string reads/writes (for slot names).

The domain layer remains clean: `operations.push_recipe()` and `queries.camera_info()` use the `PTPDevice` protocol and are unaware of the underlying transport.

---

## Rationale

| Criterion | SDK | libfuji + C | PyUSB |
|---|---|---|---|
| No C compilation | ✓ (pre-built) | ✗ | ✓ |
| Linux + macOS from `pip install` | ✗ (manual .so deploy) | ✗ | ✓ |
| Write to custom program slots (C1–Cn) | ✗ | ✓ | ✓ |
| No mandatory tether/PC Priority mode | ✗ | ✓ | ✓ |
| Open-source / freely distributable | ✗ | ✓ | ✓ |
| Maintenance surface | Fujifilm SDK versioning | C submodules + build | pyusb version pin |

---

## Runtime requirements

PyUSB requires `libusb` as a native runtime binary (not a build tool — no compiler needed):

| Platform | Install command |
|---|---|
| Linux (Debian/Ubuntu) | `sudo apt install libusb-1.0-0` |
| macOS | `brew install libusb` |

On **Linux**, USB devices are owned by `root` by default. Users need either a udev rule or membership in the `plugdev` group to access the camera without `sudo`. A udev rule should be documented (and potentially shipped) as part of the camera feature setup.

On **macOS**, libusb handles device access without additional configuration.

---

## Camera setup

The camera must be in a PTP-compatible USB mode — not USB Mass Storage. On most Fujifilm bodies this is labelled **USB RAW CONV. / BACKUP RESTORE** in the connection settings menu. In this mode the camera presents a PTP device interface that accepts `GetDevicePropValue` and `SetDevicePropValue` commands.

---

## Property codes

All device property codes used for recipe writing are documented in `src/data/camera/constants.py`. Two sets exist:

- **Normal-mode codes** — write to the currently active shooting mode.
- **Custom program slot codes** — write to a specific C1–Cn slot. These were identified by examining what PTP device properties the camera exposes beyond the official SDK surface. They are not documented by Fujifilm.

The slot cursor property (`0xD18C`) selects which custom slot subsequent slot-specific writes target. This is the mechanism that makes per-slot recipe writing possible — and the primary reason the official SDK was not sufficient.

---

## Consequences

- `pyusb==1.2.1` added to `requirements.txt`.
- `libusb` must be documented as a system-level prerequisite (not pip-installable).
- A udev rule document should be created before shipping the camera feature to Linux users.
