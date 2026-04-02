"""Corrige exercice 3 - Session State et ToolContext."""

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext


def add_item(item: str, quantity: int, tool_context: ToolContext) -> dict:
    """Adds an item with quantity to the shopping list.

    Args:
        item: The item name to add.
        quantity: How many of this item.

    Returns:
        Confirmation of the added item.
    """
    shopping_list = tool_context.state.get("shopping_list", {})
    shopping_list[item] = quantity
    tool_context.state["shopping_list"] = shopping_list
    tool_context.state["item_count"] = len(shopping_list)
    return {
        "status": "success",
        "message": f"Added {quantity}x {item}. Total items: {len(shopping_list)}",
    }


def remove_item(item: str, tool_context: ToolContext) -> dict:
    """Removes an item from the shopping list.

    Args:
        item: The item name to remove.

    Returns:
        Confirmation or error if item not found.
    """
    shopping_list = tool_context.state.get("shopping_list", {})
    if item in shopping_list:
        del shopping_list[item]
        tool_context.state["shopping_list"] = shopping_list
        tool_context.state["item_count"] = len(shopping_list)
        return {"status": "success", "message": f"Removed '{item}'. Remaining: {len(shopping_list)}"}
    return {"status": "error", "message": f"'{item}' not found in the list."}


def show_list(tool_context: ToolContext) -> dict:
    """Shows the current shopping list.

    Returns:
        Dictionary with all items and quantities.
    """
    shopping_list = tool_context.state.get("shopping_list", {})
    return {
        "status": "success",
        "shopping_list": shopping_list,
        "item_count": len(shopping_list),
    }


root_agent = Agent(
    name="shopping_list",
    model="gemini-2.5-flash",
    description="A shopping list manager that remembers items across turns.",
    instruction=(
        "You manage a shopping list. Items in list: {item_count}\n\n"
        "Use add_item to add items, remove_item to remove, show_list to display.\n"
        "Always confirm actions to the user."
    ),
    tools=[add_item, remove_item, show_list],
    output_key="last_action",
)
