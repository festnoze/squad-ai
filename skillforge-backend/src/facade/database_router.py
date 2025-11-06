from fastapi import APIRouter, HTTPException, Query
from infrastructure.fill_static_data_in_database_repository import DatabaseAdministrationRepository
from application.content_service import ContentService
from API.dependency_injection_config import deps
from facade.response_models.admin_response import AdminOperationResponse

database_router = APIRouter(prefix="/database", tags=["Database"])


@database_router.delete(
    "",
    description="Drop all database tables (PostgreSQL) or delete database",
    response_model=AdminOperationResponse,
    status_code=200,
)
async def adelete_database(database_admin_repository: DatabaseAdministrationRepository = deps.depends(DatabaseAdministrationRepository)) -> AdminOperationResponse:
    """Delete all database tables."""
    database_admin_repository.reset_database()
    return AdminOperationResponse(status="success", message="All database tables have been dropped successfully")


@database_router.post(
    "/create",
    description="Create all database tables from entities",
    response_model=AdminOperationResponse,
    status_code=200,
)
async def acreate_database(database_admin_repository: DatabaseAdministrationRepository = deps.depends(DatabaseAdministrationRepository)) -> AdminOperationResponse:
    """Create all database tables based on entity definitions (User, Thread, Message, Role, etc.)."""
    await database_admin_repository.data_context.create_database_async()
    return AdminOperationResponse(status="success", message="Database tables created successfully")


@database_router.post(
    "/data/fill",
    description="Fill static/reference data into database",
    response_model=AdminOperationResponse,
    status_code=200,
)
async def afill_static_data(database_admin_repository: DatabaseAdministrationRepository = deps.depends(DatabaseAdministrationRepository)) -> AdminOperationResponse:
    """Fill static/reference data into the database."""
    await database_admin_repository.afill_all_static_data()
    return AdminOperationResponse(status="success", message="Static data filled successfully (roles: user, assistant)")


@database_router.post(
    "/reset",
    description="Reset database: drop, recreate, and fill data",
    response_model=AdminOperationResponse,
    status_code=200,
)
async def areset_database(database_admin_repository: DatabaseAdministrationRepository = deps.depends(DatabaseAdministrationRepository)) -> AdminOperationResponse:
    """Complete database reset: drop all tables, recreate them, and fill static data."""
    database_admin_repository.reset_database()
    # await database_admin_repository.data_context.count_entities_async(entity to set ?)
    await database_admin_repository.afill_all_static_data()

    return AdminOperationResponse(status="success", message="Database reset complete")


@database_router.post(
    "/contents/export",
    description="Export all contents from database to JSON files with validation and checksums",
    response_model=dict,
    status_code=200,
)
async def aexport_contents(
    batch_size: int = Query(25, description="Number of contents per batch file", ge=1, le=1000),
    output_dir: str = Query("exports", description="Directory to save export files"),
    content_service: ContentService = deps.depends(ContentService),
) -> dict:
    """Export all contents from the database to JSON files.

    This endpoint exports all content records from the 'contents' table to JSON files
    in batches. Each batch file includes:
    - batch_id: Sequential batch number
    - timestamp: UTC timestamp of export
    - record_count: Number of records in this batch
    - checksum: MD5 checksum for data integrity validation
    - data: Array of content records

    Args:
        batch_size: Number of contents per batch file (1-1000, default: 25)
        output_dir: Directory to save export files (default: "exports")
        content_service: Injected ContentService for handling content operations

    Returns:
        dict with keys:
            - status: "success"
            - total_count: Total number of contents exported
            - batch_count: Number of batch files created
            - output_dir: Absolute path to output directory
            - files: List of exported file paths

    Raises:
        HTTPException: 500 if export fails
    """
    try:
        result = await content_service.aexport_contents_to_json_files(batch_size=batch_size, export_dir=output_dir)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export contents: {str(e)}")


@database_router.post(
    "/contents/import",
    description="Import contents from JSON files into database with validation",
    response_model=dict,
    status_code=200,
)
async def aimport_contents(
    input_dir: str = Query("exports", description="Directory containing export JSON files"),
    validate_checksums: bool = Query(True, description="Whether to validate checksums before importing"),
    content_service: ContentService = deps.depends(ContentService),
) -> dict:
    """Import contents from JSON files into the database.

    This endpoint imports content records from batch JSON files created by the export endpoint.
    It validates checksums (if enabled) and performs bulk inserts for efficiency.

    Args:
        input_dir: Directory containing batch_*.json files (default: "exports")
        validate_checksums: Whether to validate MD5 checksums before importing (default: True)
        content_service: Injected ContentService for handling content operations

    Returns:
        dict with keys:
            - status: "success", "partial_success", or "error"
            - total_imported: Total number of contents successfully imported
            - total_batches: Total number of batch files processed
            - failed_batches: List of batch filenames that failed
            - errors: List of error messages for failed batches

    Raises:
        HTTPException: 404 if input directory not found
        HTTPException: 400 if no batch files found
        HTTPException: 500 if critical error occurs
    """
    try:
        result = await content_service.aimport_contents_from_json_files(input_dir=input_dir, validate_checksums=validate_checksums)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import contents: {str(e)}")
