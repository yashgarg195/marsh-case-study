"""
Marsh Pitch Generator — Streamlit UI
=====================================
Main application entry point. Provides a UI for generating AI-powered
insurance marketing pitches and auditing them for factual accuracy.
"""

import os
import json
import streamlit as st
from dotenv import load_dotenv

# Load environment variables early
load_dotenv()

# Import project modules
from parse_policy_docs import parse_all_docs, load_chunks
from generate_company_profile import generate_company_profile
from generate_marketing_pitch import generate_marketing_pitch
from audit_pitch_content import audit_pitch_content
from render_pptx import render_pptx

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Marsh Pitch Generator",
    page_icon="🏢",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Custom CSS for Marsh branding
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header {
        color: #003087;
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 0;
    }
    .sub-header {
        color: #666;
        font-size: 1.1rem;
        margin-top: 0;
    }
    .pass-badge {
        background-color: #28a745;
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: bold;
    }
    .fail-badge {
        background-color: #dc3545;
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: bold;
    }
    .review-badge {
        background-color: #ffc107;
        color: black;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown('<p class="main-header">🏢 Marsh Pitch Generator</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">AI-powered insurance marketing pitches, grounded in policy documents & audited for accuracy</p>', unsafe_allow_html=True)
st.divider()

# ---------------------------------------------------------------------------
# Sidebar: Inputs
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Check for API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        st.error("⚠️ GEMINI_API_KEY not set. Add it to your `.env` file.")
        st.code("GEMINI_API_KEY=your_key_here", language="bash")
        st.stop()
    else:
        st.success("✅ Gemini API key loaded")
    
    st.divider()
    
    # Company name input
    company_name = st.text_input(
        "Company Name",
        placeholder="e.g., Infosys, Tata Consultancy Services",
        help="Enter the client company name to generate a tailored pitch."
    )
    
    # Policy document selection
    available_docs = {
        "ABHI_Product_Brochure": "Aditya Birla Health Insurance",
        "Care_Health_Product_Brochure": "Care Health Insurance",
        "HDFC_Product_Brochure": "HDFC ERGO Optima Secure+",
        "Niva_Bupa_Product_Brochure": "Niva Bupa Health Insurance",
    }
    
    selected_doc_keys = st.multiselect(
        "Policy Documents to Include",
        options=list(available_docs.keys()),
        default=list(available_docs.keys()),
        format_func=lambda x: available_docs.get(x, x),
        help="Select which policy documents to ground the pitch in."
    )
    
    st.divider()
    
    # Generate button
    generate_clicked = st.button("🚀 Generate Pitch", use_container_width=True, type="primary")

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

def display_slide(slide_data: dict, slide_idx: int):
    """Render a single slide card."""
    title = slide_data.get("title", f"Slide {slide_idx + 1}")
    bullets = slide_data.get("bullets", [])
    
    with st.container():
        st.markdown(f"### 📄 Slide {slide_data.get('slide_number', slide_idx + 1)}: {title}")
        for bullet in bullets:
            if isinstance(bullet, dict):
                text = bullet.get("text", "")
                source = bullet.get("source_chunk_id")
                if source:
                    st.markdown(f"- {text}  \n  <small style='color:#888'>📎 Source: `{source}`</small>", unsafe_allow_html=True)
                else:
                    st.markdown(f"- {text}  \n  <small style='color:#cc8800'>⚠️ No source reference</small>", unsafe_allow_html=True)
            else:
                st.markdown(f"- {bullet}")
        st.divider()


def display_audit_report(audit_result: dict):
    """Render the audit report with color coding."""
    status = audit_result.get("overall_status", "unknown")
    score = audit_result.get("confidence_score", 0)
    flagged = audit_result.get("flagged_claims", [])
    verified = audit_result.get("verified_claims_count", 0)
    total = audit_result.get("total_claims_count", 0)
    
    # Status badge
    if status == "pass":
        st.markdown(f'<span class="pass-badge">✅ AUDIT PASSED</span>', unsafe_allow_html=True)
    elif status == "fail":
        st.markdown(f'<span class="fail-badge">❌ AUDIT FAILED</span>', unsafe_allow_html=True)
    else:
        st.markdown(f'<span class="review-badge">⚠️ NEEDS REVIEW</span>', unsafe_allow_html=True)
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Confidence Score", f"{score:.0%}")
    col2.metric("Verified Claims", f"{verified}/{total}")
    col3.metric("Flagged Claims", len(flagged))
    
    # Flagged claims details
    if flagged:
        st.subheader("🚩 Flagged Claims")
        for claim in flagged:
            claim_status = claim.get("status", "unknown")
            if claim_status in ("not_supported", "invalid_reference"):
                icon = "🔴"
            elif claim_status == "untraceable":
                icon = "🟡"
            else:
                icon = "🟠"
            
            with st.expander(f"{icon} Slide {claim.get('slide', '?')}: {claim.get('bullet_text', '')[:80]}..."):
                st.markdown(f"**Status:** `{claim_status}`")
                st.markdown(f"**Reason:** {claim.get('reason', 'N/A')}")
                st.markdown(f"**Full text:** {claim.get('bullet_text', '')}")


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------
if generate_clicked:
    # Input validation
    if not company_name or not company_name.strip():
        st.error("❌ Please enter a company name.")
        st.stop()
    
    if not selected_doc_keys:
        st.error("❌ Please select at least one policy document.")
        st.stop()
    
    company_name = company_name.strip()
    
    # ---- Step 0: Parse policy documents ----
    with st.spinner("📄 Parsing policy documents..."):
        try:
            all_chunks = parse_all_docs()
            if not all_chunks:
                st.error("❌ No chunks extracted from policy documents. Check the `policies/` directory.")
                st.stop()
            
            # Filter chunks by selected docs
            chunks = [c for c in all_chunks if c.get("doc_name") in selected_doc_keys]
            if not chunks:
                st.error("❌ No chunks found for the selected documents.")
                st.stop()
            
            st.success(f"✅ Loaded {len(chunks)} chunks from {len(selected_doc_keys)} document(s)")
        except Exception as e:
            st.error(f"❌ Error parsing documents: {str(e)}")
            st.stop()
    
    # ---- Step 1: Generate Company Profile ----
    with st.spinner(f"🏢 Generating company profile for **{company_name}**..."):
        try:
            profile = generate_company_profile(company_name)
            if "error" in profile:
                st.error(f"❌ Company profile generation failed: {profile['error']}")
                st.stop()
            st.success("✅ Company profile generated")
        except Exception as e:
            st.error(f"❌ Error generating company profile: {str(e)}")
            st.stop()
    
    # ---- Step 2: Generate Marketing Pitch ----
    with st.spinner("📊 Generating marketing pitch..."):
        try:
            pitch_data = generate_marketing_pitch(profile, chunks)
            if not pitch_data.get("slides"):
                st.error("❌ Pitch generation returned no slides. Check API response.")
                st.stop()
            st.success(f"✅ Generated {len(pitch_data['slides'])} slides")
        except Exception as e:
            st.error(f"❌ Error generating pitch: {str(e)}")
            st.stop()
    
    # ---- Step 3: Audit Pitch Content ----
    with st.spinner("🔍 Auditing pitch for factual accuracy..."):
        try:
            audit_result = audit_pitch_content(pitch_data, chunks)
            st.success("✅ Audit complete")
        except Exception as e:
            st.error(f"❌ Error during audit: {str(e)}")
            audit_result = {
                "overall_status": "error",
                "confidence_score": 0.0,
                "flagged_claims": [],
                "verified_claims_count": 0,
                "total_claims_count": 0,
            }
    
    # ---- Step 4: Generate PPTX ----
    pptx_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pitch_output.pptx")
    with st.spinner("📑 Building PowerPoint deck..."):
        try:
            # Add company_name to pitch_data for the PPTX title slide
            pitch_data_with_name = {**pitch_data, "company_name": company_name}
            result = render_pptx(pitch_data_with_name, pptx_path)
            if result == pptx_path:
                st.success("✅ PowerPoint deck generated")
            else:
                st.warning(f"⚠️ PPTX generation issue: {result}")
        except Exception as e:
            st.warning(f"⚠️ Could not generate PPTX: {str(e)}")
            pptx_path = None
    
    # ---- Display Results ----
    st.divider()
    
    # Company Profile
    with st.expander("🏢 Company Profile", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Company:** {profile.get('company_name', company_name)}")
            st.markdown(f"**Industry:** {profile.get('industry', 'N/A')}")
            st.markdown(f"**Size:** {profile.get('size', 'N/A')}")
        with col2:
            st.markdown("**Key Risks:**")
            for risk in profile.get('key_risks', []):
                st.markdown(f"- {risk}")
        
        if profile.get('assumptions'):
            st.markdown("---")
            st.markdown("**⚠️ Assumptions Made:**")
            for assumption in profile['assumptions']:
                st.markdown(f"- **{assumption.get('field', '?')}**: {assumption.get('assumed_value', '?')} — _{assumption.get('justification', '')}_")
    
    # Generated Slides
    st.subheader("📊 Generated Pitch Deck")
    for idx, slide in enumerate(pitch_data.get("slides", [])):
        display_slide(slide, idx)
    
    # Recommended Policy
    rec = pitch_data.get("recommended_policy", {})
    if rec:
        st.subheader("⭐ Recommended Policy")
        st.info(f"**{rec.get('doc_name', 'N/A')}** — {rec.get('reason', 'No reason provided')}")
    
    # Audit Report
    st.subheader("🔍 Audit Report")
    display_audit_report(audit_result)
    
    # Download button
    if pptx_path and os.path.exists(pptx_path):
        with open(pptx_path, "rb") as f:
            st.download_button(
                label="📥 Download PowerPoint Deck",
                data=f.read(),
                file_name=f"marsh_pitch_{company_name.replace(' ', '_').lower()}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True,
            )
    
    # Raw JSON (collapsible)
    with st.expander("🔧 Raw JSON Output"):
        tab1, tab2, tab3 = st.tabs(["Profile", "Pitch", "Audit"])
        with tab1:
            st.json(profile)
        with tab2:
            st.json(pitch_data)
        with tab3:
            st.json(audit_result)
