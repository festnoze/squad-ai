"""Database helper utilities for repository initialization."""

from envvar import EnvHelper


class DatabaseHelper:
    """Helper class for database-related operations."""

    @staticmethod
    def build_postgres_connection_url(db_path_or_url: str | None = None) -> str:
        """Build PostgreSQL connection URL from environment variables or return provided URL.

        Args:
            db_path_or_url: Optional database path or URL. If provided, returns as-is.
                          If None, builds URL from environment variables.

        Returns:
            str: PostgreSQL connection URL in format: postgresql://username:password@host/dbname

        Example:
            >>> DatabaseHelper.build_postgres_connection_url()
            'postgresql://postgres:admin@localhost:5432/skillforge_dev'
            >>> DatabaseHelper.build_postgres_connection_url("postgresql://custom:pwd@host/db")
            'postgresql://custom:pwd@host/db'
        """
        if db_path_or_url:
            return db_path_or_url

        username = EnvHelper.get_postgres_username()
        password = EnvHelper.get_postgres_password()
        host = EnvHelper.get_postgres_host()
        dbname = EnvHelper.get_postgres_database_name()

        return f"postgresql://{username}:{password}@{host}/{dbname}"
