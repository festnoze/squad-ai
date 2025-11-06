"""Dependency Injection Configuration

This module provides centralized dependency injection configuration using lagom.
It initializes the container and FastApiIntegration for use across the application.
"""

from lagom import Container
from lagom.integrations.fast_api import FastApiIntegration
from envvar import EnvHelper
from infrastructure.thread_repository import ThreadRepository
from infrastructure.user_repository import UserRepository
from infrastructure.school_repository import SchoolRepository
from infrastructure.context_repository import ContextRepository
from infrastructure.content_repository import ContentRepository, ContentRepositoryStudi, ContentRepositoryBlackboard
from infrastructure.llm_service import LlmService
from infrastructure.role_repository import RoleRepository
from infrastructure.fill_static_data_in_database_repository import DatabaseAdministrationRepository
from infrastructure.course_hierarchy_repository import CourseHierarchyRepository
from application.thread_service import ThreadService
from application.user_service import UserService
from application.content_service import ContentService
from application.summary_service import SummaryService
from application.course_service import CourseService

# Initialize the DI container (singleton instance)
container = Container()

# Register dependencies
container[ThreadRepository] = ThreadRepository
container[UserRepository] = UserRepository
container[SchoolRepository] = SchoolRepository
container[ContextRepository] = ContextRepository
if EnvHelper.get_lms_type() == "studi":
    container[ContentRepository] = ContentRepositoryStudi  # type: ignore[type-abstract]
elif EnvHelper.get_lms_type() == "blackboard":
    container[ContentRepository] = ContentRepositoryBlackboard  # type: ignore[type-abstract]
else:
    raise ValueError(f"Unhandled LMS type in dependency_injection_config: '{EnvHelper.get_lms_type()}'")
container[LlmService] = LlmService
container[RoleRepository] = RoleRepository
container[DatabaseAdministrationRepository] = DatabaseAdministrationRepository
container[CourseHierarchyRepository] = CourseHierarchyRepository
#
container[ThreadService] = ThreadService
container[UserService] = UserService
container[ContentService] = ContentService
container[SummaryService] = SummaryService
container[CourseService] = CourseService

# Create FastAPI integration for dependency injection in routes
deps = FastApiIntegration(container)
