# ADR 022: X-T2 backup-blob strategy

**Status**: Accepted
**Date**: 2026-10-31

Extends [ADR 021](021-camera-model-strategies.md), which opened a per-model
`CameraStrategy` seam on both the server and the browser and deferred the X-T2
strategy to a follow-up. This records how that second strategy works, and the
decisions its mechanism forces.

---

## Context

The X-T2 (and other pre-X-T3 bodies) have no per-slot PTP property interface. A
recipe is not a set of device properties on these bodies; it is a region of a
single fixed settings-backup blob (5660 bytes on the captured firmware). Reading
or writing one slot means reading, editing and restoring the whole blob. The
mechanism is proven on hardware: `GetObjectInfo`/`GetObject` read it,
`SendObjectInfo`/`SendObject` restore it, at object handle 0, with no checksum.

Three properties of the blob shape the design:

- **A global white balance.** Each white-balance entry (Auto, Daylight, ...) has
  one red/blue shift for the whole camera, shared by every slot that uses it, in
  a table separate from the slot records. Changing a recipe's shift changes it
  for every kept slot on that entry.
- **A reduced capability set.** Fifteen film simulations; no Color Chrome Effect,
  Color Chrome FX Blue, Clarity, D-Range Priority, or grain size.
- **No self-correcting write.** The blob is edited by fixed byte offset, so a
  wrongly-shaped blob would corrupt a write silently.

---

## Anatomy of the blob

The blob is one fixed-layout file. The parts the codec touches sit at known byte
offsets; everything else is carried through a push byte-for-byte.

```
 offset        X-T2 settings backup blob (5660 bytes, 0x0000..0x161C)
 +--------+----------------------------------------------------------------+
 0x0000   | Header                                                         |
          |   magic "FUJIFILMX-BACKUP0100X-T2", then size anchors:         |
          |   header_size=168 @0x98, body_size=5492 @0xA0, marker=1 @0xAC  |
 +--------+----------------------------------------------------------------+
 0x0195   | Global white-balance shift table                               |
          |   12 entries x 2 bytes = one (R, B) shift per WB mode          |
          |   (Auto, Daylight, Shade, Fluorescent 1..3, Incandescent,      |
          |    Underwater, Kelvin, Custom 1..3)                            |
 +--------+----------------------------------------------------------------+
 0x01AD   | Other camera settings (menus, custom functions, ...)           |
          |   not decoded; preserved unchanged across a push               |
 +--------+----------------------------------------------------------------+
 0x0ED8   | Live / lens drift region (0x0ED8..0x0EDD)                      |
          |   volatile device state; excluded from the read-back verify    |
 +--------+----------------------------------------------------------------+
 0x0F00   | Custom recipe slots: C1..C7, 7 x 256 bytes                     |
          |   C1 @0x0F00  C2 @0x1000  C3 @0x1100  ...  C7 @0x1500          |
 +--------+----------------------------------------------------------------+
 0x1600   | Tail                                                           |
 0x161C   +----------------------------------------------------------------+
```

Each recipe slot is 256 bytes with its own fixed field offsets (relative to the
slot start):

```
 one recipe slot (256 bytes)
   +0x16  write counter       (camera-managed; excluded from verify)
   +0x24  WB selector --------------.  picks WHICH white balance this slot uses
   +0x25  Kelvin index              |  (when the selector = Kelvin)
   +0x3E  noise reduction           |
   +0x45  film simulation           |
   +0x48  dynamic range             |
   +0x4C  color                     |
   +0x4E  sharpness                 |
   +0x4F  highlight                 |
   +0x50  shadow                    |
   +0x51  grain                     |
   +0x7E  name (32 bytes ASCII)     |
                                    v
        the (R, B) shift for that WB lives ONCE, in the global table at 0x0195,
        shared by every slot that selects it
```

That last arrow is the whole reason for the white-balance feasibility rule: a
slot records only which WB it uses; the shift for that WB is global, so two kept
slots on the same WB cannot carry different shifts.

## The operation: download, edit, upload

A push is never a per-field write. It downloads the whole blob, edits a few
regions in memory, and uploads the whole blob back, at PTP object handle 0.

```
   CAMERA (X-T2)                      FILMCASE (server or browser)
        |                                      |
        |  1. GetObjectInfo / GetObject        |
        | -------------- download ----------->  |   whole blob (5660 B)
        |                                      |
        |                                2. validate_backup
        |                                   (header + 7 slots + WB table parse,
        |                                    or refuse to touch it)
        |                                      |
        |                                3. edit in place:
        |                                   - slot Cn record (film sim, tones, ...)
        |                                   - global WB shift entry (only if needed)
        |                                   everything else left byte-for-byte
        |                                      |
        |  4. SendObjectInfo / SendObject      |
        | <------------- upload --------------  |   modified blob
        |                                      |
        |  5. GetObject again (verify on)      |
        | -------------- read back ---------->  |
        |                                6. compare the fidelity region
        |                                   (RecipeWriteError on any mismatch)
```

Steps 5 and 6 run only when `CAMERA_VERIFY_WRITES` is on, and the comparison
skips the live/drift region and the per-slot write counter. A collection push is
the same shape: it edits several slots and the shared WB table in one in-memory
blob, then uploads once.

---

## Problem

Drive the X-T2 as a second `CameraStrategy`, on both transports, without the use
cases or views learning its mechanism; push single recipes and whole collections
safely; and reflect its constraints in the UI before the user commits.

---

## Decisions

### Read-modify-restore behind the strategy seam

`BackupBlobStrategy` implements the same `CameraStrategy` surface as the
per-property one. `read_slots` decodes the blob; `push_recipe` reads the blob,
strictly validates it, maps the recipe to the X-T2 subset, checks feasibility,
edits the target slot and the global WB entry in place, and restores once. The
codec (`src/domain/camera/xt2_backup/`) is pure functions over bytes; the
strategy composes them over a connected device. No use case changed: `get_strategy`
returns this strategy for a backup-blob profile, and that is the only branch.

### A strict pre-write validation gate

Because the edit is by fixed offset, the blob read back must have the layout
assumed. `validate_backup` is a hard gate: it parses the header anchors, all
seven slot records, and the WB table, and a caller must refuse to edit or restore
a blob it does not pass. A shifted or wrong blob fails the parse rather than
corrupting a write.

### Unsupported fields are dropped, not rejected

A recipe carrying a field the X-T2 lacks (Clarity, CCE, CC-FX Blue, D-Range
Priority, grain size) is still pushable: `map_recipe` drops those fields and
reports them. Only a value the X-T2 cannot represent at all (a film simulation it
lacks, an out-of-range tone) raises `RecipeNotRepresentable`. The dropped fields
are surfaced in the picker before the push, not as a push result, so the per-
property push signature was left unchanged.

### The global white balance is a push-feasibility constraint

A push is refused when setting its WB entry's shift would retune a kept slot that
shares the entry. The slot picker greys out the conflicting slots with the
reason; the collection modal reports it up front. This has no per-property
analogue, so it lives only in the backup-blob strategy and reads as all-feasible
on the per-property path.

### Collection push is one restore, as one operation

A collection cannot be a loop of single-recipe pushes on the X-T2: it must
resolve the shared white balance across every recipe and restore once, and a
per-recipe loop would also mis-check cross-recipe WB feasibility. So
`push_collection_to_camera` is one use case that delegates to
`strategy.push_collection`: the per-property body writes each slot in turn (the
prior behaviour, now server-callable), the X-T2 edits one blob and restores once.
The collection read reports `single_operation`, and the interface drives one POST
(server) or one `strategy.pushCollection` (browser) instead of the per-recipe
loop for a backup-blob body.

### The write lock is lifted, with a verify-gated read-back as the safety net

ADR 021 left all X-T2 writes locked. That lock is lifted: the push performs a
live restore on user action, like the X-S10 push. The safety net is the existing,
shared `CAMERA_VERIFY_WRITES` setting: with it on, the strategy reads the blob
back after restoring and raises `RecipeWriteError` on any fidelity-region
mismatch (excluding the live/drift region and the camera-managed per-slot
counter). The restore status read uses a longer `CAMERA_RESTORE_TIMEOUT_MS`
because a settings commit takes seconds, and a lost status ack is tolerated
(`RestoreAckTimeout`): the write may have applied, so the outcome is confirmed by
read-back rather than by re-sending a settings commit. Hard rails remain: only a
strictly-validated, pristine-pull-derived blob is ever restored, never one built
from scratch, and the vendor firmware path (the `0x900C` family) is not used.

### The browser mirror runs the same codec on the served layout

The browser is a second implementation (ADR 016), so it gains the whole strategy:
`getBackup`/`restoreBackup` over WebUSB, a JS port of the codec, and a
`BackupBlobStrategy` selected by the served interface. The X-T2 byte layout, the
client's copy of `constants_xt2`, is served in the client config rather than
duplicated, and the JS codec is asserted byte-for-byte against the same committed
pristine blob as the Python codec, on a committed fixture of that served layout
that a Python test guards against drift.

---

## Consequences

The X-T2 is a fully supported push target on both transports: the picker greys
out infeasible slots and warns about dropped fields, and the push refuses an
unrepresentable or infeasible recipe with a reason before writing anything. The
per-property path is unchanged; its collection push is now a server-callable use
case rather than only a client loop.

The cost is a second codec maintained in two languages. The golden-fixture
discipline (ADR 016) contains it: both sides decode the same committed blob, and
the served-layout fixture cannot drift from `constants_xt2` without a test
failing. The byte layout is X-T2 specific, so the backup-blob profile stays an
explicit per-model opt-in; a future body with a similar but not identical backup
would get its own layout, with any genuinely shared logic lifted out of
`xt2_backup` then, not before.
