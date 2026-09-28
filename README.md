# Salon Customer Insights

Tools for a salon's customer list (an Excel sheet of names, phone numbers,
birthdays and anniversaries):

1. **Data cleaning** – `scripts/clean_data.py` turns the workbook into clean JSON/CSV,
   flags gaps, and finds phone numbers entered twice under different spellings.
2. **Local RAG** – `rag/` answers questions like *"who has birthdays in July"* by
   retrieving matching records with TF-IDF, optionally passing them to Claude.
3. **Dashboard** – `dashboard/index.html`, a static page with hand-built SVG charts.

## Privacy: real data stays local

The customer sheet is real personal data. The repo is split so none of it can be
committed:

| Where | What | In git? |
|---|---|---|
| `data/local/` | source xlsx, `customers.json/.csv`, `stats.json`, `dup_mobiles.json`, RAG index | **No** – gitignored |
| `dashboard/data.json` | real aggregates + duplicate-mobile groups (names, phones) | **No** – gitignored |
| `dashboard/data.sample.json` | 40 **synthetic** customers (invented names, 555 numbers) | Yes |
| code, prompts, workflow | no customer data | Yes |

The public GitHub Pages site therefore always shows the synthetic sample. The real
dashboard only exists on the machine where you run the cleaner. `*.xlsx` is also
gitignored as a backstop.

## Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
```

## 1. Clean the data

Copy the workbook to `data/local/customers_source.xlsx` (or pass `--input`):

```bash
python scripts/clean_data.py
python scripts/clean_data.py --input "path/to/Customers.xlsx"
```

Writes `data/local/{customers.json, customers.csv, stats.json, dup_mobiles.json}`
and `dashboard/data.json`.

What it does:

- **Date of Entry** is normalized to ISO dates. The sheet mixes text dates
  (`8/16/2026`, M/D/Y) with real Excel dates. The Excel dates were produced by
  opening an M/D/Y export in a D/M/Y-locale Excel, which silently swapped day and
  month whenever the day was ≤ 12. The cleaner swaps those back and flags each
  one (`entry_date_swapped`).
- `full_name` is built from First/Middle/Last. Whitespace is collapsed and month
  names normalized (`june` → `June`).
- Per-row flags: `missing_phone`, `missing_birthday`, `missing_anniversary`,
  `missing_last_name`, `invalid_phone` (not 10 digits).
- **Duplicate mobiles**: any `Mobile_1` shared by several rows is reported in
  `dup_mobiles.json`. These are usually one customer entered twice
  (e.g. "Bea Mockwell" / "Beaa Mockwell" in the sample data).

`scripts/make_sample_data.py` regenerates the synthetic `dashboard/data.sample.json`
using the same stats code.

## 2. Ask questions (RAG)

```bash
python rag/build_index.py
python rag/query.py "who has birthdays in July" -k 25
python rag/query.py "phone number 5550831970"
python rag/query.py "what is Bea Mockwell's anniversary"
```

- **Retrieval** (`rag/build_index.py`): each customer becomes one text document
  (name, phones, birthday, anniversary, entry date, notes). Scores are a blend of
  word TF-IDF and character n-gram TF-IDF (cosine similarity); the n-grams
  tolerate spelling variants and partial numbers. Month questions are expanded
  with field tags (`birth_july`, `anniv_july`) so "birthdays in July" doesn't
  return July anniversaries. No API key or model download is needed.
- **Prompt** (`rag/prompts.py`): the system prompt tells the model to answer only
  from the retrieved records and never invent names, numbers or dates. The user
  prompt lists the top-k records as numbered `Record #N` blocks before the
  question.
- **Generation** (`rag/query.py`): if `ANTHROPIC_API_KEY` is set, the prompt goes
  to Claude (`claude-sonnet-5`). Otherwise it runs in retrieval-only mode and
  prints the records and the prompt. Note that generation mode sends the
  retrieved customer records to the Anthropic API.

Top-k retrieval returns at most *k* rows. For "list everyone who…" questions,
raise `-k` (July has ~23 birthdays).

## 3. Dashboard

```bash
python scripts/clean_data.py         # writes dashboard/data.json
python -m http.server -d dashboard 8000
# open http://localhost:8000
```

The page fetches `./data.json`. If that is missing (as on GitHub Pages), it falls
back to `./data.sample.json` and shows a "synthetic sample data" banner. It
follows the system light/dark setting, with a manual toggle.

### GitHub Pages

`.github/workflows/deploy-dashboard.yml` publishes `dashboard/` on every push to
`main`. Enable it once under **Settings → Pages → Source: GitHub Actions**.
