"""
SermonFlow — Human review step.

1. Generates a PDF preview of all slides (song lyrics + sermon points)
2. Emails it for review
3. Waits for approval (approval = reply email or manual flag file)

Environment variables required:
  REVIEW_EMAIL_TO      — address to send the review PDF
  SMTP_HOST            — e.g. smtp.gmail.com
  SMTP_PORT            — e.g. 587
  SMTP_USER            — your sending address
  SMTP_PASSWORD        — app password or SMTP password

For Gmail: use an App Password (myaccount.google.com → Security → App Passwords).
"""

import os
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    raise SystemExit("fpdf2 missing.\nRun: pip install fpdf2")


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

# Slide canvas: 16:9 at 96 px/in equivalent → 1920×1080 → scale to A4 landscape
# fpdf works in mm; use 297×167 mm (roughly 16:9 in A4 landscape width)
SLIDE_W_MM = 270.0
SLIDE_H_MM = 152.0
MARGIN_MM = 13.5


class _SlidePDF(FPDF):
    def header(self):
        pass  # no default header

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", size=7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, f"Page {self.page_no()}", align="C")


def _add_slide_page(
    pdf: _SlidePDF,
    text: str,
    label: str = "",
    bg_rgb: tuple = (20, 20, 20),
    text_rgb: tuple = (255, 255, 255),
    font_size: int = 28,
) -> None:
    pdf.add_page()

    # Dark background rectangle
    pdf.set_fill_color(*bg_rgb)
    pdf.rect(0, 0, pdf.w, pdf.h, "F")

    # Small section label in top-left corner
    if label:
        pdf.set_font("Helvetica", size=8)
        pdf.set_text_color(160, 160, 160)
        pdf.set_xy(MARGIN_MM, MARGIN_MM)
        pdf.cell(0, 5, label)

    # Center the main text vertically and horizontally
    pdf.set_font("Helvetica", "B", size=font_size)
    pdf.set_text_color(*text_rgb)

    lines = text.split("\n")
    line_h = font_size * 0.45  # mm
    total_h = line_h * len(lines)
    start_y = (pdf.h - total_h) / 2

    for i, line in enumerate(lines):
        pdf.set_xy(MARGIN_MM, start_y + i * line_h)
        pdf.cell(pdf.w - 2 * MARGIN_MM, line_h, line, align="C")


def generate_pdf(schema: dict, output_path: str = "review_slides.pdf") -> str:
    """
    Generate a PDF with one page per slide from the service schema.
    Returns the path to the created PDF.
    """
    pdf = _SlidePDF(
        orientation="L", unit="mm", format=(SLIDE_H_MM + 20, SLIDE_W_MM + 20)
    )
    pdf.set_auto_page_break(False)

    plan_title = schema.get("service", {}).get("plan_title", "Service")
    plan_date = schema.get("service", {}).get("plan_date", "")[:10]

    # Title page
    pdf.add_page()
    pdf.set_fill_color(10, 10, 40)
    pdf.rect(0, 0, pdf.w, pdf.h, "F")
    pdf.set_font("Helvetica", "B", 36)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(0, pdf.h / 2 - 20)
    pdf.cell(pdf.w, 15, plan_title, align="C")
    pdf.set_font("Helvetica", size=16)
    pdf.set_text_color(180, 180, 220)
    pdf.set_xy(0, pdf.h / 2)
    pdf.cell(pdf.w, 10, plan_date, align="C")
    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(120, 120, 160)
    pdf.set_xy(0, pdf.h / 2 + 12)
    pdf.cell(pdf.w, 8, "SermonFlow - Review Copy", align="C")

    for item in schema.get("items", []):
        item_type = item.get("item_type")
        title = item.get("title", "")

        if item_type == "song":
            # Section divider page
            _add_slide_page(
                pdf,
                title,
                label=f"seq {item['sequence']}  ·  SONG",
                bg_rgb=(15, 15, 50),
                font_size=32,
            )
            song = item.get("song", {})
            for section in song.get("sections", []):
                for slide_text in section.get("slides", []):
                    _add_slide_page(
                        pdf,
                        slide_text,
                        label=section.get("label", ""),
                        bg_rgb=(20, 20, 20),
                    )

        elif item_type in ("header", "item"):
            sermon_slides = item.get("slides_to_generate", [])
            if sermon_slides:
                _add_slide_page(
                    pdf,
                    title,
                    label=f"seq {item['sequence']}  ·  SERMON",
                    bg_rgb=(30, 10, 10),
                    font_size=32,
                )
                for slide_text in sermon_slides:
                    _add_slide_page(
                        pdf,
                        slide_text,
                        label=title,
                        bg_rgb=(18, 8, 8),
                    )

    pdf.output(output_path)
    print(f"Review PDF saved to {output_path}  ({pdf.page} pages)")
    return output_path


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def send_review_email(
    pdf_path: str,
    plan_title: str = "Sunday Service",
    plan_date: str = "",
    to_email: str = None,
) -> None:
    """Send the review PDF via SMTP."""
    to_email = to_email or os.environ.get("REVIEW_EMAIL_TO")
    if not to_email:
        raise ValueError("REVIEW_EMAIL_TO not set and to_email not provided")

    smtp_host = os.environ.get("SMTP_HOST") or exit("SMTP_HOST not set")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER") or exit("SMTP_USER not set")
    smtp_pass = os.environ.get("SMTP_PASSWORD") or exit("SMTP_PASSWORD not set")

    msg = EmailMessage()
    msg["Subject"] = f"[SermonFlow] Review — {plan_title} {plan_date}"
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.set_content(
        f"SermonFlow has prepared slides for {plan_title} ({plan_date}).\n\n"
        "Please review the attached PDF and reply APPROVE or REJECT.\n\n"
        "— SermonFlow"
    )

    with open(pdf_path, "rb") as f:
        pdf_data = f.read()
    msg.add_attachment(
        pdf_data,
        maintype="application",
        subtype="pdf",
        filename=Path(pdf_path).name,
    )

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_pass)
        smtp.send_message(msg)

    print(f"Review email sent to {to_email}")


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------

_APPROVED_FLAG = Path("APPROVED")
_REJECTED_FLAG = Path("REJECTED")


def wait_for_approval(timeout_secs: int = 3600, poll_secs: int = 30) -> bool:
    """
    Block until a human creates an APPROVED or REJECTED file in this directory,
    or until timeout_secs elapses.

    Returns True if approved, False if rejected or timed out.

    To approve from the command line:  touch APPROVED
    To reject:                         touch REJECTED
    """
    print(f"Waiting for approval (timeout {timeout_secs}s)…")
    print("  Create an 'APPROVED' file here to proceed, or 'REJECTED' to abort.")

    _APPROVED_FLAG.unlink(missing_ok=True)
    _REJECTED_FLAG.unlink(missing_ok=True)

    elapsed = 0
    while elapsed < timeout_secs:
        if _APPROVED_FLAG.exists():
            _APPROVED_FLAG.unlink(missing_ok=True)
            print("Approved!")
            return True
        if _REJECTED_FLAG.exists():
            _REJECTED_FLAG.unlink(missing_ok=True)
            print("Rejected.")
            return False
        time.sleep(poll_secs)
        elapsed += poll_secs

    print(f"Approval timed out after {timeout_secs}s.")
    return False


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json, sys

    schema_path = "service_schema.json"
    if not Path(schema_path).exists():
        print(f"{schema_path} not found — run pco.py first.")
        sys.exit(1)

    with open(schema_path) as f:
        schema = json.load(f)

    pdf_path = generate_pdf(schema, "review_slides.pdf")
    print(f"Open {pdf_path} to preview.")
