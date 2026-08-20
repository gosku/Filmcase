# Pushing recipes from the browser

Filmcase can talk to your camera in one of two ways, chosen by the `CAMERA_TRANSPORT` setting.

| Value | Where the camera is plugged in | How it talks |
|---|---|---|
| `server` (default) | The machine running Filmcase | PyUSB, in the Django process |
| `browser` | The machine you browse from | WebUSB, in the page |

Server mode is the right choice when Filmcase runs on your own desktop. Browser mode exists for the case server mode cannot cover: Filmcase running somewhere you do not sit, a NAS or a home server, with the camera on your desk.

Nothing else changes. The recipes, the slots and the result are the same either way, and the same code decides what to write; only the machine holding the USB cable differs.

---

## Turning it on

Docker, in `.env`:

```
CAMERA_TRANSPORT=browser
```

Native install, in `src/config/env`:

```
CAMERA_TRANSPORT=browser
```

Restart Filmcase. Open a named recipe and click **Send to camera**. The first time, the browser asks which device to use; pick the camera. It will not ask again.

---

## What browser mode needs

Three things, and it is worth checking them before wondering why nothing happens. Open `/camera/diagnostics/` and run the probe: it reports each one.

### A secure context

Browsers only expose USB to a secure context: an HTTPS origin, or `localhost`. **Plain HTTP to a LAN address never qualifies**, even though the camera is right there and everything else on the page works. There is no browser flag worth shipping that changes this.

For a Docker install this means reaching Filmcase on its HTTPS port rather than by IP over HTTP. A self-signed certificate is enough: the browser checks the scheme, not whether the certificate is trusted, so accepting the warning once is sufficient. See [Running in Docker](docker.md) for the certificate setup.

### A Chromium browser

WebUSB is Chromium-only. Chrome, Edge, Brave and Opera have it; Firefox and Safari do not, and have no plans to. In those browsers the button explains itself rather than failing silently.

### Permission on the USB device

The browser needs the same access to the raw USB node that the server-side path needs, and for the same reasons. On Linux that usually means libgphoto2's udev rules, and it usually means stopping whatever already claimed the camera. See [Camera USB Access on Linux](camera_usb_access.md); everything there applies to the browser process instead of the Django process.

---

## How the permission works

The browser remembers the camera per origin. You are asked once, and from then on Filmcase finds it silently, across page loads and browser restarts.

You will be asked again if any of these change:

- **The address.** `https://filmcase.local:8443` and `http://localhost:8000` are separate origins with separate grants.
- **The camera.** The grant is per device, so a second body needs its own.
- **The browser profile.** Private windows never keep grants, and clearing site data drops them.

The camera also has to be plugged in and awake for Filmcase to find the remembered grant. Unplugging does not revoke it; the entry comes back when you reconnect.

---

## When something goes wrong

The push reports the same messages the server-side path does, because the same failures happen either way.

**"No camera found."** The camera is not connected, is asleep, or is in the wrong USB mode. It needs to be in PC Connection or RAW CONV. mode, not USB Mass Storage.

**"Some settings couldn't be saved (…)."** The camera accepted the recipe but refused those particular settings, and the rest were written. This is usually a setting the camera will not accept in its current state rather than a fault; the DR400 case in the troubleshooting notes is the known example, where the camera declines a dynamic range its current ISO cannot support.

**"This recipe can't be written to the camera: … is not valid."** The recipe itself holds a value the camera cannot take. This one is fixable in Filmcase rather than at the camera.

**It takes a few seconds and then works.** Some cameras intermittently accept a
request and never answer it. Filmcase retries, and escalates to resetting the
camera's PTP state if retrying is not enough, so a stall costs a pause rather
than a failure. `CAMERA_USB_TIMEOUT_MS` controls how long each attempt waits
before giving up on one transfer; lower it if the pauses are annoying and your
camera is otherwise reliable.

**Nothing happens at all.** Open the browser console. If a module failed to load you will see it there, and `/camera/diagnostics/` will confirm whether the browser can reach a camera from this address at all.

### Getting more detail

Every read and write is recorded in the page. In the browser console:

```js
FilmcaseCameraEvents.recent()
```

That returns the sequence of operations for the current page, most recent last, including which property failed and the response code the camera gave. It is the browser's equivalent of the `camera.ptp_write.*` events the server logs, and it is the most useful thing to include when reporting a problem.

---

## A note on speed

A push writes around twenty properties, each with a short pause on either side, because the hardware needs them. It takes a couple of seconds.

If you switch to another tab mid-push it will take considerably longer. Chrome slows timers in hidden tabs to at most one per second, which stretches those pauses. The push still completes correctly; it just crawls. Leave the tab in front while it runs.

---

## For contributors

The browser-side code lives in `src/interfaces/static/js/camera/`, layered `interfaces -> application -> domain -> vendor`, with module names mirroring their Python counterparts so the two can be read side by side.

There is no build step. The browser loads the same files the tests import.

The encoding tables are served from `camera/client-config.json` rather than duplicated, so a table added on the server needs no second edit. Behaviour is pinned by four fixtures in `tests/fixtures/camera/` that both suites assert, covering the wire format, the recipe conversion, the validation outcomes and the push sequence. A change to the Python write path fails the JavaScript suite, and the other way round.

Run the JavaScript tests with `make test-js`. See [Contributing](contributing.md) and [ADR 016](ADRs/016-client-side-camera-transport.md).
