# PTP Write Value Verification — Fujifilm Custom Slot

Tracks write values (domain value → PTP integer sent to camera) that still need
experimental confirmation. For most properties, a second independent source
confirmed that write values equal read values. The three properties below were
not written by that source and have no write-path evidence yet.

Test method: set `PROP_SLOT_CURSOR` to the target slot, write the value via
`set_property_uint16`, read back immediately, and visually confirm on the
camera body.

---

## DRangePriority (0xD191)

Read values confirmed from X-S10 direct reads. Write values assumed equal —
unverified.

| Domain value | Expected write value | Read-back | Camera body | Status |
|---|---|---|---|---|
| Off    | 0      | 0      | ✓ | ✅ confirmed 2026-03-26 X-S10 |
| Weak   | 1      | 1      | ✓ | ✅ confirmed 2026-03-26 X-S10 |
| Strong | 2      | 2      | ✓ | ✅ confirmed 2026-03-26 X-S10 |
| Auto   | 0x8000 | 0x8000 | ✓ | ✅ confirmed 2026-03-26 X-S10 |

---

## MonochromaticColorWarmCool (0xD193)

| Domain value | Write value | Read-back | Camera body | Status |
|---|---|---|---|---|
| −18 | 65356 (0xFF4C) | 65356 | ✓ | ✅ confirmed 2026-03-26 X-S10 |
| 0   | 0 (0x0000)     | 0     | ✓ | ✅ confirmed 2026-03-26 X-S10 |
| +18 | 180 (0x00B4)   | 180   | ✓ | ✅ confirmed 2026-03-26 X-S10 |

Encoding: int16 ÷ 10, range −18..+18. Write = read confirmed.

---

## MonochromaticColorMagentaGreen (0xD194)

| Domain value | Write value | Read-back | Camera body | Status |
|---|---|---|---|---|
| −18 | 65356 (0xFF4C) | 65356 | ✓ | ✅ confirmed 2026-03-26 X-S10 |
| 0   | 0 (0x0000)     | 0     | ✓ | ✅ confirmed 2026-03-26 X-S10 |
| +18 | 180 (0x00B4)   | 180   | ✓ | ✅ confirmed 2026-03-26 X-S10 |

Encoding: int16 ÷ 10, range −18..+18. Write = read confirmed.
