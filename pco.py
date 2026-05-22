"""
SermonFlow — Planning Center Online API client.

Auth: HTTP Basic with PAT (app_id + secret).
Export PCO_ID and PCO_SECRET in your shell (e.g. ~/.zshrc).
"""

import os
import json
from datetime import date, datetime, timedelta, timezone
import requests

BASE_URL = "https://api.planningcenteronline.com"
APP_ID = os.environ.get("PCO_ID") or exit("PCO_ID not set in environment")
SECRET = os.environ.get("PCO_SECRET") or exit("PCO_SECRET not set in environment")
AUTH = (APP_ID, SECRET)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _get(path: str, params: dict = None) -> dict:
    # Accept full URLs (from pagination links) or bare paths
    url = path if path.startswith("http") else BASE_URL + path
    resp = requests.get(url, auth=AUTH, params=params)
    if not resp.ok:
        print(f"HTTP {resp.status_code}: {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json()


def _get_all(path: str, params: dict = None) -> list:
    """Fetch every page and return the combined data list."""
    params = dict(params or {})
    params.setdefault("per_page", 100)
    results = []
    while path:
        payload = _get(path, params)
        data = payload.get("data", [])
        if isinstance(data, list):
            results.extend(data)
        elif isinstance(data, dict):
            results.append(data)
        path = payload.get("links", {}).get("next")
        params = {}  # next link already encodes params
    return results


def _get_all_with_included(path: str, params: dict = None) -> tuple[list, dict]:
    """Fetch every page and return (data_list, included_index).
    included_index keys are (type, id) tuples.
    """
    params = dict(params or {})
    params.setdefault("per_page", 100)
    results = []
    included = {}
    while path:
        payload = _get(path, params)
        data = payload.get("data", [])
        if isinstance(data, list):
            results.extend(data)
        elif isinstance(data, dict):
            results.append(data)
        for obj in payload.get("included", []):
            included[(obj["type"], obj["id"])] = obj
        path = payload.get("links", {}).get("next")
        params = {}
    return results, included


# ---------------------------------------------------------------------------
# Service types
# ---------------------------------------------------------------------------


def get_service_types() -> list:
    return _get_all("/services/v2/service_types")


def find_service_type(name_fragment: str) -> dict | None:
    fragment = name_fragment.lower()
    for st in get_service_types():
        if fragment in st["attributes"]["name"].lower():
            return st
    return None


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


def get_future_plans(service_type_id: str) -> list:
    return _get_all(
        f"/services/v2/service_types/{service_type_id}/plans",
        {"filter": "future", "order": "sort_date"},
    )


def get_next_sunday_plan(service_type_id: str) -> dict | None:
    plans = get_future_plans(service_type_id)
    if not plans:
        return None

    today = date.today()
    days_until_sunday = (6 - today.weekday()) % 7 or 7
    next_sunday = today + timedelta(days=days_until_sunday)

    for plan in plans:
        sort_date_str = plan["attributes"].get("sort_date", "")
        if sort_date_str:
            plan_date = date.fromisoformat(sort_date_str[:10])
            if plan_date >= next_sunday:
                return plan

    return plans[0]


def get_plan(service_type_id: str, plan_id: str) -> dict:
    return _get(f"/services/v2/service_types/{service_type_id}/plans/{plan_id}")


# ---------------------------------------------------------------------------
# Plan items
# ---------------------------------------------------------------------------


def get_plan_items(service_type_id: str, plan_id: str) -> list:
    return _get_all(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items",
        {"include": "song,arrangement,key", "order": "sequence"},
    )


def extract_songs(items: list) -> list:
    return [i for i in items if i["attributes"].get("item_type") == "song"]


# ---------------------------------------------------------------------------
# Arrangements & sections (lyrics)
# ---------------------------------------------------------------------------


def get_song_arrangements(song_id: str) -> list:
    return _get_all(f"/services/v2/songs/{song_id}/arrangements")


def get_arrangement_sections(song_id: str, arrangement_id: str) -> list:
    return _get_all(
        f"/services/v2/songs/{song_id}/arrangements/{arrangement_id}/sections"
    )


def get_song_lyrics(song_id: str, arrangement_id: str = None) -> list[dict]:
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
# Service schema
# ---------------------------------------------------------------------------


def _infer_section_type(label: str) -> str:
    l = label.lower()
    if "verse" in l:
        return "verse"
    if "pre" in l:
        return "pre_chorus"  # must precede "chorus"
    if "chorus" in l:
        return "chorus"
    if "bridge" in l:
        return "bridge"
    if "intro" in l:
        return "intro"
    if "outro" in l:
        return "outro"
    if "tag" in l:
        return "tag"
    return "other"


def build_service_schema(
    service_type_name: str = "*Weekend Services",
    save_path: str = "service_schema.json",
) -> dict:
    """
    Fetch next Sunday's plan and build the canonical SermonFlow service schema.
    Saves to save_path as JSON (pass save_path=None to skip).
    """
    service_type = find_service_type(service_type_name)
    if service_type is None:
        raise ValueError(f"No service type matching '{service_type_name}'")

    st_id = service_type["id"]
    plan = get_next_sunday_plan(st_id)
    if plan is None:
        raise ValueError("No future plans found")

    plan_id = plan["id"]
    plan_attrs = plan["attributes"]

    items_data, included = _get_all_with_included(
        f"/services/v2/service_types/{st_id}/plans/{plan_id}/items",
        {"include": "song,arrangement,key", "order": "sequence"},
    )

    schema_items = []
    for item in sorted(items_data, key=lambda x: x["attributes"].get("sequence", 0)):
        attrs = item["attributes"]
        item_type = attrs.get("item_type", "item")

        entry = {
            "sequence": attrs.get("sequence", 0),
            "item_id": item["id"],
            "item_type": item_type,
            "title": attrs.get("title", ""),
            "description": attrs.get("description", ""),
            "length_secs": attrs.get("length", 0),
            "slides_to_generate": [],
        }

        if item_type == "song":
            song_rel = item["relationships"].get("song", {}).get("data")
            arr_rel = item["relationships"].get("arrangement", {}).get("data")

            song_obj = included.get(("Song", song_rel["id"])) if song_rel else None
            arr_obj = included.get(("Arrangement", arr_rel["id"])) if arr_rel else None

            song_attrs = song_obj["attributes"] if song_obj else {}
            arr_attrs = arr_obj["attributes"] if arr_obj else {}

            song_id = song_rel["id"] if song_rel else None
            arr_id = arr_rel["id"] if arr_rel else None

            sections_raw = (
                get_arrangement_sections(song_id, arr_id)
                if (song_id and arr_id)
                else []
            )
            sections = [
                {
                    "section_id": s["id"],
                    "label": s["attributes"].get("label", ""),
                    "section_type": _infer_section_type(
                        s["attributes"].get("label", "")
                    ),
                    "lyrics": s["attributes"].get("lyrics", ""),
                    "slides": [],
                }
                for s in sections_raw
                if isinstance(s, dict)
            ]

            entry["song"] = {
                "song_id": song_id,
                "ccli_number": song_attrs.get("ccli_number", ""),
                "author": song_attrs.get("author", ""),
                "copyright": song_attrs.get("copyright", ""),
                "arrangement": {
                    "arrangement_id": arr_id,
                    "name": arr_attrs.get("name", ""),
                    "chord_chart_key": arr_attrs.get("chord_chart_key", ""),
                    "sequence": arr_attrs.get("sequence", ""),
                },
                "sections": sections,
            }

        schema_items.append(entry)

    schema = {
        "service": {
            "plan_id": plan_id,
            "service_type_id": st_id,
            "plan_title": plan_attrs.get("title") or plan_attrs.get("dates", ""),
            "plan_date": plan_attrs.get("sort_date", ""),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "items": schema_items,
    }

    if save_path:
        with open(save_path, "w") as f:
            json.dump(schema, f, indent=2)
        print(f"Schema saved to {save_path}")

    return schema


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

    st = service_types[0]
    st_id = st["id"]
    print(f"\nUsing: {st['attributes']['name']} (id={st_id})")

    print("\n=== Building Service Schema ===")
    schema = build_service_schema(
        service_type_name=st["attributes"]["name"].split()[0].lower(),
        save_path="service_schema.json",
    )

    svc = schema["service"]
    print(f"  Plan: {svc['plan_title']} on {svc['plan_date'][:10]}")
    print(f"  Items: {len(schema['items'])}")
    for item in schema["items"]:
        marker = "♪" if item["item_type"] == "song" else " "
        print(
            f"  {marker} seq={item['sequence']:>3}  {item['item_type']:<10}  {item['title']}"
        )
        if item["item_type"] == "song":
            for sec in item.get("song", {}).get("sections", []):
                print(
                    f"       [{sec['label']}] {sec['lyrics'][:60]}{'...' if len(sec['lyrics']) > 60 else ''}"
                )

    print("\nDone.")
