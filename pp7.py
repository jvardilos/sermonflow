"""
SermonFlow — ProPresenter 7 file packager.

Builds a .pro file (protobuf binary) from a list of slides.

Dependency: propresenter_pb2.py must exist in this directory.
Generate it once with:

  git clone https://github.com/greyshirtguy/ProPresenter7-Proto
  pip install grpcio-tools
  python -m grpc_tools.protoc \\
      --proto_path=ProPresenter7-Proto/Proto \\
      --python_out=. \\
      ProPresenter7-Proto/Proto/*.proto

Environment variable (optional):
  PP7_OUTPUT_DIR   — where to drop .pro files
                     defaults to ~/Documents/ProPresenter/Libraries/Default/
"""

import os
import uuid

try:
    import pco_types.propresenter_pb2 as pp7
except ImportError:
    raise SystemExit(
        "propresenter_pb2.py not found.\n"
        "Generate it with:\n"
        "  git clone https://github.com/greyshirtguy/ProPresenter7-Proto\n"
        "  pip install grpcio-tools\n"
        "  python -m grpc_tools.protoc \\\n"
        "      --proto_path=ProPresenter7-Proto/Proto \\\n"
        "      --python_out=. \\\n"
        "      ProPresenter7-Proto/Proto/*.proto"
    )

DEFAULT_OUTPUT_DIR = os.path.expanduser("~/Documents/ProPresenter/Libraries/Default/")

# Default slide dimensions — 1920x1080
SLIDE_WIDTH = 1920.0
SLIDE_HEIGHT = 1080.0

# Default colors
BG_BLACK = (0.0, 0.0, 0.0, 1.0)  # r, g, b, a
BG_DARK = (0.08, 0.08, 0.08, 1.0)
TEXT_WHITE = (1.0, 1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# UUID helpers
# ---------------------------------------------------------------------------


def _new_uuid() -> str:
    return str(uuid.uuid4()).upper()


def _make_uuid(value: str) -> pp7.UUID:
    u = pp7.UUID()
    u.string = value
    return u


# ---------------------------------------------------------------------------
# RTF builder
# ---------------------------------------------------------------------------


def _build_rtf(text: str, font_size_pt: int = 60, bold: bool = False) -> bytes:
    """
    Build a minimal RTF string for a PP7 text element.
    Font size in points; RTF uses half-points (\fs = pt * 2).
    """
    bold_on = r"\b " if bold else ""
    bold_off = r"\b0 " if bold else ""
    # Escape backslash and braces in text
    safe = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    # Replace actual newlines with RTF line break
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


def _make_color(r: float, g: float, b: float, a: float = 1.0) -> pp7.Color:
    c = pp7.Color()
    c.red = r
    c.green = g
    c.blue = b
    c.alpha = a
    return c


def _make_size(w: float, h: float) -> pp7.Size:
    s = pp7.Size()
    s.width = w
    s.height = h
    return s


def _make_text_element(
    text: str,
    font_size_pt: int = 60,
    bold: bool = False,
    color: tuple = TEXT_WHITE,
) -> pp7.SlideElement:
    elem = pp7.SlideElement()
    elem.uuid.CopyFrom(_make_uuid(_new_uuid()))
    # Full-slide text box centered
    elem.position.x = 0.0
    elem.position.y = 0.0
    elem.position.width = SLIDE_WIDTH
    elem.position.height = SLIDE_HEIGHT
    elem.rtf_data = _build_rtf(text, font_size_pt=font_size_pt, bold=bold)
    return elem


def _make_slide(
    text: str,
    bg_color: tuple = BG_DARK,
    font_size_pt: int = 60,
    bold: bool = False,
) -> pp7.Slide:
    slide = pp7.Slide()
    slide.uuid.CopyFrom(_make_uuid(_new_uuid()))
    slide.size.CopyFrom(_make_size(SLIDE_WIDTH, SLIDE_HEIGHT))
    slide.background_color.CopyFrom(_make_color(*bg_color))
    slide.elements.append(
        _make_text_element(text, font_size_pt=font_size_pt, bold=bold)
    )
    return slide


def _make_cue(
    slide_text: str, bg_color: tuple = BG_DARK, font_size_pt: int = 60
) -> pp7.Cue:
    cue = pp7.Cue()
    cue.uuid.CopyFrom(_make_uuid(_new_uuid()))

    action = pp7.Action()
    action.uuid.CopyFrom(_make_uuid(_new_uuid()))

    slide_action = pp7.SlideType()
    pres_slide = pp7.PresentationSlide()
    pres_slide.base_slide.CopyFrom(
        _make_slide(slide_text, bg_color=bg_color, font_size_pt=font_size_pt)
    )
    slide_action.presentation.CopyFrom(pres_slide)
    action.slide.CopyFrom(slide_action)
    cue.actions.append(action)

    return cue


# ---------------------------------------------------------------------------
# CCLI metadata
# ---------------------------------------------------------------------------


def _apply_ccli(presentation: pp7.Presentation, meta: dict) -> None:
    presentation.ccli_number = str(meta.get("ccli_number", ""))
    presentation.title = meta.get("title", "")
    presentation.author = meta.get("author", "")
    presentation.copyright = meta.get("copyright", "")
    presentation.publisher = meta.get("publisher", "")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_song_presentation(
    title: str,
    slides: list[str],
    ccli_meta: dict = None,
    bg_color: tuple = BG_DARK,
    font_size_pt: int = 60,
) -> pp7.Presentation:
    """
    Build a PP7 Presentation for a worship song.

    Args:
        title:        Song title (used as presentation name)
        slides:       List of slide text strings (may contain \\n for line breaks)
        ccli_meta:    {ccli_number, title, author, copyright, publisher}
        bg_color:     RGBA tuple for slide background
        font_size_pt: Font size in points
    """
    pres = pp7.Presentation()
    pres.uuid.CopyFrom(_make_uuid(_new_uuid()))
    pres.name = title

    if ccli_meta:
        _apply_ccli(pres, {**ccli_meta, "title": title})

    for text in slides:
        pres.cues.append(_make_cue(text, bg_color=bg_color, font_size_pt=font_size_pt))

    return pres


def build_sermon_presentation(
    title: str,
    slides: list[str],
    bg_color: tuple = BG_BLACK,
    font_size_pt: int = 54,
) -> pp7.Presentation:
    """Build a PP7 Presentation for sermon point slides."""
    pres = pp7.Presentation()
    pres.uuid.CopyFrom(_make_uuid(_new_uuid()))
    pres.name = title

    for text in slides:
        pres.cues.append(_make_cue(text, bg_color=bg_color, font_size_pt=font_size_pt))

    return pres


def save_presentation(presentation: pp7.Presentation, path: str) -> str:
    """Serialize to .pro file. Returns the path written."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(presentation.SerializeToString())
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
        if item.get("item_type") != "song":
            continue

        title = item.get("title", "unknown")
        song = item.get("song", {})

        # Collect all formatted slide texts from all sections
        all_slides = []
        for section in song.get("sections", []):
            all_slides.extend(section.get("slides", []))

        if not all_slides:
            print(f"  Skipping '{title}' — no slides generated yet")
            continue

        ccli_meta = {
            "ccli_number": song.get("ccli_number", ""),
            "author": song.get("author", ""),
            "copyright": song.get("copyright", ""),
            "publisher": "",
        }

        pres = build_song_presentation(title, all_slides, ccli_meta=ccli_meta)
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
        path = os.path.join(output_dir, f"{safe_title}.pro")
        save_presentation(pres, path)
        saved.append(path)

    return saved
