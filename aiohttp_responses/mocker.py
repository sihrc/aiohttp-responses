import asyncio
import json
import typing as t
from copy import deepcopy
from functools import partial
from unittest import mock
from unittest.mock import MagicMock
from urllib.parse import parse_qsl, urlencode

from aiohttp import (
    ClientRequest,
    ClientResponse,
    ClientSession,
    RequestInfo,
    StreamReader,
    hdrs,
)
from aiohttp.client_proto import ResponseHandler
from aiohttp.helpers import TimerNoop
from aiohttp.typedefs import URL, StrOrURL
from multidict import CIMultiDict, CIMultiDictProxy

from .context import Context

original_request: t.Callable[..., t.Coroutine] = ClientSession._request


class NoMatch(Exception):
    ...


def default_json_serializer(obj: t.Any):
    return json.dumps(obj).encode("utf-8")


class MockResponse:
    _default_content_type: str = "application/json"

    headers: dict[str, str]
    status: int
    status_reason: str | None
    body: bytes | None
    json: t.Any

    def __init__(
        self,
        status: int = 200,
        status_reason: str | None = None,
        headers: dict[str, str] | None = None,
        json: t.Any = None,
        body: str | bytes | None = None,
    ):
        self.headers = headers or {}
        self.headers[hdrs.CONTENT_TYPE] = self.headers.get(
            hdrs.CONTENT_TYPE, self._default_content_type
        )
        self.status = status
        self.status_reason = status_reason

        if json is not None and body is not None:
            raise ValueError("Can only accept one of 'json' or 'body' argument")

        self.json = json
        if isinstance(body, str):
            body = body.encode("utf-8")

        self.body = body

    def build_body(self, json_serializer: t.Callable[..., bytes]) -> bytes:
        if self.body is not None:
            return self.body
        return json_serializer(self.json)


def normalize_url(url: StrOrURL) -> URL:
    """Normalize url to make comparisons."""
    url = URL(url)
    return url.with_query(urlencode(sorted(parse_qsl(url.query_string))))


class MockAIOHTTPResponses:
    enabled: bool = False
    _patcher: mock._patcher
    _loop: Context[asyncio.AbstractEventLoop | None]
    _default_response_headers: Context[dict[str, str]]
    _json_serializer: Context[t.Callable[[t.Any], bytes]]
    _settable_contexts: tuple[str, ...] = (
        "loop",
        "response_headers",
        "json_serializer",
    )

    _mocks: Context[list[MockResponse]]
    _patch_instances: Context[list[ClientSession]]

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        response_headers: dict[str, str] | None = None,
        json_serializer: t.Callable[[t.Any], bytes] = default_json_serializer,
        patch_instances: list[ClientSession] | None = None,
        mocks: list[MockResponse] | None = None,
    ):
        self._loop = Context(loop)
        self._default_response_headers = Context(response_headers or {})
        self._json_serializer = Context(json_serializer)
        self._mocks = Context(mocks or [])
        self._patch_instances = Context(patch_instances or [])

        self.init_patch()

    @property
    def patch_instances(self) -> list[ClientSession]:
        return self._patch_instances.value

    @property
    def mocks(self) -> list[MockResponse]:
        return self._mocks.value

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop.value or asyncio.get_event_loop()

    @property
    def response_headers(self) -> dict[str, str]:
        return self._default_response_headers.value

    @property
    def json_serializer(self) -> t.Callable[[t.Any], bytes]:
        return self._json_serializer.value

    def match(self, method: str, str_or_url: StrOrURL, **req_kwargs) -> MockResponse:
        # TODO
        raise NoMatch()

    def add(self, method: str, url_pattern: str):
        # TODO
        pass

    def init_patch(self) -> None:
        async def mock_request(
            client_session: ClientSession,
            method: str,
            str_or_url: StrOrURL,
            **req_kwargs,
        ) -> ClientResponse:
            try:
                assert self.enabled
                mock_response: MockResponse = self.match(
                    method, str_or_url, **req_kwargs
                )
            except (NoMatch, AssertionError):
                return await original_request(
                    client_session, method, str_or_url, **req_kwargs
                )

            # FIXME: get proper URL based on match in case of pattern
            str_or_url = normalize_url(str_or_url)
            current_loop: asyncio.AbstractEventLoop = self.loop

            response: ClientResponse = client_session._response_class(
                method,
                str_or_url,
                request_info=RequestInfo(
                    url=str_or_url,
                    method=method,
                    headers=CIMultiDictProxy(
                        CIMultiDict(
                            **{
                                **self.response_headers,
                                **req_kwargs.get("request_headers", {}),
                            }
                        )
                    ),
                ),
                writer=MagicMock(),
                continue100=None,
                timer=TimerNoop(),
                loop=current_loop,
                session=client_session,
                traces=[],
            )

            # Set Response Headers
            response._headers = CIMultiDictProxy(CIMultiDict(mock_response.headers))
            response._raw_headers = self._build_raw_headers(mock_response.headers)

            # Set Cookies
            for hdr in response._headers.getall(hdrs.SET_COOKIE, ()):
                response.cookies.load(hdr)

            # Set Status
            response.status = mock_response.status
            response.reason = mock_response.status_reason

            stream_reader: StreamReader = StreamReader(
                ResponseHandler(loop=current_loop), limit=2**16, loop=current_loop
            )

            stream_reader.feed_data(
                mock_response.build_body(json_serializer=self.json_serializer)
            )
            stream_reader.feed_eof()
            response.content = stream_reader
            return response

        patcher: mock._patch = mock.patch.object(
            ClientSession, "_request", mock_request
        )
        patcher.start()

    def __enter__(self, **context_kwargs) -> "MockAIOHTTPResponses":
        self._mocks.set(deepcopy(self._mocks.value))
        self._mocks.value.extend(context_kwargs.get("mocks", []))

        self._patch_instances.set(deepcopy(self._patch_instances.value))
        self._patch_instances.value.extend(context_kwargs.get("patch_instances", []))

        for arg in self._settable_contexts:
            try:
                value: t.Any = context_kwargs[arg]
                context: Context = t.cast(Context, getattr(self, f"_{arg}"))
                context.set(value)
            except KeyError:
                pass

        self.enabled = True
        return self

    def __exit__(self, _, __, ___) -> None:
        for arg in self._settable_contexts:
            context: Context = t.cast(Context, getattr(self, f"_{arg}"))
            context.reset()

        self._mocks.reset()
        self._patch_instances.reset()

        self.enabled = False

    def _build_raw_headers(
        self, headers: dict[str, str]
    ) -> tuple[tuple[bytes, bytes], ...]:
        """
        Convert a dict of headers to a tuple of tuples

        Mimics the format of ClientResponse.
        """

        return tuple((k.encode("utf-8"), v.encode("utf-8")) for k, v in headers.items())


for method in ClientRequest.ALL_METHODS:
    setattr(
        MockAIOHTTPResponses, method, partial(MockAIOHTTPResponses.add, method=method)
    )
