import logging
import os
import sys

# Make `founder_bot` importable without an editable install (e.g. on Railway,
# where only requirements.txt deps are installed).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import httpx
from openai import OpenAI
from dotenv import load_dotenv

from founder_bot.bot import Bot
from founder_bot.company import fetch_company_context
from founder_bot.config import Settings
from founder_bot.drafter import draft_email
from founder_bot.enrich import (
    ApolloProvider, CompanyDomainResolver, DuckDuckGoDomainResolver, EmailVerifier,
    EnrichmentChain, HunterProvider, LinkedInScrapeProvider, PatternGuessProvider,
    TeamFinder,
)
from founder_bot.gmail_draft import connect, create_draft
from founder_bot.kb import load_kb
from founder_bot.pipeline import Pipeline
from founder_bot.urls import normalize_linkedin_url


def _load_resume(settings, http):
    """Load the resume PDF to attach: from RESUME_PATH (local) or RESUME_URL (hosted).

    A relative RESUME_PATH is resolved against both the working directory and this
    script's directory (the repo root), so it works regardless of where the host
    launches the process from.
    """
    if settings.resume_path:
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = [settings.resume_path]
        if not os.path.isabs(settings.resume_path):
            candidates.append(os.path.join(here, settings.resume_path))
        for candidate in candidates:
            if os.path.isfile(candidate):
                with open(candidate, "rb") as handle:
                    return (os.path.basename(candidate), handle.read())
        logging.warning("RESUME_PATH set but file not found: %s", settings.resume_path)
    if settings.resume_url:
        try:
            resp = http.get(settings.resume_url, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError:
            logging.warning("Could not download resume from RESUME_URL")
            return None
        name = settings.resume_url.rstrip("/").split("/")[-1] or "resume.pdf"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        return (name, resp.content)
    return None


def main():
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    settings = Settings.from_env()

    http = httpx.Client(timeout=20.0)
    llm_client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    def save_gmail_draft(email, draft):
        imap = connect(settings.gmail_address, settings.gmail_app_password)
        try:
            create_draft(
                imap, email, draft,
                from_email=settings.gmail_address,
                attachment=resume,
                footer_text=settings.email_footer,
                footer_html=settings.email_footer_html,
            )
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
            CompanyDomainResolver(settings.serper_api_key, http),  # real domain (Serper, if key)
            DuckDuckGoDomainResolver(http),                        # real domain (keyless fallback)
            HunterProvider(settings.hunter_api_key, http),
            PatternGuessProvider(),
        ],
    )

    verifier = EmailVerifier(settings.hunter_api_key, http)
    team_finder = TeamFinder(settings.hunter_api_key, http)
    resume = _load_resume(settings, http)
    if resume:
        logging.info("Attaching resume to drafts: %s", resume[0])
    else:
        logging.info("No resume configured (set RESUME_PATH or RESUME_URL to attach one).")

    pipeline = Pipeline(
        normalize=normalize_linkedin_url,
        enrich=chain.run,
        verify_email=verifier.verify,
        find_team=team_finder.find,
        fetch_company=lambda domain: fetch_company_context(domain, http),
        load_kb=lambda: settings.kb_text or load_kb(settings.kb_dir),
        draft=lambda lead, ctx, kb: draft_email(llm_client, settings.llm_model, lead, ctx, kb),
    )

    bot = Bot(
        owner_id=settings.telegram_owner_id,
        pipeline=pipeline,
        create_gmail_draft=save_gmail_draft,
        signature=settings.email_footer,
    )
    app = bot.build_application(settings.telegram_bot_token)
    app.run_polling()


if __name__ == "__main__":
    main()
