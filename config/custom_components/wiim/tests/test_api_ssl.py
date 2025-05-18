import pytest

from config.custom_components.wiim.api import WiiMClient


@pytest.mark.asyncio
async def test_ssl_context_included(monkeypatch):
    """Ensure each request passes an SSLContext or False fallback."""

    async def dummy_request(self, endpoint: str, method: str = "GET", **kwargs):  # type: ignore[no-self-arg]
        assert "ssl" in kwargs
        return {}

    monkeypatch.setattr(WiiMClient, "_request", dummy_request, raising=True)

    client = WiiMClient("192.0.2.1")
    await client.get_status()
    await client.close()
