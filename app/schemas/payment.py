from typing import Any

from pydantic import BaseModel, Field


class CreatePaymentRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=100)
    return_url: str
    cancel_url: str


class CreatePaymentResponse(BaseModel):
    payment_id: str
    checkout_url: str


class PayOSWebhookPayload(BaseModel):
    code: str | None = None
    desc: str | None = None
    success: bool | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    signature: str | None = None
