"""
Redis cache service for SkillForge API (activated with: REDIS_ENABLED=True).

This module provides a centralized caching service using Redis for storing
and retrieving frequently accessed data with configurable TTL (Time To Live).
"""

import json
import logging
from typing import Any, Callable, Awaitable
from redis import asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError

#
from envvar import EnvHelper
from infrastructure.caching.caching_type_encoders import UUIDEncoder


class CacheService:
    """
    Async Redis cache service for managing cached data.

    Provides methods to get, set, delete, and check existence of cached items
    with automatic JSON serialization/deserialization.

    Methods can be used explicitly'as this' or through the use of the caching decorator which automatically
    handles the retrieving, else calling the method and caching the result (see caching_decorator.py).
    """

    _instance: Redis | None = None
    _enabled: bool = True

    @classmethod
    async def ainitialize(cls) -> None:
        """
        Initialize the Redis connection pool.

        Should be called once during application startup.
        """
        logger = logging.getLogger(__name__)
        cls._enabled = EnvHelper.get_redis_enabled()

        if not cls._enabled:
            logger.info("Redis caching is disabled via REDIS_ENABLED=False")
            cls._instance = None
            return

        try:
            cls._instance = await aioredis.from_url(
                f"redis://{EnvHelper.get_redis_host()}:{EnvHelper.get_redis_port()}",
                db=EnvHelper.get_redis_db(),
                password=EnvHelper.get_redis_password(),
                decode_responses=True,
                encoding="utf-8",
            )
            # Test connection
            ping_res = cls._instance.ping()
            if ping_res and isinstance(ping_res, Awaitable):
                await ping_res
                logger.info(f"Redis cache initialized successfully at {EnvHelper.get_redis_host()}:{EnvHelper.get_redis_port()} (db={EnvHelper.get_redis_db()})")
        except RedisError as e:
            logger.warning(f"Failed to connect to Redis: {e}. Caching will be disabled.")
            cls._enabled = False
            cls._instance = None
        except Exception as e:
            logger.error(f"Unexpected error initializing Redis: {e}")
            cls._enabled = False
            cls._instance = None

    @classmethod
    async def aclose(cls) -> None:
        """
        Close the Redis connection pool.

        Should be called during application shutdown.
        """
        logger = logging.getLogger(__name__)
        if cls._instance:
            await cls._instance.aclose()
            cls._instance = None
            logger.info("Redis cache connection closed")

    @classmethod
    async def aget_or_set(cls, key: str, method: Callable, ttl: int | None = None, *args: Any, **kwargs: Any) -> Any | None:
        """
        Get a value from cache or execute a method if not found, then cache the result.

        Args:
            key: Cache key
            method: Async method to call if cache miss
            ttl: Time-to-live in seconds. If None, uses default from env vars
            *args: Positional arguments to pass to the method
            **kwargs: Keyword arguments to pass to the method

        Returns:
            Cached or freshly computed value
        """
        logger = logging.getLogger(__name__)

        # Try to get from cache first
        cached_value = await cls.aget(key)
        if cached_value is not None:
            logger.debug(f"Cache hit for key '{key}'")
            return cached_value

        logger.debug(f"Cache miss for key '{key}', executing method")

        # Cache miss - execute the method
        result = await method(*args, **kwargs)

        # Cache the result
        if result is not None:
            await cls.aadd(key, result, ttl=ttl)
            logger.debug(f"Cached result for key '{key}'")

        return result

    @classmethod
    async def aget(cls, key: str) -> Any | None:
        """
        Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value (deserialized from JSON) or None if not found or cache disabled
        """
        logger = logging.getLogger(__name__)
        if not cls._enabled or not cls._instance:
            return None

        try:
            value = await cls._instance.get(key)
            if value is None:
                return None
            return json.loads(value)
        except RedisError as e:
            logger.warning(f"Redis GET error for key '{key}': {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to deserialize cached value for key '{key}': {e}")
            return None

    @classmethod
    async def aadd(cls, key: str, value: Any, ttl: int | None = None) -> bool:
        """
        Set a value in cache.

        Args:
            key: Cache key
            value: Value to cache (Pydantic models or JSON-serializable data)
            ttl: Time-to-live in seconds. If None, uses default from env vars

        Returns:
            True if successful, False otherwise

        Note:
            Automatically handles Pydantic models by calling model_dump(mode="json")
            to properly serialize UUIDs and datetime objects.
        """
        logger = logging.getLogger(__name__)
        if not cls._enabled or not cls._instance:
            return False

        try:
            # Check if value is a Pydantic model (has model_dump method)
            if hasattr(value, "model_dump"):
                data_to_cache = value.model_dump(mode="json")
            else:
                data_to_cache = value

            serialized_value = json.dumps(data_to_cache, cls=UUIDEncoder)
            expire_time = ttl if ttl is not None else EnvHelper.get_redis_ttl()
            await cls._instance.setex(key, expire_time, serialized_value)
            return True
        except (RedisError, TypeError, ValueError) as e:
            logger.warning(f"Redis SET error for key '{key}': {e}")
            return False

    @classmethod
    async def adelete(cls, key: str) -> bool:
        """
        Delete a key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False otherwise
        """
        logger = logging.getLogger(__name__)
        if not cls._enabled or not cls._instance:
            return False

        try:
            result = await cls._instance.delete(key)
            return int(result) > 0
        except RedisError as e:
            logger.warning(f"Redis DELETE error for key '{key}': {e}")
            return False

    @classmethod
    async def aexists(cls, key: str) -> bool:
        """
        Check if a key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        logger = logging.getLogger(__name__)
        if not cls._enabled or not cls._instance:
            return False

        try:
            result = await cls._instance.exists(key)
            return int(result) > 0
        except RedisError as e:
            logger.warning(f"Redis EXISTS error for key '{key}': {e}")
            return False

    @classmethod
    async def adelete_pattern(cls, pattern: str) -> int:
        """
        Delete all keys matching a pattern.

        Args:
            pattern: Key pattern (e.g., "user:*", "thread:123:*")

        Returns:
            Number of keys deleted
        """
        logger = logging.getLogger(__name__)
        if not cls._enabled or not cls._instance:
            return 0

        try:
            keys = await cls._instance.keys(pattern)
            if not keys:
                return 0
            return int(await cls._instance.delete(*keys))
        except RedisError as e:
            logger.warning(f"Redis DELETE_PATTERN error for pattern '{pattern}': {e}")
            return 0

    @classmethod
    async def aclear_all(cls) -> bool:
        """
        Clear all keys in the current Redis database.

        WARNING: This will delete ALL cached data in the current DB.

        Returns:
            True if successful, False otherwise
        """
        logger = logging.getLogger(__name__)
        if not cls._enabled or not cls._instance:
            return False

        try:
            await cls._instance.flushdb()
            logger.info("Redis cache cleared (FLUSHDB)")
            return True
        except RedisError as e:
            logger.error(f"Redis FLUSHDB error: {e}")
            return False

    @classmethod
    async def aget_ttl(cls, key: str) -> int:
        """
        Get the remaining time-to-live for a key.

        Args:
            key: Cache key

        Returns:
            TTL in seconds, -1 if key has no expiry, -2 if key doesn't exist
        """
        logger = logging.getLogger(__name__)
        if not cls._enabled or not cls._instance:
            return -2

        try:
            ttl = await cls._instance.ttl(key)
            return int(ttl)
        except RedisError as e:
            logger.warning(f"Redis TTL error for key '{key}': {e}")
            return -2

    @classmethod
    def is_enabled(cls) -> bool:
        """
        Check if caching is enabled and available.

        Returns:
            True if caching is enabled, False otherwise
        """
        return cls._enabled and cls._instance is not None
