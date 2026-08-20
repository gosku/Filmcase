# ADR 016 — Client-side camera transport over WebUSB

**Status**: Accepted
**Date**: 2026-08-20

Extends [ADR 001](001-camera-bridge.md), which chose PyUSB over raw PTP/USB and, implicitly, chose to run that transport on the server. Both transports now ship; this records why the second one exists and what it costs.

---

## Context

ADR 001 settled how Filmcase talks to a camera: raw PTP/USB over PyUSB, because the official SDK cannot write to a custom program slot. It did not examine *where* that conversation happens, because at the time there was only one answer. `PTPUSBDevice` runs inside the Django process, so the camera has to be plugged into whatever machine runs Filmcase.

That assumption held while Filmcase was something you ran on your own desktop. It stopped holding when the app started shipping as a container. A NAS, a home server, or any box you do not sit in front of can run Filmcase perfectly well, and the camera is still on the desk. In that arrangement every other feature works and "Send to camera" is simply impossible: the server scans a USB bus that will never have a camera on it.

---

## Problem

Move the transport to the machine the user is sitting at, without ending up with two implementations that quietly disagree about what to write to a camera.

The second half is the hard part. The write path is not a thin wrapper over a documented API. It is a set of undocumented property codes, a non-linear noise reduction table, a sentinel value for grain, an ordering rule where the colour temperature must precede the white balance shifts, and a set of delays that exist because the hardware needs them. Any of those getting out of step between two implementations produces a recipe that looks correct in the app and is wrong on the camera, which is the worst failure this feature has: silent, and only visible in a photograph taken later.

---

## Decisions

### The browser talks to the camera over WebUSB

A `CAMERA_TRANSPORT` setting selects `server` or `browser`. Server mode is unchanged and remains the default. Browser mode moves the slot listing and the recipe push into the page.

The alternative was an agent process on the user's machine that the server talks to. That solves the same problem and adds an install step, a second thing to keep running, and a protocol between them. The browser is already there.

### The encoding tables are served, not duplicated

`camera/client-config.json` serves the property codes, the value tables and the eight `CAMERA_*` timing settings. The browser holds no copy.

This is the single most important decision for keeping the two in step. A film simulation added to `constants.py` reaches the client on the next request, with no generated file, no CI diff check, and nothing for a contributor to remember. The client is served the write order too, so both sides order their writes from one list.

### The behaviour is pinned by golden fixtures both suites assert

Four shared fixtures, generated from the Python and asserted independently by the Python and JavaScript suites: the wire format, the recipe conversion, the validation accept/reject table, and the push sequence itself including its pauses and its failure modes.

Serving the tables removes the risk of the *data* diverging. These remove the risk of the *behaviour* diverging, which is the part serving cannot help with. A change to `push_recipe.py` fails the JavaScript suite, and vice versa.

### The JavaScript is layered, with a vendor layer in place of a data layer

`interfaces -> application -> domain -> vendor`. There is no data layer because the client owns no database. What it has instead is a vendor layer for everything outside the browser: the Filmcase backend, and the camera.

That is why `ptp_usb_device.js` sits in vendor while `ptp_usb_device.py` sits in `src/domain/camera/`. It speaks a foreign protocol to a foreign system. The `PTPDevice` protocol is the domain-facing contract; the transport behind it is not domain logic in either codebase. The Python placement is worth revisiting on its own terms and was left alone here.

### No build step

Native ES modules, no bundler, no dependencies. The browser loads the same files the tests import. Node is needed to run the tests and by nothing else, so it is a contributor requirement rather than an install requirement.

---

## Consequences

### What this buys

A headless install becomes fully usable. This was the entire point.

Linux permissions get simpler for the common case. The browser's per-origin consent replaces the udev rule for most users, though the underlying permission on the raw USB node still applies to the browser process.

### What it costs

**Two implementations of the write path.** The fixtures make divergence loud rather than silent, but a change to the push sequence now means changing it twice. Module names mirror the Python one for one so the two can be read side by side.

**A recovery path with no server-side counterpart.** Around 250 lines that exist because the browser cannot cancel a transfer. It is exercised by fakes built to match observed traces, not by hardware in CI, so it is the part of this feature most likely to need revisiting when a different camera model turns up.

**Browser mode only works in a secure context.** WebUSB needs HTTPS or `localhost`. Plain HTTP to a LAN address never qualifies, whatever the browser flags suggest, so a Docker install has to be reached over its HTTPS port. `camera/diagnostics/` answers this in one click and the failure card links to it.

**Chromium only.** Firefox and Safari have no WebUSB. The button degrades to a card explaining why rather than a dead click.

**A push leaves no server-side record.** Server mode publishes `camera.ptp_write.*` into the event log; the browser cannot. Events go to `console.debug` and a bounded buffer readable as `FilmcaseCameraEvents.recent()`, which is enough to support a user over a chat. A reporting endpoint was deliberately deferred until there is evidence anyone needs it.

### The browser needs a recovery mechanism the server does not

This is the one substantial behavioural difference, and it was not anticipated. It emerged from testing against a real X-S10, which intermittently accepts a request and never answers it.

An earlier draft of this ADR recorded the opposite decision: that a timed-out transfer should be fatal to the connection, on the reasoning that a late reply would desynchronise the stream. That reasoning was wrong, and the hardware said so. Retrying in place is what the server does and it recovers every time, which means the camera drops the request rather than deferring it: nothing is queued, so nothing goes stale. The transaction ids are checked at runtime and have never disagreed.

What the browser does need is a way to unstick itself, for two reasons the server does not share.

WebUSB cannot cancel a transfer. `Promise.race` abandons the promise while the read stays queued, and a camera that never answers leaves every later read waiting behind one that cannot finish. libusb genuinely cancels, so PyUSB's retry reads against a free endpoint while the browser's never got to read at all.

Reopening the USB device does not help either. PTP state lives above USB: after a full close, open and claim, the camera still answered `OpenSession` with `SessionAlreadyOpen`, still holding the session its stuck transaction belonged to. `Device Reset`, a class control request on endpoint 0, is what clears it.

So the browser escalates: `Cancel Request` and a drain first, then reopen with `Device Reset` if a second stall follows. The slot cursor is restored afterwards, because it is connection state and every later write goes to whichever slot the camera is pointing at.

None of this exists server-side, and it is not obvious whether it should. The server has never been observed to hit the stall, plausibly because WebUSB's per-transfer overhead is what pushes this camera over the edge. Worth revisiting if it ever does.
