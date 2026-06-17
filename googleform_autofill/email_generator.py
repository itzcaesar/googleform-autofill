"""
Realistic Indonesian email address & identity generator.

Produces lowercase email addresses that mimic how Indonesians of different
generations build their usernames, across several common providers. Supports
several *styles* (eras), gender-aware name selection, compound/regional names,
light leetspeak for the younger styles, name-derived usernames, reproducible
output via a seed, and batch de-duplication.

Styles
------
  classic       : full-name adults, dotted or joined, birth-year-ish digits
  professional  : clean firstname.lastname, rarely any digits
  millennial     : 1985-1999 birth years, full names
  genz          : aesthetic / gamer / nickname (2000-2010 vibe)
  alpha         : very aesthetic + leetspeak (2010-2017 vibe)
  chinese       : Chinese-Indonesian given name + family name
  mix (default) : weighted blend of all of the above

Usernames obey each provider's rules (Gmail: letters, numbers and dots only;
others additionally allow underscores/hyphens), 6-30 chars, no leading/trailing
or consecutive separators.

References:
  - Surnames (frequency-ranked): https://surnam.es/indonesia
  - Common given names: https://en.tempo.co/read/1686766/20-most-common-indonesian-names
  - Gmail username rules: https://support.google.com/mail/answer/9211434
"""

import random
import re

DOMAIN = "gmail.com"

# Email providers weighted per style/era. Younger styles skew almost entirely to
# gmail (and a little icloud); older styles keep more legacy yahoo/hotmail.
PROVIDERS = {
    "classic":      {"gmail.com": 52, "yahoo.com": 18, "yahoo.co.id": 15,
                     "hotmail.com": 8, "outlook.com": 7},
    "professional": {"gmail.com": 70, "outlook.com": 13, "yahoo.com": 8,
                     "hotmail.com": 5, "company": 4},
    "millennial":   {"gmail.com": 67, "yahoo.com": 14, "yahoo.co.id": 8,
                     "hotmail.com": 5, "outlook.com": 6},
    "genz":         {"gmail.com": 90, "icloud.com": 5, "yahoo.com": 3,
                     "outlook.com": 2},
    "alpha":        {"gmail.com": 92, "icloud.com": 6, "outlook.com": 2},
    "chinese":      {"gmail.com": 76, "outlook.com": 9, "yahoo.com": 8,
                     "hotmail.com": 7},
}

# Plausible Indonesian domains for the "company" provider, split by life stage.
# Campus (.ac.id) addresses fit current students / recent grads; corporate
# addresses imply employment. School-age respondents get neither (see
# _work_domain) and fall back to a consumer provider instead.
CAMPUS_DOMAINS = [
    "ui.ac.id", "ugm.ac.id", "itb.ac.id", "binus.ac.id", "students.itb.ac.id",
    "student.uns.ac.id", "upi.edu", "unpad.ac.id", "student.unair.ac.id",
]
CORPORATE_DOMAINS = [
    "telkom.co.id", "bca.co.id", "pertamina.com", "bri.co.id", "mandiri.co.id",
    "kompas.com", "tokopedia.com", "gojek.com", "astra.co.id", "unilever.com",
]
WORK_DOMAINS = CAMPUS_DOMAINS + CORPORATE_DOMAINS  # back-compat alias

# Providers a user can explicitly choose. "auto" keeps the era-weighted blend
# above; "company" picks an age-appropriate campus/corporate domain.
PROVIDER_CHOICES = ["auto", "gmail.com", "yahoo.com", "yahoo.co.id",
                    "hotmail.com", "outlook.com", "icloud.com", "proton.me",
                    "company"]

# Real Indonesian public figures (politicians, artists, athletes, influencers)
# whose names the random pools could otherwise accidentally assemble. Stored
# normalized (lowercase, letters only). Any generated name/username matching one
# of these is rejected and regenerated, so respondents never look like a celebrity.
BLOCKED_NAMES = {
    # artists / entertainers
    "ivangunawan", "raffiahmad", "nagitaslavina", "agnezmo", "agnesmonica",
    "raisaandriana", "ananghermansyah", "diansastrowardoyo", "diansastro",
    "niaramadhani", "arielnoah", "maiaestianty", "deddycorbuzier",
    "attahalilintar", "ariwibowo", "rezarahadian", "lunamaya", "citacitata",
    "viavallen", "gitagutawa", "dewipersik", "krisdayanti", "syahrini",
    "ayutingting", "vidialdiano", "afgansyahreza", "rossa", "isyanasarasvati",
    "judika", "rizkyfebian", "prilylatuconsina", "verrelbramasta",
    "bungacitralestari", "titikamal",
    # politicians / public officials
    "jokowidodo", "prabowosubianto", "susilobambangyudhoyono", "megawati",
    "ganjarpranowo", "aniesbaswedan", "ridwankamil", "sandiagauno",
    "srimulyani", "basukitjahajapurnama", "gibranrakabuming",
    # athletes
    "bambangpamungkas", "taufikhidayat", "jonathanchristie", "kevinsanjaya",
    "marcusgideon", "egymaulana",
}

STYLES = ["classic", "professional", "millennial", "genz", "alpha", "chinese", "mix"]
GENDERS = ["any", "male", "female"]

# Concrete styles only (everything except the "mix" meta-style)
CONCRETE_STYLES = ["classic", "professional", "millennial", "genz", "alpha", "chinese"]

# Plausible *current* age range (inclusive) for a person whose email reads like
# each style. Used so a generated age/education lines up with the email vibe:
# a Gen Alpha handle implies a teenager, a millennial handle implies a 30-something.
STYLE_AGE_RANGES = {
    "alpha":        (13, 17),   # born ~2010+, still in school
    "genz":         (17, 27),   # late teens / twenties
    "millennial":   (28, 43),   # born ~1983-1998
    "professional": (27, 50),   # working-age adults, clean names
    "classic":      (40, 65),   # older, formal full names
    "chinese":      (17, 50),   # broad adult range
}

# Weights used by the "mix" style when choosing a concrete style per address
_MIX_WEIGHTS = {
    "classic": 22, "professional": 12, "millennial": 14,
    "genz": 26, "alpha": 12, "chinese": 14,
}

# ----------------------------- Name pools ----------------------------- #

MALE_FIRST = [
    "adi", "agus", "ahmad", "aldi", "andi", "angga", "anton", "ari", "arief",
    "arif", "bagas", "bagus", "bambang", "bayu", "bima", "budi", "cahyo",
    "dafa", "dedi", "deni", "dimas", "dion", "doni", "dwiki", "eko", "fadil",
    "fahmi", "faisal", "fajar", "farhan", "ferdi", "firman", "galih", "gilang",
    "hadi", "hafiz", "hendra", "hendro", "ibnu", "ilham", "indra", "irfan",
    "iqbal", "joko", "kurnia", "naufal", "panji", "putra", "rafa", "raffa",
    "raihan", "rama", "rangga", "rendi", "reza", "rizal", "rizki", "rizky",
    "rudi", "satria", "surya", "teguh", "tio", "wahyu", "wawan","wisnu", "yoga",
     "yusuf", "zaki",
    # extra
    "adnan", "akbar", "alif", "aryo", "danang", "denny", "edwin", "fauzan",
    "ghani", "hafidz", "ivan", "krisna", "luthfi", "miftah", "nanda", "oki",
    "rendy", "ridho", "rifki", "samuel", "taufik", "umar", "vito", "yandi",
]

FEMALE_FIRST = [
    "alya", "aminah", "anisa", "annisa", "aqila", "aulia", "ayu", "cantika",
    "citra", "dewi", "devi", "diah", "dinda", "eka", "endang", "fatimah",
    "fitri", "gita", "hana", "indah", "intan", "kartika", "keisha", "khanza",
    "lia", "maya", "mega", "melati", "nabila", "nadia", "nadya", "nayla",
    "novita", "nur", "putri", "rahma", "rahmi", "raisa", "ratna", "rina",
    "rini", "ririn", "salsabila", "sari", "sinta", "siti", "sri", "suci",
    "syifa", "tari", "tika", "vina", "wardah", "wulan", "yanti", "yuni",
    "zahra",
    # extra
    "adelia", "amel", "bunga", "clara", "dian", "elsa", "farah", "gisel",
    "hesti", "ika", "jihan", "kirana", "lala", "mira", "nisa", "olla",
    "puspa", "qonita", "riris", "shofia", "talita", "ulfa", "vania", "winda",
]

# Tokens commonly used as a *first* token in compound Indonesian names
RELIGIOUS_MALE = ["muhammad", "mohammad", "ahmad", "abdul"]
RELIGIOUS_FEMALE = ["siti", "nur", "dewi"]
ORDINAL = ["eka", "dwi", "tri", "catur"]                  # Javanese birth-order
BALINESE_MALE = ["putu", "kadek", "komang", "ketut", "gede", "wayan", "made"]
BALINESE_FEMALE = ["putu", "kadek", "komang", "ketut", "luh", "wayan", "made"]

# Common second/middle given tokens for compound names
MIDDLE = [
    "putra", "putri", "pratama", "pratiwi", "ramadhan", "permata", "cahya",
    "aji", "ayu", "dwi", "tri", "nugraha", "kusuma", "wati", "ningsih",
]

SURNAMES = [
    # Frequency-ranked common surnames
    "sari", "setiawan", "hidayat", "lestari", "saputra", "wati", "rahayu",
    "kurniawan", "santoso", "putra", "susanti", "wahyuni", "ningsih",
    "susanto", "gunawan", "arifin", "astuti", "wijaya", "handayani",
    "rahman", "irawan", "hasanah", "nurhayati", "wulandari", "wibowo",
    "efendi", "yanti", "maulana", "hadi", "suryani", "wahyudi", "pratama",
    "utami", "anwar", "hermawan", "prasetyo", "rahmawati", "nugroho",
    "rohman", "ramadhan", "pratiwi", "permana", "kusuma", "cahyono",
    "firmansyah", "pangestu", "mahendra", "anggraini", "oktaviani", "puspita",
    # Batak / Sumatran family names
    "siregar", "nasution", "lubis", "harahap", "sinaga", "purba",
    "simanjuntak", "situmorang", "nainggolan", "panjaitan", "manurung",
    "ginting", "tarigan", "sembiring", "hutapea", "sitorus", "pasaribu",
    "damanik", "sihombing",
]

# Chinese-Indonesian
CHINESE_FIRST = [
    "kevin", "jessica", "felicia", "vincent", "steven", "michelle", "william",
    "eric", "andreas", "christine", "edward", "jonathan", "clarissa",
    "nicholas", "brian", "melissa", "fenny", "ricky", "yulia", "stevanie",
    "albert", "richard", "vanessa", "angeline",
]
CHINESE_SURNAME = [
    "wijaya", "tanuwijaya", "halim", "salim", "santoso", "hartono", "gunawan",
    "kurniawan", "setiawan", "wibowo", "sutanto", "budiman", "susanto",
    "limanto", "tanoto", "wijdjaja", "thejakusuma",
]

# ----------------------- Gen Z / Gen Alpha flavour -------------------- #

GENZ_MALE = [
    "rafa", "raffa", "kenzo", "bryan", "kevin", "zaki", "rasya", "alvaro",
    "gibran", "rayhan", "adelio", "fathan", "dafa", "elano", "kenan",
    "naufal", "arsy", "raihan", "bima", "keenan", "xavier", "ezar",
]
GENZ_FEMALE = [
    "kayla", "keisha", "bilqis", "aqila", "khanza", "shakira", "nayla",
    "vanya", "cleo", "aira", "biella", "nadya", "queen", "raisa", "syifa",
    "alika", "rara", "zee", "felicia", "jessica", "kenzie", "alesha",
]

AESTHETIC = [
    "luvr", "lover", "core", "vibes", "moon", "star", "starz", "angel",
    "baby", "bby", "sad", "soft", "cloud", "dreamy", "cherry", "peachy",
    "bunny", "kitty", "saturn", "pluto", "galaxy", "cute", "sleepy", "bored",
    "gabut", "santuy", "malas", "lazy", "honey", "lonely", "delulu", "slay",
    "aura", "rizz", "skibidi", "mewing",
    # extra flavour
    "sunset", "rain", "storm", "frost", "ocean", "velvet", "amber", "mocha",
    "latte", "mint", "blush", "ghost", "echo", "nova", "ember", "lunar",
    "fluffy", "sugar", "candy", "boba", "matcha", "strawberry", "vanilla",
    "comel", "kepo", "mageran", "rebahan", "healing",
]

GAMERTAG = [
    "xd", "ttv", "yt", "gg", "pro", "noob", "afk", "clutch", "op", "ez",
    "69", "123", "007", "777", "999", "21", "1x", "real", "ffx", "mlbb",
    # extra flavour
    "ml", "ff", "pubg", "valo", "genshin", "roblox", "sigma", "based",
    "main", "alt", "smurf", "rank", "mvp", "goat", "wibu", "otaku",
]

PREFIX = ["its", "itz", "im", "real", "the", "just", "not", "ur", "yours", "x",
          "official", "iam", "call", "only", "lil", "big", "mr", "ms"]

_LEET = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5"}


# ------------------------------ Helpers ------------------------------- #

def _rng(rng):
    return rng if rng is not None else random


def _leetify(text: str, rng, prob: float = 0.5) -> str:
    """Randomly substitute some letters with leetspeak digits."""
    r = _rng(rng)
    if r.random() > prob:
        return text
    out = []
    for ch in text:
        sub = _LEET.get(ch)
        out.append(sub if (sub and r.random() < 0.4) else ch)
    return "".join(out)


def _year(rng, lo: int, hi: int) -> str:
    r = _rng(rng)
    y = r.randint(lo, hi)
    return r.choice([str(y), f"{y % 100:02d}"])


def _short_num(rng) -> str:
    r = _rng(rng)
    return r.choice([
        str(r.randint(1, 99)), str(r.randint(1, 999)),
        f"{r.randint(1, 31):02d}", r.choice(["88", "99", "77", "12", "23"]),
    ])


def _sanitize(local: str, provider: str = "gmail.com", rng=None) -> str:
    """Force a username to satisfy the provider's rules.

    Gmail allows only letters, numbers and dots. Other providers additionally
    allow underscores and hyphens. All output is lowercased, 6-30 chars, with no
    leading/trailing or repeated separators.
    """
    r = _rng(rng)
    local = local.lower()
    if provider == "gmail.com":
        local = re.sub(r"[^a-z0-9.]", "", local)
        local = re.sub(r"\.{2,}", ".", local)
        local = local.strip(".")
    else:
        local = re.sub(r"[^a-z0-9._-]", "", local)
        # collapse any run of separators down to a single separator
        local = re.sub(r"([._-])[._-]+", r"\1", local)
        local = local.strip("._-")
    if len(local) < 6:
        local = (local + str(r.randint(100, 99999)))[:30].strip("._-")
    if len(local) > 30:
        local = local[:30].rstrip("._-")
    return local


def _work_domain(rng, age):
    """Pick a campus/corporate domain appropriate to ``age``, or None when the
    person is too young to plausibly have one (school age)."""
    r = _rng(rng)
    if age is None:
        age = 30
    if age < 18:
        return None                      # school-age: no work/campus email
    if age <= 23:                        # student / fresh grad
        if age >= 22 and r.random() < 0.3:
            return r.choice(CORPORATE_DOMAINS)
        return r.choice(CAMPUS_DOMAINS)
    if age <= 26:                        # could be either
        return r.choice(CAMPUS_DOMAINS if r.random() < 0.4 else CORPORATE_DOMAINS)
    return r.choice(CORPORATE_DOMAINS)   # working adult


def _pick_provider(rng, style: str, provider=None, age=None) -> str:
    """Pick an email provider domain.

    ``provider`` may be:
      - None or "auto": era-weighted blend appropriate to ``style`` (default)
      - a provider name (e.g. "gmail.com" or "company"): forced
      - a dict of {provider: weight}: weighted blend (an "auto" key falls back
        to the era-weighted blend)

    ``age`` (when known) keeps the "company" provider realistic: school-age
    respondents never get a work/campus address and fall back to a consumer
    provider, students get campus (.ac.id) domains, adults get corporate ones.
    """
    r = _rng(rng)
    choice = None
    if isinstance(provider, dict):
        picked = _pick_weighted(r, provider, "auto")
        if picked and picked != "auto":
            choice = picked
    elif provider and provider != "auto":
        choice = provider
    if choice is None:
        # Auto: weight by the style's era
        table = PROVIDERS.get(style, {"gmail.com": 100})
        names = list(table.keys())
        weights = [table[n] for n in names]
        choice = r.choices(names, weights=weights, k=1)[0]
    if choice == "company":
        work = _work_domain(r, age)
        if work:
            return work
        # Too young for a work/campus address -> consumer provider instead
        return "icloud.com" if r.random() < 0.15 else "gmail.com"
    return choice


# --------------------------- Name selection --------------------------- #

def _given(rng, gender: str, style: str) -> str:
    r = _rng(rng)
    if style == "chinese":
        return r.choice(CHINESE_FIRST)
    if style in ("genz", "alpha"):
        if gender == "male":
            return r.choice(GENZ_MALE)
        if gender == "female":
            return r.choice(GENZ_FEMALE)
        return r.choice(GENZ_MALE + GENZ_FEMALE)
    if gender == "male":
        return r.choice(MALE_FIRST)
    if gender == "female":
        return r.choice(FEMALE_FIRST)
    return r.choice(MALE_FIRST + FEMALE_FIRST)


def _family(rng, style: str) -> str:
    r = _rng(rng)
    if style == "chinese":
        return r.choice(CHINESE_SURNAME)
    return r.choice(SURNAMES)


def _name_parts(rng, gender: str, style: str) -> dict:
    """Pick raw, separator-free name tokens for a persona.

    Returns a dict with keys prefix / first / mid / last (any may be None).
    These feed both the human-readable display name and the email username so
    a respondent's name and email address agree with each other.
    """
    r = _rng(rng)
    if style == "chinese":
        return {"prefix": None, "first": r.choice(CHINESE_FIRST),
                "mid": None, "last": r.choice(CHINESE_SURNAME)}
    if style in ("genz", "alpha"):
        first = _given(rng, gender, style)
        last = r.choice(SURNAMES) if r.random() < 0.5 else None
        return {"prefix": None, "first": first, "mid": None, "last": last}
    # classic / professional / millennial
    first = _given(rng, gender, "classic")
    prefix = None
    roll = r.random()
    if roll < 0.12:
        prefix = r.choice(RELIGIOUS_MALE if gender != "female" else RELIGIOUS_FEMALE)
    elif roll < 0.18:
        prefix = r.choice(ORDINAL)
    elif roll < 0.24:
        prefix = r.choice(BALINESE_MALE if gender != "female" else BALINESE_FEMALE)
    mid = r.choice(MIDDLE) if r.random() < 0.22 else None
    last = _family(rng, style)
    return {"prefix": prefix, "first": first, "mid": mid, "last": last}


def _name_tokens(parts: dict) -> list:
    return [t for t in (parts.get("prefix"), parts.get("first"),
                        parts.get("mid"), parts.get("last")) if t]


def display_name(parts: dict) -> str:
    """Human-readable full name, e.g. 'Muhammad Adi Santoso'."""
    return " ".join(t.capitalize() for t in _name_tokens(parts)) or "Anonim"


def _norm_alpha(text: str) -> str:
    """Lowercase, letters-only form of a string for blocklist comparison."""
    return re.sub(r"[^a-z]", "", text.lower())


def _is_celebrity(name: str, username: str = "") -> bool:
    """True if the display name or username resembles a real public figure."""
    nn = _norm_alpha(name)
    un = _norm_alpha(username)
    for b in BLOCKED_NAMES:
        if b and (b in nn or (un and b in un)):
            return True
    return False


def _sep(rng, allow_us: bool) -> str:
    """A separator between name tokens. Underscores only when the provider
    allows them (i.e. not Gmail)."""
    r = _rng(rng)
    return r.choice([".", "", "_", "."] if allow_us else [".", ""])


# ----------------------------- Builders ------------------------------- #

def _name_style_username(rng, parts: dict, style: str, allow_us: bool = False) -> str:
    """classic / professional / millennial / chinese (returns un-sanitized local)."""
    r = _rng(rng)
    prefix, first = parts.get("prefix"), parts["first"]
    mid, last = parts.get("mid"), parts.get("last") or _family(rng, style)
    sep = _sep(rng, allow_us)

    # Occasionally fold the prefix (e.g. 'muhammad') into the first token
    fbase = first
    if prefix and r.random() < 0.5:
        fbase = f"{prefix}{r.choice(['.', '', '_'] if allow_us else ['.', ''])}{first}"

    if style == "professional":
        local = f"{first}.{last}" if r.random() < 0.65 else f"{first}{last}"
        if mid and r.random() < 0.2:
            local = f"{first}.{mid}.{last}"
        if r.random() < 0.18:
            local += _year(rng, 1985, 2000)
        return local

    year = _year(rng, 1985, 1999) if style == "millennial" else _year(rng, 1980, 2003)

    pattern = r.choices(
        ["first_last", "first_last_num", "last_first", "first_mid_last",
         "finit_last", "first_num", "first_last_dotnum", "first_initlast_num",
         "last_first_num"],
        weights=[16, 24, 7, 9, 8, 7, 12, 9, 8], k=1,
    )[0]

    if pattern == "first_last":
        local = f"{fbase}{sep}{last}"
    elif pattern == "first_last_num":
        local = f"{first}{sep}{last}{year}"
    elif pattern == "last_first":
        local = f"{last}{sep}{first}"
    elif pattern == "first_mid_last":
        local = f"{first}{sep}{mid or r.choice(MIDDLE)}{sep}{last}"
    elif pattern == "finit_last":
        local = f"{first[0]}{last}{_short_num(rng) if r.random() < 0.4 else ''}"
    elif pattern == "first_num":
        local = f"{first}{year}"
    elif pattern == "first_initlast_num":
        local = f"{first}{sep}{last[0]}{_short_num(rng)}"
    elif pattern == "last_first_num":
        local = f"{last}{sep}{first}{_short_num(rng) if r.random() < 0.5 else ''}"
    else:
        local = f"{first}.{last}.{year}"
    return local


def _nickname_username(rng, parts: dict, style: str, allow_us: bool = False) -> str:
    """genz / alpha (returns un-sanitized local)."""
    r = _rng(rng)
    name = parts["first"]
    last = parts.get("last")
    sep = _sep(rng, allow_us)
    is_alpha = (style == "alpha")
    year = _year(rng, 2010, 2017) if is_alpha else _year(rng, 2000, 2010)

    pattern = r.choices(
        ["prefix_name", "name_aesthetic", "name_repeat", "name_gamertag",
         "aesthetic_name", "name_year", "x_name_x", "name_leet",
         "name_aesthetic_num", "name_last", "name_dot_aesthetic",
         "aesthetic_name_year"],
        weights=[12, 18, 8, 14, 7, 11, 4, 7, 6, 6, 4, 3], k=1,
    )[0]

    if pattern == "prefix_name":
        local = f"{r.choice(PREFIX)}{sep}{name}"
    elif pattern == "name_aesthetic":
        local = f"{name}{sep}{r.choice(AESTHETIC)}"
    elif pattern == "name_repeat":
        local = f"{name}{name[-1] * r.randint(2, 4)}"
    elif pattern == "name_gamertag":
        local = f"{name}{sep}{r.choice(GAMERTAG)}"
    elif pattern == "aesthetic_name":
        local = f"{r.choice(AESTHETIC)}{sep}{name}"
    elif pattern == "name_year":
        local = f"{name}{year}"
    elif pattern == "x_name_x":
        local = f"x{name}x"
    elif pattern == "name_aesthetic_num":
        local = f"{name}{sep}{r.choice(AESTHETIC)}{_short_num(rng)}"
    elif pattern == "name_last":
        if last:
            local = f"{name}{sep}{last}{_short_num(rng) if r.random() < 0.5 else ''}"
        else:
            local = f"{name}{sep}{r.choice(AESTHETIC)}"
    elif pattern == "name_dot_aesthetic":
        local = f"{name}.{r.choice(AESTHETIC)}"
    elif pattern == "aesthetic_name_year":
        local = f"{r.choice(AESTHETIC)}{name}{year}"
    else:  # name_leet
        local = f"{name}{r.choice(['69', '77', '777', '21', '23', '99'])}"

    # Alpha leans harder into leetspeak; genz gets only a tiny touch (mostly clean)
    local = _leetify(local, rng, prob=0.55 if is_alpha else 0.06)
    return local


def _pick_weighted(rng, weights: dict, fallback):
    """Pick a key from a {name: weight} dict, ignoring non-positive weights.

    Weights are relative, so they can be percentages (e.g. summing to 100) or
    any other positive numbers. Returns ``fallback`` if nothing is selectable.
    """
    r = _rng(rng)
    items = [(k, float(v)) for k, v in weights.items() if v and float(v) > 0]
    if not items:
        return fallback
    names = [k for k, _ in items]
    w = [v for _, v in items]
    return r.choices(names, weights=w, k=1)[0]


def _resolve_style(rng, style) -> str:
    """Resolve a style spec into a single concrete style.

    ``style`` may be:
      - a style name from STYLES (a "mix" is expanded via _MIX_WEIGHTS)
      - a dict mapping style names to percentages/weights, e.g.
        {"genz": 60, "professional": 40}; "mix" keys are themselves expanded.
    """
    if isinstance(style, dict):
        picked = _pick_weighted(rng, style, "mix")
        return _resolve_style(rng, picked)
    if style not in STYLES:
        style = "mix"
    if style != "mix":
        return style
    r = _rng(rng)
    names = list(_MIX_WEIGHTS.keys())
    weights = [_MIX_WEIGHTS[n] for n in names]
    return r.choices(names, weights=weights, k=1)[0]


def _resolve_gender(rng, gender) -> str:
    """Resolve a gender spec into a single concrete gender.

    ``gender`` may be a name from GENDERS, or a dict mapping gender names to
    percentages/weights, e.g. {"male": 50, "female": 50}.
    """
    if isinstance(gender, dict):
        picked = _pick_weighted(rng, gender, "any")
        return picked if picked in GENDERS else "any"
    return gender if gender in GENDERS else "any"


# Public wrappers so callers (e.g. main.py) can resolve a style/gender spec
# into a single concrete value without reaching into private helpers.
def resolve_style(style, rng=None) -> str:
    """Resolve a style name or {style: %} blend into one concrete style."""
    return _resolve_style(rng, style)


def resolve_gender(gender, rng=None) -> str:
    """Resolve a gender name or {gender: %} blend into one concrete gender."""
    return _resolve_gender(rng, gender)


def age_for_style(style, rng=None, lo=None, hi=None) -> int:
    """Pick a plausible current age for someone whose email matches ``style``.

    ``style`` may be a name or a {style: %} blend (it is resolved first).
    ``lo`` / ``hi`` optionally clamp the result to a caller-supplied range; if
    that clamp leaves no overlap with the style's natural range, the explicit
    clamp wins (so an operator-set age range is never silently ignored).
    """
    r = _rng(rng)
    style = _resolve_style(r, style)
    a, b = STYLE_AGE_RANGES.get(style, (18, 55))
    lo_eff = a if lo is None else lo
    hi_eff = b if hi is None else hi
    ia, ib = max(a, lo_eff), min(b, hi_eff)
    if ia <= ib:
        return r.randint(ia, ib)
    if lo is not None and hi is not None and lo <= hi:
        return r.randint(lo, hi)
    return r.randint(a, b)


# ------------------------------- API ---------------------------------- #

def generate_identity(style="mix", gender="any", rng=None, provider="auto",
                      age=None) -> dict:
    """Generate one coherent respondent identity.

    Returns a dict with the resolved ``style`` and ``gender``, the person's
    ``first`` / ``last`` name, a display ``full_name``, the email ``username``,
    the ``provider`` domain and the assembled ``email`` address. The name and
    email are derived from the same tokens so they agree with each other.

    ``style`` and ``gender`` may each be a single name or a {name: percent} dict.
    ``provider`` controls the domain: "auto" (era-weighted), a specific domain
    like "gmail.com", or a {provider: percent} dict. ``age`` (the persona's age,
    if known) keeps "company" addresses age-appropriate; when omitted it is
    derived from the style so standalone previews stay realistic too.
    """
    r = _rng(rng)
    style = _resolve_style(r, style)
    gender = _resolve_gender(r, gender)
    if age is None:
        age = age_for_style(style, rng=r)
    domain = _pick_provider(r, style, provider, age)
    allow_us = domain != "gmail.com"
    # Build a name + username, retrying if it happens to resemble a real
    # public figure (e.g. "Ivan Gunawan", "Raffi Ahmad").
    parts = _name_parts(r, gender, style)
    local = ""
    for _ in range(12):
        if _is_celebrity(display_name(parts)):
            parts = _name_parts(r, gender, style)
            continue
        if style in ("genz", "alpha"):
            raw = _nickname_username(r, parts, style, allow_us)
        else:
            raw = _name_style_username(r, parts, style, allow_us)
        local = _sanitize(raw, domain, r)
        if not _is_celebrity(display_name(parts), local):
            break
        parts = _name_parts(r, gender, style)
    return {
        "style": style,
        "gender": gender,
        "first": parts["first"].capitalize(),
        "last": (parts.get("last") or "").capitalize(),
        "full_name": display_name(parts),
        "username": local,
        "provider": domain,
        "email": f"{local}@{domain}",
    }


def generate_username(style="mix", gender="any", rng=None, provider="auto") -> str:
    """Generate an email local part (no domain) in the given style and gender.

    ``style`` and ``gender`` may each be a single name (see STYLES / GENDERS)
    or a dict of {name: percentage} for a weighted blend, e.g.
    ``style={"genz": 70, "professional": 30}`` or ``gender={"male": 50, "female": 50}``.
    """
    return generate_identity(style, gender, rng, provider)["username"]


def generate_email(style="mix", gender="any", rng=None, provider="auto") -> str:
    """Generate one realistic Indonesian email address.

    The provider domain varies by style/era when ``provider`` is "auto" (Gmail
    dominant for younger styles, more legacy Yahoo/Hotmail for older ones), or
    can be forced to a specific domain / {provider: percent} blend. ``style`` and
    ``gender`` accept a single name or a {name: percentage} dict.
    """
    return generate_identity(style, gender, rng, provider)["email"]


def generate_emails(count: int, style="mix", gender="any",
                    unique: bool = True, seed=None, provider="auto") -> list:
    """
    Generate a list of addresses.

    Args:
        count: how many to generate
        style: a style name (see STYLES) or a {style: percentage} dict for a blend
        gender: a gender name (see GENDERS) or a {gender: percentage} dict for a blend
        unique: avoid duplicates within the batch when possible
        seed: optional int for reproducible output
        provider: "auto" (era-weighted), a domain like "gmail.com", or a
                  {provider: percentage} dict
    """
    count = max(0, count)
    rng = random.Random(seed) if seed is not None else None
    if not unique:
        return [generate_email(style, gender, rng, provider) for _ in range(count)]

    seen, out, attempts, cap = set(), [], 0, count * 30 + 50
    while len(out) < count and attempts < cap:
        addr = generate_email(style, gender, rng, provider)
        attempts += 1
        if addr not in seen:
            seen.add(addr)
            out.append(addr)
    # If the pool got exhausted, top up allowing duplicates
    while len(out) < count:
        out.append(generate_email(style, gender, rng, provider))
    return out


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    style = sys.argv[2] if len(sys.argv) > 2 else "mix"
    gender = sys.argv[3] if len(sys.argv) > 3 else "any"
    provider = sys.argv[4] if len(sys.argv) > 4 else "auto"
    for addr in generate_emails(n, style, gender, provider=provider):
        print(addr)
