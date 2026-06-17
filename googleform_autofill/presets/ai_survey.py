"""Preset: Survei Tingkat Adopsi Teknologi AI di Masyarakat.

Demographic target — a predominantly student / young-adult Indonesian sample:
  <18   ~10 %   (SMP / SMA students)
  18-25 ~50 %   (SMA akhir + mahasiswa + fresh grad)
  26-35 ~27 %   (young working adults)
  36+   ~12 %   (small senior tail)

Timing target — believable human pacing for a 19-question survey:
  Recommended --delay: 45 (fast), 60 (typical), 90 (careful)
  human_delay() adds natural variance: median ≈ base, mean higher,
  ~10% of responses have a longer "distracted" gap.

Provider mix: consumer-only domains (no company/corporate addresses).
Email style: no leet-speak/alpha — only genz + millennial + professional
  produce realistic-looking Indonesian names without the "bot tell" of
  handles like r4yh4n.h3al1ng or kevin.goat.
"""

from dataclasses import dataclass, field
from typing import Dict, List

try:
    from googleform_autofill.realism import Calibration
except ImportError:
    from realism import Calibration  # type: ignore[no-redef]


@dataclass
class Preset:
    name: str
    description: str
    main_kwargs: Dict = field(default_factory=dict)
    calibration: Calibration = field(default_factory=Calibration)
    conditionals: List[dict] = field(default_factory=list)


AI_SURVEY = Preset(
    name="ai-survey",
    description="Survei Tingkat Adopsi Teknologi AI di Masyarakat",
    main_kwargs=dict(
        random_email=True,

        # ------------------------------------------------------------------ #
        # Target demographic: pelajar (SMP/SMA), mahasiswa, and working
        # masyarakat — roughly 15-40 years old. No >45 respondents.
        #
        # Style → age mapping (STYLE_AGE_RANGES):
        #   alpha        13-17  →  <18 pelajar SMP/SMA slice
        #   genz         17-27  →  mahasiswa + fresh grad bulk
        #   millennial   28-43  →  young working adults (capped at 40 below)
        #   chinese      17-50  →  small name-diversity mix
        # "professional" (27-50) and "classic" (40-65) removed entirely —
        # they push too many personas above 45.
        # ------------------------------------------------------------------ #
        email_style={
            "alpha":        12,   # pelajar SMP/SMA (<18)
            "genz":         62,   # mahasiswa + awal karir (17-27)
            "millennial":   21,   # working adults (28-40, capped below)
            "chinese":       5,   # name diversity
        },

        # Hard age cap: no personas older than 40.
        # Combined with the style mix this eliminates the >45 tail.
        age_range="15-40",

        email_gender={"male": 52, "female": 48},

        # Consumer-only; no company/corporate addresses
        email_provider={
            "gmail.com":   76,
            "yahoo.co.id":  9,
            "yahoo.com":    6,
            "outlook.com":  6,
            "icloud.com":   3,
        },

        # Most respondents tick 1-2 options; engaged users up to 3
        # (controlled per-field in choose_checkbox, this is a hard cap)
        checkbox_min=1,
        checkbox_max=3,

        # ~3% rare-but-legal demographic outliers
        anomaly_rate=0.03,

        # Recommended base delay for believable timestamps.
        # The TUI preset uses 45 s; CLI users can override with --delay.
        # human_delay() varies this: most gaps 20-90 s, occasional 2-5 min.
        suggested_delay=45,
    ),

    calibration=Calibration(
        shift={
            "tech":        -0.10,   # more Pemula, less Mahir
            "engagement":  -0.07,   # Tidak Pernah rises to ~15-18%
            "benefit":     +0.02,
            "trust":        0.00,
            "access":       0.00,
            "concern":     +0.05,
        },
        sigma_scale={
            "tech":        1.22,
            "engagement":  1.15,
            "benefit":     1.12,
            "trust":       1.30,
            "access":      1.15,
            "concern":     1.40,
        },
    ),

    conditionals=[
        # ------------------------------------------------------------------ #
        # P(AI usage frequency | tech skill)  ← PRIMARY PREDICTION TARGET
        # The tightest table: maximum class separation so the forest can learn.
        # noise=0.05 (5% uniform) keeps it from being a perfect lookup table.
        # ------------------------------------------------------------------ #
        {
            "target": "usage_freq",
            "driver": "tech_skill",
            "noise":  0.05,
            "table": {
                "Pemula": {
                    "Tidak Pernah":                0.42,
                    "Jarang":                      0.38,
                    "Beberapa kali dalam seminggu": 0.13,
                    "Setiap Hari":                 0.07,
                },
                "Menengah": {
                    "Tidak Pernah":                0.08,
                    "Jarang":                      0.27,
                    "Beberapa kali dalam seminggu": 0.40,
                    "Setiap Hari":                 0.25,
                },
                "Mahir": {
                    "Tidak Pernah":                0.02,
                    "Jarang":                      0.08,
                    "Beberapa kali dalam seminggu": 0.30,
                    "Setiap Hari":                 0.60,
                },
            },
        },
        # ------------------------------------------------------------------ #
        # P(tech-news following | tech skill)
        # Curious/skilled people follow tech news more.  noise=0.08
        # ------------------------------------------------------------------ #
        {
            "target": "tech_news",
            "driver": "tech_skill",
            "noise":  0.08,
            "table": {
                "Pemula": {
                    "Tidak Pernah":  0.38,
                    "Jarang":        0.37,
                    "Kadang-Kadang": 0.18,
                    "Sering":        0.07,
                },
                "Menengah": {
                    "Tidak Pernah":  0.08,
                    "Jarang":        0.22,
                    "Kadang-Kadang": 0.42,
                    "Sering":        0.28,
                },
                "Mahir": {
                    "Tidak Pernah":  0.02,
                    "Jarang":        0.08,
                    "Kadang-Kadang": 0.30,
                    "Sering":        0.60,
                },
            },
        },
        # ------------------------------------------------------------------ #
        # P(AI benefit | tech skill)
        # Skilled users rate AI as more beneficial.  noise=0.08
        # ------------------------------------------------------------------ #
        {
            "target": "ai_benefit",
            "driver": "tech_skill",
            "noise":  0.08,
            "table": {
                "Pemula":   {"1": 0.30, "2": 0.35, "3": 0.22, "4": 0.09, "5": 0.04},
                "Menengah": {"1": 0.06, "2": 0.20, "3": 0.36, "4": 0.27, "5": 0.11},
                "Mahir":    {"1": 0.02, "2": 0.06, "3": 0.22, "4": 0.40, "5": 0.30},
            },
        },
        # ------------------------------------------------------------------ #
        # P(AI trust | tech skill)
        # Skilled users have tested AI and trust it more.  noise=0.08
        # ------------------------------------------------------------------ #
        {
            "target": "ai_trust",
            "driver": "tech_skill",
            "noise":  0.08,
            "table": {
                "Pemula":   {"1": 0.28, "2": 0.36, "3": 0.22, "4": 0.10, "5": 0.04},
                "Menengah": {"1": 0.07, "2": 0.25, "3": 0.38, "4": 0.22, "5": 0.08},
                "Mahir":    {"1": 0.02, "2": 0.10, "3": 0.28, "4": 0.38, "5": 0.22},
            },
        },
        # ------------------------------------------------------------------ #
        # P(access ease | tech skill)
        # Skilled users find AI tools easier to discover.  noise=0.08
        # ------------------------------------------------------------------ #
        {
            "target": "ai_access",
            "driver": "tech_skill",
            "noise":  0.08,
            "table": {
                "Pemula":   {"1": 0.25, "2": 0.38, "3": 0.25, "4": 0.08, "5": 0.04},
                "Menengah": {"1": 0.05, "2": 0.18, "3": 0.40, "4": 0.28, "5": 0.09},
                "Mahir":    {"1": 0.02, "2": 0.06, "3": 0.25, "4": 0.42, "5": 0.25},
            },
        },
        # ------------------------------------------------------------------ #
        # P(privacy concern | tech skill)
        # Skilled users are more privacy-aware.  noise=0.12 (concern is personal)
        # ------------------------------------------------------------------ #
        {
            "target": "concern_privacy",
            "driver": "tech_skill",
            "noise":  0.12,
            "table": {
                "Pemula":   {"1": 0.22, "2": 0.24, "3": 0.27, "4": 0.17, "5": 0.10},
                "Menengah": {"1": 0.10, "2": 0.16, "3": 0.28, "4": 0.28, "5": 0.18},
                "Mahir":    {"1": 0.05, "2": 0.10, "3": 0.24, "4": 0.35, "5": 0.26},
            },
        },
        # ------------------------------------------------------------------ #
        # P(job replacement concern | tech skill)
        # Skilled users see AI capability first-hand.  noise=0.12
        # ------------------------------------------------------------------ #
        {
            "target": "concern_job",
            "driver": "tech_skill",
            "noise":  0.12,
            "table": {
                "Pemula":   {"1": 0.24, "2": 0.24, "3": 0.26, "4": 0.16, "5": 0.10},
                "Menengah": {"1": 0.09, "2": 0.17, "3": 0.28, "4": 0.28, "5": 0.18},
                "Mahir":    {"1": 0.04, "2": 0.09, "3": 0.22, "4": 0.35, "5": 0.30},
            },
        },
    ],
)
