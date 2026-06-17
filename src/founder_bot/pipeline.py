from typing import Callable, Optional

from founder_bot.models import Draft, Lead, Result


class InvalidUrlError(ValueError):
    """Raised when the input is not a valid LinkedIn profile URL."""


class Pipeline:
    """Orchestrate: validate URL → enrich → company context → draft. Fail-soft per step."""

    def __init__(
        self,
        normalize: Callable[[str], Optional[str]],
        enrich: Callable[[str], Optional[Lead]],
        fetch_company: Callable[[Optional[str]], Optional[str]],
        load_kb: Callable[[], str],
        draft: Callable[[Lead, Optional[str], str], Draft],
    ):
        self.normalize = normalize
        self.enrich = enrich
        self.fetch_company = fetch_company
        self.load_kb = load_kb
        self.draft = draft

    def run(self, raw_url: str) -> Result:
        url = self.normalize(raw_url)
        if url is None:
            raise InvalidUrlError("That doesn't look like a LinkedIn profile URL.")

        lead = self.enrich(url)
        if lead is None:
            raise RuntimeError("Could not identify this person from the LinkedIn URL.")

        warnings: list[str] = []
        if not lead.email:
            warnings.append("No email found — draft saved without a recipient; add it manually.")

        company_context = self.fetch_company(lead.domain)
        if company_context is None:
            warnings.append("Limited company context — drafted from profile + your knowledge base only.")

        draft = self.draft(lead, company_context, self.load_kb())
        return Result(lead=lead, company_context=company_context, draft=draft, warnings=warnings)
