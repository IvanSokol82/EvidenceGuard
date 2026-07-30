import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ui_landing_page(async_client: AsyncClient):
    response = await async_client.get("/")
    assert response.status_code == 200
    assert "EvidenceGuard" in response.text
    assert "Черга перевірки" in response.text


@pytest.mark.asyncio
async def test_ui_documents_page(async_client: AsyncClient):
    response = await async_client.get("/ui/documents")
    assert response.status_code == 200
    assert "Затверджені документи компанії" in response.text


@pytest.mark.asyncio
async def test_ui_new_questionnaire_page(async_client: AsyncClient):
    response = await async_client.get("/ui/questionnaires/new")
    assert response.status_code == 200
    assert "Опрацювати новий security questionnaire" in response.text


@pytest.mark.asyncio
async def test_ui_review_page(async_client: AsyncClient):
    response = await async_client.get("/ui/review")
    assert response.status_code == 200
    assert "Черга ручної перевірки" in response.text
