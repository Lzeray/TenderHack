"""The production React entry point and its hashed assets are reachable through FastAPI."""
import re

import pytest
from fastapi.testclient import TestClient

from ktru_assist.api import WEB, app


@pytest.mark.skipif(not (WEB / "index.html").exists(), reason="сначала npm run build в frontend/")
def test_react_entry_and_assets_are_served():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="root"' in response.text and 'type="module"' in response.text
    assets = re.findall(r'(?:src|href)="(/static/assets/[^\"]+)"', response.text)
    assert len(assets) >= 2
    for url in assets:
        asset = client.get(url)
        assert asset.status_code == 200
        assert "javascript" in asset.headers["content-type"] or "text/css" in asset.headers["content-type"]
