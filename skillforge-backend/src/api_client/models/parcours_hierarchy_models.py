"""
Pydantic models for Studi Parcours API hierarchy response.
These models match the C# data contracts from Studi.Api.Parcours.ExchangeDataContract.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RessourceHierarchy(BaseModel):
    """Represents a resource (Ressource) in the hierarchy."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(..., description="Resource ID")
    titre: str = Field(..., description="Resource title")
    categorie: str = Field(..., alias="categorie", description="Resource category")
    ordre: int = Field(..., description="Order/position in the list")
    duree: Optional[int] = Field(None, description="Duration in minutes")
    difficulty: Optional[int] = Field(None, description="Difficulty level")
    priority: Optional[str] = Field(None, description="Priority level")


class ThemeHierarchy(BaseModel):
    """Represents a theme in the hierarchy."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(..., description="Theme ID")
    code: str = Field(..., description="Theme code")
    titre: str = Field(..., description="Theme title")
    description: Optional[str] = Field(None, description="Theme description")
    ordre: int = Field(..., description="Order/position in the list")
    duree: int = Field(..., description="Duration in minutes")
    ressources: list[RessourceHierarchy] = Field(default_factory=list, description="List of resources in this theme")


class ModuleHierarchy(BaseModel):
    """Represents a module in the hierarchy."""

    id: int = Field(..., description="Module ID")
    code: str = Field(..., description="Module code")
    titre: str = Field(..., description="Module title")
    description: Optional[str] = Field(None, description="Module description")
    ordre: int = Field(..., description="Order/position in the list")
    duree: int = Field(..., description="Duration in minutes")
    ponderation_debut: int = Field(..., description="Start weighting")
    ponderation_fin: int = Field(..., description="End weighting")
    type: Optional[str] = Field(None, description="Module type")
    themes: list[ThemeHierarchy] = Field(default_factory=list, description="List of themes in this module")

    model_config = ConfigDict(populate_by_name=True)


class ExamenHierarchy(BaseModel):
    """Represents an exam (Examen) in the hierarchy."""

    id: int = Field(..., description="Exam ID")
    name: str = Field(..., description="Exam name")
    examen_type_id: int = Field(..., alias="examenTypeId", description="Exam type ID")

    model_config = ConfigDict(populate_by_name=True)


class MatiereHierarchy(BaseModel):
    """Represents a subject (Matiere) in the hierarchy."""

    id: int = Field(..., description="Subject ID")
    code: str = Field(..., description="Subject code")
    titre: str = Field(..., description="Subject title")
    description: Optional[str] = Field(None, description="Subject description")
    ordre: int = Field(..., description="Order/position in the list")
    duree: int = Field(..., description="Duration in minutes")
    ponderation_debut: int = Field(..., description="Start weighting")
    ponderation_fin: int = Field(..., description="End weighting")
    element_type_id: int = Field(..., alias="elementId", description="Element type ID")
    is_optional: bool = Field(..., alias="is_option", description="Whether this subject is optional")
    planning: bool = Field(..., description="Whether this subject has planning")
    linked_blocks_ids: list[int] = Field(default_factory=list, alias="linkedEvaluationsBlocksIds", description="Linked evaluation blocks IDs")
    modules: list[ModuleHierarchy] = Field(default_factory=list, description="List of modules in this subject")
    examens: list[ExamenHierarchy] = Field(default_factory=list, description="List of exams in this subject")

    model_config = ConfigDict(populate_by_name=True)


class EvaluationModuleHierarchy(BaseModel):
    """Represents an evaluation module in the hierarchy."""

    id: int = Field(..., description="Evaluation module ID")
    code: str = Field(..., description="Evaluation module code")
    titre: str = Field(..., description="Evaluation module title")
    duree: int = Field(..., description="Duration in minutes")

    model_config = ConfigDict(populate_by_name=True)


class EvaluationHierarchy(BaseModel):
    """Represents an evaluation in the hierarchy."""

    id: int = Field(..., description="Evaluation ID")
    code: str = Field(..., description="Evaluation code")
    titre: str = Field(..., description="Evaluation title")
    categorie: str = Field(..., description="Evaluation category")
    ordre: int = Field(..., description="Order/position in the list")
    coefficient: float = Field(..., description="Coefficient/weight")
    status: str = Field(..., description="Evaluation status")
    evaluation_type_id: int = Field(..., alias="evaluationTypeId", description="Evaluation type ID")
    not_rated: bool = Field(..., alias="notRated", description="Whether this evaluation is not rated")
    info_note: bool = Field(..., alias="infoNote", description="Whether this evaluation has info notes")
    delivery_note: bool = Field(..., alias="deliveryNote", description="Whether delivery note is required")
    delivery_copy: bool = Field(..., alias="deliveryCopy", description="Whether delivery copy is required")
    delivery_correction_type: bool = Field(..., alias="deliveryCorrectionType", description="Delivery correction type")
    use_model: bool = Field(..., alias="useModel", description="Whether to use a model")
    is_resit_evaluation: bool = Field(..., alias="isResitEvaluation", description="Whether this is a resit evaluation")
    link_evaluation_grid: Optional[str] = Field(None, alias="linkEvaluationGrid", description="Link to evaluation grid")
    titre_legal: Optional[str] = Field(None, alias="legalTitleName", description="Legal title name")
    mode_enonce_id: Optional[int] = Field(None, alias="modeEnonceId", description="Statement mode ID")
    exam_session_id: Optional[int] = Field(None, alias="examSessionId", description="Exam session ID")
    exam_session_start_date: Optional[datetime] = Field(None, alias="examSessionStartDate", description="Exam session start date")
    exam_session_end_date: Optional[datetime] = Field(None, alias="examSessionEndDate", description="Exam session end date")
    delai_reservation: Optional[int] = Field(None, alias="codelaiReservationde", description="Reservation delay")
    remise_documents_obligatoire: Optional[bool] = Field(None, alias="remiseDocumentsObligatoire", description="Whether document submission is mandatory")
    autorisation_eleve_inscription_oral: Optional[bool] = Field(None, alias="autorisationEleveInscriptionOral", description="Whether student oral registration is authorized")
    modules: list[EvaluationModuleHierarchy] = Field(default_factory=list, description="List of evaluation modules")

    model_config = ConfigDict(populate_by_name=True)


class BlocHierarchy(BaseModel):
    """Represents a bloc in the hierarchy."""

    id: int = Field(..., description="Bloc ID")
    code: str = Field(..., description="Bloc code")
    libelle: str = Field(..., description="Bloc label")
    ordre: int = Field(..., description="Order/position in the list")
    coefficient: float = Field(..., description="Coefficient/weight")
    block_type_id: int = Field(..., alias="blocId", description="Block type ID")
    is_optional: bool = Field(..., alias="is_option", description="Whether this bloc is optional")
    linked_element_id: Optional[int] = Field(None, alias="linkedElementId", description="Linked element ID")
    evaluations: list[EvaluationHierarchy] = Field(default_factory=list, description="List of evaluations in this bloc")

    model_config = ConfigDict(populate_by_name=True)


class ParcoursHierarchy(BaseModel):
    """
    Represents the complete parcours hierarchy response from the API.
    This is the root model returned by the /{parcoursId}/hierarchy endpoint.
    """

    id: int = Field(..., description="Parcours ID")
    code: str = Field(..., description="Parcours code")
    titre: str = Field(..., description="Parcours title")
    publication_date: datetime = Field(..., alias="publication_date", description="Publication date")
    archived: bool = Field(..., description="Whether this parcours is archived")
    file_name: str = Field(..., alias="parcours_json", description="Parcours JSON filename")
    blocs: list[BlocHierarchy] = Field(default_factory=list, description="List of blocs in this parcours")
    matieres: list[MatiereHierarchy] = Field(default_factory=list, description="List of subjects in this parcours")
    examens: list[ExamenHierarchy] = Field(default_factory=list, description="List of exams in this parcours")

    model_config = ConfigDict(populate_by_name=True)
