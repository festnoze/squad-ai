from models.base_model import IdStatefulBaseModel


class Content(IdStatefulBaseModel):
    """Content model representing scraped course content.

    Inherits common fields (id, created_at, updated_at, deleted_at) from IdStatefulBaseModel.

    Attributes:
        filter: JSON object containing content filter information (e.g., url, resource_name)
        content_full: string containing full content information in markdown
    """

    filter: dict = {}
    context_metadata: dict = {}
    content_full: str = ""
    content_html: str = ""
    content_media: dict = {}
