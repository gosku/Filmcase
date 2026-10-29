# ADR 021: Per-model camera strategies

**Status**: Accepted
**Date**: 2026-10-29

Extends [ADR 001](001-camera-bridge.md), which chose raw PTP/USB over PyUSB and,
with it, the custom-slot property interface as the one way to read and write a
camera. Extends [ADR 016](016-client-side-camera-transport.md), whose browser
transport must mirror whatever the server decides to write. This records why the
camera code now resolves a per-model strategy instead of assuming one interface.

---

## Context

Every camera path in the app assumes one mechanism: a slot cursor selects a
custom slot and each recipe field is its own PTP device property. That is how the
X-S10 and every body from the X-T3 onward work, and ADR 001 settled it when there
was only one camera to support.

The X-T2 (and other pre-X-T3 bodies) do not have that interface at all. On those
bodies the recipes live inside a single settings backup blob; reading or writing
one means reading, editing and restoring the whole blob, with its own byte
encodings, a white balance that is global rather than per slot, a smaller set of
supported fields, and a strict pre-write validation of the blob. None of that
fits behind the per-property assumption, and scattering `if model == ...` through
the use cases would spread the difference everywhere it is read or written.

---

## Problem

Support two fundamentally different camera mechanisms without the use cases, the
views, or the browser client having to know which one they are driving, and
without duplicating the orchestration (connect, retry, disconnect, error
translation) that both share.

---

## Decisions

### A strategy is the middle layer between the use case and the primitives

A `CameraStrategy` owns the model-specific algorithm (read slots, validate a
recipe, push a recipe). A use case resolves a strategy from the camera model and
delegates to it, staying thin: it manages only the connection lifecycle and
error translation. `get_strategy(camera_name)` is the single resolution point;
the X-T2 backup-blob strategy is added there, selected on the profile's
interface, without any caller changing.

The strategy is pure: it receives an already-connected device and never opens or
closes it. That keeps the lifecycle in one place (the use case) and makes the
strategy testable against a fake device.

### Capability differences are data, in a per-model profile

A `CameraProfile` describes what one model accepts: the valid value set for each
recipe field, and which interface drives it. Recipe validation reads the allowed
values from the profile rather than from hard-coded sets, so one validator serves
every model: a value an older body lacks fails for that body and passes for one
that has it.

Profiles are keyed per model, not per sensor. Two bodies on the same sensor can
differ (the X-T4 has more film simulations than the X-T3), so sensor generation
is too coarse to key on. The existing `CAMERA_TO_SENSOR` table keeps its separate
job of tagging an imported JPEG's sensor.

### An unknown model falls back to the per-property profile

`get_profile` returns the per-property profile for any model it does not know,
rather than refusing. This preserves the prior behaviour, which assumed the
per-property interface for any connected camera, and it means a body the app has
never heard of is still driven on the common path rather than rejected. A precise
per-model support list can be introduced later; for now every camera is assumed
supported.

### The refactor is applied to both implementations

The browser client (ADR 016) is a second implementation of the same read and
push algorithm, not just a consumer of served data, so the strategy seam is
opened on both sides in this change. The JavaScript gains a `domain/strategies.js`
with a `PerPropertyStrategy` and `getStrategy`, and its use cases become thin
delegators, mirroring the Python one for one. This is what lets the X-T2
backup-over-WebUSB strategy slot into the browser in the follow-up exactly as the
X-T2 backup-over-PTP strategy slots into the server: a refactor that touched only
Python would leave the browser unable to gain the second strategy without first
doing this same refactor under the pressure of the new feature.

Where the Python strategy reads a model's capabilities from a `CameraProfile`,
the client reads them from the served config, which ADR 016 already keeps as the
single source of truth for both transports. The client has a served vendor layer
in place of a data layer, so the served config is the client's profile; there is
no separate client-side profile object to keep in step.

---

## Consequences

### What this buys

The X-T2 backup-blob strategy drops in as a second `CameraStrategy` and a second
`CameraProfile`, selected by `get_strategy`, with no change to the use cases or
the views. Model-relative validation already works: the X-T2 profile carries its
smaller field set and reduced film-sim list, and the shared validator enforces
it.

### What it costs

The push algorithm and the per-property slot read moved out of the use cases into
the strategy, on both sides, so `RecipeWriteError` now lives in the domain (where
the strategy raises it) and is re-exported by the push use case for its public
contract, in both the Python and the JavaScript. This is a behaviour-preserving
move; the existing camera tests pass unchanged on both sides, which is the proof.

### What is deferred

This change (PR 1) is the refactor only, on both the server and the browser. The
X-T2 strategy (as a backup read-modify-restore over PTP on the server and over
WebUSB in the browser), the backup codec, the blob transport opcodes
(`GetObject`/`SendObject`, both retried and lost-ack tolerant), the
global-white-balance push feasibility, and collection push as a first-class use
case all land in the follow-up. Until then the `CameraStrategy` surface carries
only the methods the per-property path needs (`read_slots`, `validate_recipe`,
`push_recipe`); it grows the backup-oriented methods (`read_slot_recipe`,
`validate_backup`, collection push) when their callers arrive, so nothing is dead
code.

`get_camera_status` keeps its own tolerant slot read (it returns blanks for a
body that does not serve a field, rather than retrying), because that read has
different semantics from the strategy's and nothing is gained by forcing it
through the same path yet.

All X-T2 camera writes remain write-locked: the push path can be built and tested
against captured blobs, but no live restore happens without explicit per-action
authorization, to avoid bricking the camera.
