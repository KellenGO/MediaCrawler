"""Small serial provider-chain executor for platform search paths.

This module deliberately knows nothing about a platform, cookies, or result
models.  A provider returns the number of results it emitted.  A zero-result
return is a valid success; only an exception before the first emitted result
may advance to the next eligible provider.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional, Sequence, Union


ProviderRun = Callable[[], Awaitable[int]]
ProviderCleanup = Callable[[], Awaitable[None]]
ProviderEligible = Union[bool, Callable[[], bool]]
ProviderEmitted = Callable[[], int]


@dataclass(frozen=True)
class SearchProvider:
    """One serial attempt in a platform's provider chain."""

    id: str
    run: ProviderRun
    eligible: ProviderEligible = True
    cleanup: Optional[ProviderCleanup] = None
    emitted_count: ProviderEmitted = lambda: 0
    fallback_reason: Optional[str] = None


@dataclass
class ProviderChainTrace:
    """Safe execution metadata; provider IDs only."""

    provider_used: Optional[str] = None
    provider_attempts: List[str] = field(default_factory=list)
    fallback_active: bool = False
    fallback_reason: Optional[str] = None

    @property
    def provider_attempt_count(self) -> int:
        return len(self.provider_attempts)


@dataclass(frozen=True)
class ProviderChainResult:
    provider_used: Optional[str]
    provider_attempts: List[str]
    fallback_active: bool
    fallback_reason: Optional[str]
    emitted_count: int


def _is_eligible(provider: SearchProvider) -> bool:
    value = provider.eligible
    return bool(value() if callable(value) else value)


async def _cleanup(provider: SearchProvider) -> None:
    if provider.cleanup is None:
        return
    try:
        await provider.cleanup()
    except Exception:
        # Cleanup must not turn a successful search into a failed one. The
        # provider owns the concrete resource and may log its own diagnostics.
        pass


async def run_provider_chain(
    providers: Sequence[SearchProvider],
    *,
    trace: Optional[ProviderChainTrace] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> ProviderChainResult:
    """Run eligible providers serially with conservative fallback semantics."""

    trace = trace or ProviderChainTrace()
    eligible = [provider for provider in providers if _is_eligible(provider)]

    for index, provider in enumerate(eligible):
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()

        trace.provider_used = provider.id
        trace.provider_attempts.append(provider.id)
        try:
            emitted_count = max(0, int(await provider.run()))
        except asyncio.CancelledError:
            await _cleanup(provider)
            raise
        except Exception:
            emitted_count = max(0, int(provider.emitted_count()))
            await _cleanup(provider)
            # A partially emitted provider owns the result stream. Re-running
            # the query through another provider could duplicate or reorder it.
            if emitted_count > 0 or index >= len(eligible) - 1:
                raise
            trace.fallback_active = True
            trace.fallback_reason = provider.fallback_reason or "provider_failed"
            continue

        await _cleanup(provider)
        return ProviderChainResult(
            provider_used=trace.provider_used,
            provider_attempts=list(trace.provider_attempts),
            fallback_active=trace.fallback_active,
            fallback_reason=trace.fallback_reason,
            emitted_count=emitted_count,
        )

    return ProviderChainResult(
        provider_used=trace.provider_used,
        provider_attempts=list(trace.provider_attempts),
        fallback_active=trace.fallback_active,
        fallback_reason=trace.fallback_reason,
        emitted_count=0,
    )
