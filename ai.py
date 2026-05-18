"""
SermonFlow — AI formatting layer (Claude API).

Two tasks:
  1. format_lyric_slides()   — break lyric sections into display slides
  2. generate_sermon_slides() — turn yellow-highlighted sermon notes into slides

Environment variable required:
  ANTHROPIC_API_KEY
"""

import os
import json
import anthropic

MODEL = "claude-sonnet-4-6"

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY") or exit(
            "ANTHROPIC_API_KEY not set"
        )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# System prompts (cached — same prompt reused across calls in a session)
# ---------------------------------------------------------------------------

_LYRIC_SYSTEM = """\
You are a worship slide formatter for a Sunday morning church service.
Your job is to break lyric sections into individual display slides.

Rules:
- Each slide shows 1–2 lines of lyrics
- Break at natural phrase or breath points — never mid-phrase or mid-thought
- Keep rhyming couplets together on the same slide when possible
- Max ~55 characters per line for screen readability
- Preserve the original lyrics exactly — no paraphrasing
- Label each slide as "Section (n/total)" e.g. "Verse 1 (1/3)"

Return ONLY valid JSON, no markdown fences:
{"slides": [{"text": "line1\\nline2", "section_label": "Verse 1 (1/2)"}]}"""

_SERMON_SYSTEM = """\
You are a sermon slide formatter for a Sunday morning church service.
Your job is to turn the pastor's highlighted sermon notes into clean display slides.

Rules:
- One slide per highlight
- Clean up capitalization and punctuation for screen display
- Keep it concise — slides are visual anchors, not full sentences
- Preserve the key word or phrase the pastor highlighted
- If a highlight is too long for one slide, split it naturally

Return ONLY valid JSON, no markdown fences:
{"slides": [{"text": "slide text here"}]}"""


def _parse_json_response(raw: str) -> dict:
    text = raw.strip()
    # Strip markdown code fences if the model adds them anyway
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# Lyric slide formatter
# ---------------------------------------------------------------------------


def format_lyric_slides(song_title: str, sections: list[dict]) -> list[dict]:
    """
    Break lyric sections into display slides.

    Args:
        song_title: e.g. "Amazing Grace"
        sections:   [{label, lyrics}, ...]  from pco.get_song_lyrics()

    Returns:
        [{text, section_label}, ...]
    """
    if not sections:
        return []

    sections_text = "\n\n".join(f"[{s['label']}]\n{s['lyrics']}" for s in sections)
    prompt = f"Song: {song_title}\n\n{sections_text}"

    msg = _get_client().messages.create(
        model=MODEL,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": _LYRIC_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": prompt}],
    )

    result = _parse_json_response(msg.content[0].text)
    slides = result.get("slides", [])
    print(f"  Formatted '{song_title}' → {len(slides)} slides")
    return slides


# ---------------------------------------------------------------------------
# Sermon slide generator
# ---------------------------------------------------------------------------


def generate_sermon_slides(highlights: list[str]) -> list[dict]:
    """
    Generate sermon slides from yellow-highlighted pastor notes.

    Args:
        highlights: list of strings from gdocs.get_sermon_highlights()

    Returns:
        [{text}, ...]
    """
    if not highlights:
        return []

    prompt = "Pastor's highlighted sermon notes:\n" + "\n".join(
        f"{i+1}. {h}" for i, h in enumerate(highlights)
    )

    msg = _get_client().messages.create(
        model=MODEL,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": _SERMON_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": prompt}],
    )

    result = _parse_json_response(msg.content[0].text)
    slides = result.get("slides", [])
    print(f"  Generated {len(slides)} sermon slides from {len(highlights)} highlights")
    return slides


# ---------------------------------------------------------------------------
# Attach AI slides into the service schema
# ---------------------------------------------------------------------------


def format_schema_slides(schema: dict) -> dict:
    """
    Walk the service schema and populate slides[] on every song section
    using format_lyric_slides(). Returns the mutated schema.
    """
    for item in schema.get("items", []):
        if item.get("item_type") != "song":
            continue

        song = item.get("song", {})
        title = item.get("title", "")
        sections = song.get("sections", [])
        if not sections:
            continue

        print(f"Formatting lyrics: {title}")
        formatted = format_lyric_slides(title, sections)

        # Distribute formatted slides back into sections by section_label prefix
        for slide in formatted:
            label = slide.get("section_label", "")
            # Match to the section whose label is a prefix of the slide label
            for section in sections:
                if section["label"] and label.startswith(section["label"]):
                    section["slides"].append(slide["text"])
                    break
            else:
                # Fallback: append to last section
                if sections:
                    sections[-1]["slides"].append(slide["text"])

    return schema


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Lyric formatter smoke-test ===")
    test_sections = [
        {
            "label": "Verse 1",
            "lyrics": "Amazing grace how sweet the sound\nThat saved a wretch like me\nI once was lost but now am found\nWas blind but now I see",
        },
        {
            "label": "Chorus",
            "lyrics": "My chains are gone I've been set free\nMy God my Savior has ransomed me\nAnd like a flood His mercy reigns\nUnending love amazing grace",
        },
    ]
    slides = format_lyric_slides("Amazing Grace", test_sections)
    for s in slides:
        print(f"\n  [{s.get('section_label','')}]")
        print(f"  {s['text']}")

    print("\n=== Sermon slide smoke-test ===")
    test_highlights = [
        "God's grace is sufficient for every need",
        "We are justified by faith not by works",
        "The peace that passes all understanding",
    ]
    sermon_slides = generate_sermon_slides(test_highlights)
    for s in sermon_slides:
        print(f"  • {s['text']}")
