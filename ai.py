"""
SermonFlow — AI formatting layer (Claude API).

Task:
  generate_sermon_slides() — turn yellow-highlighted sermon notes into slides

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
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Sermon slide smoke-test ===")
    test_highlights = [
        "God's grace is sufficient for every need",
        "We are justified by faith not by works",
        "The peace that passes all understanding",
    ]
    sermon_slides = generate_sermon_slides(test_highlights)
    for s in sermon_slides:
        print(f"  • {s['text']}")
