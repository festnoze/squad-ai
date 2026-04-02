"""Corrige exercice 11 - Concepts avances."""

from google.adk.agents import Agent
from google.adk.tools import LongRunningFunctionTool


def request_purchase_approval(item: str, price: float, justification: str) -> dict:
    """Requests manager approval for a purchase. Pauses until approved.

    Args:
        item: What to purchase.
        price: Cost in dollars.
        justification: Why this purchase is needed.

    Returns:
        Dictionary with pending approval status.
    """
    return {
        "status": "pending",
        "message": f"Approval requested for {item} (${price:.2f})",
        "justification": justification,
        "ticket_id": "PO-001",
    }


purchase_tool = LongRunningFunctionTool(func=request_purchase_approval)


def save_purchase_record(item: str, price: float, approved: bool) -> dict:
    """Records a purchase decision.

    Args:
        item: The purchased item.
        price: The price paid.
        approved: Whether the purchase was approved.

    Returns:
        Dictionary with record confirmation.
    """
    status = "recorded" if approved else "rejected"
    return {"status": "success", "message": f"Purchase {status}: {item} (${price:.2f})"}


root_agent = Agent(
    name="purchase_assistant",
    model="gemini-2.5-flash",
    description="A purchase assistant that requires approval before buying.",
    instruction=(
        "You help with purchasing. For any purchase request:\n"
        "1. Use request_purchase_approval to get manager approval first\n"
        "2. Once approved, use save_purchase_record to record it\n"
        "Never proceed without approval."
    ),
    tools=[purchase_tool, save_purchase_record],
)
