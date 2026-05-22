# SermonFlow

Automated church service presentation pipeline. Takes a Planning Center order of service and a pastor's Google Docs sermon notes (yellow-highlighted text = slides), runs them through Claude AI to format worship lyrics and sermon points, and produces ProPresenter 7 `.pro` files ready for Sunday morning. Includes a human review PDF emailed before anything goes live.

```
Planning Center  +  Google Docs (highlights)
        │                   │
        └─────────┬──────────┘
                  ▼
         Claude AI formatting
         (lyric slides + sermon points)
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
  ProPresenter 7       Review PDF
  .pro files           (emailed for approval)
```

---

## Prerequisites

- Python 3.12+
- Git
- Planning Center Personal Access Token
- Anthropic API key
- Google Cloud project with Docs API enabled (see Google Setup below)

---

## Install

```bash
git clone <this-repo>
cd sermonflow-pco
git submodule update --init --recursive   # pulls ProPresenter7-Proto

python3 -m venv deps
source deps/bin/activate                  # Windows: deps\Scripts\activate

pip install -r requirements.txt
```

---

## Protobuf code generation

The ProPresenter `.pro` file format is Google Protocol Buffers. You need to
compile the `.proto` schema files into Python classes once after cloning.

```bash
make proto
```

This runs two `protoc` steps — the main PP7 schemas and the Google wrapper
types — and creates the required output directories automatically. See the
Makefile for the exact commands.

---

## Environment variables

Copy and fill in:

```bash
# Planning Center Personal Access Token
export PCO_ID="your_app_id"
export PCO_SECRET="your_secret"

# Anthropic (Claude API)
export ANTHROPIC_API_KEY="your_key"

# Google Docs — the long ID from the doc URL (/d/<THIS>/edit)
export GDOCS_DOC_ID="your_doc_id"

# ProPresenter output directory (defaults to ~/Documents/ProPresenter/Libraries/Default/)
export PP7_OUTPUT_DIR="/path/to/your/pp/library"

# Email review step (optional — skip with --skip-review if not configured)
export REVIEW_EMAIL_TO="reviewer@church.org"
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USER="you@gmail.com"
export SMTP_PASSWORD="your_app_password"
```

Or put them all in a `.env` file at the project root (never commit it).

---

## Google Docs setup (one-time)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → New Project
2. **APIs & Services** → **Library** → search `Google Docs API` → Enable
3. **APIs & Services** → **Credentials** → **+ Create Credentials** → **OAuth client ID**
   - Configure consent screen if prompted: External, add your Gmail as a Test User
   - Application type: **Desktop app** → Create
4. Download the JSON → save as `credentials.json` in this directory
5. First run opens a browser for one-time authorization → saves `token.json`

---

## Run

```bash
source deps/bin/activate

# Full pipeline (email review not configured? use --skip-review)
python pipeline.py --skip-review --service-type Weekend

# No Google Doc yet?
python pipeline.py --skip-review --skip-gdocs --service-type Weekend

# Reuse a previously fetched schema (skips PCO API call)
python pipeline.py --skip-review --schema service_schema.json

# Generate review PDF from existing schema only
python pipeline.py --pdf-only --schema service_schema.json
```

### All flags

| Flag | Effect |
|---|---|
| `--service-type TEXT` | Service type name fragment to match in PCO (default: `sunday`) |
| `--doc-id TEXT` | Google Doc ID (overrides `GDOCS_DOC_ID` env var) |
| `--output-dir PATH` | Directory for `.pro` files (overrides `PP7_OUTPUT_DIR`) |
| `--schema PATH` | Load existing `service_schema.json` instead of fetching from PCO |
| `--skip-gdocs` | Skip Google Docs step |
| `--skip-ai` | Skip Claude AI formatting (passes raw lyrics through) |
| `--skip-pp7` | Skip ProPresenter file generation |
| `--skip-review` | Skip PDF generation and review email |
| `--no-wait` | Send review email but don't block waiting for approval |
| `--pdf-only` | Generate review PDF from existing schema, then exit |

---

## Individual module smoke tests

Each module can run standalone:

```bash
python pco.py        # lists service types + builds schema from PCO
python ai.py         # formats sample lyrics + sermon slides via Claude
python gdocs.py      # extracts highlights from GDOCS_DOC_ID doc
python review.py     # generates review_slides.pdf from service_schema.json
```

---

## Approval gate

When the review email is sent, the pipeline blocks waiting for a human to
create a flag file in the project directory:

```bash
touch APPROVED   # proceed
touch REJECTED   # abort pipeline
```

Times out after 1 hour.

---

## Files not committed

| File | Purpose |
|---|---|
| `credentials.json` | Google OAuth client secrets (download from Cloud Console) |
| `token.json` | Google OAuth token (auto-created on first run) |
| `service_schema.json` | Generated PCO service data |
| `review_slides.pdf` | Generated review PDF |
| `.env` | Local environment variables |
