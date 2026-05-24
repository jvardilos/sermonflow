"""
Decode a .pro file and print its contents.

Usage:
  python decode_pro.py <file.pro>           # text proto format (default)
  python decode_pro.py <file.pro> --json    # JSON format
  python decode_pro.py <file.pro> --slides  # slides-only summary
"""

import sys
import os

import pco_types  # registers pco_types/ on sys.path
import pco_types.presentation_pb2 as presentation_pb2
from google.protobuf import text_format, json_format


def load(path: str) -> presentation_pb2.Presentation:
    pres = presentation_pb2.Presentation()
    with open(path, "rb") as f:
        pres.ParseFromString(f.read())
    return pres


def print_text(pres: presentation_pb2.Presentation) -> None:
    print(text_format.MessageToString(pres))


def print_json(pres: presentation_pb2.Presentation) -> None:
    import json
    print(json.dumps(json_format.MessageToDict(pres), indent=2))


def print_slides(pres: presentation_pb2.Presentation) -> None:
    """Human-readable slide summary — titles and text only."""
    print(f"Presentation: {pres.name!r}  ({len(pres.cues)} cues)")
    for i, cue in enumerate(pres.cues):
        for action in cue.actions:
            which = action.WhichOneof("ActionTypeData")
            if which != "slide":
                print(f"  [{i}] (non-slide action: {which})")
                continue
            base = action.slide.presentation.base_slide
            texts = []
            for elem in base.elements:
                rtf = elem.element.text.rtf_data
                if rtf:
                    # strip RTF wrapper to show plain text approximation
                    raw = rtf.decode("utf-8", errors="replace")
                    # grab everything after the last } of the header groups
                    text_part = raw.rsplit("\\cf1 ", 1)[-1].rstrip("}")
                    texts.append(text_part.replace(r"\line ", "\n       "))
            bg = base.background_color
            draws = base.draws_background_color
            info_flags = [e.info for e in base.elements]
            print(f"  [{i}] draws_bg={draws}  bg=({bg.red:.2f},{bg.green:.2f},{bg.blue:.2f},{bg.alpha:.2f})  elem_info={info_flags}")
            for t in texts:
                print(f"       {t}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    path = args[0]
    mode = args[1] if len(args) > 1 else ""

    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)

    pres = load(path)

    if mode == "--json":
        print_json(pres)
    elif mode == "--slides":
        print_slides(pres)
    else:
        print_text(pres)
