"""
SermonFlow — main pipeline orchestrator.

Usage:
  python pipeline.py [options]

Options:
  --service-type TEXT   Service type name fragment (default: sunday)
  --doc-id TEXT         Google Doc ID for sermon notes (or set GDOCS_DOC_ID)
  --output-dir PATH     Where to save .pro files (or set PP7_OUTPUT_DIR)
  --skip-gdocs          Skip Google Docs step (no sermon slides)
  --skip-ai             Skip AI formatting (pass raw lyrics through)
  --skip-pp7            Skip ProPresenter file generation
  --skip-review         Skip PDF generation and review email
  --schema PATH         Load an existing service_schema.json instead of fetching
  --pdf-only            Generate review PDF from existing schema, then exit

Pipeline stages:
  1. Fetch service schema from Planning Center
  2. Extract sermon highlights from Google Docs
  3. AI-format lyric slides + generate sermon slides
  4. Package ProPresenter 7 .pro files
  5. Generate review PDF + send email
  6. Wait for approval
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _step(n: int, label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Step {n}: {label}")
    print(f"{'='*60}")


def _load_schema(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _save_schema(schema: dict, path: str = "service_schema.json") -> None:
    with open(path, "w") as f:
        json.dump(schema, f, indent=2)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> None:

    schema_path = args.schema or "service_schema.json"

    # ------------------------------------------------------------------
    # Step 1: Service schema
    # ------------------------------------------------------------------
    _step(1, "Planning Center — fetch service schema")

    if args.schema and Path(args.schema).exists():
        print(f"Loading existing schema from {args.schema}")
        schema = _load_schema(args.schema)
    else:
        from pco import build_service_schema

        schema = build_service_schema(
            service_type_name=args.service_type,
            save_path=schema_path,
        )

    svc = schema["service"]
    print(f"Plan: {svc['plan_title']}  ({svc['plan_date'][:10]})")
    songs = [i for i in schema["items"] if i["item_type"] == "song"]
    headers = [i for i in schema["items"] if i["item_type"] != "song"]
    print(
        f"Items: {len(schema['items'])} total  ({len(songs)} songs, {len(headers)} non-song)"
    )

    if args.pdf_only:
        _pdf_and_exit(schema, args)
        return

    # ------------------------------------------------------------------
    # Step 2: Google Docs highlights
    # ------------------------------------------------------------------
    _step(2, "Google Docs — extract sermon highlights")

    highlights = []
    if args.skip_gdocs:
        print("Skipped (--skip-gdocs)")
    else:
        try:
            from gdocs import get_sermon_highlights

            doc_id = args.doc_id or os.environ.get("GDOCS_DOC_ID")
            if not doc_id:
                print("No doc ID — skipping Google Docs step.")
                print("Pass --doc-id or set GDOCS_DOC_ID to enable sermon slides.")
            else:
                highlights = get_sermon_highlights(doc_id)
        except Exception as e:
            print(f"Google Docs step failed: {e}")
            print("Continuing without sermon slides.")

    # ------------------------------------------------------------------
    # Step 3: Slides
    # ------------------------------------------------------------------
    _step(3, "Slides — promote lyrics + attach sermon highlights")

    # Lyrics are manual — promote raw PCO lyrics to slides
    for item in schema["items"]:
        if item["item_type"] != "song":
            continue
        for section in item.get("song", {}).get("sections", []):
            if not section["slides"] and section["lyrics"]:
                section["slides"] = [section["lyrics"]]

    # Attach highlights directly to the "Message" item as slides (raw, no AI)
    if highlights:
        for item in schema["items"]:
            if item.get("title") == "Message":
                item["slides_to_generate"] = highlights
                print(f"Attached {len(highlights)} highlight(s) to Message")
                break

    _save_schema(schema, schema_path)
    print(f"Schema updated → {schema_path}")

    # ------------------------------------------------------------------
    # Step 4: ProPresenter 7 files
    # ------------------------------------------------------------------
    _step(4, "ProPresenter 7 — build .pro files")

    if args.skip_pp7:
        print("Skipped (--skip-pp7)")
    else:
        try:
            from pp7 import build_and_save_from_schema

            output_dir = args.output_dir or os.environ.get("PP7_OUTPUT_DIR")
            saved = build_and_save_from_schema(schema, output_dir=output_dir)
            print(f"Saved {len(saved)} .pro file(s)")
            for path in saved:
                print(f"  → {path}")
        except SystemExit as e:
            # pp7.py raises SystemExit if propresenter_pb2 is missing
            print(f"PP7 step skipped: {e}")
        except Exception as e:
            print(f"PP7 step failed: {e}")

    # ------------------------------------------------------------------
    # Step 5: Review PDF + email
    # ------------------------------------------------------------------
    _step(5, "Review — generate PDF + send email")

    if args.skip_review:
        print("Skipped (--skip-review)")
        return

    _pdf_and_exit(schema, args)


def _pdf_and_exit(schema: dict, args: argparse.Namespace) -> None:
    try:
        from review import generate_pdf, send_review_email

        svc = schema["service"]
        pdf_path = generate_pdf(schema, "review_slides.pdf")

        to_email = os.environ.get("REVIEW_EMAIL_TO")
        if to_email and os.environ.get("SMTP_HOST"):
            send_review_email(
                pdf_path,
                plan_title=svc.get("plan_title", ""),
                plan_date=svc.get("plan_date", "")[:10],
            )
        else:
            print("Email not configured — skipping send.")

        print(f"Review PDF: {pdf_path}")
        print("Pipeline complete.")

    except Exception as e:
        print(f"Review step failed: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="SermonFlow — build ProPresenter slides from Planning Center + Google Docs"
    )
    p.add_argument(
        "--service-type",
        default="sunday",
        help="Service type name fragment (default: sunday)",
    )
    p.add_argument(
        "--doc-id", default=None, help="Google Doc ID (overrides GDOCS_DOC_ID env var)"
    )
    p.add_argument(
        "--output-dir",
        default=None,
        help="Directory for .pro files (overrides PP7_OUTPUT_DIR)",
    )
    p.add_argument(
        "--schema",
        default=None,
        help="Load existing service_schema.json instead of fetching",
    )
    p.add_argument("--skip-gdocs", action="store_true")
    p.add_argument("--skip-ai", action="store_true")
    p.add_argument("--skip-pp7", action="store_true")
    p.add_argument("--skip-review", action="store_true")
    p.add_argument(
        "--pdf-only",
        action="store_true",
        help="Generate review PDF from existing schema and exit",
    )
    return p


if __name__ == "__main__":
    parser = _build_parser()
    run(parser.parse_args())
