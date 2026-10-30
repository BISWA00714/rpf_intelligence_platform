"""
Streamlit Web Application for the RFP Intelligence Platform.
Interactive procurement analytics dashboard supporting:
- Mode A: 20-Field Extraction & Addendum Audit Viewer
- Mode B: Cited Natural Language Q&A with Evidence Inspection
- Hybrid Search & Evidence Explorer (BM25 + Qdrant RRF)
- Side-by-Side RFP Comparison Matrix
- Observability Execution Trace Viewer
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

import streamlit as st

# Ensure repository root is on PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import settings
from schemas.extraction import REQUIRED_FIELDS, BidExtractionOutput
from schemas.search import SearchResult
from ingestion.discovery import discover_bids
from indexing.bm25_index import BM25Index
from search.engine import RAGSearchEngine
from agents.orchestrator import MultiAgentOrchestrator

# Set page configuration
st.set_page_config(
    page_title="RFP Intelligence Platform",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.5rem;
    }
    .confidence-high {
        color: #059669;
        font-weight: 600;
    }
    .confidence-med {
        color: #D97706;
        font-weight: 600;
    }
    .confidence-low {
        color: #DC2626;
        font-weight: 600;
    }
    .citation-box {
        background-color: #F1F5F9;
        border-left: 4px solid #3B82F6;
        padding: 0.6rem 0.8rem;
        border-radius: 4px;
        font-size: 0.9rem;
        margin-top: 0.4rem;
    }
    .addendum-banner {
        background-color: #FEF3C7;
        border-left: 4px solid #F59E0B;
        padding: 0.8rem 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
        color: #92400E;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_shared_search_engine():
    """Cached singleton of hybrid search engine."""
    return RAGSearchEngine()


@st.cache_resource
def get_shared_orchestrator():
    """Cached singleton of LangGraph multi-agent orchestrator."""
    return MultiAgentOrchestrator(search_engine=get_shared_search_engine())


def load_cached_extraction(bid_id: str) -> Optional[Dict[str, Any]]:
    """Loads cached 20-field extraction JSON if available."""
    paths = [
        settings.DATA_DIR / f"{bid_id}_extracted.json",
        settings.PROCESSED_DIR / f"{bid_id}_extracted.json"
    ]
    for p in paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return None


# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/color/96/briefcase--v1.png", width=64)
    st.title("RFP Control Center")
    
    # Discovery
    discovered_bids = discover_bids()
    bid_options = [b.bid_id for b in discovered_bids] if discovered_bids else ["Bid1", "Bid2"]
    selected_bid = st.selectbox("Select Active Bid Package", options=bid_options, index=0)
    
    st.divider()
    
    st.subheader("System Infrastructure")
    st.caption(f"**Embedding Model:** `{settings.EMBEDDING_MODEL}`")
    st.caption(f"**Vector Store:** `{settings.VECTOR_STORE_TYPE.upper()}` (Local Disk)")
    st.caption(f"**Lexical Engine:** `BM25Okapi`")
    
    bm25 = get_shared_search_engine().bm25_index
    total_indexed = len(bm25.chunks) if bm25 else 0
    st.caption(f"**Indexed Chunks:** `{total_indexed}`")
    
    st.divider()
    st.info("💡 **Grounded Evidence Guarantee**: Every extracted field and Q&A answer links to exact file names and page numbers.")


# Main Application Tabs
st.markdown('<div class="main-title">📋 RFP Intelligence Platform</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Evidence-Grounded Procurement Intelligence • Addendum Reconciliation • Hybrid RAG • Multi-Agent Orchestration</div>', unsafe_allow_html=True)

tab_extraction, tab_qa, tab_search, tab_compare, tab_docs, tab_traces = st.tabs([
    "📌 Mode A: 20-Field Extraction",
    "💬 Mode B: Cited Procurement Q&A",
    "🔍 Hybrid Search Explorer",
    "⚖️ Side-by-Side Comparison",
    "📂 Documents & Ingestion",
    "🩺 Observability & Traces"
])


# ==============================================================================
# TAB 1: MODE A - 20-FIELD EXTRACTION
# ==============================================================================
with tab_extraction:
    st.header(f"Structured 20-Field Extraction: {selected_bid}")
    
    col_actions, col_status = st.columns([1, 2])
    with col_actions:
        re_extract = st.button("⚡ Run Multi-Agent Extraction Pipeline", key="run_extract_btn")
    
    extracted_data = load_cached_extraction(selected_bid)
    
    if re_extract:
        with st.spinner(f"Orchestrating specialist extraction agents for {selected_bid}..."):
            orchestrator = get_shared_orchestrator()
            out = orchestrator.extract_bid(selected_bid)
            extracted_data = out.model_dump()
            
            # Save to disk
            with open(settings.DATA_DIR / f"{selected_bid}_extracted.json", "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, indent=2)
            st.success(f"Extraction complete for {selected_bid}!")
            st.rerun()

    if not extracted_data:
        st.warning(f"No extraction record found for {selected_bid}. Click 'Run Multi-Agent Extraction Pipeline' to process.")
    else:
        fields = extracted_data.get("fields", {})
        addendum_changes = extracted_data.get("addendum_changes", [])
        val_summary = extracted_data.get("validation", {})
        
        # Addendum Alert Banner
        if addendum_changes:
            for ch in addendum_changes:
                st.markdown(f"""
                <div class="addendum-banner">
                    <strong>⚠️ Addendum Reconciliation Override: {ch.get('field_name')}</strong><br/>
                    Original: <code>{ch.get('original_value')}</code> &rarr; 
                    <strong>Amended: <code>{ch.get('new_value')}</code></strong><br/>
                    <em>{ch.get('notes')}</em>
                </div>
                """, unsafe_allow_html=True)
        
        # Metric Overview
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Required Fields", len(REQUIRED_FIELDS))
        m2.metric("Fields Validated", val_summary.get("passed", 0))
        m3.metric("Non-Applicable / Null", val_summary.get("not_found", 0))
        m4.metric("Addendum Overrides", len(addendum_changes))
        
        st.subheader("Field-by-Field Breakdown")
        
        for idx, field_name in enumerate(REQUIRED_FIELDS):
            f_data = fields.get(field_name, {})
            val = f_data.get("value")
            conf = f_data.get("confidence", 0.0)
            notes = f_data.get("notes", "")
            sources = f_data.get("sources", [])
            
            with st.expander(f"**{idx+1}. {field_name}**: {val if val is not None else '*(null / not found)*'}", expanded=False):
                c_val, c_conf = st.columns([3, 1])
                with c_val:
                    st.markdown(f"**Extracted Value:** `{val}`" if val else "**Extracted Value:** *None / Not Found*")
                    st.markdown(f"**Notes:** {notes}")
                with c_conf:
                    conf_color = "confidence-high" if conf >= 0.9 else ("confidence-med" if conf >= 0.7 else "confidence-low")
                    st.markdown(f"**Confidence:** <span class='{conf_color}'>{conf * 100:.1f}%</span>", unsafe_allow_html=True)
                
                if sources:
                    st.markdown("**Grounding Citations:**")
                    for s in sources:
                        quote_text = f' — *"{s.get("quote")}"*' if s.get("quote") else ""
                        st.markdown(f"""
                        <div class="citation-box">
                            📄 <strong>File:</strong> <code>{s.get('file')}</code> | 
                            <strong>Page:</strong> {s.get('page')} {quote_text}
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.caption("No direct citations required (null or derived field).")
        
        # Download Raw JSON
        st.download_button(
            label="💾 Download Validated JSON Record",
            data=json.dumps(extracted_data, indent=2),
            file_name=f"{selected_bid}_extracted.json",
            mime="application/json"
        )


# ==============================================================================
# TAB 2: MODE B - CITED PROCUREMENT Q&A
# ==============================================================================
with tab_qa:
    st.header("Procurement Q&A with Evidence Citations")
    st.write("Ask natural-language procurement questions grounded in the ingested bid documents.")
    
    # Prompt suggestions
    st.caption("💡 Quick Prompt Starters:")
    sample_queries = [
        "What is the final submission deadline after all addendums?",
        "Which affidavits and supporting documents are required?",
        "Is a bid bond required, and what is the amount?",
        "What are the White Glove software installation and asset tagging requirements?",
        "What hardware model, processor, and warranty are requested?"
    ]
    col_q1, col_q2 = st.columns(2)
    selected_query_preset = None
    for i, sq in enumerate(sample_queries):
        col = col_q1 if i % 2 == 0 else col_q2
        if col.button(sq, key=f"sq_{i}"):
            st.session_state["active_query"] = sq

    active_q = st.session_state.get("active_query", "")
    user_query = st.text_input("Enter Question:", value=active_q, placeholder="e.g. What is the pre-bid conference date and link?")
    
    if st.button("🔍 Get Cited Answer", key="ask_btn") and user_query:
        with st.spinner(f"Retrieving evidence and orchestrating QA Agent for {selected_bid}..."):
            orchestrator = get_shared_orchestrator()
            t0 = time.time()
            qa_res = orchestrator.answer_question(user_query, bid_id=selected_bid)
            elapsed = time.time() - t0
            
            st.subheader("Answer")
            st.markdown(qa_res["answer"])
            
            st.caption(f"⏱️ Generated in {elapsed:.2f}s | Run ID: `{qa_res['run_id']}`")
            
            citations = qa_res.get("citations", [])
            if citations:
                st.subheader(f"Grounded Citations ({len(citations)})")
                for c in citations:
                    st.markdown(f"""
                    <div class="citation-box">
                        📄 <strong>Source File:</strong> <code>{c.get('file')}</code> | 
                        <strong>Page:</strong> {c.get('page')}<br/>
                        <div style="margin-top: 4px; color: #374151;"><em>"{c.get('quote')}"</em></div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No supporting citations found for this answer.")


# ==============================================================================
# TAB 3: HYBRID SEARCH EXPLORER
# ==============================================================================
with tab_search:
    st.header("Hybrid RAG Search Explorer")
    st.write("Inspect dense semantic retrieval (Qdrant) and lexical BM25 fused via Reciprocal Rank Fusion (RRF).")
    
    col_sq, col_topk, col_rerank = st.columns([3, 1, 1])
    with col_sq:
        search_query_text = st.text_input("Search Term / Alphanumeric Identifier:", value="Dell Latitude 5550")
    with col_topk:
        search_top_k = st.slider("Top K Passages", min_value=1, max_value=15, value=5)
    with col_rerank:
        enable_rerank = st.checkbox("Neural Reranker", value=False)
        
    if st.button("Execute Hybrid Search", key="exec_search_btn"):
        engine = get_shared_search_engine()
        results: SearchResult = engine.search(
            query_input=search_query_text,
            bid_id=selected_bid,
            top_k=search_top_k,
            use_reranker=enable_rerank
        )
        
        st.subheader(f"Ranked Evidence Passages ({len(results.evidence)})")
        st.caption(f"Query: `{results.query}` | Latency: `{results.execution_time_ms:.1f}ms`")
        
        for idx, p in enumerate(results.evidence):
            with st.container():
                st.markdown(f"""
                <div class="metric-card">
                    <div style="display: flex; justify-content: space-between;">
                        <strong>Rank #{idx+1}: {p.file_name} (Page {p.page_number})</strong>
                        <span style="color: #2563EB; font-weight: bold;">RRF Score: {p.score:.4f}</span>
                    </div>
                    <div style="margin-top: 6px; font-size: 0.85rem; color: #64748B;">
                        Chunk ID: <code>{p.chunk_id}</code> | Section: <em>{p.section_title or 'General'}</em> | <em>{p.citation}</em>
                    </div>
                    <div style="margin-top: 8px; font-size: 0.92rem; line-height: 1.4;">
                        {p.text}
                    </div>
                </div>
                """, unsafe_allow_html=True)


# ==============================================================================
# TAB 4: SIDE-BY-SIDE COMPARISON
# ==============================================================================
with tab_compare:
    st.header("Side-by-Side RFP Bid Comparison Matrix")
    st.write("Compare procurement profiles, submission modalities, warranty clauses, and technical specifications across bids.")
    
    b1_data = load_cached_extraction("Bid1") or {}
    b2_data = load_cached_extraction("Bid2") or {}
    
    b1_f = b1_data.get("fields", {})
    b2_f = b2_data.get("fields", {})
    
    comparison_dimensions = [
        ("Solicitation Number", "Bid Number"),
        ("Title", "Title"),
        ("Issuing Entity", "company_name"),
        ("Final Due Date", "Due Date"),
        ("Submission Type", "Bid Submission Type"),
        ("Contract Term", "Term of Bid"),
        ("Pre-Bid Meeting", "Pre Bid Meeting"),
        ("Bid Bond Requirement", "Bid Bond Requirement"),
        ("Delivery Timeline", "Delivery Date"),
        ("Installation/Services", "Installation"),
        ("Key Hardware Specs", "Product Specification"),
        ("Required Affidavits/Docs", "Any Additional Documentation Required"),
    ]
    
    table_rows = []
    for label, field_key in comparison_dimensions:
        val1 = b1_f.get(field_key, {}).get("value") or "None / Not specified"
        val2 = b2_f.get(field_key, {}).get("value") or "None / Not specified"
        table_rows.append({"Dimension": label, "Bid1 (Dallas ISD)": val1, "Bid2 (State of Maryland)": val2})
        
    st.table(table_rows)
    
    st.subheader("Key Architectural & Procurement Differences")
    st.markdown("""
    - **Procurement Vehicle:**
      - **Bid1:** Direct competitive school district RFP subject to Texas Education Code procurement rules.
      - **Bid2:** Secondary competition PORFP under State of Maryland Master Contract `060B5400007`.
    - **Addendum Reconciliation:**
      - **Bid1:** Addendum 2 superseded the original base RFP deadline, extending it from June 27, 2024 to July 9, 2024.
      - **Bid2:** No addenda issued; base PORFP due date of June 10, 2024 remained authoritative.
    - **Deployment Scope:**
      - **Bid1:** Mandates extensive White Glove deployment services (asset tagging, laser etching, software image staging).
      - **Bid2:** Hardware supply only with 3-year manufacturer extended warranty; no installation services requested.
    """)


# ==============================================================================
# TAB 5: DOCUMENTS & INGESTION VIEWER
# ==============================================================================
with tab_docs:
    st.header(f"Document Manifest & Ingestion Explorer: {selected_bid}")
    st.write("Inspect parsed document structures, table extraction statistics, OCR status, and upload new RFP files.")

    manifest_file = settings.PROCESSED_DIR / f"{selected_bid}_manifest.json"
    if manifest_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        m_docs = manifest_data.get("documents", [])
        m_pages = manifest_data.get("total_pages", 0)
        m_tables = sum(sum(len(p.get("tables", [])) for p in d.get("pages", [])) for d in m_docs)
        m_scanned = sum(sum(1 for p in d.get("pages", []) if p.get("is_scanned")) for d in m_docs)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Documents", len(m_docs))
        c2.metric("Total Pages", m_pages)
        c3.metric("Extracted Tables", m_tables)
        c4.metric("Scanned/OCR Pages", m_scanned)

        st.subheader("Document Inventory")
        doc_rows = []
        for d in m_docs:
            d_tables = sum(len(p.get("tables", [])) for p in d.get("pages", []))
            d_scanned = sum(1 for p in d.get("pages", []) if p.get("is_scanned"))
            doc_rows.append({
                "File Name": d.get("file_name"),
                "Type": d.get("doc_type", "").upper(),
                "Pages": d.get("total_pages"),
                "Tables": d_tables,
                "OCR Applied": "Yes" if d_scanned > 0 else "No"
            })
        st.dataframe(doc_rows, use_container_width=True)
    else:
        st.info(f"No parsed manifest found for {selected_bid}. Ingest the folder to view document metadata.")

    st.divider()
    st.subheader("Upload Additional Bid Documents")
    uploaded_files = st.file_uploader(
        f"Add PDF or HTML files to {selected_bid}",
        type=["pdf", "html", "htm"],
        accept_multiple_files=True
    )
    if uploaded_files:
        target_dir = settings.RAW_BIDS_DIR / selected_bid
        target_dir.mkdir(parents=True, exist_ok=True)
        for uf in uploaded_files:
            file_dest = target_dir / uf.name
            with open(file_dest, "wb") as f_out:
                f_out.write(uf.read())
            st.success(f"Uploaded: `{uf.name}` to `{target_dir.name}`")

        if st.button("⚡ Run Ingestion & Re-Index Package"):
            with st.spinner("Ingesting and indexing documents..."):
                from ingestion.pipeline import run_ingestion_pipeline
                from indexing.index_manager import IndexManager
                run_ingestion_pipeline(bid_path=str(target_dir))
                im = IndexManager()
                im.index_all(rebuild=True)
                st.success("Ingestion & re-indexing completed successfully!")
                st.rerun()


# ==============================================================================
# TAB 6: OBSERVABILITY & TRACES
# ==============================================================================
with tab_traces:
    st.header("Observability & Execution Traces")
    st.write("Inspect execution telemetry, agent invocation graphs, retry critic iterations, and latency traces.")
    
    trace_files = list(settings.LOGS_DIR.glob("*_trace.json"))
    if not trace_files:
        st.info("No execution trace logs found. Run an extraction or Q&A task to generate traces.")
    else:
        trace_map = {f.name: f for f in sorted(trace_files, reverse=True)}
        selected_trace = st.selectbox("Select Trace Log:", options=list(trace_map.keys()))
        
        with open(trace_map[selected_trace], "r", encoding="utf-8") as f:
            trace_content = json.load(f)
            
        st.json(trace_content)
