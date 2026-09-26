import os
from typing import List, Dict, Any, Optional

try:
    import chromadb
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False

class VectorStore:
    def __init__(self, collection_name: str = "regulatory_docs", persist_dir: str = "./chroma_db"):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._in_memory_docs: List[Dict[str, Any]] = []

    @property
    def client(self):
        if HAS_CHROMADB and self._client is None:
            os.makedirs(self.persist_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self.persist_dir)
        return self._client

    @property
    def collection(self):
        if HAS_CHROMADB and self._collection is None:
            self._collection = self.client.get_or_create_collection(name=self.collection_name)
            if self._collection.count() == 0:
                self._seed_default_documents()
        return self._collection

    def _seed_default_documents(self):
        """Seed default compliance circular chunks if store is empty."""
        seed_docs = [
            {
                "id": "rbi_lcr_2026_1",
                "text": "RBI/2026-27/89 Section 1: Liquidity Coverage Ratio (LCR) Maintenance and HQLA Buffers. All Commercial Banks and Deposit-taking NBFCs must maintain an LCR of at least 100%. Phased implementation starts June 1, 2026, with full enforcement mandatory by January 1, 2027.",
                "metadata": {
                    "circular_no": "RBI/2026-27/89",
                    "section": "Section 1 - LCR Maintenance",
                    "issuing_authority": "Reserve Bank of India",
                    "effective_date": "2026-06-01",
                    "status": "Phased",
                    "impacted_teams": "Treasury, Risk Management, Compliance",
                    "source_url": "https://rbi.org.in/scripts/BS_CircularIndexDisplay.aspx?Id=12689"
                }
            },
            {
                "id": "rbi_lcr_2026_2",
                "text": "RBI/2026-27/89 Section 2: Run-off Rates on Retail and SME Deposits. Banks are required to assign an additional 5% run-off factor on internet and mobile banking enabled deposits to ensure operational liquidity during high-velocity digital outflows.",
                "metadata": {
                    "circular_no": "RBI/2026-27/89",
                    "section": "Section 2 - Deposit Run-off Factors",
                    "issuing_authority": "Reserve Bank of India",
                    "effective_date": "2026-06-01",
                    "status": "Phased",
                    "impacted_teams": "Treasury, Digital Banking, ALCO",
                    "source_url": "https://rbi.org.in/scripts/BS_CircularIndexDisplay.aspx?Id=12689"
                }
            },
            {
                "id": "sebi_cyber_2026_1",
                "text": "SEBI/HO/MIRSD/2026/14 Section 3: Enhanced Cybersecurity and Operational Resilience Framework. Mandates quarterly vulnerability assessment and penetration testing (VAPT), 2-hour cybersecurity incident reporting to SEBI, and designated Chief Information Security Officer (CISO) governance.",
                "metadata": {
                    "circular_no": "SEBI/HO/MIRSD/2026/14",
                    "section": "Section 3 - Cyber Resilience",
                    "issuing_authority": "SEBI",
                    "effective_date": "2026-10-01",
                    "status": "Upcoming",
                    "impacted_teams": "Information Security, IT Operations, Legal",
                    "source_url": "https://sebi.gov.in/legal/circulars/oct-2026/cybersecurity-framework.html"
                }
            },
            {
                "id": "rbi_nbfc_2025_1",
                "text": "RBI/2025-26/112 Section 4: Scale Based Regulation for Non-Banking Financial Companies (NBFCs). Middle and Upper Layer NBFCs must maintain minimum Common Equity Tier 1 (CET1) capital ratio of 9% and Tier 1 Capital ratio of 12% by April 1, 2026.",
                "metadata": {
                    "circular_no": "RBI/2025-26/112",
                    "section": "Section 4 - NBFC Capital Adequacy",
                    "issuing_authority": "Reserve Bank of India",
                    "effective_date": "2026-04-01",
                    "status": "In Force",
                    "impacted_teams": "Finance, Audit & Assurance, Board Risk Committee",
                    "source_url": "https://rbi.org.in/scripts/BS_CircularIndexDisplay.aspx?Id=12512"
                }
            },
            {
                "id": "irdai_health_2026_1",
                "text": "IRDAI/HLT/REG/2026/05 Section 2: Master Circular on Health Insurance Products and Claim Settlement Timelines. Cashless pre-authorization decisions must be granted within 1 hour of request submission by insurance desk.",
                "metadata": {
                    "circular_no": "IRDAI/HLT/REG/2026/05",
                    "section": "Section 2 - Cashless Pre-Auth Timelines",
                    "issuing_authority": "IRDAI",
                    "effective_date": "2026-03-15",
                    "status": "In Force",
                    "impacted_teams": "Claims Operations, Customer Support, Underwriting",
                    "source_url": "https://irdai.gov.in/document-detail?folderId=1295"
                }
            }
        ]

        docs = [d["text"] for d in seed_docs]
        metas = [d["metadata"] for d in seed_docs]
        ids = [d["id"] for d in seed_docs]

        self.add_documents(documents=docs, metadatas=metas, ids=ids)

    def add_documents(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]):
        """Add document chunks with metadata to vectorstore."""
        if not documents:
            return
        if HAS_CHROMADB:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
        else:
            for doc, meta, doc_id in zip(documents, metadatas, ids):
                self._in_memory_docs.append({
                    "id": doc_id,
                    "text": doc,
                    "metadata": meta
                })

    def query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Query vectorstore for matching text chunks.
        Returns a list of dicts with keys: id, text, metadata, distance.
        """
        if HAS_CHROMADB:
            try:
                count = self.collection.count()
                if count == 0:
                    self._seed_default_documents()
                    count = self.collection.count()
                if count == 0:
                    return []

                n_results = min(top_k, count)
                results = self.collection.query(
                    query_texts=[query],
                    n_results=n_results
                )
                
                output = []
                if results and results.get("documents") and results["documents"][0]:
                    docs = results["documents"][0]
                    ids = results["ids"][0] if results.get("ids") else [f"doc_{i}" for i in range(len(docs))]
                    metas = results["metadatas"][0] if results.get("metadatas") else [{} for _ in docs]
                    distances = results["distances"][0] if results.get("distances") else [0.0 for _ in docs]
                    
                    for doc_id, text, meta, dist in zip(ids, docs, metas, distances):
                        output.append({
                            "id": doc_id,
                            "text": text,
                            "metadata": meta or {},
                            "distance": dist
                        })
                return output
            except Exception:
                return []
        else:
            if not self._in_memory_docs:
                self._seed_default_documents()
            if not self._in_memory_docs:
                return []
            
            query_words = set(query.lower().split())
            results = []
            for doc in self._in_memory_docs:
                text = doc["text"].lower()
                matches = sum(1 for w in query_words if w in text)
                # If query matched any word or return top documents
                results.append((matches, doc))
            
            results.sort(key=lambda x: x[0], reverse=True)
            return [doc for _, doc in results[:top_k]]

vectorstore = VectorStore()

