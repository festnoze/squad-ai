from models.base_model import IdStatefulBaseModel


class Context(IdStatefulBaseModel):
    """Context model representing a conversation context.

    Inherits common fields (id, created_at, updated_at, deleted_at) from IdStatefulBaseModel.

    Attributes:
        context_filter: JSON object containing context for filtering information
        context_full: JSON object containing full context information
    """

    context_filter: dict = {}
    context_full: dict = {}
