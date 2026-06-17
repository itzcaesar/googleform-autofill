"""Generate an offline sample dataset with the ai-survey preset, for auditing.

Lets you validate the realism engine for the AI-adoption survey *without*
submitting to the live form. Pairs with ``audit.py``:

    python tools/sample_ai_survey.py 415 data/sample.csv
    python tools/audit.py data/sample.csv

The form schema below mirrors the real form's questions and options.
"""
import csv, datetime, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import RandomFillStrategy
from googleform_autofill import form, realism
from googleform_autofill.presets import get_preset

P = get_preset("ai-survey")

MC, CB, LS = form.FIELD_TYPE_MULTIPLE_CHOICE, form.FIELD_TYPE_CHECKBOXES, form.FIELD_TYPE_LINEAR_SCALE
SCALE = ["1", "2", "3", "4", "5"]

# (header, type, options) in form order — tech_skill before usage_freq so the CPT fires.
FIELDS = [
    ("Berapa usia Anda saat ini?", MC, ["<18", "18–25", "26–35", "36–45", ">45"]),
    ("Jenis Kelamin:", MC, ["Laki-Laki", "Perempuan"]),
    ("Apa status pekerjaan Anda saat ini?", MC,
     ["Pelajar (SD/SMP/SMA)", "Mahasiswa", "Pegawai Negeri / ASN", "Pegawai swasta",
      "Wirausaha / Pengusaha", "Ibu Rumah Tangga", "Lainnya"]),
    ("Apa tingkat pendidikan terakhir atau yang sedang Anda tempuh?", MC,
     ["SMP / Sederajat", "SMA / Sederajat", "D3", "D4 / S1", "S2 +"]),
    ("Di mana domisili/lingkungan tempat tinggal Anda?", MC,
     ["Perkotaan", "Pinggiran Kota", "Pedesaan"]),
    ("Berapa rata-rata durasi penggunaan internet Anda per hari?", MC,
     ["<2 jam", "2–5 jam", ">5 jam"]),
    ("Perangkat apa yang paling sering Anda gunakan untuk mengakses internet?", MC,
     ["Handphone (HP)", "Laptop/PC", "Keduanya"]),
    ("Bagaimana Anda menilai tingkat kemampuan teknologi Anda?", MC,
     ["Pemula", "Menengah", "Mahir"]),
    ("Seberapa sering Anda mengikuti atau membaca berita tren teknologi terbaru?", MC,
     ["Tidak Pernah", "Jarang", "Kadang-Kadang", "Sering"]),
    ("Apa tujuan utama Anda menggunakan AI?", CB,
     ["Pekerjaan", "Belajar / Pendidikan", "Sekadar Ingin Tahu / Eksplorasi", "Hiburan", "Lainnya"]),
    ("Menurut Anda, seberapa bermanfaat teknologi AI bagi kehidupan Anda?", LS, SCALE),
    ("Tools AI apa saja yang pernah Anda ketahui atau gunakan? (Bisa pilih lebih dari satu)", CB,
     ["ChatGPT", "Gemini", "Copilot", "Siri", "Google Assistant", "Canva AI", "Lainnya"]),
    ("Seberapa besar tingkat kepercayaan Anda terhadap akurasi informasi/hasil dari AI?", LS, SCALE),
    ("Pada skala 1-5, seberapa mudah Anda menemukan dan mengakses tools AI yang Anda butuhkan?", LS, SCALE),
    ("Saya khawatir terhadap keamanan privasi data saat menggunakan AI", LS, SCALE),
    ("Saya khawatir AI akan menggantikan pekerjaan manusia di masa depan", LS, SCALE),
    ("Seberapa sering Anda menggunakan tools AI?", MC,
     ["Tidak Pernah", "Jarang", "Beberapa kali dalam seminggu", "Setiap Hari"]),
]


def gen(n, out, seed=2024):
    strat = RandomFillStrategy(random_email=True,
                               email_style=P.main_kwargs["email_style"],
                               email_gender=P.main_kwargs["email_gender"],
                               email_provider=P.main_kwargs["email_provider"],
                               email_seed=seed,
                               checkbox_min=1, checkbox_max=5,
                               calibration=P.calibration,
                               conditionals=P.conditionals,
                               anomaly_rate=P.main_kwargs["anomaly_rate"])
    headers = ["Timestamp", "Email Address"] + [f[0] for f in FIELDS]
    t = datetime.datetime(2026, 6, 14, 9, 0, 0)
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        for _ in range(n):
            p = strat.start_submission()
            t += datetime.timedelta(seconds=realism.human_delay(45.0))
            row = [t.strftime("%d/%m/%Y %H:%M:%S"), p.email]
            for header, typ, opts in FIELDS:
                v = strat.fill(typ, "id", opts, required=True, entry_name=header)
                row.append(", ".join(v) if isinstance(v, list) else v)
            w.writerow(row)
    print(f"Wrote {n} rows to {out}")


if __name__ == "__main__":
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _default_out = os.path.join(_root, "data", "sample.csv")
    gen(int(sys.argv[1]) if len(sys.argv) > 1 else 415,
        sys.argv[2] if len(sys.argv) > 2 else _default_out)
