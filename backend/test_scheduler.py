import os
import json
import pytest
from unittest.mock import patch, MagicMock

from scheduler import (
    load_sources,
    load_ingested_urls,
    save_ingested_urls,
    fetch_notification_links,
    run_ingestion_job
)

def test_load_sources_creates_default(tmp_path):
    sources_file = tmp_path / "sources.json"
    sources = load_sources(str(sources_file))
    assert isinstance(sources, list)
    assert len(sources) > 0
    assert os.path.exists(sources_file)

def test_load_and_save_ingested_urls(tmp_path):
    ingested_file = tmp_path / "ingested_urls.json"
    initial_urls = load_ingested_urls(str(ingested_file))
    assert initial_urls == set()

    test_urls = {"https://example.com/circ1", "https://example.com/circ2"}
    save_ingested_urls(test_urls, str(ingested_file))

    loaded = load_ingested_urls(str(ingested_file))
    assert loaded == test_urls

def test_fetch_notification_links():
    mock_html = """
    <html>
      <body>
        <a href="/circulars/2026-01.html">Circular 01</a>
        <a href="https://example.com/notification/display.aspx?id=99">Notification 99</a>
        <a href="/about-us">About Us</a>
      </body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.text = mock_html
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        links = fetch_notification_links("https://example.com/index.html")
        assert "https://example.com/circulars/2026-01.html" in links
        assert "https://example.com/notification/display.aspx?id=99" in links
        assert not any("about-us" in l for l in links)

def test_run_ingestion_job_manual_pass(tmp_path):
    sources_file = tmp_path / "test_sources.json"
    ingested_file = tmp_path / "test_ingested.json"

    with open(sources_file, "w") as f:
        json.dump(["https://example.com/index"], f)

    fake_links = ["https://example.com/circular/101"]
    fake_ingest_data = {
        "circular_no": "CIRC-101",
        "issuing_date": "2026-09-01",
        "sections": [{"section_no": "1", "title": "Scope", "summary": "Applies to all banks."}],
        "source_url": "https://example.com/circular/101"
    }

    with patch("scheduler.fetch_notification_links", return_value=fake_links), \
         patch("scheduler.ingest_url", return_value=fake_ingest_data) as mock_ingest, \
         patch("scheduler.process_and_vectorize") as mock_vectorize:

        res = run_ingestion_job(sources_file=str(sources_file), ingested_file=str(ingested_file))

        assert res["newly_ingested_count"] == 1
        assert "https://example.com/circular/101" in res["urls"]
        mock_ingest.assert_called_once_with(url="https://example.com/circular/101")
        mock_vectorize.assert_called_once()

        # Second run should skip already ingested URL
        res_2 = run_ingestion_job(sources_file=str(sources_file), ingested_file=str(ingested_file))
        assert res_2["newly_ingested_count"] == 0
