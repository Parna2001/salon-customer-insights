"""Build a local TF-IDF retrieval index over the cleaned customer records.

Usage:
    python rag/build_index.py [--customers data/local/customers.json]
                              [--index data/local/rag_index.pkl]

No API key or model download needed: scikit-learn TF-IDF + cosine similarity.
The index embeds customer PII, so it is written under data/local/ (gitignored).
"""
from __future__ import annotations

import argparse
import json
import pickle
import re
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CUSTOMERS = ROOT / "data/local/customers.json"
DEFAULT_INDEX = ROOT / "data/local/rag_index.pkl"

MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]
MONTH_ALIASES = {m: m for m in MONTHS} | {m[:3]: m for m in MONTHS} | {"sept": "september"}

# Word-level TF-IDF carries most of the signal; character n-grams add
# tolerance for name spelling variants and partial phone numbers.
WORD_WEIGHT, CHAR_WEIGHT = 0.7, 0.3


def fmt_date(day, month) -> str:
    if day and month:
        return f"{day} {month}"
    return month or "unknown"


def record_to_doc(c: dict) -> str:
    """Flatten one customer into a single text document.

    Field-tagged tokens (birth_july, anniv_march) let a query like
    "birthdays in July" separate birthdays from anniversaries.
    """
    parts = [f"Customer: {c['full_name']}."]
    if c.get("last_name"):
        parts.append(f"Surname {c['last_name']}.")
    phones = [p for p in (c.get("mobile_1"), c.get("mobile_2")) if p]
    parts.append(f"Phone: {' / '.join(phones)}." if phones else "Phone: none on file.")
    bm = (c.get("birth_month") or "").lower()
    parts.append(f"Birthday: {fmt_date(c.get('birth_day'), c.get('birth_month'))}"
                 + (f" birth_{bm}." if bm else "."))
    am = (c.get("anniversary_month") or "").lower()
    parts.append(f"Anniversary: {fmt_date(c.get('anniversary_day'), c.get('anniversary_month'))}"
                 + (f" anniv_{am}." if am else "."))
    if c.get("entry_date"):
        parts.append(f"Customer since {c['entry_date']}.")
    if c.get("notes"):
        parts.append(f"Notes: {c['notes']}.")
    return " ".join(parts)


def expand_query(q: str) -> str:
    """Add field-tagged month tokens so month questions hit the right field."""
    ql = q.lower()
    months = {MONTH_ALIASES[w] for w in re.findall(r"[a-z]+", ql) if w in MONTH_ALIASES}
    if not months:
        return q
    wants_birth = "birth" in ql or "bday" in ql
    wants_anniv = "anniv" in ql or "wedding" in ql
    if not (wants_birth or wants_anniv):
        wants_birth = wants_anniv = True
    extra = []
    for m in months:
        if wants_birth:
            extra += [f"birth_{m}"] * 3
        if wants_anniv:
            extra += [f"anniv_{m}"] * 3
    return q + " " + " ".join(extra)


class CustomerIndex:
    def __init__(self, customers: list[dict]):
        self.customers = customers
        self.docs = [record_to_doc(c) for c in customers]
        self.word_vec = TfidfVectorizer(lowercase=True, token_pattern=r"(?u)\b\w+\b",
                                        sublinear_tf=True)
        self.char_vec = TfidfVectorizer(lowercase=True, analyzer="char_wb",
                                        ngram_range=(3, 5), sublinear_tf=True)
        self.word_m = self.word_vec.fit_transform(self.docs)
        self.char_m = self.char_vec.fit_transform(self.docs)

    def search(self, question: str, k: int = 8) -> list[tuple[float, dict, str]]:
        q = expand_query(question)
        scores = (WORD_WEIGHT * cosine_similarity(self.word_vec.transform([q]), self.word_m)[0]
                  + CHAR_WEIGHT * cosine_similarity(self.char_vec.transform([question]), self.char_m)[0])
        top = np.argsort(-scores)[:k]
        return [(float(scores[i]), self.customers[i], self.docs[i]) for i in top if scores[i] > 0]

    # Pickle plain state (not the class) so the index loads whether this
    # module ran as __main__ or was imported by query.py.
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.__dict__, f)

    @classmethod
    def load(cls, path: Path) -> "CustomerIndex":
        if not path.exists():
            raise SystemExit(f"No index at {path}. Run: python rag/build_index.py")
        index = cls.__new__(cls)
        with open(path, "rb") as f:
            index.__dict__.update(pickle.load(f))
        return index


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customers", type=Path, default=DEFAULT_CUSTOMERS)
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = ap.parse_args()

    customers = json.loads(args.customers.read_text(encoding="utf-8"))
    index = CustomerIndex(customers)
    index.save(args.index)
    print(f"Indexed {len(customers)} records "
          f"({len(index.word_vec.vocabulary_)} word terms, {len(index.char_vec.vocabulary_)} char n-grams)"
          f" -> {args.index}")


if __name__ == "__main__":
    main()
