import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters,
)

from founder_bot.models import Result
from founder_bot.pipeline import InvalidUrlError

logger = logging.getLogger(__name__)


def _format_preview(result: Result, label: str, signature: str = "") -> str:
    lead = result.lead
    email = lead.email or "(none found)"
    status = f", {lead.email_status}" if lead.email_status else ""
    warnings = "\n".join(f"⚠️ {w}" for w in result.warnings)
    body = result.draft.body + (f"\n\n{signature}" if signature else "")
    return (
        f"*[{label}]*\n"
        f"*To:* {lead.name}"
        f"{' — ' + lead.title if lead.title else ''}"
        f"{' @ ' + lead.company if lead.company else ''}\n"
        f"*Email:* {email} ({lead.email_confidence}{status})\n\n"
        f"*Subject:* {result.draft.subject}\n\n"
        f"{body}\n\n"
        f"{warnings}"
    ).strip()


class Bot:
    """Telegram wiring. Owns the pipeline + gmail-draft creator; holds the per-chat
    list of drafted Results so each can be saved by index.
    """

    def __init__(self, owner_id: int, pipeline, create_gmail_draft, signature: str = ""):
        self.owner_id = owner_id
        self.pipeline = pipeline
        self.create_gmail_draft = create_gmail_draft
        self.signature = signature
        self._pending: dict[int, list[Result]] = {}

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != self.owner_id:
            return  # whitelist: ignore everyone else
        chat_id = update.effective_chat.id
        await update.message.reply_text("Working on it…")
        try:
            results = self.pipeline.run(update.message.text)
        except InvalidUrlError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return
        except Exception as exc:  # fail-soft: surface the error, don't crash
            logger.exception("pipeline failed")
            await update.message.reply_text(f"❌ Something went wrong: {exc}")
            return

        self._pending[chat_id] = results
        for index, result in enumerate(results):
            label = "Primary" if index == 0 else f"Co-founder {index}"
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("✅ Save to Gmail", callback_data=f"save:{index}")]]
            )
            await update.message.reply_text(
                _format_preview(result, label, self.signature),
                parse_mode="Markdown", reply_markup=keyboard,
            )
        if len(results) > 1:
            await update.message.reply_text(
                f"Found {len(results) - 1} co-founder(s). Each draft above has its own Save button."
            )

    async def handle_save(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.from_user.id != self.owner_id:
            return
        try:
            index = int((query.data or "").split(":", 1)[1])
        except (IndexError, ValueError):
            index = -1
        results = self._pending.get(query.message.chat_id) or []
        if not 0 <= index < len(results):
            await query.edit_message_text("Nothing to save (expired).")
            return
        result = results[index]
        try:
            self.create_gmail_draft(result.lead.email, result.draft)
        except Exception as exc:
            logger.exception("gmail draft failed")
            await query.edit_message_text(f"❌ Could not save draft: {exc}")
            return
        await query.edit_message_text(f"✅ Saved to Gmail Drafts: {result.lead.name}")

    def build_application(self, token: str) -> Application:
        app = Application.builder().token(token).build()
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        app.add_handler(CallbackQueryHandler(self.handle_save, pattern="^save:"))
        return app
