"""
Prompt templates for the Regulatory Copilot RAG pipeline.
"""

QUERY_REWRITE_PROMPT = """You are a regulatory compliance research assistant.
Given a user question, generate 2 to 3 distinct, specific search queries optimized for vector search against regulatory circulars, compliance guidelines, and policy documents.
Return ONLY a JSON array of strings, for example: ["query 1", "query 2", "query 3"].

User Question: {question}"""

ANSWER_PROMPT = """You are an expert regulatory compliance copilot.
Answer the user's question using ONLY the provided regulatory context chunks.
If the context does not contain enough information to fully answer, state what is missing clearly.
Do not invent information or cite external sources outside the provided context.

Context Chunks:
{context}

User Question: {question}

Draft Answer:"""

VERIFY_PROMPT = """You are a compliance quality assurance verifier.
Compare the draft answer against the source context chunks.
Identify every claim made in the draft answer and verify whether it is directly supported by the context.

Context Chunks:
{context}

Draft Answer:
{draft_answer}

Return strict JSON only matching this schema:
{{
    "verified_claims": [str],
    "unverified_claims": [str]
}}"""

FORMAT_PROMPT = """You are a structured data formatting assistant for a regulatory copilot.
Format the final answer and metadata into strict JSON matching the required schema.

Original Question: {question}
Context Chunks: {context}
Draft Answer: {draft_answer}
Verification Results: {verification_results}

Return strict JSON only matching this exact schema:
{{
    "answer": "Clear comprehensive final answer with references to sources",
    "citations": [
        {{
            "circular_no": "circular number or null",
            "section": "section title or number or null",
            "excerpt": "relevant text quote",
            "url": "source url or null"
        }}
    ],
    "effective_dates": [
        {{
            "provision": "provision description",
            "date": "effective date"
        }}
    ],
    "impacted_teams": ["team name (e.g., Compliance, Risk, Operations, IT)"],
    "unverified_claims": ["any claim from draft answer that could not be verified"],
    "confidence_note": "A short note on answer confidence or limitations, or null"
}}"""
