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
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
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
    from vector_search_tool import VectorSearchTool
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

# State Agent import
try:
    from agents.state_agent import StateAgent
    STATE_AGENT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ State Agent imports failed: {e}")
    print("⚠️ Agent state tracking will not be available")
    STATE_AGENT_AVAILABLE = False

# COA Compliance Agent import
try:
    from agents.coa_agent import COAComplianceAgent, create_coa_agent
    COA_AGENT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ COA Compliance Agent imports failed: {e}")
    print("⚠️ COA compliance tracking will not be available")
    COA_AGENT_AVAILABLE = False

# Time Savings Agent
try:
    from agents.time_agent import TimeSavingsAgent, TaskType, Timeframe, create_time_savings_agent
    TIME_SAVINGS_AGENT_AVAILABLE = True
except ImportError as e:
    TIME_SAVINGS_AGENT_AVAILABLE = False
    print(f"⚠️ Time Savings Agent not available: {e}")

# Image Generation Agent
try:
    from agents.image_agent import ImageGenerationAgent, create_image_generation_agent
    IMAGE_GENERATION_AGENT_AVAILABLE = True
except ImportError as e:
    IMAGE_GENERATION_AGENT_AVAILABLE = False
    print(f"⚠️ Image Generation Agent not available: {e}")

# Site Agent import
try:
    from agents.site_agent import SiteAgent, create_site_agent
    SITE_AGENT_AVAILABLE = True
except ImportError as e:
    SITE_AGENT_AVAILABLE = False
    print(f"⚠️ Site Agent not available: {e}")

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
    
    # Start scheduled analytics for Time Savings Agent
    if time_savings_agent:
        try:
            time_savings_agent.start_scheduled_analytics()
            print("✅ Scheduled Time Savings Analytics started")
        except Exception as e:
            print(f"⚠️ Failed to start scheduled analytics: {e}")
    
    yield
    
    # Shutdown
    if notification_agent:
        try:
            notification_agent.stop()
            print("🛑 Notification Agent stopped")
        except Exception as e:
            print(f"⚠️ Error stopping Notification Agent: {e}")
    
    # Stop scheduled analytics
    if time_savings_agent:
        try:
            time_savings_agent.stop_scheduled_analytics()
        except Exception as e:
            print(f"⚠️ Error stopping scheduled analytics: {e}")
    
    print("🛑 PrecepGo ADK Panel shutting down...")

app = FastAPI(title="PrecepGo ADK Panel", lifespan=lifespan)

# Configure CORS to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://precepgo-adk-frontend-g4y4qz5rfa-uc.a.run.app",
        "http://localhost:3000",  # For local development
        "http://localhost:5173",  # For Vite dev server
        "http://localhost:8080",  # For local backend testing
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
            firestore_db=notification_db
        )
        print("✅ Notification Agent initialized")
    except Exception as e:
        print(f"⚠️ Failed to initialize Notification Agent: {e}")
        notification_agent = None
elif NOTIFICATION_AGENT_AVAILABLE:
    print("⚠️ Notification Agent not initialized: Firestore not available")

# Initialize COA Compliance Agent
coa_agent = None
if COA_AGENT_AVAILABLE and FIRESTORE_AVAILABLE:
    try:
        # Get Firestore client for COA agent
        from google.cloud import firestore
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            coa_db = firestore.Client(project=project_id)
        else:
            coa_db = firestore.Client()
        
        # Get mapping file path from environment or use default
        mapping_file_path = os.getenv("COA_MAPPING_FILE_PATH", "/mnt/user-data/uploads/Standard_D_Mapping_to_Clinical_Evaluations__1_.docx")
        
        coa_agent = COAComplianceAgent(
            firestore_db=coa_db,
            mapping_file_path=mapping_file_path
        )
        print("✅ COA Compliance Agent initialized")
    except Exception as e:
        print(f"⚠️ Failed to initialize COA Compliance Agent: {e}")
        coa_agent = None
elif COA_AGENT_AVAILABLE:
    print("⚠️ COA Compliance Agent not initialized: Firestore not available")

# Initialize State Agent
state_agent = None
if STATE_AGENT_AVAILABLE and FIRESTORE_AVAILABLE:
    try:
        from google.cloud import firestore
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            state_db = firestore.Client(project=project_id)
        else:
            state_db = firestore.Client()
        
        state_agent = StateAgent(firestore_db=state_db)
        print("✅ State Agent initialized")
    except Exception as e:
        print(f"⚠️ Failed to initialize State Agent: {e}")
        state_agent = None
elif STATE_AGENT_AVAILABLE:
    print("⚠️ State Agent not initialized: Firestore not available")

# Initialize Time Savings Agent
time_savings_agent = None
if TIME_SAVINGS_AGENT_AVAILABLE and FIRESTORE_AVAILABLE:
    try:
        # Reuse Firestore client from state agent if available
        if state_agent and hasattr(state_agent, 'db'):
            time_savings_db = state_agent.db
        else:
            from google.cloud import firestore
            project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
            if project_id:
                time_savings_db = firestore.Client(project=project_id)
            else:
                time_savings_db = firestore.Client()
        
        time_savings_agent = TimeSavingsAgent(firestore_db=time_savings_db, state_agent=state_agent)
        print("✅ Time Savings Agent initialized")
    except Exception as e:
        print(f"⚠️ Failed to initialize Time Savings Agent: {e}")
        time_savings_agent = None
elif TIME_SAVINGS_AGENT_AVAILABLE:
    print("⚠️ Time Savings Agent not initialized: Firestore not available")

# Initialize Image Generation Agent
image_generation_agent = None
if IMAGE_GENERATION_AGENT_AVAILABLE and FIRESTORE_AVAILABLE:
    try:
        # Reuse Firestore client from state agent if available
        if state_agent and hasattr(state_agent, 'db'):
            image_gen_db = state_agent.db
        else:
            from google.cloud import firestore
            project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
            if project_id:
                image_gen_db = firestore.Client(project=project_id)
            else:
                image_gen_db = firestore.Client()
        
        # Get project ID for Vertex AI initialization
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        
        print(f"\n🎨 Initializing Image Generation Agent (main.py)...")
        print(f"   - Project ID: {project_id}")
        print(f"   - Firestore DB: {'Available' if image_gen_db else 'Not available'}")
        
        # Auto-detect Firebase Storage bucket if not set
        # Default to auth-demo-90be0.appspot.com which is the working bucket
        storage_bucket_name = os.getenv("STORAGE_BUCKET_NAME")
        storage_bucket_url = os.getenv("STORAGE_BUCKET_URL")
        
        if storage_bucket_url:
            # Parse gs://bucket-name/folder format
            if storage_bucket_url.startswith("gs://"):
                parts = storage_bucket_url.replace("gs://", "").split("/", 1)
                storage_bucket_name = parts[0]
                storage_folder = parts[1] if len(parts) > 1 else "agent_assets"
            else:
                storage_bucket_name = storage_bucket_url
                storage_folder = "agent_assets"
            print(f"   - Using bucket URL from env: {storage_bucket_url}")
        elif not storage_bucket_name:
            # Default to working bucket if not set
            storage_bucket_name = "auth-demo-90be0.appspot.com"
            storage_folder = "agent_assets"
            print(f"   - Using default bucket: {storage_bucket_name}")
        else:
            storage_folder = "agent_assets"
            print(f"   - Using bucket name from env: {storage_bucket_name}")
        
        print(f"   - Storage Bucket Name: {storage_bucket_name}")
        print(f"   - Storage Folder: {storage_folder}")
        
        image_generation_agent = ImageGenerationAgent(
            firestore_db=image_gen_db,
            project_id=project_id,
            storage_bucket_name=storage_bucket_name,
            storage_folder=storage_folder
        )
        
        # Verify initialization
        if image_generation_agent:
            has_model = image_generation_agent.imagen_model is not None
            has_bucket = image_generation_agent.bucket is not None
            
            print(f"   - Image Agent created: ✅")
            print(f"   - Imagen Model: {'✅ Available' if has_model else '❌ Not available'}")
            print(f"   - Storage Bucket: {'✅ Available' if has_bucket else '❌ Not available'}")
            
            if has_model and has_bucket:
                print("✅ Image Generation Agent initialized successfully")
            else:
                print("⚠️ Image Generation Agent initialized but missing model or bucket")
        else:
            print("❌ Image Generation Agent failed to create")
    except Exception as e:
        print(f"⚠️ Failed to initialize Image Generation Agent: {e}")
        import traceback
        traceback.print_exc()
        image_generation_agent = None
elif IMAGE_GENERATION_AGENT_AVAILABLE:
    print("⚠️ Image Generation Agent not initialized: Firestore not available")

# Initialize Site Agent
site_agent = None
if SITE_AGENT_AVAILABLE and FIRESTORE_AVAILABLE:
    try:
        from google.cloud import firestore
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            site_db = firestore.Client(project=project_id)
        else:
            site_db = firestore.Client()
        
        site_agent = SiteAgent(firestore_db=site_db)
        print("✅ Site Agent initialized")
    except Exception as e:
        print(f"⚠️ Failed to initialize Site Agent: {e}")
        import traceback
        traceback.print_exc()
        site_agent = None
elif SITE_AGENT_AVAILABLE:
    print("⚠️ Site Agent not initialized: Firestore not available")

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
    """Fetch concept text and metadata using Vertex AI Vector Search"""
    # Use Vector Search if available, otherwise fall back to MCP
    if USE_VECTOR_SEARCH and VECTOR_SEARCH_AVAILABLE:
        try:
            print(f"🔍 Searching using Vector Search for: '{concept}'")
            
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
                
                print(f"✅ Found content using Vector Search: {len(documents)} results from {section}")
                
                return {
                    "content": combined_content,
                    "book_title": "Clinical Anesthesia",
                    "chapter_title": topic or section,
                    "section_title": section,
                    "section_num": section_num,
                    "num_results": len(documents)
                }
            else:
                error_msg = results.get('error', 'No results found')
                print(f"⚠️ Vector Search found no results: {error_msg}")
                raise ValueError(f"Could not find content for: '{concept}'. Error: {error_msg}")
                
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
        raise ValueError("MCP_URL not configured - cannot retrieve content")
    
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
            print(f"🔍 Searching for: '{search_term}'")
            res = _call_mcp("/mcp/search", method="POST", json_body={"query": search_term})
            
            if isinstance(res, dict) and res.get("results"):
                mcp_data = process_mcp_response(res, concept)
                
                # Only accept results from clinical anesthesia book
                if mcp_data.get("content") and ("clinical" in mcp_data.get("book_title", "").lower() or "anesthesia" in mcp_data.get("book_title", "").lower()):
                    print(f"✅ Found content using search term: '{search_term}'")
                    return mcp_data
                else:
                    print(f"⚠️ Results found but not from clinical anesthesia book")
            else:
                print(f"⚠️ No results for: '{search_term}'")
                
        except Exception as e:
            print(f"⚠️ MCP search error for '{search_term}': {e}")
            continue
    
    # If we get here, we couldn't find content
    raise ValueError(f"Could not find content for: '{concept}'. Try simpler search terms like: {keywords[0] if keywords else concept.split()[0]}")

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
    """Select appropriate scenario based on concept - enhanced with clinical scenarios"""
    concept_lower = concept.lower()
    
    # Clinical scenarios based on content
    clinical_scenarios = {
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
    
    # Match concept to clinical scenarios
    for key, scenarios in clinical_scenarios.items():
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
    """ADK Tool: Get medical content for a concept"""
    try:
        knowledge = await retrieve_medical_knowledge(concept)
        if not knowledge.get("raw_content"):
            raise ValueError(f"No content found for: {concept}")
        return knowledge["raw_content"]
    except Exception as e:
        raise ValueError(f"Failed to retrieve content for '{concept}': {str(e)}")

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
                name="medical_question_generator_rag",
                description="Evidence-based medical question generator using Retrieval-Augmented Generation. You are an expert medical educator specializing in CRNA (Certified Registered Nurse Anesthetist) education. You use Retrieval-Augmented Generation (RAG) to ensure all content is factually accurate and evidence-based. RAG Process (CRITICAL - Follow this order): 1. RETRIEVE: Use get_medical_content to fetch verified medical knowledge from authoritative sources 2. VERIFY: Ensure the retrieved content is from reliable medical literature 3. GENERATE: Use only the retrieved facts to create questions, answers, and rationales 4. GROUND: All generated content must be traceable back to the retrieved medical knowledge. Your role is to generate high-quality, clinically relevant multiple choice questions that test: Clinical reasoning and decision-making based on ACTUAL medical guidelines, Patient safety principles from verified sources, Evidence-based practice from medical literature, AANA and ASA guidelines as documented in retrieved content. Process: 1. Use get_medical_content to fetch VERIFIED content for the concept 2. Use select_patient_for_concept to choose appropriate patient demographics 3. Use generate_medical_question to create the final question with patient context. Always ensure: ALL content is grounded in retrieved medical knowledge (NO hallucinations!), Patient demographics match the medical concept (pediatric concepts get pediatric patients), Questions are appropriate for the specified level (junior/senior), Answer choices are explanatory with clinical context, Rationales cite evidence from retrieved medical literature, Focus on practical clinical scenarios backed by real guidelines, Source attribution is included.",
                tools=[
                    get_medical_content,
                    select_patient_for_concept,
                    generate_medical_question
                ],
                model=LiteLlm(model=MODEL_GEMINI_FLASH)
            )
            
            # Create runner - exactly as tutorial
            self.runner = Runner(
                app_name="precepgo-adk-panel",
                agent=self.agent,
                session_service=self.session_service
            )
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
        
        # Return the scenario data (including student info and rationale if available)
        scenario_response = {
            "case": scenario_data.get("case", {}),
            "patient": scenario_data.get("patient", {}),
            "scenario": scenario_data.get("scenario", ""),
            "option_a": scenario_data.get("option_a", {}),
            "option_b": scenario_data.get("option_b", {}),
            "best_answer": scenario_data.get("best_answer", {}),
            "learning_points": scenario_data.get("learning_points", []),
            "references": scenario_data.get("references", "")
        }
        
        # Add student-specific information if available
        if scenario_data.get("student"):
            scenario_response["student"] = scenario_data.get("student")
        if scenario_data.get("case_rationale"):
            scenario_response["case_rationale"] = scenario_data.get("case_rationale")
        if scenario_data.get("student_analysis"):
            scenario_response["student_analysis"] = scenario_data.get("student_analysis")
        
        return {
            "ok": True,
            "scenario": scenario_response,
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
    
    # Set state to ACTIVE immediately for responsive UI feedback
    if state_agent:
        state_agent.set_agent_state("evaluation_agent", StateAgent.STATE_ACTIVE)
    
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
        # Set state back to IDLE on error
        if state_agent:
            state_agent.set_agent_error("evaluation_agent", str(e))
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creating demo evaluation: {str(e)}")

# Alias endpoint for frontend compatibility
@app.post("/agents/evaluation/create-demo")
async def create_demo_evaluation_alias():
    """Alias for /mentor/create-demo-evaluation"""
    return await create_demo_evaluation()

@app.post("/agents/site/generate-report")
async def generate_site_report():
    """
    Generate a comprehensive site report analyzing all evaluations.
    Creates a report listing clinical sites, case types, and preceptor information.
    
    Returns:
        Dictionary with report ID and summary
    """
    if not site_agent:
        raise HTTPException(
            status_code=503,
            detail="Site Agent not available. Please ensure agents/site_agent.py is properly configured."
        )
    
    try:
        result = site_agent.generate_site_report()
        
        if result.get("success"):
            return {
                "ok": True,
                "report_id": result.get("report_id"),
                "summary": result.get("analysis_summary"),
                "message": "Site report generated successfully"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to generate site report")
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating site report: {str(e)}")

@app.post("/agents/coa-compliance/generate-reports")
async def generate_coa_reports(student_ids: Optional[List[str]] = None):
    """
    Generate COA compliance reports for all students or specified students.
    
    Args:
        student_ids: Optional list of student IDs to process (if None, processes all)
        
    Returns:
        List of compliance reports
    """
    if not coa_agent:
        raise HTTPException(
            status_code=503,
            detail="COA Compliance Agent not available. Please ensure agents/coa_agent.py is properly configured."
        )
    
    try:
        # Use provided student IDs or None to process all
        student_id_list = student_ids
        
        # Generate consolidated report
        consolidated_report = coa_agent.generate_reports(student_ids=student_id_list)
    
        # Clean report for JSON serialization (handle Firestore-specific objects)
        from google.cloud.firestore_v1 import SERVER_TIMESTAMP as _SERVER_TIMESTAMP
        
        def clean_value(val):
            """Recursively clean a value for JSON serialization"""
            # Skip SERVER_TIMESTAMP sentinels and other Sentinel objects
            # Check multiple ways to detect Sentinel objects
            is_sentinel = (
                val is _SERVER_TIMESTAMP or
                (hasattr(val, '__class__') and 'Sentinel' in str(type(val))) or
                str(type(val)) == "<class 'google.cloud.firestore_v1._helpers.Sentinel'>"
            )
            if is_sentinel:
                return None  # Convert sentinels to None (which is JSON-serializable)
            # Convert GeoPoint to dict
            elif hasattr(val, 'latitude') and hasattr(val, 'longitude'):
                return {
                    "latitude": val.latitude,
                    "longitude": val.longitude
                }
            # Convert Firestore Timestamp objects
            elif hasattr(val, 'seconds') and hasattr(val, 'nanoseconds'):
                return {
                    "seconds": val.seconds,
                    "nanoseconds": getattr(val, 'nanoseconds', 0)
                }
            # Convert datetime objects to ISO strings
            elif isinstance(val, datetime):
                return val.isoformat()
            # Handle lists
            elif isinstance(val, list):
                cleaned_list = []
                for item in val:
                    cleaned_item = clean_value(item)
                    # Only skip None if it came from a sentinel (handled above)
                    cleaned_list.append(cleaned_item)
                return cleaned_list
            # Handle dictionaries
            elif isinstance(val, dict):
                cleaned_dict = {}
                for k, v in val.items():
                    cleaned_v = clean_value(v)
                    # Only skip None if it came from a sentinel (handled above)
                    cleaned_dict[k] = cleaned_v
                return cleaned_dict
            # Try to serialize primitive types
            else:
                try:
                    import json
                    json.dumps(val)  # Test if serializable
                    return val
                except (TypeError, ValueError):
                    # Convert non-serializable values to string
                    return str(val)
        
        cleaned_report = clean_value(consolidated_report)
        
        return {
            "ok": True,
            "reports": cleaned_report,
            "total_standards": len(coa_agent.coa_mapping) if coa_agent.coa_mapping else 0
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating COA compliance reports: {str(e)}")

@app.post("/agents/automated-mode/start")
async def start_automated_mode():
    """
    Start automated mode - agents will run automatically for 15 minutes.
    Each agent runs on its own 5-minute timer.
    """
    if not state_agent:
        raise HTTPException(
            status_code=503,
            detail="State Agent not available. Please ensure agents/state_agent.py is properly configured."
        )
    
    try:
        if state_agent.is_automated_mode_active():
            return {
                "ok": False,
                "detail": "Automated mode is already running"
            }
        
        success = state_agent.start_automated_mode(duration_minutes=15)
        
        if success:
            return {
                "ok": True,
                "message": "Automated mode started successfully",
                "duration_minutes": 15
            }
        else:
            return {
                "ok": False,
                "detail": "Failed to start automated mode"
            }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error starting automated mode: {str(e)}")

@app.post("/agents/automated-mode/stop")
async def stop_automated_mode():
    """
    Stop automated mode manually.
    """
    if not state_agent:
        raise HTTPException(
            status_code=503,
            detail="State Agent not available. Please ensure agents/state_agent.py is properly configured."
        )
    
    try:
        success = state_agent.stop_automated_mode()
        
        if success:
            return {
                "ok": True,
                "message": "Automated mode stopped successfully"
            }
        else:
            return {
                "ok": False,
                "detail": "Automated mode is not running"
            }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error stopping automated mode: {str(e)}")

@app.get("/agents/automated-mode/status")
async def get_automated_mode_status():
    """
    Get automated mode status.
    Optimized to avoid Firestore timeouts - uses in-memory state first.
    """
    if not state_agent:
        return {
            "ok": False,
            "active": False,
            "detail": "State Agent not available"
        }
    
    try:
        # Check in-memory state first (fast, no Firestore call)
        is_active = state_agent.is_automated_mode_active()
        
        # Try to get Firestore state, but don't fail if it times out
        try:
            all_states = state_agent.get_all_states()
            automated_mode = all_states.get("automated_mode", "OFF")
            start_time = all_states.get("automated_mode_start_time")
            end_time = all_states.get("automated_mode_end_time")
        except Exception as firestore_error:
            # If Firestore fails, use in-memory state
            print(f"⚠️ Firestore query failed in status endpoint: {firestore_error}")
            automated_mode = "ON" if is_active else "OFF"
            start_time = None
            end_time = None
        
        return {
            "ok": True,
            "active": is_active,
            "automated_mode": automated_mode,
            "start_time": start_time,
            "end_time": end_time
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "ok": False,
            "active": False,
            "detail": f"Error getting status: {str(e)}"
        }

@app.get("/agents/{agent_name}/status")
async def get_agent_status(agent_name: str):
    """
    Get the status of a specific agent.
    
    agent_name: One of: evaluation_agent, scenario_agent, notification_agent, coa_agent
    """
    if not state_agent:
        return {
            "ok": False,
            "agent": agent_name,
            "state": "error",
            "detail": "State Agent not available"
        }
    
    try:
        state = state_agent.get_agent_state(agent_name)
        result = state_agent.get_agent_result(agent_name)
        error = state_agent.get_agent_error(agent_name)
        
        return {
            "ok": True,
            "agent": agent_name,
            "state": state or "idle",
            "result": result,
            "error": error
        }
    except Exception as e:
        return {
            "ok": False,
            "agent": agent_name,
            "state": "error",
            "detail": f"Error getting status: {str(e)}"
        }

@app.get("/agents/test")
async def test_agents_endpoint():
    """Test endpoint to verify /agents routes are working"""
    return {
        "ok": True,
        "message": "Agents endpoint is working",
        "available_endpoints": [
            "/agents/{agent_name}/status",
            "/agents/evaluation/create-demo",
            "/agents/automated-mode/start",
            "/agents/automated-mode/stop",
            "/agents/automated-mode/status",
            "/agents/time-savings/task/start",
            "/agents/time-savings/task/complete",
            "/agents/time-savings/analytics",
            "/agents/time-savings/report"
        ]
    }

# ============================================================================
# Time Savings Analytics API Endpoints
# ============================================================================

@app.post("/agents/time-savings/task/start")
async def start_time_tracking(request: Dict[str, Any]):
    """
    Start tracking a task for time savings analysis.
    
    Request body:
    {
        "task_type": "evaluation_completion" | "admin_review" | ...,
        "user_id": "user123",
        "is_ai_assisted": true,
        "agent_name": "evaluations_agent",
        "metadata": {}
    }
    
    Returns:
    {
        "ok": true,
        "task_id": "task_abc123",
        "message": "Task tracking started"
    }
    """
    if not time_savings_agent:
        raise HTTPException(
            status_code=503,
            detail="Time Savings Agent not available"
        )
    
    try:
        task_type_str = request.get("task_type")
        if not task_type_str:
            raise HTTPException(status_code=400, detail="task_type is required")
        
        task_type = TaskType(task_type_str)
        user_id = request.get("user_id", "anonymous")
        is_ai_assisted = request.get("is_ai_assisted", True)
        agent_name = request.get("agent_name")
        metadata = request.get("metadata", {})
        
        task_id = time_savings_agent.log_task_start(
            task_type=task_type,
            user_id=user_id,
            is_ai_assisted=is_ai_assisted,
            agent_name=agent_name,
            metadata=metadata
        )
        
        return {
            "ok": True,
            "task_id": task_id,
            "message": "Task tracking started"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid task_type: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting task tracking: {str(e)}")

@app.post("/agents/time-savings/task/complete")
async def complete_time_tracking(request: Dict[str, Any]):
    """
    Complete tracking a task.
    
    Request body:
    {
        "task_id": "task_abc123",
        "duration_minutes": 5.5,  # Optional, will calculate if not provided
        "metadata": {}
    }
    
    Returns:
    {
        "ok": true,
        "message": "Task tracking completed",
        "time_saved_minutes": 12.5
    }
    """
    if not time_savings_agent:
        raise HTTPException(
            status_code=503,
            detail="Time Savings Agent not available"
        )
    
    try:
        task_id = request.get("task_id")
        if not task_id:
            raise HTTPException(status_code=400, detail="task_id is required")
        
        duration_minutes = request.get("duration_minutes")
        metadata = request.get("metadata", {})
        
        success = time_savings_agent.log_task_complete(
            task_id=task_id,
            duration_minutes=duration_minutes,
            metadata=metadata
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Task not found or already completed")
        
        # Get the updated task to return time saved
        from google.cloud import firestore
        task_ref = time_savings_agent.db.collection(time_savings_agent.collection_name).document(task_id)
        task_doc = task_ref.get()
        
        if task_doc.exists:
            task_data = task_doc.to_dict()
            return {
                "ok": True,
                "message": "Task tracking completed",
                "time_saved_minutes": task_data.get("time_saved_minutes", 0),
                "time_saved_hours": task_data.get("time_saved_hours", 0),
                "duration_minutes": task_data.get("duration_minutes", 0)
            }
        else:
            return {
                "ok": True,
                "message": "Task tracking completed"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error completing task tracking: {str(e)}")

@app.get("/agents/time-savings/analytics")
async def get_time_savings_analytics(
    timeframe: str = "monthly",
    user_id: Optional[str] = None,
    include_insights: bool = False
):
    """
    Get time savings analytics for a given timeframe.
    
    Query parameters:
    - timeframe: "daily" | "weekly" | "monthly" | "semester" | "all_time" (default: monthly)
    - user_id: Optional user ID to filter by
    - include_insights: Whether to include AI-generated insights (default: false)
    
    Returns:
    {
        "timeframe": "monthly",
        "total_hours_saved": 47.5,
        "fte_equivalent": 1.2,
        "cost_savings": 2018.75,
        "total_tasks": 125,
        "task_breakdown": {...},
        "agent_breakdown": {...},
        "top_agent": "evaluations_agent",
        "insights": "..." (if include_insights=true)
    }
    """
    if not time_savings_agent:
        raise HTTPException(
            status_code=503,
            detail="Time Savings Agent not available"
        )
    
    try:
        # Validate timeframe
        try:
            timeframe_enum = Timeframe(timeframe.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe: {timeframe}. Must be one of: daily, weekly, monthly, semester, all_time"
        )
        
        # Update state_agent if available
        if time_savings_agent.state_agent:
            try:
                from agents.state_agent import StateAgent
                time_savings_agent.state_agent.set_agent_state("time_agent", StateAgent.STATE_ACTIVE)
            except Exception as e:
                print(f"⚠️ Failed to update state_agent: {e}")
        
        savings_data = time_savings_agent.calculate_savings(timeframe_enum, user_id)
        
        # Always write analytics data to time_saved document when API is called
        try:
            # Calculate all timeframes for complete analytics
            all_time_savings = time_savings_agent.calculate_savings(Timeframe.ALL_TIME, update_time_saved=False)
            daily_savings = time_savings_agent.calculate_savings(Timeframe.DAILY, update_time_saved=False)
            weekly_savings = time_savings_agent.calculate_savings(Timeframe.WEEKLY, update_time_saved=False)
            monthly_savings = time_savings_agent.calculate_savings(Timeframe.MONTHLY, update_time_saved=False)
            semester_savings = time_savings_agent.calculate_savings(Timeframe.SEMESTER, update_time_saved=False)
            
            # Generate insights for all-time data
            insights = None
            if time_savings_agent.gemini_agent:
                try:
                    insights = time_savings_agent.generate_insights(all_time_savings)
                except Exception as e:
                    print(f"⚠️ Failed to generate insights: {e}")
            
            # Write all analytics data to time_saved document
            time_savings_agent._write_analytics_to_time_saved(
                all_time_savings=all_time_savings,
                daily_savings=daily_savings,
                weekly_savings=weekly_savings,
                monthly_savings=monthly_savings,
                semester_savings=semester_savings,
                insights=insights
            )
        except Exception as e:
            print(f"⚠️ Failed to write analytics to time_saved: {e}")
        
        # Update state_agent to completed
        if time_savings_agent.state_agent:
            try:
                from agents.state_agent import StateAgent
                time_savings_agent.state_agent.set_agent_result(
                    "time_agent",
                    {
                        "timeframe": timeframe,
                        "total_hours_saved": savings_data.get('total_hours_saved', 0),
                        "total_tasks": savings_data.get('total_tasks', 0)
                    },
                    StateAgent.STATE_IDLE
                )
            except Exception as e:
                print(f"⚠️ Failed to update state_agent result: {e}")
        
        # Generate insights for the requested timeframe if requested
        if include_insights and time_savings_agent.gemini_agent:
            try:
                insights = time_savings_agent.generate_insights(savings_data)
                savings_data["insights"] = insights
            except Exception as e:
                savings_data["insights"] = f"Failed to generate insights: {str(e)}"
        
        return {
            "ok": True,
            **savings_data
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating analytics: {str(e)}")

@app.get("/agents/time-savings/report")
async def get_time_savings_report(
    format_type: str = "summary",
    timeframe: str = "monthly",
    user_id: Optional[str] = None,
    include_insights: bool = True
):
    """
    Generate a comprehensive time savings report.
    
    Query parameters:
    - format_type: "summary" | "detailed" (default: summary)
    - timeframe: "daily" | "weekly" | "monthly" | "semester" | "all_time" (default: monthly)
    - user_id: Optional user ID to filter by
    - include_insights: Whether to include AI-generated insights (default: true)
    
    Returns:
    Complete report dictionary with metrics, breakdowns, and insights
    """
    if not time_savings_agent:
        raise HTTPException(
            status_code=503,
            detail="Time Savings Agent not available"
        )
    
    try:
        # Validate format_type
        if format_type not in ["summary", "detailed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid format_type: {format_type}. Must be 'summary' or 'detailed'"
            )
        
        # Validate timeframe
        try:
            timeframe_enum = Timeframe(timeframe.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe: {timeframe}. Must be one of: daily, weekly, monthly, semester, all_time"
            )
        
        report = time_savings_agent.generate_report(
            format_type=format_type,
            timeframe=timeframe_enum,
            user_id=user_id,
            include_insights=include_insights
        )
        
        return {
            "ok": True,
            **report
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")

@app.post("/agents/image-generation/process-scenarios")
async def process_scenarios_with_images(
    limit: Optional[int] = None,
    skip_existing: bool = True
):
    """
    Process all scenarios in agent_scenarios collection and generate images for them.
    
    Query parameters:
    - limit: Optional limit on number of scenarios to process
    - skip_existing: Whether to skip scenarios that already have images (default: true)
    
    Returns:
    {
        "success": true,
        "processed": 5,
        "failed": 0,
        "skipped": 2,
        "results": [...]
    }
    """
    if not image_generation_agent:
        raise HTTPException(
            status_code=503,
            detail="Image Generation Agent not available"
        )
    
    # Check if image agent is fully ready
    if not image_generation_agent.imagen_model:
        raise HTTPException(
            status_code=503,
            detail="Imagen model not available. Please check Vertex AI configuration."
        )
    
    if not image_generation_agent.bucket:
        raise HTTPException(
            status_code=503,
            detail=f"Cloud Storage bucket not available. Bucket name: {image_generation_agent.storage_bucket_name or 'Not set'}. Please check STORAGE_BUCKET_NAME or STORAGE_BUCKET_URL environment variable."
        )
    
    try:
        results = image_generation_agent.process_all_scenarios(
            limit=limit,
            skip_existing=skip_existing
        )
        
        # Include debug info in response
        response_data = {
            "ok": True,
            **results
        }
        
        # Add error details if available
        if results.get("error_details"):
            response_data["error_details"] = results.get("error_details")
        
        return response_data
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ Exception in API endpoint: {error_details}")
        raise HTTPException(status_code=500, detail=f"Error processing scenarios: {str(e)}")

@app.post("/agents/image-generation/process-scenario/{scenario_id}")
async def process_single_scenario(scenario_id: str):
    """
    Process a single scenario document and generate an image for it.
    
    Path parameters:
    - scenario_id: ID of the scenario document to process
    
    Returns:
    {
        "success": true,
        "scenario_id": "...",
        "image_url": "https://..."
    }
    """
    if not image_generation_agent:
        raise HTTPException(
            status_code=503,
            detail="Image Generation Agent not available"
        )
    
    try:
        result = image_generation_agent.process_scenario_document(scenario_id)
        
        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to process scenario")
            )
        
        return {
            "ok": True,
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing scenario: {str(e)}")

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

@app.post("/agents/notification/safety-check")
async def run_safety_check_alias():
    """Alias for /agents/notification/run-safety-check"""
    return await run_safety_check()

@app.post("/agents/notification/run-safety-check")
async def run_safety_check():
    """
    Manually trigger the notification agent to check for negative evaluations.
    
    Returns:
        Result of the safety check
    """
    if not notification_agent:
        raise HTTPException(
            status_code=503,
            detail="Notification Agent not available. Please ensure agents/notification_agent.py is properly configured."
        )
    
    try:
        print("🔍 Manual safety check triggered")
        # Run the notification check synchronously
        notification_agent.process_notifications()
        
        # Get the state to see results
        result_info = {
            "ok": True,
            "message": "Safety check completed successfully",
            "timestamp": datetime.now().isoformat()
        }
        
        # Try to get state info if available
        if notification_agent.state_agent:
            try:
                state = notification_agent.state_agent.get_agent_state("notification_agent")
                result_info["state"] = state
                
                all_states = notification_agent.state_agent.get_all_states()
                last_result = all_states.get('notification_agent_last_result', {})
                if last_result:
                    result_info["last_result"] = last_result
            except Exception as e:
                print(f"⚠️ Could not get state info: {e}")
        
        return result_info
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error running safety check: {str(e)}")

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
            <h1>🏥 PrecepGo ADK Panel</h1>
            
            <div style="background-color: #ffebee; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #dc3545;">
                <strong>🚨 Run Safety Check:</strong> 
                <br><small style="color: #555;">Manually trigger the notification agent to check for dangerous evaluations (-1 ratings) in the agent_evaluations collection. If any dangerous ratings are found, notification records will be saved to the agent_notifications collection.</small>
                <br>
                <button id="safetyCheckBtn" onclick="runSafetyCheck()" style="margin-top: 10px; padding: 12px 24px; background: #dc3545; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🚨 Run Safety Check
                </button>
                <div id="safetyCheckResult" style="margin-top: 15px; display: none;"></div>
            </div>
            
            <div style="background-color: #e8f5e9; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #4caf50;">
                <strong>📊 Create Demo Evaluation:</strong> 
                <br><small style="color: #555;">Generate a fake demo evaluation document and save it to Firestore subcollection 'agent_evaluations'. Creates realistic evaluation data with preceptee/preceptor info, scores, and metadata.</small>
                <br>
                <button id="createEvalBtn" onclick="createDemoEvaluation()" style="margin-top: 10px; padding: 12px 24px; background: #4caf50; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    📊 Create Demo Evaluation
                </button>
                <div id="evaluationResult" style="margin-top: 15px; display: none;"></div>
            </div>
            
            <div style="background-color: #e1f5fe; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #0288d1;">
                <strong>📋 Generate COA Compliance Reports:</strong> 
                <br><small style="color: #555;">Generate COA Standard D compliance reports for all students. Processes all students from students.json, queries their evaluations from Firestore, and generates aggregated scores for each COA standard. Saves consolidated report to Firestore.</small>
                <br>
                <button id="coaReportBtn" onclick="generateCOAReports()" style="margin-top: 10px; padding: 12px 24px; background: #0288d1; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    📋 Generate COA Compliance Reports
                </button>
                <div id="coaReportResult" style="margin-top: 15px; display: none;"></div>
            </div>
            
            <div style="background-color: #f3e5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #9c27b0;">
                <strong>🏥 Generate Site Report:</strong> 
                <br><small style="color: #555;">Analyze all evaluations from agent_evaluations collection to generate a comprehensive site report. Creates a list of all clinical sites with case types, and a list of preceptors with student counts and case types they've precepted. Uses AI to generate insights and saves report to agent_sites collection.</small>
                <br>
                <button id="siteReportBtn" onclick="generateSiteReport()" style="margin-top: 10px; padding: 12px 24px; background: #9c27b0; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🏥 Generate Site Report
                </button>
                <div id="siteReportResult" style="margin-top: 15px; display: none;"></div>
            </div>
            
            <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #ffc107;">
                <strong>🎯 Make Scenario:</strong> 
                <br><small style="color: #555;">Generate a clinical scenario with 2 decision options. The system will pick a random case, match it with an appropriate patient, search Vector DB for medical content, and create a challenging scenario for CRNA students.</small>
                <br>
                <button id="makeScenarioBtn" onclick="makeScenario()" style="margin-top: 10px; padding: 12px 24px; background: #ffc107; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🎯 Make Scenario
                </button>
                <div id="scenarioResult" style="margin-top: 15px; display: none;"></div>
            </div>
            
            <div style="background-color: #f3e5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #9c27b0;">
                <strong>🤖 Automated Mode:</strong> 
                <br><small style="color: #555;">Start automated mode to run agents automatically for 15 minutes. Each agent runs on its own 5-minute timer. Manual agent buttons will be disabled while automated mode is active.</small>
                <br>
                <div id="automatedModeStatus" style="margin-top: 10px; padding: 10px; background: white; border-radius: 4px; display: none;">
                    <span id="automatedModeStatusText">Checking status...</span>
                </div>
                <button id="startAutomatedModeBtn" onclick="startAutomatedMode()" style="margin-top: 10px; padding: 12px 24px; background: #9c27b0; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🤖 Start Automated Mode (15 min)
                </button>
                <button id="stopAutomatedModeBtn" onclick="stopAutomatedMode()" style="margin-top: 10px; padding: 12px 24px; background: #e91e63; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold; margin-left: 10px; display: none;">
                    🛑 Stop Automated Mode
                </button>
                </div>
                
            <div style="background-color: #fff8e1; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #ff9800;">
                <strong>⏱️ Time Savings Analytics:</strong> 
                <br><small style="color: #555;">View time savings estimates from AI agents. Estimates are calculated using Gemini Flash and saved to agent_time/time_saved in Firestore.</small>
                <br>
                <div style="margin-top: 10px;">
                    <label for="timeframeSelect" style="display: inline-block; margin-right: 10px;">Timeframe:</label>
                    <select id="timeframeSelect" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-right: 10px;">
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                        <option value="monthly" selected>Monthly</option>
                        <option value="semester">Semester</option>
                        <option value="all_time">All Time</option>
                    </select>
                    <button onclick="getTimeSavingsAnalytics()" style="padding: 10px 20px; background: #ff9800; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: bold;">
                        📊 View Analytics
                    </button>
                </div>
                <div id="timeSavingsResult" style="margin-top: 15px; display: none;"></div>
            </div>
            
            <div style="background-color: #e8eaf6; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #3f51b5;">
                <strong>🎨 Generate Scenario Images:</strong> 
                <br><small style="color: #555;">Process all scenarios in agent_scenarios collection and generate images using Imagen. Images are saved to Cloud Storage and scenario documents are updated with image URLs.</small>
                <br>
                <div style="margin-top: 10px;">
                    <label for="imageGenLimit" style="display: inline-block; margin-right: 10px;">Limit (optional):</label>
                    <input type="number" id="imageGenLimit" placeholder="All scenarios" min="1" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-right: 10px; width: 120px;">
                    <label style="margin-right: 10px;">
                        <input type="checkbox" id="imageGenSkipExisting" checked style="margin-right: 5px;">
                        Skip scenarios with existing images
                    </label>
                    <button id="imageGenBtn" onclick="generateScenarioImages()" style="margin-top: 10px; padding: 12px 24px; background: #3f51b5; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold;">
                        🎨 Generate Images for Scenarios
                    </button>
                </div>
                <div id="imageGenResult" style="margin-top: 15px; display: none;"></div>
            </div>
        </div>
        
        <script>
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
                                
                                ${scenario.student ? `
                                    <div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 2px solid #4caf50; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                                        <div style="display: flex; align-items: center; margin-bottom: 15px;">
                                            <div style="font-size: 2em; margin-right: 10px;">👨‍🎓</div>
                                            <div>
                                                <h3 style="margin: 0; color: #1b5e20; font-size: 1.3em;">Scenario Generated For: ${scenario.student.name || 'Unknown'}</h3>
                                                <p style="margin: 5px 0 0 0; color: #2e7d32; font-weight: 500;">${scenario.student.class_standing || 'N/A'} SRNA • ${scenario.student.hospital || 'N/A'}</p>
                                            </div>
                                        </div>
                                        
                                        ${scenario.case_rationale ? `
                                            <div style="background: #ffffff; padding: 15px; border-radius: 6px; margin-top: 15px; border-left: 4px solid #4caf50; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                                                <h4 style="margin: 0 0 10px 0; color: #2e7d32; font-size: 1.1em; display: flex; align-items: center;">
                                                    <span style="margin-right: 8px;">💡</span>
                                                    Why This Scenario Helps This Student:
                                                </h4>
                                                <p style="margin: 0; line-height: 1.8; color: #333; font-size: 1.05em;">${scenario.case_rationale}</p>
                                            </div>
                                        ` : ''}
                                        
                                        ${scenario.student_analysis ? `
                                            <div style="background: #ffffff; padding: 15px; border-radius: 6px; margin-top: 15px; border-left: 4px solid #81c784;">
                                                <h4 style="margin: 0 0 12px 0; color: #2e7d32; font-size: 1em; display: flex; align-items: center;">
                                                    <span style="margin-right: 8px;">📊</span>
                                                    Based on Student's Evaluation History:
                                                </h4>
                                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 0.95em;">
                                                    ${scenario.student_analysis.recent_cases && scenario.student_analysis.recent_cases.length > 0 ? `
                                                        <div style="padding: 8px; background: #f1f8f4; border-radius: 4px;">
                                                            <strong style="color: #2e7d32;">Recent Cases:</strong><br>
                                                            <span style="color: #555;">${scenario.student_analysis.recent_cases.slice(0, 3).join(', ')}</span>
                                                        </div>
                                                    ` : ''}
                                                    ${scenario.student_analysis.struggling_areas && scenario.student_analysis.struggling_areas.length > 0 ? `
                                                        <div style="padding: 8px; background: #fff3cd; border-radius: 4px;">
                                                            <strong style="color: #856404;">Areas for Improvement:</strong><br>
                                                            <span style="color: #555;">${scenario.student_analysis.struggling_areas.slice(0, 3).join(', ')}</span>
                                                        </div>
                                                    ` : ''}
                                                    ${scenario.student_analysis.weak_ac_count > 0 || scenario.student_analysis.weak_pc_count > 0 ? `
                                                        <div style="padding: 8px; background: #f1f8f4; border-radius: 4px; grid-column: 1 / -1;">
                                                            <strong style="color: #2e7d32;">Performance Indicators:</strong>
                                                            <span style="color: #555; margin-left: 8px;">
                                                                ${scenario.student_analysis.weak_ac_count > 0 ? `<span style="color: #d32f2f;">${scenario.student_analysis.weak_ac_count} weak AC scores</span>` : ''}
                                                                ${scenario.student_analysis.weak_ac_count > 0 && scenario.student_analysis.weak_pc_count > 0 ? ' • ' : ''}
                                                                ${scenario.student_analysis.weak_pc_count > 0 ? `<span style="color: #d32f2f;">${scenario.student_analysis.weak_pc_count} weak PC scores</span>` : ''}
                                                            </span>
                                                        </div>
                                                    ` : ''}
                                                </div>
                                            </div>
                                        ` : ''}
                                    </div>
                                ` : ''}
                                
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
            
            // Run Safety Check function
            async function runSafetyCheck() {
                const resultDiv = document.getElementById('safetyCheckResult');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '<p style="color: #dc3545; text-align: center;">⏳ Running safety check... This may take a moment.</p>';
                
                try {
                    const response = await fetch('/agents/notification/run-safety-check', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (data.ok) {
                        let html = `
                            <div style="background: white; padding: 20px; border-radius: 8px; border: 2px solid #dc3545; margin-top: 15px;">
                                <h3 style="color: #2c3e50; margin-top: 0;">✅ Safety Check Completed</h3>
                                
                                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <h4 style="margin-top: 0; color: #495057;">📊 Check Results</h4>
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                                        <div><strong>Status:</strong> <span style="color: #27ae60; font-weight: bold;">Completed</span></div>
                                        <div><strong>Timestamp:</strong> ${data.timestamp ? new Date(data.timestamp).toLocaleString() : 'N/A'}</div>
                                        ${data.last_result ? `
                                            <div style="grid-column: 1 / -1;">
                                                <strong>Notifications Found:</strong> ${data.last_result.notifications_sent || 0}
                                            </div>
                                        ` : ''}
                                    </div>
                                </div>
                        `;
                        
                        if (data.last_result && data.last_result.notifications_sent > 0) {
                            html += `
                                <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #ffc107;">
                                    <h4 style="margin-top: 0; color: #856404;">⚠️ Dangerous Evaluations Found</h4>
                                    <p style="margin: 0; color: #856404;">
                                        <strong>${data.last_result.notifications_sent}</strong> dangerous evaluation(s) were found and notification records have been saved to the <code>agent_notifications</code> collection in Firestore.
                                    </p>
                                    <p style="margin: 10px 0 0 0; color: #856404; font-size: 0.9em;">
                                        Please review these notifications and take appropriate action.
                                    </p>
                                </div>
                            `;
                        } else {
                            html += `
                                <div style="background: #d1f2eb; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #27ae60;">
                                    <h4 style="margin-top: 0; color: #155724;">✅ No Dangerous Evaluations</h4>
                                    <p style="margin: 0; color: #155724;">
                                        No dangerous evaluations (-1 ratings) were found in the <code>agent_evaluations</code> collection.
                                    </p>
                                </div>
                            `;
                        }
                        
                        if (data.state) {
                            html += `
                                <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <h4 style="margin-top: 0; color: #1976d2;">🔍 Agent State</h4>
                                    <div style="font-size: 0.9em; color: #555;">
                                        <strong>Status:</strong> ${data.state.status || 'N/A'}<br>
                                        ${data.state.last_updated ? `<strong>Last Updated:</strong> ${new Date(data.state.last_updated).toLocaleString()}<br>` : ''}
                                    </div>
                                </div>
                            `;
                        }
                        
                        html += `
                                <div style="background: #ffebee; padding: 10px; border-radius: 5px; margin-top: 15px; border-left: 4px solid #dc3545;">
                                    <small style="color: #c62828;">
                                        <strong>Note:</strong> The notification agent automatically checks every 15 minutes. You can also manually trigger a check using this button at any time.
                                    </small>
                                </div>
                            </div>
                        `;
                        
                        resultDiv.innerHTML = html;
                    } else {
                        resultDiv.innerHTML = `<div style="color: #dc3545; padding: 15px; background: #ffebee; border-radius: 5px;">❌ Safety check failed: ${data.detail || 'Unknown error'}</div>`;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `<div style="color: #dc3545; padding: 15px; background: #ffebee; border-radius: 5px;">❌ Error: ${error.message}</div>`;
                }
            }
            
            // Automated Mode Functions
            let automatedModeCheckInterval = null;
            
            async function checkAutomatedModeStatus() {
                try {
                    const response = await fetch('/agents/automated-mode/status');
                    const data = await response.json();
                    
                    const statusDiv = document.getElementById('automatedModeStatus');
                    const statusText = document.getElementById('automatedModeStatusText');
                    const startBtn = document.getElementById('startAutomatedModeBtn');
                    const stopBtn = document.getElementById('stopAutomatedModeBtn');
                    
                    if (data.ok && data.active) {
                        statusDiv.style.display = 'block';
                        statusDiv.style.background = '#fff3cd';
                        statusDiv.style.borderLeft = '4px solid #ffc107';
                        statusText.innerHTML = `<strong>🟢 Automated Mode Active</strong><br>Agents are running automatically. Manual buttons are disabled.`;
                        startBtn.style.display = 'none';
                        stopBtn.style.display = 'inline-block';
                        
                        // Disable all agent buttons
                        disableAgentButtons(true);
                    } else {
                        statusDiv.style.display = 'block';
                        statusDiv.style.background = '#e8f5e9';
                        statusDiv.style.borderLeft = '4px solid #4caf50';
                        statusText.innerHTML = `<strong>⚪ Automated Mode Inactive</strong><br>Manual buttons are enabled.`;
                        startBtn.style.display = 'inline-block';
                        stopBtn.style.display = 'none';
                        
                        // Enable all agent buttons
                        disableAgentButtons(false);
                    }
                } catch (error) {
                    console.error('Error checking automated mode status:', error);
                }
            }
            
            function disableAgentButtons(disable) {
                const buttons = [
                    document.getElementById('createEvalBtn'),
                    document.getElementById('makeScenarioBtn'),
                    document.getElementById('safetyCheckBtn'),
                    document.getElementById('coaReportBtn'),
                    document.getElementById('siteReportBtn'),
                    document.getElementById('imageGenBtn')
                ];
                
                buttons.forEach(btn => {
                    if (btn) {
                        if (disable) {
                            btn.disabled = true;
                            btn.style.opacity = '0.5';
                            btn.style.cursor = 'not-allowed';
                        } else {
                            btn.disabled = false;
                            btn.style.opacity = '1';
                            btn.style.cursor = 'pointer';
                        }
                    }
                });
            }
            
            async function startAutomatedMode() {
                try {
                    const response = await fetch('/agents/automated-mode/start', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    
                    const data = await response.json();
                    
                    if (data.ok) {
                        alert(`✅ Automated mode started!\n\nAgents will run automatically for 15 minutes.\nEach agent runs on its own 5-minute timer.`);
                        checkAutomatedModeStatus();
                    } else {
                        alert(`❌ Failed to start automated mode: ${data.detail || 'Unknown error'}`);
                    }
                } catch (error) {
                    alert(`❌ Error: ${error.message}`);
                }
            }
            
            async function stopAutomatedMode() {
                if (!confirm('Are you sure you want to stop automated mode?')) {
                    return;
                }
                
                try {
                    const response = await fetch('/agents/automated-mode/stop', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    
                    const data = await response.json();
                    
                    if (data.ok) {
                        alert('✅ Automated mode stopped successfully');
                        checkAutomatedModeStatus();
                    } else {
                        alert(`❌ Failed to stop automated mode: ${data.detail || 'Unknown error'}`);
                    }
                } catch (error) {
                    alert(`❌ Error: ${error.message}`);
                }
            }
            
            // Check automated mode status on page load and every 5 seconds
            checkAutomatedModeStatus();
            automatedModeCheckInterval = setInterval(checkAutomatedModeStatus, 5000);
            
            // Generate Site Report function
            async function generateSiteReport() {
                const resultDiv = document.getElementById('siteReportResult');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '<p style="color: #9c27b0; text-align: center;">⏳ Generating site report... This may take a moment.</p>';
                
                try {
                    const response = await fetch('/agents/site/generate-report', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (data.ok && data.report_id) {
                        const summary = data.summary || {};
                        
                        let html = `
                            <div style="background: white; padding: 20px; border-radius: 8px; border: 2px solid #9c27b0; margin-top: 15px;">
                                <h3 style="color: #2c3e50; margin-top: 0;">✅ Site Report Generated Successfully</h3>
                                
                                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <h4 style="margin-top: 0; color: #495057;">📊 Report Summary</h4>
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                                        <div><strong>Total Sites:</strong> ${summary.total_sites || 0}</div>
                                        <div><strong>Total Preceptors:</strong> ${summary.total_preceptors || 0}</div>
                                        <div style="grid-column: 1 / -1;"><strong>Total Evaluations Analyzed:</strong> ${summary.total_evaluations || 0}</div>
                                        <div style="grid-column: 1 / -1;"><strong>Report ID:</strong> <code>${data.report_id}</code></div>
                                    </div>
                                </div>
                                
                                <div style="background: #e8f5e9; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #4caf50;">
                                    <h4 style="margin-top: 0; color: #2e7d32;">✅ Report Saved</h4>
                                    <p style="margin: 0; color: #155724;">
                                        The site report has been saved to Firestore in the <code>agent_sites</code> collection.
                                        The report includes detailed analysis of clinical sites, case types, and preceptor information.
                                    </p>
                                    <p style="margin: 10px 0 0 0; color: #155724; font-size: 0.9em;">
                                        You can view the full report in Firestore at: <code>agent_sites/${data.report_id}</code>
                                    </p>
                                </div>
                                
                                ${data.message ? `
                                    <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                        <strong style="color: #1976d2;">ℹ️ Info:</strong>
                                        <p style="margin: 5px 0 0 0; color: #555;">${data.message}</p>
                                    </div>
                                ` : ''}
                            </div>
                        `;
                        
                        resultDiv.innerHTML = html;
                    } else {
                        resultDiv.innerHTML = `<div style="color: #e74c3c; padding: 15px; background: #ffebee; border-radius: 5px;">❌ Failed to generate site report: ${data.detail || data.error || 'Unknown error'}</div>`;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `<div style="color: #e74c3c; padding: 15px; background: #ffebee; border-radius: 5px;">❌ Error: ${error.message}</div>`;
                }
            }
            
            // Generate COA Compliance Reports function
            async function generateCOAReports() {
                const resultDiv = document.getElementById('coaReportResult');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '<p style="color: #0288d1; text-align: center;">⏳ Generating COA compliance reports... This may take a moment.</p>';
                
                try {
                    const response = await fetch('/agents/coa-compliance/generate-reports', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (data.ok && data.reports) {
                        const report = data.reports;
                        
                        let html = `
                            <div style="background: white; padding: 20px; border-radius: 8px; border: 2px solid #0288d1; margin-top: 15px;">
                                <h3 style="color: #2c3e50; margin-top: 0;">✅ COA Compliance Reports Generated</h3>
                                
                                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <h4 style="margin-top: 0; color: #495057;">📊 Summary</h4>
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                                        <div><strong>Students Processed:</strong> ${report.students_processed || 0}</div>
                                        <div><strong>Total Standards:</strong> ${report.total_standards || 0}</div>
                                        <div><strong>Generated At:</strong> ${report.generated_at ? new Date(report.generated_at).toLocaleString() : 'N/A'}</div>
                                </div>
                                </div>
                                
                                <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <h4 style="margin-top: 0; color: #1976d2;">📋 COA Standard Scores</h4>
                                    <div style="max-height: 400px; overflow-y: auto;">
                                        <table style="width: 100%; border-collapse: collapse;">
                                            <thead>
                                                <tr style="background: #bbdefb;">
                                                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #2196f3;">Standard ID</th>
                                                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #2196f3;">Score</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                        `;
                        
                        // Sort by score descending
                        const sortedScores = (report.standard_scores || []).sort((a, b) => b.score - a.score);
                        
                        sortedScores.forEach((scoreObj, index) => {
                            html += `
                                <tr style="${index % 2 === 0 ? 'background: #f5f5f5;' : ''}">
                                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><code>${scoreObj.id}</code></td>
                                    <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold; color: ${scoreObj.score > 0 ? '#27ae60' : '#999'};">${scoreObj.score}</td>
                                </tr>
                            `;
                        });
                        
                        html += `
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                                
                                ${report.student_reports && report.student_reports.length > 0 ? `
                                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                        <h4 style="margin-top: 0; color: #856404;">👥 Student Reports</h4>
                                        <div style="max-height: 300px; overflow-y: auto;">
                                            ${report.student_reports.map((studentReport) => `
                                                <div style="background: white; padding: 10px; margin-bottom: 10px; border-radius: 5px; border-left: 3px solid #ffc107;">
                                                    <strong>${studentReport.student_name}</strong> (${studentReport.student_id}) - 
                                                    <span>Evaluations: ${studentReport.evaluations_processed}, Total Score: ${studentReport.total_score}</span>
                                                </div>
                                            `).join('')}
                                        </div>
                                    </div>
                                ` : ''}
                                
                                <div style="background: #d1f2eb; padding: 10px; border-radius: 5px; margin-top: 15px; border-left: 4px solid #27ae60;">
                                    <small style="color: #155724;">✅ Report saved to Firestore: <code>agent_coa_reports/${report.firestore_doc_id || 'N/A'}</code></small>
                                </div>
                            </div>
                        `;
                        
                        resultDiv.innerHTML = html;
                    } else {
                        resultDiv.innerHTML = `<div style="color: red; padding: 15px; background: #ffebee; border-radius: 5px;">Error: ${data.detail || 'Unknown error'}</div>`;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `<div style="color: red; padding: 15px; background: #ffebee; border-radius: 5px;">Error: ${error.message}</div>`;
                }
            }
            
            // Get Time Savings Analytics function
            async function getTimeSavingsAnalytics() {
                const resultDiv = document.getElementById('timeSavingsResult');
                const timeframe = document.getElementById('timeframeSelect').value;
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '<p style="color: #ff9800; text-align: center;">⏳ Loading time savings analytics...</p>';
                
                try {
                    const response = await fetch(`/agents/time-savings/analytics?timeframe=${timeframe}&include_insights=true`);
                    const data = await response.json();
                    
                    if (data.ok) {
                        let html = `
                            <div style="background: white; padding: 20px; border-radius: 8px; border: 2px solid #ff9800; margin-top: 15px;">
                                <h3 style="color: #2c3e50; margin-top: 0;">⏱️ Time Savings Analytics (${timeframe.charAt(0).toUpperCase() + timeframe.slice(1)})</h3>
                                
                                <!-- Key Metrics -->
                                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px;">
                                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #ffc107;">
                                        <div style="font-size: 0.9em; color: #856404; margin-bottom: 5px;">Total Hours Saved</div>
                                        <div style="font-size: 1.8em; font-weight: bold; color: #856404;">${data.total_hours_saved || 0}</div>
                                            </div>
                                    <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; border-left: 4px solid #2196f3;">
                                        <div style="font-size: 0.9em; color: #1976d2; margin-bottom: 5px;">FTE Equivalent</div>
                                        <div style="font-size: 1.8em; font-weight: bold; color: #1976d2;">${data.fte_equivalent || 0}</div>
                                                </div>
                                    <div style="background: #e8f5e9; padding: 15px; border-radius: 5px; border-left: 4px solid #4caf50;">
                                        <div style="font-size: 0.9em; color: #2e7d32; margin-bottom: 5px;">Cost Savings</div>
                                        <div style="font-size: 1.8em; font-weight: bold; color: #2e7d32;">$${data.cost_savings ? data.cost_savings.toLocaleString() : 0}</div>
                                            </div>
                                    <div style="background: #f3e5f5; padding: 15px; border-radius: 5px; border-left: 4px solid #9c27b0;">
                                        <div style="font-size: 0.9em; color: #7b1fa2; margin-bottom: 5px;">Total Tasks</div>
                                        <div style="font-size: 1.8em; font-weight: bold; color: #7b1fa2;">${data.total_tasks || 0}</div>
                                        </div>
                            </div>
                        `;
                        
                        // Task Breakdown
                        if (data.task_breakdown && Object.keys(data.task_breakdown).length > 0) {
                            html += `
                                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <h4 style="margin-top: 0; color: #495057;">📊 Tasks by Type</h4>
                                    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px;">
                            `;
                            for (const [taskType, count] of Object.entries(data.task_breakdown)) {
                                html += `
                                    <div style="background: white; padding: 10px; border-radius: 4px; border-left: 3px solid #ff9800;">
                                        <strong>${taskType.replace(/_/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase())}:</strong><br>
                                        <span style="font-size: 1.2em; font-weight: bold; color: #ff9800;">${count}</span>
                                    </div>
                                `;
                            }
                            html += `</div></div>`;
                        }
                        
                        // Agent Breakdown
                        if (data.agent_breakdown && Object.keys(data.agent_breakdown).length > 0) {
                            html += `
                                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <h4 style="margin-top: 0; color: #495057;">🤖 Time Saved by Agent</h4>
                                    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px;">
                            `;
                            for (const [agentName, hours] of Object.entries(data.agent_breakdown)) {
                                html += `
                                    <div style="background: white; padding: 10px; border-radius: 4px; border-left: 3px solid #2196f3;">
                                        <strong>${agentName.replace(/_/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase())}:</strong><br>
                                        <span style="font-size: 1.2em; font-weight: bold; color: #2196f3;">${hours} hrs</span>
                            </div>
                        `;
                            }
                            html += `</div></div>`;
                        }
                        
                        // Top Agent
                        if (data.top_agent) {
                            html += `
                                <div style="background: #e8f5e9; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #4caf50;">
                                    <h4 style="margin-top: 0; color: #2e7d32;">🏆 Top Performing Agent</h4>
                                    <p style="margin: 0; font-size: 1.1em; font-weight: bold; color: #2e7d32;">${data.top_agent.replace(/_/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase())}</p>
                                </div>
                            `;
                        }
                        
                        // AI Insights
                        if (data.insights) {
                            html += `
                                <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #ffc107;">
                                    <h4 style="margin-top: 0; color: #856404;">💡 AI-Powered Insights</h4>
                                    <div style="white-space: pre-wrap; line-height: 1.6; color: #856404;">${data.insights}</div>
                                </div>
                            `;
                        }
                        
                        html += `
                                <div style="background: #d1f2eb; padding: 10px; border-radius: 5px; margin-top: 15px; border-left: 4px solid #27ae60;">
                                    <small style="color: #155724;">✅ Data from <code>agent_time/time_saved</code> in Firestore</small>
                                </div>
                            </div>
                        `;
                        
                        resultDiv.innerHTML = html;
                    } else {
                        resultDiv.innerHTML = `<div style="color: #dc3545; padding: 15px; background: #ffebee; border-radius: 5px;">❌ Error: ${data.detail || 'Unknown error'}</div>`;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `<div style="color: #dc3545; padding: 15px; background: #ffebee; border-radius: 5px;">❌ Error: ${error.message}</div>`;
                }
            }
            
            // Generate Scenario Images function
            async function generateScenarioImages() {
                const resultDiv = document.getElementById('imageGenResult');
                const limitInput = document.getElementById('imageGenLimit');
                const skipExistingCheckbox = document.getElementById('imageGenSkipExisting');
                
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '<p style="color: #3f51b5; text-align: center;">⏳ Generating images for scenarios... This may take a while.</p>';
                
                try {
                    // Build query parameters
                    const params = new URLSearchParams();
                    if (limitInput.value) {
                        params.append('limit', limitInput.value);
                    }
                    params.append('skip_existing', skipExistingCheckbox.checked.toString());
                    
                    const response = await fetch(`/agents/image-generation/process-scenarios?${params.toString()}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (data.ok && data.success) {
                        let html = `
                            <div style="background: white; padding: 20px; border-radius: 8px; border: 2px solid #3f51b5; margin-top: 15px;">
                                <h3 style="color: #2c3e50; margin-top: 0;">🎨 Image Generation Results</h3>
                                
                                ${data.message ? `
                                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #ffc107;">
                                        <strong>ℹ️ Info:</strong> ${data.message}
                                    </div>
                                ` : ''}
                                
                                <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <h4 style="margin-top: 0; color: #1976d2;">📊 Collection Statistics</h4>
                                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px;">
                                        ${data.total_scenarios !== undefined ? `
                                            <div><strong>Total Scenarios:</strong> ${data.total_scenarios}</div>
                                        ` : ''}
                                        ${data.scenarios_without_images !== undefined ? `
                                            <div><strong>Without Images:</strong> ${data.scenarios_without_images}</div>
                                        ` : ''}
                                        ${data.scenarios_processed !== undefined ? `
                                            <div><strong>Attempted:</strong> ${data.scenarios_processed}</div>
                                        ` : ''}
                                    </div>
                                </div>
                                
                                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px;">
                                    <div style="background: #e8f5e9; padding: 15px; border-radius: 5px; border-left: 4px solid #4caf50;">
                                        <div style="font-size: 0.9em; color: #2e7d32; margin-bottom: 5px;">✅ Processed</div>
                                        <div style="font-size: 1.8em; font-weight: bold; color: #2e7d32;">${data.processed || 0}</div>
                                    </div>
                                    <div style="background: #ffebee; padding: 15px; border-radius: 5px; border-left: 4px solid #dc3545;">
                                        <div style="font-size: 0.9em; color: #c62828; margin-bottom: 5px;">❌ Failed</div>
                                        <div style="font-size: 1.8em; font-weight: bold; color: #c62828;">${data.failed || 0}</div>
                                    </div>
                                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #ffc107;">
                                        <div style="font-size: 0.9em; color: #856404; margin-bottom: 5px;">⏭️ Skipped</div>
                                        <div style="font-size: 1.8em; font-weight: bold; color: #856404;">${data.skipped || 0}</div>
                                    </div>
                                </div>
                        `;
                        
                        // Show errors if any
                        if (data.error) {
                            html += `
                                <div style="background: #ffebee; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #dc3545;">
                                    <h4 style="margin-top: 0; color: #c62828;">❌ Error</h4>
                                    <p style="margin: 0; color: #c62828;">${data.error}</p>
                                    ${data.error_details ? `
                                        <details style="margin-top: 10px;">
                                            <summary style="cursor: pointer; color: #1976d2;">Show error details</summary>
                                            <pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; margin-top: 10px; font-size: 0.85em;">${data.error_details}</pre>
                                        </details>
                                    ` : ''}
                                </div>
                            `;
                        }
                        
                        // Show individual results if available
                        if (data.results && data.results.length > 0) {
                            html += `
                                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                                    <h4 style="margin-top: 0; color: #495057;">📋 Scenario Results</h4>
                                    <div style="max-height: 400px; overflow-y: auto;">
                                        <table style="width: 100%; border-collapse: collapse;">
                                            <thead>
                                                <tr style="background: #e3f2fd;">
                                                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #2196f3;">Scenario ID</th>
                                                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #2196f3;">Status</th>
                                                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #2196f3;">Image URL</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                            `;
                            
                            data.results.forEach((result, index) => {
                                const statusColor = result.success ? '#4caf50' : '#dc3545';
                                const statusText = result.success ? (result.skipped ? '⏭️ Skipped' : '✅ Success') : '❌ Failed';
                                html += `
                                    <tr style="${index % 2 === 0 ? 'background: #f5f5f5;' : ''}">
                                        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><code>${result.scenario_id || 'N/A'}</code></td>
                                        <td style="padding: 8px; border-bottom: 1px solid #ddd; color: ${statusColor}; font-weight: bold;">${statusText}</td>
                                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">
                                            ${result.image_url ? `<a href="${result.image_url}" target="_blank" style="color: #2196f3; text-decoration: none;">View Image 🔗</a>` : '-'}
                                        </td>
                                    </tr>
                                `;
                            });
                            
                            html += `
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            `;
                        }
                        
                        html += `
                                <div style="background: #e3f2fd; padding: 10px; border-radius: 5px; margin-top: 15px; border-left: 4px solid #2196f3;">
                                    <small style="color: #1976d2;">✅ Images saved to Cloud Storage and scenario documents updated in Firestore</small>
                                </div>
                            </div>
                        `;
                        
                        resultDiv.innerHTML = html;
                    } else {
                        resultDiv.innerHTML = `<div style="color: #dc3545; padding: 15px; background: #ffebee; border-radius: 5px;">❌ Error: ${data.detail || data.error || 'Unknown error'}</div>`;
                }
                } catch (error) {
                    resultDiv.innerHTML = `<div style="color: #dc3545; padding: 15px; background: #ffebee; border-radius: 5px;">❌ Error: ${error.message}</div>`;
                }
            }
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)