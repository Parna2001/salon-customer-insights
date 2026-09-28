"""Generate dashboard/data.sample.json from synthetic (fake) customers.

Usage:
    python scripts/make_sample_data.py

All names are invented and every phone number uses the 555 prefix, so nothing
here can match a real customer. This is the only customer-shaped data that is
committed to the repo; the dashboard falls back to it when data.json is absent.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_data import MONTHS, ROOT, build_stats, find_dup_mobiles  # noqa: E402

FIRST = ["Ada", "Bea", "Cora", "Dina", "Esme", "Faye", "Gia", "Hana", "Iris", "Juno",
         "Kira", "Lena", "Mira", "Nora", "Opal", "Pia", "Rhea", "Sage", "Tess", "Vera"]
LAST = ["Sample", "Placeholder", "Demo", "Fixture", "Mockwell", "Testa"]


def synthetic_customers(n: int = 40, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    start = dt.date(2025, 1, 1)
    customers = []
    for i in range(1, n + 1):
        has_last = rng.random() > 0.25
        first, last = rng.choice(FIRST), rng.choice(LAST) if has_last else None
        phone = None if rng.random() < 0.05 else f"555{rng.randrange(10**7):07d}"
        b = rng.random() > 0.25
        a = rng.random() > 0.6
        entry = start + dt.timedelta(days=rng.randrange(600)) if rng.random() > 0.4 else None
        customers.append({
            "id": i,
            "entry_date": entry.isoformat() if entry else None,
            "first_name": first, "middle_name": None, "last_name": last,
            "full_name": " ".join(p for p in (first, last) if p),
            "mobile_1": phone, "mobile_2": None,
            "birth_day": rng.randint(1, 28) if b else None,
            "birth_month": rng.choice(MONTHS) if b else None,
            "anniversary_day": rng.randint(1, 28) if a else None,
            "anniversary_month": rng.choice(MONTHS) if a else None,
            "notes": None,
            "missing_phone": phone is None,
            "missing_birthday": not b, "missing_anniversary": not a,
            "missing_last_name": not has_last,
            "invalid_phone": False, "entry_date_swapped": False,
        })
    # A few deliberate duplicate-mobile groups (same person, different spelling).
    for src_id, dst_id in ((3, 17), (8, 29), (12, 33)):
        src, dst = customers[src_id - 1], customers[dst_id - 1]
        src["mobile_1"] = dst["mobile_1"] = src["mobile_1"] or f"555{rng.randrange(10**7):07d}"
        src["missing_phone"] = dst["missing_phone"] = False
        # Same person, re-entered with a doubled letter in the first name.
        dst["first_name"] = src["first_name"] + src["first_name"][-1]
        dst["last_name"], dst["missing_last_name"] = src["last_name"], src["missing_last_name"]
        dst["full_name"] = " ".join(p for p in (dst["first_name"], dst["last_name"]) if p)
    return customers


def main() -> None:
    customers = synthetic_customers()
    dups = find_dup_mobiles(customers)
    stats = build_stats(customers, dups)
    stats["generated_at"] = "synthetic sample"
    out = ROOT / "dashboard/data.sample.json"
    out.write_text(json.dumps({"sample": True, "stats": stats, "dup_mobiles": dups}, indent=2), encoding="utf-8")
    print(f"{len(customers)} synthetic customers, {len(dups)} duplicate groups -> {out}")


if __name__ == "__main__":
    main()
