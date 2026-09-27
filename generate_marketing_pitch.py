"""
generate_marketing_pitch.py
============================
Calls the Gemini API to generate a structured marketing pitch based on
a company profile and policy document chunks.
"""

import os
import json
import logging
from typing import Dict, List, Any
from dotenv import load_dotenv
import google.generativeai as genai

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Gemini API
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
else:
    logger.warning("GEMINI_API_KEY not found in environment variables. Set it in .env file.")


def _validate_pitch(data: dict) -> bool:
    """Validate that the pitch data matches the expected schema."""
    if not isinstance(data, dict):
        return False
    if "slides" not in data or "recommended_policy" not in data:
        return False
    if not isinstance(data["slides"], list) or len(data["slides"]) == 0:
        return False
    for slide in data["slides"]:
        if not isinstance(slide, dict):
            return False
        if "slide_number" not in slide or "title" not in slide or "bullets" not in slide:
            return False
        if not isinstance(slide["bullets"], list):
            return False
        for bullet in slide["bullets"]:
            if not isinstance(bullet, dict) or "text" not in bullet:
                return False
    rec = data["recommended_policy"]
    if not isinstance(rec, dict):
        return False
    if "doc_name" not in rec or "reason" not in rec:
        return False
    return True


def generate_marketing_pitch(company_profile: Dict[str, Any], chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generates a structured marketing pitch using Gemini API.

    Args:
        company_profile: Output from generate_company_profile.
        chunks: List of chunk dicts from parse_policy_docs.

    Returns:
        A dictionary with 'slides' and 'recommended_policy' keys.
    """
    if not api_key:
        return {
            "slides": [],
            "recommended_policy": {"doc_name": "Error", "reason": "GEMINI_API_KEY not set", "source_chunk_id": "none"}
        }

    try:
        model = genai.GenerativeModel(
            model_name='gemini-3.5-flash-lite',
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2,
            )
        )

        # Prepare chunk summaries with IDs
        available_chunk_ids = [chunk.get("chunk_id") for chunk in chunks if chunk.get("chunk_id")]
        
        # Build chunk context (include full text for grounding)
        chunk_context = []
        for c in chunks:
            chunk_context.append({
                "chunk_id": c.get("chunk_id"),
                "doc_name": c.get("doc_name"),
                "section_title": c.get("section_title"),
                "text": c.get("text", "")
            })

        prompt = f"""You are an expert insurance broker at Marsh. Create a compelling, personalized marketing pitch for a prospective client.

CLIENT PROFILE:
{json.dumps(company_profile, indent=2)}

AVAILABLE POLICY DOCUMENT CHUNKS (use these as your ONLY source of truth for policy details):
{json.dumps(chunk_context, indent=2)}

VALID SOURCE CHUNK IDs (you may ONLY use these IDs):
{json.dumps(available_chunk_ids)}

OUTPUT FORMAT — Return a JSON object with this EXACT structure:
{{
  "slides": [
    {{
      "slide_number": <int>,
      "title": "<string>",
      "bullets": [
        {{"text": "<string>", "source_chunk_id": "<string or null>"}}
      ]
    }}
  ],
  "recommended_policy": {{
    "doc_name": "<string — the doc_name of the recommended policy, e.g. 'ABHI_Product_Brochure'>",
    "insurer_name": "<string — official corporate name of the insurer, e.g. 'Aditya Birla Health Insurance' or 'HDFC ERGO General Insurance'>",
    "product_name": "<string — specific product name, e.g. 'Activ One VIP+' or 'Optima Secure+'>",
    "reason": "<string — why this policy is recommended>",
    "source_chunk_id": "<string — chunk_id supporting the recommendation>"
  }}
}}

SLIDE REQUIREMENTS:
1. Slide 1: Company overview — summarize the client's industry, size, and key risk exposures. These bullets will have source_chunk_id = null (they come from the profile, not policy docs).
2. Slide 2: Why choose Marsh — general value proposition about Marsh's expertise, market position, and advisory capabilities. These bullets will have source_chunk_id = null.
3. Slide 3-4: Policy benefits mapped to the company's key risks — for EACH key risk, identify specific policy benefits that address it. EVERY bullet about a specific coverage amount, benefit, limit, waiting period, or policy feature MUST include the source_chunk_id of the chunk you found it in.
4. Final slide: Recommended policy — name the single best policy for this client and explain why.

CRITICAL RULES:
- EVERY bullet describing a specific coverage amount, benefit, limit, or policy feature MUST include a valid source_chunk_id from the list above.
- If a claim cannot be traced to a specific chunk, set source_chunk_id to null. NEVER fabricate a chunk ID.
- Only use chunk IDs from the 'VALID SOURCE CHUNK IDs' list.
- Produce 3-5 slides total.
- Make bullets concise and actionable.
"""

        # Attempt 1
        try:
            logger.info("Generating marketing pitch via Gemini API...")
            response = model.generate_content(prompt)
            pitch_data = json.loads(response.text)
            
            if _validate_pitch(pitch_data):
                logger.info(f"Successfully generated pitch with {len(pitch_data['slides'])} slides")
                return pitch_data
            else:
                logger.warning("First attempt returned invalid schema. Retrying...")
                raise ValueError("Invalid pitch schema")
                
        except Exception as e:
            logger.warning(f"First attempt failed: {e}. Retrying once...")
            # Retry once
            response = model.generate_content(prompt)
            pitch_data = json.loads(response.text)
            
            if _validate_pitch(pitch_data):
                logger.info(f"Retry succeeded with {len(pitch_data['slides'])} slides")
                return pitch_data
            else:
                logger.error("Retry also returned invalid schema")
                return {
                    "slides": [],
                    "recommended_policy": {
                        "doc_name": "Error",
                        "reason": "Failed to generate valid pitch after 2 attempts",
                        "source_chunk_id": "none"
                    }
                }

    except Exception as e:
        logger.error(f"Failed to generate marketing pitch: {e}")
        return {
            "slides": [],
            "recommended_policy": {
                "doc_name": "Error",
                "reason": str(e),
                "source_chunk_id": "none"
            }
        }


if __name__ == "__main__":
    from parse_policy_docs import parse_all_docs
    from generate_company_profile import generate_company_profile
    
    # Parse docs first
    chunks = parse_all_docs()
    
    # Generate a test profile
    profile = generate_company_profile("Infosys")
    print("Profile:", json.dumps(profile, indent=2))
    
    if "error" not in profile:
        pitch = generate_marketing_pitch(profile, chunks)
        print("\nPitch:", json.dumps(pitch, indent=2))
