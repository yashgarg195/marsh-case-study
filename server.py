"""
server.py
=========
FastAPI backend for Marsh Pitch Generator.
Exposes clean REST APIs for:
- Policy document management & drag-and-drop PDF uploads
- AI company profiling with assumption tracking
- Grounded pitch generation with source traceability
- Two-step factual accuracy auditing
- Executive PowerPoint presentation rendering & download
"""

import os
import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import pipeline modules
from parse_policy_docs import (
    load_chunks,
    parse_all_docs,
    get_available_docs,
    add_and_parse_doc
)
from generate_company_profile import generate_company_profile
from generate_marketing_pitch import generate_marketing_pitch
from audit_pitch_content import audit_pitch_content
from render_pptx import render_pptx
from render_audit_pdf import render_audit_pdf

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Marsh Pitch Generator API", version="2.0.0")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prevent aggressive browser caching of frontend static assets & download links
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in ("/", "/app.js", "/index.html") or path.startswith("/api/download"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Ensure exports directory exists
EXPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
os.makedirs(EXPORTS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------
class ProfileRequest(BaseModel):
    company_name: str

class PitchRequest(BaseModel):
    company_profile: Dict[str, Any]
    selected_policies: Optional[List[str]] = None

class AuditRequest(BaseModel):
    pitch_data: Dict[str, Any]
    selected_policies: Optional[List[str]] = None

class FullPipelineRequest(BaseModel):
    company_name: str
    selected_policies: Optional[List[str]] = None
    company_profile_override: Optional[Dict[str, Any]] = None

class RenderPptxRequest(BaseModel):
    pitch_data: Dict[str, Any]
    company_name: Optional[str] = "Client"

class RenderAuditPdfRequest(BaseModel):
    company_name: str
    company_profile: Dict[str, Any]
    pitch_data: Dict[str, Any]
    audit_report: Dict[str, Any]
    selected_policies: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    api_key_configured = bool(os.getenv("GEMINI_API_KEY"))
    return {
        "status": "healthy",
        "api_key_configured": api_key_configured,
        "model": "gemini-3.5-flash-lite"
    }


@app.get("/api/policies")
def list_policies():
    """Returns all available policy documents and their chunk counts."""
    try:
        policies = get_available_docs()
        chunks = load_chunks()
        return {
            "policies": policies,
            "total_chunks": len(chunks)
        }
    except Exception as e:
        logger.error(f"Error listing policies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clause/{chunk_id}")
def get_clause_detail(chunk_id: str):
    """Retrieves full text and metadata for a specific policy clause ID."""
    chunks = load_chunks()
    match = next((c for c in chunks if str(c.get("chunk_id")) == chunk_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Clause '{chunk_id}' not found.")
    return match


@app.post("/api/upload-policy")
async def upload_policy(file: UploadFile = File(...)):
    """Upload a new policy PDF document, extracts its sections, and updates chunk index."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    try:
        content = await file.read()
        res = add_and_parse_doc(content, file.filename)
        policies = get_available_docs()
        return {
            "message": f"Successfully indexed policy '{res['doc_name']}'",
            "details": res,
            "policies": policies
        }
    except Exception as e:
        logger.error(f"Error uploading policy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process policy PDF: {str(e)}")


@app.post("/api/profile")
def create_profile(req: ProfileRequest):
    """Generates an AI-inferred company profile with explicit assumptions."""
    name = req.company_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Company name cannot be empty.")
    
    try:
        profile = generate_company_profile(name)
        if "error" in profile:
            raise HTTPException(status_code=500, detail=profile["error"])
        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Company profile error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pitch")
def create_pitch(req: PitchRequest):
    """Generates a grounded 3-5 slide marketing pitch based on company profile and policy chunks."""
    selected_docs = req.selected_policies or []
    chunks = load_chunks(selected_docs if selected_docs else None)
    
    if not chunks:
        # Fallback to parse all docs if cache not populated
        chunks = parse_all_docs()
        if selected_docs:
            chunks = [c for c in chunks if c.get("doc_name") in selected_docs]
            
    if not chunks:
        raise HTTPException(status_code=400, detail="No policy chunks available for the selected documents.")
        
    try:
        pitch = generate_marketing_pitch(req.company_profile, chunks)
        if not pitch.get("slides"):
            raise HTTPException(status_code=500, detail="Failed to generate slide content.")
        return pitch
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pitch generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/audit")
def audit_pitch(req: AuditRequest):
    """Audits pitch content for factual accuracy against the source policy chunks."""
    selected_docs = req.selected_policies or []
    chunks = load_chunks(selected_docs if selected_docs else None)
    
    if not chunks:
        chunks = parse_all_docs()
        if selected_docs:
            chunks = [c for c in chunks if c.get("doc_name") in selected_docs]
            
    try:
        report = audit_pitch_content(req.pitch_data, chunks)
        return report
    except Exception as e:
        logger.error(f"Audit error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/render-pptx")
def export_pptx(req: RenderPptxRequest):
    """Renders the executive PowerPoint deck and returns download link."""
    company_clean = (req.company_name or "client").replace(" ", "_").lower()
    filename = f"marsh_pitch_{company_clean}.pptx"
    output_path = os.path.join(EXPORTS_DIR, filename)
    
    data_with_name = {**req.pitch_data, "company_name": req.company_name}
    result = render_pptx(data_with_name, output_path)
    
    if result != output_path:
        raise HTTPException(status_code=500, detail=f"PPTX generation error: {result}")
        
    return {
        "filename": filename,
        "download_url": f"/api/download-pptx/{filename}"
    }


@app.get("/api/download-pptx/{filename}")
def download_pptx(filename: str):
    file_path = os.path.join(EXPORTS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found. Please generate the pitch first.")
    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache"
        }
    )



@app.post("/api/render-audit-pdf")
def export_audit_pdf(req: RenderAuditPdfRequest):
    """Renders the executive Audit & Traceability Report PDF and returns download link."""
    company_clean = (req.company_name or "client").replace(" ", "_").lower()
    filename = f"marsh_audit_report_{company_clean}.pdf"
    output_path = os.path.join(EXPORTS_DIR, filename)

    selected_docs = req.selected_policies or []
    chunks = load_chunks(selected_docs if selected_docs else None)
    if not chunks:
        chunks = parse_all_docs()

    result = render_audit_pdf(
        company_name=req.company_name,
        company_profile=req.company_profile,
        pitch_data=req.pitch_data,
        audit_report=req.audit_report,
        chunks=chunks,
        output_path=output_path
    )

    if result != output_path:
        raise HTTPException(status_code=500, detail=f"Audit PDF generation error: {result}")

    return {
        "filename": filename,
        "download_url": f"/api/download-audit-pdf/{filename}"
    }


@app.get("/api/download-audit-pdf/{filename}")
def download_audit_pdf(filename: str):
    file_path = os.path.join(EXPORTS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found. Please generate the pitch first.")
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache"
        }
    )


# ---------------------------------------------------------------------------
# Mount Static Frontend
# ---------------------------------------------------------------------------
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    # Make sure cache is primed
    parse_all_docs()
    port = int(os.getenv("PORT", 8000))
    print(f"\n🚀 Marsh Pitch Generator API & UI running on: http://localhost:{port}\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
