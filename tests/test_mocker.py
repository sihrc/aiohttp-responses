import pytest

from aiohttp_responses.mocker import MockAIOHTTPResponses


async def test_mock_url(mock_responses):
    with MockAIOHTTPResponses() as f:
        yield f

    mock_responses
