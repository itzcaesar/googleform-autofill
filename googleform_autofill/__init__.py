"""googleform_autofill — core engine package."""
from .form import parse_form_entries, fill_form_entries, get_form_submit_request
from .realism import Calibration, compute_traits, choose_occupation, validate_record
from .presets import get_preset, PRESETS

__all__ = [
    "parse_form_entries", "fill_form_entries", "get_form_submit_request",
    "Calibration", "compute_traits", "choose_occupation", "validate_record",
    "get_preset", "PRESETS",
]
