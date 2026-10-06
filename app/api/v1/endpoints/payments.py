from fastapi import APIRouter

from app.api.deps import CurrentUserDep
from app.schemas.payment import CreatePaymentRequest, CreatePaymentResponse, PayOSWebhookPayload
from app.services.payment_service import payment_service

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/payos", response_model=CreatePaymentResponse)
async def create_payos_payment(
    request: CreatePaymentRequest,
    current_user: CurrentUserDep,
):
    return await payment_service.create_payment(request)


@router.post("/payos/webhook")
async def payos_webhook(payload: PayOSWebhookPayload):
    return await payment_service.handle_webhook(payload)
