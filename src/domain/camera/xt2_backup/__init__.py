"""
X-T2 settings-backup codec.

Pure functions over the backup blob bytes: decode slots, strictly validate the
layout, map a recipe onto the X-T2 capability subset, check push feasibility
against the global white balance, edit recipe bytes in place, and verify a
restore read back faithfully. No camera access and no DB; the BackupBlobStrategy
composes these over a connected device.
"""
from __future__ import annotations

from ._apply import apply_recipe
from ._apply import apply_recipes
from ._decode import decode_slot_recipe
from ._decode import decode_slot_states
from ._feasibility import Feasibility
from ._feasibility import check_collection_feasibility
from ._feasibility import check_feasibility
from ._mapping import RecipeNotRepresentable
from ._mapping import Xt2Mapping
from ._mapping import map_recipe
from ._validate import BackupValidationReport
from ._validate import validate_backup
from ._verify import RoundTripResult
from ._verify import verify_round_trip

__all__ = [
    "BackupValidationReport",
    "Feasibility",
    "RecipeNotRepresentable",
    "RoundTripResult",
    "Xt2Mapping",
    "apply_recipe",
    "apply_recipes",
    "check_collection_feasibility",
    "check_feasibility",
    "decode_slot_recipe",
    "decode_slot_states",
    "map_recipe",
    "validate_backup",
    "verify_round_trip",
]
