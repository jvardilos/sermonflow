"""
SermonFlow — Planning Center Online API client.

Auth: HTTP Basic with PAT (app_id + secret).
Set PCO_APP_ID and PCO_SECRET in a .env file or environment.
"""

import os
from datetime import date, timedelta
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.planningcenteronline.com"
APP_ID = os.environ["PCO_APP_ID"]
SECRET = os.environ["PCO_SECRET"]
AUTH = (APP_ID, SECRET)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(path: str, params: dict = None) -> dict:
    url = BASE_URL + path
    resp = requests.get(url, auth=AUTH, params=params)
    resp.raise_for_status()
    return resp.json()


def _get_all(path: str, params: dict = None) -> list:
    """Fetch every page and return the combined data list."""
    params = dict(params or {})
    params.setdefault("per_page", 100)
    results = []
    while path:
        payload = _get(path, params)
        results.extend(payload.get("data", []))
        path = payload.get("links", {}).get("next")
        params = {}          # next link already encodes params
    return results


# ---------------------------------------------------------------------------
# Service types
# ---------------------------------------------------------------------------

def get_service_types() -> list:
    """Return all service types."""
    return _get_all("/services/v2/service_types")


def find_service_type(name_fragment: str) -> dict | None:
    """Return the first service type whose name contains name_fragment (case-insensitive)."""
    fragment = name_fragment.lower()
    for st in get_service_types():
        if fragment in st["attributes"]["name"].lower():
            return st
    return None


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

def get_future_plans(service_type_id: str) -> list:
    """Return upcoming plans for a service type, sorted ascending."""
    return _get_all(
        f"/services/v2/service_types/{service_type_id}/plans",
        {"filter": "future", "order": "sort_date"},
    )


def get_next_sunday_plan(service_type_id: str) -> dict | None:
    """Return the plan whose sort_date falls on the next Sunday (or the nearest future plan)."""
    plans = get_future_plans(service_type_id)
    if not plans:
        return None

    today = date.today()
    days_until_sunday = (6 - today.weekday()) % 7 or 7   # weekday: Mon=0 Sun=6
    next_sunday = today + timedelta(days=days_until_sunday)

    for plan in plans:
        sort_date_str = plan["attributes"].get("sort_date", "")
        if sort_date_str:
            plan_date = date.fromisoformat(sort_date_str[:10])
            if plan_date >= next_sunday:
                return plan

    return plans[0]   # fallback: nearest future plan


def get_plan(service_type_id: str, plan_id: str) -> dict:
    return _get(f"/services/v2/service_types/{service_type_id}/plans/{plan_id}")


# ---------------------------------------------------------------------------
# Plan items
# ---------------------------------------------------------------------------

def get_plan_items(service_type_id: str, plan_id: str) -> list:
    """Return all items in service order, with songs included."""
    return _get_all(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items",
        {"include": "song", "order": "sequence"},
    )


def extract_songs(items: list) -> list:
    """Return only items that are songs, preserving service order."""
    return [i for i in items if i["attributes"].get("item_type") == "song"]


# ---------------------------------------------------------------------------
# Arrangements & sections (lyrics)
# ---------------------------------------------------------------------------

def get_song_arrangements(song_id: str) -> list:
    return _get_all(f"/services/v2/songs/{song_id}/arrangements")


def get_arrangement_sections(song_id: str, arrangement_id: str) -> list:
    """Return lyric sections in order for a given arrangement."""
    return _get_all(
        f"/services/v2/songs/{song_id}/arrangements/{arrangement_id}/sections"
    )


def get_song_lyrics(song_id: str, arrangement_id: str = None) -> list[dict]:
    """
    Return ordered lyric sections for a song.

    If arrangement_id is None the first (default) arrangement is used.
    Each returned dict: {label, lyrics}
    """
    arrangements = get_song_arrangements(song_id)
    if not arrangements:
        return []

    if arrangement_id is None:
        arrangement = arrangements[0]
    else:
        arrangement = next(
            (a for a in arrangements if a["id"] == arrangement_id), arrangements[0]
        )

    arrangement_id = arrangement["id"]
    sections = get_arrangement_sections(song_id, arrangement_id)
    return [
        {
            "label": s["attributes"].get("label", ""),
            "lyrics": s["attributes"].get("lyrics", ""),
        }
        for s in sections
    ]


# ---------------------------------------------------------------------------
# Convenience: full service snapshot
# ---------------------------------------------------------------------------

def get_service_snapshot(service_type_name: str = "sunday") -> dict:
    """
    High-level helper that returns a dict with:
      - service_type
      - plan
      - items  (all items in order)
      - songs  (song items with lyrics attached)
    """
    service_type = find_service_type(service_type_name)
    if service_type is None:
        raise ValueError(f"No service type matching '{service_type_name}' found.")

    st_id = service_type["id"]
    plan = get_next_sunday_plan(st_id)
    if plan is None:
        raise ValueError("No future plans found.")

    plan_id = plan["id"]
    items = get_plan_items(st_id, plan_id)
    song_items = extract_songs(items)

    # Attach lyrics to each song item
    for item in song_items:
        song_id = item["relationships"].get("song", {}).get("data", {}).get("id")
        if song_id:
            item["_lyrics"] = get_song_lyrics(song_id)
        else:
            item["_lyrics"] = []

    return {
        "service_type": service_type,
        "plan": plan,
        "items": items,
        "songs": song_items,
    }


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Service Types ===")
    service_types = get_service_types()
    for st in service_types:
        print(f"  [{st['id']}] {st['attributes']['name']}")

    if not service_types:
        print("No service types found — check your credentials.")
        raise SystemExit(1)

    # Use the first service type for the rest of the smoke-test
    st = service_types[0]
    st_id = st["id"]
    print(f"\nUsing service type: {st['attributes']['name']} (id={st_id})")

    print("\n=== Next Sunday Plan ===")
    plan = get_next_sunday_plan(st_id)
    if plan is None:
        print("No future plans found.")
        raise SystemExit(0)

    plan_attrs = plan["attributes"]
    print(f"  [{plan['id']}] {plan_attrs.get('title') or '(untitled)'} — {plan_attrs.get('sort_date', '')[:10]}")

    print("\n=== Plan Items ===")
    items = get_plan_items(st_id, plan["id"])
    for item in items:
        a = item["attributes"]
        print(f"  seq={a.get('sequence'):>3}  type={a.get('item_type','?'):<10}  {a.get('title','')}")

    print("\n=== Songs with Lyrics ===")
    song_items = extract_songs(items)
    if not song_items:
        print("  No song items in this plan.")
    for item in song_items[:1]:    # demo: first song only
        song_id = item["relationships"].get("song", {}).get("data", {}).get("id")
        print(f"  Song: {item['attributes'].get('title','')}  (song_id={song_id})")
        if song_id:
            lyrics = get_song_lyrics(song_id)
            for section in lyrics:
                print(f"\n    [{section['label']}]")
                print(f"    {section['lyrics'][:120]}{'...' if len(section['lyrics']) > 120 else ''}")

    print("\nDone.")
