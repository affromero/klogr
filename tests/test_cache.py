"""Behavioral tests for the cache decorator."""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from klogr import DisableableLRUCache, lru_cache
from klogr.cache import is_lru_cache_disabled, show_all_cache_info


class CacheConfigurationTests(TestCase):
    """Exercise the decorator in a clean working directory."""

    def test_same_disable_scope_restores_state_after_nested_exception(
        self,
    ) -> None:
        """Restore the outer override, then the original configuration."""
        scope = DisableableLRUCache()
        with patch.dict(os.environ, {"DISABLE_LRU_CACHE": "False"}):
            with scope:
                try:
                    with scope:
                        assert is_lru_cache_disabled()
                        message = "exit the inner scope"
                        raise RuntimeError(message)
                except RuntimeError:
                    pass
                assert is_lru_cache_disabled()
            assert not is_lru_cache_disabled()

    def test_report_accepts_the_public_sync_wrapper(self) -> None:
        """Find cache statistics by the function returned by the decorator."""
        with patch.dict(os.environ, {"DISABLE_LRU_CACHE": "False"}):

            @lru_cache()
            def load() -> int:
                return 42

            assert load() == 42
            show_all_cache_info(load)

    def test_missing_dotenv_keeps_caching_enabled(self) -> None:
        """Cache calls without requiring a local config file."""
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, clear=True),
        ):
            previous = Path.cwd()
            try:
                os.chdir(directory)

                @lru_cache(print_cache_info=False)
                def load() -> object:
                    return object()

                assert load() is load()
            finally:
                os.chdir(previous)

    def test_disable_scope_bypasses_cache_for_new_decorators(self) -> None:
        """Produce distinct values while caching is disabled."""
        with DisableableLRUCache():

            @lru_cache(print_cache_info=False)
            def load() -> object:
                return object()

        assert load() is not load()

    def test_generator_hit_refreshes_eviction_order(self) -> None:
        """Keep a recently replayed sequence in a two-entry cache."""
        with patch.dict(os.environ, {"DISABLE_LRU_CACHE": "False"}):

            @lru_cache(maxsize=2, print_cache_info=False)
            def load(_key: str) -> Iterator[object]:
                yield object()

        first = list(load("first"))
        second = list(load("second"))
        assert first == list(load("first"))
        list(load("third"))
        assert first == list(load("first"))
        assert second != list(load("second"))


class AsyncCacheTests(IsolatedAsyncioTestCase):
    """Exercise coroutine and async sequence caching."""

    async def test_coroutine_hit_refreshes_eviction_order(self) -> None:
        """Keep the most recently read value in a two-entry cache."""
        with patch.dict(os.environ, {"DISABLE_LRU_CACHE": "False"}):

            @lru_cache(maxsize=2, print_cache_info=False)
            async def load(_key: str) -> object:
                return object()

        first = await load("first")
        second = await load("second")
        assert first is await load("first")
        await load("third")
        assert first is await load("first")
        assert second is not await load("second")

    async def test_async_generator_hit_refreshes_eviction_order(self) -> None:
        """Keep the most recently replayed async sequence."""
        with patch.dict(os.environ, {"DISABLE_LRU_CACHE": "False"}):

            @lru_cache(maxsize=2, print_cache_info=False)
            async def load(_key: str) -> AsyncIterator[object]:
                yield object()

        first = [value async for value in load("first")]
        second = [value async for value in load("second")]
        assert first == [value async for value in load("first")]
        async for _ in load("third"):
            pass
        assert first == [value async for value in load("first")]
        assert second != [value async for value in load("second")]

    async def test_overlapping_misses_preserve_the_cache(self) -> None:
        """Handle overlapping misses for the same key without corrupting eviction."""
        both_entered = asyncio.Event()
        allow_completion = asyncio.Event()
        entered = 0

        with patch.dict(os.environ, {"DISABLE_LRU_CACHE": "False"}):

            @lru_cache(maxsize=2, print_cache_info=False)
            async def load(key: str) -> object:
                nonlocal entered
                if key == "shared":
                    entered += 1
                    if entered == 2:
                        both_entered.set()
                    await allow_completion.wait()
                return object()

        tasks = [asyncio.create_task(load("shared")) for _ in range(2)]
        try:
            await asyncio.wait_for(both_entered.wait(), timeout=5)
        finally:
            allow_completion.set()
            await asyncio.gather(*tasks)
        first = await load("first")
        await load("second")
        assert first is await load("first")

    async def test_zero_and_unbounded_sizes(self) -> None:
        """Honor zero and unlimited capacities like functools.lru_cache."""
        with patch.dict(os.environ, {"DISABLE_LRU_CACHE": "False"}):

            @lru_cache(maxsize=0, print_cache_info=False)
            async def uncached(_key: list[int]) -> object:
                return object()

            @lru_cache(maxsize=None, print_cache_info=False)
            async def unbounded(_key: int) -> object:
                return object()

        assert await uncached([0]) is not await uncached([0])
        first = await unbounded(0)
        for key in range(1, 130):
            await unbounded(key)
        assert first is await unbounded(0)
