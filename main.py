import os
import re
import random
import textwrap
import json
import asyncio
import warnings
import logging
import requests
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from google.auth.transport.requests import Request as GARequest
from google.oauth2 import id_token
from contextlib import asynccontextmanager

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()  # This loads .env file if it exists

# Ignore all warnings
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)

# Vector Search imports - For Vertex AI Vector Search RAG
try:
    from vector_search_tool import search_barash_content, VectorSearchTool
    VECTOR_SEARCH_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Vector Search imports failed: {e}")
    print("⚠️ Will fall back to MCP server if available")
    VECTOR_SEARCH_AVAILABLE = False

# Firestore imports - For saving scenarios
try:
    from firestore_service import get_firestore_service, FirestoreScenarioService
    FIRESTORE_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Firestore imports failed: {e}")
    print("⚠️ Scenarios will not be saved to Firestore")
    FIRESTORE_AVAILABLE = False

# Scenario Agent import
try:
    from agents.scenario_agent import ClinicalScenarioAgent
    CLINICAL_SCENARIO_AGENT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Scenario Agent imports failed: {e}")
    print("⚠️ Clinical scenario generation will not be available")
    CLINICAL_SCENARIO_AGENT_AVAILABLE = False

# Evaluations Agent import
try:
    from agents.evaluations_agent import EvaluationsAgent
    EVALUATIONS_AGENT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Evaluations Agent imports failed: {e}")
    print("⚠️ Demo evaluation generation will not be available")
    EVALUATIONS_AGENT_AVAILABLE = False

# Notification Agent import
try:
    from agents.notification_agent import NotificationAgent, create_notification_agent
    NOTIFICATION_AGENT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Notification Agent imports failed: {e}")
    print("⚠️ Notification monitoring will not be available")
    NOTIFICATION_AGENT_AVAILABLE = False

# ADK imports exactly as shown in the tutorial
try:
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm  # For multi-model support
    from google.adk.sessions import InMemorySessionService
    from google.adk.runners import Runner
    from google.genai import types  # For creating message Content/Parts
    ADK_IMPORTS = True
except ImportError as e:
    print(f"⚠️ ADK imports failed: {e}")
    print("⚠️ Will use ADK-compatible fallback implementation")
    ADK_IMPORTS = False

# Gemini API imports - For Google ADK Hackathon!
try:
    import google.generativeai as genai
    GEMINI_API_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Gemini API imports failed: {e}")
    GEMINI_API_AVAILABLE = False

# Vertex AI imports - For image generation
try:
    from vertexai.generative_models import GenerativeModel
    from vertexai.preview.vision_models import ImageGenerationModel
    import vertexai
    VERTEX_AI_IMPORTS = True
except ImportError as e:
    print(f"⚠️ Vertex AI imports failed: {e}")
    VERTEX_AI_IMPORTS = False

# Configure Gemini API for Google ADK Hackathon!
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_AVAILABLE and GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        print("✅ Gemini API configured successfully")
    except Exception as e:
        print(f"⚠️ Gemini API configuration failed: {e}")
        GEMINI_API_AVAILABLE = False
elif GEMINI_API_AVAILABLE and not GEMINI_API_KEY:
    print("⚠️ GEMINI_API_KEY environment variable not set")
    print("   Get your API key from: https://makersuite.google.com/app/apikey")
    GEMINI_API_AVAILABLE = False

# Configure Vertex AI (for image generation)
VERTEX_AI_AVAILABLE = False
if VERTEX_AI_IMPORTS:
    try:
        vertexai.init(project="precepgo-mentor-ai", location="us-central1")
        print("✅ Vertex AI initialized successfully (for image generation)")
        VERTEX_AI_AVAILABLE = True
    except Exception as e:
        print(f"⚠️ Vertex AI initialization failed: {e}")
        VERTEX_AI_AVAILABLE = False

# Configure ADK to use Vertex AI
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

# --- Define Model Constants for easier use ---
# Gemini API model identifiers (using models/ prefix for google-generativeai)
MODEL_GEMINI_FLASH = "models/gemini-2.5-flash"  # Fast and efficient
MODEL_GEMINI_PRO = "models/gemini-2.5-pro"      # Most powerful for deep research
MODEL_GEMINI_DEEP_THINK = "models/gemini-2.5-pro"  # Use Pro model (thinking-exp not available via API)

print("\nEnvironment configured for Google ADK Hackathon.")

# Mock classes for ADK-compatible fallback
class MockSessionService:
    async def create_session(self, app_name: str, user_id: str, session_id: str):
        return MockSession()

class MockSession:
    def __init__(self):
        self.state = {}

class MockAgent:
    def __init__(self, name: str, description: str, instructions: str, tools: list, model):
        self.name = name
        self.description = description
        self.instructions = instructions
        self.tools = tools
        self.model = model

class MockLiteLlm:
    def __init__(self, model: str):
        self.model = model

class MockRunner:
    def __init__(self, agent):
        self.agent = agent
    
    async def run(self, prompt: str, session):
        """Generate question using ADK-compatible fallback logic"""
        # Extract concept and level from session state
        concept = session.state.get("concept", "medical concept")
        level = session.state.get("level", "default")
        
        # Use the tools to generate question
        content = await get_medical_content(concept)
        patient = await select_patient_for_concept(concept)
        question_data = await generate_medical_question(concept, content, patient, level)
        
        # Return mock response with the actual question data
        return MockResponse(question_data)

class MockResponse:
    def __init__(self, question_data):
        # Store the complete question data
        self.question_data = question_data
        # Keep a simple content string for compatibility
        self.content = f"Generated question for: {question_data.get('concept', 'concept')}"

# Global state for scheduled research
research_state = {
    "running": False,
    "last_run": None,
    "last_chapter": None,
    "questions_generated": 0,
    "next_run": None,
    "status": "idle"
}

# Lifespan context manager for FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: No automatic background task - research is manual-only
    print("🚀 PrecepGo ADK Panel started - Research is manual trigger only")
    
    # Start Notification Agent monitoring
    if notification_agent:
        try:
            notification_agent.start()
            print("✅ Notification Agent monitoring started")
        except Exception as e:
            print(f"⚠️ Failed to start Notification Agent: {e}")
    
    yield
    
    # Shutdown
    if notification_agent:
        try:
            notification_agent.stop()
            print("🛑 Notification Agent stopped")
        except Exception as e:
            print(f"⚠️ Error stopping Notification Agent: {e}")
    
    print("🛑 PrecepGo ADK Panel shutting down...")

app = FastAPI(title="PrecepGo ADK Panel", lifespan=lifespan)

MCP_URL = os.getenv("MCP_URL")  # Legacy MCP server (deprecated in favor of Vector Search)
USE_VECTOR_SEARCH = os.getenv("USE_VECTOR_SEARCH", "true").lower() == "true"  # Use Vector Search by default

# Load medical concepts from JSON file
def load_medical_concepts() -> Dict[str, Any]:
    """Load medical concepts from JSON file"""
    try:
        with open("data/concepts.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("data/concepts.json not found, using fallback")
        return {"concepts": {}, "scenarios": [], "tags": []}
    except json.JSONDecodeError as e:
        print(f"Error parsing data/concepts.json: {e}")
        return {"concepts": {}, "scenarios": [], "tags": []}

# Load patient templates from JSON file
def load_patient_templates() -> list:
    """Load patient templates from JSON file"""
    try:
        with open("data/patient_templates.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("data/patient_templates.json not found, using fallback")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing data/patient_templates.json: {e}")
        return []

# Load cases from JSON file
def load_cases() -> list:
    """Load cases from JSON file"""
    try:
        with open("data/cases.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("data/cases.json not found, using fallback")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing data/cases.json: {e}")
        return []

# Load data at startup
MEDICAL_CONCEPTS = load_medical_concepts()
PATIENT_TEMPLATES = load_patient_templates()
CASES = load_cases()

# Initialize Clinical Scenario Agent
clinical_scenario_agent = None
if CLINICAL_SCENARIO_AGENT_AVAILABLE:
    try:
        clinical_scenario_agent = ClinicalScenarioAgent(
            cases=CASES,
            patient_templates=PATIENT_TEMPLATES
        )
        print("✅ Clinical Scenario Agent initialized")
    except Exception as e:
        print(f"⚠️ Failed to initialize Clinical Scenario Agent: {e}")
        clinical_scenario_agent = None

# Initialize Evaluations Agent
evaluations_agent = None
if EVALUATIONS_AGENT_AVAILABLE:
    try:
        evaluations_agent = EvaluationsAgent()
        print("✅ Evaluations Agent initialized")
    except Exception as e:
        print(f"⚠️ Failed to initialize Evaluations Agent: {e}")
        evaluations_agent = None

# Initialize Notification Agent
notification_agent = None
if NOTIFICATION_AGENT_AVAILABLE and FIRESTORE_AVAILABLE:
    try:
        # Get Firestore client for notification agent
        from google.cloud import firestore
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            notification_db = firestore.Client(project=project_id)
        else:
            notification_db = firestore.Client()
        
        notification_agent = NotificationAgent(
            admin_email="wasoje4172@fandoe.com",
            firestore_db=notification_db
        )
        print("✅ Notification Agent initialized")
    except Exception as e:
        print(f"⚠️ Failed to initialize Notification Agent: {e}")
        notification_agent = None
elif NOTIFICATION_AGENT_AVAILABLE:
    print("⚠️ Notification Agent not initialized: Firestore not available")

# MCP Client Helper
def _call_mcp(path: str, method: str = "GET", json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str,str]] = None):
    if not MCP_URL:
        raise HTTPException(status_code=500, detail="MCP_URL not set on ADK service")
    
    url = MCP_URL.rstrip("/") + path
    headers = {}
    
    # Try to get Google Cloud auth token if available
    try:
        audience = MCP_URL
        token = id_token.fetch_id_token(GARequest(), audience)
        headers["Authorization"] = f"Bearer {token}"
    except Exception as e:
        print(f"⚠️ Could not get Google Cloud auth token: {e}")
        print("⚠️ Attempting unauthenticated request to MCP server")
    
    if method == "POST":
        headers["Content-Type"] = "application/json"
        r = requests.post(url, headers=headers, json=json_body or {}, timeout=30)
    else:
        r = requests.get(url, headers=headers, params=params, timeout=30)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=f"MCP error: {r.text}")
    try:
        return r.json()
    except Exception:
        return {"text": r.text}

def process_mcp_response(res: dict, concept: str) -> dict:
    """Process MCP response to extract content and metadata"""
    result = {
        "content": "",
        "book_title": "",
        "chapter_title": "",
        "section_title": ""
    }
    
    if "results" in res and res["results"]:
        first_result = res["results"][0]
        result["content"] = first_result.get("matches", [{}])[0].get("context", "") if first_result.get("matches") else ""
        result["book_title"] = first_result.get("book_title", "")
        result["chapter_title"] = first_result.get("chapter_title", "")
        result["section_title"] = first_result.get("section_title", "")
        
        # Combine all match contexts for richer content
        if first_result.get("matches"):
            contexts = [match.get("context", "") for match in first_result["matches"][:3]]
            result["content"] = "\n".join(contexts)
    elif "content" in res:
        result["content"] = res["content"]
    elif "text" in res:
        result["content"] = res["text"]
    
    return result

def fetch_concept_text(concept: str) -> dict:
    """Fetch concept text and metadata from Barash using Vertex AI Vector Search"""
    # Use Vector Search if available, otherwise fall back to MCP
    if USE_VECTOR_SEARCH and VECTOR_SEARCH_AVAILABLE:
        try:
            print(f"🔍 Searching Barash using Vector Search for: '{concept}'")
            
            # Use vector search tool
            tool = VectorSearchTool()
            results = tool.search(query=concept, num_results=5)
            
            if results.get('success') and results.get('num_results', 0) > 0:
                # Combine all results into content
                documents = results['results']['documents']
                metadatas = results['results']['metadatas']
                
                # Extract metadata from first result
                first_meta = metadatas[0] if metadatas else {}
                section = first_meta.get('section', 'Unknown Section')
                topic = first_meta.get('topic', 'General')
                
                # Combine all document contexts
                combined_content = "\n\n".join(documents)
                
                # Extract section number from section name if available
                section_num = ""
                if section:
                    import re
                    match = re.search(r'Section\s+(\d+)', section, re.IGNORECASE)
                    if match:
                        section_num = match.group(1)
                
                print(f"✅ Found Barash content using Vector Search: {len(documents)} results from {section}")
                
                return {
                    "content": combined_content,
                    "book_title": "Barash, Cullen, and Stoelting's Clinical Anesthesia",
                    "chapter_title": topic or section,
                    "section_title": section,
                    "section_num": section_num,
                    "num_results": len(documents)
                }
            else:
                error_msg = results.get('error', 'No results found')
                print(f"⚠️ Vector Search found no results: {error_msg}")
                raise ValueError(f"Could not find Barash content for: '{concept}'. Error: {error_msg}")
                
        except Exception as e:
            print(f"⚠️ Vector Search error for '{concept}': {e}")
            if MCP_URL:
                print("⚠️ Falling back to MCP server...")
                return fetch_concept_text_mcp(concept)
            else:
                raise ValueError(f"Vector Search failed and MCP_URL not configured: {str(e)}")
    
    # Fall back to MCP if Vector Search not available
    elif MCP_URL:
        return fetch_concept_text_mcp(concept)
    else:
        raise ValueError("Neither Vector Search nor MCP_URL configured. Please set up Vector Search or configure MCP_URL")

def fetch_concept_text_mcp(concept: str) -> dict:
    """Legacy MCP server fetch (fallback only)"""
    if not MCP_URL:
        raise ValueError("MCP_URL not configured - cannot retrieve Barash content")
    
    # Extract key search terms from concept
    # Remove common words and focus on medical terms
    stop_words = ["and", "the", "in", "of", "for", "to", "with", "a", "an", "or"]
    words = concept.lower().split()
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    
    # Build search term list prioritizing medical keywords
    search_terms = [
        keywords[0] if keywords else concept,  # First medical keyword
        " ".join(keywords[:2]) if len(keywords) >= 2 else concept,  # First 2 keywords
        concept.split()[0],  # First word of original
        " ".join(keywords[:3]) if len(keywords) >= 3 else concept,  # First 3 keywords
        concept,  # Full original concept
    ]
    
    # Remove duplicates while preserving order
    search_terms = list(dict.fromkeys(search_terms))
    
    for search_term in search_terms:
        try:
            print(f"🔍 Searching Barash for: '{search_term}'")
            res = _call_mcp("/mcp/search", method="POST", json_body={"query": search_term})
            
            if isinstance(res, dict) and res.get("results"):
                mcp_data = process_mcp_response(res, concept)
                
                # Only accept results from Barash book
                if mcp_data.get("content") and "barash" in mcp_data.get("book_title", "").lower():
                    print(f"✅ Found Barash content using search term: '{search_term}'")
                    return mcp_data
                else:
                    print(f"⚠️ Results found but not from Barash book")
            else:
                print(f"⚠️ No results for: '{search_term}'")
                
        except Exception as e:
            print(f"⚠️ MCP search error for '{search_term}': {e}")
            continue
    
    # If we get here, we couldn't find Barash content
    raise ValueError(f"Could not find Barash content for: '{concept}'. Try simpler search terms like: {keywords[0] if keywords else concept.split()[0]}")

def select_appropriate_patient(concept: str, scenario: str) -> dict:
    """Select a patient template that matches the medical concept"""
    concept_lower = concept.lower()
    
    # Define concept-patient matching rules
    pediatric_concepts = ["pediatric", "child", "infant", "neonate", "tonsillectomy"]
    geriatric_concepts = ["elderly", "geriatric", "frail", "osteoporosis", "parkinson"]
    obesity_concepts = ["obesity", "bariatric", "morbid obesity", "sleep apnea"]
    cardiac_concepts = ["cardiac", "heart", "coronary", "hypertension", "heart failure"]
    airway_concepts = ["airway", "difficult airway", "intubation", "laryngoscopy"]
    
    # Filter patients based on concept
    suitable_patients = []
    
    for patient in PATIENT_TEMPLATES:
        age = patient["age"]
        categories = patient.get("categories", [])
        comorbidities = [c.lower() for c in patient["comorbidities"]]
        
        # Pediatric concepts need pediatric patients
        if any(pc in concept_lower for pc in pediatric_concepts):
            if "Pediatric" in categories or age < 18:
                suitable_patients.append(patient)
        
        # Geriatric concepts need elderly patients
        elif any(gc in concept_lower for gc in geriatric_concepts):
            if "Geriatric" in categories or age > 65:
                suitable_patients.append(patient)
        
        # Obesity concepts need obese patients
        elif any(oc in concept_lower for oc in obesity_concepts):
            if any("obesity" in c.lower() for c in comorbidities):
                suitable_patients.append(patient)
        
        # Cardiac concepts need patients with cardiac issues
        elif any(cc in concept_lower for cc in cardiac_concepts):
            if any(cc in c.lower() for c in comorbidities for cc in ["heart", "cardiac", "hypertension", "coronary"]):
                suitable_patients.append(patient)
        
        # Airway concepts can use any patient but prefer those with airway issues
        elif any(ac in concept_lower for ac in airway_concepts):
            if any("airway" in c.lower() or "respiratory" in c.lower() for c in patient.get("health_traits", [])):
                suitable_patients.append(patient)
            else:
                suitable_patients.append(patient)  # Any patient for general airway concepts
        
        # Default: any patient
        else:
            suitable_patients.append(patient)
    
    # If no suitable patients found, use all patients
    if not suitable_patients:
        suitable_patients = PATIENT_TEMPLATES
    
    return random.choice(suitable_patients)

def extract_keywords(txt: str, fallback: str) -> str:
    """Extract keywords from content"""
    candidates = re.findall(r"\b([A-Z][a-zA-Z-]{3,})\b", txt)
    for c in candidates:
        if c.lower() not in {"The","This","That","Which","With","While","Dose","Notes"}:
            return c
    return fallback

def extract_bullets(content: str, limit: int = 6) -> list:
    """Extract bullet points from content"""
    lines = [l.strip(" -•\t") for l in content.splitlines() if l.strip()]
    keep = [l for l in lines if any(k in l.lower() for k in
            ["step","ensure","avoid","monitor","dose","indication","contra","risk","complication","technique","position","device","plan","backup"])]
    if not keep:
        keep = lines
    uniq = []
    for l in keep:
        s = textwrap.shorten(l, width=120, placeholder="…")
        if s not in uniq:
            uniq.append(s)
    return uniq[:limit]

def select_appropriate_scenario(concept: str, level: str) -> str:
    """Select appropriate scenario based on concept - enhanced with Barash-specific scenarios"""
    concept_lower = concept.lower()
    
    # Barash-specific scenarios based on content
    barash_scenarios = {
        "genomic": ["coronary artery bypass grafting with genetic risk factors", "perioperative myocardial infarction risk assessment", "pharmacogenomic-guided drug selection"],
        "pharmacokinetic": ["target-controlled propofol infusion", "remifentanil-sevoflurane balanced anesthesia", "drug dosing in hepatic dysfunction"],
        "pharmacodynamic": ["opioid-hypnotic synergy optimization", "context-sensitive drug recovery", "MAC reduction with opioids"],
        "wound": ["major abdominal surgery with infection risk", "cardiac surgery requiring optimal tissue oxygenation", "contaminated trauma wound management"],
        "infection": ["surgical site infection prevention", "antibiotic prophylaxis for joint replacement", "immunocompromised patient undergoing surgery"],
        "allergic": ["suspected anaphylaxis during induction", "neuromuscular blocker administration with allergy history", "antibiotic selection with penicillin allergy"],
        "anesthesia mechanism": ["volatile anesthetic administration", "propofol infusion for sedation", "GABAergic modulation during anesthesia"],
        "gabaa": ["benzodiazepine administration", "etomidate use in hemodynamically unstable patient", "propofol for status epilepticus"],
        "mac": ["volatile anesthetic titration", "opioid-sparing anesthetic technique", "emergence from general anesthesia"],
        "cytochrome": ["warfarin management perioperatively", "opioid rotation in chronic pain patient", "drug interaction with azole antifungals"]
    }
    
    # Match concept to Barash scenarios
    for key, scenarios in barash_scenarios.items():
        if key in concept_lower:
            return random.choice(scenarios)
    
    # Try to find concept-specific scenarios from JSON
    for key, data in MEDICAL_CONCEPTS["concepts"].items():
        if concept_lower in key or key in concept_lower:
            scenarios = data.get("scenarios", [])
            if scenarios:
                return random.choice(scenarios)
    
    # High-risk scenarios for senior level
    if level == "senior" and any(term in concept_lower for term in ["airway", "difficult", "emergency"]):
        high_risk_scenarios = [
            "emergency cricothyrotomy", "massive hemorrhage", "cardiac arrest",
            "anaphylaxis", "malignant hyperthermia", "difficult airway with C-spine injury"
        ]
        return random.choice(high_risk_scenarios)
    
    # Standard scenarios
    scenarios = MEDICAL_CONCEPTS.get("scenarios", [
        "rapid sequence induction", "difficult airway", "emergent intubation",
        "pediatric tonsillectomy", "laparoscopic cholecystectomy",
        "cardiac induction with severe AS", "regional block with anticoagulation"
    ])
    return random.choice(scenarios)

# RAG Tools - Retrieval-Augmented Generation for factual accuracy
async def retrieve_medical_knowledge(concept: str) -> dict:
    """
    RAG Tool: Retrieve factual medical knowledge from authoritative sources.
    This ensures all generated content is grounded in real medical data.
    """
    mcp_data = fetch_concept_text(concept)
    content = mcp_data.get("content", "")
    
    # Extract structured knowledge from the content
    knowledge = {
        "concept": concept,
        "raw_content": content,
        "book_title": mcp_data.get("book_title", "Medical Knowledge Base"),
        "chapter_title": mcp_data.get("chapter_title", ""),
        "section_title": mcp_data.get("section_title", ""),
        "source": f"{mcp_data.get('book_title', 'MCP Medical Knowledge Base')}",
        "verified": True if content else False,
        "key_facts": [],
        "clinical_guidelines": [],
        "safety_considerations": []
    }
    
    # Add chapter citation if available
    if knowledge["chapter_title"]:
        knowledge["source"] += f" - {knowledge['chapter_title']}"
    
    # Parse content for structured information
    if content:
        lines = content.split('\n')
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ["guideline", "standard", "protocol", "aana", "asa"]):
                knowledge["clinical_guidelines"].append(line.strip())
            elif any(keyword in line_lower for keyword in ["safety", "risk", "caution", "contraindication", "complication"]):
                knowledge["safety_considerations"].append(line.strip())
            elif line.strip() and len(line.strip()) > 20:
                knowledge["key_facts"].append(line.strip())
    
    return knowledge

async def get_medical_content(concept: str) -> str:
    """ADK Tool: Get medical content for a concept from Barash Section 2 ONLY"""
    try:
        knowledge = await retrieve_medical_knowledge(concept)
        if not knowledge.get("raw_content"):
            raise ValueError(f"No Barash content found for: {concept}")
        return knowledge["raw_content"]
    except Exception as e:
        raise ValueError(f"Failed to retrieve Barash content for '{concept}': {str(e)}")

async def select_patient_for_concept(concept: str) -> dict:
    """ADK Tool: Select appropriate patient for concept"""
    return select_appropriate_patient(concept, "clinical scenario")

async def generate_clinical_image(concept: str, scenario: str) -> dict:
    """
    Generate a clinical image using Imagen 3 on Vertex AI.
    Creates simple, professional medical imagery relevant to the concept.
    """
    if not VERTEX_AI_AVAILABLE:
        return {
            "image_url": None,
            "image_prompt": "Image generation not available - Vertex AI not initialized. Run ./setup_gcloud_auth.sh to configure authentication.",
            "generated": False,
            "auth_required": True
        }
    
    try:
        # Create simple, professional prompt for CRNA clinical scenarios
        if "airway" in concept.lower():
            prompt = "Professional medical illustration: CRNA anesthesia provider performing airway management in modern operating room, medical equipment visible, clean clinical setting, realistic medical photography style"
        elif "induction" in concept.lower():
            prompt = "Professional medical illustration: CRNA preparing anesthesia induction, IV medications and monitoring equipment, sterile operating room environment, realistic medical photography style"
        elif "pediatric" in concept.lower():
            prompt = "Professional medical illustration: CRNA providing pediatric anesthesia care, child patient in safe surgical environment, medical monitors and equipment, realistic medical photography style"
        else:
            prompt = f"Professional medical illustration: CRNA anesthesia provider in operating room for {scenario}, medical equipment and monitoring systems, clean clinical setting, realistic medical photography style"
        
        # Generate image using Imagen 3
        model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        
        # Generate with safety filters and professional settings
        response = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="16:9",
            safety_filter_level="block_some",
            person_generation="allow_adult"
        )
        
        if response.images:
            image = response.images[0]
            # Convert to base64 for embedding
            import base64
            from io import BytesIO
            
            buffered = BytesIO()
            image._pil_image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            return {
                "image_url": f"data:image/png;base64,{img_str}",
                "image_prompt": prompt,
                "generated": True
            }
        else:
            return {
                "image_url": None,
                "image_prompt": prompt,
                "generated": False
            }
            
    except Exception as e:
        error_msg = str(e)
        print(f"Error generating image: {error_msg}")
        
        # Check if it's an authentication error
        auth_required = "authenticate" in error_msg.lower() or "credentials" in error_msg.lower()
        
        return {
            "image_url": None,
            "image_prompt": f"Image generation failed. {error_msg if not auth_required else 'Authentication required - run ./setup_gcloud_auth.sh to configure Google Cloud credentials.'}",
            "generated": False,
            "auth_required": auth_required
        }

async def fetch_all_barash_sections() -> list:
    """
    Fetch content from all 9 Barash sections for comprehensive research.
    Returns a list of section data with content from all chapters.
    """
    # All 9 Barash sections with key search terms
    sections = [
        {
            "section_num": 1,
            "section_name": "Introduction and Overview",
            "search_terms": [
                "History of Anesthesia",
                "Anesthesia Before Ether",
                "Physical and Psychological Anesthesia",
                "Early Analgesics and Soporifics",
                "Inhaled Anesthetics",
                "Control of the Airway",
                "Tracheal Intubation",
                "Advanced Airway Devices",
                "Anesthesia Delivery Systems",
                "Patient Monitors",
                "Safety Standards",
                "Professionalism and Anesthesia Practice"
            ]
        },
        {
            "section_num": 2,
            "section_name": "Basic Science and Fundamentals",
            "search_terms": [
                "Genomic Basis of Perioperative Precision Medicine",
                "Experimental Design and Statistics",
                "Inflammation, Wound Healing, and Infection",
                "The Allergic Response",
                "Mechanisms of Anesthesia and Consciousness",
                "Basic Principles of Clinical Pharmacology"
            ]
        },
        {
            "section_num": 3,
            "section_name": "Cardiac Anatomy and Physiology",
            "search_terms": [
                "Cardiac Anatomy",
                "Cardiac Physiology",
                "Cardiac Function",
                "Cardiovascular System",
                "Heart Anatomy",
                "Cardiac Cycle"
            ]
        },
        {
            "section_num": 4,
            "section_name": "Anesthetic Drugs and Adjuvants",
            "search_terms": [
                "Inhalation Anesthetics",
                "Intravenous Anesthetics",
                "Neuromuscular Blocking Agents",
                "Local Anesthetics",
                "Opioids",
                "Anesthetic Adjuvants"
            ]
        },
        {
            "section_num": 5,
            "section_name": "Preoperative Assessment and Perioperative Monitoring",
            "search_terms": [
                "Preoperative Assessment",
                "Perioperative Monitoring",
                "Patient Evaluation",
                "Anesthetic Risk Assessment",
                "ASA Physical Status",
                "Preoperative Testing"
            ]
        },
        {
            "section_num": 6,
            "section_name": "Basic Anesthetic Management",
            "search_terms": [
                "Anesthetic Induction",
                "Airway Management",
                "General Anesthesia",
                "Regional Anesthesia",
                "Anesthetic Maintenance",
                "Emergence from Anesthesia"
            ]
        },
        {
            "section_num": 7,
            "section_name": "Anesthesia Subspecialty Care",
            "search_terms": [
                "Neuroanesthesia",
                "Cerebral Perfusion",
                "Intracranial Pressure Monitoring",
                "Cerebral Oxygenation",
                "Cerebral Protection",
                "Hypothermia",
                "Pituitary Surgery",
                "Cerebral Aneurysm Surgery",
                "Epilepsy Surgery",
                "Awake Craniotomy",
                "Traumatic Brain Injury",
                "Spine Surgery",
                "Spinal Cord Injury"
            ]
        },
        {
            "section_num": 8,
            "section_name": "Anesthesia for Selected Surgical Services",
            "search_terms": [
                "Laparoscopic Surgery",
                "Robotic Surgery",
                "Physiologic Impact of Laparoscopy",
                "Cardiovascular System",
                "Respiratory System",
                "Pneumoperitoneum",
                "Positioning",
                "Monitoring",
                "Ventilation Management",
                "Fluid Management",
                "Complications",
                "Postoperative Management",
                "Acute Pain Management",
                "Postoperative Nausea and Vomiting"
            ]
        },
        {
            "section_num": 9,
            "section_name": "Postanesthetic Management, Critical Care, and Pain Management",
            "search_terms": [
                "Postanesthetic Management",
                "Critical Care",
                "Pain Management",
                "Postoperative Care",
                "Recovery Room",
                "PACU Management",
                "Postoperative Complications",
                "Respiratory Management",
                "Cardiovascular Management",
                "Neurologic Management",
                "Pain Assessment",
                "Analgesic Techniques",
                "Regional Analgesia",
                "Patient-Controlled Analgesia",
                "Chronic Pain Management"
            ]
        }
    ]
    
    all_sections_content = []
    
    for section in sections:
        print(f"📖 Fetching Section {section['section_num']}: {section['section_name']}")
        section_content = {
            "section_num": section["section_num"],
            "section_name": section["section_name"],
            "chapters": [],
            "total_content": "",
            "word_count": 0
        }
        
        # Search for each term in this section using Vector Search
        for term in section["search_terms"]:
            try:
                if USE_VECTOR_SEARCH and VECTOR_SEARCH_AVAILABLE:
                    # Use Vector Search with section filtering
                    tool = VectorSearchTool()
                    section_filter = f"Section {section['section_num']}"
                    
                    results = tool.search(
                        query=term,
                        num_results=10,  # Get more results per term
                        section_filter=section_filter
                    )
                    
                    if results.get('success') and results.get('num_results', 0) > 0:
                        documents = results['results']['documents']
                        chapter_content = "\n\n".join(documents)
                        
                        if chapter_content:
                            section_content["chapters"].append({
                                "title": term,
                                "content": chapter_content,
                                "word_count": len(chapter_content.split())
                            })
                            section_content["total_content"] += f"\n\n=== {term} ===\n\n{chapter_content}"
                    
                elif MCP_URL:
                    # Fallback to MCP
                    res = _call_mcp("/mcp/search", method="POST", json_body={
                        "query": term,
                        "limit": 50
                    })
                    
                    if res.get("results"):
                        chapter_content = ""
                        chapter_title = term
                        
                        # Combine all matches for this search term
                        for result in res["results"][:15]:
                            if result.get("matches"):
                                for match in result["matches"]:
                                    context = match.get("context", "")
                                    if context:
                                        chapter_content += context + "\n\n"
                        
                        if chapter_content:
                            # Check if this is from Barash book
                            if any("barash" in str(result.get("book_title", "")).lower() for result in res["results"][:5]):
                                section_content["chapters"].append({
                                    "title": chapter_title,
                                    "content": chapter_content,
                                    "word_count": len(chapter_content.split())
                                })
                                section_content["total_content"] += f"\n\n=== {chapter_title} ===\n\n{chapter_content}"
            
            except Exception as e:
                print(f"⚠️ Error fetching {term}: {e}")
                continue
        
        section_content["word_count"] = len(section_content["total_content"].split())
        if section_content["word_count"] > 0:
            all_sections_content.append(section_content)
            print(f"✅ Section {section['section_num']}: {len(section_content['chapters'])} chapters, {section_content['word_count']:,} words")
    
    return all_sections_content

async def fetch_full_barash_chapter() -> dict:
    """
    Fetch a full chapter from Barash Section 2 for deep research.
    Returns the complete chapter text for question generation.
    """
    # List of Barash Section 2 chapters
    chapters = [
        "Genomic Basis of Perioperative Precision Medicine",
        "Experimental Design and Statistics",
        "Inflammation, Wound Healing, and Infection",
        "The Allergic Response",
        "Mechanisms of Anesthesia and Consciousness",
        "Basic Principles of Clinical Pharmacology"
    ]
    
    # Rotate through chapters or select randomly
    chapter = random.choice(chapters)
    
    print(f"📖 Fetching chapter: {chapter}")
    
    try:
        # Try to get the full chapter from MCP
        res = _call_mcp("/mcp/search", method="POST", json_body={
            "query": chapter,
            "limit": 50  # Get more content for full chapter
        })
        
        if res.get("results"):
            # Combine all matches to get comprehensive chapter content
            full_content = ""
            for result in res["results"][:10]:  # Take top 10 results
                if result.get("matches"):
                    for match in result["matches"]:
                        context = match.get("context", "")
                        if context:
                            full_content += context + "\n\n"
            
            if full_content:
                return {
                    "chapter": chapter,
                    "content": full_content,
                    "word_count": len(full_content.split()),
                    "source": "Barash, Cullen, and Stoelting's Clinical Anesthesia - Section 2: Basic Science and Fundamentals"
                }
        
        # Fallback: Read from local file if MCP doesn't return enough
        print("⚠️ MCP returned limited content, using local file")
        with open("data/Section 2 - Basic Science and Fundamental's.txt", "r") as f:
            full_text = f.read()
        
        return {
            "chapter": chapter,
            "content": full_text[:50000],  # Take first 50k chars for now
            "word_count": len(full_text.split()),
            "source": "Barash, Cullen, and Stoelting's Clinical Anesthesia - Section 2: Basic Science and Fundamentals"
        }
        
    except Exception as e:
        print(f"❌ Error fetching chapter: {e}")
        # Fallback to local file
        with open("data/Section 2 - Basic Science and Fundamental's.txt", "r") as f:
            full_text = f.read()
        
        return {
            "chapter": "Section 2 - Basic Science and Fundamentals",
            "content": full_text[:50000],
            "word_count": len(full_text.split()),
            "source": "Barash, Cullen, and Stoelting's Clinical Anesthesia"
        }

async def generate_chapter_questions() -> dict:
    """
    Deep research on ALL Barash sections and generate comprehensive MCQ questions.
    Researches all 9 sections from the MCP server and creates expanded question set.
    """
    print("🔬 Starting comprehensive deep research on ALL Barash sections...")
    
    # Step 1: Fetch content from all 9 Barash sections
    all_sections = await fetch_all_barash_sections()
    
    if not all_sections:
        raise ValueError("No Barash content found in MCP server. Please verify MCP_URL is configured correctly.")
    
    total_words = sum(section["word_count"] for section in all_sections)
    total_chapters = sum(len(section["chapters"]) for section in all_sections)
    
    print(f"📊 Loaded {len(all_sections)} sections with {total_chapters} chapters")
    print(f"📝 Total word count: {total_words:,} words")
    
    # Combine all section content for comprehensive research
    combined_content = "\n\n".join([
        f"\n\n{'='*80}\nSECTION {section['section_num']}: {section['section_name']}\n{'='*80}\n\n{section['total_content']}"
        for section in all_sections
    ])
    
    # Calculate question distribution: concise set spanning all sections
    total_questions = 20  # Generate 20 questions covering all 9 sections
    
    # Step 2: Generate questions using Gemini API via the agent module
    questions_text = None
    
    if GEMINI_API_AVAILABLE:
        try:
            # Import and use the Gemini Agent module
            from gemini_agent import GeminiAgent
            
            print(f"🤖 Using Gemini Agent for question generation...")
            agent = GeminiAgent(model_name=MODEL_GEMINI_PRO)
            
            # Generate questions using the agent
            questions_text = agent.generate_questions(
                content=combined_content,
                num_questions=total_questions,
                sections=all_sections,
                temperature=0.1,
                max_tokens=16384
            )
            print("✅ Gemini API generation successful!")
            
        except ImportError:
            print("⚠️ Gemini agent module not found, please ensure gemini_agent.py exists")
            questions_text = None
        except Exception as e:
            print(f"⚠️ Gemini API failed: {e}")
            print("   Make sure GEMINI_API_KEY is set in .env file")
            questions_text = None
    
    # Step 2b: Fail if Gemini API didn't generate questions
    if not questions_text:
        error_msg = "❌ ERROR: Gemini API failed to generate questions. Please check:\n"
        error_msg += "   1. GEMINI_API_KEY is set in .env file\n"
        error_msg += "   2. API key is valid\n"
        error_msg += "   3. Check server logs for detailed error messages\n"
        print(error_msg)
        raise ValueError("Gemini API question generation failed. Check API key and logs for details.")
        
    # Step 3: Save to Questions.md file
    output_filename = "Context/Questions.md"
    
    with open(output_filename, "w") as f:
        f.write(f"# Comprehensive Multiple Choice Questions: All Barash Sections\n")
        f.write(f"## Based on Barash, Cullen, and Stoelting's Clinical Anesthesia, 9th Edition\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Sections Covered:** {len(all_sections)} sections (Sections 1-9)\n")
        f.write(f"**Total Chapters:** {total_chapters}\n")
        f.write(f"**Total Words:** {total_words:,}\n")
        f.write(f"**Total Questions:** {total_questions}\n\n")
        f.write("**Sections Included:**\n")
        for section in all_sections:
            f.write(f"- Section {section['section_num']}: {section['section_name']} ({len(section['chapters'])} chapters, {section['word_count']:,} words)\n")
        f.write("\n---\n\n")
        f.write("## Questions\n\n")
        f.write(questions_text)
        f.write("\n\n---\n\n")
        f.write(f"**Created:** {datetime.now().strftime('%B %d, %Y')}\n")
        f.write(f"**File Location:** {os.path.abspath(output_filename)}\n")
        f.write(f"**Source:** MCP Server - {MCP_URL}\n")
    
    # Update research state
    research_state["last_chapter"] = f"All {len(all_sections)} Sections"
    research_state["questions_generated"] = total_questions
    research_state["last_run"] = datetime.now()
    
    print(f"✅ Generated {total_questions} comprehensive questions from {len(all_sections)} sections and saved to {output_filename}")
    
    return {
        "success": True,
        "sections_covered": len(all_sections),
        "chapters_covered": total_chapters,
        "total_words": total_words,
        "questions_generated": total_questions,
        "file": output_filename,
        "timestamp": datetime.now().isoformat(),
        "sections": [f"Section {s['section_num']}: {s['section_name']}" for s in all_sections]
    }

async def generate_medical_question(concept: str, content: str, patient: dict, level: str) -> dict:
    """
    ADK Tool: Generate medical question with RAG-verified factual content.
    Uses Retrieval-Augmented Generation to ensure accuracy.
    """
    # RAG Step 1: Retrieve and verify knowledge
    knowledge = await retrieve_medical_knowledge(concept)
    
    if not knowledge["verified"]:
        raise ValueError(f"Could not retrieve verified medical knowledge for: {concept}")
    
    # RAG Step 2: Use retrieved facts to generate factually grounded content
    content = knowledge["raw_content"]
    
    # Create clinical vignette
    age = patient["age"]
    name = patient["full_name"].split()[-1].lower()
    female_names = {"nguyen", "patel", "chen", "okafor", "gomez", "hassan", "gomez"}
    sex = "female" if name in female_names else "male"
    weight_kg = patient["weight"]["kg"]
    weight_lbs = patient["weight"]["lbs"]
    comorbidities = patient["comorbidities"][:2] if len(patient["comorbidities"]) >= 2 else patient["comorbidities"]
    if not comorbidities:
        comorbidities = ["no significant comorbidities"]
    comorbid_text = ", ".join(str(c) for c in comorbidities)
    
    if age < 18:
        asa_class = random.choice(["ASA I", "ASA II"])
    elif age > 65 or len(patient["comorbidities"]) > 2:
        asa_class = random.choice(["ASA III", "ASA IV"])
    else:
        asa_class = random.choice(["ASA II", "ASA III"])
    
    scenario = select_appropriate_scenario(concept, level)
    
    vignette = (
        f"A {age}-year-old {sex} (Weight: {weight_kg} kg / {weight_lbs} lbs) presenting for {scenario}. "
        f"History: {asa_class}, {comorbid_text}. "
    )
    
    # Generate TWO narrative clinical choices that both seem plausible
    # Written as second-person actions describing what the CRNA does/thinks
    content_lower = content.lower()
    comorbidity1 = comorbidities[0] if len(comorbidities) > 0 else "medical history"
    comorbidity2 = comorbidities[1] if len(comorbidities) > 1 else "current condition"
    
    # Define realistic clinical narrative choice pairs based on concept
    if "pharmacokinetic" in concept.lower() or "pharmacodynamic" in concept.lower():
        option_a = f"You review the patient's {weight_kg}kg weight and calculate a standard propofol dose of 2mg/kg. You administer the induction dose and note acceptable hemodynamics, so you proceed with the case using your usual infusion rates."
        option_b = f"You consider that this patient's {comorbidity1.lower()} likely affects hepatic blood flow and drug clearance. You reduce your initial propofol dose by 30% and plan to titrate the infusion rate based on clinical effect, recognizing altered pharmacokinetics in this {asa_class} patient."
        correct_answer = "B"
        
    elif "cytochrome" in concept.lower() or "cyp" in concept.lower() or "p450" in concept.lower():
        option_a = f"You proceed with your planned fentanyl-based anesthetic, noting the patient takes antihypertensives. You figure the preoperative medications were held appropriately and continue with standard dosing."
        option_b = f"You review the patient's medication list and notice they take a CYP3A4 inhibitor. You adjust your opioid choice to remifentanil, which is metabolized by plasma esterases rather than hepatic CYP enzymes, avoiding potential drug accumulation."
        correct_answer = "B"
        
    elif "gabaa" in concept.lower() or "gaba" in concept.lower():
        option_a = f"You administer a propofol bolus of 200mg rapidly to ensure quick loss of consciousness. The patient's blood pressure drops to 75/40 mmHg but you expect it will recover as redistribution occurs."
        option_b = f"You recognize that GABAergic agents can cause dose-dependent cardiovascular depression, especially in this {asa_class} patient. You titrate propofol in 20mg increments, allowing 30-45 seconds between doses to assess effect while monitoring blood pressure continuously."
        correct_answer = "B"
        
    elif "mac" in concept.lower() or "alveolar" in concept.lower():
        option_a = f"You maintain sevoflurane at 2% (approximately 1 MAC) throughout the case. The patient is immobile and you feel confident this concentration provides adequate anesthesia."
        option_b = f"You've given fentanyl 200mcg for analgesia. Knowing that opioids reduce MAC by 50% or more, you decrease sevoflurane to 1% and reassess. This allows faster emergence while maintaining adequate anesthetic depth per Barash principles."
        correct_answer = "B"
        
    elif "anaphylaxis" in concept.lower() or "allergic" in concept.lower():
        option_a = f"You notice the blood pressure dropping to 70/40 mmHg after antibiotic administration. You give ephedrine 10mg IV and increase your IV fluid rate, thinking this is normal anesthetic-induced hypotension that will respond to vasopressor support."
        option_b = f"You see sudden hypotension (BP 70/40), flushing, and wheezing immediately after antibiotic infusion. Recognizing anaphylaxis, you stop all agents, call for help, give epinephrine 10-50mcg IV (titrating up as needed), provide 100% O2, and start rapid fluid resuscitation while preparing for potential cardiovascular collapse."
        correct_answer = "B"
        
    elif "wound" in concept.lower() or "oxygenation" in concept.lower():
        option_a = f"You maintain the patient's core temperature at 35.5°C to reduce metabolic demand. You keep IV fluids at maintenance rate (80ml/hr) to prevent volume overload, as the patient had acceptable vital signs throughout."
        option_b = f"You actively warm the patient to maintain normothermia above 36°C, knowing hypothermia causes vasoconstriction and impairs wound oxygen delivery. You give additional fluid boluses (500ml crystalloid) to optimize perfusion, as wound oxygenation depends on both temperature and tissue perfusion per Barash."
        correct_answer = "B"
        
    elif "antibiotic" in concept.lower() or "prophylaxis" in concept.lower():
        option_a = f"The surgery is slightly delayed. You decide to wait and give cefazolin 2g IV right as the surgeon makes the first incision so the antibiotic levels will be highest exactly when contamination occurs."
        option_b = f"You review the timing guidelines and administer cefazolin 2g IV at 30 minutes before the planned incision time. When surgery is delayed 20 minutes, you recognize you're still within the critical 60-minute pre-incision window that Barash describes as the 'decisive period' for antibiotic effectiveness."
        correct_answer = "B"
        
    elif "genomic" in concept.lower() or "genetic" in concept.lower():
        option_a = f"You note the patient's history of {comorbidity1.lower()} and proceed with your usual anesthetic technique. The patient had previous anesthetics without complications, so you use the same approach."
        option_b = f"You consider that the patient's {comorbidity1.lower()} and family history may indicate genetic susceptibility to perioperative MI. You review genetic risk factors from Barash Chapter 6 and choose an anesthetic technique that minimizes myocardial oxygen demand while planning enhanced monitoring."
        correct_answer = "B"
        
    elif "target-controlled" in concept.lower() or "tci" in concept.lower():
        option_a = f"You give propofol boluses (30mg every 2-3 minutes) based on the patient's clinical signs - watching for loss of eyelash reflex and acceptable blood pressure. You adjust doses based on what you see."
        option_b = f"You set up a target-controlled infusion system to maintain an effect-site concentration of 3mcg/ml propofol. This accounts for pharmacokinetic redistribution and allows more precise control than intermittent bolusing, with predictable emergence based on context-sensitive decrement time."
        correct_answer = "B"
        
    elif "opioid" in concept.lower() and "synergy" in concept.lower():
        option_a = f"You want to avoid opioid-related respiratory depression postoperatively. You maintain sevoflurane at 2.5% throughout the case, accepting some intraoperative hypertension but planning for faster wake-up."
        option_b = f"You combine remifentanil infusion (0.1mcg/kg/min) with lower sevoflurane (1%). Per Barash response surface models, this synergistic approach allows 50% reduction in volatile agent while maintaining hemodynamic stability and ensuring rapid, predictable emergence."
        correct_answer = "B"
        
    elif "context-sensitive" in concept.lower() or "half-time" in concept.lower():
        option_a = f"The case is running long (4 hours). You continue your fentanyl infusion at 2mcg/kg/hr, knowing its elimination half-life is relatively short and the patient should wake up reasonably quickly."
        option_b = f"After 4 hours of fentanyl infusion, you recognize that context-sensitive half-time increases dramatically with prolonged infusions due to peripheral tissue accumulation. You switch to remifentanil for the final hour to ensure predictable emergence, as its context-sensitive half-time remains <5 minutes regardless of infusion duration."
        correct_answer = "B"
        
    else:
        # Default: clinical judgment scenario with patient-specific factors
        option_a = f"You assess the patient's {comorbidity1.lower()} and {comorbidity2.lower()}, then proceed with your standard technique. The patient is {asa_class} but has had successful anesthetics before, so you use familiar doses and monitoring."
        option_b = f"You carefully consider how this patient's {comorbidity1.lower()} and {comorbidity2.lower()} alter anesthetic requirements. Following Barash principles, you individualize your approach by adjusting drug doses, enhancing monitoring, and preparing for potential complications specific to this {asa_class} patient's risk profile."
        correct_answer = "B"
    
    # Create options list with labels
    options = [
        {"label": "A", "text": option_a, "correct": correct_answer == "A"},
        {"label": "B", "text": option_b, "correct": correct_answer == "B"}
    ]
    
    # Get the correct answer text
    correct_answer_text = option_b if correct_answer == "B" else option_a
    incorrect_answer_text = option_a if correct_answer == "B" else option_b
    
    # RAG Step 3: Generate human-friendly rationale using retrieved facts and comparing both choices
    rationale_parts = []
    
    # Start with clinical context
    if age < 18:
        rationale_parts.append(f"**Clinical Context:** This is a {age}-year-old pediatric patient with {comorbid_text}, requiring careful consideration of age-appropriate dosing and physiologic responses.")
    elif age > 65:
        rationale_parts.append(f"**Clinical Context:** This {age}-year-old patient with {comorbid_text} presents age-related challenges requiring individualized anesthetic management.")
    else:
        rationale_parts.append(f"**Clinical Context:** A {age}-year-old {asa_class} patient with {comorbid_text} presenting for {scenario}.")
    
    rationale_parts.append("")
    
    # RAG: Add key facts from Barash if available
    if knowledge["key_facts"]:
        rationale_parts.append(f"**Key Principles from {knowledge['book_title']}:**")
        # Select most relevant key facts (limit to 2-3 for readability)
        for fact in knowledge["key_facts"][:3]:
            if len(fact) > 50:  # Only include substantial facts
                rationale_parts.append(f"• {fact[:280]}")
        rationale_parts.append("")
    
    # RAG: Use clinical guidelines if available
    if knowledge["clinical_guidelines"]:
        rationale_parts.append(f"**Evidence-Based Guidelines:**")
        for guideline in knowledge["clinical_guidelines"][:2]:
            rationale_parts.append(f"• {guideline[:250]}")
        rationale_parts.append("")
    
    # Explain why Choice B is correct and Choice A is incorrect
    rationale_parts.extend([
        "**Analysis of Choices:**",
        "",
        f"**Choice A** (Incorrect): \"{option_a}\"",
        f"This approach is suboptimal because:",
    ])
    
    # Specific reasoning for why Choice A is wrong - reference the narrative
    if "standard" in option_a.lower() or "usual" in option_a.lower():
        rationale_parts.append(f"• While this seems reasonable, it fails to account for how {comorbidity1.lower()} alters drug pharmacokinetics")
        rationale_parts.append(f"• Standard dosing ignores this {asa_class} patient's individual risk factors")
        rationale_parts.append(f"• Risk of hemodynamic instability or delayed emergence")
    elif "proceed" in option_a.lower() and "figured" in option_a.lower():
        rationale_parts.append(f"• Making assumptions about drug interactions without verification is risky")
        rationale_parts.append(f"• CYP450 interactions can cause significant drug accumulation")
        rationale_parts.append(f"• Barash Ch.11 emphasizes the importance of reviewing medication interactions")
    elif "rapidly" in option_a.lower() or "200mg" in option_a.lower():
        rationale_parts.append(f"• Rapid bolus dosing can cause profound hypotension, especially in {asa_class} patients")
        rationale_parts.append(f"• The significant BP drop (75/40) indicates excessive cardiovascular depression")
        rationale_parts.append(f"• This violates the principle of titrating GABAergic agents to effect")
    elif "1 mac" in option_a.lower() or "2%" in option_a.lower():
        rationale_parts.append(f"• Fails to utilize the MAC-sparing effects of opioids")
        rationale_parts.append(f"• Higher volatile concentrations prolong emergence unnecessarily")
        rationale_parts.append(f"• Doesn't optimize the synergy between agents described in Barash")
    elif "ephedrine" in option_a.lower() and "thinking this is normal" in option_a.lower():
        rationale_parts.append(f"• Misidentifies anaphylaxis as routine hypotension - critical diagnostic error")
        rationale_parts.append(f"• Ephedrine is inadequate for anaphylactic shock")
        rationale_parts.append(f"• Delay in epinephrine administration increases morbidity and mortality")
    elif "35.5" in option_a.lower() or "reduce metabolic" in option_a.lower():
        rationale_parts.append(f"• Hypothermia causes peripheral vasoconstriction, reducing wound oxygen delivery")
        rationale_parts.append(f"• Restrictive fluids in a normovolemic patient impairs tissue perfusion")
        rationale_parts.append(f"• Contradicts Barash evidence showing normothermia reduces infection rates")
    elif "right as" in option_a.lower() or "exactly when contamination" in option_a.lower():
        rationale_parts.append(f"• Antibiotics given at incision miss the 'decisive period' for effectiveness")
        rationale_parts.append(f"• Barash cites Classen's data showing highest infection rates with this timing")
        rationale_parts.append(f"• Antibiotics need time to achieve therapeutic tissue levels")
    elif "same approach" in option_a.lower() or "usual technique" in option_a.lower():
        rationale_parts.append(f"• Previous success doesn't guarantee safety in a different clinical context")
        rationale_parts.append(f"• Fails to consider genetic or physiologic factors affecting risk")
        rationale_parts.append(f"• Doesn't apply precision medicine principles")
    else:
        rationale_parts.append(f"• Does not individualize care for this patient's specific risk factors")
        rationale_parts.append(f"• Misses opportunity to apply Barash evidence-based principles")
        rationale_parts.append(f"• May lead to suboptimal outcomes")
    
    rationale_parts.extend([
        "",
        f"**Choice B** (Correct): \"{option_b}\"",
        f"This is the evidence-based approach because:",
    ])
    
    # Specific reasoning for why Choice B is correct
    if "adjust" in option_b.lower() or "pharmacokinetic" in option_b.lower():
        rationale_parts.append(f"• Accounts for altered drug clearance due to {comorbidities[0].lower()}")
        rationale_parts.append(f"• Optimizes drug dosing for safety and efficacy")
        rationale_parts.append(f"• Follows pharmacokinetic principles detailed in Barash Chapter 11")
    elif "titrate" in option_b.lower() or "monitor" in option_b.lower():
        rationale_parts.append(f"• Allows individualized dosing based on patient response")
        rationale_parts.append(f"• Minimizes risk of overdose in this {asa_class} patient")
        rationale_parts.append(f"• Maintains hemodynamic stability throughout the case")
    elif "before incision" in option_b.lower() or "60 minutes" in option_b.lower():
        rationale_parts.append(f"• Achieves therapeutic tissue levels during the 'decisive period' (Classen et al., per Barash)")
        rationale_parts.append(f"• Reduces surgical site infection rates by up to 50%")
        rationale_parts.append(f"• Supported by decades of evidence-based research")
    elif "epinephrine" in option_b.lower():
        rationale_parts.append(f"• Epinephrine is the first-line drug for anaphylaxis (per Barash Chapter 9)")
        rationale_parts.append(f"• Reverses vasodilation (α-effect) and bronchospasm (β2-effect)")
        rationale_parts.append(f"• Stopping anesthetic agents and fluid resuscitation address the pathophysiology")
    elif "synergy" in option_b.lower():
        rationale_parts.append(f"• Opioid-hypnotic synergy allows lower doses of each agent")
        rationale_parts.append(f"• Minimizes cardiovascular depression from high-dose volatile agents")
        rationale_parts.append(f"• Response surface models demonstrate optimal concentration pairs (Barash Ch.11)")
    else:
        rationale_parts.append(f"• Individualizes care based on patient's specific risk factors")
        rationale_parts.append(f"• Applies evidence-based principles from authoritative literature")
        rationale_parts.append(f"• Optimizes outcomes for this {asa_class} patient with {comorbidities[0].lower()}")
    
    rationale_parts.append("")
    
    # RAG: Add safety considerations from retrieved knowledge
    if knowledge["safety_considerations"]:
        rationale_parts.append("**Safety Considerations from Barash:**")
        for safety_point in knowledge["safety_considerations"][:2]:
            rationale_parts.append(f"• {safety_point[:250]}")
        rationale_parts.append("")
    
    # Add clinical pearls
    rationale_parts.extend([
        "**Clinical Pearls:**",
        f"• Patient weight ({weight_kg} kg) and comorbidities ({comorbid_text}) significantly impact drug selection",
        f"• {asa_class} classification indicates careful anesthetic planning required",
        f"• Evidence-based approach optimizes outcomes and minimizes complications",
        "",
        f"**Answer:** Choice {correct_answer} is correct.",
        "",
        f"**Reference:** {knowledge['source']}"
    ])
    
    rationale = "\n".join(rationale_parts)
    
    # Generate clinical image using Imagen 3
    image_data = await generate_clinical_image(concept, scenario)
    
    return {
        "format": "mcq_vignette",
        "question": vignette,
        "answer": correct_answer,  # "A" or "B"
        "correct_answer_text": correct_answer_text,
        "incorrect_answer_text": incorrect_answer_text,
        "options": options,  # List of dicts with label, text, correct
        "rationale": rationale,
        "concept": concept,
        "level": level,
        "scenario": scenario,
        "patient": patient,
        "image": image_data
    }

# ADK Agent System - Following the exact tutorial pattern
class ADKMedicalAgent:
    """ADK-based medical question generation agent following tutorial pattern"""
    
    def __init__(self):
        self.session_service = None
        self.agent = None
        self.runner = None
        self._initialize_adk()
    
    def _initialize_adk(self):
        """Initialize ADK components with Vertex AI"""
        try:
            # Check if ADK imports are available
            if not ADK_IMPORTS:
                print("⚠️ ADK not available, using ADK-compatible fallback")
                self._initialize_fallback()
                return
            
            # Check if Vertex AI is available
            if not VERTEX_AI_AVAILABLE:
                print("⚠️ Vertex AI not available, using ADK-compatible fallback")
                self._initialize_fallback()
                return
            
            # Create session service - exactly as tutorial
            self.session_service = InMemorySessionService()
            
            # Create agent with tools - following RAG pattern
            self.agent = Agent(
                name="Medical Question Generator with RAG",
                description="Evidence-based medical question generator using Retrieval-Augmented Generation",
                instructions="""
                You are an expert medical educator specializing in CRNA (Certified Registered Nurse Anesthetist) education.
                You use Retrieval-Augmented Generation (RAG) to ensure all content is factually accurate and evidence-based.
                
                RAG Process (CRITICAL - Follow this order):
                1. RETRIEVE: Use get_medical_content to fetch verified medical knowledge from authoritative sources
                2. VERIFY: Ensure the retrieved content is from reliable medical literature
                3. GENERATE: Use only the retrieved facts to create questions, answers, and rationales
                4. GROUND: All generated content must be traceable back to the retrieved medical knowledge
                
                Your role is to generate high-quality, clinically relevant multiple choice questions that test:
                - Clinical reasoning and decision-making based on ACTUAL medical guidelines
                - Patient safety principles from verified sources
                - Evidence-based practice from medical literature
                - AANA and ASA guidelines as documented in retrieved content
                
                Process:
                1. Use get_medical_content to fetch VERIFIED content for the concept
                2. Use select_patient_for_concept to choose appropriate patient demographics
                3. Use generate_medical_question to create the final question with patient context
                   - This function uses RAG to ensure accuracy
                
                Always ensure:
                - ALL content is grounded in retrieved medical knowledge (NO hallucinations!)
                - Patient demographics match the medical concept (pediatric concepts get pediatric patients)
                - Questions are appropriate for the specified level (junior/senior)
                - Answer choices are explanatory with clinical context
                - Rationales cite evidence from retrieved medical literature
                - Focus on practical clinical scenarios backed by real guidelines
                - Source attribution is included
                """,
                tools=[
                    get_medical_content,
                    select_patient_for_concept,
                    generate_medical_question
                ],
                model=LiteLlm(model=MODEL_GEMINI_FLASH)
            )
            
            # Create runner - exactly as tutorial
            self.runner = Runner(agent=self.agent)
            print("✅ ADK agent initialized successfully with Vertex AI")
            
        except Exception as e:
            print(f"Error initializing ADK: {e}")
            print("🔄 Falling back to ADK-compatible implementation")
            self._initialize_fallback()
    
    def _initialize_fallback(self):
        """Initialize ADK-compatible fallback system"""
        try:
            # Create mock session service
            self.session_service = MockSessionService()
            
            # Create mock agent
            self.agent = MockAgent(
                name="Medical Question Generator (ADK-Compatible)",
                description="Expert medical question generator for CRNA education",
                instructions="Generate clinically relevant medical questions using ADK-compatible fallback",
                tools=[get_medical_content, select_patient_for_concept, generate_medical_question],
                model=MockLiteLlm(model=MODEL_GEMINI_FLASH)
            )
            
            # Create mock runner
            self.runner = MockRunner(agent=self.agent)
            print("✅ ADK-compatible fallback initialized")
            
        except Exception as e:
            print(f"Error initializing fallback: {e}")
            self.agent = None
            self.runner = None
            self.session_service = None
    
    async def generate_question(self, concept: str, level: str) -> dict:
        """Generate a medical question using ADK agent - following tutorial pattern"""
        if not self.agent or not self.runner:
            raise HTTPException(status_code=500, detail="ADK agent not initialized")
        
        try:
            # Create session - exactly as tutorial
            session = await self.session_service.create_session(
                app_name="precepgo-adk-panel",
                user_id="system",
                session_id=f"question_{random.randint(1000, 9999)}"
            )
            
            # Set context in session state - following tutorial pattern
            session.state.update({
                "concept": concept,
                "level": level,
                "medical_concepts": MEDICAL_CONCEPTS,
                "patient_templates": PATIENT_TEMPLATES
            })
            
            # Generate question using ADK agent - exactly as tutorial
            prompt = f"""
            Generate a multiple choice question about {concept} for {level} level students.
            
            Use the tools to:
            1. Get medical content for {concept}
            2. Select an appropriate patient for this concept
            3. Generate the question with patient context
            
            Return the complete question with answer choices and rationale.
            """
            
            response = await self.runner.run(
                prompt=prompt,
                session=session
            )
            
            # For fallback, extract the actual question data
            if hasattr(response, 'question_data'):
                # This is the fallback MockResponse with structured data
                return response.question_data
            else:
                # This is a real ADK response (if ever available)
                return {
                    "question": response.content,
                    "format": "mcq_vignette",
                    "concept": concept,
                    "level": level
                }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"ADK error: {str(e)}")

# Initialize ADK agent
adk_agent = ADKMedicalAgent()

# Pydantic Models
class MakeQuestionRequest(BaseModel):
    concept: str
    level: str = "default"
    format: Optional[str] = "mcq_vignette"

# Note: match_patient_to_case and get_medical_content_for_scenario have been moved to ClinicalScenarioAgent
# These functions are now encapsulated within the agent and can be accessed via:
# clinical_scenario_agent.match_patient_to_case(case)
# clinical_scenario_agent.get_medical_content_for_scenario(case, patient)

# API Endpoints
@app.post("/mentor/make-scenario")
async def make_scenario():
    """
    Generate a clinical scenario with 2 decision options.
    Uses the Clinical Scenario Agent to handle the complete workflow.
    """
    if not clinical_scenario_agent:
        raise HTTPException(
            status_code=503,
            detail="Scenario Agent not available. Please ensure agents/scenario_agent.py is properly configured."
        )
    
    try:
        # Use the agent to generate the scenario
        scenario_data = clinical_scenario_agent.generate_scenario(
            save_to_file=True,
            save_to_firestore=True
        )
        
        # Return the scenario data
        return {
            "ok": True,
            "scenario": {
                "case": scenario_data.get("case", {}),
                "patient": scenario_data.get("patient", {}),
                "scenario": scenario_data.get("scenario", ""),
                "option_a": scenario_data.get("option_a", {}),
                "option_b": scenario_data.get("option_b", {}),
                "best_answer": scenario_data.get("best_answer", {}),
                "learning_points": scenario_data.get("learning_points", []),
                "references": scenario_data.get("references", "")
            },
            "firestore_id": scenario_data.get("firestore_id"),
            "saved_to_firestore": scenario_data.get("saved_to_firestore", False)
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating scenario: {str(e)}")

@app.post("/mentor/create-demo-evaluation")
async def create_demo_evaluation():
    """
    Create a demo evaluation document in Firestore.
    Uses the Evaluations Agent to generate fake evaluation data.
    """
    if not evaluations_agent:
        raise HTTPException(
            status_code=503,
            detail="Evaluations Agent not available. Please ensure agents/evaluations_agent.py is properly configured."
        )
    
    try:
        # Use the agent to create and save demo evaluation
        evaluation_data = evaluations_agent.create_and_save_demo_evaluation()
        
        # Clean the evaluation data for JSON serialization
        # Remove Firestore-specific objects that can't be serialized
        try:
            from google.cloud.firestore_v1 import SERVER_TIMESTAMP as _SERVER_TIMESTAMP
        except ImportError:
            _SERVER_TIMESTAMP = None
        
        cleaned_evaluation = {}
        for key, value in evaluation_data.items():
            # Skip SERVER_TIMESTAMP sentinels
            if _SERVER_TIMESTAMP and (value is _SERVER_TIMESTAMP or (hasattr(value, '__class__') and 'Sentinel' in str(type(value)))):
                continue
            # Skip internal Firestore fields that shouldn't be exposed
            elif key in ['created_at', 'modified_at', 'created_by']:
                continue
            # Convert GeoPoint to dict if present
            elif hasattr(value, 'latitude') and hasattr(value, 'longitude'):
                cleaned_evaluation[key] = {
                    "latitude": value.latitude,
                    "longitude": value.longitude
                }
            # Convert datetime objects to ISO strings
            elif isinstance(value, datetime):
                cleaned_evaluation[key] = value.isoformat()
            # Convert Firestore Timestamp objects
            elif hasattr(value, 'seconds') and hasattr(value, 'nanoseconds'):
                cleaned_evaluation[key] = {
                    "seconds": value.seconds,
                    "nanoseconds": getattr(value, 'nanoseconds', 0)
                }
            # Keep other values as-is
            else:
                try:
                    # Try to serialize to check if it's JSON-serializable
                    import json
                    json.dumps(value)
                    cleaned_evaluation[key] = value
                except (TypeError, ValueError):
                    # Convert non-serializable values to string
                    cleaned_evaluation[key] = str(value)
        
        # Return the cleaned evaluation data
        return {
            "ok": True,
            "evaluation": cleaned_evaluation,  # Return cleaned evaluation data
            "firestore_doc_id": evaluation_data.get("firestore_doc_id"),
            "firestore_parent_doc_id": evaluation_data.get("firestore_parent_doc_id"),
            "saved_to_firestore": evaluation_data.get("saved_to_firestore", False)
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creating demo evaluation: {str(e)}")

@app.get("/")
def root():
    return {"message": "PrecepGo ADK Panel - Medical Question Generator", "status": "running"}

@app.get("/adk/status")
def adk_status():
    """Check ADK agent status"""
    return {
        "adk_available": adk_agent.agent is not None,
        "runner_available": adk_agent.runner is not None,
        "session_service_available": adk_agent.session_service is not None,
        "agent_name": adk_agent.agent.name if adk_agent.agent else None,
        "model": "gemini-1.5-flash" if adk_agent.agent else None
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy", 
        "mcp_url_configured": bool(MCP_URL),
        "firestore_available": FIRESTORE_AVAILABLE
    }

@app.get("/mentor/concepts")
def get_available_concepts():
    """Get list of available medical concepts"""
    concepts = list(MEDICAL_CONCEPTS["concepts"].keys())
    return {
        "concepts": concepts,
        "total_count": len(concepts),
        "scenarios": MEDICAL_CONCEPTS.get("scenarios", []),
        "tags": MEDICAL_CONCEPTS.get("tags", [])
    }

@app.get("/mentor/patients")
def get_patient_templates():
    """Get list of available patient templates"""
    return {
        "patients": PATIENT_TEMPLATES,
        "total_count": len(PATIENT_TEMPLATES),
        "categories": list(set([cat for patient in PATIENT_TEMPLATES for cat in patient.get("categories", [])]))
    }

@app.get("/mentor/scenarios")
def list_scenarios(limit: int = 50):
    """
    List scenarios from Firestore.
    
    Args:
        limit: Maximum number of scenarios to return (default: 50)
        
    Returns:
        List of scenarios
    """
    if not FIRESTORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Firestore not available")
    
    try:
        firestore_service = get_firestore_service()
        if not firestore_service:
            raise HTTPException(status_code=503, detail="Firestore service not initialized")
        
        scenarios = firestore_service.list_scenarios(limit=limit)
        
        return {
            "ok": True,
            "scenarios": scenarios,
            "total_count": len(scenarios)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing scenarios: {str(e)}")

@app.get("/mentor/scenarios/{doc_id}")
def get_scenario(doc_id: str):
    """
    Get a specific scenario by Firestore document ID.
    
    Args:
        doc_id: Firestore document ID
        
    Returns:
        Scenario data
    """
    if not FIRESTORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Firestore not available")
    
    try:
        firestore_service = get_firestore_service()
        if not firestore_service:
            raise HTTPException(status_code=503, detail="Firestore service not initialized")
        
        scenario = firestore_service.get_scenario(doc_id)
        
        if not scenario:
            raise HTTPException(status_code=404, detail=f"Scenario not found: {doc_id}")
        
        return {
            "ok": True,
            "scenario": scenario
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting scenario: {str(e)}")

@app.get("/mentor/scenarios/by-case/{case_code}")
def get_scenarios_by_case(case_code: str):
    """
    Get scenarios filtered by case code.
    
    Args:
        case_code: Case code to filter by
        
    Returns:
        List of matching scenarios
    """
    if not FIRESTORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Firestore not available")
    
    try:
        firestore_service = get_firestore_service()
        if not firestore_service:
            raise HTTPException(status_code=503, detail="Firestore service not initialized")
        
        scenarios = firestore_service.get_scenarios_by_case(case_code)
        
        return {
            "ok": True,
            "scenarios": scenarios,
            "total_count": len(scenarios),
            "case_code": case_code
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying scenarios: {str(e)}")

@app.delete("/mentor/scenarios/{doc_id}")
def delete_scenario(doc_id: str):
    """
    Delete a scenario from Firestore.
    
    Args:
        doc_id: Firestore document ID
        
    Returns:
        Success status
    """
    if not FIRESTORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Firestore not available")
    
    try:
        firestore_service = get_firestore_service()
        if not firestore_service:
            raise HTTPException(status_code=503, detail="Firestore service not initialized")
        
        success = firestore_service.delete_scenario(doc_id)
        
        return {
            "ok": success,
            "deleted_id": doc_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting scenario: {str(e)}")

@app.get("/research/status")
def get_research_status():
    """Check status of scheduled research task"""
    return {
        "running": research_state["running"],
        "status": research_state["status"],
        "last_run": research_state["last_run"].isoformat() if research_state["last_run"] else None,
        "last_chapter": research_state["last_chapter"],
        "questions_generated": research_state["questions_generated"],
        "next_run_in_seconds": None  # Manual only - no automatic scheduling
    }

@app.post("/research/trigger")
async def trigger_research_now():
    """Manually trigger the research task immediately"""
    try:
        print("🎯 Manual research trigger requested")
        research_state["status"] = "running"
        research_state["running"] = True
        result = await generate_chapter_questions()
        research_state["status"] = "completed"
        research_state["running"] = False
        return {"ok": True, "result": result}
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Research failed: {error_msg}")
        research_state["status"] = f"error: {error_msg}"
        research_state["running"] = False
        raise HTTPException(status_code=500, detail=f"Research failed: {error_msg}")

@app.get("/research/questions")
def get_generated_questions():
    """Get the content of the generated Questions.md file"""
    try:
        with open("Context/Questions.md", "r") as f:
            content = f.read()
        return {
            "ok": True,
            "content": content,
            "file": "Context/Questions.md",
            "exists": True
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "content": "No questions generated yet. Click 'Trigger Research Now' to generate questions.",
            "file": "Context/Questions.md",
            "exists": False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading questions: {str(e)}")

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Simple HTML dashboard for testing the AI agent"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>PrecepGo ADK Panel - Medical Question Generator</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #2c3e50; text-align: center; margin-bottom: 30px; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; color: #34495e; }
            select, input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 16px; }
            button { background-color: #3498db; color: white; padding: 12px 24px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; width: 100%; }
            button:hover { background-color: #2980b9; }
            .result { margin-top: 30px; padding: 20px; background-color: #ecf0f1; border-radius: 5px; }
            .question { background-color: #fff3cd; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #ffc107; }
            .answer { background-color: #d4edda; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #28a745; }
            .options { background-color: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .rationale { background-color: #e2e3e5; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .loading { text-align: center; color: #6c757d; }
            .questions-display { background-color: white; padding: 20px; margin-top: 20px; border-radius: 8px; border: 2px solid #3498db; max-height: 600px; overflow-y: auto; }
            .questions-display h2, .questions-display h3 { color: #2c3e50; }
            .questions-display pre { background: #f5f5f5; padding: 10px; border-radius: 4px; white-space: pre-wrap; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏥 PrecepGo ADK Panel - Medical Question Generator</h1>
            <p style="text-align: center; color: #6c757d; margin-bottom: 10px;">
                <strong>Powered by Barash Clinical Anesthesia, 9th Edition + Vertex AI</strong>
            </p>
            <p style="text-align: center; color: #27ae60; margin-bottom: 30px; font-size: 14px;">
                📚 All 9 Barash Sections: Introduction, Basic Science, Cardiac, Pharmacology, Assessment, Management, Subspecialty Care, Surgical Services, Postanesthetic Care
            </p>
            
            <div style="background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #2196f3;">
                <strong>🔬 Manual Research Agent:</strong> 
                <span id="researchStatus">Loading...</span>
                <br><small style="color: #555;">Click the button below to trigger comprehensive research across ALL 9 Barash sections (Sections 1-9). This will generate 20 questions covering Introduction, Basic Science, Cardiac, Pharmacology, Assessment, Management, Subspecialty Care, Surgical Services, and Postanesthetic Care.</small>
                <br>
                <button onclick="triggerResearch()" style="margin-top: 10px; padding: 12px 24px; background: #2196f3; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🚀 Start Comprehensive Research (All 9 Sections)
                </button>
                <button onclick="checkStatus()" style="margin-top: 10px; padding: 8px 16px; background: #4caf50; color: white; border: none; border-radius: 4px; cursor: pointer; margin-left: 10px;">
                    🔄 Refresh Status
                </button>
            </div>
            
            <div style="background-color: #e8f5e9; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #27ae60;">
                <strong>📖 Content Source:</strong> All questions are generated from ALL 9 Barash sections via MCP server
                <br><small style="color: #555;"><strong>Sections covered:</strong> Section 1 (Introduction & Overview), Section 2 (Basic Science & Fundamentals), Section 3 (Cardiac Anatomy & Physiology), Section 4 (Anesthetic Drugs & Adjuvants), Section 5 (Preoperative Assessment & Monitoring), Section 6 (Basic Anesthetic Management), Section 7 (Anesthesia Subspecialty Care), Section 8 (Anesthesia for Selected Surgical Services), Section 9 (Postanesthetic Management, Critical Care, and Pain Management)</small>
            </div>
            
            <div style="background-color: #e8f5e9; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #4caf50;">
                <strong>📊 Create Demo Evaluation:</strong> 
                <br><small style="color: #555;">Generate a fake demo evaluation document and save it to Firestore subcollection 'agent_evaluations'. Creates realistic evaluation data with preceptee/preceptor info, scores, and metadata.</small>
                <br>
                <button onclick="createDemoEvaluation()" style="margin-top: 10px; padding: 12px 24px; background: #4caf50; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    📊 Create Demo Evaluation
                </button>
                <div id="evaluationResult" style="margin-top: 15px; display: none;"></div>
            </div>
            
            <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #ffc107;">
                <strong>🎯 Make Scenario:</strong> 
                <br><small style="color: #555;">Generate a clinical scenario with 2 decision options. The system will pick a random case, match it with an appropriate patient, search Vector DB for medical content, and create a challenging scenario for CRNA students.</small>
                <br>
                <button onclick="makeScenario()" style="margin-top: 10px; padding: 12px 24px; background: #ffc107; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🎯 Make Scenario
                </button>
                <div id="scenarioResult" style="margin-top: 15px; display: none;"></div>
            </div>
            
            <form id="questionForm">
                <div class="form-group">
                    <label for="concept">Medical Concept (from All Barash Sections):</label>
                    <select id="concept" name="concept" required>
                        <!-- Section 1: Introduction and Overview -->
                        <optgroup label="📖 Section 1: Introduction & Overview">
                            <option value="history of anesthesia">History of Anesthesia</option>
                            <option value="anesthesia before ether">Anesthesia Before Ether</option>
                            <option value="control of the airway">Control of the Airway</option>
                            <option value="tracheal intubation">Tracheal Intubation</option>
                            <option value="safety standards">Safety Standards</option>
                            <option value="professionalism in anesthesia">Professionalism in Anesthesia</option>
                        </optgroup>
                        
                        <!-- Section 2: Basic Science and Fundamentals -->
                        <optgroup label="📖 Section 2: Basic Science & Fundamentals">
                            <option value="perioperative genomics and precision medicine">Perioperative Genomics and Precision Medicine</option>
                            <option value="pharmacogenomics in anesthesia">Pharmacogenomics in Anesthesia</option>
                            <option value="genetic variability in drug response">Genetic Variability in Drug Response</option>
                            <option value="randomized controlled trials">Randomized Controlled Trials</option>
                            <option value="surgical site infection prevention">Surgical Site Infection Prevention</option>
                            <option value="anaphylaxis recognition and treatment">Anaphylaxis Recognition and Treatment</option>
                            <option value="GABAa receptors and anesthetic action">GABAa Receptors and Anesthetic Action</option>
                            <option value="minimum alveolar concentration">Minimum Alveolar Concentration (MAC)</option>
                            <option value="pharmacokinetics and pharmacodynamics">Pharmacokinetics and Pharmacodynamics</option>
                            <option value="cytochrome P450 interactions">Cytochrome P450 Drug Interactions</option>
                        </optgroup>
                        
                        <!-- Section 3: Cardiac Anatomy and Physiology -->
                        <optgroup label="📖 Section 3: Cardiac Anatomy & Physiology">
                            <option value="cardiac anatomy">Cardiac Anatomy</option>
                            <option value="cardiac physiology">Cardiac Physiology</option>
                            <option value="cardiovascular system">Cardiovascular System</option>
                            <option value="cardiac cycle">Cardiac Cycle</option>
                            <option value="heart function">Heart Function</option>
                        </optgroup>
                        
                        <!-- Section 4: Anesthetic Drugs and Adjuvants -->
                        <optgroup label="📖 Section 4: Anesthetic Drugs & Adjuvants">
                            <option value="inhalation anesthetics">Inhalation Anesthetics</option>
                            <option value="intravenous anesthetics">Intravenous Anesthetics</option>
                            <option value="neuromuscular blocking agents">Neuromuscular Blocking Agents</option>
                            <option value="local anesthetics">Local Anesthetics</option>
                            <option value="opioids">Opioids</option>
                            <option value="anesthetic adjuvants">Anesthetic Adjuvants</option>
                        </optgroup>
                        
                        <!-- Section 5: Preoperative Assessment and Monitoring -->
                        <optgroup label="📖 Section 5: Preoperative Assessment & Monitoring">
                            <option value="preoperative assessment">Preoperative Assessment</option>
                            <option value="perioperative monitoring">Perioperative Monitoring</option>
                            <option value="patient evaluation">Patient Evaluation</option>
                            <option value="ASA physical status">ASA Physical Status</option>
                            <option value="preoperative testing">Preoperative Testing</option>
                        </optgroup>
                        
                        <!-- Section 6: Basic Anesthetic Management -->
                        <optgroup label="📖 Section 6: Basic Anesthetic Management">
                            <option value="anesthetic induction">Anesthetic Induction</option>
                            <option value="airway management">Airway Management</option>
                            <option value="general anesthesia">General Anesthesia</option>
                            <option value="regional anesthesia">Regional Anesthesia</option>
                            <option value="anesthetic maintenance">Anesthetic Maintenance</option>
                            <option value="emergence from anesthesia">Emergence from Anesthesia</option>
                        </optgroup>
                        
                        <!-- Section 7: Anesthesia Subspecialty Care -->
                        <optgroup label="📖 Section 7: Anesthesia Subspecialty Care">
                            <option value="neuroanesthesia">Neuroanesthesia</option>
                            <option value="cerebral perfusion">Cerebral Perfusion</option>
                            <option value="intracranial pressure monitoring">Intracranial Pressure Monitoring</option>
                            <option value="cerebral protection">Cerebral Protection</option>
                            <option value="pituitary surgery">Pituitary Surgery</option>
                            <option value="cerebral aneurysm surgery">Cerebral Aneurysm Surgery</option>
                            <option value="traumatic brain injury">Traumatic Brain Injury</option>
                            <option value="spine surgery">Spine Surgery</option>
                        </optgroup>
                        
                        <!-- Section 8: Anesthesia for Selected Surgical Services -->
                        <optgroup label="📖 Section 8: Surgical Services">
                            <option value="laparoscopic surgery">Laparoscopic Surgery</option>
                            <option value="robotic surgery">Robotic Surgery</option>
                            <option value="pneumoperitoneum">Pneumoperitoneum</option>
                            <option value="positioning">Positioning</option>
                            <option value="ventilation management">Ventilation Management</option>
                            <option value="fluid management">Fluid Management</option>
                            <option value="postoperative management">Postoperative Management</option>
                        </optgroup>
                        
                        <!-- Section 9: Postanesthetic Management, Critical Care, and Pain Management -->
                        <optgroup label="📖 Section 9: Postanesthetic & Pain Management">
                            <option value="postanesthetic management">Postanesthetic Management</option>
                            <option value="critical care">Critical Care</option>
                            <option value="pain management">Pain Management</option>
                            <option value="recovery room">Recovery Room</option>
                            <option value="PACU management">PACU Management</option>
                            <option value="postoperative complications">Postoperative Complications</option>
                            <option value="analgesic techniques">Analgesic Techniques</option>
                            <option value="patient-controlled analgesia">Patient-Controlled Analgesia</option>
                        </optgroup>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="level">Student Level:</label>
                    <select id="level" name="level">
                        <option value="junior">Junior</option>
                        <option value="default" selected>Default</option>
                        <option value="senior">Senior</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="format">Question Format:</label>
                    <select id="format" name="format">
                        <option value="mcq_vignette" selected>Multiple Choice (MCQ)</option>
                    </select>
                </div>
                
                <button type="submit">Generate Question</button>
            </form>
            
            <div id="result" class="result" style="display: none;">
                <div id="loading" class="loading">Generating question with ADK agent...</div>
                <div id="questionContent" style="display: none;"></div>
            </div>
            
            <!-- Generated Questions Display -->
            <div style="margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h2 style="margin: 0; color: #2c3e50;">📚 Generated Questions (Context/Questions.md)</h2>
                    <button onclick="loadQuestions()" style="padding: 8px 16px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer;">
                        🔄 Refresh Questions
                    </button>
                </div>
                <div id="questionsDisplay" class="questions-display">
                    <p style="color: #6c757d; text-align: center;">Click "Refresh Questions" to load the latest generated questions...</p>
                </div>
            </div>
        </div>
        
        <script>
            // Check research status on page load
            async function checkStatus() {
                try {
                    const response = await fetch('/research/status');
                    const data = await response.json();
                    
                    const statusEl = document.getElementById('researchStatus');
                    let statusHTML = `Status: <strong style="color: ${data.status === 'completed' ? '#27ae60' : data.status === 'running' ? '#f39c12' : '#e74c3c'}">${data.status}</strong>`;
                    
                    if (data.last_run) {
                        const lastRun = new Date(data.last_run);
                        statusHTML += `<br>Last Run: ${lastRun.toLocaleString()}`;
                    }
                    
                    if (data.last_chapter) {
                        statusHTML += `<br>Last Chapter: ${data.last_chapter}`;
                        statusHTML += `<br>Questions: ${data.questions_generated}`;
                    }
                    
                    statusEl.innerHTML = statusHTML;
                } catch (error) {
                    document.getElementById('researchStatus').innerHTML = `<span style="color: #e74c3c;">Error checking status</span>`;
                }
            }
            
            // Trigger research manually
            async function triggerResearch() {
                const statusEl = document.getElementById('researchStatus');
                statusEl.innerHTML = '<strong style="color: #f39c12;">⏳ Running deep research...</strong>';
                
                try {
                    const response = await fetch('/research/trigger', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    
                    const data = await response.json();
                    
                    if (data.ok) {
                        alert(`✅ Research completed!\n\nChapter: ${data.result.chapter}\nQuestions: ${data.result.questions_generated}\nSaved to: ${data.result.file}`);
                        checkStatus();
                        loadQuestions();  // Auto-refresh questions after generation
                    } else {
                        alert('❌ Research failed. Check console for details.');
                        checkStatus();
                    }
                } catch (error) {
                    alert(`❌ Error: ${error.message}`);
                    checkStatus();
                }
            }
            
            // Load generated questions from Context/Questions.md
            async function loadQuestions() {
                const questionsEl = document.getElementById('questionsDisplay');
                questionsEl.innerHTML = '<p style="color: #f39c12; text-align: center;">⏳ Loading questions...</p>';
                
                try {
                    const response = await fetch('/research/questions');
                    const data = await response.json();
                    
                    if (data.ok && data.content) {
                        // Display markdown as preformatted text with basic styling
                        questionsEl.innerHTML = '<pre style="white-space: pre-wrap; font-family: inherit; line-height: 1.6;">' + 
                            data.content + '</pre>';
                    } else {
                        questionsEl.innerHTML = '<p style="color: #e74c3c; text-align: center;">No questions available yet. Generate some first!</p>';
                    }
                } catch (error) {
                    questionsEl.innerHTML = `<p style="color: #e74c3c; text-align: center;">Error loading questions: ${error.message}</p>`;
                }
            }
            
            // Check status on page load
            checkStatus();
            loadQuestions();
            
            // Refresh status every 30 seconds
            setInterval(checkStatus, 30000);
            
            // Refresh questions every 30 seconds
            setInterval(loadQuestions, 30000);
            
            // Create Demo Evaluation function
            async function createDemoEvaluation() {
                const resultDiv = document.getElementById('evaluationResult');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '<p style="color: #4caf50; text-align: center;">⏳ Creating demo evaluation... This may take a moment.</p>';
                
                try {
                    const response = await fetch('/mentor/create-demo-evaluation', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (data.ok && data.evaluation) {
                        const eval = data.evaluation;
                        
                        // Helper function to format AC scores
                        function formatACScores(eval) {
                            const acScores = [];
                            for (let i = 0; i <= 12; i++) {
                                const key = `ac_${i}`;
                                if (eval[key] !== undefined) {
                                    acScores.push({ key, score: eval[key] });
                                }
                            }
                            return acScores;
                        }
                        
                        // Helper function to format PC scores
                        function formatPCScores(eval) {
                            const pcScores = [];
                            for (let i = 0; i <= 10; i++) {
                                const key = `pc_${i}`;
                                if (eval[key] !== undefined) {
                                    pcScores.push({ key, score: eval[key] });
                                }
                            }
                            return pcScores;
                        }
                        
                        const acScores = formatACScores(eval);
                        const pcScores = formatPCScores(eval);
                        
                        let html = `
                            <div style="background: white; padding: 20px; border-radius: 8px; border: 2px solid #4caf50; margin-top: 15px;">
                                <h3 style="color: #2c3e50; margin-top: 0;">✅ Demo Evaluation Created</h3>
                                
                                <!-- Basic Info -->
                                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <h4 style="margin-top: 0; color: #495057;">Basic Information</h4>
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                                        <div><strong>Preceptee:</strong> ${eval.preceptee_user_name || 'Unknown'}</div>
                                        <div><strong>Preceptor:</strong> ${eval.preceptor_name || 'Unknown'}</div>
                                        <div><strong>Case Type:</strong> ${eval.case_type || 'Unknown'}</div>
                                        <div><strong>Class Standing:</strong> ${eval.class_standing || 'N/A'}</div>
                                        <div><strong>Completed:</strong> ${eval.completed ? 'Yes' : 'No'}</div>
                                        <div><strong>Doc ID:</strong> ${eval.docId || 'N/A'}</div>
                                        <div><strong>Request ID:</strong> ${eval.request_id || 'N/A'}</div>
                                        ${eval.timestamp ? `<div><strong>Timestamp:</strong> ${eval.timestamp.seconds ? new Date(eval.timestamp.seconds * 1000).toLocaleString() : eval.timestamp}</div>` : ''}
                                        ${eval.completion_date ? `<div><strong>Completion Date:</strong> ${eval.completion_date.seconds ? new Date(eval.completion_date.seconds * 1000).toLocaleString() : eval.completion_date}</div>` : ''}
                                        ${eval.request_date ? `<div><strong>Request Date:</strong> ${eval.request_date.seconds ? new Date(eval.request_date.seconds * 1000).toLocaleString() : eval.request_date}</div>` : ''}
                                    </div>
                                </div>
                                
                                <!-- Preceptor Comment -->
                                ${eval.comments ? `
                                    <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                        <h4 style="margin-top: 0; color: #1976d2;">📝 Preceptor Comment</h4>
                                        <p style="white-space: pre-wrap; line-height: 1.6; margin: 0;">${eval.comments}</p>
                                    </div>
                                ` : ''}
                                
                                <!-- Focus Areas -->
                                ${eval.focus_areas ? `
                                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                        <h4 style="margin-top: 0; color: #856404;">🎯 Focus Areas</h4>
                                        <p style="white-space: pre-wrap; line-height: 1.6; margin: 0;">${eval.focus_areas}</p>
                                    </div>
                                ` : ''}
                                
                                <!-- AC Scores -->
                                ${acScores.length > 0 ? `
                                    <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                        <h4 style="margin-top: 0; color: #495057;">📊 AC Scores (Anesthesia Competency)</h4>
                                        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px;">
                                            ${acScores.map(ac => `
                                                <div style="background: white; padding: 8px; border-radius: 4px; border-left: 3px solid #4caf50;">
                                                    <strong style="font-size: 0.85em;">${ac.key}:</strong><br>
                                                    <span style="font-size: 1.2em; font-weight: bold; color: #4caf50;">${ac.score}%</span>
                                                </div>
                                            `).join('')}
                                        </div>
                                    </div>
                                ` : ''}
                                
                                <!-- PC Scores -->
                                ${pcScores.length > 0 ? `
                                    <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                        <h4 style="margin-top: 0; color: #495057;">⭐ PC Scores (Performance Categories)</h4>
                                        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px;">
                                            ${pcScores.map(pc => {
                                                let scoreDisplay = '';
                                                let scoreColor = '#495057';
                                                if (pc.score === -1) {
                                                    scoreDisplay = '⚠️ Dangerous';
                                                    scoreColor = '#dc3545';
                                                } else if (pc.score === 0) {
                                                    scoreDisplay = 'N/A';
                                                    scoreColor = '#6c757d';
                                                } else {
                                                    scoreDisplay = '★'.repeat(pc.score) + '☆'.repeat(4 - pc.score);
                                                    scoreColor = pc.score >= 3 ? '#4caf50' : pc.score >= 2 ? '#ffc107' : '#dc3545';
                                                }
                                                return `
                                                    <div style="background: white; padding: 8px; border-radius: 4px; border-left: 3px solid ${scoreColor};">
                                                        <strong style="font-size: 0.85em;">${pc.key}:</strong><br>
                                                        <span style="font-size: 1.1em; font-weight: bold; color: ${scoreColor};">${scoreDisplay}</span>
                                                    </div>
                                                `;
                                            }).join('')}
                                        </div>
                                    </div>
                                ` : ''}
                        `;
                        
                        if (data.saved_to_firestore && data.firestore_doc_id) {
                            html += `
                                <div style="background: #d1f2eb; padding: 10px; border-radius: 5px; margin-top: 15px; border-left: 4px solid #27ae60;">
                                    <small style="color: #155724;">✅ Saved to Firestore</small><br>
                                    <small style="color: #155724;"><strong>Parent Doc:</strong> ${data.firestore_parent_doc_id || 'N/A'}</small><br>
                                    <small style="color: #155724;"><strong>Subcollection:</strong> agent_evaluations</small><br>
                                    <small style="color: #155724;"><strong>Document ID:</strong> <code>${data.firestore_doc_id}</code></small>
                                </div>
                            `;
                        } else {
                            html += `
                                <div style="background: #fff3cd; padding: 10px; border-radius: 5px; margin-top: 15px; border-left: 4px solid #ffc107;">
                                    <small style="color: #856404;">⚠️ Not saved to Firestore (Firestore may not be configured)</small>
                                </div>
                            `;
                        }
                        
                        html += `</div>`;
                        resultDiv.innerHTML = html;
                    } else {
                        resultDiv.innerHTML = `<p style="color: #e74c3c; text-align: center;">❌ Failed to create evaluation: ${data.error || 'Unknown error'}</p>`;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `<p style="color: #e74c3c; text-align: center;">❌ Error: ${error.message}</p>`;
                }
            }
            
            // Make Scenario function
            async function makeScenario() {
                const resultDiv = document.getElementById('scenarioResult');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '<p style="color: #f39c12; text-align: center;">⏳ Generating scenario... This may take a moment.</p>';
                
                try {
                    const response = await fetch('/mentor/make-scenario', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (data.ok && data.scenario) {
                        const scenario = data.scenario;
                        let html = `
                            <div style="background: white; padding: 20px; border-radius: 8px; border: 2px solid #ffc107; margin-top: 15px;">
                                <h3 style="color: #2c3e50; margin-top: 0;">🎯 Clinical Scenario</h3>
                                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <strong>Case:</strong> ${scenario.case?.name || 'Unknown'}<br>
                                    <strong>Patient:</strong> ${scenario.patient?.name || 'Unknown'} (Age: ${scenario.patient?.age || 'Unknown'})<br>
                                    <strong>Categories:</strong> ${scenario.patient?.categories?.join(', ') || 'N/A'}
                                </div>
                                
                                <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <h4 style="margin-top: 0; color: #1976d2;">📋 Scenario</h4>
                                    <p style="white-space: pre-wrap; line-height: 1.6;">${scenario.scenario || 'No scenario provided'}</p>
                                </div>
                                
                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;">
                                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #ffc107;">
                                        <h4 style="margin-top: 0; color: #856404;">Option A: ${scenario.option_a?.title || 'Option A'}</h4>
                                        <p style="white-space: pre-wrap; line-height: 1.6;">${scenario.option_a?.description || 'No description'}</p>
                                        ${scenario.option_a?.considerations ? '<ul style="margin: 10px 0;"><li>' + scenario.option_a.considerations.join('</li><li>') + '</li></ul>' : ''}
                                    </div>
                                    
                                    <div style="background: #d1ecf1; padding: 15px; border-radius: 5px; border-left: 4px solid #17a2b8;">
                                        <h4 style="margin-top: 0; color: #0c5460;">Option B: ${scenario.option_b?.title || 'Option B'}</h4>
                                        <p style="white-space: pre-wrap; line-height: 1.6;">${scenario.option_b?.description || 'No description'}</p>
                                        ${scenario.option_b?.considerations ? '<ul style="margin: 10px 0;"><li>' + scenario.option_b.considerations.join('</li><li>') + '</li></ul>' : ''}
                                    </div>
                                </div>
                                
                                ${scenario.best_answer ? `
                                    <div style="background: #d1f2eb; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #27ae60;">
                                        <h4 style="margin-top: 0; color: #155724;">✅ Best Answer: Option ${scenario.best_answer?.option || 'N/A'}</h4>
                                        <p style="white-space: pre-wrap; line-height: 1.6; font-weight: 500;">${scenario.best_answer?.rationale || 'No rationale provided'}</p>
                                    </div>
                                ` : ''}
                                
                                ${scenario.learning_points ? `
                                    <div style="background: #d4edda; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                        <h4 style="margin-top: 0; color: #155724;">📚 Learning Points</h4>
                                        <ul style="margin: 0;">
                                            ${scenario.learning_points.map(point => `<li style="margin-bottom: 8px;">${point}</li>`).join('')}
                                        </ul>
                                    </div>
                                ` : ''}
                                
                                ${scenario.references ? `
                                    <div style="background: #e2e3e5; padding: 15px; border-radius: 5px;">
                                        <strong>📖 References:</strong> ${scenario.references}
                                    </div>
                                ` : ''}
                                
                                ${data.firestore_id ? `
                                    <div style="background: #d1f2eb; padding: 10px; border-radius: 5px; margin-top: 15px; border-left: 4px solid #27ae60;">
                                        <small style="color: #155724;">✅ Saved to Firestore: <code>${data.firestore_id}</code></small>
                                    </div>
                                ` : ''}
                            </div>
                        `;
                        resultDiv.innerHTML = html;
                    } else {
                        resultDiv.innerHTML = `<p style="color: #e74c3c; text-align: center;">❌ Failed to generate scenario: ${data.error || 'Unknown error'}</p>`;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `<p style="color: #e74c3c; text-align: center;">❌ Error: ${error.message}</p>`;
                }
            }
            
            document.getElementById('questionForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const formData = new FormData(e.target);
                const data = Object.fromEntries(formData);
                
                const resultDiv = document.getElementById('result');
                const loadingDiv = document.getElementById('loading');
                const contentDiv = document.getElementById('questionContent');
                
                resultDiv.style.display = 'block';
                loadingDiv.style.display = 'block';
                contentDiv.style.display = 'none';
                
                try {
                    const response = await fetch('/mentor/create-question', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(data)
                    });
                    
                    const result = await response.json();
                    
                    if (result.ok) {
                        const q = result.question;
                        
                        // Generate image HTML if available
                        let imageHTML = '';
                        if (q.image && q.image.image_url) {
                            imageHTML = `
                                <h3>🖼️ Clinical Context:</h3>
                                <div style="margin: 15px 0; text-align: center;">
                                    <img src="${q.image.image_url}" 
                                         alt="Clinical scenario illustration" 
                                         style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                                    <p style="font-size: 12px; color: #6c757d; margin-top: 5px;">
                                        Generated by Imagen 3 on Vertex AI
                                    </p>
                                </div>
                            `;
                        }
                        
                        contentDiv.innerHTML = `
                            ${imageHTML}
                            <h3>📝 Question:</h3>
                            <div class="question">${q.question || 'Question content not available'}</div>
                            
                            <h3>🎯 Choose the Best Clinical Action:</h3>
                            <div class="options">
                                ${(q.options || []).map((option) => {
                                    const isCorrect = option.correct;
                                    const borderColor = isCorrect ? '#28a745' : '#6c757d';
                                    const bgColor = isCorrect ? '#d4edda' : '#f8f9fa';
                                    return `<div style="margin: 10px 0; padding: 15px; background: ${bgColor}; border-radius: 5px; border-left: 4px solid ${borderColor};">
                                        <div style="display: flex; align-items: start;">
                                            <div style="font-weight: bold; font-size: 20px; margin-right: 15px; color: ${borderColor};">
                                                ${option.label}
                                            </div>
                                            <div style="flex: 1;">
                                                <div style="font-size: 16px; line-height: 1.5;">
                                                    ${option.text}
                                                </div>
                                                ${isCorrect ? '<div style="margin-top: 8px; color: #28a745; font-weight: bold;">✓ Correct Answer</div>' : ''}
                                            </div>
                                        </div>
                                    </div>`;
                                }).join('')}
                            </div>
                            
                            <h3>💡 Detailed Rationale:</h3>
                            <div class="rationale" style="white-space: pre-wrap;">${q.rationale || 'Rationale not available'}</div>
                            
                            <div style="margin-top: 20px; padding: 10px; background: #d1ecf1; border-radius: 5px; font-size: 14px;">
                                <strong>Concept:</strong> ${q.concept || 'N/A'} | 
                                <strong>Level:</strong> ${q.level || 'N/A'} | 
                                <strong>Format:</strong> ${q.format || 'N/A'}
                            </div>
                        `;
                        
                        loadingDiv.style.display = 'none';
                        contentDiv.style.display = 'block';
                    } else {
                        contentDiv.innerHTML = `<div style="color: red;">Error: ${result.detail || 'Unknown error'}</div>`;
                        loadingDiv.style.display = 'none';
                        contentDiv.style.display = 'block';
                    }
                } catch (error) {
                    contentDiv.innerHTML = `<div style="color: red;">Error: ${error.message}</div>`;
                    loadingDiv.style.display = 'none';
                    contentDiv.style.display = 'block';
                }
            });
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)