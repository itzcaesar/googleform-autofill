# Backward-compatibility shim — real implementation lives in
# googleform_autofill/presets/.
from googleform_autofill.presets import PRESETS, get_preset  # noqa: F401
from googleform_autofill.presets.ai_survey import Preset      # noqa: F401
