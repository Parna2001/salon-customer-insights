"""Ask a question about the customer database.

Usage:
    python rag/query.py "who has birthdays in July" [-k 10] [--show-prompt]

Retrieves the top-k records from the local TF-IDF index. If ANTHROPIC_API_KEY
is set, sends the RAG prompt to Claude for a generated answer; otherwise runs
in retrieval-only mode and prints the records and the prompt it would send.

Note: generation mode sends the retrieved records (names, phones, dates) to
the Anthropic API.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_index import DEFAULT_INDEX, CustomerIndex  # noqa: E402
from prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402

MODEL = "claude-sonnet-5"


def generate(system: str, user: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.AuthenticationError:
        raise SystemExit("ANTHROPIC_API_KEY was rejected.")
    except anthropic.RateLimitError:
        raise SystemExit("Rate limited by the Anthropic API; try again shortly.")
    except anthropic.APIStatusError as e:
        raise SystemExit(f"Anthropic API error ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        raise SystemExit("Could not reach the Anthropic API.")
    if response.stop_reason == "refusal":
        return "(The model declined to answer this question.)"
    return "".join(b.text for b in response.content if b.type == "text")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=8, help="number of records to retrieve (default 8)")
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    ap.add_argument("--show-prompt", action="store_true", help="print the full prompt in generation mode too")
    args = ap.parse_args()

    index = CustomerIndex.load(args.index)
    hits = index.search(args.question, k=args.k)

    print(f"Top {len(hits)} records for: {args.question!r}\n")
    for rank, (score, c, _doc) in enumerate(hits, start=1):
        print(f"  #{rank}  {score:.3f}  {c['full_name']:<30} "
              f"mobile={c.get('mobile_1') or '-':<11} "
              f"birthday={(c.get('birth_day') or '')} {c.get('birth_month') or '-':<10} "
              f"anniversary={(c.get('anniversary_day') or '')} {c.get('anniversary_month') or '-'}")

    user_prompt = build_user_prompt(args.question, [c for _, c, _ in hits])
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if not has_key or args.show_prompt:
        print("\n--- system prompt ---\n" + SYSTEM_PROMPT)
        print("--- user prompt ---\n" + user_prompt)

    if has_key:
        print(f"--- answer ({MODEL}) ---")
        print(generate(SYSTEM_PROMPT, user_prompt))
    else:
        print("(retrieval-only mode: set ANTHROPIC_API_KEY to generate an answer with Claude)")


if __name__ == "__main__":
    main()
