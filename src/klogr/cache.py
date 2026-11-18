"""LRU cache with a disable hook, plus on-disk cache helpers."""

from __future__ import annotations

import functools
import inspect
import os
import sys
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextvars import ContextVar, Token
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeVar, cast, runtime_checkable

from beartype import beartype
from dotenv import dotenv_values
from jaxtyping import jaxtyped
from pydantic.dataclasses import dataclass
from sha256sum import sha256sum as _sha256sum

from .logger import get_logger
from .path import path_expanduser, path_join

if TYPE_CHECKING:
    from typing_extensions import Self

_Function = TypeVar("_Function", bound=Callable[..., object])
_Key = TypeVar("_Key")
_Value = TypeVar("_Value")

logger = get_logger()

# Runtime override for cache disabled state (None means use dotenv)
_lru_cache_disabled_override: ContextVar[bool | None] = ContextVar(
    "_lru_cache_disabled_override", default=None
)


@runtime_checkable
class _CachedFunction(Protocol):
    def cache_info(self) -> object: ...

    _original_qualname: str

    # Support both sync and async calls
    def __call__(self, *args: object, **kwargs: object) -> object: ...


@dataclass(eq=False, repr=False)
class CacheInfo:
    """Unified cache info class for both sync and async caches."""

    hits: int = 0
    misses: int = 0
    maxsize: int | None = None
    currsize: int = 0

    def __repr__(self) -> str:
        """Represent the cache info."""
        return f"CacheInfo(hits={self.hits}, misses={self.misses}, maxsize={self.maxsize}, currsize={self.currsize})"


_cached_functions: list[_CachedFunction] = []


def _get_cached_function_info(func: Callable[..., object]) -> str:
    """Get function info."""
    cache_info = (
        func.cache_info() if isinstance(func, _CachedFunction) else None
    )
    info = f" || {cache_info}" if cache_info else ""

    wrapped_func = inspect.unwrap(func)
    name = getattr(
        wrapped_func, "__qualname__", type(wrapped_func).__qualname__
    )

    try:
        file_info = f" (at {inspect.getfile(wrapped_func)}:{inspect.getsourcelines(wrapped_func)[1]})"
    except (OSError, TypeError):
        # Handle cases where source code can't be retrieved (e.g., decorated functions)
        file_info = (
            f" (at {getattr(wrapped_func, '__module__', 'unknown')}.{name})"
        )

    return f"{name}{file_info}{info}"


def _attach_cache_info(
    function: Callable[..., object], info: Callable[[], object], name: str
) -> _CachedFunction:
    vars(function).update(cache_info=info, _original_qualname=name)
    return cast("_CachedFunction", function)


def is_lru_cache_disabled() -> bool:
    """Check if LRU cache is disabled.

    Returns:
        True if cache is disabled via runtime override or DISABLE_LRU_CACHE env var.

    """
    override = _lru_cache_disabled_override.get()
    if override is not None:
        return override
    configured = os.getenv("DISABLE_LRU_CACHE")
    if configured is None:
        configured = dotenv_values(Path(".env")).get("DISABLE_LRU_CACHE")
    return configured == "True"


def _store_cached(
    cache: OrderedDict[_Key, _Value],
    key: _Key,
    value: _Value,
    *,
    maxsize: int | None,
) -> None:
    if maxsize is not None and maxsize <= 0:
        return
    cache[key] = value
    cache.move_to_end(key)
    if maxsize is not None and len(cache) > maxsize:
        cache.popitem(last=False)


class DisableableLRUCache:
    """Context manager to temporarily disable LRU cache.

    Example:
        >>> @lru_cache()
        >>> def expensive_function(x: int) -> int:
        >>>     return x * 2
        >>>
        >>> # Cache is enabled here
        >>> result1 = expensive_function(5)  # Cached
        >>>
        >>> with DisableableLRUCache():
        >>> # Cache is disabled within this block
        >>>     result2 = expensive_function(5)  # Not cached
        >>>
        >>> # Cache is re-enabled here
        >>> result3 = expensive_function(5)  # Cached again

    Note:
        This only affects functions decorated AFTER entering the context.
        Already-decorated functions that were decorated before the context
        will continue using their existing cache behavior since the decorator
        logic runs at decoration time, not call time.

    """

    _tokens: ContextVar[tuple[Token[bool | None], ...]]

    def __init__(self) -> None:
        """Initialize the context manager."""
        self._tokens = ContextVar("klogr_cache_scope_tokens", default=())

    def __enter__(self) -> Self:
        """Enter the context and disable LRU cache."""
        token = _lru_cache_disabled_override.set(True)
        self._tokens.set((*self._tokens.get(), token))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit the context and restore the previous cache state."""
        tokens = self._tokens.get()
        if tokens:
            _lru_cache_disabled_override.reset(tokens[-1])
            self._tokens.set(tokens[:-1])


def show_all_cache_info(
    func: Callable[..., object] | None = None,
) -> None:
    """Show cache info for all cached functions."""
    msg = "-" * 30 + "\n"
    msg += "Cached functions:\n" if func is None else "Cached function: "
    if func is None:
        funcs = _cached_functions
    else:
        funcs = [_func for _func in _cached_functions if _func == func]
        if len(funcs) == 0:
            name = getattr(func, "__qualname__", type(func).__qualname__)
            error = f"Function {name} not found in cache"
            raise ValueError(error)
    for _func in funcs:
        # hits means the function was called with the same arguments
        # misses means the function was called with different arguments
        msg += _get_cached_function_info(_func) + "\n"
    msg += "-" * 30 + "\n"
    logger.debug(msg, stack_offset=2)


def lru_cache(
    maxsize: int | None = 128,
    *,
    max_misses: int = -1,
    print_cache_info: bool = True,
) -> Callable[[_Function], _Function]:
    """Decorate a function with functools.lru_cache, unless in unit test mode.

    This decorator wraps a function with functools.lru_cache, providing
        caching functionality for the function's results. However, if the code is
        running in unit test mode, the decorator is a no-op and does not provide caching.

    Supports sync functions, async functions, regular generators, and async generators.
        For generators (both sync and async), the sequence of yielded values is cached
        and re-yielded on subsequent calls with the same arguments.

    Arguments:
        maxsize (int | None): The maximum size of the cache. Defaults to 128.
        max_misses (int): The maximum number of misses before raising a cache miss error. Defaults to -1 (disabled).
        print_cache_info (bool): Whether to print the cache info. Defaults to True.

    Returns:
        Callable: The decorated function. If in unit test mode, returns the
            original function without caching. Otherwise, returns the function
            wrapped with lru_cache, providing caching of its results.

    Example:
        >>> @lru_cache()
        >>> def example_function(arg1, arg2):
        >>>     return arg1 + arg2
        >>> @lru_cache()
        >>> def gen_example(arg1):
        >>>     for i in range(arg1):
        >>>         yield i
        >>> @lru_cache()
        >>> async def async_example(arg1, arg2):
        >>>     return arg1 + arg2
        >>> @lru_cache()
        >>> async def async_gen_example(arg1):
        >>>     for i in range(arg1):
        >>>         yield i
    Note:
        This decorator is useful for preventing caching during unit tests,
            where repeated function calls with the same arguments are often needed.

    """

    def decorator(func: _Function) -> _Function:
        """Apply an LRU cache to the input function or return the function itself.

        This decorator function applies an LRU cache to the given function
            if the code is not running in unittest mode. If it is in
            unittest mode, the function is returned as is.

        Arguments:
            func (Callable[..., object]): The function to be decorated.

        Returns:
            Callable[..., object]: The decorated function with an applied LRU
                cache if not in unittest mode, or the original function if
                in unittest mode.

        Example:
            >>> @lru_cache()
            >>> def test_func(x, y):
            >>>     return x + y
        Note:
            This decorator is useful for optimizing functions that are
                called repeatedly with the same arguments, but should not be
                used in unittest mode to avoid cached results.

        """
        call: Callable[..., object] = func
        name = getattr(call, "__qualname__", type(call).__qualname__)
        has_capacity = maxsize is None or maxsize > 0
        # Check if function is async, async generator, or regular generator
        is_async = inspect.iscoroutinefunction(func)
        is_async_gen = inspect.isasyncgenfunction(func)
        is_gen = inspect.isgeneratorfunction(func)

        # Use cache when not in unit test mode
        if not is_lru_cache_disabled():
            # ------------------------------
            # REGULAR GENERATORS
            # ------------------------------
            if is_gen:
                # For regular generators, cache the sequence of yielded values
                gen_cache: OrderedDict[tuple[object, ...], list[object]] = (
                    OrderedDict()
                )
                gen_hits = 0
                gen_misses = 0

                def _create_cached_generator(
                    args: tuple[object, ...],
                    kwargs_items: tuple[tuple[str, object], ...],
                ) -> Iterator[object]:
                    """Create a generator that yields from cached values or computes new ones."""
                    nonlocal gen_hits, gen_misses

                    # Create cache key
                    key = (args, kwargs_items)

                    # Check if sequence is cached
                    if has_capacity and key in gen_cache:
                        gen_cache.move_to_end(key)
                        gen_hits += 1
                        if print_cache_info:
                            logger.debug(f"Cache hit for generator {name}")
                        # Yield from cached sequence
                        for value in gen_cache[key]:
                            yield value
                        return

                    # Compute result by consuming the generator
                    gen_misses += 1
                    cached_values: list[object] = []
                    gen = cast(
                        "Iterator[object]", call(*args, **dict(kwargs_items))
                    )
                    for value in gen:
                        cached_values.append(value)
                        yield value

                    _store_cached(
                        gen_cache, key, cached_values, maxsize=maxsize
                    )

                    if print_cache_info:
                        logger.debug(
                            f"Cached sequence for generator {name} (cache size: {len(gen_cache)}, sequence length: {len(cached_values)})"
                        )

                    # Check max misses
                    if max_misses != -1 and gen_misses > max_misses:
                        msg = f"Function {name} has {gen_misses} cache misses. This is too many. This is probably a bug. If not, update the max_misses parameter."
                        raise ValueError(msg)

                @functools.wraps(func)
                def gen_cached_wrapper(
                    *args: object, **kwargs: object
                ) -> Iterator[object]:
                    """Cache yielded sequences."""
                    # Create cache key components
                    kwargs_items = tuple(sorted(kwargs.items()))
                    # Return a generator that handles caching
                    return _create_cached_generator(args, kwargs_items)

                # Add a unified cache_info method
                def cache_info() -> CacheInfo:
                    """Get the cache info."""
                    return CacheInfo(
                        hits=gen_hits,
                        misses=gen_misses,
                        maxsize=maxsize,
                        currsize=len(gen_cache),
                    )

                _cached_functions.append(
                    _attach_cache_info(gen_cached_wrapper, cache_info, name)
                )

                return cast("_Function", gen_cached_wrapper)

            # ------------------------------
            # ASYNC GENERATORS
            # ------------------------------
            if is_async_gen:
                # For async generators, cache the sequence of yielded values
                async_gen_cache: OrderedDict[
                    tuple[object, ...], list[object]
                ] = OrderedDict()
                async_gen_hits = 0
                async_gen_misses = 0

                async def _create_cached_async_generator(
                    args: tuple[object, ...],
                    kwargs_items: tuple[tuple[str, object], ...],
                ) -> AsyncIterator[object]:
                    """Create an async generator that yields from cached values or computes new ones."""
                    nonlocal async_gen_hits, async_gen_misses

                    # Create cache key
                    key = (args, kwargs_items)

                    # Check if sequence is cached
                    if has_capacity and key in async_gen_cache:
                        async_gen_cache.move_to_end(key)
                        async_gen_hits += 1
                        if print_cache_info:
                            logger.debug(
                                f"Cache hit for async generator {name}"
                            )
                        # Yield from cached sequence
                        for value in async_gen_cache[key]:
                            yield value
                        return

                    # Compute result by consuming the generator
                    async_gen_misses += 1
                    cached_values: list[object] = []
                    async_gen = cast(
                        "AsyncIterator[object]",
                        call(*args, **dict(kwargs_items)),
                    )
                    async for value in async_gen:
                        cached_values.append(value)
                        yield value

                    _store_cached(
                        async_gen_cache, key, cached_values, maxsize=maxsize
                    )

                    if print_cache_info:
                        logger.debug(
                            f"Cached sequence for async generator {name} (cache size: {len(async_gen_cache)}, sequence length: {len(cached_values)})"
                        )

                    # Check max misses
                    if max_misses != -1 and async_gen_misses > max_misses:
                        msg = f"Function {name} has {async_gen_misses} cache misses. This is too many. This is probably a bug. If not, update the max_misses parameter."
                        raise ValueError(msg)

                @functools.wraps(func)
                def async_gen_cached_wrapper(
                    *args: object, **kwargs: object
                ) -> AsyncIterator[object]:
                    """Async generator wrapper that caches yielded sequences."""
                    # Create cache key components
                    kwargs_items = tuple(sorted(kwargs.items()))
                    # Return an async generator that handles caching
                    return _create_cached_async_generator(args, kwargs_items)

                # Add a unified cache_info method
                def cache_info() -> CacheInfo:
                    """Get the cache info."""
                    return CacheInfo(
                        hits=async_gen_hits,
                        misses=async_gen_misses,
                        maxsize=maxsize,
                        currsize=len(async_gen_cache),
                    )

                _cached_functions.append(
                    _attach_cache_info(
                        async_gen_cached_wrapper, cache_info, name
                    )
                )

                return cast("_Function", async_gen_cached_wrapper)

            # ------------------------------
            # SYNC FUNCTIONS
            # ------------------------------
            if not is_async:
                # For sync functions, use functools lru_cache
                cached_func = functools.lru_cache(
                    maxsize=maxsize, typed=False
                )(func)

                # Create a wrapper that calls show_all_cache_info() on execution
                @functools.wraps(cached_func)
                def cached_wrapper(*args: object, **kwargs: object) -> object:
                    """Wrap that shows cache info on execution and preserves cache functionality."""
                    output = cached_func(*args, **kwargs)
                    info = cached_func.cache_info()
                    if print_cache_info:
                        show_all_cache_info(cached_wrapper)
                    if max_misses != -1 and info.misses > max_misses:
                        msg = f"Function {name} has {info.misses} cache misses. This is too many. This is probably a bug. If not, update the max_misses parameter."
                        raise ValueError(msg)
                    return output

                # Preserve the cache_info method and other attributes
                _cached_functions.append(
                    _attach_cache_info(
                        cached_wrapper, cached_func.cache_info, name
                    )
                )

                return cast("_Function", cached_wrapper)

            # ------------------------------
            # ASYNC FUNCTIONS
            # ------------------------------

            # For regular async functions, implement manual caching with unified CacheInfo
            async_cache: OrderedDict[tuple[object, ...], object] = (
                OrderedDict()
            )
            async_hits = 0
            async_misses = 0

            @functools.wraps(func)
            async def async_cached_wrapper(
                *args: object, **kwargs: object
            ) -> object:
                """Async wrapper that caches results properly."""
                nonlocal async_hits, async_misses

                # Create cache key
                key = (args, tuple(sorted(kwargs.items())))

                # Check if result is cached
                if has_capacity and key in async_cache:
                    async_cache.move_to_end(key)
                    async_hits += 1
                    if print_cache_info:
                        logger.info(
                            f"Cache hit for async {name} (hits={async_hits}, misses={async_misses})"
                        )
                    return async_cache[key]

                # Compute result
                async_misses += 1
                if print_cache_info:
                    logger.info(
                        f"Cache miss for async {name} - executing function (hits={async_hits}, misses={async_misses})"
                    )
                result = await cast("Awaitable[object]", call(*args, **kwargs))

                _store_cached(async_cache, key, result, maxsize=maxsize)

                if print_cache_info:
                    logger.debug(
                        f"Cached result for async {name} (cache size: {len(async_cache)})"
                    )

                # Check max misses
                if max_misses != -1 and async_misses > max_misses:
                    msg = f"Function {name} has {async_misses} cache misses. This is too many. This is probably a bug. If not, update the max_misses parameter."
                    raise ValueError(msg)

                return result

            # Add a unified cache_info method
            def cache_info() -> CacheInfo:
                """Get the cache info."""
                return CacheInfo(
                    hits=async_hits,
                    misses=async_misses,
                    maxsize=maxsize,
                    currsize=len(async_cache),
                )

            _cached_functions.append(
                _attach_cache_info(async_cached_wrapper, cache_info, name)
            )

            return cast("_Function", async_cached_wrapper)

        # No-operation decorator
        # ------------------------------
        # PASSTHROUGH DECORATORS
        # ------------------------------

        # ------------------------------
        # ASYNC GENERATORS
        # ------------------------------
        if is_async_gen:

            @functools.wraps(func)
            async def async_gen_wrapper(
                *args: object, **kwargs: object
            ) -> AsyncIterator[object]:
                """Async generator wrapper that passes through when cache is disabled."""
                logger.warning(
                    f"{_get_cached_function_info(func)} has @lru_cache but it is disabled!"
                )
                async for value in cast(
                    "AsyncIterator[object]", call(*args, **kwargs)
                ):
                    yield value

            return cast("_Function", async_gen_wrapper)

        # ------------------------------
        # REGULAR GENERATORS
        # ------------------------------
        if is_gen:

            @functools.wraps(func)
            def gen_wrapper(
                *args: object, **kwargs: object
            ) -> Iterator[object]:
                """Pass through generator when cache is disabled."""
                logger.warning(
                    f"{_get_cached_function_info(func)} has @lru_cache but it is disabled!"
                )
                yield from cast("Iterator[object]", call(*args, **kwargs))

            return cast("_Function", gen_wrapper)

        # ------------------------------
        # ASYNC FUNCTIONS
        # ------------------------------
        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args: object, **kwargs: object) -> object:
                """Async wrapper that passes through when cache is disabled."""
                logger.warning(
                    f"{_get_cached_function_info(func)} has @lru_cache but it is disabled!"
                )
                return await cast("Awaitable[object]", call(*args, **kwargs))

            return cast("_Function", async_wrapper)

        # ------------------------------
        # SYNC FUNCTIONS
        # ------------------------------
        @functools.wraps(func)
        def wrapper(*args: object, **kwargs: object) -> object:
            """Act as a wrapper for another function, preserving its.

                metadata and allowing flexible argument passing.

            This function can be used to wrap another function,
                maintaining its metadata. It accepts any number of
                positional and keyword arguments, which are passed
                directly to the wrapped function.

            Arguments:
                *args (object): Represents any number of positional
                    arguments that can be passed to the wrapped
                    function.
                **kwargs (object): Represents any number of keyword
                    arguments that can be passed to the wrapped
                    function.

            Returns:
                object: Returns the result of calling the wrapped function
                    with the provided arguments and keyword arguments.

            Example:
                >>> wrapped_function =
                    wrapper_function(original_function, arg1, arg2,
                    keyword_arg1=value1)

            Note:
                The wrapped function and its arguments are not specified
                    until the wrapper function is called.

            """
            logger.warning(
                f"{_get_cached_function_info(func)} has @lru_cache but it is disabled!"
            )
            return call(*args, **kwargs)

        return cast("_Function", wrapper)

    return decorator


def get_cache_dir() -> str:
    """Locate a platform-appropriate cache directory for flit to use.

    This function identifies the appropriate cache directory for the
        specified platform and app. It does not ensure
    that the cache directory exists.

    Arguments:
        platform (str): The platform for which the cache directory is to be
            located.
        app (str): The application for which the cache directory is to be
            located.
        flit (bool | None): A flag indicating if flit is to be used.
            Defaults to None.

    Returns:
        str: The path of the located cache directory.

    Example:
        >>> locate_cache_dir("Windows", "flit", flit=True)

    Note:
        The function does not create the cache directory, it only locates
            the appropriate directory for the given platform and app.

    """
    # Linux, Unix, AIX, etc.
    if os.name == "posix" and sys.platform != "darwin":
        # use ~/.cache if empty OR not set
        cache_dir = os.environ.get("XDG_CACHE_HOME", None) or path_expanduser(
            "~/.cache"
        )

    # Mac OS
    elif sys.platform == "darwin":
        cache_dir = path_join(path_expanduser("~"), "Library/Caches")

    # Windows
    else:
        cache_dir = os.environ.get("LOCALAPPDATA", "") or path_expanduser(
            "~\\AppData\\Local",
        )

    return cache_dir


@jaxtyped(typechecker=beartype)
def sha256sum(filename: str) -> str:
    """Calculate the SHA-256 hash of a file and return the first 8 characters.

    This function takes a filename as an argument, calculates the SHA-256
        hash of the file, and returns the first 8 characters of the hash.

    Arguments:
        filename (str): A string representing the name of the file for which
            the SHA-256 hash needs to be calculated.

    Returns:
        str: A string containing the first 8 characters of the SHA-256 hash
            of the file.

    Example:
        >>> calculate_file_hash("example.txt")

    Note:
        The file must exist in the current working directory or a full path
            must be provided.

    """
    return _sha256sum(filename)[:8]
