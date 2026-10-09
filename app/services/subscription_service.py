from app.models.user import User


class SubscriptionService:
    async def ensure_can_create_job(self, user: User, job_type: str) -> None:
        # Placeholder for Supabase subscription lookup / usage quota checks.
        # Keep this async so the call site does not change when real IO is added.
        return None


subscription_service = SubscriptionService()
