"""Minimal demo UI: ask a question, see the cited answer, the computation and the sources.

    pip install -e ".[ui]" && streamlit run ui/app.py

Talks only to the rag-service API (which talks only to the gateway). Non-commercial demo.
"""

from __future__ import annotations

import os
import uuid

import httpx
import streamlit as st

API = os.environ.get("RAG_SERVICE_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="grounded-finrag", layout="wide")
st.title("grounded-finrag")
st.caption("Answers from FinanceBench filings with verified [document, page] citations. "
           "Non-commercial demo; not investment advice.")

question = st.text_input("Question", placeholder="What was 3M's FY2018 capital expenditure (in USD millions)?")
if st.button("Answer", type="primary") and question.strip():
    request_id = uuid.uuid4().hex
    with st.spinner("Retrieving and answering through the gateway..."):
        try:
            resp = httpx.post(f"{API}/answer", json={"question": question},
                              headers={"X-Request-Id": request_id}, timeout=300)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            st.error(f"rag-service error: {e}")
            st.stop()

    if data["abstained"]:
        st.warning(f"{data['answer']} (reason: {data.get('abstain_reason')})")
    else:
        st.success(data["answer"].split("\n")[0])
        st.markdown(data["answer"])

    cols = st.columns(3)
    cols[0].metric("Mode", data["mode"])
    cols[1].metric("Support score", f"{data['support']:.3f}" if data.get("support") is not None else "n/a")
    cols[2].metric("Total time (ms)", f"{data['timings_ms'].get('total', 0):.0f}")

    if data.get("computation"):
        comp = data["computation"]
        st.subheader("Computation (evaluated in Python)")
        st.code(f"{comp['metric']} = {comp['formula']}\n= {comp['result']:,.4f} {comp['unit']}")
        st.table([{"input": k, "value": v} for k, v in comp["inputs"].items()])

    if data["citations"]:
        st.subheader("Citations")
        for c in data["citations"]:
            st.write(f"- {c['doc_name']}, page {c['page']}")
    st.caption(f"Request ID {data['request_id']}: the same ID appears in the gateway's audit log for every "
               "model call made for this question.")
