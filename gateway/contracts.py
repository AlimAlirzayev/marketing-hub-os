"""Typed contracts at the gateway execution boundary.

Provider text is untrusted data. The worker must never infer success merely
because ``executor.execute`` returned a dictionary: every outcome is validated
before it may mutate queue state, memory, skills, or the operator UI.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ExecutionStatus = Literal["success", "partial", "failure", "needs_approval"]


class ExecutionOutcome(BaseModel):
    """Validated executor-to-worker hand-off with fail-closed state rules."""

    model_config = ConfigDict(extra="forbid")

    status: ExecutionStatus = "success"
    result: str = Field(min_length=1, max_length=1_000_000)
    artifacts: list[str] = Field(default_factory=list)
    needs_approval: bool = False
    error_code: str | None = Field(default=None, max_length=80)
    retryable: bool = False
    route: str | None = Field(default=None, max_length=240)

    @model_validator(mode="before")
    @classmethod
    def _legacy_approval_shape(cls, value):
        if isinstance(value, dict) and value.get("needs_approval") and "status" not in value:
            value = {**value, "status": "needs_approval"}
        return value

    @model_validator(mode="after")
    def _consistent_state(self):
        if self.status == "needs_approval":
            self.needs_approval = True
        elif self.needs_approval:
            raise ValueError("needs_approval is only valid with status=needs_approval")
        if self.status == "failure" and not self.error_code:
            raise ValueError("failure outcomes require error_code")
        if self.status != "failure" and self.error_code:
            raise ValueError("error_code is only valid with status=failure")
        return self

    @classmethod
    def failed(
        cls,
        message: str,
        *,
        error_code: str,
        retryable: bool = False,
        route: str | None = None,
    ) -> "ExecutionOutcome":
        return cls(
            status="failure",
            result=message,
            error_code=error_code,
            retryable=retryable,
            route=route,
        )
