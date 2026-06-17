from typing import Callable, Optional

from founder_bot.models import Draft, Lead, Result


class InvalidUrlError(ValueError):
    """Raised when the input is not a valid LinkedIn profile URL."""


class Pipeline:
    """Orchestrate: validate URL → enrich → verify email → company context → draft,
    then repeat the draft for any co-founders found. Returns a list of Results
    (primary first). Fail-soft per step.
    """

    def __init__(
        self,
        normalize: Callable[[str], Optional[str]],
        enrich: Callable[[str], Optional[Lead]],
        verify_email: Callable[[Lead], Lead],
        find_team: Callable[[Lead], list[Lead]],
        fetch_company: Callable[[Optional[str]], Optional[str]],
        load_kb: Callable[[], str],
        draft: Callable[[Lead, Optional[str], str], Draft],
    ):
        self.normalize = normalize
        self.enrich = enrich
        self.verify_email = verify_email
        self.find_team = find_team
        self.fetch_company = fetch_company
        self.load_kb = load_kb
        self.draft = draft

    def run(self, raw_url: str) -> list[Result]:
        url = self.normalize(raw_url)
        if url is None:
            raise InvalidUrlError("That doesn't look like a LinkedIn profile URL.")

        lead = self.enrich(url)
        if lead is None:
            raise RuntimeError("Could not identify this person from the LinkedIn URL.")
        lead = self.verify_email(lead)

        # Company context + KB are shared across everyone at the same company.
        company_context = self.fetch_company(lead.domain)
        kb_text = self.load_kb()

        results = [self._build_result(lead, company_context, kb_text, is_primary=True)]
        for cofounder in self.find_team(lead):
            verified = self.verify_email(cofounder)
            results.append(self._build_result(verified, company_context, kb_text, is_primary=False))
        return results

    def _build_result(
        self, lead: Lead, company_context: Optional[str], kb_text: str, is_primary: bool
    ) -> Result:
        warnings: list[str] = []
        if not lead.email:
            warnings.append("No email found — draft saved without a recipient; add it manually.")
        elif lead.email_status and lead.email_status != "valid":
            warnings.append(f"Email status: {lead.email_status} — verify before sending.")
        if is_primary and company_context is None:
            warnings.append("Limited company context — drafted from profile + your knowledge base only.")
        draft = self.draft(lead, company_context, kb_text)
        return Result(lead=lead, company_context=company_context, draft=draft, warnings=warnings)
