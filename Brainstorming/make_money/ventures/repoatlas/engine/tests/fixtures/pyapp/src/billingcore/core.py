RETRY_WINDOW_DAYS = 3


class InvoiceEngine:
    """Retries failed payments, suspends after the retry window."""

    def list_all(self):
        return []

    def retry(self, invoice_id):
        return {"invoice": invoice_id, "window_days": RETRY_WINDOW_DAYS}


def suspend_subscription(subscription_id):
    return {"suspended": subscription_id}
