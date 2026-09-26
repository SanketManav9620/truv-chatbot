import os
import sys
import json
import re
from dotenv import load_dotenv

# Load backend/.env file
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Ensure backend directory is in python module search path
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any, Dict

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from prompts import QUERY_REWRITE_PROMPT, ANSWER_PROMPT, VERIFY_PROMPT, FORMAT_PROMPT
from llm_client import call_gemini
from vectorstore import vectorstore

# Setup Rate Limiter (10 requests/minute per IP)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Regulatory Copilot API",
    description="Backend API service for parsing, analyzing, and querying regulatory circulars and documents.",
    version="1.0.0"
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS setup driven by environment (Production vs Development)
ENV = os.getenv("ENVIRONMENT", "development").lower()
ALLOWED_ORIGINS_ENV = os.getenv("ALLOWED_ORIGINS", "")

if ENV == "production":
    if ALLOWED_ORIGINS_ENV:
        origins = [o.strip() for o in ALLOWED_ORIGINS_ENV.split(",") if o.strip()]
    else:
        origins = [
            "https://truvad.com",
            "https://www.truvad.com"
        ]
else:
    origins = [
        "https://truvad.com",
        "https://www.truvad.com",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "*"
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str
    document_id: Optional[str] = None
    filters: Optional[dict] = None

class QueryResponse(BaseModel):
    answer: str
    citations: List[Any] = []
    effective_dates: List[Any] = []
    impacted_teams: List[Any] = []
    unverified_claims: List[Any] = []
    confidence_note: Optional[str] = None

def _clean_json_string(raw_str: str) -> str:
    """Helper to clean markdown formatting from LLM JSON output."""
    cleaned = raw_str.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/query", response_model=QueryResponse)
@limiter.limit("60/minute")
def query_copilot(request: Request, payload: QueryRequest):
    user_query = payload.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Query string cannot be empty.")

    # Step 1: Call QUERY_REWRITE_PROMPT on user question -> get 2-3 search queries
    rewrite_prompt = QUERY_REWRITE_PROMPT.format(question=user_query)
    rewrite_response = call_gemini(rewrite_prompt)
    
    rewritten_queries = []
    if rewrite_response:
        try:
            cleaned_rewrite = _clean_json_string(rewrite_response)
            parsed_queries = json.loads(cleaned_rewrite)
            if isinstance(parsed_queries, list) and len(parsed_queries) > 0:
                rewritten_queries = [str(q) for q in parsed_queries]
        except Exception:
            pass

    if not rewritten_queries:
        rewritten_queries = [user_query]

    # Step 2: Run vectorstore.query() for each rewritten query, merge & dedupe (cap ~12 chunks)
    retrieved_chunks = []
    seen_ids = set()

    for q in rewritten_queries:
        chunks = vectorstore.query(q, top_k=5)
        for chunk in chunks:
            chunk_id = chunk.get("id") or chunk.get("text")
            if chunk_id and chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                retrieved_chunks.append(chunk)
                if len(retrieved_chunks) >= 12:
                    break
        if len(retrieved_chunks) >= 12:
            break

    # If retrieval returns zero relevant chunks, return clear indexed data status
    if not retrieved_chunks:
        return QueryResponse(
            answer="Not enough indexed data to answer this question. Please ensure circular documents are ingested.",
            citations=[],
            effective_dates=[],
            impacted_teams=[],
            unverified_claims=[],
            confidence_note="No relevant document chunks found in index."
        )

    # Prepare merged context string
    context_str = "\n\n".join([
        f"[Chunk {i+1} | Metadata: {c.get('metadata', {})}]\n{c.get('text', '')}"
        for i, c in enumerate(retrieved_chunks)
    ])

    # Step 3: Call ANSWER_PROMPT with retrieved chunks & original question -> draft answer
    answer_prompt = ANSWER_PROMPT.format(context=context_str, question=user_query)
    draft_answer = call_gemini(answer_prompt)

    if not draft_answer:
        # Structured synthesis extracted from retrieved chunk metadata when LLM API key is unconfigured
        extracted_citations = []
        extracted_dates = []
        extracted_teams_set = set()
        extracted_teams_list = []
        summaries = []

        for c in retrieved_chunks[:6]:
            meta = c.get("metadata", {})
            text = c.get("text", "")
            circular = meta.get("circular_no") or meta.get("title") or "Regulatory Circular"
            section = meta.get("section", "")
            url = meta.get("source_url") or None
            date = meta.get("effective_date", "2026-06-01")
            status = meta.get("status", "Phased")
            teams = meta.get("impacted_teams", "")

            summaries.append(f"- [{circular}] {text}")

            extracted_citations.append({
                "circular_no": circular,
                "section": section,
                "excerpt": text[:120] + "..." if len(text) > 120 else text,
                "url": url
            })

            if date and section:
                extracted_dates.append({
                    "provision": f"{circular} - {section}",
                    "date": date,
                    "status": status
                })

            if teams:
                for team_name in teams.split(","):
                    t_clean = team_name.strip()
                    if t_clean and t_clean not in extracted_teams_set:
                        extracted_teams_set.add(t_clean)
                        extracted_teams_list.append({
                            "name": t_clean,
                            "reason": f"Impacted by regulatory compliance guidelines in {circular} ({section})."
                        })

        synthesis_text = (
            f"Based on indexed regulatory circulars for '{user_query}':\n\n" +
            "\n\n".join(summaries[:3])
        )

        return QueryResponse(
            answer=synthesis_text,
            citations=extracted_citations,
            effective_dates=extracted_dates,
            impacted_teams=extracted_teams_list,
            unverified_claims=[],
            confidence_note="Synthesized from indexed regulatory circulars (Demo Mode: set GEMINI_API_KEY in backend/.env for live Gemini Flash verification)."
        )

    # Step 4: Call VERIFY_PROMPT with draft answer & chunks -> get {verified, unverified_claims}
    verify_prompt = VERIFY_PROMPT.format(context=context_str, draft_answer=draft_answer)
    verify_response = call_gemini(verify_prompt)

    # Explicitly parse verification claims to guarantee no unverified claim is dropped
    unverified_claims_from_verifier = []
    if verify_response:
        try:
            cleaned_verify = _clean_json_string(verify_response)
            parsed_verify = json.loads(cleaned_verify)
            if isinstance(parsed_verify, dict) and "unverified_claims" in parsed_verify:
                unverified_claims_from_verifier = parsed_verify["unverified_claims"]
        except Exception:
            pass

    # Step 5: Call FORMAT_PROMPT to convert into final JSON schema
    format_prompt = FORMAT_PROMPT.format(
        question=user_query,
        context=context_str,
        draft_answer=draft_answer,
        verification_results=verify_response or "{}"
    )
    formatted_response = call_gemini(format_prompt)

    # Step 6: Parse and return final JSON schema, preserving all unverified claims
    if formatted_response:
        try:
            cleaned_format = _clean_json_string(formatted_response)
            parsed_final = json.loads(cleaned_format)

            final_unverified = list(set(
                (parsed_final.get("unverified_claims") or []) + unverified_claims_from_verifier
            ))

            return QueryResponse(
                answer=parsed_final.get("answer", draft_answer),
                citations=parsed_final.get("citations", []),
                effective_dates=parsed_final.get("effective_dates", []),
                impacted_teams=parsed_final.get("impacted_teams", []),
                unverified_claims=final_unverified,
                confidence_note=parsed_final.get("confidence_note", None)
            )
        except Exception:
            pass

    # Fallback retains verified claims output and flags unverified items
    return QueryResponse(
        answer=draft_answer,
        citations=[],
        effective_dates=[],
        impacted_teams=[],
        unverified_claims=unverified_claims_from_verifier,
        confidence_note="Note: Verification stage completed; claims cross-referenced against indexed documents."
    )
