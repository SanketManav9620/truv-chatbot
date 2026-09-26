import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from google import genai
from dotenv import load_dotenv

load_dotenv()

PROMPT_TEMPLATE = """You are a regulatory-document parser. Extract from this notification text:
(a) exact circular/notification number,
(b) issuing date,
(c) effective date(s), including any provisions with different/phased effective dates,
(d) entity types covered (e.g. NBFC, bank, insurer, cooperative bank),
(e) a paragraph-by-paragraph summary, preserving section numbers.
Return strict JSON only, matching this schema:
{"circular_no": str, "issuing_date": str, "effective_dates": [{"provision": str, "date": str}], "entity_types": [str], "sections": [{"section_no": str, "title": str, "summary": str}]}
Copy all numbers, dates, and legal thresholds EXACTLY as written. Do not paraphrase figures. If a field is not present in the text, use null.

TEXT:
{raw_text}"""

def extract_clean_text_from_html(html_content: str) -> str:
    """Extracts main text content from HTML string while stripping nav, footer, menu, script, style tags."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Strip non-body/noise elements
    for element in soup(['script', 'style', 'nav', 'footer', 'header', 'menu', 'aside']):
        element.decompose()
    
    # Target main content area if present, otherwise whole body
    main_target = soup.find('main') or soup.find('article') or soup.find('div', id='content') or soup.body or soup
    
    text = main_target.get_text(separator='\n')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return '\n'.join(lines)

def fetch_url_text(url: str) -> str:
    """Fetches URL content and returns clean extracted text."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return extract_clean_text_from_html(response.text)

def _call_gemini_api(raw_text: str, client: genai.Client | None = None) -> dict:
    """Calls Gemini API with structured prompt and parses JSON response with 1 retry on malformed JSON."""
    if client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError("GEMINI_API_KEY is not configured in environment/backend/.env.")
        client = genai.Client(api_key=api_key)
    
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    prompt = PROMPT_TEMPLATE.replace("{raw_text}", raw_text)
    
    last_exception = None
    
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt
            )
            
            response_text = (response.text or "").strip()
            
            # Clean up potential markdown wrapper (e.g. ```json ... ```)
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            parsed_json = json.loads(response_text)
            if isinstance(parsed_json, dict):
                return parsed_json
            else:
                raise ValueError(f"Expected JSON object, got {type(parsed_json).__name__}")
                
        except (json.JSONDecodeError, ValueError, Exception) as err:
            last_exception = err
            if attempt == 1:
                raise ValueError(f"Failed to parse Gemini model response as JSON after retry: {err}") from err

def ingest_url(url: str, html_override: str | None = None, client: genai.Client | None = None) -> dict:
    """
    Ingests a regulatory document URL (or html_override if supplied), extracts clean text,
    calls Gemini API to parse notification structure into JSON, and attaches
    source_url and ingested_at metadata.
    """
    if html_override is not None:
        raw_text = extract_clean_text_from_html(html_override)
    else:
        raw_text = fetch_url_text(url)
    
    extracted = _call_gemini_api(raw_text, client=client)
    
    ingested_at = datetime.now(timezone.utc).isoformat()
    
    result = {
        "source_url": url,
        "ingested_at": ingested_at
    }
    result.update(extracted)
    return result
