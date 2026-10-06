from uuid import uuid4

from app.schemas.payment import CreatePaymentRequest, CreatePaymentResponse, PayOSWebhookPayload


class PaymentService:
    async def create_payment(self, request: CreatePaymentRequest) -> CreatePaymentResponse:
        # Placeholder for PayOS create payment link.
        payment_id = str(uuid4())
        return CreatePaymentResponse(
            payment_id=payment_id,
            checkout_url=f"https://pay.payos.vn/web/{payment_id}",
        )

    async def handle_webhook(self, payload: PayOSWebhookPayload) -> dict[str, str]:
        # Verify PayOS signature and update subscription/order state here.
        return {"status": "accepted"}


payment_service = PaymentService()
