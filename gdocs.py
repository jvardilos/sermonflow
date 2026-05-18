"""
SermonFlow — Google Docs highlight extractor.

Extracts yellow-highlighted text from the pastor's sermon notes Google Doc.
Yellow highlight = slide content.

Setup (one-time):
  1. console.cloud.google.com → New project → Enable "Google Docs API"
  2. APIs & Services → Credentials → Create OAuth 2.0 Client ID (Desktop app)
  3. Download JSON → save as credentials.json in this directory
  4. pip install google-auth-oauthlib google-api-python-client
  5. First run opens a browser for authorization and saves token.json

Environment variable required:
  GDOCS_DOC_ID   — the document ID from the Google Doc URL
                   (the long string between /d/ and /edit in the URL)
"""

import os
import json

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    raise SystemExit(
        "Google API packages missing.\n"
        "Run: pip install google-auth-oauthlib google-api-python-client"
    )

SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]

_HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(_HERE, "token.json")
CREDS_PATH = os.path.join(_HERE, "credentials.json")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_creds() -> Credentials:
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_PATH):
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDS_PATH}.\n"
                    "Download it from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


def get_service():
    return build("docs", "v1", credentials=_get_creds())


# ---------------------------------------------------------------------------
# Document fetching
# ---------------------------------------------------------------------------

def get_doc(doc_id: str) -> dict:
    return get_service().documents().get(documentId=doc_id).execute()


# ---------------------------------------------------------------------------
# Highlight extraction
# ---------------------------------------------------------------------------

# Google Docs represents yellow highlight as high R+G, low B.
# The default "yellow" highlight in Google Docs is exactly {r:1, g:1, b:0}.
# We allow some tolerance for custom yellows.
def _is_yellow(rgb: dict) -> bool:
    r = rgb.get("red",   0.0)
    g = rgb.get("green", 0.0)
    b = rgb.get("blue",  0.0)
    return r >= 0.8 and g >= 0.7 and b <= 0.35


def extract_highlights(doc: dict) -> list[str]:
    """
    Walk the document body and return yellow-highlighted text spans,
    in document order. Adjacent highlighted runs are merged.
    """
    highlights = []
    current_runs: list[str] = []

    def flush():
        if current_runs:
            text = "".join(current_runs).strip()
            if text:
                highlights.append(text)
            current_runs.clear()

    content = doc.get("body", {}).get("content", [])
    for block in content:
        paragraph = block.get("paragraph")
        if not paragraph:
            flush()
            continue

        for element in paragraph.get("elements", []):
            run = element.get("textRun")
            if not run:
                continue

            text = run.get("content", "")
            style = run.get("textStyle", {})
            bg_color = (
                style
                .get("backgroundColor", {})
                .get("color", {})
                .get("rgbColor", {})
            )

            if _is_yellow(bg_color):
                current_runs.append(text)
            else:
                flush()

        # A paragraph break resets the current run
        flush()

    flush()
    return highlights


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_sermon_highlights(doc_id: str = None) -> list[str]:
    """
    Fetch the Google Doc and return yellow-highlighted strings in order.
    Uses GDOCS_DOC_ID env var if doc_id is not provided.
    """
    doc_id = doc_id or os.environ.get("GDOCS_DOC_ID")
    if not doc_id:
        raise ValueError(
            "doc_id required — pass it directly or set GDOCS_DOC_ID env var."
        )

    doc = get_doc(doc_id)
    highlights = extract_highlights(doc)
    print(f"Extracted {len(highlights)} highlighted passages from '{doc.get('title', doc_id)}'")
    return highlights


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    doc_id = os.environ.get("GDOCS_DOC_ID")
    if not doc_id:
        print("Set GDOCS_DOC_ID to your Google Doc ID and re-run.")
        raise SystemExit(1)

    highlights = get_sermon_highlights(doc_id)
    print(f"\n=== {len(highlights)} highlighted passages ===")
    for i, h in enumerate(highlights, 1):
        print(f"  {i:>2}. {h[:100]}{'...' if len(h) > 100 else ''}")
