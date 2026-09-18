"""
All AI calls go through Groq — vision extraction (OCR-style stat reading from
screenshots) and a short grounded narrative. Nothing is guessed: the vision
prompt explicitly requires null for anything not clearly legible, and the
narrative prompt is only given the already-extracted, verified data.
"""
from __future__ import annotations

import base64
import json
import logging

from groq import Groq

import config

logger = logging.getLogger(__name__)
_client = Groq(api_key=config.GROQ_API_KEY)

SCHEMA_FIELDS = [
    "level", "start_date", "total_xp", "xp_progress_current", "xp_progress_target",
    "stardust", "pokecoins", "pokemon_caught", "pokestops_visited", "distance_walked_km",
    "pokemon_storage_current", "pokemon_storage_max", "item_storage_current", "item_storage_max",
    "shiny_count", "legendary_count", "mythical_count", "shadow_count", "purified_count",
    "lucky_count", "iv100_count", "hatched_count", "event_count", "mega_count",
    "dynamax_count", "location_bg_count", "special_bg_count",
]

VISION_SYSTEM_PROMPT = f"""You are an OCR and data-extraction engine for Pokémon GO account screenshots.
Look ONLY at what is literally visible in the image. Extract a JSON object with these possible fields:

{json.dumps(SCHEMA_FIELDS, indent=2)}

Plus:
- "rare_pokemon": array of {{"name": str, "cp": int or null, "tag": one of
  ["shiny","legendary","mythical","shadow","purified","lucky","other"]}} for any
  individual Pokémon entries visible (e.g. a Pokémon list/box screen).
- "items": array of {{"name": str, "qty": int or null}} for any bag/item screen entries.

STRICT RULES:
- If a value is not clearly and legibly visible in THIS image, set it to null. Do not estimate,
  infer, round, or guess ANY number or text.
- Only include a Pokémon in "rare_pokemon" if its name is actually readable in this image.
- Only include an item in "items" if its name is actually readable in this image.
- Do not invent Pokémon, items, or stats that are not in this specific screenshot.
- Output ONLY the JSON object. No commentary, no markdown fences.
"""

NARRATIVE_SYSTEM_PROMPT = """You write a short, punchy 2-4 sentence marketing paragraph for a
Pokémon GO account sale listing, in the style of a premium account marketplace.

You will be given verified, already-extracted account data as JSON. You MUST NOT invent any
Pokémon, stat, or number that is not present in that JSON. You may only reference Pokémon names
that appear in the "rare_pokemon" list, and only mention stats that are non-null in the JSON.
If the JSON has very little data, keep the paragraph short and general (e.g. mention it's a
collector-ready account) without fabricating specifics. Do not use markdown. Output only the
paragraph text, nothing else."""


def _image_to_data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def extract_stats_from_image(image_bytes: bytes) -> dict:
    """Send a single screenshot to the Groq vision model and return parsed JSON."""
    data_url = _image_to_data_url(image_bytes)
    try:
        completion = _client.chat.completions.create(
            model=config.VISION_MODEL,
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract the JSON object for this Pokémon GO screenshot.",
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            temperature=0.1,
            max_completion_tokens=1500,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content
        return json.loads(raw)
    except Exception:
        logger.exception("Vision extraction failed for one screenshot")
        return {}


def merge_stats(extractions: list[dict]) -> dict:
    """Combine per-image extractions into one stats dict. First non-null value wins
    for scalar fields; list fields (rare_pokemon, items) are deduplicated by name."""
    merged: dict = {k: None for k in SCHEMA_FIELDS}
    rare_by_name: dict[str, dict] = {}
    items_by_name: dict[str, dict] = {}

    for ext in extractions:
        if not isinstance(ext, dict):
            continue
        for key in SCHEMA_FIELDS:
            if merged.get(key) is None and ext.get(key) is not None:
                merged[key] = ext.get(key)

        for p in ext.get("rare_pokemon", []) or []:
            name = (p.get("name") or "").strip()
            if not name:
                continue
            existing = rare_by_name.get(name.lower())
            if existing is None or (p.get("cp") and not existing.get("cp")):
                rare_by_name[name.lower()] = {
                    "name": name,
                    "cp": p.get("cp"),
                    "tag": p.get("tag", "other"),
                }

        for it in ext.get("items", []) or []:
            name = (it.get("name") or "").strip()
            if not name:
                continue
            existing = items_by_name.get(name.lower())
            if existing is None or (it.get("qty") and not existing.get("qty")):
                items_by_name[name.lower()] = {"name": name, "qty": it.get("qty")}

    merged["rare_pokemon"] = list(rare_by_name.values())
    merged["items"] = list(items_by_name.values())
    return merged


FIELD_LABELS = {
    "level": "Trainer Level",
    "start_date": "Start Date",
    "total_xp": "Total XP",
    "xp_progress_current": "XP Progress",
    "xp_progress_target": "XP Progress target",
    "stardust": "Stardust",
    "pokecoins": "PokéCoins",
    "pokemon_caught": "Pokémon Caught",
    "pokestops_visited": "PokéStops Visited",
    "distance_walked_km": "Distance Walked",
    "pokemon_storage_current": "Pokémon Storage",
    "item_storage_current": "Item Storage",
    "shiny_count": "Shiny Pokémon count",
    "legendary_count": "Legendary Pokémon count",
    "mythical_count": "Mythical Pokémon count",
    "shadow_count": "Shadow Pokémon count",
    "purified_count": "Purified Pokémon count",
}


def missing_fields_list(stats: dict) -> list[str]:
    out = []
    for key, label in FIELD_LABELS.items():
        if stats.get(key) is None:
            out.append(label)
    if not stats.get("rare_pokemon"):
        out.append("Rare/Featured Pokémon list")
    if not stats.get("items"):
        out.append("Items & Resources list")
    return out


def generate_narrative(stats: dict) -> str:
    payload = {
        "level": stats.get("level"),
        "stardust": stats.get("stardust"),
        "shiny_count": stats.get("shiny_count"),
        "legendary_count": stats.get("legendary_count"),
        "mythical_count": stats.get("mythical_count"),
        "shadow_count": stats.get("shadow_count"),
        "rare_pokemon": stats.get("rare_pokemon", []),
    }
    try:
        completion = _client.chat.completions.create(
            model=config.TEXT_MODEL,
            messages=[
                {"role": "system", "content": NARRATIVE_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            temperature=0.6,
            max_completion_tokens=250,
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        logger.exception("Narrative generation failed")
        return "This account is ready for its next trainer, with the collection detailed below."
