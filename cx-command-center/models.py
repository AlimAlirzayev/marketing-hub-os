"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IncomingMessage(BaseModel):
    source: str = Field(default="manual", description="Connector or upstream system")
    channel: str = Field(default="website_form")
    account: str | None = None
    external_id: str | None = None
    author_name: str | None = None
    author_handle: str | None = None
    text: str
    rating: float | None = None
    url: str | None = None
    occurred_at: datetime | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StatusUpdate(BaseModel):
    status: str
    owner: str | None = None
    note: str | None = None


class AskRequest(BaseModel):
    question: str
    days: int = 30


class ReplyRequest(BaseModel):
    message: str | None = None
    dry_run: bool = True
