import os
import sys
import json
import argparse
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

from ingest import ingest_url
from vectorstore import vectorstore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("regulatory_scheduler")

DEFAULT_SOURCES_FILE = os.path.join(os.path.dirname(__file__), "sources.json")
DEFAULT_INGESTED_FILE = os.path.join(os.path.dirname(__file__), "ingested_urls.json")

DEFAULT_SOURCES = [
    "https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx",
    "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&smid=0&ssid=0"
]

def load_sources(filepath: str = DEFAULT_SOURCES_FILE) -> list[str]:
    """Loads regulator notification index URLs from sources.json, creating a default file if missing."""
    if not os.path.exists(filepath):
        logger.info(f"Sources file '{filepath}' not found. Creating default sources.json...")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SOURCES, f, indent=2)
        return DEFAULT_SOURCES

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "sources" in data:
                return data["sources"]
            return DEFAULT_SOURCES
    except Exception as err:
        logger.error(f"Error loading sources file '{filepath}': {err}. Using default sources.")
        return DEFAULT_SOURCES

def load_ingested_urls(filepath: str = DEFAULT_INGESTED_FILE) -> set[str]:
    """Loads set of previously ingested URLs from ingested_urls.json."""
    if not os.path.exists(filepath):
        return set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return set(data)
            elif isinstance(data, dict) and "ingested_urls" in data:
                return set(data["ingested_urls"])
            return set()
    except Exception as err:
        logger.error(f"Error reading ingested URLs file '{filepath}': {err}.")
        return set()

def save_ingested_urls(ingested_urls: set[str], filepath: str = DEFAULT_INGESTED_FILE):
    """Saves updated set of ingested URLs to ingested_urls.json."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(sorted(list(ingested_urls)), f, indent=2)
    except Exception as err:
        logger.error(f"Failed to save ingested URLs to '{filepath}': {err}")

def fetch_notification_links(index_url: str) -> list[str]:
    """Fetches a regulator index page and extracts candidate notification/circular links."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(index_url, headers=headers, timeout=20)
        response.raise_for_status()
    except Exception as err:
        logger.warning(f"Could not fetch index URL '{index_url}': {err}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    found_links = []
    base_domain = urlparse(index_url).netloc

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith("javascript:") or href.startswith("#") or href.startswith("mailto:"):
            continue

        full_url = urljoin(index_url, href)
        parsed = urlparse(full_url)
        
        # Keep http/https links
        if parsed.scheme in ("http", "https"):
            # Filter obvious noise like home or contact pages
            path_lower = parsed.path.lower()
            if any(term in path_lower for term in ["circular", "notification", "display", "id=", "doc", "pdf", "html", "sid="]):
                found_links.append(full_url)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for link in found_links:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
            
    return deduped

def process_and_vectorize(data: dict):
    """Constructs text chunks from ingested notification JSON and adds them to vectorstore."""
    circular_no = data.get("circular_no", "UNKNOWN")
    source_url = data.get("source_url", "")
    issuing_date = data.get("issuing_date", "")
    sections = data.get("sections") or []

    documents = []
    metadatas = []
    ids = []

    if sections:
        for idx, sec in enumerate(sections):
            sec_no = sec.get("section_no", str(idx + 1))
            sec_title = sec.get("title", "")
            summary = sec.get("summary", "")
            
            chunk_text = f"Circular: {circular_no} | Date: {issuing_date} | Section {sec_no}: {sec_title}\n{summary}"
            doc_id = f"{circular_no}_sec_{sec_no}_{idx}"
            
            documents.append(chunk_text)
            metadatas.append({
                "circular_no": circular_no,
                "issuing_date": issuing_date,
                "section": sec_title or sec_no,
                "source_url": source_url
            })
            ids.append(doc_id)
    else:
        chunk_text = f"Circular: {circular_no} | Date: {issuing_date} | Source: {source_url}"
        doc_id = f"{circular_no}_full"
        documents.append(chunk_text)
        metadatas.append({
            "circular_no": circular_no,
            "issuing_date": issuing_date,
            "source_url": source_url
        })
        ids.append(doc_id)

    vectorstore.add_documents(documents=documents, metadatas=metadatas, ids=ids)

def run_ingestion_job(sources_file: str = DEFAULT_SOURCES_FILE, ingested_file: str = DEFAULT_INGESTED_FILE) -> dict:
    """Runs a single pass of checking index pages for new circulars and ingesting them."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    logger.info(f"[{timestamp}] Starting regulator circular ingestion check...")

    sources = load_sources(sources_file)
    ingested_urls = load_ingested_urls(ingested_file)

    newly_ingested = []

    for index_url in sources:
        logger.info(f"Scanning regulator index page: {index_url}")
        candidate_links = fetch_notification_links(index_url)
        
        for link in candidate_links:
            if link in ingested_urls:
                continue

            logger.info(f"Found new un-ingested circular link: {link}")
            try:
                ingested_data = ingest_url(url=link)
                process_and_vectorize(ingested_data)
                
                ingested_urls.add(link)
                save_ingested_urls(ingested_urls, ingested_file)
                newly_ingested.append(link)
                logger.info(f"Successfully ingested & vectorized: {link} (Circular No: {ingested_data.get('circular_no')})")
            except Exception as err:
                logger.error(f"Failed to ingest URL '{link}': {err}")

    if newly_ingested:
        logger.info(f"[{timestamp}] Ingestion pass completed: {len(newly_ingested)} new circular(s) newly ingested.")
    else:
        logger.info(f"[{timestamp}] Ingestion pass completed: no new circulars found.")

    return {"newly_ingested_count": len(newly_ingested), "urls": newly_ingested}

def start_scheduler():
    """Starts the 24-hour background scheduler loop."""
    logger.info("Initializing 24-hour recurring ingestion scheduler...")
    
    # Try using APScheduler if installed
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        # Run job once immediately, then every 24 hours
        scheduler.add_job(run_ingestion_job, 'interval', hours=24, next_run_time=datetime.now())
        scheduler.start()
        logger.info("APScheduler BackgroundScheduler started. Running every 24 hours.")
        try:
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            logger.info("Scheduler stopped cleanly.")
    except ImportError:
        logger.info("APScheduler not installed. Falling back to internal loop (sleep 24 hours).")
        while True:
            try:
                run_ingestion_job()
            except Exception as err:
                logger.error(f"Error during ingestion job loop: {err}")
            time.sleep(86400) # Sleep 24 hours

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regulatory Copilot Circular Ingestion Scheduler")
    parser.add_argument("--once", action="store_true", help="Run a single ingestion pass manually and exit")
    parser.add_argument("--sources", type=str, default=DEFAULT_SOURCES_FILE, help="Path to sources.json config file")
    parser.add_argument("--ingested", type=str, default=DEFAULT_INGESTED_FILE, help="Path to ingested_urls.json file")
    
    args = parser.parse_args()

    if args.once:
        logger.info("Running manual single pass (--once mode)...")
        res = run_ingestion_job(sources_file=args.sources, ingested_file=args.ingested)
        logger.info(f"Completed manual pass. Results: {res}")
    else:
        start_scheduler()
