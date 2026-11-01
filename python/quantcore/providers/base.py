"""Data-provider contract: capabilities, permissions, quotas and rate limiting.

Network providers are never exercised by the default test suite: tests use recorded
fixtures (``tests/fixtures``) or injected fake modules.  Live access requires explicit
opt-in (``allow_network=True`` or ``QC_ALLOW_NETWORK=1``) plus credentials.
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from ..calendar import TradingCalendar, to_date_int
from ..data.panel import (
    PanelData,
    normalize_bars,
    normalize_corporate_actions,
    normalize_financials,
    normalize_securities,
)
from ..errors import ProviderError, ProviderPermissionError, ProviderUnavailableError


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a provider can deliver."""

    calendar: bool = True
    security_master: bool = True
    daily_bars: bool = True
    financials: bool = False
    corporate_actions: bool = False
    index_members: bool = False
    minute_bars: bool = False
    realtime: bool = False

    def supports(self, capability: str) -> bool:
        if not hasattr(self, capability):
            raise KeyError(f"unknown capability: {capability}")
        return bool(getattr(self, capability))

    def to_dict(self) -> dict[str, bool]:
        return {
            "calendar": self.calendar,
            "security_master": self.security_master,
            "daily_bars": self.daily_bars,
            "financials": self.financials,
            "corporate_actions": self.corporate_actions,
            "index_members": self.index_members,
            "minute_bars": self.minute_bars,
            "realtime": self.realtime,
        }


@dataclass(frozen=True)
class ProviderQuota:
    """Rate-limit / quota declaration for a provider tier."""

    max_calls: int | None = None
    window_seconds: float = 60.0
    daily_call_limit: int | None = None
    min_interval_seconds: float = 0.0
    tier: str = "free"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_calls": self.max_calls,
            "window_seconds": self.window_seconds,
            "daily_call_limit": self.daily_call_limit,
            "min_interval_seconds": self.min_interval_seconds,
            "tier": self.tier,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ProviderPermission:
    """Credential/licence requirements for a provider."""

    requires_credentials: bool = False
    env_vars: tuple[str, ...] = ()
    keyring_service: str | None = None
    license_note: str = ""

    def credentials_present(self, env: Mapping[str, str] | None = None) -> bool:
        if not self.requires_credentials:
            return True
        environment = env if env is not None else os.environ
        if any(environment.get(name) for name in self.env_vars):
            return True
        return self._keyring_lookup() is not None

    def resolve_credential(
        self,
        env: Mapping[str, str] | None = None,
        keyring_lookup: Callable[[str], str | None] | None = None,
    ) -> str | None:
        if not self.requires_credentials:
            return None
        environment = env if env is not None else os.environ
        for name in self.env_vars:
            value = environment.get(name)
            if value:
                return value
        if keyring_lookup is not None:
            return keyring_lookup(self.keyring_service or "")
        return self._keyring_lookup()

    def _keyring_lookup(self) -> str | None:
        if not self.keyring_service:
            return None
        try:  # keyring is optional at runtime; never hard-fail credential probing
            import keyring

            return keyring.get_password(self.keyring_service, "token")
        except Exception:  # pragma: no cover - keyring backend unavailable
            return None

    def describe(self) -> dict[str, Any]:
        return {
            "requires_credentials": self.requires_credentials,
            "env_vars": list(self.env_vars),
            "keyring_service": self.keyring_service,
            "license_note": self.license_note,
        }


class RateLimiter:
    """Deterministic token-bucket style limiter with injectable clock/sleep."""

    def __init__(
        self,
        quota: ProviderQuota,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.quota = quota
        self._clock = clock
        self._sleep = sleeper
        self._window_start = clock()
        self._window_calls = 0
        self._last_call: float | None = None
        self._day_key = time.strftime("%Y%m%d", time.gmtime(clock()))
        self._day_calls = 0

    def acquire(self, calls: int = 1) -> None:
        if calls < 1:
            raise ValueError("calls must be >= 1")
        if self.quota.daily_call_limit is not None:
            day_key = time.strftime("%Y%m%d", time.gmtime(self._clock()))
            if day_key != self._day_key:
                self._day_key, self._day_calls = day_key, 0
            if self._day_calls + calls > self.quota.daily_call_limit:
                raise ProviderError(
                    f"daily call limit {self.quota.daily_call_limit} exceeded for this provider"
                )
        if self.quota.min_interval_seconds > 0 and self._last_call is not None:
            wait = self.quota.min_interval_seconds - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        if self.quota.max_calls is not None:
            now = self._clock()
            if now - self._window_start >= self.quota.window_seconds:
                self._window_start, self._window_calls = now, 0
            if self._window_calls + calls > self.quota.max_calls:
                wait = self.quota.window_seconds - (now - self._window_start)
                if wait > 0:
                    self._sleep(wait)
                self._window_start, self._window_calls = self._clock(), 0
            self._window_calls += calls
        self._day_calls += calls
        self._last_call = self._clock()

    def snapshot(self) -> dict[str, Any]:
        return {
            "quota": self.quota.to_dict(),
            "window_calls": self._window_calls,
            "day_calls": self._day_calls,
        }


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: float = 0.0

    def delay_for_attempt(self, attempt: int) -> float:
        delay = min(self.max_delay, self.base_delay * (2 ** max(0, attempt - 1)))
        return delay + self.jitter


def retry_call[T](
    fn: Callable[[], T],
    policy: RetryPolicy | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    retry_on: tuple[type[BaseException], ...] = (ProviderError, OSError),
) -> T:
    """Call ``fn`` with bounded exponential backoff on transient provider errors."""
    effective = policy or RetryPolicy()
    last_error: BaseException | None = None
    for attempt in range(1, effective.attempts + 1):
        try:
            return fn()
        except retry_on as exc:
            last_error = exc
            if attempt >= effective.attempts:
                break
            sleeper(effective.delay_for_attempt(attempt))
    assert last_error is not None
    raise last_error


class DataProvider(ABC):
    """Contract every market-data provider implements."""

    name: ClassVar[str] = "base"
    capabilities: ClassVar[ProviderCapabilities] = ProviderCapabilities()
    quota: ClassVar[ProviderQuota] = ProviderQuota()
    permission: ClassVar[ProviderPermission] = ProviderPermission()

    def __init__(
        self,
        limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
        allow_network: bool = False,
    ) -> None:
        self.allow_network = allow_network
        self.retry_policy = retry or RetryPolicy()
        self.limiter = limiter or RateLimiter(self.quota)
        self._request_count = 0

    # -- capability / permission guards ----------------------------------
    def supports(self, capability: str) -> bool:
        return self.capabilities.supports(capability)

    def require(self, capability: str) -> None:
        if not self.supports(capability):
            raise ProviderUnavailableError(f"{self.name} does not provide {capability!r}")

    def require_permission(self) -> None:
        if not self.permission.credentials_present():
            envs = ", ".join(self.permission.env_vars) or "(none declared)"
            raise ProviderPermissionError(
                f"{self.name} requires credentials; set one of: {envs} "
                f"or store a token in keyring service {self.permission.keyring_service!r}"
            )

    def ensure_available(self) -> None:
        """Raise if the provider cannot be used in the current environment.

        The default implementation only enforces declared credentials; providers with
        optional dependencies or local files override it.
        """
        if self.permission.requires_credentials:
            self.require_permission()

    def quota_info(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "capabilities": self.capabilities.to_dict(),
            "quota": self.quota.to_dict(),
            "permission": self.permission.describe(),
            "requests_made": self._request_count,
        }

    # -- data access ------------------------------------------------------
    @abstractmethod
    def fetch_calendar(self, start: int | str, end: int | str) -> TradingCalendar:
        """Return the trading calendar for the requested window."""

    @abstractmethod
    def fetch_security_master(self) -> pd.DataFrame:
        """Return the securities master table in canonical form."""

    @abstractmethod
    def fetch_daily_bars(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        """Return daily bars in canonical form (one row per ``(date, sec_id)``)."""

    def fetch_financials(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        self.require("financials")
        raise NotImplementedError(f"{self.name} must implement fetch_financials")

    def fetch_corporate_actions(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        self.require("corporate_actions")
        raise NotImplementedError(f"{self.name} must implement fetch_corporate_actions")

    # -- convenience ------------------------------------------------------
    def fetch_panel(
        self,
        start: int | str,
        end: int | str,
        codes: Iterable[str] | None = None,
    ) -> PanelData:
        """Fetch calendar/master/bars (+ optional PIT data) and assemble a PanelData."""
        start_i, end_i = to_date_int(start), to_date_int(end)
        self.ensure_available()
        self._request_count += 1
        calendar = self.fetch_calendar(start_i, end_i)
        securities = normalize_securities(self.fetch_security_master())
        bars = normalize_bars(self.fetch_daily_bars(codes, start_i, end_i))
        financials = (
            normalize_financials(self.fetch_financials(codes, start_i, end_i))
            if self.supports("financials")
            else pd.DataFrame()
        )
        actions = (
            normalize_corporate_actions(self.fetch_corporate_actions(codes, start_i, end_i))
            if self.supports("corporate_actions")
            else pd.DataFrame()
        )
        return PanelData(
            calendar=calendar,
            securities=securities,
            bars=bars,
            financials=financials,
            corporate_actions=actions,
            meta={
                "provider": self.name,
                "source": "SYNTHETIC" if self.name == "synthetic" else self.name.upper(),
                "synthetic": self.name == "synthetic",
                "capabilities": self.capabilities.to_dict(),
                "quota": self.quota.to_dict(),
            },
        )


def subset_frame(
    frame: pd.DataFrame,
    start: int | None = None,
    end: int | None = None,
    date_column: str = "date",
    codes: Iterable[str] | None = None,
    code_column: str = "code",
) -> pd.DataFrame:
    """Filter a frame by date window and code list (shared by concrete providers)."""
    out = frame
    if start is not None:
        out = out[out[date_column] >= start]
    if end is not None:
        out = out[out[date_column] <= end]
    if codes is not None:
        wanted = set(codes)
        out = out[out[code_column].isin(wanted) | out["sec_id"].isin(wanted)]
    return out.reset_index(drop=True)


SYNTHETIC_PROVIDER_NOTE = "provider=synthetic: every value is SYNTHETIC"
