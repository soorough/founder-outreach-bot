import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters,
)

from founder_bot.models import Result
from founder_bot.pipeline import InvalidUrlError

logger = logging.getLogger(__name__)


def _format_preview(result: Result) -> str:
    lead = result.lead
    email = lead.email or "(none found)"
    confidence = lead.email_confidence
    warnings = "\n".join(f"⚠️ {w}" for w in result.warnings)
    return (
        f"*To:* {lead.name}"
        f"{' — ' + lead.title if lead.title else ''}"
        f"{' @ ' + lead.company if lead.company else ''}\n"
        f"*Email:* {email} ({confidence})\n\n"
        f"*Subject:* {result.draft.subject}\n\n"
        f"{result.draft.body}\n\n"
        f"{warnings}"
    ).strip()


class Bot:
    """Telegram wiring. Owns the pipeline + gmail-draft creator; holds pending results per chat."""

    def __init__(self, owner_id: int, pipeline, create_gmail_draft):
        self.owner_id = owner_id
        self.pipeline = pipeline
        self.create_gmail_draft = create_gmail_draft
        self._pending: dict[int, Result] = {}

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != self.owner_id:
            return  # whitelist: ignore everyone else
        chat_id = update.effective_chat.id
        await update.message.reply_text("Working on it…")
        try:
            result = self.pipeline.run(update.message.text)
        except InvalidUrlError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return
        except Exception as exc:  # fail-soft: surface the error, don't crash
            logger.exception("pipeline failed")
            await update.message.reply_text(f"❌ Something went wrong: {exc}")
            return
        self._pending[chat_id] = result
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Save to Gmail", callback_data="save")]]
        )
        await update.message.reply_text(
            _format_preview(result), parse_mode="Markdown", reply_markup=keyboard
        )

    async def handle_save(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.from_user.id != self.owner_id:
            return
        result = self._pending.pop(query.message.chat_id, None)
        if result is None:
            await query.edit_message_text("Nothing to save (already saved or expired).")
            return
        try:
            self.create_gmail_draft(result.lead.email, result.draft)
        except Exception as exc:
            logger.exception("gmail draft failed")
            await query.edit_message_text(f"❌ Could not save draft: {exc}")
            return
        await query.edit_message_text("✅ Saved to Gmail Drafts.")

    def build_application(self, token: str) -> Application:
        app = Application.builder().token(token).build()
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        app.add_handler(CallbackQueryHandler(self.handle_save, pattern="^save$"))
        return app
