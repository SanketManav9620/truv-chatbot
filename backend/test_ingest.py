import os
import json
from unittest.mock import MagicMock
from ingest import ingest_url, extract_clean_text_from_html

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "tests", "fixtures", "sample_circular.html")

def test_extract_clean_text_from_html():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    clean_text = extract_clean_text_from_html(html_content)
    
    # Assert header nav and footer noise are stripped out
    assert "Home" not in clean_text
    assert "About RBI" not in clean_text
    assert "Copyright 2026" not in clean_text
    
    # Assert main regulatory content is preserved
    assert "RBI/2026-27/89" in clean_text
    assert "Section 1: Framework" in clean_text
    assert "Liquidity Coverage Ratio" in clean_text

def test_ingest_url_returns_expected_keys():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Mock Gemini Client to prevent network calls during testing
    mock_client = MagicMock()
    mock_response = MagicMock()
    
    mock_json_payload = {
        "circular_no": "RBI/2026-27/89",
        "issuing_date": "April 15, 2026",
        "effective_dates": [
            {"provision": "Provision A", "date": "June 1, 2026"},
            {"provision": "Provision B", "date": "October 1, 2026"}
        ],
        "entity_types": ["NBFC", "Commercial Bank"],
        "sections": [
            {
                "section_no": "1",
                "title": "Framework",
                "summary": "All covered entities shall maintain a minimum Liquidity Coverage Ratio (LCR) of 100%."
            }
        ]
    }
    
    mock_response.text = json.dumps(mock_json_payload)
    mock_client.models.generate_content.return_value = mock_response

    test_url = "https://example.com/regulatory/rbi-2026-89"
    result = ingest_url(url=test_url, html_override=html_content, client=mock_client)

    # Assert expected keys exist in returned dict
    expected_keys = {
        "circular_no",
        "issuing_date",
        "effective_dates",
        "entity_types",
        "sections",
        "source_url",
        "ingested_at"
    }
    assert expected_keys.issubset(set(result.keys()))
    assert result["source_url"] == test_url
    assert result["circular_no"] == "RBI/2026-27/89"
    assert result["issuing_date"] == "April 15, 2026"
    assert len(result["effective_dates"]) == 2
    assert "NBFC" in result["entity_types"]
    assert "ingested_at" in result

def test_ingest_url_retry_on_malformed_json():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    mock_client = MagicMock()
    
    # 1st attempt returns malformed text, 2nd attempt returns valid JSON
    bad_response = MagicMock()
    bad_response.text = "INVALID NON-JSON TEXT"
    
    good_response = MagicMock()
    good_response.text = json.dumps({
        "circular_no": "CIRC-999",
        "issuing_date": "2026-05-20",
        "effective_dates": [],
        "entity_types": ["Bank"],
        "sections": []
    })
    
    mock_client.models.generate_content.side_effect = [bad_response, good_response]

    test_url = "https://example.com/test-retry"
    result = ingest_url(url=test_url, html_override=html_content, client=mock_client)

    assert result["circular_no"] == "CIRC-999"
    assert mock_client.models.generate_content.call_count == 2
