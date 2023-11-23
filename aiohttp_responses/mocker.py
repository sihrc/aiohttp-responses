import asyncio
import json
import typing as t
from unittest import mock

from aiohttp import ClientResponse, ClientSession, RequestInfo, StreamReader, hdrs
from aiohttp.client_proto import ResponseHandler
from aiohttp.helpers import TimerNoop
from aiohttp.typedefs import StrOrURL
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
    body: bytes

    def __init__(
        self,
        status: int = 200,
        status_reason: str = None,
        headers: dict[str, str] = None,
        json: t.Any = None,
        body: str | bytes = None,
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
        self.body = body

    def build_body(self, json_serializer: t.Callable[..., bytes]) -> bytes:
        if self.body is not None:
            return self.body
        return json_serializer(self.json)


class MockAIOHTTPResponses:
    enabled: bool = False
    _patcher: mock._patcher
    _loop: Context[asyncio.BaseEventLoop | None]
    _default_response_headers: Context[dict[str, str]]
    _json_serializer: Context[t.Callable[[t.Any], bytes]]
    _settable_contexts: tuple[str] = ("loop", "response_headers", "json_serializer")

    def __init__(
        self,
        *,
        loop: asyncio.BaseEventLoop = None,
        response_headers: dict[str, str] = None,
        json_serializer: t.Callable[[t.Any], bytes] = default_json_serializer,
    ):
        self._loop = Context(loop)
        self._default_response_headers = Context(response_headers or {})
        self._json_serializer = Context(json_serializer)
        self.init_patch()

    def __enter__(self, **context_kwargs):
        for arg in self._settable_contexts:
            try:
                value: t.Any = context_kwargs[arg]
                context: Context = t.cast(Context, getattr(self, f"_{arg}"))
                context.set(value)
            except KeyError:
                pass

        self.enabled = True

    def __exit__(self, _, __, ___):
        for arg in self._settable_contexts:
            context: Context = t.cast(Context, getattr(self, f"_{arg}"))
            context.reset()

        self.enabled = False

    @property
    def loop(self) -> asyncio.BaseEventLoop:
        return self._loop.value or asyncio.get_event_loop()

    @property
    def response_headers(self) -> dict[str, str] | None:
        return self._default_response_headers.value

    @property
    def json_serializer(self) -> t.Callable([t.Any], bytes):
        return self._json_serializer.value

    def match(self, method: str, str_or_url: StrOrURL, **req_kwargs) -> MockResponse:
        # TODO
        raise NoMatch()

    def init_patch(self):
        async def mock_request(
            client_session: ClientSession,
            method: str,
            str_or_url: StrOrURL,
            **req_kwargs,
        ) -> ClientResponse:
            try:
                assert self.enabled
                mock_response: MockResponse = self.match(method, str_or_url, req_kwargs)
            except (NoMatch, AssertionError):
                return await original_request(
                    client_session, method, str_or_url, **req_kwargs
                )

            current_loop: asyncio.BaseEventLoop = self.loop

            response: ClientResponse = client_session._response_class(
                method,
                str_or_url,
                request_info=RequestInfo(
                    url=str_or_url,
                    method=method,
                    headers=CIMultiDictProxy(
                        **{
                            **self.response_headers,
                            **req_kwargs.get("request_headers", {}),
                        }
                    ),
                ),
                writer=None,
                continue100=None,
                timer=TimerNoop(),
                loop=current_loop,
                session=client_session,
            )

            # Set Response Headers
            response._headers = CIMultiDict(mock_response.headers)
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

    def _build_raw_headers(self, headers: dict[str, str]) -> tuple[bytes]:
        """
        Convert a dict of headers to a tuple of tuples

        Mimics the format of ClientResponse.
        """

        return tuple(
            item.encode("utf-8") for values in headers.items() for item in values
        )
