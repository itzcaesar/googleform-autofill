"""
Google Form Auto-Fill and Submit Tool
Version 2.0 - Enhanced with better error handling, custom fill strategies, and submission tracking
Date: 2025-11-27
"""

import argparse
import datetime
import json
import logging
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Union

import requests

from googleform_autofill import form, email_generator, realism
from googleform_autofill.presets import get_preset, PRESETS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

import re


def parse_age_option(opt: str) -> Optional[tuple]:
    """
    Parse an age-range *option label* into an inclusive (lo, hi) bound.

    Handles the common Google Form variants:
        "<18" / "< 18"      -> (0, 17)
        "<=18" / "≤18"      -> (0, 18)
        "18-25" / "18–25"   -> (18, 25)   (hyphen, en-dash or em-dash)
        ">45" / "> 45"      -> (46, 150)
        ">=45" / "≥45"      -> (45, 150)
        "45+"               -> (45, 150)
        "30"                -> (30, 30)

    Returns None if no number can be found.
    """
    if not opt:
        return None
    s = str(opt).strip().replace("–", "-").replace("—", "-").replace("≤", "<=").replace("≥", ">=")
    nums = [int(x) for x in re.findall(r"\d+", s)]
    if not nums:
        return None
    if len(nums) >= 2:
        return (min(nums[0], nums[1]), max(nums[0], nums[1]))
    n = nums[0]
    has_eq = "=" in s
    if "<" in s:
        return (0, n if has_eq else n - 1)
    if ">" in s or s.rstrip().endswith("+"):
        return (n if (has_eq or s.rstrip().endswith("+")) else n + 1, 150)
    return (n, n)


def parse_weight_spec(spec: str, valid: List[str], label: str = "value") -> Dict[str, float]:
    """
    Parse a percentage/weight spec like "genz=70,professional=30" into a dict.

    Accepts ',' or ';' separators and '=' or ':' between name and number. Names
    must be in ``valid``; unknown or non-positive entries are dropped. Raises
    ValueError if nothing usable is found.
    """
    if not spec:
        return {}
    out: Dict[str, float] = {}
    parts = re.split(r"[,;]", spec)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.split(r"[=:]", part, maxsplit=1)
        if len(m) != 2:
            raise ValueError(f"Invalid {label} entry '{part}'. Use name=percent.")
        name, raw = m[0].strip().lower(), m[1].strip()
        if name not in valid:
            raise ValueError(f"Unknown {label} '{name}'. Choose from: {', '.join(valid)}")
        try:
            val = float(raw)
        except ValueError:
            raise ValueError(f"Invalid percentage '{raw}' for '{name}'.")
        if val > 0:
            out[name] = val
    if not out:
        raise ValueError(f"No usable {label} percentages in '{spec}'.")
    return out


# ========== Education / persona coherence ========== #

# Education tiers, lowest to highest. These mirror the common Indonesian
# "pendidikan terakhir" options the forms use.
EDU_SMP, EDU_SMA, EDU_D3, EDU_S1, EDU_S2 = 1, 2, 3, 4, 5
EDU_LABELS = {EDU_SMP: "SMP", EDU_SMA: "SMA", EDU_D3: "D3",
              EDU_S1: "D4/S1", EDU_S2: "S2+"}

# Ordered (tier, regex) rules. Higher tiers are checked first so that, e.g.,
# "D4 / S1" is read as S1 rather than matching a looser D-something rule.
_EDU_RULES = [
    (EDU_S2, r"(s\s*-?\s*2|s\s*-?\s*3|magister|master|doktor|ph\.?\s*d|pascasarjana|pasca\s*sarjana)"),
    (EDU_S1, r"(s\s*-?\s*1|d\s*-?\s*4|sarjana|bachelor)"),
    (EDU_D3, r"(d\s*-?\s*3|d\s*-?\s*2|d\s*-?\s*1|diploma)"),
    (EDU_SMA, r"(sma|smk|slta|stm|aliyah|senior high|high school)"),
    (EDU_SMP, r"(smp|sltp|tsanawiyah|junior high)"),
    (EDU_SMP, r"\b(sd|elementary|tidak sekolah)\b"),  # below SMP -> clamp to lowest option
]


def classify_education(label: str):
    """Map a free-form education option label to an EDU_* tier, or None."""
    if not label:
        return None
    s = str(label).lower()
    for tier, pattern in _EDU_RULES:
        if re.search(pattern, s):
            return tier
    return None


def education_tier_for_age(age: int, rng=None) -> int:
    """Pick a plausible highest-education tier for a given age.

    Gates each tier behind a realistic minimum age so impossible combinations
    (e.g. a 15-year-old with an S2) never occur, then weights the eligible
    tiers toward what's typical for that age.
    """
    r = rng if rng is not None else random
    if age < 15:
        return EDU_SMP
    # Population-realistic skew (Indonesia): SMA dominates, S1 substantial,
    # D3 small, S2+ rare (~5%). Tiers stay gated behind a plausible minimum age.
    weights = {EDU_SMP: 3 if age < 17 else 1}
    weights[EDU_SMA] = 7
    if age >= 19:
        weights[EDU_D3] = 2
    if age >= 21:
        weights[EDU_S1] = 3 if age < 23 else 5
    if age >= 26:
        weights[EDU_S2] = 1
    tiers = list(weights.keys())
    return r.choices(tiers, weights=[weights[t] for t in tiers], k=1)[0]


def is_education_field(entry_name: str) -> bool:
    """Heuristic: does this field ask for level of education?"""
    if not entry_name:
        return False
    s = entry_name.lower()
    keywords = ["pendidikan", "education", "lulusan", "edukasi",
                "tingkat pendidikan", "jenjang", "ijazah"]
    return any(k in s for k in keywords)


# Fields that contain "nama" but are NOT a person's name
_NOT_PERSON_NAME = ["username", "user name", "pengguna", "akun", "instansi",
                    "sekolah", "kampus", "universitas", "perusahaan", "kantor",
                    "produk", "barang", "toko", "jalan", "band", "grup", "tim",
                    "email", "panggilan ortu", "orang tua", "ayah", "ibu",
                    "wali", "hewan", "kota", "tempat"]


def is_name_field(entry_name: str) -> bool:
    """Heuristic: does this field ask for the respondent's (person) name?"""
    if not entry_name:
        return False
    s = entry_name.lower()
    if any(x in s for x in _NOT_PERSON_NAME):
        return False
    return ("nama" in s) or bool(re.search(r"\bname\b", s)) or ("full name" in s)


def is_gender_field(entry_name: str) -> bool:
    """Heuristic: does this field ask for gender / sex?"""
    if not entry_name:
        return False
    s = entry_name.lower()
    return any(k in s for k in ["jenis kelamin", "kelamin", "gender", "sex"])


def is_phone_field(entry_name: str) -> bool:
    """Heuristic: does this field ask for a phone / WhatsApp number?"""
    if not entry_name:
        return False
    s = entry_name.lower()
    keywords = ["telepon", "telpon", "no hp", "nomor hp", "no. hp", "nohp",
                "no telp", "nomor telepon", "phone", "whatsapp", "wa ", "no wa",
                "nomor wa", "kontak", "handphone", "hp/wa"]
    if any(k in s for k in keywords):
        return True
    # bare "hp" as a word
    return bool(re.search(r"\bhp\b", s))


def match_gender_option(options: List[str], gender: str):
    """Pick the option label matching ``gender`` ('male'/'female'), or None.

    Handles 'male' being a substring of 'female' by checking female markers
    first on each option."""
    if gender not in ("male", "female") or not options:
        return None
    fem_kw = ["perempuan", "wanita", "female", "cewek", "akhwat", "putri"]
    male_kw = ["laki", "pria", "cowok", "ikhwan", "putra"]
    for opt in options:
        ol = opt.lower()
        is_f = any(k in ol for k in fem_kw)
        is_m = (any(k in ol for k in male_kw) or ("male" in ol)) and not is_f
        if gender == "female" and is_f:
            return opt
        if gender == "male" and is_m:
            return opt
    # single-letter codes: L/P (laki/perempuan) or M/F
    for opt in options:
        code = opt.strip().lower()
        if gender == "male" and code in ("l", "m"):
            return opt
        if gender == "female" and code in ("p", "f", "w"):
            return opt
    return None


# Indonesian mobile prefixes (after the leading 0): Telkomsel, Indosat, XL, Axis, Tri, Smartfren
_PHONE_PREFIXES = [
    "811", "812", "813", "821", "822", "823", "851", "852", "853",  # Telkomsel
    "814", "815", "816", "855", "856", "857", "858",                # Indosat
    "817", "818", "819", "859", "877", "878",                       # XL
    "831", "832", "833", "838",                                     # Axis
    "895", "896", "897", "898", "899",                              # Tri
    "881", "882", "883", "884", "885", "886", "887", "888", "889",  # Smartfren
]


def generate_phone(rng=None) -> str:
    """Generate a plausible Indonesian mobile number like '081234567890'."""
    r = rng if rng is not None else random
    prefix = r.choice(_PHONE_PREFIXES)
    rest_len = r.choice([6, 7, 8])
    rest = "".join(str(r.randint(0, 9)) for _ in range(rest_len))
    return "0" + prefix + rest


class Persona:
    """A single coherent respondent: matching name, email, gender, age and
    education tier, generated once per submission."""

    __slots__ = ("style", "gender", "age", "edu_tier", "identity", "phone", "traits", "answers")

    def __init__(self, style: str, gender: str, age: int, edu_tier: int,
                 identity: Optional[Dict] = None, phone: str = "",
                 traits: Optional[Dict[str, float]] = None,
                 answers: Optional[Dict[str, Any]] = None):
        self.style = style
        self.gender = gender
        self.age = age
        self.edu_tier = edu_tier
        self.identity = identity or {}
        self.phone = phone
        # Latent 0..1 traits (tech savviness, AI engagement, attitude, etc.)
        # that drive correlated, realistic answers to the survey questions.
        self.traits = traits or {}
        # Answers already chosen this submission, keyed by realism role. Lets
        # conditional tables read an earlier answer and the validator audit the
        # finished row for logical consistency.
        self.answers = answers if answers is not None else {}

    @property
    def full_name(self) -> str:
        return self.identity.get("full_name", "")

    @property
    def email(self) -> str:
        return self.identity.get("email", "")

    def __repr__(self):
        return (f"Persona(name={self.full_name!r}, email={self.email!r}, "
                f"gender={self.gender}, age={self.age}, "
                f"edu={EDU_LABELS.get(self.edu_tier)})")


# ========== Fill Strategies ========== #

class FillStrategy:
    """Base class for form filling strategies."""
    
    def __init__(self, email: str = "test@example.com", custom_values: Optional[Dict] = None,
                 age_range: Optional[str] = None, random_email: bool = False,
                 email_style="mix", email_gender="any",
                 email_seed: Optional[int] = None,
                 checkbox_min: int = 1, checkbox_max: Optional[int] = None,
                 match_age_options: bool = True,
                 coherent_identity: bool = True,
                 email_provider="auto",
                 calibration=None,
                 conditionals=None,
                 anomaly_rate: float = 0.0):
        """
        Initialize fill strategy.

        Args:
            email: Email address to use for email fields
            custom_values: Dictionary of entry_id -> value mappings for custom values
            age_range: Age range in format "min-max" (e.g., "18-25")
            random_email: If True, generate a realistic Indonesian @gmail.com
                          address for the email field instead of using `email`
            email_style: Generator style when random_email is on (see
                         email_generator.STYLES): classic/professional/millennial/
                         genz/alpha/chinese/mix. May also be a {style: percent} dict.
            email_gender: "any", "male", or "female" (or a {gender: percent} dict)
            email_seed: optional int for reproducible email generation
            checkbox_min: minimum options to tick on a checkbox ("choose many") field
            checkbox_max: maximum options to tick; None = min(option_count, 3)
            match_age_options: when an age question is a multiple-choice/dropdown
                               with range options (e.g. "18-25"), pick the option(s)
                               matching age_range instead of choosing at random
            coherent_identity: when True, build one coherent persona per submission
                               so the email style, age and education level all agree
                               (e.g. a Gen Z email -> a tw20-something -> SMA/S1, never S2)
        """
        self.email = email
        self.custom_values = custom_values or {}
        self.random_email = random_email
        self.email_style = email_style
        self.email_gender = email_gender
        self.checkbox_min = checkbox_min
        self.checkbox_max = checkbox_max
        self.match_age_options = match_age_options
        self.coherent_identity = coherent_identity
        self.email_provider = email_provider
        # Marginal-shaping calibration and explicit conditional-probability
        # tables (both optional; supplied by a preset for a specific form).
        self.calibration = calibration
        self.conditionals = conditionals
        # Fraction of submissions allowed a rare-but-legal demographic outlier.
        self.anomaly_rate = anomaly_rate
        # A dedicated RNG so a seed yields a reproducible *sequence* across submissions
        self._email_rng = random.Random(email_seed) if email_seed is not None else None
        self._persona: Optional[Persona] = None
        # Emails already handed out this batch, to guarantee no duplicates
        self._used_emails: set = set()
        self.age_min = None
        self.age_max = None
        # Parse age range if provided
        if age_range:
            self._parse_age_range(age_range)

    def start_submission(self) -> Optional[Persona]:
        """Begin a new submission: build a fresh coherent persona (if enabled).

        Called once per generated response so that the email, age and
        education fields within a single submission describe the same person.
        """
        if not self.coherent_identity:
            self._persona = None
            return None
        rng = self._email_rng if self._email_rng is not None else random
        style = email_generator.resolve_style(self.email_style, rng=rng)
        gender = email_generator.resolve_gender(self.email_gender, rng=rng)
        # A real person has a definite gender. When "any" is requested, commit to
        # one per persona so the name, gender field and gendered name tokens agree.
        if gender == "any":
            gender = rng.choice(["male", "female"])
        age = email_generator.age_for_style(style, rng=rng,
                                            lo=self.age_min, hi=self.age_max)
        edu_tier = education_tier_for_age(age, rng=rng)
        regen = lambda: email_generator.generate_identity(
            style, gender, rng=rng, provider=self.email_provider, age=age)
        identity = regen()
        # Guarantee a unique email across the whole batch (important for 300+ runs)
        if self.random_email:
            identity = self._unique_identity(identity, regen, rng)
        phone = generate_phone(rng)
        traits = realism.compute_traits(age, edu_tier, style, rng=rng,
                                        calibration=self.calibration)
        self._persona = Persona(style, gender, age, edu_tier,
                                identity=identity, phone=phone, traits=traits)
        logger.debug(f"New persona: {self._persona}")
        return self._persona

    def _age_bounds(self) -> tuple:
        """Effective (lo, hi) age bounds for the current fill.

        When a coherent persona is active its single age is used so age fields
        and the email vibe stay consistent; otherwise fall back to the
        configured age_range."""
        if self._persona is not None:
            return self._persona.age, self._persona.age
        return self.age_min, self.age_max

    def _age_options(self, options: List[str]) -> List[str]:
        """Return the option labels whose age range overlaps the effective
        age bounds (persona age if coherent, else configured age_range).
        Empty list if no bounds are set or nothing matches."""
        lo, hi = self._age_bounds()
        if lo is None or hi is None or not options:
            return []
        matches = []
        for opt in options:
            rng = parse_age_option(opt)
            # inclusive interval overlap test
            if rng and rng[0] <= hi and rng[1] >= lo:
                matches.append(opt)
        return matches

    def _education_option(self, options: List[str]):
        """Pick the option matching the persona's education tier (or the
        nearest plausible one). Returns None if no persona or no classifiable
        education options."""
        if self._persona is None or not options:
            return None
        target = self._persona.edu_tier
        valid = [(o, classify_education(o)) for o in options]
        valid = [(o, t) for o, t in valid if t is not None]
        if not valid:
            return None
        exact = [o for o, t in valid if t == target]
        if exact:
            return random.choice(exact)
        # No exact tier on the form -> choose the closest available tier
        nearest_tier = min((t for _, t in valid), key=lambda t: abs(t - target))
        candidates = [o for o, t in valid if t == nearest_tier]
        return random.choice(candidates)

    def _checkbox_range(self, n_options: int) -> tuple:
        """Return (lo, hi) selection counts for a checkbox field, clamped to
        the number of available options."""
        if n_options <= 0:
            return 0, 0
        lo = max(1, self.checkbox_min)
        hi = self.checkbox_max if self.checkbox_max is not None else min(n_options, 3)
        lo = min(lo, n_options)
        hi = min(max(hi, lo), n_options)
        return lo, hi

    def _parse_age_range(self, age_range: str) -> None:
        """Parse age range string like '18-25' into min and max values."""
        try:
            parts = age_range.split('-')
            if len(parts) != 2:
                raise ValueError(f"Invalid age range format: {age_range}. Use format: 'min-max' (e.g., '18-25')")
            
            self.age_min = int(parts[0].strip())
            self.age_max = int(parts[1].strip())
            
            if self.age_min > self.age_max:
                raise ValueError(f"Minimum age ({self.age_min}) cannot be greater than maximum age ({self.age_max})")
            
            if self.age_min < 0 or self.age_max > 150:
                raise ValueError(f"Age values must be between 0 and 150")
            
            logger.info(f"Age range set to: {self.age_min}-{self.age_max} years")
        except ValueError as e:
            logger.error(f"Error parsing age range: {e}")
            raise
    
    def _is_age_field(self, entry_name: str) -> bool:
        """Check if the field name indicates an age field."""
        if not entry_name:
            return False
        
        entry_name_lower = entry_name.lower()
        age_keywords = ['age', 'umur', 'usia', 'tahun', 'edad', 'alter']
        
        return any(keyword in entry_name_lower for keyword in age_keywords)
    
    def _generate_age(self) -> str:
        """Generate an age consistent with the current persona/age range."""
        if self._persona is not None:
            return str(self._persona.age)
        if self.age_min is not None and self.age_max is not None:
            return str(random.randint(self.age_min, self.age_max))
        else:
            # Default age range if not specified
            return str(random.randint(18, 65))

    def _suffix_email(self, email: str, rng) -> str:
        """Return a unique variant of ``email`` by appending digits to the local
        part. Used as a last resort when regeneration keeps colliding."""
        r = rng if rng is not None else random
        local, _, dom = email.partition("@")
        for _ in range(300):
            n = str(r.randint(1, 999999))
            base = local[:30 - len(n)].rstrip("._-") or "user"
            cand = f"{base}{n}@{dom}"
            if cand not in self._used_emails:
                return cand
        return email

    def _register_unique_email(self, email: str, regen, rng) -> str:
        """Ensure ``email`` is unique within the batch, regenerating (via the
        ``regen`` callable) on collision and falling back to a numeric suffix.
        Records and returns the final address."""
        tries = 0
        while email in self._used_emails and tries < 30:
            email = regen()
            tries += 1
        if email in self._used_emails:
            email = self._suffix_email(email, rng)
        self._used_emails.add(email)
        return email

    def _unique_identity(self, identity: Dict, regen, rng) -> Dict:
        """Like :meth:`_register_unique_email` but keeps the whole identity
        (name + username + email) consistent."""
        tries = 0
        while identity["email"] in self._used_emails and tries < 30:
            identity = regen()
            tries += 1
        if identity["email"] in self._used_emails:
            new_email = self._suffix_email(identity["email"], rng)
            identity = dict(identity)
            identity["email"] = new_email
            identity["username"] = new_email.partition("@")[0]
        self._used_emails.add(identity["email"])
        return identity

    def _email_value(self) -> str:
        """Return the value to use for an email field."""
        if self.random_email:
            # Use the coherent persona's email so it matches the name/age/edu
            # filled elsewhere; otherwise generate a standalone (deduped) one.
            if self._persona is not None and self._persona.email:
                return self._persona.email
            rng = self._email_rng
            regen = lambda: email_generator.generate_email(
                self.email_style, self.email_gender, rng=rng,
                provider=self.email_provider)
            return self._register_unique_email(regen(), regen, rng)
        return self.email

    def _person_name(self) -> str:
        """A realistic full name for a 'Nama' field, matching the persona when
        one is active, otherwise freshly generated from the configured style."""
        if self._persona is not None and self._persona.full_name:
            return self._persona.full_name
        return email_generator.generate_identity(
            self.email_style, self.email_gender, rng=self._email_rng,
            provider=self.email_provider)["full_name"]

    def _phone_value(self) -> str:
        """A plausible Indonesian mobile number (persona's if available)."""
        if self._persona is not None and self._persona.phone:
            return self._persona.phone
        return generate_phone(self._email_rng)

    def _gender_for_match(self) -> str:
        """The concrete gender to use when matching a gender choice field."""
        if self._persona is not None:
            return self._persona.gender
        return email_generator.resolve_gender(self.email_gender, rng=self._email_rng)

    def _ordinal_answer(self, options: List[str], entry_name: str):
        """Trait/CPT-driven answer for an ordinal single-select or scale field.

        Tries an explicit conditional-probability table first (if a preset
        supplied one and the driver answer is already chosen), then the latent
        engine. Records the chosen value under its role so later questions and
        the validator can use it. Returns None if not a recognised ordinal field.
        """
        traits = self._persona.traits if self._persona is not None else None
        role = realism.classify_role(entry_name)
        recorded = self._persona.answers if self._persona is not None else {}
        ans = realism.cpt_choice(role, options, recorded, self.conditionals,
                                 self._email_rng)
        if ans is None:
            ans = realism.answer_choice(options, entry_name, traits, self._email_rng)
        if ans is not None and self._persona is not None and role:
            self._persona.answers[role] = ans
        return ans
    
    def fill(self, type_id: Union[int, str], entry_id: Union[str, int], 
             options: List[str], required: bool = False, entry_name: str = '') -> Union[str, List[str]]:
        """
        Fill a form entry with appropriate value.
        
        Args:
            type_id: Form field type ID
            entry_id: Entry ID
            options: Available options for the field
            required: Whether the field is required
            entry_name: Name/label of the entry
        
        Returns:
            Value to fill the field with
        """
        raise NotImplementedError("Subclasses must implement fill method")


class RandomFillStrategy(FillStrategy):
    """Fill form fields with random values."""
    
    def fill(self, type_id: Union[int, str], entry_id: Union[str, int], 
             options: List[str], required: bool = False, entry_name: str = '') -> Union[str, List[str]]:
        """Fill with random values."""
        # Check for custom values first
        if str(entry_id) in self.custom_values:
            return self.custom_values[str(entry_id)]
        
        # Handle email address
        if entry_id == 'emailAddress':
            return self._email_value()

        # Handle different field types
        if type_id in [form.FIELD_TYPE_SHORT_ANSWER, form.FIELD_TYPE_PARAGRAPH]:
            if not required:
                return ''
            
            # Check if this is an age field
            if self._is_age_field(entry_name):
                return self._generate_age()

            # Respondent's name / phone -> realistic, persona-consistent values
            if is_name_field(entry_name):
                return self._person_name()
            if is_phone_field(entry_name):
                return self._phone_value()

            responses = [
                'This is a test response',
                'Automated form submission',
                'Sample answer',
                'Test data entry',
                'Generated response'
            ]
            return random.choice(responses)
        
        if type_id in (form.FIELD_TYPE_MULTIPLE_CHOICE, form.FIELD_TYPE_DROPDOWN):
            if not options:
                return ''
            # Age question shown as range options -> pick one matching the persona/age
            if self.match_age_options and self._is_age_field(entry_name):
                matches = self._age_options(options)
                if matches:
                    return random.choice(matches)
            # Gender question -> pick the option matching the persona's gender
            if is_gender_field(entry_name):
                g = match_gender_option(options, self._gender_for_match())
                if g is not None:
                    return g
            # Education question -> pick a level consistent with the persona's age
            if is_education_field(entry_name):
                edu = self._education_option(options)
                if edu is not None:
                    if self._persona is not None:
                        self._persona.answers["education"] = edu
                    return edu
            # Job-status question -> pick something coherent with the persona's
            # age/education/gender (no <18 civil servants, no S2 schoolkids).
            if self._persona is not None and realism.is_occupation_question(entry_name):
                occ = realism.choose_occupation(
                    options, self._persona.age, self._persona.edu_tier,
                    self._persona.gender, self._email_rng,
                    anomaly_rate=self.anomaly_rate)
                if occ is not None:
                    self._persona.answers["occupation"] = occ
                    return occ
            # Trait/CPT-driven ordinal answer (skill, frequency, device,
            # domicile, duration...) so related questions correlate the way
            # real ones do.
            ans = self._ordinal_answer(options, entry_name)
            if ans is not None:
                return ans
            return random.choice(options)
        
        if type_id == form.FIELD_TYPE_CHECKBOXES:
            if not options:
                return []
            if self._persona is not None and self._persona.traits:
                return realism.choose_checkbox(
                    options, entry_name, self._persona.traits, self._email_rng)
            lo, hi = self._checkbox_range(len(options))
            return random.sample(options, k=random.randint(lo, hi))
        
        if type_id == form.FIELD_TYPE_LINEAR_SCALE:
            if not options:
                return ''
            ans = self._ordinal_answer(options, entry_name)
            if ans is not None:
                return ans
            return random.choice(options)
        
        if type_id == form.FIELD_TYPE_GRID_CHOICE:
            return random.choice(options) if options else ''
        
        if type_id == form.FIELD_TYPE_DATE:
            return datetime.date.today().strftime('%Y-%m-%d')
        
        if type_id == form.FIELD_TYPE_TIME:
            return datetime.datetime.now().strftime('%H:%M')
        
        return ''


class FixedFillStrategy(FillStrategy):
    """Fill form fields with fixed values."""
    
    def __init__(self, email: str = "test@example.com",
                 text_value: str = "Fixed response",
                 custom_values: Optional[Dict] = None,
                 age_range: Optional[str] = None,
                 random_email: bool = False,
                 email_style="mix",
                 email_gender="any",
                 email_seed: Optional[int] = None,
                 checkbox_min: int = 1,
                 checkbox_max: Optional[int] = None,
                 match_age_options: bool = True,
                 coherent_identity: bool = True,
                 email_provider="auto",
                 calibration=None,
                 conditionals=None,
                 anomaly_rate: float = 0.0):
        """
        Initialize with fixed values.

        Args:
            email: Email address
            text_value: Fixed text to use for text fields
            custom_values: Custom value mappings
            age_range: Age range in format "min-max"
            random_email: If True, generate a realistic Indonesian @gmail.com address
            email_style: Generator style (see email_generator.STYLES); may be a {style: %} dict
            email_gender: "any", "male", or "female" (or a {gender: %} dict)
            email_seed: optional int for reproducible email generation
            checkbox_min/checkbox_max: how many options to tick on checkbox fields
            coherent_identity: keep email style, age and education consistent per submission
        """
        super().__init__(email, custom_values, age_range, random_email,
                         email_style, email_gender, email_seed,
                         checkbox_min, checkbox_max, match_age_options,
                         coherent_identity, email_provider,
                         calibration, conditionals, anomaly_rate)
        self.text_value = text_value
    
    def fill(self, type_id: Union[int, str], entry_id: Union[str, int], 
             options: List[str], required: bool = False, entry_name: str = '') -> Union[str, List[str]]:
        """Fill with fixed values."""
        # Check for custom values first
        if str(entry_id) in self.custom_values:
            return self.custom_values[str(entry_id)]
        
        if entry_id == 'emailAddress':
            return self._email_value()

        if type_id in [form.FIELD_TYPE_SHORT_ANSWER, form.FIELD_TYPE_PARAGRAPH]:
            if not required:
                return ''

            # Check if this is an age field
            if self._is_age_field(entry_name):
                return self._generate_age()

            # Respondent's name / phone -> realistic, persona-consistent values
            if is_name_field(entry_name):
                return self._person_name()
            if is_phone_field(entry_name):
                return self._phone_value()

            return self.text_value
        
        if type_id in [form.FIELD_TYPE_MULTIPLE_CHOICE, form.FIELD_TYPE_DROPDOWN,
                       form.FIELD_TYPE_LINEAR_SCALE, form.FIELD_TYPE_GRID_CHOICE]:
            if not options:
                return ''
            if (type_id in (form.FIELD_TYPE_MULTIPLE_CHOICE, form.FIELD_TYPE_DROPDOWN)
                    and self.match_age_options and self._is_age_field(entry_name)):
                matches = self._age_options(options)
                if matches:
                    return matches[0]
            if (type_id in (form.FIELD_TYPE_MULTIPLE_CHOICE, form.FIELD_TYPE_DROPDOWN)
                    and is_gender_field(entry_name)):
                g = match_gender_option(options, self._gender_for_match())
                if g is not None:
                    return g
            if (type_id in (form.FIELD_TYPE_MULTIPLE_CHOICE, form.FIELD_TYPE_DROPDOWN)
                    and is_education_field(entry_name)):
                edu = self._education_option(options)
                if edu is not None:
                    return edu
            return options[0]
        
        if type_id == form.FIELD_TYPE_CHECKBOXES:
            if not options:
                return []
            lo, _ = self._checkbox_range(len(options))
            return list(options[:lo])
        
        if type_id == form.FIELD_TYPE_DATE:
            return datetime.date.today().strftime('%Y-%m-%d')
        
        if type_id == form.FIELD_TYPE_TIME:
            return datetime.datetime.now().strftime('%H:%M')
        
        return ''


# Legacy function for backward compatibility
def fill_random_value(type_id, entry_id, options, required=False, entry_name=''):
    """
    Legacy fill function for backward compatibility.
    
    Note: Use RandomFillStrategy class instead for better control.
    """
    strategy = RandomFillStrategy()
    return strategy.fill(type_id, entry_id, options, required, entry_name)



# ========== Core Functions ========== #

def generate_request_body(
    url: str, 
    only_required: bool = False,
    fill_strategy: Optional[FillStrategy] = None,
    custom_values: Optional[Dict] = None
) -> Optional[Dict[str, Any]]:
    """
    Generate form request body data.
    
    Args:
        url: Google Form URL
        only_required: Only include required fields
        fill_strategy: Strategy to use for filling values
        custom_values: Custom values for specific fields
    
    Returns:
        Dictionary containing form data ready for submission
    """
    try:
        if fill_strategy is None:
            fill_strategy = RandomFillStrategy(custom_values=custom_values)

        # Begin a new coherent persona for this submission (no-op if disabled)
        if hasattr(fill_strategy, "start_submission"):
            fill_strategy.start_submission()

        data = form.get_form_submit_request(
            url,
            only_required=only_required,
            fill_algorithm=fill_strategy.fill,
            output="return",
            with_comment=False
        )
        
        if not data:
            logger.error("Failed to generate request body")
            return None
        
        parsed_data = json.loads(data)
        logger.info(f"Generated request body with {len(parsed_data)} fields")

        # Post-generation logical audit (Gemini point 1). Generation is
        # correct-by-construction, so this is a safety net that flags any
        # impossible age/education/occupation combination that slips through.
        persona = getattr(fill_strategy, "_persona", None)
        if persona is not None and getattr(persona, "answers", None):
            violations = realism.validate_record(
                persona.age, persona.answers.get("education"),
                persona.answers.get("occupation"))
            if violations:
                logger.warning("Logical inconsistency in generated row: "
                               + "; ".join(violations))
        return parsed_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse generated data: {e}")
        return None
    except Exception as e:
        logger.error(f"Error generating request body: {e}")
        return None


def get_page_count(url: str) -> int:
    """
    Get the number of pages in a Google Form.
    
    Args:
        url: Google Form URL
    
    Returns:
        Number of pages in the form (0 if single page or error)
    """
    try:
        entries = form.parse_form_entries(url, only_required=False)
        if not entries:
            return 0
        
        # Check for pageHistory entry
        for entry in entries:
            if entry.get('id') == 'pageHistory':
                page_history = entry.get('default_value', '')
                if page_history:
                    # Count pages from pageHistory (e.g., "0,1,2" = 3 pages)
                    return len(page_history.split(','))
        
        return 0
    except Exception as e:
        logger.debug(f"Error getting page count: {e}")
        return 0


def submit_form(url: str, data: Dict[str, Any], timeout: int = 10, verify_ssl: bool = True) -> bool:
    """
    Submit form data to Google Forms.
    
    Args:
        url: Google Form URL
        data: Form data dictionary
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates
    
    Returns:
        True if submission was successful, False otherwise
    """
    try:
        response_url = form.get_form_response_url(url)
        logger.info(f"Submitting to: {response_url}")
        logger.debug(f"Data: {json.dumps(data, indent=2)}")
        
        response = requests.post(
            response_url, 
            data=data, 
            timeout=timeout,
            verify=verify_ssl,
            allow_redirects=True
        )
        
        # Google Forms typically returns 200 for both success and some errors
        if response.status_code == 200:
            # Check multiple indicators of success
            response_text = response.text.lower()
            
            # Check for success indicators in the response
            success_indicators = [
                'your response has been recorded' in response_text,
                'thank you' in response_text,
                'formResponse' in response.url,
                'closedform' in response.url,
            ]
            
            # Check for error indicators
            error_indicators = [
                'error' in response_text and 'submit' in response_text,
                'invalid' in response_text,
                'formrestricted' in response.url,
            ]
            
            if any(success_indicators) and not any(error_indicators):
                logger.info("✓ Form submitted successfully!")
                return True
            elif any(error_indicators):
                logger.error("Form submission rejected (form may be restricted or have validation errors)")
                logger.debug(f"Response URL: {response.url}")
                logger.debug(f"Response snippet: {response.text[:500]}")
                return False
            else:
                # Ambiguous response - treat as success if status is 200
                logger.info("✓ Form submitted (status 200 received)")
                logger.debug(f"Response URL: {response.url}")
                return True
        else:
            logger.error(f"Submission failed with status code: {response.status_code}")
            logger.debug(f"Response: {response.text[:500]}")
            return False
            
    except requests.Timeout:
        logger.error(f"Request timed out after {timeout} seconds")
        return False
    except requests.RequestException as e:
        logger.error(f"Network error during submission: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during submission: {e}")
        return False


def submit_form_progressive(
    url: str,
    data: Dict[str, Any],
    page_delay: float = 0.5,
    timeout: int = 10,
    verify_ssl: bool = True
) -> bool:
    """
    Submit multi-page form progressively, simulating clicking "Next" button on each page.
    
    This function splits the submission into multiple requests, one for each page,
    which more closely mimics how a user would interact with the form.
    
    Args:
        url: Google Form URL
        data: Complete form data dictionary
        page_delay: Delay between page submissions in seconds
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates
    
    Returns:
        True if all pages were submitted successfully, False otherwise
    """
    try:
        # Check if this is a multi-page form
        page_count = get_page_count(url)
        
        if page_count <= 1:
            # Single page form, use normal submission
            logger.debug("Single page form detected, using normal submission")
            return submit_form(url, data, timeout, verify_ssl)
        
        logger.info(f"Multi-page form detected with {page_count} pages")
        logger.info("Submitting progressively (simulating 'Next' button clicks)...")
        
        response_url = form.get_form_response_url(url)
        
        # Submit each page
        for page_num in range(page_count):
            logger.info(f"📄 Submitting page {page_num + 1}/{page_count}...")
            
            # Create page-specific data
            page_data = data.copy()
            
            # Update pageHistory to show progression
            current_history = ','.join(map(str, range(page_num + 1)))
            page_data['pageHistory'] = current_history
            
            # For pages before the last one, we're just navigating
            is_final_page = (page_num == page_count - 1)
            
            try:
                response = requests.post(
                    response_url,
                    data=page_data,
                    timeout=timeout,
                    verify=verify_ssl,
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    # For final page, check success indicators
                    if is_final_page:
                        response_text = response.text.lower()
                        success_indicators = [
                            'your response has been recorded' in response_text,
                            'thank you' in response_text,
                            'formResponse' in response.url,
                        ]
                        
                        if any(success_indicators):
                            logger.info(f"✓ Page {page_num + 1}/{page_count} submitted (Final page - Success!)")
                        else:
                            logger.info(f"✓ Page {page_num + 1}/{page_count} submitted (Final page)")
                    else:
                        logger.info(f"✓ Page {page_num + 1}/{page_count} submitted (Next)")
                        # Delay before next page
                        if page_delay > 0:
                            time.sleep(page_delay)
                else:
                    logger.error(f"Failed to submit page {page_num + 1} (Status: {response.status_code})")
                    logger.debug(f"Response snippet: {response.text[:300]}")
                    return False
                    
            except requests.RequestException as e:
                logger.error(f"Error submitting page {page_num + 1}: {e}")
                return False
        
        logger.info("✓ All pages submitted successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error in progressive submission: {e}")
        return False


def submit_multiple(
    url: str, 
    count: int = 1, 
    delay: float = 1.0,
    only_required: bool = False,
    fill_strategy: Optional[FillStrategy] = None,
    save_responses: bool = False,
    progressive: bool = False,
    timeout: int = 10,
    delay_jitter: float = 0.0,
    stop_on_failure: bool = False,
    human_timing: bool = True
) -> Dict[str, int]:
    """
    Submit form multiple times.

    Args:
        url: Google Form URL
        count: Number of times to submit
        delay: Delay between submissions in seconds
        only_required: Only fill required fields
        fill_strategy: Strategy for filling values
        save_responses: Save generated responses to file
        progressive: Use progressive page-by-page submission for multi-page forms
        timeout: Request timeout in seconds
        delay_jitter: Random extra delay (0..jitter seconds) added per submission
                      to look less robotic
        stop_on_failure: Abort the batch on the first failed submission
        human_timing: Use a natural, right-skewed delay distribution between
                      submissions instead of a constant gap (avoids a bot-like
                      timestamp pattern)

    Returns:
        Dictionary with submission statistics
    """
    stats = {
        'total': count,
        'successful': 0,
        'failed': 0,
        'responses': []
    }
    
    logger.info(f"Starting batch submission: {count} submissions with {delay}s delay")
    if progressive:
        logger.info("Progressive mode enabled (page-by-page submission)")
    
    for i in range(count):
        logger.info(f"\n--- Submission {i + 1}/{count} ---")
        
        try:
            # Generate new data for each submission
            data = generate_request_body(url, only_required, fill_strategy)
            if not data:
                logger.error("Failed to generate request body")
                stats['failed'] += 1
                continue
            
            if save_responses:
                stats['responses'].append(data)
            
            # Submit (choose method based on progressive flag)
            if progressive:
                success = submit_form_progressive(url, data, timeout=timeout)
            else:
                success = submit_form(url, data, timeout=timeout)

            if success:
                stats['successful'] += 1
            else:
                stats['failed'] += 1
                if stop_on_failure:
                    logger.warning("Stopping batch early (stop_on_failure enabled)")
                    break

            # Delay before next submission (except for last one)
            if i < count - 1:
                if human_timing:
                    # Natural, right-skewed gap so the timestamp column doesn't
                    # show the tell-tale constant spacing of a bot.
                    wait = realism.human_delay(delay if delay > 0 else 8.0)
                    if delay_jitter > 0:
                        wait += random.uniform(0, delay_jitter)
                else:
                    wait = delay + (random.uniform(0, delay_jitter) if delay_jitter > 0 else 0)
                if wait > 0:
                    logger.debug(f"Waiting {wait:.2f}s before next submission...")
                    time.sleep(wait)
                
        except KeyboardInterrupt:
            logger.warning("\nBatch submission interrupted by user")
            break
        except Exception as e:
            logger.error(f"Error in submission {i + 1}: {e}")
            stats['failed'] += 1
    
    # Save responses if requested
    if save_responses and stats['responses']:
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"form_outputs/responses_{timestamp}.json"
            os.makedirs("form_outputs", exist_ok=True)
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(stats['responses'], f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(stats['responses'])} responses to: {filename}")
        except Exception as e:
            logger.error(f"Failed to save responses: {e}")
    
    return stats


def main(
    url: str, 
    only_required: bool = False,
    email: str = "test@example.com",
    custom_values: Optional[Dict] = None,
    count: int = 1,
    delay: float = 1.0,
    strategy: str = "random",
    save_responses: bool = False,
    dry_run: bool = False,
    progressive: bool = False,
    age_range: Optional[str] = None,
    random_email: bool = False,
    email_style: str = "mix",
    email_gender: str = "any",
    email_seed: Optional[int] = None,
    timeout: int = 10,
    delay_jitter: float = 0.0,
    stop_on_failure: bool = False,
    checkbox_min: int = 1,
    checkbox_max: Optional[int] = None,
    match_age_options: bool = True,
    coherent_identity: bool = True,
    email_provider="auto",
    preset: Optional[str] = None,
    anomaly_rate: float = 0.0
) -> bool:
    """
    Main function to fill and submit Google Form.

    Args:
        url: Google Form URL
        only_required: Only fill required fields
        email: Email address for email fields
        custom_values: Custom values for specific fields
        count: Number of submissions
        delay: Delay between submissions
        strategy: Fill strategy ('random' or 'fixed')
        save_responses: Save generated responses
        dry_run: Generate data but don't submit
        progressive: Use progressive page-by-page submission for multi-page forms
        age_range: Age range in format "min-max" (e.g., "18-25")
        random_email: Generate a realistic Indonesian @gmail.com per submission
        email_style: Email generator style (see email_generator.STYLES)
        email_gender: "any", "male", or "female"
        email_seed: optional int for reproducible email generation
        timeout: Request timeout in seconds
        delay_jitter: Random extra delay (0..jitter) added per submission
        stop_on_failure: Abort a batch on the first failure

    Returns:
        True if all submissions were successful
    """
    try:
        # Apply a named preset (form-specific calibration + conditional tables
        # + demographic defaults). Preset main_kwargs only fill options the
        # caller left at their default, so explicit arguments always win.
        calibration = None
        conditionals = None
        if preset:
            pobj = get_preset(preset)
            calibration = pobj.calibration
            conditionals = pobj.conditionals
            logger.info(f"Using preset '{preset}': {pobj.description}")
            cur = dict(random_email=random_email, email_style=email_style,
                       email_gender=email_gender, email_provider=email_provider,
                       checkbox_min=checkbox_min, checkbox_max=checkbox_max,
                       age_range=age_range, anomaly_rate=anomaly_rate)
            dflt = dict(random_email=False, email_style="mix", email_gender="any",
                        email_provider="auto", checkbox_min=1, checkbox_max=None,
                        age_range=None, anomaly_rate=0.0)
            for k, v in pobj.main_kwargs.items():
                if k in cur and cur[k] == dflt.get(k):
                    cur[k] = v
            random_email = cur["random_email"]
            email_style = cur["email_style"]
            email_gender = cur["email_gender"]
            email_provider = cur["email_provider"]
            checkbox_min = cur["checkbox_min"]
            checkbox_max = cur["checkbox_max"]
            age_range = cur["age_range"]
            anomaly_rate = cur["anomaly_rate"]

        # Create fill strategy
        strat_kwargs = dict(
            email=email, custom_values=custom_values, age_range=age_range,
            random_email=random_email, email_style=email_style,
            email_gender=email_gender, email_seed=email_seed,
            checkbox_min=checkbox_min, checkbox_max=checkbox_max,
            match_age_options=match_age_options,
            coherent_identity=coherent_identity,
            email_provider=email_provider,
            calibration=calibration,
            conditionals=conditionals,
            anomaly_rate=anomaly_rate,
        )
        if strategy == "fixed":
            fill_strat = FixedFillStrategy(**strat_kwargs)
        else:
            fill_strat = RandomFillStrategy(**strat_kwargs)
        
        # Check if this is a multi-page form
        page_count = get_page_count(url)
        if page_count > 1 and not dry_run:
            if progressive:
                logger.info(f"🔄 Multi-page form detected ({page_count} pages) - Progressive mode enabled")
            else:
                logger.info(f"📄 Multi-page form detected ({page_count} pages) - Using standard submission")
                logger.info(f"💡 Tip: Use --progressive flag for page-by-page submission simulation")
        
        # Dry run mode - just show what would be submitted
        if dry_run:
            logger.info("=== DRY RUN MODE - No actual submission ===")
            data = generate_request_body(url, only_required, fill_strat, custom_values)
            if data:
                print("\nGenerated form data:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                if page_count > 1:
                    print(f"\nℹ️  This is a multi-page form with {page_count} pages")
                    print(f"   pageHistory field: {data.get('pageHistory', 'N/A')}")
                return True
            return False
        
        # Single submission
        if count == 1:
            data = generate_request_body(url, only_required, fill_strat, custom_values)
            if not data:
                return False
            
            if save_responses:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"form_outputs/response_{timestamp}.json"
                os.makedirs("form_outputs", exist_ok=True)
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved response to: {filename}")
            
            # Choose submission method
            if progressive:
                success = submit_form_progressive(url, data, timeout=timeout)
            else:
                success = submit_form(url, data, timeout=timeout)

            if success:
                logger.info("\n✓ Done! Form submitted successfully.")
            else:
                logger.error("\n✗ Failed to submit form.")
            return success
        
        # Multiple submissions
        else:
            stats = submit_multiple(
                url, count, delay, only_required,
                fill_strat, save_responses, progressive,
                timeout=timeout, delay_jitter=delay_jitter,
                stop_on_failure=stop_on_failure
            )
            
            logger.info(f"\n{'='*50}")
            logger.info("SUBMISSION SUMMARY")
            logger.info(f"{'='*50}")
            logger.info(f"Total attempts:  {stats['total']}")
            logger.info(f"Successful:      {stats['successful']} ✓")
            logger.info(f"Failed:          {stats['failed']} ✗")
            logger.info(f"Success rate:    {stats['successful']/stats['total']*100:.1f}%")
            logger.info(f"{'='*50}")
            
            return stats['failed'] == 0
            
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if logger.level == logging.DEBUG:
            import traceback
            traceback.print_exc()
        return False



# ========== Command Line Interface ========== #

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Google Form Auto-Fill and Submit Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Submit form once with random values
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform
  
  # Submit only required fields
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform -r
  
  # Submit with custom email
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --email myemail@gmail.com
  
  # Submit with age range for age/umur fields
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --age-range "18-25"
  
  # Submit multiple times with delay
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --count 5 --delay 2
  
  # Use fixed values instead of random
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --strategy fixed
  
  # Dry run (generate data but don't submit)
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --dry-run
  
  # Save generated responses to file
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --save-responses
  
  # Load custom values from JSON file
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --custom-file values.json
  
  # Verbose mode for debugging
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform -v
  
  # Progressive mode for multi-page forms (simulates clicking "Next" button)
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --progressive

Custom values JSON format:
  {
    "entry.123456": "Custom value",
    "entry.789012": ["Option 1", "Option 2"]
  }
        """
    )
    
    # Required arguments
    parser.add_argument(
        'url', 
        help='Google Form URL (viewform or formResponse)'
    )
    
    # Fill options
    fill_group = parser.add_argument_group('Fill Options')
    fill_group.add_argument(
        '-r', '--required', 
        action='store_true', 
        help='Only fill required fields'
    )
    fill_group.add_argument(
        '--email', 
        default='test@example.com',
        help='Email address for email fields (default: test@example.com)'
    )
    fill_group.add_argument(
        '--strategy',
        choices=['random', 'fixed'],
        default='random',
        help='Fill strategy: random or fixed values (default: random)'
    )
    fill_group.add_argument(
        '--custom-file',
        metavar='FILE',
        help='JSON file with custom field values'
    )
    fill_group.add_argument(
        '--age-range',
        metavar='MIN-MAX',
        help='Age range for age/umur fields (e.g., "18-25", "20-30")'
    )
    fill_group.add_argument(
        '--random-email',
        action='store_true',
        help='Generate a realistic Indonesian @gmail.com address for the email '
             'field (a fresh one per submission) instead of using --email'
    )
    fill_group.add_argument(
        '--email-style',
        choices=email_generator.STYLES,
        default='mix',
        help='Style for --random-email: classic, professional, millennial, '
             'genz, alpha, chinese, or mix (default)'
    )
    fill_group.add_argument(
        '--email-gender',
        choices=email_generator.GENDERS,
        default='any',
        help='Gender for generated email names (default: any)'
    )
    fill_group.add_argument(
        '--email-style-mix',
        metavar='SPEC',
        help='Custom style percentages for --random-email, e.g. '
             '"genz=70,professional=30". Overrides --email-style. '
             f'Valid styles: {", ".join(email_generator.CONCRETE_STYLES)}'
    )
    fill_group.add_argument(
        '--email-gender-mix',
        metavar='SPEC',
        help='Custom gender percentages for generated emails, e.g. '
             '"male=50,female=50". Overrides --email-gender.'
    )
    fill_group.add_argument(
        '--email-provider',
        choices=email_generator.PROVIDER_CHOICES,
        default='auto',
        help='Force the email provider domain for --random-email. "auto" (default) '
             'picks an era-appropriate provider; or choose gmail.com, yahoo.com, '
             'outlook.com, etc. ("company" = a random workplace/edu domain)'
    )
    fill_group.add_argument(
        '--email-provider-mix',
        metavar='SPEC',
        help='Custom provider percentages for --random-email, e.g. '
             '"gmail.com=70,yahoo.com=20,outlook.com=10". Overrides --email-provider.'
    )
    fill_group.add_argument(
        '--email-seed',
        type=int,
        metavar='N',
        help='Seed for reproducible email generation'
    )
    fill_group.add_argument(
        '--checkbox-min',
        type=int,
        default=1,
        metavar='N',
        help='Minimum options to tick on checkbox ("choose many") fields (default: 1)'
    )
    fill_group.add_argument(
        '--checkbox-max',
        type=int,
        metavar='N',
        help='Maximum options to tick on checkbox fields (default: min(options, 3))'
    )
    fill_group.add_argument(
        '--no-age-match',
        action='store_false',
        dest='match_age_options',
        help='Disable matching --age-range to range options on age multiple-choice/'
             'dropdown fields (pick at random instead)'
    )
    fill_group.add_argument(
        '--no-coherent',
        action='store_false',
        dest='coherent_identity',
        help='Disable coherent persona generation (by default the email style, '
             'age and education level are kept consistent per submission)'
    )
    fill_group.add_argument(
        '--preset',
        metavar='NAME',
        choices=list(PRESETS.keys()),
        help='Apply a form-specific realism preset (calibration + conditional '
             'tables + demographic mix). Available: '
             + ', '.join(PRESETS.keys())
    )
    fill_group.add_argument(
        '--anomaly-rate',
        type=float,
        default=0.0,
        metavar='RATE',
        help='Fraction (0..1) of submissions allowed a rare-but-legal '
             'demographic outlier, e.g. 0.03 for ~3%% (default: 0). Illegal '
             'combinations stay impossible regardless.'
    )

    # Submission options
    submit_group = parser.add_argument_group('Submission Options')
    submit_group.add_argument(
        '--count',
        type=int,
        default=1,
        metavar='N',
        help='Number of times to submit the form (default: 1)'
    )
    submit_group.add_argument(
        '--delay',
        type=float,
        default=1.0,
        metavar='SEC',
        help='Delay between submissions in seconds (default: 1.0)'
    )
    submit_group.add_argument(
        '--delay-jitter',
        type=float,
        default=0.0,
        metavar='SEC',
        help='Random extra delay (0..JITTER s) added per submission to look human (default: 0)'
    )
    submit_group.add_argument(
        '--timeout',
        type=int,
        default=10,
        metavar='SEC',
        help='Request timeout in seconds (default: 10)'
    )
    submit_group.add_argument(
        '--stop-on-failure',
        action='store_true',
        help='Abort a batch on the first failed submission'
    )
    submit_group.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate form data but do not submit'
    )
    submit_group.add_argument(
        '--progressive',
        action='store_true',
        help='Use progressive page-by-page submission for multi-page forms (simulates "Next" button)'
    )
    
    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument(
        '--save-responses',
        action='store_true',
        help='Save generated responses to JSON file in form_outputs/'
    )
    output_group.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging output'
    )
    output_group.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Minimal output (errors only)'
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.quiet:
        logger.setLevel(logging.ERROR)
    elif args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Load custom values from file if provided
    custom_values = None
    if args.custom_file:
        try:
            if not os.path.exists(args.custom_file):
                logger.error(f"Custom values file not found: {args.custom_file}")
                sys.exit(1)
            
            with open(args.custom_file, 'r', encoding='utf-8') as f:
                custom_values = json.load(f)
            logger.info(f"Loaded {len(custom_values)} custom values from {args.custom_file}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in custom values file: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error loading custom values file: {e}")
            sys.exit(1)
    
    # Validate arguments
    if args.count < 1:
        logger.error("Count must be at least 1")
        sys.exit(1)
    
    if args.delay < 0:
        logger.error("Delay cannot be negative")
        sys.exit(1)

    # Parse optional percentage blends for email style/gender
    email_style_arg = args.email_style
    email_gender_arg = args.email_gender
    email_provider_arg = args.email_provider
    try:
        if args.email_style_mix:
            email_style_arg = parse_weight_spec(
                args.email_style_mix, email_generator.CONCRETE_STYLES, "style")
        if args.email_gender_mix:
            email_gender_arg = parse_weight_spec(
                args.email_gender_mix, ["male", "female", "any"], "gender")
        if args.email_provider_mix:
            email_provider_arg = parse_weight_spec(
                args.email_provider_mix, email_generator.PROVIDER_CHOICES, "provider")
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Run main function
    try:
        success = main(
            url=args.url,
            only_required=args.required,
            email=args.email,
            custom_values=custom_values,
            count=args.count,
            delay=args.delay,
            strategy=args.strategy,
            save_responses=args.save_responses,
            dry_run=args.dry_run,
            progressive=args.progressive,
            age_range=args.age_range,
            random_email=args.random_email,
            email_style=email_style_arg,
            email_gender=email_gender_arg,
            email_seed=args.email_seed,
            timeout=args.timeout,
            delay_jitter=args.delay_jitter,
            stop_on_failure=args.stop_on_failure,
            checkbox_min=args.checkbox_min,
            checkbox_max=args.checkbox_max,
            match_age_options=args.match_age_options,
            coherent_identity=args.coherent_identity,
            email_provider=email_provider_arg,
            preset=args.preset,
            anomaly_rate=args.anomaly_rate
        )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.warning("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
