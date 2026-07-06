"""Async HTTP transport for the Dreame cloud protocols.

Step 1 of the incremental async migration (strangler pattern): the HTTP
layer is async-native (``aiohttp``) so it can later run directly on the
Home Assistant event loop with an injected websession. Until the device
and protocol layers move off their dedicated worker threads, those threads
drive the async core through :class:`BlockingHttpClient`, a thin blocking
facade that owns a private event loop in a single daemon thread.

Design constraints:
- The facade NEVER touches the Home Assistant event loop — requests run on
  a private loop, so a slow cloud call can never stall HA.
- Everything is lazy: the loop thread and the ``aiohttp.ClientSession`` are
  created on first use and can be recreated after ``close_session()`` /
  ``shutdown()`` (the protocols reset their session on every login).
- Exceptions are normalized to :class:`HttpTimeoutError` /
  :class:`HttpConnectionError` / :class:`HttpRequestError` so the protocol
  code does not depend on the transport library.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
import threading
from typing import Any

import aiohttp

# Read the whole body of every response we accept; map downloads are a few MB.
_DEFAULT_TIMEOUT = 30.0


class HttpRequestError(Exception):
    """Base error for a failed HTTP exchange (transport-level)."""


class HttpTimeoutError(HttpRequestError):
    """The request timed out."""


class HttpConnectionError(HttpRequestError):
    """The connection could not be established or was dropped."""


@dataclass(frozen=True)
class HttpResponse:
    """Transport-agnostic response snapshot (body fully read)."""

    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)
    cookies: Mapping[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Return the body decoded as UTF-8 (errors replaced)."""
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """Parse the body as JSON."""
        return json.loads(self.text)


class AsyncHttpClient:
    """aiohttp-based client owning (or borrowing) a ``ClientSession``.

    When ``session`` is provided (e.g. Home Assistant's shared websession in
    the final async architecture) it is borrowed and never closed by this
    class. Otherwise a private session is created lazily on the running loop.
    """

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._external_session = session
        self._session: aiohttp.ClientSession | None = None
        self._cookies: list[tuple[str, str, str]] = []

    def set_cookie(self, name: str, value: str, domain: str) -> None:
        """Register a cookie applied to the session (survives session resets)."""
        self._cookies = [(n, v, d) for n, v, d in self._cookies if (n, d) != (name, domain)]
        self._cookies.append((name, value, domain))
        if (session := self._active_session()) is not None:
            session.cookie_jar.update_cookies({name: value}, response_url=_cookie_url(domain))

    def _active_session(self) -> aiohttp.ClientSession | None:
        return self._external_session or self._session

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._external_session is not None:
            return self._external_session
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            for name, value, domain in self._cookies:
                self._session.cookie_jar.update_cookies({name: value}, response_url=_cookie_url(domain))
        return self._session

    def session_cookie(self, name: str) -> str | None:
        """Return a cookie value from the session jar (any domain), if present."""
        if (session := self._active_session()) is None:
            return None
        for cookie in session.cookie_jar:
            if cookie.key == name:
                return cookie.value
        return None

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        data: Any = None,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        allow_redirects: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> HttpResponse:
        """Execute a request and return the fully-read response.

        Raises:
            HttpTimeoutError: on timeout.
            HttpConnectionError: on connection-level failures.
            HttpRequestError: on any other transport error.
        """
        session = self._ensure_session()
        try:
            async with session.request(
                method,
                url,
                headers=dict(headers) if headers else None,
                data=data,
                params={k: str(v) for k, v in params.items()} if params else None,
                cookies=dict(cookies) if cookies else None,
                allow_redirects=allow_redirects,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                body = await response.read()
                return HttpResponse(
                    status=response.status,
                    body=body,
                    headers=dict(response.headers),
                    cookies={key: morsel.value for key, morsel in response.cookies.items()},
                )
        except TimeoutError as ex:
            raise HttpTimeoutError(str(ex) or "timed out") from ex
        except aiohttp.ClientConnectionError as ex:
            raise HttpConnectionError(str(ex)) from ex
        except aiohttp.ClientError as ex:
            raise HttpRequestError(str(ex)) from ex

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        allow_redirects: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> HttpResponse:
        """HTTP GET."""
        return await self.request(
            "GET",
            url,
            headers=headers,
            params=params,
            cookies=cookies,
            allow_redirects=allow_redirects,
            timeout=timeout,
        )

    async def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        data: Any = None,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> HttpResponse:
        """HTTP POST."""
        return await self.request(
            "POST",
            url,
            headers=headers,
            data=data,
            params=params,
            cookies=cookies,
            timeout=timeout,
        )

    async def close(self) -> None:
        """Close the private session (borrowed sessions are left untouched)."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None


def _cookie_url(domain: str) -> Any:
    """Build the response_url anchor aiohttp needs to scope a cookie to a domain."""
    from yarl import URL

    return URL(f"https://{domain.lstrip('.')}/")


class BlockingHttpClient:
    """Blocking facade over :class:`AsyncHttpClient` for legacy worker threads.

    Runs a private event loop in one daemon thread; calls submitted from the
    protocol worker threads block on ``run_coroutine_threadsafe(...).result()``.
    Calling it from a running event loop is a programming error and raises
    immediately instead of deadlocking.
    """

    def __init__(self) -> None:
        self._async_client = AsyncHttpClient()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ loop
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                loop = asyncio.new_event_loop()
                thread = threading.Thread(target=loop.run_forever, name="dreame-http", daemon=True)
                thread.start()
                self._loop = loop
                self._loop_thread = thread
            return self._loop

    def _run(self, coro_factory: Callable[[], Any], timeout: float) -> Any:
        # The coroutine is only created after the running-loop guard so that a
        # misuse from the event loop does not leave an un-awaited coroutine.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError("BlockingHttpClient must not be called from an event loop; use AsyncHttpClient instead")
        loop = self._ensure_loop()
        # Margin over the aiohttp timeout so the transport error (not a bare
        # concurrent.futures.TimeoutError) is what callers see.
        future = asyncio.run_coroutine_threadsafe(coro_factory(), loop)
        try:
            return future.result(timeout=timeout + 5.0)
        except TimeoutError as ex:
            future.cancel()
            raise HttpTimeoutError("timed out") from ex

    # --------------------------------------------------------------- requests
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        allow_redirects: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> HttpResponse:
        """Blocking HTTP GET (worker threads only)."""
        return self._run(
            lambda: self._async_client.get(
                url,
                headers=headers,
                params=params,
                cookies=cookies,
                allow_redirects=allow_redirects,
                timeout=timeout,
            ),
            timeout,
        )

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        data: Any = None,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> HttpResponse:
        """Blocking HTTP POST (worker threads only)."""
        return self._run(
            lambda: self._async_client.post(
                url,
                headers=headers,
                data=data,
                params=params,
                cookies=cookies,
                timeout=timeout,
            ),
            timeout,
        )

    def set_cookie(self, name: str, value: str, domain: str) -> None:
        """Register a cookie on the underlying async client."""
        self._async_client.set_cookie(name, value, domain)

    def session_cookie(self, name: str) -> str | None:
        """Return a cookie value from the session jar (any domain), if present."""
        return self._async_client.session_cookie(name)

    # ---------------------------------------------------------------- teardown
    def close_session(self) -> None:
        """Drop the current HTTP session (next request opens a fresh one).

        The protocols call this on every (re)login to reset cookies and
        connections, mirroring the old ``requests.session()`` swap.
        """
        with self._lock:
            loop = self._loop
        if loop is None or not loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(self._async_client.close(), loop)
        future.result(timeout=10.0)

    def shutdown(self) -> None:
        """Close the session and stop the private loop thread for good."""
        with self._lock:
            loop, thread = self._loop, self._loop_thread
            self._loop = None
            self._loop_thread = None
        if loop is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self._async_client.close(), loop).result(timeout=10.0)
        loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=10.0)
