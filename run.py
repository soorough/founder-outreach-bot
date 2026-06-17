import logging

import httpx
from openai import OpenAI
from dotenv import load_dotenv

from founder_bot.bot import Bot
from founder_bot.company import fetch_company_context
from founder_bot.config import Settings
from founder_bot.drafter import draft_email
from founder_bot.enrich import (
    ApolloProvider, CompanyDomainResolver, EnrichmentChain, HunterProvider,
    LinkedInScrapeProvider, PatternGuessProvider,
)
from founder_bot.gmail_draft import connect, create_draft
from founder_bot.kb import load_kb
from founder_bot.pipeline import Pipeline
from founder_bot.urls import normalize_linkedin_url


def main():
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    settings = Settings.from_env()

    http = httpx.Client(timeout=20.0)
    llm_client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    def save_gmail_draft(email, draft):
        imap = connect(settings.gmail_address, settings.gmail_app_password)
        try:
            create_draft(imap, email, draft, from_email=settings.gmail_address)
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    chain = EnrichmentChain(
        identity_providers=[
            ApolloProvider(settings.apollo_api_key, http),  # paid; no-ops without a working key
            LinkedInScrapeProvider(http),                   # free fallback: name + company from meta tags
        ],
        email_fillers=[
            CompanyDomainResolver(settings.serper_api_key, http),  # find real domain first
            HunterProvider(settings.hunter_api_key, http),
            PatternGuessProvider(),
        ],
    )

    pipeline = Pipeline(
        normalize=normalize_linkedin_url,
        enrich=chain.run,
        fetch_company=lambda domain: fetch_company_context(domain, http),
        load_kb=lambda: load_kb(settings.kb_dir),
        draft=lambda lead, ctx, kb: draft_email(llm_client, settings.llm_model, lead, ctx, kb),
    )

    bot = Bot(
        owner_id=settings.telegram_owner_id,
        pipeline=pipeline,
        create_gmail_draft=save_gmail_draft,
    )
    app = bot.build_application(settings.telegram_bot_token)
    app.run_polling()


if __name__ == "__main__":
    main()
