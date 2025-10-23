from fastapi import APIRouter
from infrastructure.fill_static_data_in_database_repository import DatabaseAdministrationRepository
from dependency_injection_config import deps
from facade.response_models.admin_response import AdminOperationResponse

admin_router = APIRouter(prefix="/admin", tags=["Admin"])


@admin_router.delete(
    "/database",
    description="Drop all database tables (PostgreSQL) or delete database",
    response_model=AdminOperationResponse,
    status_code=200,
)
async def adelete_database(database_admin_repository: DatabaseAdministrationRepository = deps.depends(DatabaseAdministrationRepository)) -> AdminOperationResponse:
    """Delete all database tables."""
    database_admin_repository.reset_database()
    return AdminOperationResponse(status="success", message="All database tables have been dropped successfully")


@admin_router.post(
    "/database/create",
    description="Create all database tables from entities",
    response_model=AdminOperationResponse,
    status_code=200,
)
async def acreate_database(database_admin_repository: DatabaseAdministrationRepository = deps.depends(DatabaseAdministrationRepository)) -> AdminOperationResponse:
    """Create all database tables based on entity definitions (User, Thread, Message, Role, etc.)."""
    await database_admin_repository.data_context.create_database_async()
    return AdminOperationResponse(status="success", message="Database tables created successfully")


@admin_router.post(
    "/database/data/fill",
    description="Fill static/reference data into database",
    response_model=AdminOperationResponse,
    status_code=200,
)
async def afill_static_data(database_admin_repository: DatabaseAdministrationRepository = deps.depends(DatabaseAdministrationRepository)) -> AdminOperationResponse:
    """Fill static/reference data into the database."""
    await database_admin_repository.afill_all_static_data()
    return AdminOperationResponse(status="success", message="Static data filled successfully (roles: user, assistant)")


@admin_router.post(
    "/database/reset",
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
