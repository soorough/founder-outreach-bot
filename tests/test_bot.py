import asyncio

from founder_bot.bot import Bot, _format_preview
from founder_bot.models import Draft, Lead, Result


def test_preview_lists_alternatives_when_present():
    result = Result(
        lead=Lead(name="Ada", domain="ae.com", email="ada.lovelace@ae.com",
                  email_confidence="low", email_alternatives=["ada@ae.com", "alovelace@ae.com"]),
        draft=Draft(subject="S", body="B"),
    )
    text = _format_preview(result, "Primary")
    assert "ada.lovelace@ae.com (low)" in text
    assert "Also try:" in text and "ada@ae.com" in text


def test_preview_omits_alternatives_when_none():
    result = Result(
        lead=Lead(name="Ada", email="ada@ae.com", email_confidence="high"),
        draft=Draft(subject="S", body="B"),
    )
    assert "Also try:" not in _format_preview(result, "Primary")


class _FakeMessage:
    def __init__(self, text="", chat_id=1):
        self.text = text
        self.chat_id = chat_id
        self.sent = []  # (text, reply_markup)

    async def reply_text(self, text, parse_mode=None, reply_markup=None):
        self.sent.append((text, reply_markup))
        return self


def _obj(**kw):
    return type("O", (), kw)()


class _FakeUpdate:
    def __init__(self, text, user_id=42, chat_id=1):
        self.effective_user = _obj(id=user_id)
        self.effective_chat = _obj(id=chat_id)
        self.message = _FakeMessage(text, chat_id)


class _FakeQuery:
    def __init__(self, data, user_id=42, chat_id=1):
        self.data = data
        self.from_user = _obj(id=user_id)
        self.message = _obj(chat_id=chat_id)
        self.edited = None

    async def answer(self):
        pass

    async def edit_message_text(self, text):
        self.edited = text


class _Pipeline:
    def __init__(self, by_url):
        self.by_url = by_url

    def run(self, url):
        return self.by_url[url]


def _result(name, email):
    return Result(lead=Lead(name=name, email=email), company_context=None,
                  draft=Draft(subject=f"S-{name}", body="B"), warnings=[])


def _token_of(message, i=0):
    with_kb = [m for m in message.sent if m[1] is not None]  # skip "Working on it…"
    return with_kb[i][1].inline_keyboard[0][0].callback_data


def _make_bot(by_url, saved):
    return Bot(owner_id=42, pipeline=_Pipeline(by_url),
               create_gmail_draft=lambda email, draft: saved.append((email, draft.subject)))


def test_save_targets_the_right_draft_even_after_more_urls():
    # The reported bug: sending u2 must not make u1's Save button save u2's draft.
    saved = []
    bot = _make_bot({"u1": [_result("Alice", "alice@a.com")],
                     "u2": [_result("Bob", "bob@b.com")]}, saved)

    up1 = _FakeUpdate("u1")
    asyncio.run(bot.handle_url(up1, None))
    up2 = _FakeUpdate("u2")
    asyncio.run(bot.handle_url(up2, None))

    token1 = _token_of(up1.message)
    query = _FakeQuery(token1)
    asyncio.run(bot.handle_save(_obj(callback_query=query), None))

    assert saved == [("alice@a.com", "S-Alice")]  # not Bob
    assert "Alice" in query.edited


def test_save_includes_alternatives_note_in_draft_body():
    saved = []
    bot = Bot(owner_id=42, pipeline=_Pipeline({}),
              create_gmail_draft=lambda email, draft: saved.append((email, draft.body)))
    result = Result(
        lead=Lead(name="Ada", domain="ae.com", email="ada.lovelace@ae.com",
                  email_confidence="low", email_alternatives=["ada@ae.com", "alovelace@ae.com"]),
        draft=Draft(subject="S", body="Hi Ada,"),
    )
    token = bot._store(result)
    asyncio.run(bot.handle_save(_obj(callback_query=_FakeQuery(token)), None))

    email, body = saved[0]
    assert email == "ada.lovelace@ae.com"            # primary still the To address
    assert "also try: ada@ae.com, alovelace@ae.com" in body
    assert body.endswith("Hi Ada,")                  # original body preserved below the note


def test_save_without_alternatives_leaves_body_unchanged():
    saved = []
    bot = Bot(owner_id=42, pipeline=_Pipeline({}),
              create_gmail_draft=lambda email, draft: saved.append((email, draft.body)))
    result = Result(lead=Lead(name="Ada", email="ada@ae.com", email_confidence="high"),
                    draft=Draft(subject="S", body="Hi Ada,"))
    token = bot._store(result)
    asyncio.run(bot.handle_save(_obj(callback_query=_FakeQuery(token)), None))
    assert saved[0][1] == "Hi Ada,"                  # no note prepended


def test_each_cofounder_gets_a_distinct_token():
    saved = []
    bot = _make_bot({"u": [_result("Ada", "ada@ae.com"), _result("Bob", "bob@ae.com")]}, saved)
    up = _FakeUpdate("u")
    asyncio.run(bot.handle_url(up, None))
    assert _token_of(up.message, 0) != _token_of(up.message, 1)

    asyncio.run(bot.handle_save(_obj(callback_query=_FakeQuery(_token_of(up.message, 1))), None))
    assert saved == [("bob@ae.com", "S-Bob")]


def test_non_owner_save_ignored():
    saved = []
    bot = _make_bot({"u": [_result("Ada", "ada@ae.com")]}, saved)
    up = _FakeUpdate("u")
    asyncio.run(bot.handle_url(up, None))
    asyncio.run(bot.handle_save(_obj(callback_query=_FakeQuery(_token_of(up.message), user_id=999)), None))
    assert saved == []


def test_unknown_token_reports_expired():
    saved = []
    bot = _make_bot({"u": [_result("Ada", "ada@ae.com")]}, saved)
    query = _FakeQuery("save:deadbeef")
    asyncio.run(bot.handle_save(_obj(callback_query=query), None))
    assert saved == []
    assert "expired" in query.edited.lower()
