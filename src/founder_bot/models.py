from typing import Literal, Optional
from pydantic import BaseModel

Confidence = Literal["high", "medium", "low", "none"]
Source = Literal["apollo", "hunter", "pattern"]


class Lead(BaseModel):
    name: str
    title: Optional[str] = None
    company: Optional[str] = None
    domain: Optional[str] = None
    email: Optional[str] = None
    email_confidence: Confidence = "none"
    email_status: Optional[str] = None  # Hunter verifier: valid | invalid | accept_all | unknown ...
    source: Optional[Source] = None
    email_alternatives: list[str] = []  # other likely patterns to try when unverified


class Draft(BaseModel):
    subject: str
    body: str


class Result(BaseModel):
    lead: Lead
    company_context: Optional[str] = None
    draft: Optional[Draft] = None
    warnings: list[str] = []
