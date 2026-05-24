"""
SermonFlow — ProPresenter 7 file packager.

Builds a .pro file (protobuf binary) from a list of slides.

Dependency: pco_types/ directory with generated pb2 files must exist.
Generate with:
  git clone https://github.com/greyshirtguy/ProPresenter7-Proto
  pip install grpcio-tools
  python -m grpc_tools.protoc \\
      --proto_path=ProPresenter7-Proto/Proto \\
      --python_out=pco_types \\
      ProPresenter7-Proto/Proto/*.proto

Environment variable (optional):
  PP7_OUTPUT_DIR   — where to drop .pro files
                     defaults to ~/Documents/ProPresenter/Libraries/Default/
"""

import os
import uuid


import pco_types.presentation_pb2 as presentation_pb2
import pco_types.cue_pb2 as cue_pb2
import pco_types.action_pb2 as action_pb2
import pco_types.slide_pb2 as slide_pb2
import pco_types.presentationSlide_pb2 as presentationSlide_pb2
import pco_types.basicTypes_pb2 as basicTypes_pb2
import pco_types.graphicsData_pb2 as graphicsData_pb2

DEFAULT_OUTPUT_DIR = os.path.expanduser("libs")

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


def _set_uuid(msg) -> None:
    msg.uuid.string = _new_uuid()


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
    outer.info = 2  # INFO_IS_TEXT_ELEMENT
    inner = outer.element
    inner.uuid.string = _new_uuid()
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

    act = cue.actions.add()
    act.uuid.string = _new_uuid()

    pres_slide = presentationSlide_pb2.PresentationSlide()
    pres_slide.base_slide.CopyFrom(
        _make_slide(slide_text, bg_color=bg_color, font_size_pt=font_size_pt)
    )
    act.slide.presentation.CopyFrom(pres_slide)

    return cue


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_song_presentation(
    title: str,
    slides: list[str],
    bg_color: tuple = BG_DARK,
    font_size_pt: int = 60,
) -> presentation_pb2.Presentation:
    """
    Build a PP7 Presentation for a worship song.

    Args:
        title:        Song title (used as presentation name)
        slides:       List of slide text strings (may contain \\n for line breaks)
        bg_color:     RGBA tuple for slide background
        font_size_pt: Font size in points
    """
    pres = presentation_pb2.Presentation()
    pres.uuid.string = _new_uuid()
    pres.name = title

    for text in slides:
        pres.cues.append(_make_cue(text, bg_color=bg_color, font_size_pt=font_size_pt))

    return pres


def build_sermon_presentation(
    title: str,
    slides: list[str],
    bg_color: tuple = BG_BLACK,
    font_size_pt: int = 54,
) -> presentation_pb2.Presentation:
    """Build a PP7 Presentation for sermon point slides."""
    pres = presentation_pb2.Presentation()
    pres.uuid.string = _new_uuid()
    pres.name = title

    for text in slides:
        pres.cues.append(_make_cue(text, bg_color=bg_color, font_size_pt=font_size_pt))

    return pres


def save_presentation(pres: presentation_pb2.Presentation, path: str) -> str:
    """Serialize to .pro file. Returns the path written."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(pres.SerializeToString())
    print(f"Saved: {path}")
    return path


def build_and_save_from_schema(
    schema: dict,
    output_dir: str = None,
) -> list[str]:
    """
    Build one .pro file per song item in the schema and save them.
    Returns list of saved file paths.
    """
    output_dir = output_dir or os.environ.get("PP7_OUTPUT_DIR") or DEFAULT_OUTPUT_DIR
    saved = []

    for item in schema.get("items", []):
        title = item.get("title", "unknown")
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()

        if item.get("item_type") == "song":
            all_slides = []
            for section in item.get("song", {}).get("sections", []):
                all_slides.extend(section.get("slides", []))
            if not all_slides:
                print(f"  Skipping '{title}' — no slides")
                continue
            pres = build_song_presentation(title, all_slides)

        elif item.get("slides_to_generate"):
            pres = build_sermon_presentation(title, item["slides_to_generate"])

        else:
            continue

        path = os.path.join(output_dir, f"{safe_title}.pro")
        save_presentation(pres, path)
        saved.append(path)

    return saved
