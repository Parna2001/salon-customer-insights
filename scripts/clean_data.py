"""Clean the salon customer workbook into JSON/CSV + aggregate stats.

Usage:
    python scripts/clean_data.py [--input data/local/customers_source.xlsx]
                                 [--out data/local] [--dashboard dashboard/data.json]

Everything written here is real customer PII and lives under data/local/
(gitignored). dashboard/data.json holds only aggregates plus duplicate-mobile
groups and is also gitignored.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
MONTH_LOOKUP = {m.lower(): m for m in MONTHS} | {m[:3].lower(): m for m in MONTHS}
EXPECTED_HEADERS = ["Index", "Date of Entry", "First_Name", "Middle_Name", "Last_Name",
                    "Mobile_1", "Mobile_2", "Birth_Day", "Birth_Month",
                    "Anniversary_Day", "Anniversary_Month", "Notes"]


def clean_str(v) -> str | None:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def clean_phone(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    digits = re.sub(r"\D", "", str(v))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits or None


def clean_month(v) -> str | None:
    s = clean_str(v)
    if s is None:
        return None
    if s.isdigit() and 1 <= int(s) <= 12:
        return MONTHS[int(s) - 1]
    return MONTH_LOOKUP.get(s.lower())


def clean_day(v) -> int | None:
    try:
        d = int(v)
    except (TypeError, ValueError):
        return None
    return d if 1 <= d <= 31 else None


def parse_entry_date(v) -> tuple[str | None, bool]:
    """Return (iso_date, was_swapped).

    The sheet was exported as M/D/Y text and reopened in a D/M/Y-locale Excel:
    strings with day > 12 stayed text (still M/D/Y), while ambiguous strings
    (day <= 12) were silently converted to real dates with day and month
    swapped. So real Excel dates with day <= 12 get their day/month swapped
    back; this ordering was verified against row order in the source sheet.
    """
    if v is None or v == "":
        return None, False
    if isinstance(v, (dt.datetime, dt.date)):
        d = v.date() if isinstance(v, dt.datetime) else v
        if d.day <= 12:
            return dt.date(d.year, d.day, d.month).isoformat(), True
        return d.isoformat(), False
    if isinstance(v, (int, float)):  # raw Excel serial
        d = dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
        return d.isoformat(), False
    s = str(v).strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat(), False
        except ValueError:
            continue
    return None, False


def load_rows(path: Path) -> list[dict]:
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = ws.iter_rows(values_only=True)
    headers = [clean_str(h) for h in next(rows)]
    missing = [h for h in EXPECTED_HEADERS if h not in headers]
    if missing:
        raise SystemExit(f"Missing expected columns: {missing}")
    out = []
    for raw in rows:
        rec = dict(zip(headers, raw))
        if all(v in (None, "") for v in rec.values()):
            continue
        out.append(rec)
    return out


def clean_record(i: int, rec: dict) -> dict:
    first = clean_str(rec["First_Name"])
    middle = clean_str(rec["Middle_Name"])
    last = clean_str(rec["Last_Name"])
    entry_date, swapped = parse_entry_date(rec["Date of Entry"])
    m1, m2 = clean_phone(rec["Mobile_1"]), clean_phone(rec["Mobile_2"])
    b_day, b_month = clean_day(rec["Birth_Day"]), clean_month(rec["Birth_Month"])
    a_day, a_month = clean_day(rec["Anniversary_Day"]), clean_month(rec["Anniversary_Month"])
    return {
        "id": i,
        "entry_date": entry_date,
        "first_name": first,
        "middle_name": middle,
        "last_name": last,
        "full_name": " ".join(p for p in (first, middle, last) if p),
        "mobile_1": m1,
        "mobile_2": m2,
        "birth_day": b_day,
        "birth_month": b_month,
        "anniversary_day": a_day,
        "anniversary_month": a_month,
        "notes": clean_str(rec["Notes"]),
        "missing_phone": not (m1 or m2),
        "missing_birthday": not (b_day and b_month),
        "missing_anniversary": not (a_day and a_month),
        "missing_last_name": last is None,
        "invalid_phone": bool(m1 and len(m1) != 10),
        "entry_date_swapped": swapped,
    }


def find_dup_mobiles(customers: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for c in customers:
        if c["mobile_1"]:
            groups[c["mobile_1"]].append(c)
    return [
        {"mobile": phone, "count": len(cs),
         "customers": [{"id": c["id"], "full_name": c["full_name"],
                        "entry_date": c["entry_date"]} for c in cs]}
        for phone, cs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        if len(cs) > 1
    ]


def build_stats(customers: list[dict], dups: list[dict]) -> dict:
    by_month = Counter(c["entry_date"][:7] for c in customers if c["entry_date"])
    surnames = Counter(c["last_name"].title() for c in customers if c["last_name"])
    birth = Counter(c["birth_month"] for c in customers if c["birth_month"])
    anniv = Counter(c["anniversary_month"] for c in customers if c["anniversary_month"])
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "total_customers": len(customers),
        "unique_mobiles": len({c["mobile_1"] for c in customers if c["mobile_1"]}),
        "missing_phone": sum(c["missing_phone"] for c in customers),
        "missing_birthday": sum(c["missing_birthday"] for c in customers),
        "missing_anniversary": sum(c["missing_anniversary"] for c in customers),
        "missing_last_name": sum(c["missing_last_name"] for c in customers),
        "missing_entry_date": sum(c["entry_date"] is None for c in customers),
        "invalid_phone": sum(c["invalid_phone"] for c in customers),
        "entry_dates_swapped": sum(c["entry_date_swapped"] for c in customers),
        "duplicate_mobile_groups": len(dups),
        "duplicate_mobile_rows": sum(d["count"] for d in dups),
        "birth_months": {m: birth.get(m, 0) for m in MONTHS},
        "anniversary_months": {m: anniv.get(m, 0) for m in MONTHS},
        "entries_by_month": dict(sorted(by_month.items())),
        "top_surnames": [{"surname": s, "count": n} for s, n in surnames.most_common(15)],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=ROOT / "data/local/customers_source.xlsx")
    ap.add_argument("--out", type=Path, default=ROOT / "data/local")
    ap.add_argument("--dashboard", type=Path, default=ROOT / "dashboard/data.json",
                    help="where to write the dashboard's data file (gitignored)")
    args = ap.parse_args()

    customers = [clean_record(i, r) for i, r in enumerate(load_rows(args.input), start=1)]
    dups = find_dup_mobiles(customers)
    stats = build_stats(customers, dups)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "customers.json").write_text(json.dumps(customers, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(args.out / "customers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(customers[0]))
        w.writeheader()
        w.writerows(customers)
    (args.out / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    (args.out / "dup_mobiles.json").write_text(json.dumps(dups, indent=2, ensure_ascii=False), encoding="utf-8")

    args.dashboard.parent.mkdir(parents=True, exist_ok=True)
    args.dashboard.write_text(json.dumps({"stats": stats, "dup_mobiles": dups}, indent=2, ensure_ascii=False),
                              encoding="utf-8")

    print(f"{stats['total_customers']} customers -> {args.out}")
    for k in ("missing_phone", "missing_birthday", "missing_anniversary", "missing_last_name",
              "missing_entry_date", "invalid_phone", "entry_dates_swapped",
              "duplicate_mobile_groups", "duplicate_mobile_rows"):
        print(f"  {k:24} {stats[k]}")
    print(f"dashboard data -> {args.dashboard}")


if __name__ == "__main__":
    main()
