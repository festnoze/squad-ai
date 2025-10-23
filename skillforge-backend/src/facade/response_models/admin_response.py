from pydantic import BaseModel


class AdminOperationResponse(BaseModel):
    """Response model for admin operations.

    Attributes:
        status: Operation status (e.g., 'success', 'error')
        message: Descriptive message about the operation result
    """

    status: str
    message: str
