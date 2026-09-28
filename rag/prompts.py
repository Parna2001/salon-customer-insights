"""RAG prompt templates for answering questions over salon customer records."""
from __future__ import annotations

SYSTEM_PROMPT = """\
You answer questions for a salon owner about their customer records.

You are given a small set of customer records retrieved by keyword search. \
Answer ONLY from those records.

Rules:
- Never invent or guess a name, phone number, birthday, anniversary, or date. \
Copy them exactly as they appear in the records.
- The records are a search result, not the full database. If the question asks \
for "all" customers matching something, list the matches you can see and say \
the list may be incomplete.
- If the records don't contain the answer, say so plainly instead of guessing.
- Ignore retrieved records that don't match the question (for example, an \
anniversary in July when the question is about July birthdays).
- Cite the record numbers you used, like (Record #2).
- Keep the answer short: a sentence or a compact list.
"""

USER_TEMPLATE = """\
Retrieved customer records:

{records}

Question: {question}
"""

RECORD_TEMPLATE = """\
Record #{n}
  Name: {full_name}
  Mobile: {mobile_1}
  Alternate mobile: {mobile_2}
  Birthday: {birthday}
  Anniversary: {anniversary}
  Customer since: {entry_date}
  Notes: {notes}"""


def _day_month(day, month) -> str:
    if day and month:
        return f"{day} {month}"
    return month or "not recorded"


def format_record(n: int, c: dict) -> str:
    return RECORD_TEMPLATE.format(
        n=n,
        full_name=c["full_name"],
        mobile_1=c.get("mobile_1") or "not recorded",
        mobile_2=c.get("mobile_2") or "none",
        birthday=_day_month(c.get("birth_day"), c.get("birth_month")),
        anniversary=_day_month(c.get("anniversary_day"), c.get("anniversary_month")),
        entry_date=c.get("entry_date") or "not recorded",
        notes=c.get("notes") or "none",
    )


def build_user_prompt(question: str, customers: list[dict]) -> str:
    records = "\n\n".join(format_record(i, c) for i, c in enumerate(customers, start=1))
    return USER_TEMPLATE.format(records=records or "(no matching records)", question=question)
