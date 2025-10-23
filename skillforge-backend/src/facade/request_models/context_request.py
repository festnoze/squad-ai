from pydantic import BaseModel, Field
from typing import Literal


class RessourceDescriptionRequest(BaseModel):
    ressource_id: str | None = None
    ressource_type: Literal["text", "video", "pdf", "image", "interactive"] | None = None
    ressource_code: str | None = None
    ressource_title: str | None = None
    ressource_url: str | None = None
    ressource_path: str | None = None


class CourseContextRequest(BaseModel):
    context_type: str = Field(..., description="Type of context (studi, blackboard, etc.)")


class ContextBlackBoardRequest(CourseContextRequest):
    context_type: Literal["blackboard"] = "blackboard"


class CourseContextStudiRequest(CourseContextRequest):
    context_type: Literal["studi"] = "studi"
    ressource: RessourceDescriptionRequest | None = None
    theme_id: str | None = None
    module_id: str | None = None
    matiere_id: str | None = None
    parcour_id: str | None = None
    parcours_name: str | None = None
