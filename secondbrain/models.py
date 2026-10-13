"""Structured-output schema Claude fills in for each batch of source items."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .profiles import NAMES

Profile = Literal[NAMES]  # Triveni Mall, Sangam, Sundarban, ADLLP & Group, Caliber, Personal, Other
_PF = "Business profile this belongs to (exact name from the profile list)."


class NewCommitment(BaseModel):
    owner: str = Field(description="Person who promised to do it. Use the CEO's name if it's on them.")
    owner_email: Optional[str]
    item: str = Field(description="What will be done, one crisp line.")
    due: Optional[str] = Field(description="YYYY-MM-DD, resolved from relative dates; null if none.")
    status: Literal["Open", "Done"]
    project: Optional[str]
    profile: Profile = Field(description=_PF)
    source_ref: str = Field(description="The ref attribute of the item this came from.")
    evidence: str = Field(description="Short quote proving it.")


class CommitmentUpdate(BaseModel):
    id: str = Field(description="ID of an existing open commitment.")
    status: Literal["Open", "Done", "Blocked", "Cancelled"]
    due: Optional[str] = Field(description="New YYYY-MM-DD if the deadline moved, else null.")
    source_ref: str
    evidence: str


class Decision(BaseModel):
    decision: str
    made_by: str
    date: str = Field(description="YYYY-MM-DD")
    project: Optional[str]
    profile: Profile = Field(description=_PF)
    source_ref: str
    evidence: str


class Risk(BaseModel):
    risk: str
    severity: Literal["High", "Medium", "Low"]
    project: Optional[str]
    profile: Profile = Field(description=_PF)
    owner: Optional[str]
    source_ref: str
    evidence: str


class Approval(BaseModel):
    item: str = Field(description="What the CEO is being asked to approve/sign/decide.")
    requested_by: str
    requested_by_email: Optional[str]
    due: Optional[str] = Field(description="YYYY-MM-DD or null")
    amount: Optional[str] = Field(description="Money involved, with currency, if stated.")
    project: Optional[str]
    profile: Profile = Field(description=_PF)
    source_ref: str
    evidence: str


class ApprovalUpdate(BaseModel):
    id: str = Field(description="ID of an existing pending approval.")
    status: Literal["Pending", "Approved", "Rejected", "Done"]
    source_ref: str
    evidence: str


class Person(BaseModel):
    name: str
    email: Optional[str]
    organisation: Optional[str]
    role: Optional[str]
    phone: Optional[str] = Field(description="Mobile number with country code if seen (signature, WhatsApp), else null.")


class Extraction(BaseModel):
    commitments: list[NewCommitment]
    commitment_updates: list[CommitmentUpdate]
    decisions: list[Decision]
    risks: list[Risk]
    approvals: list[Approval]
    approval_updates: list[ApprovalUpdate]
    people: list[Person]
