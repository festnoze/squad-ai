import asyncio
import logging
from functools import wraps
from typing import Any, Callable
from inspect import signature
from typing import get_type_hints, get_origin, get_args

#
from infrastructure.caching.cache_service import CacheService


def cache_retrieval_or_caching(key_pattern: str, ttl: int | None = None) -> Callable[..., Any]:
    """
    Decorator for automatic retrieving from Redis Cache first, if not found - caching of decorated method results.

    Args:
        key_pattern: Cache key pattern with placeholders for method arguments.
                     Use {arg_name} for named arguments or {0}, {1} for positional.
                     Special placeholder {self.attr} accesses instance attributes.
        ttl: Time-to-live in seconds. If None, uses default from env vars.

    Examples:
        @cache_retrieval_or_caching("thread:{thread_id}:page:{page_number}:size:{page_size}", ttl=600)
        async def aget_thread_by_id(self, thread_id: UUID, page_number: int = 0, page_size: int = 0):
            ...

        @cache_retrieval_or_caching("user:{user_id}", ttl=1800)
        async def aget_user_by_id(self, user_id: UUID):
            ...

        @cache_retrieval_or_caching("thread:{self.thread_id}:messages", ttl=300)
        async def aget_messages(self):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Skip caching if cache is disabled
            if not CacheService.is_enabled():
                return await func(*args, **kwargs)

            # Get function signature to map args to parameter names
            sig = signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            # Build the cache key by replacing placeholders
            cache_key = key_pattern

            # Replace {arg_name} with actual values
            for param_name, param_value in bound_args.arguments.items():
                placeholder = f"{{{param_name}}}"
                if placeholder in cache_key:
                    cache_key = cache_key.replace(placeholder, str(param_value))

            # Replace {self.attr} with instance attribute values
            if "{self." in cache_key and len(args) > 0:
                self_obj = args[0]
                import re

                for match in re.finditer(r"\{self\.(\w+)\}", cache_key):
                    attr_name = match.group(1)
                    if hasattr(self_obj, attr_name):
                        attr_value = getattr(self_obj, attr_name)
                        cache_key = cache_key.replace(match.group(0), str(attr_value))

            # Get return type annotation to handle Pydantic model deserialization
            type_hints = get_type_hints(func)
            return_type = type_hints.get("return", None)

            # Handle Optional[Model] or Model | None annotations
            actual_return_type = return_type
            if return_type is not None:
                origin = get_origin(return_type)
                # Check for Union types (including Optional which is Union[X, None])
                if origin is type(None) or str(origin) == "typing.Union":
                    type_args = get_args(return_type)
                    # Filter out NoneType to get the actual model type
                    non_none_types = [t for t in type_args if t is not type(None)]
                    if non_none_types:
                        actual_return_type = non_none_types[0]

            # Try to get from cache first (only if cache is available)
            cached_value = None
            try:
                cached_value = await CacheService.aget(cache_key)
            except asyncio.CancelledError:
                # If cancelled during cache access, re-raise immediately
                raise
            except Exception as e:
                # Cache access failed (possibly during shutdown) - continue without cache
                logger = logging.getLogger(__name__)
                logger.debug(f"Cache access failed for key '{cache_key}': {e}")

            if cached_value is not None:
                logger = logging.getLogger(__name__)
                logger.debug(f"Cache hit for key '{cache_key}'")

                # If cached value is a dict and return type is a Pydantic model, deserialize
                if isinstance(cached_value, dict) and actual_return_type is not None:
                    if hasattr(actual_return_type, "model_validate"):
                        return actual_return_type.model_validate(cached_value)

                return cached_value

            # Cache miss - execute the method
            logger = logging.getLogger(__name__)
            logger.debug(f"Cache miss for key '{cache_key}', executing method")

            try:
                result = await func(*args, **kwargs)
            except asyncio.CancelledError:
                # If the main function is cancelled, re-raise immediately
                raise

            # Cache the result (only if cache is still available)
            if result is not None:
                try:
                    await CacheService.aadd(cache_key, result, ttl=ttl)
                    logger.debug(f"Cached result for key '{cache_key}'")
                except asyncio.CancelledError:
                    # If cancelled during cache write, re-raise
                    raise
                except Exception as e:
                    # Cache write failed (possibly during shutdown) - continue without caching
                    logger.debug(f"Failed to cache result for key '{cache_key}': {e}")

            return result

        return wrapper

    return decorator
