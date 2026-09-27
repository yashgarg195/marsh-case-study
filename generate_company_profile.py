"""
generate_company_profile.py
===========================
Fetches verified external corporate facts via Wikipedia REST API, then
uses Gemini 3.5 Flash-Lite to synthesize corporate healthcare risks,
workforce exposures, and explicit assumptions.
"""

import os
import json
import logging
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any
from rapidfuzz import fuzz
import google.generativeai as genai
from dotenv import load_dotenv
from jsonschema import validate, ValidationError

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configure Gemini
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# JSON Schema for validation
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "company_name": {"type": "string"},
        "industry": {"type": "string"},
        "size": {"type": "string"},
        "key_risks": {
            "type": "array",
            "items": {"type": "string"}
        },
        "assumptions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "assumed_value": {},
                    "justification": {"type": "string"}
                },
                "required": ["field", "assumed_value", "justification"]
            }
        },
        "data_source": {"type": "string"},
        "is_unverified_entity": {"type": "boolean"}
    },
    "required": ["company_name", "industry", "size", "key_risks", "assumptions"]
}


def fetch_external_company_facts(company_name: str) -> Optional[Dict[str, Any]]:
    """
    Fetches real-time verified company facts from the public Wikipedia REST API.
    Includes safeguard: verifies title similarity to reject false-positive hits.
    """
    try:
        clean_query = company_name.strip()
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_query)}&format=json"
        
        req = urllib.request.Request(
            search_url, 
            headers={"User-Agent": "MarshPitchGenerator/2.0 (corporate-risk-advisory)"}
        )
        with urllib.request.urlopen(req, timeout=4) as res:
            search_data = json.loads(res.read().decode('utf-8'))
            hits = search_data.get("query", {}).get("search", [])
            if not hits:
                return None
            title = hits[0].get("title", "")

        if not title:
            return None

        # Safeguard: String similarity check to avoid false-positive search results
        match_score = fuzz.token_set_ratio(clean_query.lower(), title.lower())
        if match_score < 60:
            logger.info(f"Rejected weak Wikipedia search match: query='{clean_query}', hit='{title}' (score={match_score:.1f})")
            return None

        # Fetch page summary extract
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
        req_sum = urllib.request.Request(
            summary_url,
            headers={"User-Agent": "MarshPitchGenerator/2.0 (corporate-risk-advisory)"}
        )
        with urllib.request.urlopen(req_sum, timeout=4) as res:
            summary = json.loads(res.read().decode('utf-8'))
            return {
                "source": "Wikipedia",
                "title": summary.get("title", title),
                "description": summary.get("description", ""),
                "extract": summary.get("extract", "")
            }
    except Exception as e:
        logger.warning(f"External fact lookup for '{company_name}' fell back: {e}")
        return None


def generate_company_profile(company_name: str) -> dict:
    """
    Generates a company profile grounded in real-time public data from Wikipedia
    and synthesized with Gemini 3.5 Flash-Lite.
    
    Args:
        company_name (str): The name of the company to profile.
        
    Returns:
        dict: Inferred profile with industry, size, key risks, assumptions, and data source.
    """
    if not api_key:
        return {"error": "GEMINI_API_KEY environment variable not found."}

    clean_name = company_name.strip()
    if len(clean_name) < 2 or not any(c.isalpha() for c in clean_name):
        return {"error": "Invalid company query. Please provide an organization name containing alphabetic characters."}

    # Step 1: Live factual fetch (No LLM hallucination for company existence/basics)
    external_facts = fetch_external_company_facts(clean_name)
    facts_context = ""
    is_unverified = external_facts is None or not external_facts.get("extract")
    data_source_label = "LLM Inference (Wikipedia entry unavailable)"

    if not is_unverified:
        data_source_label = f"Wikipedia ({external_facts['title']})"
        facts_context = f"""
        VERIFIED FACTS FROM WIKIPEDIA:
        - Entity: {external_facts['title']}
        - Classification: {external_facts.get('description', 'N/A')}
        - Operational Overview: {external_facts['extract']}
        
        INSTRUCTION: Ground the industry and workforce scale directly in these verified facts.
        """
        logger.info(f"Successfully grounded '{clean_name}' using Wikipedia facts.")
    else:
        facts_context = f"""
        NOTICE: This company '{clean_name}' could not be verified in public corporate registries (it may be a private boutique, early-stage firm, or unlisted entity).
        INSTRUCTION: You must explicitly document all inferred fields (industry, size) under "assumptions" with a justification note explaining that public records were unavailable.
        """
        logger.info(f"No public Wikipedia facts found for '{clean_name}'; using direct synthesis with required assumptions.")

    # Step 2: Gemini risk synthesis
    try:
        model = genai.GenerativeModel('gemini-3.5-flash-lite')
        
        prompt = f"""
        You are an expert corporate risk and insurance advisor at Marsh.
        Generate a client health risk profile for the company: "{company_name}"
        Focus on information relevant for health insurance and corporate employee benefits pitching.
        
        {facts_context}
        
        You must output your response in JSON format matching this schema:
        {{
          "company_name": "{company_name}",
          "industry": "<Primary industry classification>",
          "size": "<Workforce headcount estimate, e.g. 'Large enterprise (~315,000+ employees)'>",
          "key_risks": [
            "<Specific health, lifestyle, operational, or occupational exposure relevant to their business model>"
          ],
          "assumptions": [
            {{
              "field": "<field name like 'size' or 'industry'>",
              "assumed_value": "<value>",
              "justification": "<one-line justification>"
            }}
          ],
          "data_source": "{data_source_label}"
        }}
        
        CRITICAL RULES:
        - Any field you do not confidently know must be explicitly documented in "assumptions" with a justification. Never silently guess.
        - If verified facts were provided above, align the industry and size with them.
        - Frame key risks constructively around workforce health, desk-bound/travel strains, retention, and medical coverage needs.
        """
        
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2,
            )
        )
        
        result_text = response.text
        data = json.loads(result_text)
        
        # Ensure data_source is present
        if "data_source" not in data:
            data["data_source"] = data_source_label

        # Validate against schema
        validate(instance=data, schema=RESPONSE_SCHEMA)
        
        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        return {"error": f"Failed to parse JSON response: {str(e)}"}
    except ValidationError as e:
        logger.error(f"JSON validation error: {e}")
        return {"error": f"JSON validation error: {str(e)}"}
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        return {"error": f"Error calling Gemini API: {str(e)}"}


if __name__ == "__main__":
    print(f"Testing generate_company_profile with 'Infosys'...")
    profile = generate_company_profile("Infosys")
    print(json.dumps(profile, indent=2))
