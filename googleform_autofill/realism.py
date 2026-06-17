"""Realistic, correlated answer generation for survey-style Google Forms.

The default fill strategy answers every choice/scale question with a uniform
``random.choice``. That produces a dataset where no field is related to any
other one, so a classifier can do no better than random guessing and a
chi-square test finds no significant associations (the data "looks synthetic").

This module fixes that by giving each respondent (persona) a small set of
latent traits and deriving the survey answers from those traits, with noise.
Because several questions are driven by the *same* underlying trait, the
generated answers become correlated the way real survey answers are:

    a tech-savvy persona  -> "Mahir" skill, longer internet use, follows tech
                             news, uses AI daily, knows more AI tools, rates AI
                             as more useful, trusts it more, finds it easier to
                             access.

The noise keeps the relationship realistic (strong but not perfect), so a model
trained on the data lands at a believable accuracy instead of 25% or 100%.

The detection is keyword based (Indonesian + English) so it adapts to the form
without hard-coding entry IDs. Anything it doesn't recognise falls back to the
caller's normal random behaviour.
"""

import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# Calibration: tune the marginal distributions per trait
# --------------------------------------------------------------------------- #

@dataclass
class Calibration:
    """Knobs to shape the trait distributions so the resulting answer marginals
    look like a real survey (a dominant peak / skew) instead of a flat split.

    * ``shift``       – additive nudge to a trait's centre (e.g. ``concern: +0.12``
                        makes people lean more worried).
    * ``sigma_scale`` – multiply a trait's noise spread (``< 1`` = more peaked,
                        more agreement; ``> 1`` = flatter, more varied).
    """
    shift: Dict[str, float] = field(default_factory=dict)
    sigma_scale: Dict[str, float] = field(default_factory=dict)


def _trait(r, mean: float, sigma: float, key: str,
           cal: Optional["Calibration"]) -> float:
    """Draw one trait value, applying calibration shift/spread, clamped 0..1."""
    if cal is not None:
        sigma *= cal.sigma_scale.get(key, 1.0)
    value = r.gauss(mean, sigma)
    if cal is not None:
        value += cal.shift.get(key, 0.0)
    return _clamp(value)


# --------------------------------------------------------------------------- #
# Latent traits
# --------------------------------------------------------------------------- #

# How "techy" each email/persona style reads, on a 0..1 scale. Younger / more
# online styles skew higher; this is one of several inputs to tech-savviness.
_STYLE_TECH = {
    "alpha": 0.80,
    "genz": 0.78,
    "millennial": 0.62,
    "professional": 0.60,
    "classic": 0.42,
    "chinese": 0.58,
    "mix": 0.55,
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_traits(age: Optional[int], edu_tier: Optional[int],
                   style: str, rng=None,
                   calibration: Optional[Calibration] = None) -> Dict[str, float]:
    """Derive a coherent set of latent traits (each in 0..1) for one persona.

    The traits form a correlated backbone:

    * ``tech``       – general technology savviness, from age (younger higher),
                       education (higher higher) and the persona style.
    * ``engagement`` – how much the person actually uses/follows AI; strongly
                       driven by ``tech`` plus its own noise. Drives the usage
                       frequency target, tools known and tech-news following.
    * ``benefit``    – perceived usefulness of AI; engaged users rate it higher.
    * ``trust``      – trust in AI accuracy; tracks ``benefit`` but a notch lower
                       (people find AI useful yet stay a little skeptical).
    * ``access``     – how easy AI tools are to find/use; tracks ``tech``.
    * ``concern``    – privacy / job-replacement worry; a largely independent
                       axis, only weakly (inversely) tied to ``benefit``.

    ``calibration`` (optional) shifts/peaks these so the answer marginals look
    like a real survey rather than a flat split.
    """
    r = rng if rng is not None else random
    cal = calibration
    age = age if age is not None else 25
    # 15 y/o -> ~1.0, 60 y/o -> ~0.0
    age_score = _clamp(1.0 - (age - 15) / 45.0)
    edu_score = _clamp(((edu_tier if edu_tier else 2) - 1) / 4.0)
    style_score = _STYLE_TECH.get(style, 0.55)

    base = 0.40 * age_score + 0.25 * edu_score + 0.35 * style_score
    tech = _trait(r, base, 0.13, "tech", cal)
    engagement = _trait(r, 0.80 * tech + 0.10, 0.10, "engagement", cal)
    attitude = _trait(r, 0.60 * engagement + 0.22, 0.11, "attitude", cal)
    benefit = _trait(r, attitude, 0.09, "benefit", cal)
    trust = _trait(r, attitude - 0.10, 0.11, "trust", cal)
    access = _trait(r, 0.65 * tech + 0.25 * engagement, 0.10, "access", cal)
    # Mostly its own axis; engaged/positive users worry a little less.
    concern = _trait(r, 0.50 - 0.25 * (benefit - 0.5), 0.20, "concern", cal)

    return {
        "tech": tech,
        "engagement": engagement,
        "benefit": benefit,
        "trust": trust,
        "access": access,
        "concern": concern,
    }


# --------------------------------------------------------------------------- #
# Mapping a question to the latent trait that should drive its answer
# --------------------------------------------------------------------------- #

def classify_role(entry_name: str) -> Optional[str]:
    """Map a question to a canonical *role* string, or None.

    Roles let the rest of the module (latent mapping, conditional tables and the
    logical validator) refer to questions by meaning rather than by keyword.
    Order matters: more specific phrases are tested first.
    """
    if not entry_name:
        return None
    s = entry_name.lower()

    # Worry / concern questions (privacy, job replacement).
    if "khawatir" in s and "menggantikan" in s:
        return "concern_job"
    if "khawatir" in s or "privasi" in s:
        return "concern_privacy"

    if "bermanfaat" in s or "manfaat" in s:
        return "ai_benefit"
    if ("percaya" in s or "kepercayaan" in s) and (
            "akurasi" in s or "hasil" in s or "informasi" in s):
        return "ai_trust"
    if "mudah" in s and ("akses" in s or "mengakses" in s or "menemukan" in s):
        return "ai_access"
    if "kemampuan" in s and "teknologi" in s:
        return "tech_skill"
    if "durasi" in s and "internet" in s:
        return "internet_duration"
    # Device and domicile vary independently in the real survey (flat ~33% each),
    # so we deliberately do NOT map them to a trait — returning None lets them
    # fall through to plain random.choice, matching observed real-world variance.
    if "berita" in s or "tren teknologi" in s:
        return "tech_news"
    if "sering" in s and ("tools ai" in s or "menggunakan" in s):
        return "usage_freq"
    if is_occupation_question(entry_name):
        return "occupation"
    if "tujuan" in s:
        return "ai_purpose"
    if "tools ai" in s or ("tools" in s and ("ketahui" in s or "gunakan" in s)):
        return "ai_tools"
    return None


# Which latent trait drives each ordinal role (used when no explicit conditional
# table applies). Demographic proxies (skill) ride on ``tech``; the
# AI-behaviour questions ride on ``engagement`` and the attitude traits.
ROLE_TRAIT = {
    "tech_skill": "tech",
    "internet_duration": "tech",
    "tech_news": "engagement",
    "usage_freq": "engagement",
    "ai_benefit": "benefit",
    "ai_trust": "trust",
    "ai_access": "access",
    "concern_privacy": "concern",
    "concern_job": "concern",
}


def latent_for_question(entry_name: str) -> Optional[Tuple[str, bool]]:
    """Return ``(trait_key, invert)`` for an ordinal question, or ``None``."""
    role = classify_role(entry_name)
    if role is None:
        return None
    trait = ROLE_TRAIT.get(role)
    if trait is None:
        return None
    return (trait, False)


# --------------------------------------------------------------------------- #
# Detecting an ordered (ordinal) option set
# --------------------------------------------------------------------------- #

def _numeric_value(opt: str) -> Optional[float]:
    """Pure-number option (e.g. linear-scale "1".."5"), else None."""
    s = str(opt).strip()
    return float(s) if re.fullmatch(r"-?\d+(?:\.\d+)?", s) else None


# Ordered keyword groups, lowest intensity first. Each group is tested as a
# whole; a label is assigned the rank of the *highest* group it matches so that
# e.g. "beberapa kali dalam seminggu" reads as "weekly", not "sometimes".
_FREQ_GROUPS = [
    ["tidak pernah", "belum pernah", "never"],
    ["jarang", "rarely", "seldom"],
    ["kadang", "sesekali", "sebulan", "sometimes", "occasion"],
    ["beberapa kali", "seminggu", "mingguan", "weekly"],
    ["sering", "often", "frequent"],
    ["setiap hari", "tiap hari", "harian", "selalu", "every day", "daily", "always"],
]

_SKILL_GROUPS = [
    ["pemula", "awam", "dasar", "basic", "beginner", "rendah"],
    ["menengah", "sedang", "cukup", "intermediate", "medium"],
    ["mahir", "ahli", "lanjut", "advanced", "expert", "profesional", "tinggi"],
]

_DOMICILE_GROUPS = [
    ["pedesaan", "desa", "rural", "kampung"],
    ["pinggiran", "sub-urban", "suburban", "pinggir"],
    ["perkotaan", "kota", "urban", "metropolitan"],
]

_DEVICE_GROUPS = [
    ["handphone", "hp", "ponsel", "smartphone", "telepon"],
    ["laptop", "pc", "komputer", "desktop", "tablet"],
    ["keduanya", "dua-duanya", "semua", "both"],
]

_AGREE_GROUPS = [
    ["sangat tidak setuju", "strongly disagree"],
    ["tidak setuju", "kurang setuju", "disagree"],
    ["netral", "neutral", "biasa saja", "ragu"],
    ["setuju", "agree"],
    ["sangat setuju", "strongly agree"],
]


def _group_rank(opt: str, groups: List[List[str]]) -> Optional[int]:
    """Rank ``opt`` by the highest keyword group it matches, else None."""
    s = str(opt).lower()
    found = None
    for rank, keywords in enumerate(groups):
        if any(k in s for k in keywords):
            found = rank
    return found


def _duration_rank(opt: str) -> Optional[float]:
    """Order a duration option ("<2 jam", "2-5 jam", ">5 jam", "30 menit")."""
    s = str(opt).lower()
    if not any(u in s for u in ("jam", "menit", "hour", "minute")):
        return None
    nums = [float(x) for x in re.findall(r"\d+", s)]
    if not nums:
        return None
    scale = 1.0 / 60.0 if ("menit" in s or "minute" in s) and "jam" not in s else 1.0
    if len(nums) >= 2:
        return (nums[0] + nums[1]) / 2.0 * scale
    n = nums[0] * scale
    if "<" in s or "kurang" in s or "≤" in s:
        return n - 1
    if ">" in s or "lebih" in s or "≥" in s or s.strip().endswith("+"):
        return n + 1
    return n


def _ordered_by_key(options: List[str], key_fn) -> Optional[List[str]]:
    keys = [key_fn(o) for o in options]
    if any(k is None for k in keys):
        return None
    if len({round(k, 6) for k in keys}) < 2:  # need at least two distinct levels
        return None
    return [o for _, o in sorted(zip(keys, options), key=lambda p: p[0])]


def detect_ordered_options(options: Optional[List[str]]) -> Optional[List[str]]:
    """Return the options sorted low->high if they form an ordinal scale.

    Tries, in order: pure numbers, frequency words, skill words, agreement
    (Likert) words, duration ranges, domicile and device proxies. Returns
    ``None`` for genuinely nominal sets (e.g. job status), so the caller can
    keep choosing those at random.
    """
    if not options or len(options) < 2:
        return None

    for key_fn in (
        _numeric_value,
        lambda o: _group_rank(o, _FREQ_GROUPS),
        lambda o: _group_rank(o, _SKILL_GROUPS),
        lambda o: _group_rank(o, _AGREE_GROUPS),
        _duration_rank,
        lambda o: _group_rank(o, _DOMICILE_GROUPS),
        lambda o: _group_rank(o, _DEVICE_GROUPS),
    ):
        ordered = _ordered_by_key(options, key_fn)
        if ordered is not None:
            return ordered
    return None


# --------------------------------------------------------------------------- #
# Turning a latent value into an actual answer
# --------------------------------------------------------------------------- #

def choose_ordinal(ordered: List[str], value: float, rng=None,
                   noise: float = 0.55) -> str:
    """Pick an option from an ordered list near ``value`` (0..1), with noise.

    ``value`` maps linearly onto the option index; Gaussian ``noise`` (in index
    units) keeps the choice realistic rather than deterministic.
    """
    r = rng if rng is not None else random
    n = len(ordered)
    if n == 1:
        return ordered[0]
    center = value * (n - 1)
    idx = int(round(center + r.gauss(0.0, noise)))
    return ordered[max(0, min(n - 1, idx))]


# Rough relative familiarity of well-known AI tools, used to weight checkbox
# selections so popular tools are ticked more often than niche ones.
_TOOL_POPULARITY = {
    "chatgpt": 1.0,
    "gemini": 0.8,
    "copilot": 0.65,
    "canva": 0.6,
    "google assistant": 0.6,
    "siri": 0.55,
    "midjourney": 0.4,
    "lainnya": 0.25,
    "other": 0.25,
    "tidak": 0.15,
}


def _tool_weight(opt: str, engagement: float) -> float:
    s = str(opt).lower()
    base = 0.5
    for key, w in _TOOL_POPULARITY.items():
        if key in s:
            base = w
            break
    # More engaged users are likelier to know the less mainstream tools.
    if base < 0.6:
        base += 0.4 * engagement
    return max(0.05, base)


def _weighted_sample(options: List[str], weights: List[float], k: int,
                     rng=None) -> List[str]:
    """Sample ``k`` distinct options with probability proportional to weight."""
    r = rng if rng is not None else random
    pool = list(zip(options, weights))
    picked: List[str] = []
    k = max(0, min(k, len(pool)))
    for _ in range(k):
        total = sum(w for _, w in pool)
        if total <= 0:
            picked.extend(o for o, _ in pool[:k - len(picked)])
            break
        threshold = r.random() * total
        upto = 0.0
        for i, (opt, w) in enumerate(pool):
            upto += w
            if upto >= threshold:
                picked.append(opt)
                pool.pop(i)
                break
    return picked


def choose_checkbox(options: List[str], entry_name: str,
                    traits: Dict[str, float], rng=None) -> List[str]:
    """Select a realistic subset of checkbox options for this persona.

    Real respondents cluster around 1-3 popular tools rather than picking
    randomly across all options. This is achieved by:
    1. Skewing the *count* toward low values (most people know 1-2 tools).
    2. Heavily weighting popular/well-known tools so ChatGPT/Gemini appear
       far more often than niche options, creating realistic repeated combos
       instead of near-unique combinations on every row.
    """
    r = rng if rng is not None else random
    n = len(options)
    if n == 0:
        return []
    eng = traits.get("engagement", 0.5)

    s = (entry_name or "").lower()
    is_tools = "tools ai" in s or ("tools" in s and ("gunakan" in s or "ketahui" in s))

    if is_tools:
        # Count: most people know 1-2 tools; engaged users up to 4-5.
        # Use a geometric-like skew: P(k) drops off quickly after 2.
        # Low engagement → strongly peaks at 1-2; high → up to 4.
        max_k = min(n, max(2, round(1.5 + eng * 3.5)))
        # Draw from a skewed distribution: beta(1.2, 2.5) mapped to 1..max_k
        raw = r.betavariate(1.2, 2.5)  # peaks near 0, right tail
        k = max(1, min(max_k, round(1 + raw * (max_k - 1))))
        weights = [_tool_weight(o, eng) for o in options]
    elif "tujuan" in s:
        # AI purposes: 1-2 reasons typical; engaged users sometimes 3.
        max_k = min(n, max(1, round(1.0 + eng * 2.5)))
        raw = r.betavariate(1.0, 2.0)
        k = max(1, min(max_k, round(1 + raw * (max_k - 1))))
        weights = [1.0] * n
    else:
        max_k = min(n, max(1, round(1.0 + eng * (n - 1) * 0.5)))
        raw = r.betavariate(1.2, 2.0)
        k = max(1, min(max_k, round(1 + raw * (max_k - 1))))
        weights = [1.0] * n

    return _weighted_sample(options, weights, k, r)


def answer_choice(options: List[str], entry_name: str,
                  traits: Optional[Dict[str, float]], rng=None) -> Optional[str]:
    """Trait-driven answer for a single-select ordinal question.

    Returns ``None`` when the question isn't a recognised ordinal scale or there
    are no traits, so the caller falls back to its normal random choice.
    """
    if not traits or not options:
        return None
    mapping = latent_for_question(entry_name)
    if mapping is None:
        return None
    ordered = detect_ordered_options(options)
    if ordered is None:
        return None
    trait_key, invert = mapping
    value = traits.get(trait_key, 0.5)
    if invert:
        value = 1.0 - value
    return choose_ordinal(ordered, value, rng)


# --------------------------------------------------------------------------- #
# Occupation coherent with age / education / gender
# --------------------------------------------------------------------------- #
#
# Education tiers passed in here use the same numbering as main.py:
#   1 = SMP, 2 = SMA, 3 = D3, 4 = D4/S1, 5 = S2+
#
# Choosing the job status from the persona (instead of at random) removes the
# impossible combinations real reviewers spot immediately: a <18 civil servant,
# a "Pelajar" with an S2, a "Mahasiswa" whose last education is SMP, etc. It
# also de-uniformises the column, because the eligible jobs differ per persona.

_OCC_PATTERNS = [
    # "mahasiswa" must be tested before "pelajar": the word *contains* "siswa".
    ("mahasiswa", ["mahasiswa", "kuliah", "college student", "university student"]),
    ("pelajar", ["pelajar", "sd/smp", "sd / smp", "smp/sma", "sekolah", "sd/smp/sma"]),
    ("pns", ["negeri", "asn", "pns"]),
    ("swasta", ["swasta", "karyawan", "private"]),
    ("wirausaha", ["wirausaha", "pengusaha", "wiraswasta", "bisnis", "entrepreneur", "freelan"]),
    ("irt", ["rumah tangga", "irt"]),
    ("lainnya", ["lainnya", "lain-lain", "other", "tidak bekerja", "pengangguran"]),
]


def _occupation_category(opt: str) -> Optional[str]:
    s = str(opt).lower()
    for cat, keywords in _OCC_PATTERNS:
        if any(k in s for k in keywords):
            return cat
    return None


def _occupation_weight(cat: Optional[str], age: int, edu: int, gender: str) -> float:
    """Plausibility weight (0 = impossible) for a job given the persona.

    Under-18s are restricted to "Pelajar" / "Lainnya" only: no minors as
    civil servants, full-time private employees, entrepreneurs or homemakers.
    """
    if cat == "pelajar":
        # School pupil: only young, still at/below senior-high level.
        if age > 19 or edu >= 3:
            return 0.0
        return 6.0 if age < 18 else 2.0
    if cat == "mahasiswa":
        # Undergraduate: legally adult, not a postgraduate or SMP-only.
        if age < 18 or age > 30 or edu < 2 or edu >= 5:
            return 0.0
        return 5.0 if 18 <= age <= 24 else 1.5
    if cat == "pns":
        # Civil servant: legally adult and past secondary school.
        if age < 21 or edu < 2:
            return 0.0
        return 2.5 if age >= 25 else 1.0
    if cat == "swasta":
        if age < 18:
            return 0.0
        return 3.0 if age >= 20 else 1.0
    if cat == "wirausaha":
        if age < 18:
            return 0.0
        return 2.0 if age >= 22 else 1.0
    if cat == "irt":
        # Homemaker: adult; in this dataset effectively women.
        if age < 19 or gender == "male":
            return 0.0
        return 1.5
    # "Lainnya" / unrecognised: always a small catch-all chance.
    return 0.6


def is_occupation_question(entry_name: str) -> bool:
    """Heuristic: does this field ask for employment / job status?"""
    if not entry_name:
        return False
    s = entry_name.lower()
    if "tujuan" in s or "khawatir" in s or "menggantikan" in s:
        return False  # AI-purpose / worry questions also contain "pekerjaan"
    if "profesi" in s or "occupation" in s or "status pekerjaan" in s:
        return True
    return "pekerjaan" in s and ("status" in s or "saat ini" in s or "anda" in s)


def choose_occupation(options: List[str], age: Optional[int], edu_tier: Optional[int],
                      gender: str, rng=None, anomaly_rate: float = 0.0) -> Optional[str]:
    """Pick a job-status option consistent with the persona, or None.

    ``anomaly_rate`` (0..1) injects rare-but-legal outliers: with that
    probability the *plausibility* weighting is flattened across the options
    that are still legal for this persona (weight > 0), so you occasionally get
    an atypical-yet-possible respondent (e.g. a young entrepreneur). Truly
    impossible combinations (weight 0, such as a <18 civil servant) stay
    impossible regardless.
    """
    if not options:
        return None
    r = rng if rng is not None else random
    age = age if age is not None else 25
    edu = edu_tier if edu_tier else 2
    weights = [_occupation_weight(_occupation_category(o), age, edu, gender)
               for o in options]
    if sum(weights) <= 0:
        return None
    if anomaly_rate and r.random() < anomaly_rate:
        # Keep only the legality gate (0 vs >0); treat all legal jobs as equally
        # likely so an unusual-but-valid choice can surface.
        weights = [1.0 if w > 0 else 0.0 for w in weights]
    return _weighted_sample(options, weights, 1, r)[0]


# --------------------------------------------------------------------------- #
# Human-like submission timing
# --------------------------------------------------------------------------- #

def human_delay(base: float, rng=None) -> float:
    """A natural, right-skewed gap (seconds) between two submissions.

    Uses a lognormal distribution centred on ``base`` with heavier variance,
    plus a ~10% chance of a longer "reading/distracted" pause. The result never
    looks linear in aggregate — the median is close to ``base`` but the mean
    is higher, and occasional outliers create the natural clumping real survey
    data shows.

    Recommended base values for a believable survey:
        30–60 s  →  fast-ish respondent (students on mobile)
        60–120 s →  typical respondent
        120+ s   →  slow/careful respondent
    """
    import math
    r = rng if rng is not None else random
    if base <= 0:
        return 0.0
    # sigma=0.75 gives a right-skewed distribution with noticeable variance
    wait = r.lognormvariate(math.log(max(base, 1.0)), 0.75)
    # ~10% of the time add a longer pause (re-reading, phone distraction, etc.)
    if r.random() < 0.10:
        wait += r.uniform(base * 1.5, base * 5.0)
    return wait


# --------------------------------------------------------------------------- #
# Explicit conditional-probability tables (CPT)
# --------------------------------------------------------------------------- #
#
# The latent engine already produces conditional probabilities implicitly, but a
# preset can also state a relationship explicitly, exactly as Gemini suggested:
#
#     "Mahir"  -> P(Setiap Hari) = 0.50, P(Tidak Pernah) = 0.03, ...
#
# A rule is a dict::
#
#     {"target": "usage_freq",      # role whose answer we are choosing
#      "driver": "tech_skill",      # role whose (already chosen) answer we read
#      "noise": 0.08,               # blend this much uniform noise for realism
#      "table": {driver_answer: {target_option: probability, ...}, ...}}
#
# ``noise`` mixes a little uniform randomness into every row so the mapping is
# strong but never a perfect, tell-tale 100% rule.

def cpt_choice(role: Optional[str], options: List[str], recorded: Dict[str, str],
               conditionals: Optional[List[dict]], rng=None) -> Optional[str]:
    """Pick ``role``'s answer from an explicit conditional table, or None.

    Returns None (so the caller falls back to the latent engine) when there is
    no matching rule, the driver answer hasn't been chosen yet, or the table's
    options don't line up with this form's option labels.
    """
    if not role or not conditionals or not options:
        return None
    r = rng if rng is not None else random
    for rule in conditionals:
        if rule.get("target") != role:
            continue
        driver_answer = recorded.get(rule.get("driver"))
        if driver_answer is None:
            continue
        row = rule.get("table", {}).get(driver_answer)
        if not row:
            continue
        opts = [o for o in options if o in row]
        if not opts:
            continue
        noise = rule.get("noise", 0.07)
        weights = [row[o] * (1.0 - noise) + noise / len(opts) for o in opts]
        return _weighted_sample(opts, weights, 1, r)[0]
    return None


# --------------------------------------------------------------------------- #
# Logical validator (post-generation audit / constraint check)
# --------------------------------------------------------------------------- #
#
# Generation is already correct-by-construction (occupation is weight-gated to
# the persona), but a validator gives a hard guarantee and lets you audit any
# saved dataset for the impossible combinations reviewers look for.

# Education-tier numbering shared with main.py: 1=SMP 2=SMA 3=D3 4=D4/S1 5=S2+
def _edu_tier_from_label(label: Optional[str]) -> Optional[int]:
    if not label:
        return None
    s = label.lower()
    if re.search(r"(s\s*-?\s*2|s\s*-?\s*3|magister|master|doktor|pascasarjana)", s):
        return 5
    if re.search(r"(s\s*-?\s*1|d\s*-?\s*4|sarjana)", s):
        return 4
    if re.search(r"(d\s*-?\s*3|d\s*-?\s*2|d\s*-?\s*1|diploma)", s):
        return 3
    if re.search(r"(sma|smk|slta|aliyah)", s):
        return 2
    if re.search(r"(smp|sltp|tsanawiyah)", s):
        return 1
    if re.search(r"\b(sd|tidak sekolah)\b", s):
        return 1
    return None


def validate_record(age: Optional[int], education: Optional[str],
                    occupation: Optional[str]) -> List[str]:
    """Return a list of logical-consistency violations for one respondent.

    Empty list == the row is plausible. Checks the rules real reviewers flag:
    minors with adult jobs, schoolkids/undergrads with impossible education, and
    SMP-only civil servants / undergraduates.
    """
    problems: List[str] = []
    cat = _occupation_category(occupation) if occupation else None
    edu = _edu_tier_from_label(education)

    if age is not None and age < 18 and cat not in (None, "pelajar", "lainnya"):
        problems.append(f"age <18 with occupation '{occupation}' (expected Pelajar/Lainnya)")
    if cat == "pelajar" and edu is not None and edu >= 3:
        problems.append(f"Pelajar with higher education '{education}'")
    if cat == "mahasiswa" and edu is not None and edu < 2:
        problems.append(f"Mahasiswa with education '{education}' (below SMA)")
    if cat == "pns":
        if age is not None and age < 21:
            problems.append("Pegawai Negeri/ASN under 21")
        if edu is not None and edu < 2:
            problems.append(f"Pegawai Negeri/ASN with education '{education}'")
    return problems
