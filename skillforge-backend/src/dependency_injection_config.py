"""Dependency Injection Configuration

This module provides centralized dependency injection configuration using lagom.
It initializes the container and FastApiIntegration for use across the application.
"""

from lagom import Container
from lagom.integrations.fast_api import FastApiIntegration
from infrastructure.thread_repository import ThreadRepository
from infrastructure.user_repository import UserRepository
from infrastructure.school_repository import SchoolRepository
from infrastructure.context_repository import ContextRepository
from infrastructure.content_repository import ContentRepository, ContentRepositoryStudi
from infrastructure.llm_repository import LlmRepository
from infrastructure.fill_static_data_in_database_repository import DatabaseAdministrationRepository
from application.thread_service import ThreadService
from application.user_service import UserService
from application.content_service import ContentService


# Initialize the DI container (singleton instance)
container = Container()

# Register dependencies
container[ThreadRepository] = ThreadRepository
container[UserRepository] = UserRepository
container[SchoolRepository] = SchoolRepository
container[ContextRepository] = ContextRepository
container[ContentRepository] = ContentRepositoryStudi
container[LlmRepository] = LlmRepository
container[DatabaseAdministrationRepository] = DatabaseAdministrationRepository
#
container[ThreadService] = ThreadService
container[UserService] = UserService
container[ContentService] = ContentService

# Create FastAPI integration for dependency injection in routes
deps = FastApiIntegration(container)
