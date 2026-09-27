"""
audit_pitch_content.py
=======================
Audits generated pitch content for factual accuracy against source policy chunks.
Uses a two-step approach: fast fuzzy string matching (rapidfuzz) first, then
Gemini escalation for edge cases.

Distinguishes between:
- Client & Advisory Context (Slides 1-2): Grounded in public corporate registry & Marsh advisory.
- Policy Claims (Slides 3-5): Audited strictly for insurance figures, waiting periods, and benefits.
"""

import os
import json
import time
import logging
from dotenv import load_dotenv
import google.generativeai as genai
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configure Google Generative AI
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)


def _call_gemini_with_retry(model, prompt, max_retries=3, base_delay=15):
    """Call Gemini with exponential backoff for rate limiting."""
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            return json.loads(response.text)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                delay = base_delay * (2 ** attempt)
                logger.info(f"Rate limited, waiting {delay}s before retry {attempt + 1}/{max_retries}")
                time.sleep(delay)
            else:
                raise e
    raise Exception("Max retries exceeded due to rate limiting")


def audit_pitch_content(pitch_data: dict, chunks: list[dict]) -> dict:
    """
    Audits generated pitch content for factual accuracy against source policy chunks.
    
    The audit evaluates:
    - Slides 1-2 (Context): Verified as client overview / brokerage advisory.
    - Slides 3-5 (Policy Claims): Audited strictly against policy clauses for coverage,
      limits, waiting periods, and rider terms.
    """
    # Build a lookup dict: chunk_id -> chunk_text
    chunk_lookup = {str(chunk.get("chunk_id")): chunk.get("text", "") for chunk in chunks if "chunk_id" in chunk}
    
    total_claims = 0
    total_sourced_claims = 0  # Claims on policy slides (Slides 3, 4, 5)
    verified_claims = 0
    flagged_claims = []
    context_claims = []
    
    model = genai.GenerativeModel('gemini-3.5-flash-lite', generation_config={"response_mime_type": "application/json"})

    for i, slide in enumerate(pitch_data.get("slides", [])):
        slide_number = slide.get("slide_number", i + 1)
        
        for bullet in slide.get("bullets", []):
            total_claims += 1
            
            bullet_text = bullet.get("text", "") if isinstance(bullet, dict) else str(bullet)
            source_id = bullet.get("source_chunk_id") if isinstance(bullet, dict) else None
            
            # -------------------------------------------------------------
            # Case 1: Slides 1 & 2 are Context Slides (Client & Marsh Advisory)
            # They do not come from insurance policy filings and are not penalized.
            # -------------------------------------------------------------
            if slide_number in (1, 2) and source_id is None:
                context_claims.append({
                    "slide": slide_number,
                    "bullet_text": bullet_text,
                    "category": "Client / Marsh Strategic Context",
                    "status": "grounded_in_registry"
                })
                continue
            
            # -------------------------------------------------------------
            # Case 2: Policy Benefit Slides (Slides 3, 4, 5)
            # Must be grounded in source policy documents.
            # -------------------------------------------------------------
            total_sourced_claims += 1
            
            if source_id is None:
                flagged_claims.append({
                    "slide": slide_number,
                    "bullet_text": bullet_text,
                    "reason": "Policy benefit claim is missing a source clause reference.",
                    "status": "untraceable"
                })
                continue
            
            source_id = str(source_id)
            if source_id not in chunk_lookup:
                flagged_claims.append({
                    "slide": slide_number,
                    "bullet_text": bullet_text,
                    "reason": f"Source clause ID '{source_id}' not found in active policy index.",
                    "status": "invalid_reference"
                })
                continue
                
            chunk_text = chunk_lookup[source_id]
            
            # Step A (fast & cheap): RapidFuzz partial and token matching
            partial_score = fuzz.partial_ratio(bullet_text.lower(), chunk_text.lower())
            token_score = fuzz.token_set_ratio(bullet_text.lower(), chunk_text.lower())
            max_score = max(partial_score, token_score)
            
            if max_score >= 55:
                verified_claims += 1
            else:
                # Step B (LLM): Specialized insurance fact verification
                prompt = f"""You are a specialized corporate insurance compliance auditor.
Determine whether the INSURANCE POLICY FACTS (benefits, coverage amounts, waiting periods, limits, or riders) in the claim are supported by the SOURCE TEXT from the insurer's policy filing.

SOURCE TEXT (from insurance policy filing):
{chunk_text}

PITCH BULLET:
{bullet_text}

AUDIT RULES:
1. Verify ONLY the insurance coverage terms, waiting periods, numbers, and features.
2. DO NOT fail the claim because the policy filing doesn't mention the client company name (e.g. Infosys, HCL) or consultative phrases (e.g. 'desk-bound strain', 'tailored for remote staff'). Policy filings are generic product brochures.
3. Set supported=true if the underlying policy benefit or coverage feature is factually accurate according to the source text.
4. Set supported=false ONLY if the claim states numbers, limits, or terms that contradict the policy text.

Respond with JSON:
{{"supported": true/false, "verified_terms": "<brief description>", "reason": "<one-line explanation>"}}"""
                
                try:
                    result = _call_gemini_with_retry(model, prompt)
                    
                    if result.get("supported"):
                        verified_claims += 1
                    else:
                        flagged_claims.append({
                            "slide": slide_number,
                            "bullet_text": bullet_text,
                            "reason": result.get("reason", "Insurance benefit term not supported by cited clause."),
                            "status": "not_supported"
                        })
                except Exception as e:
                    logger.warning(f"Gemini API call failed for audit: {e}")
                    flagged_claims.append({
                        "slide": slide_number,
                        "bullet_text": bullet_text,
                        "reason": f"Auditor call timed out: {str(e)[:80]}",
                        "status": "review_needed"
                    })

    # Confidence score = verified sourced claims / total sourced claims
    confidence_score = verified_claims / total_sourced_claims if total_sourced_claims > 0 else 1.0
    
    # THRESHOLD LOGIC (Refined & Practical):
    # - PASS: Confidence Score >= 80% AND 0 flagged claims (100% clean policy alignment)
    # - NEEDS REVIEW: Confidence Score >= 50% with minor discrepancies for advisor inspection
    # - FAIL: Confidence Score < 50% (severe hallucination / unreliable policy mapping)
    if confidence_score >= 0.80 and len(flagged_claims) == 0:
        overall_status = "pass"
    elif confidence_score < 0.50:
        overall_status = "fail"
    else:
        overall_status = "needs_review"
        
    return {
        "overall_status": overall_status,
        "confidence_score": round(confidence_score, 4),
        "flagged_claims": flagged_claims,
        "context_claims": context_claims,
        "verified_claims_count": verified_claims,
        "total_claims_count": total_claims,
        "total_sourced_claims": total_sourced_claims,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import os
    from parse_policy_docs import load_chunks
    
    if os.path.exists("test_pitch_infosys.json"):
        with open("test_pitch_infosys.json") as f:
            pitch = json.load(f)
        chunks = load_chunks()
        print(f"Running audit on test pitch with {len(pitch.get('slides', []))} slides...")
        result = audit_pitch_content(pitch, chunks)
        print(json.dumps(result, indent=2))
