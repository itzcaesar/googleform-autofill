"""Statistical audit for a Google Form responses CSV (Gemini point 7).

Reads a responses export and reports, using only the standard library:

* per-column value distributions (to eyeball uniform-vs-peaked),
* the strongest pairwise relationships (Pearson for ordinal pairs, Cramer's V
  for categorical pairs),
* a logical-consistency check on age / education / occupation.

Usage:
    python audit.py "Survei ... Form Responses 1.csv"
    python audit.py responses.csv --top 15

This is the "compare the synthetic data's relationships" step: strong, sensible
correlations + zero impossible rows == the data reads as realistic. There is no
real ground-truth dataset to compare against here, so the report is absolute
rather than a synthetic-vs-real diff.
"""

import argparse
import csv
import math
from collections import Counter, defaultdict
from typing import Dict, List, Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from googleform_autofill import realism
try:
    from main import parse_age_option, is_education_field
except Exception:
    parse_age_option = None
    is_education_field = None


def _is_age_header(h: str) -> bool:
    s = h.lower()
    return any(k in s for k in ("usia", "umur", "age", "tahun"))


def _is_edu_header(h: str) -> bool:
    if is_education_field is not None:
        return is_education_field(h)
    return "pendidikan" in h.lower()


def _bucket_to_age(value: str) -> Optional[int]:
    """Most-permissive age for an age-bucket label.

    Form age is bucketed, so a combination is only "impossible" if it's
    impossible for the *whole* bucket. Using the upper bound avoids false alarms
    (e.g. a civil servant in "18-25" could be 21+), while "<18" still maps to 17
    and correctly flags adult-only jobs.
    """
    if parse_age_option is None:
        return None
    rng = parse_age_option(value)
    if not rng:
        return None
    lo, hi = rng
    return hi


# --------------------------------------------------------------------------- #
# Statistics (stdlib only)
# --------------------------------------------------------------------------- #

def pearson(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (sx * sy) if sx and sy else 0.0


def cramers_v(xs: List[str], ys: List[str]) -> float:
    """Cramer's V association (0..1) between two categorical columns."""
    cats_x = sorted(set(xs))
    cats_y = sorted(set(ys))
    if len(cats_x) < 2 or len(cats_y) < 2:
        return 0.0
    n = len(xs)
    table: Dict = defaultdict(lambda: defaultdict(int))
    for x, y in zip(xs, ys):
        table[x][y] += 1
    row_tot = {x: sum(table[x].values()) for x in cats_x}
    col_tot = {y: sum(table[x][y] for x in cats_x) for y in cats_y}
    chi2 = 0.0
    for x in cats_x:
        for y in cats_y:
            expected = row_tot[x] * col_tot[y] / n
            if expected > 0:
                chi2 += (table[x][y] - expected) ** 2 / expected
    k = min(len(cats_x), len(cats_y)) - 1
    return math.sqrt(chi2 / (n * k)) if k > 0 else 0.0


# --------------------------------------------------------------------------- #
# Loading + column typing
# --------------------------------------------------------------------------- #

SKIP = {"timestamp", "email address", "skor", "score", "nama", "name"}


def load(path: str):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("No data rows found.")
    headers = [h for h in rows[0].keys() if h and h.strip()]
    columns = {h: [r.get(h, "") for r in rows] for h in headers}
    return headers, columns, len(rows)


def ordinal_ranks(values: List[str]) -> Optional[List[float]]:
    """Map a column's values to ordinal ranks if they form a known scale."""
    uniques = [v for v in dict.fromkeys(values) if v != ""]
    ordered = realism.detect_ordered_options(uniques)
    if not ordered:
        return None
    rank = {opt: i for i, opt in enumerate(ordered)}
    return [rank.get(v) for v in values]


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

def short(h: str, width: int = 38) -> str:
    h = h.strip()
    return h if len(h) <= width else h[:width - 1] + "…"


def run(path: str, top: int = 12):
    headers, columns, n = load(path)
    print(f"Loaded {n} responses, {len(headers)} columns from:\n  {path}\n")

    analytic = [h for h in headers if h.strip().lower() not in SKIP]

    # --- distributions ---
    print("=" * 70)
    print("VALUE DISTRIBUTIONS (look for peaks/skew, not flat splits)")
    print("=" * 70)
    for h in analytic:
        vals = [v for v in columns[h] if v != ""]
        if not vals:
            continue
        # treat multi-select (comma-joined) columns by splitting
        is_multi = any("," in v for v in vals) and "pilih" in h.lower()
        if is_multi:
            flat = [opt.strip() for v in vals for opt in v.split(",")]
            c = Counter(flat)
            head = f"{short(h)}  [multi-select, {len(vals)} resp]"
        else:
            c = Counter(vals)
            head = short(h)
        total = sum(c.values())
        top_items = c.most_common(6)
        parts = ", ".join(f"{short(k,18)}={v*100//total}%" for k, v in top_items)
        print(f"  {head}\n      {parts}")

    # --- relationships ---
    ord_cols = {}
    cat_cols = {}
    for h in analytic:
        vals = columns[h]
        # Multi-select (comma-joined) columns aren't a single categorical; their
        # huge cardinality inflates Cramer's V, so leave them out of pairing.
        if any("," in v for v in vals if v) and ("pilih" in h.lower() or "lebih dari satu" in h.lower()):
            continue
        ranks = ordinal_ranks(vals)
        if ranks is not None and sum(1 for x in ranks if x is not None) > n * 0.5:
            ord_cols[h] = ranks
        else:
            cat_cols[h] = vals

    print("\n" + "=" * 70)
    print("STRONGEST RELATIONSHIPS")
    print("=" * 70)

    pairs = []
    keys = list(ord_cols)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            xs, ys = [], []
            for x, y in zip(ord_cols[a], ord_cols[b]):
                if x is not None and y is not None:
                    xs.append(x); ys.append(y)
            if len(xs) > 1:
                pairs.append((abs(pearson(xs, ys)), pearson(xs, ys), "r ", a, b))
    ckeys = list(cat_cols)
    for i in range(len(ckeys)):
        for j in range(i + 1, len(ckeys)):
            a, b = ckeys[i], ckeys[j]
            v = cramers_v(cat_cols[a], cat_cols[b])
            pairs.append((v, v, "V ", a, b))
    pairs.sort(reverse=True)
    for _, val, kind, a, b in pairs[:top]:
        print(f"  {kind} {val:+.2f}  {short(a,30)}  ×  {short(b,30)}")

    # --- logical consistency ---
    print("\n" + "=" * 70)
    print("LOGICAL CONSISTENCY (age / education / occupation)")
    print("=" * 70)
    age_h = next((h for h in headers if _is_age_header(h)), None)
    edu_h = next((h for h in headers if _is_edu_header(h)), None)
    occ_h = next((h for h in headers if realism.is_occupation_question(h)), None)
    if not (age_h and occ_h):
        print("  (could not locate age/occupation columns; skipped)")
        return
    violations = 0
    examples = []
    for idx in range(n):
        age = _bucket_to_age(columns[age_h][idx])
        edu = columns[edu_h][idx] if edu_h else None
        occ = columns[occ_h][idx]
        probs = realism.validate_record(age, edu, occ)
        if probs:
            violations += 1
            if len(examples) < 5:
                examples.append(f"row {idx + 2}: {probs[0]}")
    rate = violations * 100 / n
    print(f"  Impossible rows: {violations}/{n} ({rate:.1f}%)")
    for e in examples:
        print(f"    - {e}")
    if violations == 0:
        print("  OK: No impossible age/education/occupation combinations.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Audit a Google Form responses CSV.")
    ap.add_argument("csv", help="Path to the responses CSV")
    ap.add_argument("--top", type=int, default=12, help="How many top relationships to show")
    args = ap.parse_args()
    run(args.csv, args.top)
