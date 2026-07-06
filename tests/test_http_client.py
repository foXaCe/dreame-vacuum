"""Behavioural tests for the async HTTP transport (``dreame.http_client``).

``AsyncHttpClient`` is exercised against a real, ephemeral ``aiohttp.web``
server (no mocking of the transport itself). ``BlockingHttpClient`` is
exercised through its public blocking API, including from real background
threads, to lock down the private-event-loop facade behaviour: lazy
creation, session reset, shutdown, and the "never call me from a running
loop" guard.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
import socket
import threading

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from custom_components.dreame_vacuum.dreame.http_client import (
    AsyncHttpClient,
    BlockingHttpClient,
    HttpConnectionError,
    HttpRequestError,
    HttpTimeoutError,
)

# ---------------------------------------------------------------------------
# Shared test server application
# ---------------------------------------------------------------------------


async def _echo(request: web.Request) -> web.Response:
    body = await request.read()
    payload = {
        "method": request.method,
        "query": dict(request.query),
        "headers": {k: v for k, v in request.headers.items() if k.lower().startswith("x-")},
        "cookies": dict(request.cookies),
        "body": body.decode("utf-8", errors="replace"),
    }
    return web.json_response(payload)


async def _set_cookie(request: web.Request) -> web.Response:
    resp = web.json_response({"ok": True})
    resp.set_cookie("session", "abc123", domain="localhost")
    return resp


async def _redirect(request: web.Request) -> web.Response:
    raise web.HTTPFound(location="/echo")


async def _sleep(request: web.Request) -> web.Response:
    seconds = float(request.query.get("seconds", "2"))
    await asyncio.sleep(seconds)
    return web.json_response({"slept": seconds})


def _build_app() -> web.Application:
    app = web.Application()
    app.router.add_route("GET", "/echo", _echo)
    app.router.add_route("POST", "/echo", _echo)
    app.router.add_route("GET", "/set-cookie", _set_cookie)
    app.router.add_route("GET", "/redirect", _redirect)
    app.router.add_route("GET", "/sleep", _sleep)
    return app


def _closed_port_url() -> str:
    """Return a URL pointing at a port nothing is listening on (connection refused)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}/nope"


# ---------------------------------------------------------------------------
# Async fixture: real aiohttp server for AsyncHttpClient (async tests only)
# ---------------------------------------------------------------------------


@pytest.fixture
async def server() -> AsyncIterator[TestServer]:
    srv = TestServer(_build_app(), host="localhost")
    await srv.start_server()
    try:
        yield srv
    finally:
        await srv.close()


@pytest.fixture
def base_url(server: TestServer) -> str:
    return str(server.make_url("/")).rstrip("/")


# ---------------------------------------------------------------------------
# Sync fixture: a threaded server for BlockingHttpClient (sync tests only —
# pytest-asyncio fixtures cannot be consumed by synchronous test functions).
# ---------------------------------------------------------------------------


class _ThreadedServer:
    """Runs the same aiohttp app on a dedicated thread/loop for sync tests."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._runner: web.AppRunner
        self.port: int
        fut = asyncio.run_coroutine_threadsafe(self._start(), self._loop)
        fut.result(timeout=10)

    async def _start(self) -> None:
        self._runner = web.AppRunner(_build_app())
        await self._runner.setup()
        site = web.TCPSite(self._runner, "localhost", 0)
        await site.start()
        server_obj = site._server
        assert server_obj is not None
        self.port = server_obj.sockets[0].getsockname()[1]

    @property
    def base_url(self) -> str:
        return f"http://localhost:{self.port}"

    def stop(self) -> None:
        fut = asyncio.run_coroutine_threadsafe(self._runner.cleanup(), self._loop)
        fut.result(timeout=10)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10)


@pytest.fixture
def sync_server() -> Iterator[_ThreadedServer]:
    srv = _ThreadedServer()
    try:
        yield srv
    finally:
        srv.stop()


# ---------------------------------------------------------------------------
# AsyncHttpClient — GET / POST / params / headers
# ---------------------------------------------------------------------------


async def test_async_get_returns_status_and_body(base_url: str) -> None:
    client = AsyncHttpClient()
    try:
        resp = await client.get(f"{base_url}/echo")
        assert resp.status == 200
        assert resp.json()["method"] == "GET"
    finally:
        await client.close()


async def test_async_get_sends_params(base_url: str) -> None:
    client = AsyncHttpClient()
    try:
        resp = await client.get(f"{base_url}/echo", params={"a": 1, "b": "x"})
        assert resp.json()["query"] == {"a": "1", "b": "x"}
    finally:
        await client.close()


async def test_async_post_sends_body(base_url: str) -> None:
    client = AsyncHttpClient()
    try:
        resp = await client.post(f"{base_url}/echo", data=b"hello world")
        data = resp.json()
        assert data["method"] == "POST"
        assert data["body"] == "hello world"
    finally:
        await client.close()


async def test_async_request_sends_custom_headers(base_url: str) -> None:
    client = AsyncHttpClient()
    try:
        resp = await client.get(f"{base_url}/echo", headers={"X-Test": "42"})
        assert resp.json()["headers"]["X-Test"] == "42"
    finally:
        await client.close()


async def test_http_response_text_and_json_helpers(base_url: str) -> None:
    client = AsyncHttpClient()
    try:
        resp = await client.get(f"{base_url}/echo")
        assert isinstance(resp.text, str)
        assert resp.json() == {
            "method": "GET",
            "query": {},
            "headers": {},
            "cookies": {},
            "body": "",
        }
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# AsyncHttpClient — cookies (per-request + persistent + dedup + lookup)
# ---------------------------------------------------------------------------


async def test_async_request_scoped_cookies_are_sent(base_url: str) -> None:
    client = AsyncHttpClient()
    try:
        resp = await client.get(f"{base_url}/echo", cookies={"foo": "bar"})
        assert resp.json()["cookies"]["foo"] == "bar"
    finally:
        await client.close()


async def test_async_set_cookie_before_session_persists_on_first_request(base_url: str) -> None:
    """set_cookie() before any request queues it; it is applied when the session is created."""
    client = AsyncHttpClient()
    try:
        client.set_cookie("persist", "value1", "localhost")
        resp = await client.get(f"{base_url}/echo")
        assert resp.json()["cookies"]["persist"] == "value1"
    finally:
        await client.close()


async def test_async_set_cookie_after_session_applies_immediately(base_url: str) -> None:
    """set_cookie() called once a session already exists is applied to that session's jar right away."""
    client = AsyncHttpClient()
    try:
        await client.get(f"{base_url}/echo")  # creates the session first
        client.set_cookie("late", "v1", "localhost")
        resp = await client.get(f"{base_url}/echo")
        assert resp.json()["cookies"]["late"] == "v1"
    finally:
        await client.close()


async def test_async_set_cookie_dedups_on_re_set(base_url: str) -> None:
    """Re-setting the same (name, domain) cookie replaces the old value, no duplicates."""
    client = AsyncHttpClient()
    try:
        client.set_cookie("persist", "value1", "localhost")
        client.set_cookie("persist", "value2", "localhost")
        assert client._cookies == [("persist", "value2", "localhost")]

        resp = await client.get(f"{base_url}/echo")
        assert resp.json()["cookies"]["persist"] == "value2"
    finally:
        await client.close()


async def test_async_session_cookie_lookup(base_url: str) -> None:
    client = AsyncHttpClient()
    try:
        client.set_cookie("sess", "tok", "localhost")
        await client.get(f"{base_url}/echo")  # materializes the session + jar
        assert client.session_cookie("sess") == "tok"
        assert client.session_cookie("missing-cookie") is None
    finally:
        await client.close()


async def test_async_session_cookie_none_before_any_session() -> None:
    client = AsyncHttpClient()
    assert client.session_cookie("anything") is None


async def test_async_response_reflects_server_set_cookie(base_url: str) -> None:
    client = AsyncHttpClient()
    try:
        resp = await client.get(f"{base_url}/set-cookie")
        assert resp.cookies["session"] == "abc123"
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# AsyncHttpClient — redirects
# ---------------------------------------------------------------------------


async def test_async_redirect_followed_by_default(base_url: str) -> None:
    client = AsyncHttpClient()
    try:
        resp = await client.get(f"{base_url}/redirect")
        assert resp.status == 200
        assert resp.json()["method"] == "GET"
    finally:
        await client.close()


async def test_async_redirect_not_followed_when_disabled(base_url: str) -> None:
    client = AsyncHttpClient()
    try:
        resp = await client.get(f"{base_url}/redirect", allow_redirects=False)
        assert resp.status == 302
        assert "/echo" in resp.headers.get("Location", "")
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# AsyncHttpClient — timeouts, connection errors, generic transport errors
# ---------------------------------------------------------------------------


async def test_async_timeout_raises_http_timeout_error(base_url: str) -> None:
    client = AsyncHttpClient()
    try:
        with pytest.raises(HttpTimeoutError):
            await client.get(f"{base_url}/sleep", params={"seconds": 2}, timeout=0.2)
    finally:
        await client.close()


async def test_async_connection_refused_raises_http_connection_error() -> None:
    client = AsyncHttpClient()
    try:
        with pytest.raises(HttpConnectionError):
            await client.get(_closed_port_url(), timeout=5)
    finally:
        await client.close()


async def test_async_generic_client_error_raises_http_request_error() -> None:
    """An unsupported URL scheme is a ClientError that is neither timeout nor connection."""
    client = AsyncHttpClient()
    try:
        with pytest.raises(HttpRequestError) as exc_info:
            await client.get("ftp://localhost/nope")
        assert not isinstance(exc_info.value, HttpConnectionError)
        assert not isinstance(exc_info.value, HttpTimeoutError)
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# AsyncHttpClient — session lifecycle
# ---------------------------------------------------------------------------


async def test_async_close_then_recreate_session(base_url: str) -> None:
    client = AsyncHttpClient()
    resp1 = await client.get(f"{base_url}/echo")
    assert resp1.status == 200
    session1 = client._session
    assert session1 is not None

    await client.close()
    assert client._session is None

    resp2 = await client.get(f"{base_url}/echo")
    assert resp2.status == 200
    assert client._session is not None
    assert client._session is not session1
    await client.close()


async def test_async_close_idempotent_without_prior_session() -> None:
    client = AsyncHttpClient()
    await client.close()  # must not raise
    assert client._session is None


async def test_async_external_session_is_never_closed(base_url: str) -> None:
    async with aiohttp.ClientSession() as external:
        client = AsyncHttpClient(session=external)
        resp = await client.get(f"{base_url}/echo")
        assert resp.status == 200

        await client.close()

        assert not external.closed
        assert client._session is None  # the private slot was never used


async def test_async_external_session_receives_set_cookie(base_url: str) -> None:
    async with aiohttp.ClientSession() as external:
        client = AsyncHttpClient(session=external)
        client.set_cookie("ext", "1", "localhost")

        assert any(cookie.key == "ext" for cookie in external.cookie_jar)
        assert client.session_cookie("ext") == "1"


# ---------------------------------------------------------------------------
# BlockingHttpClient — calls from a real background thread
# ---------------------------------------------------------------------------


def test_blocking_get_from_worker_thread(sync_server: _ThreadedServer) -> None:
    client = BlockingHttpClient()
    results: list = []
    errors: list = []

    def worker() -> None:
        try:
            resp = client.get(f"{sync_server.base_url}/echo", params={"k": "v"})
            results.append(resp)
        except Exception as ex:  # pragma: no cover - defensive, surfaced via assert below
            errors.append(ex)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=10)

    try:
        assert not errors, errors
        assert len(results) == 1
        resp = results[0]
        assert resp.status == 200
        assert resp.json()["query"] == {"k": "v"}
    finally:
        client.shutdown()


def test_blocking_post_from_worker_thread(sync_server: _ThreadedServer) -> None:
    client = BlockingHttpClient()
    results: list = []

    def worker() -> None:
        resp = client.post(f"{sync_server.base_url}/echo", data=b"payload")
        results.append(resp)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=10)

    try:
        assert len(results) == 1
        assert results[0].json()["body"] == "payload"
    finally:
        client.shutdown()


# ---------------------------------------------------------------------------
# BlockingHttpClient — running-loop guard
# ---------------------------------------------------------------------------


async def test_blocking_client_from_running_loop_raises_runtime_error() -> None:
    """Calling the blocking facade from a coroutine (running loop) is a programming error."""
    client = BlockingHttpClient()
    with pytest.raises(RuntimeError, match="must not be called from an event loop"):
        client.get("http://127.0.0.1:1/unused")


# ---------------------------------------------------------------------------
# BlockingHttpClient — cookies delegation
# ---------------------------------------------------------------------------


def test_blocking_set_cookie_and_session_cookie_delegate(sync_server: _ThreadedServer) -> None:
    client = BlockingHttpClient()
    try:
        client.set_cookie("blk", "v1", "localhost")
        resp = client.get(f"{sync_server.base_url}/echo")
        assert resp.json()["cookies"]["blk"] == "v1"
        assert client.session_cookie("blk") == "v1"
    finally:
        client.shutdown()


# ---------------------------------------------------------------------------
# BlockingHttpClient — session / loop lifecycle
# ---------------------------------------------------------------------------


def test_blocking_close_session_noop_before_any_request() -> None:
    client = BlockingHttpClient()
    client.close_session()  # loop never started -> must be a silent no-op


def test_blocking_close_session_then_new_request_recreates_session(sync_server: _ThreadedServer) -> None:
    client = BlockingHttpClient()
    try:
        client.get(f"{sync_server.base_url}/echo")
        session1 = client._async_client._session
        assert session1 is not None

        client.close_session()
        assert client._async_client._session is None

        client.get(f"{sync_server.base_url}/echo")
        session2 = client._async_client._session
        assert session2 is not None
        assert session2 is not session1
    finally:
        client.shutdown()


def test_blocking_shutdown_noop_when_never_started() -> None:
    client = BlockingHttpClient()
    client.shutdown()  # must not raise


def test_blocking_shutdown_stops_loop_and_joins_thread(sync_server: _ThreadedServer) -> None:
    client = BlockingHttpClient()
    client.get(f"{sync_server.base_url}/echo")
    loop = client._loop
    thread = client._loop_thread
    assert loop is not None
    assert thread is not None
    assert thread.is_alive()

    client.shutdown()

    assert client._loop is None
    assert client._loop_thread is None
    assert not thread.is_alive()
    assert not loop.is_running()


def test_blocking_shutdown_then_new_call_relaunches_lazily(sync_server: _ThreadedServer) -> None:
    client = BlockingHttpClient()
    client.get(f"{sync_server.base_url}/echo")
    client.shutdown()

    resp = client.get(f"{sync_server.base_url}/echo")

    try:
        assert resp.status == 200
        assert client._loop is not None
        assert client._loop_thread is not None
    finally:
        client.shutdown()


def test_blocking_run_future_timeout_cancels_future_and_raises(sync_server: _ThreadedServer) -> None:
    """A coroutine that outlives the future's own result() timeout raises HttpTimeoutError.

    ``_run`` waits ``timeout + 5.0`` seconds on the future itself (a margin over the
    inner aiohttp timeout), so the only way to hit that specific branch behaviourally
    is to run a coroutine that blocks past that margin — this test takes ~5s for real.
    """
    client = BlockingHttpClient()
    try:
        with pytest.raises(HttpTimeoutError):
            client._run(lambda: asyncio.sleep(10), timeout=0.01)
    finally:
        client.shutdown()
