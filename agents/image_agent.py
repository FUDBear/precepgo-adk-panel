"""
Image Generation Agent - ADK Compliant
Uses Google's Imagen (Vertex AI) to generate educational medical images for clinical scenarios.
Automatically generates images for scenarios created by scenario_agent.
"""

import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from io import BytesIO
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Google ADK imports
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import ToolContext

# Vertex AI imports
try:
    import vertexai
    from vertexai.preview.vision_models import ImageGenerationModel
    VERTEX_AI_AVAILABLE = True
except ImportError:
    VERTEX_AI_AVAILABLE = False
    print("⚠️ Vertex AI not available - Imagen image generation unavailable")

# Cloud Storage imports
try:
    from google.cloud import storage
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False
    print("⚠️ Cloud Storage not available")

# Gemini imports for prompt enhancement
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini not available for prompt enhancement")


# ===========================================
# GLOBAL IMAGE GENERATION SETUP
# ===========================================

# Initialize Imagen model (singleton pattern)
_imagen_model = None
_storage_bucket = None
_storage_client = None
_storage_folder = "agent_assets"  # Default folder, can be overridden by STORAGE_BUCKET_URL

# Default bucket URL if not set in environment
DEFAULT_STORAGE_BUCKET_URL = "gs://auth-demo-90be0.appspot.com/agent_assets/images/clinical_scenario"

def _initialize_imagen():
    """Initialize Imagen model and Cloud Storage bucket."""
    global _imagen_model, _storage_bucket, _storage_client, _storage_folder
    
    if _imagen_model is not None:
        return _imagen_model, _storage_bucket
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("FIREBASE_PROJECT_ID")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    
    if not project_id:
        print("⚠️ Project ID not set - image generation unavailable")
        return None, None
    
    # Initialize Vertex AI and Imagen
    if VERTEX_AI_AVAILABLE:
        try:
            vertexai.init(project=project_id, location=location)
            try:
                _imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
                print("✅ Imagen model initialized (imagegeneration@006)")
            except Exception:
                try:
                    _imagen_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
                    print("✅ Imagen model initialized (imagen-3.0-generate-001)")
                except Exception as e:
                    print(f"⚠️ Failed to initialize Imagen: {e}")
                    _imagen_model = None
        except Exception as e:
            print(f"⚠️ Failed to initialize Vertex AI: {e}")
            _imagen_model = None
    
    # Initialize Cloud Storage
    if STORAGE_AVAILABLE:
        try:
            # PRIORITY: Check STORAGE_BUCKET_URL first (most explicit), fallback to default
            storage_bucket_url = os.getenv("STORAGE_BUCKET_URL") or DEFAULT_STORAGE_BUCKET_URL
            storage_bucket_name = None
            _storage_folder = "agent_assets"  # Default folder
            
            # Debug: Print what we found
            if os.getenv("STORAGE_BUCKET_URL"):
                print(f"✅ Found STORAGE_BUCKET_URL in environment: {os.getenv('STORAGE_BUCKET_URL')}")
            else:
                print(f"⚠️ STORAGE_BUCKET_URL not set, using default: {DEFAULT_STORAGE_BUCKET_URL}")
            
            if storage_bucket_url:
                # Parse gs://bucket-name/folder format
                if storage_bucket_url.startswith("gs://"):
                    parts = storage_bucket_url.replace("gs://", "").split("/", 1)
                    storage_bucket_name = parts[0]
                    if len(parts) > 1:
                        _storage_folder = parts[1]  # Use folder from URL
                    print(f"✅ Using bucket: {storage_bucket_name}")
                    print(f"✅ Using folder path: {_storage_folder}")
                else:
                    storage_bucket_name = storage_bucket_url
                    print(f"✅ Using bucket: {storage_bucket_name}")
            
            if storage_bucket_name:
                # For Firebase Storage buckets (format: {project-id}.appspot.com),
                # detect the project ID from the bucket name for cross-project access
                storage_project_id = project_id
                if storage_bucket_name.endswith('.appspot.com'):
                    # Extract project ID from bucket name (e.g., "auth-demo-90be0.appspot.com" -> "auth-demo-90be0")
                    bucket_project_id = storage_bucket_name.replace('.appspot.com', '')
                    if bucket_project_id != project_id:
                        print(f"   - Detected cross-project bucket: using project '{bucket_project_id}' for storage client")
                        storage_project_id = bucket_project_id
                
                # Initialize storage client with the correct project ID
                try:
                    _storage_client = storage.Client(project=storage_project_id)
                except Exception as client_error:
                    print(f"   - Cloud Storage Client: ⚠️ Failed to initialize with project '{storage_project_id}': {client_error}")
                    # Try without specifying project (uses default credentials)
                    try:
                        _storage_client = storage.Client()
                        print(f"   - Cloud Storage Client: ✅ Initialized with default credentials")
                    except Exception as default_error:
                        print(f"   - Cloud Storage Client: ⚠️ Failed to initialize: {default_error}")
                        raise default_error
                
                # Get bucket object (don't fail if we can't reload - actual access will be tested on upload)
                try:
                    _storage_bucket = _storage_client.bucket(storage_bucket_name)
                    
                    # Try to verify bucket access - but don't fail if reload doesn't work
                    # For cross-project buckets, reload might fail due to permissions,
                    # but we can still use the bucket for operations if we have object-level permissions
                    try:
                        _storage_bucket.reload()
                        print(f"   - Cloud Storage Bucket: ✅ ({storage_bucket_name})")
                    except Exception as reload_error:
                        # Reload failed, but we'll still try to use the bucket
                        # The actual test will happen when we try to upload
                        print(f"   - Cloud Storage Bucket: ⚠️ Cannot reload bucket metadata: {reload_error}")
                        print(f"   - Bucket object created, will test access on first upload")
                        print(f"   - Bucket project: {storage_project_id}, Bucket name: {storage_bucket_name}")
                        print(f"   - Note: Ensure Cloud Run service account has 'Storage Object Admin' role in project '{storage_project_id}'")
                        # Don't set bucket to None - keep it so we can try to use it
                except Exception as bucket_error:
                    print(f"   - Cloud Storage Bucket: ⚠️ Cannot create bucket object: {bucket_error}")
                    print(f"   - Bucket project: {storage_project_id}, Bucket name: {storage_bucket_name}")
                    _storage_bucket = None
        except Exception as e:
            print(f"⚠️ Failed to initialize Cloud Storage: {e}")
            import traceback
            traceback.print_exc()
            _storage_bucket = None
    
    return _imagen_model, _storage_bucket


# ===========================================
# TOOLS (Functions with ToolContext)
# ===========================================

def enhance_prompt_with_gemini(
    scenario_description: str,
    patient_context: Optional[Dict[str, Any]] = None,
    learning_objectives: Optional[List[str]] = None
) -> str:
    """Enhance image generation prompt using Gemini. Returns a safe, sanitized prompt."""
    SAFETY_PROMPT_SUFFIX = "Professional medical illustration style, educational, schematic diagram, no identifiable people, no graphic medical content, clean and professional."
    
    if not GEMINI_AVAILABLE:
        # Fallback: create a very generic prompt
        return f"Medical equipment and clinical setting illustration for educational purposes. {SAFETY_PROMPT_SUFFIX}"
    
    try:
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        # Sanitize scenario description - remove any patient names, ages, or identifiers
        sanitized_scenario = scenario_description
        # Remove common patient identifiers
        import re
        sanitized_scenario = re.sub(r'\b(patient|pt\.?|mr\.?|mrs\.?|ms\.?|dr\.?)\s+\w+', 'patient', sanitized_scenario, flags=re.IGNORECASE)
        sanitized_scenario = re.sub(r'\bage\s+\d+', 'age', sanitized_scenario, flags=re.IGNORECASE)
        sanitized_scenario = re.sub(r'\b\d+\s*(year|yr|yo)', 'age', sanitized_scenario, flags=re.IGNORECASE)
        
        # Build a very safe, generic prompt
        enhancement_prompt = f"""Create a safe, generic prompt for an AI image generator to create an educational medical illustration.

Scenario Context (sanitized):
{sanitized_scenario[:500]}

CRITICAL REQUIREMENTS:
- Focus ONLY on medical equipment, clinical settings, and educational diagrams
- DO NOT mention any patient information, names, ages, or personal details
- DO NOT describe any medical procedures involving patients
- Focus on: anesthesia machines, monitoring equipment, surgical instruments, operating room setup, medical diagrams
- Use generic terms: "clinical setting", "medical equipment", "operating room", "monitoring devices"
- Make it suitable for educational medical illustrations
- Avoid any graphic content, patient descriptions, or sensitive medical details
- Keep it very generic and safe

Generate a 1-2 sentence prompt that describes ONLY the medical equipment and clinical setting in a generic, educational way.

Return ONLY the prompt text, nothing else. Make it very safe and generic."""

        response = model.generate_content(enhancement_prompt)
        
        if response and response.text:
            enhanced_prompt = response.text.strip()
            # Additional sanitization
            enhanced_prompt = re.sub(r'\b(patient|pt\.?)\s+\w+', 'patient', enhanced_prompt, flags=re.IGNORECASE)
            enhanced_prompt = re.sub(r'\bage\s+\d+', 'age', enhanced_prompt, flags=re.IGNORECASE)
            enhanced_prompt = re.sub(r'\b\d+\s*(year|yr|yo)', 'age', enhanced_prompt, flags=re.IGNORECASE)
            
            final_prompt = f"{enhanced_prompt}. {SAFETY_PROMPT_SUFFIX}"
            print(f"📝 Generated prompt (first 200 chars): {final_prompt[:200]}...")
            return final_prompt
        else:
            # Very safe fallback
            return f"Medical equipment and clinical setting illustration for educational purposes. {SAFETY_PROMPT_SUFFIX}"
    except Exception as e:
        print(f"⚠️ Error enhancing prompt with Gemini: {e}")
        # Very safe fallback
        return f"Medical equipment and clinical setting illustration for educational purposes. {SAFETY_PROMPT_SUFFIX}"


def generate_image_for_scenario(tool_context: ToolContext) -> dict:
    """Generates an image for a scenario document and updates Firestore.
    
    Expects scenario_doc_id in tool_context.state (set by scenario_saver).
    
    Returns:
        dict: Generation status and image URL
    """
    scenario_doc_id = tool_context.state.get("scenario_doc_id")
    
    if not scenario_doc_id:
        return {
            "status": "error",
            "error_message": "No scenario_doc_id found in state. Ensure scenario was saved first."
        }
    
    # Initialize Imagen and Storage
    imagen_model, storage_bucket = _initialize_imagen()
    
    # Get project_id for error messages
    project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    
    if not imagen_model:
        return {
            "status": "error",
            "error_message": "Imagen model not available. Check Vertex AI configuration."
        }
    
    if not storage_bucket:
        return {
            "status": "error",
            "error_message": "Cloud Storage bucket not available. Check STORAGE_BUCKET_NAME configuration."
        }
    
    # Get Firestore client
    if project_id:
        db = firestore.Client(project=project_id)
    else:
        db = firestore.Client()
    
    try:
        print(f"🎨 Generating image for scenario: {scenario_doc_id}")
        
        # Fetch scenario document
        scenario_ref = db.collection("agent_scenarios").document(scenario_doc_id)
        scenario_doc = scenario_ref.get()
        
        if not scenario_doc.exists:
            return {
                "status": "error",
                "error_message": f"Scenario document {scenario_doc_id} not found"
            }
        
        scenario_data = scenario_doc.to_dict()
        
        # Check if image already exists
        if scenario_data.get("image"):
            print(f"⏭️  Scenario already has an image")
            return {
                "status": "success",
                "skipped": True,
                "image_url": scenario_data.get("image"),
                "scenario_id": scenario_doc_id
            }
        
        # Extract scenario description
        scenario_description = ""
        if scenario_data.get("scenario"):
            scenario_value = scenario_data.get("scenario")
            if isinstance(scenario_value, dict):
                scenario_description = scenario_value.get("description", "") or ""
            elif isinstance(scenario_value, str):
                scenario_description = scenario_value
        
        if not scenario_description:
            scenario_description = scenario_data.get("description", "") or ""
        
        if not scenario_description:
            return {
                "status": "error",
                "error_message": "No scenario description found in document"
            }
        
        # Extract patient context and learning objectives
        patient_context = scenario_data.get("patient") or {}
        learning_objectives = scenario_data.get("learning_points") or scenario_data.get("learning_objectives") or []
        
        # Enhance prompt with Gemini
        print(f"📝 Enhancing prompt...")
        final_prompt = enhance_prompt_with_gemini(
            scenario_description=scenario_description,
            patient_context=patient_context,
            learning_objectives=learning_objectives
        )
        
        # Print the full prompt for debugging
        print(f"📝 Final prompt being sent to Imagen:")
        print(f"   {final_prompt[:300]}...")
        
        # Generate image with Imagen
        print(f"🎨 Generating image with Imagen...")
        try:
            response = imagen_model.generate_images(
                prompt=final_prompt,
                number_of_images=1,
                aspect_ratio="16:9",
                safety_filter_level="block_some",
                person_generation="allow_adult"
            )
        except Exception as e:
            print(f"❌ Imagen API call failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error_message": f"Imagen API call failed: {str(e)}"
            }
        
        if not response or not hasattr(response, 'images') or not response.images:
            error_msg = "No images generated"
            if response:
                if hasattr(response, 'rai_filtered_reason'):
                    error_msg += f" - Blocked by safety filter: {response.rai_filtered_reason}"
                elif hasattr(response, 'blocked_reason'):
                    error_msg += f" - Blocked: {response.blocked_reason}"
            return {
                "status": "error",
                "error_message": error_msg
            }
        
        # Extract image bytes
        generated_image = response.images[0]
        image_bytes = None
        
        if hasattr(generated_image, '_pil_image'):
            buffer = BytesIO()
            generated_image._pil_image.save(buffer, format='PNG')
            image_bytes = buffer.getvalue()
        elif hasattr(generated_image, '_image_bytes'):
            image_bytes = generated_image._image_bytes
        elif hasattr(generated_image, 'bytes'):
            image_bytes = generated_image.bytes
        
        if not image_bytes:
            return {
                "status": "error",
                "error_message": "Could not extract image bytes from generated image"
            }
        
        # Save to Cloud Storage
        print(f"💾 Saving to Cloud Storage...")
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Use the folder path from STORAGE_BUCKET_URL if available
            # If folder from URL is "agent_assets/images/clinical_scenario", use it directly
            # Otherwise append "images/clinical_scenario" to the folder
            if _storage_folder and "clinical_scenario" in _storage_folder:
                # Folder already includes clinical_scenario path
                filename = f"{_storage_folder}/{timestamp}_{scenario_doc_id[:8]}.png"
            elif _storage_folder:
                # Folder is like "agent_assets" or "agent_assets/images", append clinical_scenario
                filename = f"{_storage_folder}/clinical_scenario/{timestamp}_{scenario_doc_id[:8]}.png"
            else:
                # Default fallback
                filename = f"agent_assets/images/clinical_scenario/{timestamp}_{scenario_doc_id[:8]}.png"
            
            print(f"📁 Saving to: {filename}")
            
            blob = storage_bucket.blob(filename)
            blob.content_type = "image/png"
            blob.upload_from_string(image_bytes, content_type="image/png")
            blob.make_public()
            image_url = blob.public_url
            
            print(f"✅ Image saved: {image_url[:80]}...")
            
            # Save image metadata to Firestore
            try:
                image_metadata = {
                    "scenario_id": scenario_doc_id,
                    "image_url": image_url,
                    "prompt": final_prompt,
                    "image_type": "clinical_scenario",
                    "generated_at": SERVER_TIMESTAMP,
                    "created_at": SERVER_TIMESTAMP
                }
                db.collection("agent_generated_images").add(image_metadata)
            except Exception as e:
                print(f"⚠️ Failed to save image metadata: {e}")
            
            # Update scenario document with image URL
            print(f"💾 Updating scenario document...")
            scenario_ref.update({
                "image": image_url,
                "image_generated_at": SERVER_TIMESTAMP,
                "updated_at": SERVER_TIMESTAMP
            })
            
            print(f"✅ Successfully generated and saved image for scenario {scenario_doc_id}")
            
            tool_context.state["image_url"] = image_url
            tool_context.state["image_generated"] = True
            
            return {
                "status": "success",
                "scenario_id": scenario_doc_id,
                "image_url": image_url
            }
        except Exception as storage_error:
            # If Cloud Storage fails, log the error but don't fail the entire scenario generation
            error_msg = f"Failed to save image to Cloud Storage: {str(storage_error)}"
            print(f"⚠️ {error_msg}")
            print(f"⚠️ Image was generated but could not be saved. Scenario will continue without image.")
            
            # Still update the scenario document to note that image generation was attempted
            try:
                scenario_ref.update({
                    "image_generation_error": error_msg,
                    "image_generation_attempted_at": SERVER_TIMESTAMP,
                    "updated_at": SERVER_TIMESTAMP
                })
            except Exception as e:
                print(f"⚠️ Failed to update scenario document: {e}")
            
            # Return success with a warning - don't fail the entire workflow
            return {
                "status": "success",
                "scenario_id": scenario_doc_id,
                "warning": "Image generated but could not be saved to Cloud Storage",
                "error": error_msg
            }
        
    except Exception as e:
        error_msg = f"Error generating image: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


# ===========================================
# AGENTS (ADK Agent instances)
# ===========================================

# Image Generator Agent
# Note: This is exported directly (not wrapped in SequentialAgent) so it can be used
# as a sub-agent in scenario_agent. ADK agents can only have one parent.
image_generator = Agent(
    name="image_generator",
    model="gemini-2.0-flash",
    description="Generates images for clinical scenarios using Imagen",
    instruction="""
    You generate educational medical images for clinical scenarios.
    
    IMPORTANT: You MUST use your generate_image_for_scenario tool to generate the image.
    
    The scenario_doc_id should be available in the state from the previous step (scenario_saver).
    
    Call your tool to generate an image for the scenario document.
    """,
    tools=[generate_image_for_scenario]
)


# Export the agent (not wrapped in SequentialAgent so it can be reused)
__all__ = ["image_generator", "generate_image_for_scenario"]
