"""
Google Form Auto-Fill - Interactive TUI
A menu-driven terminal interface over form.py / main.py.

Stdlib only (no extra dependencies). Works in Windows PowerShell, cmd, and POSIX terminals.

Run:
    python tui.py
"""

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from typing import Dict, List, Optional

from googleform_autofill import email_generator, form
from googleform_autofill.presets import PRESETS as REALISM_PRESETS, get_preset
import main as engine

# Settings persisted next to this script
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tui_settings.json")


# ---------- Color / terminal helpers ---------- #

def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        # Enable ANSI/VT processing on modern Windows terminals.
        try:
            os.system("")
        except Exception:
            return False
    return True


_COLOR = _supports_color()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(t: str) -> str:   return _c("1", t)
def dim(t: str) -> str:    return _c("2", t)
def red(t: str) -> str:    return _c("31", t)
def green(t: str) -> str:  return _c("32", t)
def yellow(t: str) -> str: return _c("33", t)
def blue(t: str) -> str:   return _c("36", t)


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def banner() -> None:
    line = "=" * 56
    print(blue(line))
    print(blue("   Google Form Auto-Fill") + dim("  -  interactive TUI"))
    print(blue(line))


def pause() -> None:
    input(dim("\nPress Enter to continue..."))


def ask(prompt: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default or ""
    return val if val else (default or "")


def ask_bool(prompt: str, default: bool) -> bool:
    d = "Y/n" if default else "y/N"
    val = ask(f"{prompt} ({d})").lower()
    if not val:
        return default
    return val in ("y", "yes", "true", "1")


def ask_int(prompt: str, default: int, lo: Optional[int] = None) -> int:
    while True:
        val = ask(prompt, str(default))
        try:
            n = int(val)
            if lo is not None and n < lo:
                print(red(f"Must be >= {lo}"))
                continue
            return n
        except ValueError:
            print(red("Enter a whole number."))


def ask_opt_int(prompt: str, default: Optional[int]) -> Optional[int]:
    """Integer that can be cleared by entering 'none' or '-'. Blank keeps current."""
    cur = "" if default is None else str(default)
    val = ask(prompt + " (blank=keep, 'none'=clear)", cur)
    if val.lower() in ("none", "-", "clear"):
        return None
    try:
        return int(val)
    except ValueError:
        print(red("Not a number; keeping current."))
        return default


def ask_float(prompt: str, default: float, lo: Optional[float] = None) -> float:
    while True:
        val = ask(prompt, str(default))
        try:
            n = float(val)
            if lo is not None and n < lo:
                print(red(f"Must be >= {lo}"))
                continue
            return n
        except ValueError:
            print(red("Enter a number."))


# ---------- Field type names ---------- #

TYPE_NAMES = {
    form.FIELD_TYPE_SHORT_ANSWER: "Short answer",
    form.FIELD_TYPE_PARAGRAPH: "Paragraph",
    form.FIELD_TYPE_MULTIPLE_CHOICE: "Multiple choice",
    form.FIELD_TYPE_DROPDOWN: "Dropdown",
    form.FIELD_TYPE_CHECKBOXES: "Checkboxes",
    form.FIELD_TYPE_LINEAR_SCALE: "Linear scale",
    form.FIELD_TYPE_GRID_CHOICE: "Grid choice",
    form.FIELD_TYPE_DATE: "Date",
    form.FIELD_TYPE_TIME: "Time",
    "required": "Special (email/page)",
}


def type_name(type_id) -> str:
    return TYPE_NAMES.get(type_id, f"Type {type_id}")


# ---------- Config ---------- #

@dataclass
class Config:
    url: str = ""
    # --- email ---
    email: str = "test@example.com"
    random_email: bool = False        # generate Indonesian @gmail.com per submission
    email_style: str = "mix"          # classic|professional|millennial|genz|alpha|chinese|mix
    email_gender: str = "any"         # any | male | female
    # Optional custom percentage blends. When set (non-empty dict of name->%),
    # they override email_style / email_gender with a weighted random pick per email.
    email_style_mix: Optional[Dict[str, float]] = None   # e.g. {"genz": 70, "professional": 30}
    email_gender_mix: Optional[Dict[str, float]] = None  # e.g. {"male": 50, "female": 50}
    email_provider: str = "auto"      # auto | gmail.com | yahoo.com | outlook.com | ...
    email_provider_mix: Optional[Dict[str, float]] = None  # e.g. {"gmail.com": 70, "yahoo.com": 30}
    email_seed: Optional[int] = None  # reproducible generation
    email_unique: bool = True         # de-dupe in batch preview
    # --- fill ---
    strategy: str = "random"          # random | fixed
    fixed_text: str = "Fixed response"
    only_required: bool = False
    age_range: Optional[str] = None
    match_age_options: bool = True    # match age_range to range options on age choice fields
    coherent_identity: bool = True    # email style -> age -> education stay consistent per submission
    checkbox_min: int = 1             # min options ticked on "choose many" fields
    checkbox_max: Optional[int] = None  # max ticked; None = min(options, 3)
    custom_values: Dict[str, object] = field(default_factory=dict)
    # --- realism preset ---
    realism_preset: Optional[str] = None   # e.g. "ai-survey"
    anomaly_rate: float = 0.0              # 0..1 fraction of rare-but-legal outliers
    # --- submission ---
    count: int = 1
    delay: float = 1.0
    delay_jitter: float = 0.0         # random extra 0..jitter per submission
    timeout: int = 10                 # request timeout (s)
    progressive: bool = False
    stop_on_failure: bool = False
    save_responses: bool = False
    # --- misc ---
    verbose: bool = False


# Named presets: each applies a bundle of field overrides (URL/custom values untouched)
# Entries marked with realism_preset apply the full realism engine (CPT + calibration).
PRESETS = [
    # ── Realism presets (use the full realism engine) ─────────────────────────
    ("★ AI Survey — dry run preview",
     "Preview one realistic Indonesian response for the AI-adoption survey. No submission.",
     dict(realism_preset="ai-survey", random_email=True,
          strategy="random", count=1, delay=45.0, delay_jitter=0.0,
          only_required=False, anomaly_rate=0.03, stop_on_failure=False)),

    ("★ AI Survey — 50 submissions",
     "50 realistic responses: student/young-adult demographic, correlated answers, human timing.",
     dict(realism_preset="ai-survey", random_email=True,
          strategy="random", count=50, delay=45.0, delay_jitter=0.0,
          only_required=False, anomaly_rate=0.03, stop_on_failure=True)),

    ("★ AI Survey — 100 submissions",
     "100 realistic responses with the ai-survey preset.",
     dict(realism_preset="ai-survey", random_email=True,
          strategy="random", count=100, delay=45.0, delay_jitter=0.0,
          only_required=False, anomaly_rate=0.03, stop_on_failure=True)),

    # ── Generic presets (simple style/count bundles, no realism engine) ───────
    ("Single test (fixed email)",
     "One submission, random fill, your fixed email - for trying a form out.",
     dict(realism_preset=None, random_email=False, strategy="random", count=1,
          delay=1.0, delay_jitter=0.0, progressive=False, only_required=False,
          anomaly_rate=0.0, stop_on_failure=False)),
    ("Indo Gen Z survey",
     "10 submissions, Gen Z @gmail.com names, human-like jitter.",
     dict(realism_preset=None, random_email=True, email_style="genz",
          email_gender="any", strategy="random", count=10, delay=2.0,
          delay_jitter=1.5, anomaly_rate=0.0, stop_on_failure=False)),
    ("Gen Alpha (youngest)",
     "15 submissions, Gen Alpha aesthetic/leetspeak names.",
     dict(realism_preset=None, random_email=True, email_style="alpha",
          email_gender="any", strategy="random", count=15, delay=2.0,
          delay_jitter=2.0, anomaly_rate=0.0)),
    ("Professional adults",
     "5 submissions, clean firstname.lastname @gmail.com, slower pace.",
     dict(realism_preset=None, random_email=True, email_style="professional",
          email_gender="any", strategy="random", count=5, delay=3.0,
          delay_jitter=1.0, anomaly_rate=0.0)),
    ("Bulk realistic mixed",
     "50 submissions, mixed-generation @gmail.com, big delay + jitter.",
     dict(realism_preset=None, random_email=True, email_style="mix",
          email_gender="any", strategy="random", count=50, delay=4.0,
          delay_jitter=3.0, anomaly_rate=0.0, stop_on_failure=True)),
    ("Required only, fast",
     "5 quick submissions filling only required fields.",
     dict(realism_preset=None, only_required=True, strategy="random", count=5,
          delay=0.5, delay_jitter=0.5, random_email=True, email_style="mix",
          anomaly_rate=0.0)),
    ("Reproducible (seed 42)",
     "10 submissions with a fixed seed - same emails every run.",
     dict(realism_preset=None, random_email=True, email_style="mix",
          email_seed=42, email_unique=True, count=10, delay=1.5,
          anomaly_rate=0.0)),
    ("Campus / young adult mix",
     "Mostly Gen Z + a few millennials -> teens-to-20s, SMA/D3/S1 education.",
     dict(realism_preset=None, random_email=True, email_style="mix",
          email_style_mix={"genz": 70, "millennial": 20, "alpha": 10},
          email_gender_mix={"male": 50, "female": 50},
          coherent_identity=True, count=20, delay=2.0, delay_jitter=1.5,
          anomaly_rate=0.0)),
]


def apply_preset(cfg: Config, overrides: Dict[str, object]) -> None:
    # A preset is a full email/submission bundle; clear any custom % blends
    # unless the preset explicitly sets them, so switching presets is predictable.
    if "email_style_mix" not in overrides:
        cfg.email_style_mix = None
    if "email_gender_mix" not in overrides:
        cfg.email_gender_mix = None
    if "email_provider_mix" not in overrides:
        cfg.email_provider_mix = None
    for key, val in overrides.items():
        setattr(cfg, key, val)


def set_log_level(verbose: bool, quiet: bool = False) -> None:
    level = logging.ERROR if quiet else (logging.DEBUG if verbose else logging.WARNING)
    for name in ("main", "form", "generator", None):
        logging.getLogger(name).setLevel(level)


def save_settings(cfg: Config, path: str = SETTINGS_PATH) -> bool:
    """Write the current config to disk as JSON."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(cfg), f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        print(red(f"Failed to save settings: {e}"))
        return False


def load_settings(cfg: Config, path: str = SETTINGS_PATH) -> bool:
    """Load config from disk into cfg in place. Returns True if loaded."""
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(red(f"Failed to read settings: {e}"))
        return False
    valid = {f.name for f in fields(Config)}
    for key, val in data.items():
        if key in valid:
            setattr(cfg, key, val)
    return True


# ---------- Screens ---------- #

def show_settings(cfg: Config) -> None:
    url_disp = cfg.url if cfg.url else red("(not set)")
    print(bold("Current settings"))
    print(f"  {'URL':<16}: {url_disp}")

    if cfg.random_email:
        seed = f", seed={cfg.email_seed}" if cfg.email_seed is not None else ""
        style_part = _fmt_mix(cfg.email_style_mix) if cfg.email_style_mix else cfg.email_style
        gender_part = _fmt_mix(cfg.email_gender_mix) if cfg.email_gender_mix else cfg.email_gender
        prov = "" if cfg.email_provider == "auto" else f", {cfg.email_provider}"
        if cfg.email_provider_mix:
            prov = f", {_fmt_mix(cfg.email_provider_mix)}"
        email_disp = green(f"random email ({style_part} / {gender_part}{prov}{seed})")
    else:
        email_disp = cfg.email
    print(f"  {'Email':<16}: {email_disp}")

    strat = cfg.strategy + (f"  text='{cfg.fixed_text}'" if cfg.strategy == "fixed" else "")
    extras = []
    if cfg.only_required:
        extras.append("required-only")
    if cfg.age_range:
        extras.append(f"age {cfg.age_range}")
    if cfg.coherent_identity:
        extras.append("coherent id")
    if cfg.checkbox_min != 1 or cfg.checkbox_max is not None:
        hi = cfg.checkbox_max if cfg.checkbox_max is not None else "auto"
        extras.append(f"checkbox {cfg.checkbox_min}-{hi}")
    print(f"  {'Fill':<16}: {strat}" + (f"  [{', '.join(extras)}]" if extras else ""))

    jit = f" (+0..{cfg.delay_jitter}s jitter)" if cfg.delay_jitter else ""
    flags = []
    if cfg.progressive:
        flags.append("progressive")
    if cfg.stop_on_failure:
        flags.append("stop-on-fail")
    if cfg.save_responses:
        flags.append("save")
    print(f"  {'Submission':<16}: count={cfg.count}, delay={cfg.delay}s{jit}, "
          f"timeout={cfg.timeout}s" + (f"  [{', '.join(flags)}]" if flags else ""))

    print(f"  {'Custom values':<16}: {len(cfg.custom_values)} set"
          + (dim(f"   verbose={cfg.verbose}") if cfg.verbose else ""))
    if cfg.realism_preset:
        try:
            p = get_preset(cfg.realism_preset)
            print(f"  {'Realism preset':<16}: " + green(f"{p.name}") +
                  dim(f"  — {p.description}") +
                  (f"  anomaly={cfg.anomaly_rate:.0%}" if cfg.anomaly_rate else ""))
        except KeyError:
            print(f"  {'Realism preset':<16}: " + red(f"{cfg.realism_preset} (unknown)"))


def require_url(cfg: Config) -> bool:
    if not cfg.url:
        print(red("\nNo form URL set. Choose option 1 first."))
        pause()
        return False
    return True


def action_set_url(cfg: Config) -> None:
    print(bold("\nSet Google Form URL"))
    print(dim("Paste a viewform / edit / formResponse URL."))
    url = ask("URL", cfg.url or None)
    if url:
        cfg.url = url.strip()
        print(green("URL set."))
    pause()


def action_preview(cfg: Config) -> None:
    if not require_url(cfg):
        return
    set_log_level(cfg.verbose)
    print(dim("\nFetching form fields..."))
    try:
        entries = form.parse_form_entries(cfg.url, only_required=cfg.only_required)
    except Exception as e:
        print(red(f"Error: {e}"))
        pause()
        return
    if not entries:
        print(red("No fields parsed. Form may require login, or URL is wrong."))
        pause()
        return

    print(bold(f"\nParsed {len(entries)} field(s):\n"))
    for i, e in enumerate(entries, 1):
        req = red("*") if e.get("required") else " "
        name = e.get("name") or e.get("container_name") or "(unnamed)"
        print(f" {req}{i:>2}. {bold(name)}  {dim('[' + type_name(e.get('type')) + ']')}")
        print(f"       id: {e.get('id')}")
        opts = e.get("options")
        if isinstance(opts, list) and opts:
            shown = [o for o in opts if o != form.ANY_TEXT_FIELD]
            print(f"       options: {', '.join(shown) if shown else dim('free text')}")
    print(dim("\n(* = required)"))
    pause()


def _strategy_obj(cfg: Config):
    # Resolve realism preset if set
    calibration = None
    conditionals = None
    anomaly_rate = cfg.anomaly_rate
    if cfg.realism_preset:
        try:
            p = get_preset(cfg.realism_preset)
            calibration = p.calibration
            conditionals = p.conditionals
            # Preset's anomaly_rate is the floor; cfg.anomaly_rate can raise it
            anomaly_rate = max(anomaly_rate,
                               p.main_kwargs.get("anomaly_rate", 0.0))
        except KeyError:
            pass
    common = dict(
        email=cfg.email, custom_values=cfg.custom_values or None, age_range=cfg.age_range,
        random_email=cfg.random_email, email_style=_effective_style(cfg),
        email_gender=_effective_gender(cfg), email_seed=cfg.email_seed,
        checkbox_min=cfg.checkbox_min, checkbox_max=cfg.checkbox_max,
        match_age_options=cfg.match_age_options,
        coherent_identity=cfg.coherent_identity,
        email_provider=_effective_provider(cfg),
        calibration=calibration,
        conditionals=conditionals,
        anomaly_rate=anomaly_rate,
    )
    if cfg.strategy == "fixed":
        return engine.FixedFillStrategy(text_value=cfg.fixed_text, **common)
    return engine.RandomFillStrategy(**common)


def action_dry_run(cfg: Config) -> None:
    if not require_url(cfg):
        return
    set_log_level(cfg.verbose)
    if cfg.realism_preset:
        print(dim(f"\nRealism preset: ") + green(cfg.realism_preset))
    print(dim("\nGenerating form data (no submission)..."))
    try:
        strat = _strategy_obj(cfg)
        data = engine.generate_request_body(cfg.url, cfg.only_required, strat, cfg.custom_values or None)
    except Exception as e:
        print(red(f"Error: {e}"))
        pause()
        return
    if not data:
        print(red("Failed to generate data."))
        pause()
        return
    print(bold(f"\nGenerated payload ({len(data)} fields):\n"))
    print(json.dumps(data, indent=2, ensure_ascii=False))
    pause()


def action_submit(cfg: Config) -> None:
    if not require_url(cfg):
        return
    print(bold("\nReady to submit"))
    print(f"  {cfg.count} submission(s), strategy={cfg.strategy}, "
          f"progressive={cfg.progressive}, required_only={cfg.only_required}")
    if not ask_bool(yellow("Submit now?"), default=False):
        print(dim("Cancelled."))
        pause()
        return

    set_log_level(cfg.verbose)  # INFO-level summary comes from engine via logging
    logging.getLogger("main").setLevel(logging.INFO)
    print()
    try:
        ok = engine.main(
            url=cfg.url,
            only_required=cfg.only_required,
            email=cfg.email,
            custom_values=cfg.custom_values or None,
            count=cfg.count,
            delay=cfg.delay,
            strategy=cfg.strategy,
            save_responses=cfg.save_responses,
            dry_run=False,
            progressive=cfg.progressive,
            age_range=cfg.age_range,
            random_email=cfg.random_email,
            email_style=_effective_style(cfg),
            email_gender=_effective_gender(cfg),
            email_seed=cfg.email_seed,
            timeout=cfg.timeout,
            delay_jitter=cfg.delay_jitter,
            stop_on_failure=cfg.stop_on_failure,
            checkbox_min=cfg.checkbox_min,
            checkbox_max=cfg.checkbox_max,
            match_age_options=cfg.match_age_options,
            coherent_identity=cfg.coherent_identity,
            email_provider=_effective_provider(cfg),
            preset=cfg.realism_preset,
            anomaly_rate=cfg.anomaly_rate,
        )
    except KeyboardInterrupt:
        print(yellow("\nInterrupted."))
        pause()
        return
    except Exception as e:
        print(red(f"\nError: {e}"))
        pause()
        return
    print(green("\nAll done.") if ok else red("\nFinished with failures."))
    pause()


def _ask_email_style(default: str) -> str:
    print(dim("  styles: " + " / ".join(email_generator.STYLES)))
    s = ask("Style", default).lower()
    return s if s in email_generator.STYLES else default


def _ask_email_gender(default: str) -> str:
    s = ask("Gender: any / male / female", default).lower()
    return s if s in email_generator.GENDERS else default


def _ask_email_provider(default: str) -> str:
    print(dim("  auto = era-appropriate mix. options: "
              + " / ".join(email_generator.PROVIDER_CHOICES)))
    s = ask("Provider", default).lower()
    return s if s in email_generator.PROVIDER_CHOICES else default


def _effective_style(cfg: Config):
    """Style spec passed to the generator: a % blend dict if set, else the name."""
    return cfg.email_style_mix if cfg.email_style_mix else cfg.email_style


def _effective_gender(cfg: Config):
    """Gender spec passed to the generator: a % blend dict if set, else the name."""
    return cfg.email_gender_mix if cfg.email_gender_mix else cfg.email_gender


def _effective_provider(cfg: Config):
    """Provider spec passed to the generator: a % blend dict if set, else the name."""
    return cfg.email_provider_mix if cfg.email_provider_mix else cfg.email_provider


def _fmt_mix(mix: Optional[Dict[str, float]]) -> str:
    """Compact human-readable summary of a percentage blend dict."""
    if not mix:
        return "off"
    return ", ".join(f"{k} {_fmt_pct(v)}%" for k, v in mix.items())


def _fmt_pct(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def _edit_mix(names: List[str], current: Optional[Dict[str, float]],
              label: str) -> Optional[Dict[str, float]]:
    """Prompt for a percentage per name and return a {name: %} dict (or None).

    Entries with 0 or blank are dropped. Percentages are treated as relative
    weights, so they need not sum to exactly 100 (but a hint is shown if not)."""
    current = current or {}
    print(bold(f"\nSet {label} percentages"))
    print(dim("Enter a percentage for each (blank or 0 = exclude). "
              "Leave everything empty to turn the blend off."))
    new: Dict[str, float] = {}
    for name in names:
        cur = current.get(name)
        raw = ask(f"  {name} %", _fmt_pct(cur) if cur is not None else "")
        if not raw.strip():
            continue
        try:
            val = float(raw)
        except ValueError:
            print(red(f"  '{raw}' is not a number; skipping {name}."))
            continue
        if val > 0:
            new[name] = val
    if not new:
        print(yellow(f"\n{label} blend disabled (using single value instead)."))
        return None
    total = sum(new.values())
    if abs(total - 100) > 0.01:
        print(dim(f"Note: percentages total {_fmt_pct(total)}% "
                  "(used as relative weights)."))
    print(green(f"{label} blend set: ") + _fmt_mix(new))
    return new


def action_preview_emails(cfg: Config) -> None:
    if cfg.email_style_mix:
        style = cfg.email_style_mix
        print(dim("Using configured style blend: " + _fmt_mix(cfg.email_style_mix)))
    else:
        style = _ask_email_style(cfg.email_style)
    if cfg.email_gender_mix:
        gender = cfg.email_gender_mix
        print(dim("Using configured gender blend: " + _fmt_mix(cfg.email_gender_mix)))
    else:
        gender = _ask_email_gender(cfg.email_gender)
    n = min(ask_int("How many sample emails to generate?", 15, lo=1), 500)
    seed = cfg.email_seed
    style_disp = _fmt_mix(style) if isinstance(style, dict) else style
    gender_disp = _fmt_mix(gender) if isinstance(gender, dict) else gender
    prov = "" if cfg.email_provider == "auto" else f", {cfg.email_provider}"
    if cfg.email_provider_mix:
        prov = f", {_fmt_mix(cfg.email_provider_mix)}"
    print(bold(f"\nSample emails ({style_disp} / {gender_disp}{prov}"
               + (f", seed={seed}" if seed is not None else "") + f", {n}):\n"))
    for addr in email_generator.generate_emails(n, style, gender,
                                                unique=cfg.email_unique, seed=seed,
                                                provider=_effective_provider(cfg)):
        print("  " + green(addr))
    if not cfg.random_email:
        print(dim("\nTip: enable Settings -> Email -> 'random @gmail.com' "
                  "to use these for the email field."))
    pause()


def action_custom_values(cfg: Config) -> None:
    while True:
        clear_screen()
        banner()
        print(bold("Custom field values\n"))
        if cfg.custom_values:
            for k, v in cfg.custom_values.items():
                print(f"  {k} = {json.dumps(v, ensure_ascii=False)}")
        else:
            print(dim("  (none set)"))
        print(dim("\nKeys are the numeric field id shown in 'Preview fields'."))
        print("\n  1. Add / update a value")
        print("  2. Remove a value")
        print("  3. Load from JSON file")
        print("  4. Clear all")
        print("  0. Back")
        choice = ask("\nChoice", "0")
        if choice == "1":
            key = ask("Field id (e.g. 123456789)")
            if not key:
                continue
            raw = ask("Value (plain text, or JSON list like [\"A\",\"B\"])")
            val: object = raw
            if raw.startswith("[") or raw.startswith("{"):
                try:
                    val = json.loads(raw)
                except json.JSONDecodeError:
                    print(red("Invalid JSON, stored as plain text."))
            cfg.custom_values[key] = val
            print(green("Set."))
            pause()
        elif choice == "2":
            key = ask("Field id to remove")
            if cfg.custom_values.pop(key, None) is not None:
                print(green("Removed."))
            else:
                print(red("Not found."))
            pause()
        elif choice == "3":
            path = ask("Path to JSON file")
            if not os.path.exists(path):
                print(red("File not found."))
                pause()
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    print(red("JSON must be an object of id -> value."))
                else:
                    cfg.custom_values.update({str(k): v for k, v in loaded.items()})
                    print(green(f"Loaded {len(loaded)} value(s)."))
            except json.JSONDecodeError as e:
                print(red(f"Invalid JSON: {e}"))
            pause()
        elif choice == "4":
            cfg.custom_values.clear()
            print(green("Cleared."))
            pause()
        elif choice == "0":
            return


def _settings_email(cfg: Config) -> None:
    while True:
        clear_screen()
        banner()
        show_settings(cfg)
        print(bold("\nEmail settings"))
        print(f"  1. Toggle random email              [{cfg.random_email}]")
        print(f"  2. Email style                      [{cfg.email_style}]")
        print(f"  3. Email gender                     [{cfg.email_gender}]")
        print(f"  4. Style mix percentages            [{_fmt_mix(cfg.email_style_mix)}]")
        print(f"  5. Gender mix percentages           [{_fmt_mix(cfg.email_gender_mix)}]")
        print(f"  6. Email provider                   [{cfg.email_provider}]")
        print(f"  7. Provider mix percentages         [{_fmt_mix(cfg.email_provider_mix)}]")
        print(f"  8. Email seed (reproducible)        [{cfg.email_seed}]")
        print(f"  9. Toggle unique in batch/preview   [{cfg.email_unique}]")
        print(f" 10. Fixed email address              [{cfg.email}]")
        print("  0. Back")
        choice = ask("\nChoice", "0")
        if choice == "1":
            cfg.random_email = not cfg.random_email
            if cfg.random_email:
                print(green("On. Sample: ")
                      + dim(email_generator.generate_email(
                          _effective_style(cfg), _effective_gender(cfg),
                          provider=_effective_provider(cfg))))
                pause()
        elif choice == "2":
            cfg.email_style = _ask_email_style(cfg.email_style)
            if cfg.email_style_mix:
                print(dim("(style blend is active and overrides this; "
                          "clear it in option 4 to use a single style)"))
            print(green("Sample: ")
                  + dim(email_generator.generate_email(
                      _effective_style(cfg), _effective_gender(cfg),
                      provider=_effective_provider(cfg))))
            pause()
        elif choice == "3":
            cfg.email_gender = _ask_email_gender(cfg.email_gender)
            if cfg.email_gender_mix:
                print(dim("(gender blend is active and overrides this; "
                          "clear it in option 5 to use a single gender)"))
                pause()
        elif choice == "4":
            cfg.email_style_mix = _edit_mix(
                email_generator.CONCRETE_STYLES, cfg.email_style_mix, "Style")
            if cfg.email_style_mix:
                print(green("Sample: ")
                      + dim(email_generator.generate_email(
                          _effective_style(cfg), _effective_gender(cfg),
                          provider=_effective_provider(cfg))))
            pause()
        elif choice == "5":
            cfg.email_gender_mix = _edit_mix(
                ["male", "female"], cfg.email_gender_mix, "Gender")
            if cfg.email_gender_mix:
                print(green("Sample: ")
                      + dim(email_generator.generate_email(
                          _effective_style(cfg), _effective_gender(cfg),
                          provider=_effective_provider(cfg))))
            pause()
        elif choice == "6":
            cfg.email_provider = _ask_email_provider(cfg.email_provider)
            if cfg.email_provider_mix:
                print(dim("(provider blend is active and overrides this; "
                          "clear it in option 7 to use a single provider)"))
            print(green("Sample: ")
                  + dim(email_generator.generate_email(
                      _effective_style(cfg), _effective_gender(cfg),
                      provider=_effective_provider(cfg))))
            pause()
        elif choice == "7":
            providers = [p for p in email_generator.PROVIDER_CHOICES if p != "auto"]
            cfg.email_provider_mix = _edit_mix(
                providers, cfg.email_provider_mix, "Provider")
            if cfg.email_provider_mix:
                print(green("Sample: ")
                      + dim(email_generator.generate_email(
                          _effective_style(cfg), _effective_gender(cfg),
                          provider=_effective_provider(cfg))))
            pause()
        elif choice == "8":
            cfg.email_seed = ask_opt_int("Seed", cfg.email_seed)
        elif choice == "9":
            cfg.email_unique = not cfg.email_unique
        elif choice == "10":
            cfg.email = ask("Email", cfg.email)
        elif choice == "0":
            return


def _settings_fill(cfg: Config) -> None:
    while True:
        clear_screen()
        banner()
        show_settings(cfg)
        cb_max = cfg.checkbox_max if cfg.checkbox_max is not None else "auto(<=3)"
        print(bold("\nFill settings"))
        print(f"  1. Strategy (random/fixed)          [{cfg.strategy}]")
        print(f"  2. Fixed text value                 [{cfg.fixed_text}]")
        print(f"  3. Toggle required-only             [{cfg.only_required}]")
        print(f"  4. Age range (e.g. 18-25)           [{cfg.age_range or 'off'}]")
        print(f"  5. Match age range to choices       [{cfg.match_age_options}]")
        print(f"  6. Checkbox min selections          [{cfg.checkbox_min}]")
        print(f"  7. Checkbox max selections          [{cb_max}]")
        print(f"  8. Coherent identity (style+age+edu)[{cfg.coherent_identity}]")
        print("  0. Back")
        choice = ask("\nChoice", "0")
        if choice == "1":
            s = ask("Strategy (random/fixed)", cfg.strategy).lower()
            cfg.strategy = "fixed" if s == "fixed" else "random"
        elif choice == "2":
            cfg.fixed_text = ask("Fixed text", cfg.fixed_text)
        elif choice == "3":
            cfg.only_required = not cfg.only_required
        elif choice == "4":
            print(dim("Used for age text fields AND age multiple-choice/dropdown "
                      "(matches option like '18-25')."))
            ar = ask("Age range min-max (blank to disable)", cfg.age_range or "")
            cfg.age_range = ar if ar else None
        elif choice == "5":
            cfg.match_age_options = not cfg.match_age_options
        elif choice == "6":
            cfg.checkbox_min = ask_int("Checkbox min selections", cfg.checkbox_min, lo=1)
        elif choice == "7":
            cfg.checkbox_max = ask_opt_int("Checkbox max selections", cfg.checkbox_max)
        elif choice == "8":
            cfg.coherent_identity = not cfg.coherent_identity
            if cfg.coherent_identity:
                print(dim("On: each submission is one person - the email style sets a\n"
                          "plausible age, and the age sets a plausible education level\n"
                          "(SMP / SMA / D3 / D4-S1 / S2+). No 15-year-old with an S2."))
            else:
                print(dim("Off: email, age and education are filled independently."))
            pause()
        elif choice == "0":
            return


def _settings_submission(cfg: Config) -> None:
    while True:
        clear_screen()
        banner()
        show_settings(cfg)
        print(bold("\nSubmission settings"))
        print(f"  1. Count                            [{cfg.count}]")
        print(f"  2. Delay (s)                        [{cfg.delay}]")
        print(f"  3. Delay jitter (s)                 [{cfg.delay_jitter}]")
        print(f"  4. Request timeout (s)              [{cfg.timeout}]")
        print(f"  5. Toggle progressive (multi-page)  [{cfg.progressive}]")
        print(f"  6. Toggle stop-on-failure           [{cfg.stop_on_failure}]")
        print(f"  7. Toggle save responses            [{cfg.save_responses}]")
        print(f"  8. Toggle verbose logs              [{cfg.verbose}]")
        print("  0. Back")
        choice = ask("\nChoice", "0")
        if choice == "1":
            cfg.count = ask_int("Count", cfg.count, lo=1)
        elif choice == "2":
            cfg.delay = ask_float("Delay (s)", cfg.delay, lo=0.0)
        elif choice == "3":
            cfg.delay_jitter = ask_float("Delay jitter (s)", cfg.delay_jitter, lo=0.0)
        elif choice == "4":
            cfg.timeout = ask_int("Request timeout (s)", cfg.timeout, lo=1)
        elif choice == "5":
            cfg.progressive = not cfg.progressive
        elif choice == "6":
            cfg.stop_on_failure = not cfg.stop_on_failure
        elif choice == "7":
            cfg.save_responses = not cfg.save_responses
        elif choice == "8":
            cfg.verbose = not cfg.verbose
        elif choice == "0":
            return


def action_settings(cfg: Config) -> None:
    while True:
        clear_screen()
        banner()
        show_settings(cfg)
        print(bold("\nSettings groups"))
        print("  1. Email settings")
        print("  2. Fill settings")
        print("  3. Submission settings")
        print("  0. Back")
        choice = ask("\nChoice", "0")
        if choice == "1":
            _settings_email(cfg)
        elif choice == "2":
            _settings_fill(cfg)
        elif choice == "3":
            _settings_submission(cfg)
        elif choice == "0":
            return


def action_presets(cfg: Config) -> None:
    clear_screen()
    banner()
    print(bold("Presets") + dim("  (applies a bundle of settings; URL & custom values kept)\n"))
    print(dim("  ★ = uses full realism engine (CPT + calibration + coherent demographics)"))
    print()
    for i, (name, desc, _) in enumerate(PRESETS, 1):
        star = yellow("★") if "★" in name else " "
        display = name.replace("★ ", "")
        print(f"  {star}{i:>2}. {bold(display)}")
        print(dim(f"       {desc}"))
    print()
    if cfg.realism_preset:
        print(dim(f"  Active realism preset: ") + green(cfg.realism_preset)
              + "  (r to clear)")
    print("   0. Back")
    choice = ask("\nApply preset # (or 'r' to clear realism preset)", "0")
    if choice.lower() == "r":
        cfg.realism_preset = None
        cfg.anomaly_rate = 0.0
        print(green("Realism preset cleared."))
        pause()
        return
    if choice == "0" or not choice.isdigit():
        return
    idx = int(choice) - 1
    if 0 <= idx < len(PRESETS):
        name, _, overrides = PRESETS[idx]
        apply_preset(cfg, overrides)
        display = name.replace("★ ", "")
        print(green(f"\nApplied preset: {display}"))
        if cfg.realism_preset:
            try:
                p = get_preset(cfg.realism_preset)
                print(dim(f"Realism engine: {p.description}"))
                # Preset may include its own email style mix — apply it to cfg
                pk = p.main_kwargs
                if cfg.email_style_mix is None and "email_style" in pk:
                    cfg.email_style_mix = pk["email_style"] if isinstance(pk["email_style"], dict) else None
                    if cfg.email_style_mix is None:
                        cfg.email_style = pk["email_style"]
                if "email_provider" in pk and isinstance(pk["email_provider"], dict):
                    cfg.email_provider_mix = pk["email_provider"]
            except KeyError:
                print(red(f"Warning: realism preset '{cfg.realism_preset}' not found."))
        elif cfg.random_email:
            print(dim("Sample email: ")
                  + email_generator.generate_email(_effective_style(cfg),
                                                   _effective_gender(cfg),
                                                   provider=_effective_provider(cfg)))
    else:
        print(red("Invalid preset number."))
    pause()


def action_save_settings(cfg: Config) -> None:
    if save_settings(cfg):
        print(green(f"\nSettings saved to: {SETTINGS_PATH}"))
    pause()


def action_load_settings(cfg: Config) -> None:
    if load_settings(cfg):
        print(green("\nSettings loaded."))
    else:
        print(dim("\nNo saved settings found."))
    pause()


def main_loop() -> None:
    cfg = Config()
    if load_settings(cfg):
        print(green(f"Loaded saved settings from {SETTINGS_PATH}"))
        pause()
    set_log_level(cfg.verbose)
    while True:
        clear_screen()
        banner()
        show_settings(cfg)
        print(bold("\nMenu"))
        print("  1. Set form URL")
        print("  2. Preview fields")
        print("  3. Dry run (show payload, no submit)")
        print("  4. " + green("Submit"))
        print("  5. Presets")
        print("  6. Settings")
        print("  7. Custom field values")
        print("  8. Preview sample emails")
        print("  9. Save settings")
        print(" 10. Load settings")
        print("  0. Quit")
        choice = ask("\nChoice", "0")
        if choice == "1":
            action_set_url(cfg)
        elif choice == "2":
            action_preview(cfg)
        elif choice == "3":
            action_dry_run(cfg)
        elif choice == "4":
            action_submit(cfg)
        elif choice == "5":
            action_presets(cfg)
        elif choice == "6":
            action_settings(cfg)
        elif choice == "7":
            action_custom_values(cfg)
        elif choice == "8":
            action_preview_emails(cfg)
        elif choice == "9":
            action_save_settings(cfg)
        elif choice == "10":
            action_load_settings(cfg)
        elif choice == "0":
            print(dim("Bye."))
            return
        else:
            print(red("Unknown choice."))
            pause()


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print(dim("\nBye."))
        sys.exit(130)
