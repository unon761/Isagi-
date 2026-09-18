"""
Isagi Bot — Pokémon GO account listing generator.

Run with:  python bot.py
"""
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import db
import groq_client
from formatting import build_description

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO
)
logger = logging.getLogger("isagi_bot")

# user_id -> list[bytes] pending screenshot images (in-memory queue)
PENDING_PHOTOS: dict[int, list[bytes]] = {}

WELCOME_TEXT = (
    "👋 Welcome to the Pokémon GO Description / Isagi bot ! 👋\n\n"
    "I generate premium, high-converting Pokémon GO account sale listings from "
    "your in-game screenshots !\n\n"
    "🎁 Your Balance: You have {trials} free trial generations!\n\n"
    "🚀 How to use: \n"
    "1. Upload one or more screenshots of your Pokémon GO account.\n"
    "2. I will queue them up.\n"
    "3. Send /generate when you are ready.\n\n"
    "Send /help to see all commands!"
)

HELP_TEXT = (
    "🤖 ISAGI BOT — COMMANDS\n\n"
    "📸 Send screenshots any time — I queue them automatically.\n\n"
    "/generate — Generate a description from your queued screenshots (4 coins)\n"
    "/clear — Clear all queued screenshots\n"
    "/balance — Show your coins, free trials and subscription status\n"
    "/pricing — Show coin and premium plan pricing\n"
    "/help — Show this message\n"
)

ADMIN_HELP_TEXT = (
    "\n👑 ADMIN COMMANDS\n\n"
    "/addcoins <id> <amount> — Add coins to any user\n"
    "/removecoins <id> <amount> — Remove coins (floors at 0)\n"
    "/addsub <id> [plan] — Grant a subscription "
    "(plan: 1day, 3day, 7day, 15day, 31day, 365day — default 31day)\n"
    "/removesub <id> — Expire a subscription immediately\n"
    "/userinfo <id> — Full profile: coins, sub status, description history\n"
)

PRICING_TEXT = (
    "💸 ISAGI BOT — POKÉMON GO DESCRIPTION PRICING\n\n"
    "🎮 STANDARD DESCRIPTION COSTS\n"
    "• 1 Description: 4 Coins (₹10)\n\n"
    "🪙 COIN EXCHANGE RATE\n"
    "• 1 Isagi Coin = ₹2.5 INR\n\n"
    "👑 PREMIUM PLANS\n"
    "Get access to premium features with unlimited description generations!\n\n"
    "⚡ 1-Day Premium: ₹49\n"
    "🚀 3-Day Premium: ₹79\n"
    "🔥 7-Day Premium: ₹149\n"
    "💎 15-Day Premium: ₹259\n"
    "👑 31-Day Premium: ₹499\n"
    "🏆 365-Day Premium: ₹799\n\n"
    "💳 HOW TO BUY / ACTIVATE\n"
    "Contact the owner directly:\n\n"
    f"👤 Owner: {config.OWNER_CONTACT}\n\n"
    "🤖 Bot: Isagi Bot\n"
    "🎯 Pokémon GO Description Generator\n"
    "✨ Fast • Accurate • Easy to Use"
)


def is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


# --------------------------------------------------------------------------
# Basic commands
# --------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username)
    row = db.get_user(user.id)
    await update.message.reply_text(WELCOME_TEXT.format(trials=row["free_trials"]))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = HELP_TEXT
    if is_admin(update.effective_user.id):
        text += ADMIN_HELP_TEXT
    await update.message.reply_text(text)


async def cmd_pricing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(PRICING_TEXT)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username)
    row = db.get_user(user.id)
    lines = [
        f"🪙 Coins: {row['coins']}",
        f"🎁 Free trials left: {row['free_trials']}",
    ]
    if db.is_sub_active(row):
        lines.append(
            f"👑 Premium active ({row['sub_plan']}) until {db.fmt_expiry(row['sub_expiry'])}"
        )
    else:
        lines.append("👑 Premium: not active")
    queued = len(PENDING_PHOTOS.get(user.id, []))
    lines.append(f"📸 Screenshots queued: {queued}")
    await update.message.reply_text("\n".join(lines))


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    PENDING_PHOTOS.pop(user_id, None)
    await update.message.reply_text("🗑️ Cleared. All queued screenshots were removed.")


# --------------------------------------------------------------------------
# Photo intake
# --------------------------------------------------------------------------

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username)

    photo = update.message.photo[-1]  # highest resolution
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())

    PENDING_PHOTOS.setdefault(user.id, []).append(image_bytes)
    total = len(PENDING_PHOTOS[user.id])

    await update.message.reply_text(
        f"📸 Screenshot received! Total queued: {total}\n"
        f"Send more, or /generate when you're ready."
    )


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

async def cmd_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username)
    row = db.get_user(user.id)

    images = PENDING_PHOTOS.get(user.id, [])
    if not images:
        await update.message.reply_text(
            "⚠️ You haven't sent any screenshots yet. Upload some first, then /generate."
        )
        return

    # --- billing check -----------------------------------------------
    is_admin_user = is_admin(user.id)
    has_sub = db.is_sub_active(row)
    charge_mode = None  # "admin" | "sub" | "trial" | "coins"

    if is_admin_user:
        charge_mode = "admin"
    elif has_sub:
        charge_mode = "sub"
    elif row["free_trials"] > 0:
        charge_mode = "trial"
    elif row["coins"] >= config.COST_PER_GENERATION:
        charge_mode = "coins"
    else:
        await update.message.reply_text(
            "❌ Not enough balance. Each description costs "
            f"{config.COST_PER_GENERATION} coins, and you have {row['coins']}.\n"
            "Use /pricing to see how to top up or get premium."
        )
        return

    status_msg = await update.message.reply_text(
        f"⚙️ Processing {len(images)} screenshot(s)...\n"
        "Running OCR, merging account statistics, and generating your professional "
        "Groq description. This usually takes 5-10 seconds."
    )

    try:
        extractions = [groq_client.extract_stats_from_image(img) for img in images]
        merged = groq_client.merge_stats(extractions)
        missing = groq_client.missing_fields_list(merged)
        narrative = groq_client.generate_narrative(merged)
        description = build_description(merged, narrative, missing)
    except Exception:
        logger.exception("Generation failed")
        await status_msg.edit_text(
            "❌ Something went wrong while generating your description. "
            "Please try again — your balance has not been charged."
        )
        return

    # --- deduct cost, only after a successful generation --------------
    if charge_mode == "trial":
        db.consume_free_trial(user.id)
    elif charge_mode == "coins":
        db.spend_coins(user.id, config.COST_PER_GENERATION)
    # "admin" and "sub" -> no charge

    db.log_generation(user.id, len(images), summary=(merged.get("level") and f"Level {merged.get('level')} account") or "Account listing")
    PENDING_PHOTOS.pop(user.id, None)

    await status_msg.delete()
    await update.message.reply_text(description)


# --------------------------------------------------------------------------
# Admin commands
# --------------------------------------------------------------------------

def _parse_target_id(args: list[str]) -> int | None:
    if not args:
        return None
    try:
        return int(args[0])
    except ValueError:
        return None


async def cmd_addcoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /addcoins <id> <amount>")
        return
    target_id = _parse_target_id(args)
    try:
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("Amount must be a whole number.")
        return
    if target_id is None or amount <= 0:
        await update.message.reply_text("Usage: /addcoins <id> <amount>")
        return
    db.ensure_user(target_id)
    db.add_coins(target_id, amount)
    row = db.get_user(target_id)
    await update.message.reply_text(f"✅ Added {amount} coins to {target_id}. New balance: {row['coins']}.")


async def cmd_removecoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /removecoins <id> <amount>")
        return
    target_id = _parse_target_id(args)
    try:
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("Amount must be a whole number.")
        return
    if target_id is None or amount <= 0:
        await update.message.reply_text("Usage: /removecoins <id> <amount>")
        return
    db.ensure_user(target_id)
    db.remove_coins(target_id, amount)
    row = db.get_user(target_id)
    await update.message.reply_text(f"✅ Removed {amount} coins from {target_id}. New balance: {row['coins']}.")


async def cmd_addsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /addsub <id> [plan]\nPlans: " + ", ".join(config.PLAN_DAYS.keys())
        )
        return
    target_id = _parse_target_id(args)
    plan = args[1] if len(args) > 1 else "31day"
    if plan not in config.PLAN_DAYS:
        await update.message.reply_text(
            "Unknown plan. Choose one of: " + ", ".join(config.PLAN_DAYS.keys())
        )
        return
    if target_id is None:
        await update.message.reply_text("Usage: /addsub <id> [plan]")
        return
    db.ensure_user(target_id)
    db.set_subscription(target_id, config.PLAN_DAYS[plan], plan)
    row = db.get_user(target_id)
    await update.message.reply_text(
        f"✅ Granted {plan} premium to {target_id}. Expires: {db.fmt_expiry(row['sub_expiry'])}."
    )


async def cmd_removesub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    target_id = _parse_target_id(args)
    if target_id is None:
        await update.message.reply_text("Usage: /removesub <id>")
        return
    db.ensure_user(target_id)
    db.remove_subscription(target_id)
    await update.message.reply_text(f"✅ Subscription for {target_id} has been expired immediately.")


async def cmd_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    target_id = _parse_target_id(args)
    if target_id is None:
        await update.message.reply_text("Usage: /userinfo <id>")
        return
    db.ensure_user(target_id)
    row = db.get_user(target_id)
    sub_status = (
        f"Active ({row['sub_plan']}) until {db.fmt_expiry(row['sub_expiry'])}"
        if db.is_sub_active(row)
        else "Not active"
    )
    history = db.get_history(target_id, limit=10)
    lines = [
        f"👤 USER INFO — {target_id}",
        f"Username: @{row['username']}" if row["username"] else "Username: (unknown)",
        f"🪙 Coins: {row['coins']}",
        f"🎁 Free trials left: {row['free_trials']}",
        f"👑 Subscription: {sub_status}",
        f"📊 Total descriptions generated: {row['total_generated']}",
        "",
        "🕒 Recent history:",
    ]
    if history:
        for h in history:
            ts = db.fmt_expiry(h["created_at"])
            lines.append(f"  • {ts} — {h['num_images']} screenshot(s) — {h['summary']}")
    else:
        lines.append("  (no descriptions generated yet)")
    await update.message.reply_text("\n".join(lines))


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main():
    db.init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("pricing", cmd_pricing))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("generate", cmd_generate))

    app.add_handler(CommandHandler("addcoins", cmd_addcoins))
    app.add_handler(CommandHandler("removecoins", cmd_removecoins))
    app.add_handler(CommandHandler("addsub", cmd_addsub))
    app.add_handler(CommandHandler("removesub", cmd_removesub))
    app.add_handler(CommandHandler("userinfo", cmd_userinfo))

    app.add_handler(MessageHandler(filters.PHOTO, on_photo))

    logger.info("Isagi Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
