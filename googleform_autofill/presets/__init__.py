"""Preset registry — imports every named preset and exposes the registry."""
from .ai_survey import AI_SURVEY

PRESETS = {
    AI_SURVEY.name: AI_SURVEY,
}


def get_preset(name: str):
    """Return the preset registered under *name* (raises KeyError if absent)."""
    return PRESETS[name]
