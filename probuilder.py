"""
probuilder.py — standalone ProPresenter .pro file builder for debugging.

Usage:
    python probuilder.py [service_schema.json] [--out ./output]

Loads a service_schema.json, walks every item verbosely, and writes one
.pro file per item that has slides.  All protobuf logic is self-contained
here so you can step through it without chasing imports across modules.
"""

import json
import os
import sys
import uuid
import argparse

# pb2 files import each other by bare name, so pco_types/ must be on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pco_types"))

import pco_types.presentation_pb2 as presentation_pb2
import pco_types.cue_pb2 as cue_pb2
import pco_types.action_pb2 as action_pb2
import pco_types.slide_pb2 as slide_pb2
import pco_types.presentationSlide_pb2 as presentationSlide_pb2
import pco_types.basicTypes_pb2 as basicTypes_pb2
import pco_types.graphicsData_pb2 as graphicsData_pb2

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SLIDE_WIDTH = 1920.0
SLIDE_HEIGHT = 1080.0

BG_BLACK = (0.0, 0.0, 0.0, 1.0)
BG_DARK = (0.08, 0.08, 0.08, 1.0)
TEXT_WHITE = (1.0, 1.0, 1.0, 1.0)

# ---------------------------------------------------------------------------
# UUID / color helpers
# ---------------------------------------------------------------------------


def _new_uuid() -> str:
    return str(uuid.uuid4()).upper()


def _make_color(r: float, g: float, b: float, a: float = 1.0) -> basicTypes_pb2.Color:
    c = basicTypes_pb2.Color()
    c.red = r
    c.green = g
    c.blue = b
    c.alpha = a
    return c


# ---------------------------------------------------------------------------
# RTF builder
# ---------------------------------------------------------------------------


def _build_rtf(text: str, font_size_pt: int = 60, bold: bool = False) -> bytes:
    bold_on = r"\b " if bold else ""
    bold_off = r"\b0 " if bold else ""
    safe = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    safe = safe.replace("\n", r"\line ")
    rtf = (
        r"{\rtf1\ansi\ansicpg1252"
        r"{\fonttbl\f0\fswiss\fcharset0 Helvetica-Bold;}"
        r"{\colortbl;\red255\green255\blue255;}"
        r"\pard\pardirnatural\qc\partightenfactor0"
        rf"\f0\fs{font_size_pt * 2} \cf1 {bold_on}{safe}{bold_off}"
        r"}"
    )
    return rtf.encode("utf-8")


# ---------------------------------------------------------------------------
# Protobuf object builders
# ---------------------------------------------------------------------------


def _make_slide(
    text: str,
    bg_color: tuple = BG_DARK,
    font_size_pt: int = 60,
    bold: bool = False,
) -> slide_pb2.Slide:
    s = slide_pb2.Slide()
    s.uuid.string = _new_uuid()
    s.size.width = SLIDE_WIDTH
    s.size.height = SLIDE_HEIGHT
    s.draws_background_color = True
    s.background_color.CopyFrom(_make_color(*bg_color))

    outer = s.elements.add()
    outer.info = 3  # INFO_IS_TEMPLATE_ELEMENT | INFO_IS_TEXT_ELEMENT
    inner = outer.element
    inner.uuid.string = _new_uuid()
    inner.opacity = 1.0
    inner.bounds.origin.x = 0.0
    inner.bounds.origin.y = 0.0
    inner.bounds.size.width = SLIDE_WIDTH
    inner.bounds.size.height = SLIDE_HEIGHT
    inner.text.rtf_data = _build_rtf(text, font_size_pt=font_size_pt, bold=bold)

    return s


def _make_cue(
    slide_text: str,
    bg_color: tuple = BG_DARK,
    font_size_pt: int = 60,
) -> cue_pb2.Cue:
    cue = cue_pb2.Cue()
    cue.uuid.string = _new_uuid()
    cue.isEnabled = True

    act = cue.actions.add()
    act.uuid.string = _new_uuid()
    act.isEnabled = True
    act.type = action_pb2.Action.ACTION_TYPE_PRESENTATION_SLIDE

    pres_slide = presentationSlide_pb2.PresentationSlide()
    pres_slide.base_slide.CopyFrom(
        _make_slide(slide_text, bg_color=bg_color, font_size_pt=font_size_pt)
    )
    act.slide.presentation.CopyFrom(pres_slide)

    return cue


def _build_presentation(
    title: str,
    slides: list[str],
    bg_color: tuple = BG_DARK,
    font_size_pt: int = 60,
) -> presentation_pb2.Presentation:
    pres = presentation_pb2.Presentation()
    pres.uuid.string = _new_uuid()
    pres.name = title
    for text in slides:
        pres.cues.append(_make_cue(text, bg_color=bg_color, font_size_pt=font_size_pt))
    return pres


def _save(pres: presentation_pb2.Presentation, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(pres.SerializeToString())


# ---------------------------------------------------------------------------
# Schema walker
# ---------------------------------------------------------------------------


def process_schema(schema: dict, output_dir: str) -> list[str]:
    saved = []
    items = schema.get("items", [])
    print(f"\nSchema: {schema.get('service', {}).get('plan_title', '?')} "
          f"({len(items)} items)")
    print(f"Output dir: {output_dir}\n")

    for item in sorted(items, key=lambda x: x.get("sequence", 0)):
        seq = item.get("sequence")
        kind = item.get("item_type")
        title = item.get("title", "unknown")
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()

        print(f"[{seq:02d}] {kind:8s}  '{title}'")

        # --- song: collect slides from sections ---
        if kind == "song":
            song = item.get("song", {})
            sections = song.get("sections", [])
            all_slides = []
            for sec in sections:
                label = sec.get("label") or sec.get("section_type", "?")
                sec_slides = sec.get("slides", [])
                print(f"         section '{label}': {len(sec_slides)} slide(s)")
                all_slides.extend(sec_slides)

            if not all_slides:
                print(f"         → SKIP: no slides in any section")
                continue

            pres = _build_presentation(title, all_slides, bg_color=BG_DARK)
            path = os.path.join(output_dir, f"{safe_title}.pro")
            _save(pres, path)
            print(f"         → WROTE {len(all_slides)} cues  →  {path}")
            saved.append(path)

        # --- non-song item: slides_to_generate field ---
        elif item.get("slides_to_generate"):
            slides = item["slides_to_generate"]
            pres = _build_presentation(title, slides, bg_color=BG_BLACK, font_size_pt=54)
            path = os.path.join(output_dir, f"{safe_title}.pro")
            _save(pres, path)
            print(f"         → WROTE {len(slides)} cues  →  {path}")
            saved.append(path)

        else:
            print(f"         → SKIP: no slides_to_generate")

    return saved


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Build PP7 .pro files from service_schema.json")
    parser.add_argument(
        "schema",
        nargs="?",
        default="service_schema.json",
        help="Path to service_schema.json (default: service_schema.json)",
    )
    parser.add_argument(
        "--out",
        default="output",
        help="Output directory for .pro files (default: output/)",
    )
    args = parser.parse_args()

    with open(args.schema) as f:
        schema = json.load(f)

    saved = process_schema(schema, args.out)

    print(f"\nDone. {len(saved)} file(s) written.")
    for p in saved:
        print(f"  {p}")


if __name__ == "__main__":
    main()
