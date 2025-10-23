from pydantic import BaseModel, Field
from facade.request_models.context_request import CourseContextStudiRequest, ContextBlackBoardRequest
from typing import Literal, Any, Annotated, Union


class QueryRequest(BaseModel):
    query_text_content: str
    query_selected_text: str
    query_quick_action: Literal["reformulation", "explanation", "summary", "translation"] | None = None
    query_attachments: list[dict[str, Any]] | None = None


# Discriminated union for course context
CourseContextUnion = Annotated[Union[CourseContextStudiRequest, ContextBlackBoardRequest], Field(discriminator="context_type")]


class UserAskNewQueryRequest(BaseModel):
    query: QueryRequest
    course_context: CourseContextUnion
