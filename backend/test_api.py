import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api import app, QueryRequest, QueryResponse
import prompts
from llm_client import call_gemini, call_claude
from vectorstore import vectorstore

client = TestClient(app)

def test_prompts_exist():
    """Verify all four prompt templates exist in prompts.py."""
    assert hasattr(prompts, "QUERY_REWRITE_PROMPT")
    assert hasattr(prompts, "ANSWER_PROMPT")
    assert hasattr(prompts, "VERIFY_PROMPT")
    assert hasattr(prompts, "FORMAT_PROMPT")

def test_call_gemini_mock():
    """Verify call_gemini wrapper invokes Gemini client properly."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Test Gemini Output"
    mock_client.models.generate_content.return_value = mock_response

    output = call_gemini(prompt="Hello", system="Test system", client=mock_client)
    assert output == "Test Gemini Output"
    mock_client.models.generate_content.assert_called_once()

def test_query_endpoint_zero_chunks():
    """Verify POST /api/query returns fallback response when vectorstore returns 0 chunks."""
    with patch("vectorstore.vectorstore.query", return_value=[]), \
         patch("api.call_gemini") as mock_call_gemini:
        
        response = client.post("/api/query", json={"query": "What are LCR requirements?"})
        
        assert response.status_code == 200
        data = response.json()
        assert "not enough indexed data" in data["answer"].lower()
        assert data["citations"] == []
        assert data["effective_dates"] == []

def test_query_endpoint_pipeline_success():
    """Verify full 6-step RAG pipeline execution on query endpoint."""
    fake_chunks = [
        {"id": "c1", "text": "LCR must be at least 100% for banks.", "metadata": {"circular": "RBI/2026/01"}}
    ]

    llm_responses = [
        '["query 1", "query 2"]', # step 1 rewrite
        "Banks must maintain an LCR of 100%.", # step 3 answer
        '{"verified_claims": ["LCR 100%"], "unverified_claims": ["Extra claim"]}', # step 4 verify
        '''{
            "answer": "Banks must maintain a minimum LCR of 100%.",
            "citations": [{"circular_no": "RBI/2026/01", "section": "1", "excerpt": "LCR 100%", "url": null}],
            "effective_dates": [{"provision": "LCR maintenance", "date": "2026-06-01"}],
            "impacted_teams": ["Treasury", "Compliance"],
            "unverified_claims": ["Extra claim"],
            "confidence_note": "High confidence"
        }''' # step 5 format
    ]

    with patch("vectorstore.vectorstore.query", return_value=fake_chunks), \
         patch("api.call_gemini", side_effect=llm_responses) as mock_gemini:

        response = client.post("/api/query", json={"query": "What is the LCR limit?"})

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Banks must maintain a minimum LCR of 100%."
        assert len(data["citations"]) == 1
        assert data["citations"][0]["circular_no"] == "RBI/2026/01"
        assert len(data["effective_dates"]) == 1
        assert data["impacted_teams"] == ["Treasury", "Compliance"]
        assert "Extra claim" in data["unverified_claims"]
        assert data["confidence_note"] == "High confidence"
