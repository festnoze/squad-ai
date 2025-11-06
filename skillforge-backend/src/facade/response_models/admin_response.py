from pydantic import BaseModel


class AdminOperationResponse(BaseModel):
    """Response model for admin operations.

    Attributes:
        status: Operation status (e.g., 'success', 'error')
        message: Descriptive message about the operation result
    """

    status: str
    message: str


class RessourceScrapingResult(BaseModel):
    """Result of scraping a single resource.

    Attributes:
        name: Name of the resource
        type: Type of resource ('opale' or 'pdf')
        url: URL of the resource
        status: Status of the scraping operation ('success', 'skipped', 'failed')
        message: Descriptive message about the operation result
    """

    name: str
    type: str
    url: str
    status: str
    message: str


class CourseContentScrapingResponse(BaseModel):
    """Response model for course content scraping operation.

    Attributes:
        status: Overall operation status ('success', 'partial_success', 'error')
        message: Descriptive message about the operation result
        parcours_name: Name of the parcours/course
        total_resources: Total number of resources to scrape
        successful: Number of successfully scraped resources
        skipped: Number of skipped resources (already exists)
        failed: Number of failed resources
        results: Detailed results for each resource
    """

    status: str
    message: str
    parcours_name: str
    total_resources: int
    successful: int
    skipped: int
    failed: int
    results: list[RessourceScrapingResult]


class CourseCreationResponse(BaseModel):
    """Response model for course creation operation.

    Attributes:
        status: Operation status ('success' or 'error')
        message: Descriptive message about the operation result
        course_id: UUID of the created course
        course_filter: Course filter extracted from the parcours hierarchy
    """

    status: str
    message: str
    course_id: str
    course_filter: dict
