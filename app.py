"""
app.py — CivicDigest local Streamlit UI
Run: streamlit run app.py
"""

import streamlit as st
from mlx_lm import load, generate

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CivicDigest",
    page_icon="🏛️",
    layout="centered",
)

st.title("🏛️ CivicDigest")
st.caption("Paste city council meeting minutes. Get a plain English summary of what was decided.")

# ---------------------------------------------------------------------------
# Load model (cached so it only loads once)
# ---------------------------------------------------------------------------
@st.cache_resource
def load_model():
    model, tokenizer = load("civicdigest-model")
    return model, tokenizer

with st.spinner("Loading model..."):
    model, tokenizer = load_model()

# ---------------------------------------------------------------------------
# Example inputs
# ---------------------------------------------------------------------------
EXAMPLES = [
    {
        "label": "Denver — Budget & Infrastructure",
        "text": (
            "AGENDA ITEM: Transportation Infrastructure Amendment No. 2\n"
            "ACTION: Council approved 9-2 a $4.7 million amendment to the Colfax Avenue "
            "repaving contract with Hensel Phelps Construction. Councilmembers Gilmore and "
            "Sawyer dissented, citing concerns about cost overruns. Work is expected to "
            "begin in May and complete by September. Residents along the corridor may "
            "experience lane closures during construction.\n\n"
            "AGENDA ITEM: 2026 General Fund Budget Amendment\n"
            "ACTION: Council voted 11-0 to approve a $2.1 million supplemental budget "
            "amendment to cover rising utility costs across city-owned facilities. The funds "
            "will be drawn from the general fund reserve."
        ),
    },
    {
        "label": "Seattle — Housing & Zoning",
        "text": (
            "AGENDA ITEM: CB 120788 — Mandatory Housing Affordability Amendment\n"
            "ACTION: The Land Use and Sustainability Committee voted 5-0 to recommend full "
            "council approval of an amendment expanding MHA requirements to 12 additional "
            "urban village zones. Developers will be required to include 7% affordable units "
            "or pay an in-lieu fee of $32.75 per square foot. Public comment period closes "
            "May 15th. Final vote expected at the April 28th full council meeting.\n\n"
            "AGENDA ITEM: Accessory Dwelling Unit Permit Streamlining\n"
            "ACTION: Passed 4-1. Reduces ADU permit review time from 120 days to 30 days "
            "for properties in single-family zones. Takes effect July 1, 2026."
        ),
    },
    {
        "label": "Phoenix — Public Safety",
        "text": (
            "AGENDA ITEM: Police Department Body Camera Contract Renewal\n"
            "ACTION: City Council approved 7-0 a 3-year contract renewal with Axon "
            "Enterprise for body-worn camera equipment and cloud storage. Total contract "
            "value: $8.4 million. The agreement includes real-time footage sharing with "
            "the City Attorney's Office for use in litigation.\n\n"
            "AGENDA ITEM: Community Violence Intervention Program Funding\n"
            "ACTION: Council approved $1.2 million in one-time funding for the Phoenix "
            "CARES program, which deploys community violence interrupters in high-crime "
            "neighborhoods. Program targets a 20% reduction in gun violence in three "
            "pilot zip codes by end of fiscal year 2027. Vote: 6-1, Councilmember Simmons "
            "dissenting."
        ),
    },
]

# ---------------------------------------------------------------------------
# Example selector
# ---------------------------------------------------------------------------
def set_example():
    selected = st.session_state.example_selector
    for ex in EXAMPLES:
        if ex["label"] == selected:
            st.session_state.minutes_input = ex["text"]
            break

example_labels = ["— choose an example —"] + [ex["label"] for ex in EXAMPLES]
st.selectbox(
    "Try an example",
    options=example_labels,
    key="example_selector",
    on_change=set_example,
    label_visibility="visible",
)

# ---------------------------------------------------------------------------
# Text input
# ---------------------------------------------------------------------------
minutes_text = st.text_area(
    "Meeting minutes",
    key="minutes_input",
    height=280,
    placeholder="Paste city council or government meeting minutes here...",
    label_visibility="collapsed",
)

# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------
if st.button("Summarize", type="primary", use_container_width=True):
    if not minutes_text.strip():
        st.warning("Paste some meeting minutes first.")
    else:
        prompt = f"### Meeting Minutes:\n{minutes_text.strip()}\n\n### Summary:"
        with st.spinner("Reading the minutes..."):
            response = generate(
                model,
                tokenizer,
                prompt=prompt,
                max_tokens=300,
                verbose=False,
            )
        st.subheader("Summary")
        st.write(response)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "CivicDigest is a fine-tuned language model. "
    "Always verify summaries against official meeting records."
)
