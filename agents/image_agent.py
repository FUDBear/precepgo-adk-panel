"""
Image Generation Agent
Uses Google's Imagen (Vertex AI) to generate educational medical images for clinical scenarios.
Processes scenarios from agent_scenarios collection and adds generated images.
"""

import os
import io
from datetime import datetime
from typing import Dict, Any, Optional, List
from io import BytesIO
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

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
    from gemini_agent import GeminiAgent, MODEL_GEMINI_FLASH
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini Agent not available for prompt enhancement")

# Firestore imports
try:
    from firestore_service import get_firestore_service
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    print("⚠️ Firestore not available")

# State Agent imports
try:
    from agents.state_agent import StateAgent
    STATE_AGENT_AVAILABLE = True
except ImportError:
    STATE_AGENT_AVAILABLE = False
    print("⚠️ State Agent not available")


class ImageGenerationAgent:
    """
    Agent for generating medical images using Google's Imagen.
    Processes scenarios from agent_scenarios collection and generates images.
    """
    
    # Safety prompt suffix added to all image generation prompts
    SAFETY_PROMPT_SUFFIX = "Professional medical illustration style, educational, no identifiable patients, no graphic content."
    
    def __init__(
        self,
        project_id: Optional[str] = None,
        location: str = "us-central1",
        storage_bucket_name: Optional[str] = None,
        storage_folder: str = "agent_assets",
        firestore_db: Optional[Any] = None
    ):
        """
        Initialize the Image Generation Agent.
        
        Args:
            project_id: GCP project ID (defaults to env var)
            location: Vertex AI location (default: us-central1)
            storage_bucket_name: Cloud Storage bucket name (defaults to env var or parsed from STORAGE_BUCKET_URL)
            storage_folder: Folder path within bucket (default: agent_assets)
            firestore_db: Optional Firestore database client
        """
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("FIREBASE_PROJECT_ID")
        self.location = location
        self.storage_folder = storage_folder
        
        # Parse bucket name from URL if provided, or use env var
        storage_bucket_url = os.getenv("STORAGE_BUCKET_URL")
        if storage_bucket_url:
            # Parse gs://bucket-name/folder format
            if storage_bucket_url.startswith("gs://"):
                parts = storage_bucket_url.replace("gs://", "").split("/", 1)
                self.storage_bucket_name = parts[0]
                if len(parts) > 1:
                    self.storage_folder = parts[1]  # Override folder if in URL
            else:
                self.storage_bucket_name = storage_bucket_name or storage_bucket_url
        else:
            self.storage_bucket_name = storage_bucket_name or os.getenv("STORAGE_BUCKET_NAME")
        
        # Auto-detect Firebase Storage bucket if not set (default is {project-id}.appspot.com)
        if not self.storage_bucket_name and self.project_id:
            self.storage_bucket_name = f"{self.project_id}.appspot.com"
            print(f"   - Auto-detected Firebase Storage bucket: {self.storage_bucket_name}")
        
        # If bucket name ends with .appspot.com, keep it as-is (Firebase Storage uses full name)
        # The bucket name like "auth-demo-90be0.appspot.com" is correct for Firebase Storage
        
        if not self.project_id:
            raise ValueError("Project ID required. Set GOOGLE_CLOUD_PROJECT or FIREBASE_PROJECT_ID env var.")
        
        # Initialize Vertex AI
        self.imagen_model = None
        if VERTEX_AI_AVAILABLE:
            try:
                vertexai.init(project=self.project_id, location=self.location)
                # Try newer stable model first, fallback to older version
                try:
                    self.imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
                    print("   - Vertex AI Imagen: ✅ (using imagegeneration@006)")
                except Exception:
                    # Fallback to older model if @006 not available
                    try:
                self.imagen_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
                        print("   - Vertex AI Imagen: ✅ (using imagen-3.0-generate-001)")
                    except Exception as model_error:
                        raise model_error
            except Exception as e:
                print(f"   - Vertex AI Imagen: ⚠️ Failed to initialize: {e}")
                self.imagen_model = None
        
        # Initialize Cloud Storage
        self.storage_client = None
        self.bucket = None
        if STORAGE_AVAILABLE and self.storage_bucket_name:
            try:
                # For Firebase Storage buckets (format: {project-id}.appspot.com),
                # detect the project ID from the bucket name for cross-project access
                storage_project_id = self.project_id
                if self.storage_bucket_name.endswith('.appspot.com'):
                    # Extract project ID from bucket name (e.g., "auth-demo-90be0.appspot.com" -> "auth-demo-90be0")
                    bucket_project_id = self.storage_bucket_name.replace('.appspot.com', '')
                    if bucket_project_id != self.project_id:
                        print(f"   - Detected cross-project bucket: using project '{bucket_project_id}' for storage client")
                        storage_project_id = bucket_project_id
                
                # Initialize storage client with the correct project ID
                # For cross-project access, we can initialize without project or with bucket's project
                try:
                    self.storage_client = storage.Client(project=storage_project_id)
                except Exception as client_error:
                    print(f"   - Cloud Storage Client: ⚠️ Failed to initialize with project '{storage_project_id}': {client_error}")
                    # Try without specifying project (uses default credentials)
                    try:
                        self.storage_client = storage.Client()
                        print(f"   - Cloud Storage Client: ✅ Initialized with default credentials")
                    except Exception as default_error:
                        print(f"   - Cloud Storage Client: ⚠️ Failed to initialize: {default_error}")
                        raise default_error
                
                # Get bucket object (don't fail if we can't reload - actual access will be tested on upload)
                try:
                    self.bucket = self.storage_client.bucket(self.storage_bucket_name)
                    
                    # Try to verify bucket access - but don't fail if reload doesn't work
                    # For cross-project buckets, reload might fail due to permissions,
                    # but we can still use the bucket for operations if we have object-level permissions
                    try:
                    self.bucket.reload()
                    print(f"   - Cloud Storage Bucket: ✅ ({self.storage_bucket_name})")
                    except Exception as reload_error:
                        # Reload failed, but we'll still try to use the bucket
                        # The actual test will happen when we try to upload
                        print(f"   - Cloud Storage Bucket: ⚠️ Cannot reload bucket metadata: {reload_error}")
                        print(f"   - Bucket object created, will test access on first upload")
                        print(f"   - Bucket project: {storage_project_id}, Bucket name: {self.storage_bucket_name}")
                        print(f"   - Note: Ensure Cloud Run service account has 'Storage Object Admin' role in project '{storage_project_id}'")
                        # Don't set bucket to None - keep it so we can try to use it
                except Exception as bucket_error:
                    print(f"   - Cloud Storage Bucket: ⚠️ Cannot create bucket object: {bucket_error}")
                    print(f"   - Bucket project: {storage_project_id}, Bucket name: {self.storage_bucket_name}")
                        self.bucket = None
            except Exception as e:
                print(f"   - Cloud Storage: ⚠️ Failed to initialize: {e}")
                import traceback
                traceback.print_exc()
                self.bucket = None
        
        # Initialize Firestore
        if firestore_db:
            self.db = firestore_db
        elif FIRESTORE_AVAILABLE:
            try:
                if self.project_id:
                    self.db = firestore.Client(project=self.project_id)
                else:
                    self.db = firestore.Client()
                print("   - Firestore: ✅")
            except Exception as e:
                print(f"   - Firestore: ⚠️ Failed to initialize: {e}")
                self.db = None
        else:
            self.db = None
        
        # Initialize Gemini Agent for prompt enhancement
        self.gemini_agent = None
        if GEMINI_AVAILABLE:
            try:
                self.gemini_agent = GeminiAgent(model_name=MODEL_GEMINI_FLASH)
                print("   - Gemini Agent (Prompt Enhancement): ✅")
            except Exception as e:
                print(f"   - Gemini Agent: ⚠️ Failed to initialize: {e}")
                self.gemini_agent = None
        
        # Initialize State Agent
        self.state_agent = None
        if STATE_AGENT_AVAILABLE and self.db:
            try:
                self.state_agent = StateAgent(firestore_db=self.db)
            except Exception as e:
                print(f"   - State Agent: ⚠️ Failed to initialize: {e}")
        
        # Initialize collections
        self.scenarios_collection = "agent_scenarios"
        self.images_collection = "agent_generated_images"
        
        print(f"✅ Image Generation Agent initialized")
        print(f"   - Project: {self.project_id}")
        print(f"   - Location: {self.location}")
        print(f"   - Imagen Model: {'Available' if self.imagen_model else 'Not available'}")
        print(f"   - Storage Bucket: {'Available' if self.bucket else 'Not available'}")
    
    def enhance_prompt_with_gemini(
        self,
        scenario_description: str,
        patient_context: Optional[Dict[str, Any]] = None,
        learning_objectives: Optional[List[str]] = None
    ) -> str:
        """
        Enhance image generation prompt using Gemini.
        
        Args:
            scenario_description: Description of the clinical scenario
            patient_context: Optional patient context (age, condition, etc.)
            learning_objectives: Optional list of learning objectives
        
        Returns:
            Enhanced prompt string
        """
        if not self.gemini_agent:
            # Return basic prompt if Gemini not available
            prompt = scenario_description
            # For pediatric cases, avoid mentioning patient age/details
            is_pediatric = any(keyword in scenario_description.lower() for keyword in [
                'pediatric', 'child', 'children', 'infant', 'toddler', 
                'year-old', 'year old', 'minor', 'young patient'
            ])
            if patient_context and not is_pediatric:
                prompt += f" Patient: {patient_context.get('full_name', 'Patient')}, Age: {patient_context.get('age', 'N/A')}."
            return f"{prompt}. {self.SAFETY_PROMPT_SUFFIX}"
        
        try:
            context_parts = []
            # Check if this is a pediatric scenario first
            is_pediatric = any(keyword in scenario_description.lower() for keyword in [
                'pediatric', 'child', 'children', 'infant', 'toddler', 
                'year-old', 'year old', 'minor', 'young patient'
            ])
            
            if patient_context:
                # For pediatric cases, only include condition, not age or name
                if is_pediatric:
                    context_parts.append(f"Medical condition: {patient_context.get('condition', 'N/A')}")
                else:
                context_parts.append(f"Patient: {patient_context.get('full_name', 'Patient')}, Age: {patient_context.get('age', 'N/A')}, Condition: {patient_context.get('condition', 'N/A')}")
            
            if learning_objectives:
                context_parts.append(f"Learning focus: {', '.join(learning_objectives)}")
            
            context_str = "\n".join(context_parts) if context_parts else "No additional context"
            
            if is_pediatric:
                # For pediatric cases, focus on medical setting/equipment, not patient details
                enhancement_prompt = f"""Create a detailed, professional prompt for generating an educational medical illustration image.

Scenario Description:
{scenario_description}

Additional Context:
{context_str}

Generate a concise, descriptive prompt (2-3 sentences max) for an AI image generator that will create a professional medical illustration. IMPORTANT: 
- Focus ONLY on the medical equipment, clinical setting, and procedures - DO NOT mention patient age, patient characteristics, or patient appearance
- Describe the operating room environment, anesthesia equipment, monitoring devices, and medical procedures
- Focus on the clinical scenario and educational value from a medical equipment/setting perspective
- Use generic terms like "patient preparation area" or "perioperative setting" rather than patient-specific details
- Be suitable for nursing education
- Avoid any patient identifiers, age references, or patient appearance descriptions

Return ONLY the prompt text, nothing else."""
            else:
            enhancement_prompt = f"""Create a detailed, professional prompt for generating an educational medical illustration image.

Scenario Description:
{scenario_description}

Additional Context:
{context_str}

Generate a concise, descriptive prompt (2-3 sentences max) for an AI image generator that will create a professional medical illustration. The prompt should:
- Focus on the clinical scenario and educational value
- Include relevant medical details (equipment, setting, clinical indicators)
- Be suitable for nursing education
- Avoid patient identifiers or graphic content

Return ONLY the prompt text, nothing else."""

            response = self.gemini_agent.model.generate_content(enhancement_prompt)
            
            if response and response.text:
                enhanced_prompt = response.text.strip()
                # Add safety suffix
                return f"{enhanced_prompt}. {self.SAFETY_PROMPT_SUFFIX}"
            else:
                # Fallback to basic prompt
                prompt = scenario_description
                # For pediatric cases, avoid mentioning patient age/details
                if patient_context and not is_pediatric:
                    prompt += f" Patient: {patient_context.get('full_name', 'Patient')}, Age: {patient_context.get('age', 'N/A')}."
                return f"{prompt}. {self.SAFETY_PROMPT_SUFFIX}"
                
        except Exception as e:
            print(f"⚠️ Failed to enhance prompt with Gemini: {e}")
            # Fallback to basic prompt
            prompt = scenario_description
            # For pediatric cases, avoid mentioning patient age/details
            is_pediatric = any(keyword in scenario_description.lower() for keyword in [
                'pediatric', 'child', 'children', 'infant', 'toddler', 
                'year-old', 'year old', 'minor', 'young patient'
            ])
            if patient_context and not is_pediatric:
                prompt += f" Patient: {patient_context.get('full_name', 'Patient')}, Age: {patient_context.get('age', 'N/A')}."
            return f"{prompt}. {self.SAFETY_PROMPT_SUFFIX}"
    
    def generate_image(
        self,
        prompt: str,
        image_type: str = "clinical_scenario",
        enhance_prompt: bool = True,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate an image using Imagen.
        
        Args:
            prompt: Image generation prompt
            image_type: Type of image (clinical_scenario, anatomical_diagram, procedure)
            enhance_prompt: Whether to enhance prompt with Gemini (default: True)
            context: Optional context dict (scenario_description, patient_context, learning_objectives)
        
        Returns:
            Dictionary with success status, image URLs, and metadata
        """
        if not self.imagen_model:
            return {
                "success": False,
                "error": "Imagen model not available",
                "image_url": None
            }
        
        try:
            # Enhance prompt if requested and context provided
            final_prompt = prompt
            if enhance_prompt and context:
                scenario_desc = context.get("scenario_description", prompt)
                patient_context = context.get("patient_context")
                learning_objectives = context.get("learning_objectives")
                
                final_prompt = self.enhance_prompt_with_gemini(
                    scenario_desc,
                    patient_context,
                    learning_objectives
                )
            elif enhance_prompt:
                # Enhance basic prompt
                final_prompt = self.enhance_prompt_with_gemini(prompt)
            else:
                # Just add safety suffix
                final_prompt = f"{prompt}. {self.SAFETY_PROMPT_SUFFIX}"
            
            print(f"🎨 Generating image with prompt: {final_prompt[:100]}...")
            
            # Generate image
            print(f"   📞 Calling Imagen API...")
            try:
            response = self.imagen_model.generate_images(
                prompt=final_prompt,
                number_of_images=1,
                    aspect_ratio="16:9",  # Match working temp dashboard settings
                    safety_filter_level="block_some",  # Match working temp dashboard settings
                person_generation="allow_adult"  # Allow adults in medical illustrations
            )
            except Exception as e:
                print(f"   ❌ Exception calling Imagen API: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "success": False,
                    "error": f"Imagen API call failed: {str(e)}",
                    "image_url": None
                }
            
            print(f"   ✅ Imagen API response received")
            
            # Debug: Log response structure
            if response:
                print(f"   🔍 Response type: {type(response)}")
                public_attrs = [attr for attr in dir(response) if not attr.startswith('_')]
                print(f"   🔍 Response public attributes: {public_attrs}")
                
                # Check for images attribute
                if hasattr(response, 'images'):
                    print(f"   🔍 Response.images: {response.images}")
                    if response.images:
                        print(f"   🔍 Number of images: {len(response.images)}")
                    else:
                        print(f"   ⚠️ Response.images is empty or None")
                        # Check for blocked reasons or errors in all attributes
                        for attr in dir(response):
                            if not attr.startswith('__'):
                                try:
                                    value = getattr(response, attr)
                                    if callable(value):
                                        continue
                                    # Check for blocking or error-related attributes
                                    if any(keyword in attr.lower() for keyword in ['block', 'error', 'reason', 'safety', 'filter', 'violation']):
                                        print(f"   🔍 {attr}: {value}")
                                except Exception:
                                    pass
                else:
                    print(f"   ⚠️ Response object has no 'images' attribute")
            
            if not response or not hasattr(response, 'images') or not response.images:
                error_msg = "No images generated"
                # Check for blocking reasons
                if response:
                    if hasattr(response, 'rai_filtered_reason'):
                        error_msg += f" - Blocked by safety filter: {response.rai_filtered_reason}"
                    elif hasattr(response, 'blocked_reason'):
                        error_msg += f" - Blocked: {response.blocked_reason}"
                    if hasattr(response, 'error'):
                        error_msg += f" - Error: {response.error}"
                print(f"   ❌ No images in response: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "image_url": None
                }
            
            # Get generated image
            generated_image = response.images[0]
            print(f"   ✅ Image object retrieved")
            
            # Extract image bytes - try multiple methods (prioritize _pil_image which worked in temp dashboard)
            image_bytes = None
            
            # Method 1: ._pil_image and convert (this is what worked in your temp dashboard!)
            if hasattr(generated_image, '_pil_image'):
                buffer = BytesIO()
                generated_image._pil_image.save(buffer, format='PNG')
                image_bytes = buffer.getvalue()
                print(f"   ✅ Got bytes via PIL conversion: {len(image_bytes)} bytes")
            # Method 2: _image_bytes (original method)
            elif hasattr(generated_image, '_image_bytes'):
                image_bytes = generated_image._image_bytes
                print(f"   ✅ Got bytes via _image_bytes: {len(image_bytes)} bytes")
            # Method 3: .bytes property
            elif hasattr(generated_image, 'bytes'):
                image_bytes = generated_image.bytes
                print(f"   ✅ Got bytes via .bytes: {len(image_bytes)} bytes")
            # Method 4: .save() method
            elif hasattr(generated_image, 'save'):
                buffer = BytesIO()
                generated_image.save(buffer)
                image_bytes = buffer.getvalue()
                print(f"   ✅ Got bytes via .save(): {len(image_bytes)} bytes")
            
            if not image_bytes:
                available_attrs = [a for a in dir(generated_image) if not a.startswith('_')]
                print(f"   ❌ Could not extract image bytes")
                print(f"   📋 Available attributes: {available_attrs}")
                return {
                    "success": False,
                    "error": "Could not extract image bytes from generated image",
                    "image_url": None
                }
            
            # Save to Cloud Storage
            image_url = None
            if self.bucket:
                print(f"   💾 Saving to Cloud Storage...")
                image_url = self._save_to_storage(
                    image_bytes,
                    prompt=final_prompt,
                    image_type=image_type
                )
                print(f"   ✅ Image saved to Cloud Storage")
            else:
                print(f"   ⚠️ Cloud Storage bucket not available, skipping save")
            
            return {
                "success": True,
                "image_url": image_url,
                "prompt": final_prompt,
                "image_type": image_type,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"⚠️ Failed to generate image: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "image_url": None
            }
    
    def generate_clinical_scenario_image(
        self,
        scenario_description: str,
        patient_context: Optional[Dict[str, Any]] = None,
        learning_objectives: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate an image for a clinical scenario.
        
        Args:
            scenario_description: Description of the clinical scenario
            patient_context: Optional patient context (age, condition, etc.)
            learning_objectives: Optional list of learning objectives
        
        Returns:
            Dictionary with success status, image URLs, and metadata
        """
        context = {
            "scenario_description": scenario_description,
            "patient_context": patient_context,
            "learning_objectives": learning_objectives
        }
        
        return self.generate_image(
            prompt=scenario_description,
            image_type="clinical_scenario",
            enhance_prompt=True,
            context=context
        )
    
    def _save_to_storage(
        self,
        image_bytes: bytes,
        prompt: str,
        image_type: str,
        index: int = 0
    ) -> str:
        """
        Save image bytes to Cloud Storage and return public URL.
        
        Args:
            image_bytes: Image bytes to save
            prompt: Prompt used to generate image
            image_type: Type of image
            index: Index for multiple images (default: 0)
        
        Returns:
            Public URL of uploaded image
        """
        if not self.bucket:
            raise ValueError("Cloud Storage bucket not initialized")
        
        # Generate filename with folder path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.storage_folder}/images/{image_type}/{timestamp}_{index}.png"
        
        # Upload to Cloud Storage
        blob = self.bucket.blob(filename)
        blob.content_type = "image/png"
        # Use upload_from_string with explicit content_type to avoid Content-Type mismatch
        blob.upload_from_string(image_bytes, content_type="image/png")
        
        # Make blob publicly readable
        blob.make_public()
        
        # Return public URL
        public_url = blob.public_url
        print(f"📤 Uploaded image to: {public_url}")
        
        return public_url
    
    def process_scenario_document(self, scenario_doc_id: str) -> Dict[str, Any]:
        """
        Process a single scenario document: generate image and update document.
        
        Args:
            scenario_doc_id: ID of the scenario document to process
        
        Returns:
            Dictionary with processing results
        """
        if not self.db:
            return {
                "success": False,
                "error": "Firestore not available",
                "scenario_id": scenario_doc_id
            }
        
        try:
            print(f"   📄 Fetching scenario document: {scenario_doc_id}")
            
            # Get scenario document
            scenario_ref = self.db.collection(self.scenarios_collection).document(scenario_doc_id)
            scenario_doc = scenario_ref.get()
            
            if not scenario_doc.exists:
                print(f"   ❌ Scenario document not found")
                return {
                    "success": False,
                    "error": f"Scenario document {scenario_doc_id} not found",
                    "scenario_id": scenario_doc_id
                }
            
            scenario_data = scenario_doc.to_dict()
            print(f"   ✅ Document found")
            
            # Check if image already exists
            if scenario_data.get("image"):
                print(f"   ⏭️  Scenario already has an image: {scenario_data.get('image')[:60]}...")
                return {
                    "success": True,
                    "skipped": True,
                    "image_url": scenario_data.get("image"),
                    "scenario_id": scenario_doc_id
                }
            
            # Extract scenario description (handle both string and dict cases)
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
                print(f"   ❌ No scenario description found in document")
                print(f"   📋 Available fields: {list(scenario_data.keys())}")
                return {
                    "success": False,
                    "error": "No scenario description found",
                    "scenario_id": scenario_doc_id,
                    "available_fields": list(scenario_data.keys())
                }
            
            print(f"   📝 Scenario description: {scenario_description[:100]}...")
            
            # Extract patient context
            patient_context = scenario_data.get("patient") or {}
            if patient_context:
                print(f"   👤 Patient context: {patient_context.get('full_name', 'N/A')}")
            
            # Extract learning objectives
            learning_objectives = scenario_data.get("learning_objectives") or scenario_data.get("objectives") or []
            if learning_objectives:
                print(f"   🎯 Learning objectives: {len(learning_objectives)} found")
            
            # Generate image
            print(f"   🎨 Generating image...")
            image_result = self.generate_clinical_scenario_image(
                scenario_description=scenario_description,
                patient_context=patient_context,
                learning_objectives=learning_objectives
            )
            
            if not image_result.get("success"):
                error_msg = image_result.get("error", "Image generation failed")
                print(f"   ❌ Image generation failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "scenario_id": scenario_doc_id
                }
            
            image_url = image_result.get("image_url")
            
            if not image_url:
                print(f"   ❌ No image URL returned from generation")
                return {
                    "success": False,
                    "error": "Image generated but no URL returned",
                    "scenario_id": scenario_doc_id
                }
            
            print(f"   ✅ Image generated successfully: {image_url[:80]}...")
            
            # Save image metadata to Firestore
            print(f"   💾 Saving image metadata to Firestore...")
            image_metadata = {
                "scenario_id": scenario_doc_id,
                "image_url": image_url,
                "prompt": image_result.get("prompt"),
                "image_type": image_result.get("image_type"),
                "generated_at": SERVER_TIMESTAMP,
                "created_at": SERVER_TIMESTAMP
            }
            
            try:
                self.db.collection(self.images_collection).add(image_metadata)
                print(f"   ✅ Image metadata saved")
            except Exception as e:
                print(f"   ⚠️ Failed to save image metadata: {e}")
            
            # Update scenario document with image URL
            print(f"   💾 Updating scenario document with image URL...")
            try:
                scenario_ref.update({
                    "image": image_url,
                    "image_generated_at": SERVER_TIMESTAMP,
                    "updated_at": SERVER_TIMESTAMP
                })
                print(f"   ✅ Scenario document updated")
            except Exception as e:
                print(f"   ⚠️ Failed to update scenario document: {e}")
                return {
                    "success": False,
                    "error": f"Failed to update scenario document: {str(e)}",
                    "scenario_id": scenario_doc_id,
                    "image_url": image_url  # Image was generated but doc update failed
                }
            
            print(f"   ✅ Successfully processed scenario {scenario_doc_id}")
            
            return {
                "success": True,
                "scenario_id": scenario_doc_id,
                "image_url": image_url,
                "image_result": image_result
            }
            
        except Exception as e:
            print(f"   ❌ Exception processing scenario {scenario_doc_id}: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "error_details": traceback.format_exc(),
                "scenario_id": scenario_doc_id
            }
    
    def process_all_scenarios(
        self,
        limit: Optional[int] = None,
        skip_existing: bool = True
    ) -> Dict[str, Any]:
        """
        Process all scenarios in the agent_scenarios collection.
        
        Args:
            limit: Optional limit on number of scenarios to process
            skip_existing: Whether to skip scenarios that already have images (default: True)
        
        Returns:
            Dictionary with processing results
        """
        if not self.db:
            print("❌ Cannot process scenarios: Firestore not available")
            return {
                "success": False,
                "error": "Firestore not available",
                "processed": 0,
                "failed": 0
            }
        
        if not self.imagen_model:
            print("❌ Cannot process scenarios: Imagen model not available")
            return {
                "success": False,
                "error": "Imagen model not available",
                "processed": 0,
                "failed": 0
            }
        
        if not self.bucket:
            error_msg = f"Cloud Storage bucket not available. Bucket name: {self.storage_bucket_name or 'Not set'}. "
            if self.storage_bucket_name and self.storage_bucket_name.endswith('.appspot.com'):
                bucket_project = self.storage_bucket_name.replace('.appspot.com', '')
                error_msg += f"Please ensure Cloud Run service account has 'Storage Object Admin' role in project '{bucket_project}'. "
            error_msg += "Please check STORAGE_BUCKET_NAME or STORAGE_BUCKET_URL environment variable."
            print(f"❌ Cannot process scenarios: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "processed": 0,
                "failed": 0
            }
        
        # Update state to PROCESSING
        if self.state_agent:
            try:
                from agents.state_agent import StateAgent
                self.state_agent.set_agent_state("image_agent", StateAgent.STATE_PROCESSING)
            except Exception as e:
                print(f"⚠️ Failed to update state_agent: {e}")
        
        try:
            print("\n" + "="*60)
            print("🎨 Starting Image Generation Process")
            print("="*60)
            print(f"📋 Collection: {self.scenarios_collection}")
            print(f"🔄 Skip existing: {skip_existing}")
            print(f"📊 Limit: {limit or 'All scenarios'}")
            
            # Query all scenarios
            query = self.db.collection(self.scenarios_collection)
            
            # Count total scenarios first
            all_scenarios = list(query.stream())
            total_count = len(all_scenarios)
            print(f"📈 Total scenarios in collection: {total_count}")
            
            if skip_existing:
                # Count scenarios without images
                scenarios_without_images = [doc for doc in all_scenarios if not doc.to_dict().get("image")]
                count_without_images = len(scenarios_without_images)
                print(f"🖼️  Scenarios without images: {count_without_images}")
                print(f"⏭️  Scenarios with existing images: {total_count - count_without_images}")
                
                if count_without_images == 0:
                    print("ℹ️  No scenarios need image generation (all already have images)")
                    return {
                        "success": True,
                        "processed": 0,
                        "failed": 0,
                        "skipped": total_count,
                        "results": [],
                        "message": "All scenarios already have images"
                    }
                
                # Use filtered list
                scenarios_to_process = scenarios_without_images
            else:
                scenarios_to_process = all_scenarios
                print(f"🔄 Processing all scenarios (including those with existing images)")
            
            # Apply limit if specified
            if limit:
                scenarios_to_process = scenarios_to_process[:limit]
                print(f"🔢 Limited to {limit} scenarios")
            
            print(f"✅ Will process {len(scenarios_to_process)} scenario(s)")
            print("="*60 + "\n")
            
            results = {
                "success": True,
                "processed": 0,
                "failed": 0,
                "skipped": 0,
                "results": [],
                "total_scenarios": total_count,
                "scenarios_without_images": count_without_images if skip_existing else total_count,
                "scenarios_processed": len(scenarios_to_process)
            }
            
            for idx, scenario_doc in enumerate(scenarios_to_process, 1):
                scenario_id = scenario_doc.id
                scenario_data = scenario_doc.to_dict()
                
                print(f"\n[{idx}/{len(scenarios_to_process)}] Processing scenario: {scenario_id}")
                print(f"   - Has image field: {'Yes' if scenario_data.get('image') else 'No'}")
                
                # Handle scenario description (can be string or dict)
                scenario_desc = "N/A"
                if scenario_data.get('scenario'):
                    scenario_value = scenario_data.get('scenario')
                    if isinstance(scenario_value, dict):
                        scenario_desc = scenario_value.get('description', 'N/A')
                    elif isinstance(scenario_value, str):
                        scenario_desc = scenario_value
                elif scenario_data.get('description'):
                    scenario_desc = scenario_data.get('description')
                
                print(f"   - Scenario description: {scenario_desc[:80] if isinstance(scenario_desc, str) else 'N/A'}...")
                
                result = self.process_scenario_document(scenario_id)
                results["results"].append(result)
                
                if result.get("success"):
                    if result.get("skipped"):
                        results["skipped"] += 1
                        print(f"   ✅ Skipped (already has image)")
                    else:
                        results["processed"] += 1
                        print(f"   ✅ Generated image: {result.get('image_url', 'N/A')[:80]}...")
                else:
                    results["failed"] += 1
                    error_msg = result.get("error", "Unknown error")
                    print(f"   ❌ Failed: {error_msg}")
            
            print("\n" + "="*60)
            print("📊 Image Generation Summary")
            print("="*60)
            print(f"✅ Processed: {results['processed']}")
            print(f"❌ Failed: {results['failed']}")
            print(f"⏭️  Skipped: {results['skipped']}")
            print(f"📈 Total scenarios: {results['total_scenarios']}")
            print("="*60 + "\n")
            
            # Update state to COMPLETED
            if self.state_agent:
                try:
                    from agents.state_agent import StateAgent
                    self.state_agent.set_agent_result(
                        "image_agent",
                        {
                            "processed": results["processed"],
                            "failed": results["failed"],
                            "skipped": results["skipped"],
                            "total_scenarios": results["total_scenarios"]
                        },
                        StateAgent.STATE_COMPLETED
                    )
                except Exception as e:
                    print(f"⚠️ Failed to update state_agent result: {e}")
            
            return results
            
        except Exception as e:
            print(f"\n❌ Failed to process scenarios: {e}")
            import traceback
            traceback.print_exc()
            
            # Update state to ERROR
            if self.state_agent:
                try:
                    from agents.state_agent import StateAgent
                    self.state_agent.set_agent_error("image_agent", str(e))
                except Exception:
                    pass
            
            return {
                "success": False,
                "error": str(e),
                "error_details": traceback.format_exc(),
                "processed": 0,
                "failed": 0
            }


# Convenience function for easy importing
def create_image_generation_agent(
    project_id: Optional[str] = None,
    location: str = "us-central1",
    storage_bucket_name: Optional[str] = None,
    storage_folder: str = "agent_assets",
    firestore_db: Optional[Any] = None
) -> ImageGenerationAgent:
    """
    Create and return an ImageGenerationAgent instance.
    
    Args:
        project_id: GCP project ID
        location: Vertex AI location
        storage_bucket_name: Cloud Storage bucket name
        storage_folder: Folder path within bucket (default: agent_assets)
        firestore_db: Optional Firestore database client
    
    Returns:
        ImageGenerationAgent instance
    """
    return ImageGenerationAgent(
        project_id=project_id,
        location=location,
        storage_bucket_name=storage_bucket_name,
        storage_folder=storage_folder,
        firestore_db=firestore_db
    )

