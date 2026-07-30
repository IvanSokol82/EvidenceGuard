import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_exports_markdown_json_email(async_client: AsyncClient, db_session_fixture: None = None):
    # Test export endpoint handling for non-existing questionnaire (404)
    fake_id = uuid.uuid4()
    resp_md = await async_client.get(f"/exports/{fake_id}/markdown")
    assert resp_md.status_code == 404

    resp_json = await async_client.get(f"/exports/{fake_id}/json")
    assert resp_json.status_code == 404

    resp_email = await async_client.get(f"/exports/{fake_id}/email")
    assert resp_email.status_code == 404
