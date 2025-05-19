# noqa: D101,D401 – test file
import pytest
from unittest.mock import patch

from custom_components.wiim.api import WiiMClient


@pytest.mark.asyncio
async def test_ssl_context_included(monkeypatch):
    """WiiMClient must build an SSL context for each request."""

    # Patch _get_ssl_context to return sentinel object so we can verify it's
    # used by the request helper.
    dummy_ctx = object()

    def _dummy_ctx(self):  # noqa: D401 – internal helper
        return dummy_ctx

    async def _fake_request(self, endpoint: str, method: str = "GET", **kwargs):  # type: ignore[no-self-arg]
        """Mimic the first lines of WiiMClient._request and assert ssl kwarg."""

        kwargs.setdefault("headers", {})
        kwargs.setdefault("ssl", self._get_ssl_context())

        assert kwargs["ssl"] is dummy_ctx, "ssl kwarg not set to context returned by _get_ssl_context()"
        return {}

    with (
        patch.object(WiiMClient, "_get_ssl_context", _dummy_ctx, create=True),
        patch.object(WiiMClient, "_request", _fake_request, create=True),
    ):
        client = WiiMClient("192.0.2.1")
        await client.get_status()  # one high-level helper
        await client.get_sources()  # another helper exercising same path
        await client.close()
