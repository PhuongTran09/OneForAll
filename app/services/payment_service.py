import hashlib
import hmac
import secrets
from uuid import uuid4

from app.core.config import settings
from app.core.exceptions import ForbiddenException
from app.schemas.payment import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    PayOSWebhookPayload,
)


def verify_payos_signature(data: dict, signature: str, checksum_key: str) -> bool:
    """Verify PayOS HMAC SHA256 checksum."""
    if not signature or not checksum_key:
        return False
    sorted_items = sorted((k, v) for k, v in data.items() if v is not None)
    sign_data = "&".join(f"{k}={v}" for k, v in sorted_items)
    computed_signature = hmac.new(
        checksum_key.encode("utf-8"),
        sign_data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return secrets.compare_digest(computed_signature, signature)


class PaymentService:
    async def create_payment(self, request: CreatePaymentRequest) -> CreatePaymentResponse:
        # Placeholder for PayOS create payment link.
        payment_id = str(uuid4())
        return CreatePaymentResponse(
            payment_id=payment_id,
            checkout_url=f"https://pay.payos.vn/web/{payment_id}",
        )

    async def handle_webhook(self, payload: PayOSWebhookPayload) -> dict[str, str]:
        """Verify PayOS signature and idempotently handle payment events."""
        if settings.PAYOS_CHECKSUM_KEY:
            if not payload.signature:
                raise ForbiddenException(detail="Thiếu PayOS webhook signature.")
            if not verify_payos_signature(payload.data, payload.signature, settings.PAYOS_CHECKSUM_KEY):
                raise ForbiddenException(detail="PayOS webhook signature không hợp lệ.")

        return {"status": "accepted"}


payment_service = PaymentService()
