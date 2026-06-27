"""Tiny threaded map with progress + per-item error isolation.

LLM calls are IO-bound, so a thread pool gives a large speedup. Each item is
isolated: an exception in one item is logged and returned as None rather than
killing the whole (expensive) run. Input order is preserved.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable


def thread_map(fn: Callable, items: list, workers: int = 8, label: str | None = None,
               every: int = 25) -> list:
    results = [None] * len(items)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception as e:  # isolate: one bad item shouldn't abort the run
                print(f"    [{label or 'task'}] item {i} failed: {type(e).__name__}: {e}")
                results[i] = None
            done += 1
            if label and done % every == 0:
                print(f"    [{label}] {done}/{len(items)}")
    return results
