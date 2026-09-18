"""
Deterministic formatting helpers.

Numbers in the target template use the Indian digit-grouping style
(e.g. 4,98,67,640 and 47,50,000). We compute this in Python rather than
trusting the LLM to get comma placement right on every run.
"""
from __future__ import annotations

NOT_VISIBLE = "Not visible in screenshots"


def indian_format(n) -> str | None:
    if n is None:
        return None
    try:
        n = int(round(float(n)))
    except (TypeError, ValueError):
        return None
    sign = "-" if n < 0 else ""
    n = abs(n)
    s = str(n)
    if len(s) <= 3:
        return sign + s
    last3 = s[-3:]
    rest = s[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return sign + ",".join(parts) + "," + last3


def line(label_emoji: str, label: str, value) -> str:
    if value is None or value == "":
        value = NOT_VISIBLE
    return f"{label_emoji} {label}: {value}"


def stat_line(emoji: str, label: str, value) -> str:
    if value is None:
        return f"{emoji} {label}: {NOT_VISIBLE}"
    return f"{emoji} {label}: {value}"


def count_line(emoji: str, value, noun: str) -> str | None:
    """Used for the Collection Stats block (e.g. '🌈 67 Shiny Pokémon')."""
    if value is None:
        return f"{emoji} {NOT_VISIBLE} — {noun}"
    return f"{emoji} {value} {noun}"


DIVIDER = "━━━━━━━━━━━━━━━━━━"


def build_description(stats: dict, narrative: str, missing_fields: list[str]) -> str:
    level = stats.get("level")
    header_level = f"LEVEL {level} ACCOUNT" if level is not None else "LEVEL — ACCOUNT"

    shiny = stats.get("shiny_count")
    legendary = stats.get("legendary_count")
    mythical = stats.get("mythical_count")
    shadow = stats.get("shadow_count")
    purified = stats.get("purified_count")

    def n(v):
        return v if v is not None else "?"

    top_banner = (
        f"🌈 {n(shiny)} Shinies • 👑 {n(legendary)} Legendaries • 💎 {n(mythical)} Mythicals • "
        f"🔥 {n(shadow)} Shadows • 🛡️ {n(purified)} Purified Pokémon ⚡"
    )

    overview_lines = [
        stat_line("⭐", "Trainer Level", level),
        stat_line("📅", "Start Date", stats.get("start_date")),
        stat_line("📈", "Total XP", indian_format(stats.get("total_xp"))),
        stat_line(
            "🎯",
            "XP Progress",
            (
                f"{indian_format(stats.get('xp_progress_current'))} / "
                f"{indian_format(stats.get('xp_progress_target'))}"
                if stats.get("xp_progress_current") is not None
                and stats.get("xp_progress_target") is not None
                else None
            ),
        ),
        stat_line("⚡", "Stardust", indian_format(stats.get("stardust"))),
        stat_line("🪙", "PokéCoins", indian_format(stats.get("pokecoins"))),
        stat_line("🐾", "Pokémon Caught", indian_format(stats.get("pokemon_caught"))),
        stat_line("🗺️", "PokéStops Visited", indian_format(stats.get("pokestops_visited"))),
        stat_line(
            "🚶",
            "Distance Walked",
            f"{stats['distance_walked_km']} km" if stats.get("distance_walked_km") is not None else None,
        ),
        stat_line(
            "🎒",
            "Pokémon Storage",
            (
                f"{stats.get('pokemon_storage_current')}/{stats.get('pokemon_storage_max')}"
                if stats.get("pokemon_storage_current") is not None
                and stats.get("pokemon_storage_max") is not None
                else None
            ),
        ),
        stat_line(
            "🎁",
            "Item Storage",
            (
                f"{stats.get('item_storage_current')}/{stats.get('item_storage_max')}"
                if stats.get("item_storage_current") is not None
                and stats.get("item_storage_max") is not None
                else None
            ),
        ),
    ]

    collection_lines = [
        count_line("🌈", shiny, "Shiny Pokémon"),
        count_line("👑", legendary, "Legendary Pokémon"),
        count_line("💎", mythical, "Mythical Pokémon"),
        count_line("🔥", shadow, "Shadow Pokémon"),
        count_line("🛡️", purified, "Purified Pokémon"),
        count_line("🍀", stats.get("lucky_count"), "Lucky Pokémon"),
        count_line("🎯", stats.get("iv100_count"), "100% IV Pokémon"),
        count_line("🥚", stats.get("hatched_count"), "Hatched Pokémon"),
        count_line("🎉", stats.get("event_count"), "Event Pokémon"),
        count_line("🧬", stats.get("mega_count"), "Mega-Evolvable Pokémon"),
        count_line("⚡", stats.get("dynamax_count"), "Dynamax Pokémon"),
        count_line("🌍", stats.get("location_bg_count"), "Location Background Pokémon"),
        count_line("❄️", stats.get("special_bg_count"), "Special Background Pokémon"),
    ]

    rare = stats.get("rare_pokemon") or []
    tag_emoji = {
        "shiny": "✨",
        "legendary": "👑",
        "mythical": "💎",
        "shadow": "🔥",
        "purified": "🛡️",
        "lucky": "🍀",
    }
    if rare:
        rare_lines = []
        for p in rare:
            emoji = tag_emoji.get((p.get("tag") or "").lower(), "⭐")
            cp = p.get("cp")
            cp_txt = f" (CP {cp})" if cp is not None else " (CP not visible)"
            rare_lines.append(f"{emoji} {p.get('name', 'Unknown')}{cp_txt}")
        rare_block = "\n".join(rare_lines)
    else:
        rare_block = f"⚠️ {NOT_VISIBLE} — no rare/featured Pokémon could be read from the images."

    items = stats.get("items") or []
    if items:
        item_lines = []
        for it in items:
            qty = it.get("qty")
            qty_txt = f"×{qty}" if qty is not None else "(qty not visible)"
            item_lines.append(f"🔹 {it.get('name', 'Unknown item')} {qty_txt}")
        items_block = "\n".join(item_lines)
    else:
        items_block = f"⚠️ {NOT_VISIBLE} — no item/resource screen could be read from the images."

    why_buy = ["✅ Complete screenshot proof included"]
    if level is not None:
        why_buy.append(f"✅ Level {level} Account Ready for Progression")
    if shiny is not None:
        why_buy.append(f"✅ {shiny} Shiny Pokémon Included")
    if legendary is not None:
        why_buy.append(f"✅ {legendary} Legendary Pokémon Collection")
    if mythical is not None:
        why_buy.append(f"✅ {mythical} Mythical Pokémon")
    if shadow is not None:
        why_buy.append(f"✅ {shadow} Shadow Pokémon")
    if purified is not None:
        why_buy.append(f"✅ {purified} Purified Pokémon")
    why_buy.append("✅ Excellent Account for Collectors and Players")

    missing_note = ""
    if missing_fields:
        missing_note = (
            "\n\n⚠️ NOTE: The following details were not clearly visible in your "
            "screenshots and were left out rather than guessed:\n- "
            + "\n- ".join(missing_fields)
        )

    parts = [
        "🔥 POKÉMON GO ACCOUNT ON SALE 🔥",
        "",
        f"⚡ {header_level} ⚡",
        top_banner,
        "",
        narrative.strip(),
        "",
        DIVIDER,
        "",
        "🏆 ACCOUNT OVERVIEW",
        "",
        DIVIDER,
        *overview_lines,
        "",
        DIVIDER,
        "",
        "✨ COLLECTION STATS",
        "",
        DIVIDER,
        *collection_lines,
        "",
        DIVIDER,
        "",
        "🔥 RARE & FEATURED POKÉMON",
        "",
        DIVIDER,
        rare_block,
        "",
        DIVIDER,
        "",
        "⚡ ITEMS & RESOURCES",
        "",
        DIVIDER,
        stat_line("💎", "Stardust", indian_format(stats.get("stardust"))),
        stat_line("🪙", "PokéCoins", indian_format(stats.get("pokecoins"))),
        items_block,
        "",
        DIVIDER,
        "",
        "💥 WHY BUY THIS ACCOUNT?",
        "",
        DIVIDER,
        *why_buy,
        "",
        "🔥 ACCOUNT ON SALE — SERIOUS BUYERS ONLY! 🔥",
        "",
        "📌 Complete screenshot proof included.",
        missing_note,
    ]
    return "\n".join(p for p in parts if p is not None)
