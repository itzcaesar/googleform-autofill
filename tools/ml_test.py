"""Random Forest accuracy test on the generated sample.
Tests at multiple dataset sizes to show how signal grows with more data.
"""
import csv
import random
from collections import Counter

TARGET = 'Seberapa sering Anda menggunakan tools AI?'
TARGET_ORDER = ['Tidak Pernah', 'Jarang', 'Beberapa kali dalam seminggu', 'Setiap Hari']

ORDINAL = {
    'Bagaimana Anda menilai tingkat kemampuan teknologi Anda?':
        ['Pemula', 'Menengah', 'Mahir'],
    'Seberapa sering Anda mengikuti atau membaca berita tren teknologi terbaru?':
        ['Tidak Pernah', 'Jarang', 'Kadang-Kadang', 'Sering'],
    'Apa tingkat pendidikan terakhir atau yang sedang Anda tempuh?':
        ['SMP / Sederajat', 'SMA / Sederajat', 'D3', 'D4 / S1', 'S2 +'],
    'Berapa usia Anda saat ini?':
        ['<18', '18\u201325', '26\u201335', '36\u201345', '>45'],
}
NUMERIC = [
    'Menurut Anda, seberapa bermanfaat teknologi AI bagi kehidupan Anda?',
    'Seberapa besar tingkat kepercayaan Anda terhadap akurasi informasi/hasil dari AI?',
    'Pada skala 1-5, seberapa mudah Anda menemukan dan mengakses tools AI yang Anda butuhkan?',
    'Saya khawatir terhadap keamanan privasi data saat menggunakan AI',
    'Saya khawatir AI akan menggantikan pekerjaan manusia di masa depan',
]
TOOLS_COL = 'Tools AI apa saja yang pernah Anda ketahui atau gunakan? (Bisa pilih lebih dari satu)'
KNOWN_TOOLS = ['ChatGPT', 'Gemini', 'Copilot', 'Siri', 'Google Assistant', 'Canva AI', 'Lainnya']


def featurize(rows):
    X, y = [], []
    for r in rows:
        lbl = TARGET_ORDER.index(r[TARGET]) if r[TARGET] in TARGET_ORDER else None
        if lbl is None:
            continue
        feats = []

        # Ordinal features
        for col, order in ORDINAL.items():
            v = order.index(r[col]) if r.get(col) in order else -1
            feats.append(v)

        # Numeric (Likert 1-5) features
        for col in NUMERIC:
            try:
                feats.append(int(r.get(col, 0)))
            except (ValueError, TypeError):
                feats.append(0)

        # Number of AI tools known (strong engagement proxy)
        tools_str = r.get(TOOLS_COL, '')
        n_tools = sum(1 for t in KNOWN_TOOLS if t in tools_str)
        feats.append(n_tools)

        # Binary: knows ChatGPT specifically (most discriminating single tool)
        feats.append(1 if 'ChatGPT' in tools_str else 0)

        X.append(feats)
        y.append(lbl)
    return X, y


def load_csv(path):
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def run_test(rows, label):
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score, StratifiedKFold

    X, y = featurize(rows)
    n = len(X)
    dist = Counter(y)
    dist_str = '  '.join(f"{TARGET_ORDER[k]}={v*100//n}%" for k, v in sorted(dist.items()))

    clf = RandomForestClassifier(n_estimators=300, max_depth=None,
                                 min_samples_leaf=2, random_state=42)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(clf, np.array(X), np.array(y), cv=cv, scoring='accuracy')

    print(f"\n{label} (n={n})")
    print(f"  Classes:  {dist_str}")
    print(f"  RF 5-fold CV: {scores.mean()*100:.1f}% ± {scores.std()*100:.1f}%")
    print(f"  Per fold: {[f'{s*100:.1f}%' for s in scores]}")
    print(f"  vs random baseline: +{(scores.mean()-0.25)*100:.1f} pp")
    return scores.mean()


if __name__ == '__main__':
    import sys
    import os

    # Try loading existing sample
    sample_path = r'data\sample.csv'
    if not os.path.exists(sample_path):
        print(f"Sample not found at {sample_path}. Run: python tools/sample_ai_survey.py 2000")
        sys.exit(1)

    rows_all = load_csv(sample_path)
    n_all = len(rows_all)

    print("=" * 60)
    print("ML SIGNAL TEST — Random Forest on AI Survey Data")
    print("=" * 60)
    print(f"Features: {len(ORDINAL)} ordinal + {len(NUMERIC)} Likert + 2 tool features")
    print(f"Target:   {TARGET} (4 classes)")

    # Test at different sizes to show the scaling behaviour
    sizes = [s for s in [415, 1000, 2000] if s <= n_all]
    if n_all not in sizes:
        sizes.append(n_all)

    accs = []
    rng = random.Random(42)
    for size in sizes:
        sample = rng.sample(rows_all, size) if size < n_all else rows_all
        acc = run_test(sample, f"Sample size {size}")
        accs.append((size, acc))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Random baseline (4 classes):   25.0%")
    print(f"  Gemini flat data (old):        ~21.7%  (below random — no signal)")
    for size, acc in accs:
        print(f"  This preset, n={size:<5}:        {acc*100:.1f}%")
    print()
    if accs:
        best = max(accs, key=lambda x: x[1])
        if best[1] >= 0.45:
            print("  Result: STRONG signal — data is learnable.")
        elif best[1] >= 0.35:
            print("  Result: MODERATE signal — model beats random clearly.")
            print("  Tip: generate 2000+ rows for better accuracy.")
        else:
            print("  Result: WEAK signal — generate more rows (2000+).")
