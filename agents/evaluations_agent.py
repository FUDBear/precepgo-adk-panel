"""
Evaluations Agent
Independent agent for generating demo evaluation data and saving to Firestore.
Handles creation of fake evaluation documents in the 'agent_evaluations' subcollection.
"""

import os
import json
import random
import re
import string
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP, GeoPoint

# Gemini API imports
try:
    import google.generativeai as genai
    from google.generativeai.types import HarmBlockThreshold, HarmCategory
    from google.ai.generativelanguage_v1beta.types import Candidate
    from google.auth.exceptions import TransportError
    from google.api_core import retry
    GEMINI_TYPES_AVAILABLE = True
except ImportError as e:
    GEMINI_TYPES_AVAILABLE = False
    print(f"⚠️ Some Gemini types not available: {e}")

# Import dependencies
try:
    from firestore_service import get_firestore_service, FirestoreScenarioService
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    print("⚠️ Firestore not available")

# Import Vector Search and Gemini for enhanced comment generation
try:
    from vector_search_tool import VectorSearchTool
    VECTOR_SEARCH_AVAILABLE = True
except ImportError:
    VECTOR_SEARCH_AVAILABLE = False
    print("⚠️ Vector Search Tool not available")

try:
    from agents.state_agent import StateAgent
    STATE_AGENT_AVAILABLE = True
except ImportError:
    STATE_AGENT_AVAILABLE = False
    print("⚠️ State Agent not available")

try:
    from gemini_agent import GeminiAgent, MODEL_GEMINI_PRO, MODEL_GEMINI_FLASH
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini Agent not available")


class EvaluationsAgent:
    """
    Independent agent for generating demo evaluation data.
    Creates fake evaluation documents matching the structure from evaluation_example.text.
    """
    
    # AC Metric Definitions (Anesthesia Competency)
    AC_METRICS = {
        "ac_0": "Procedural Room Readiness",
        "ac_1": "Pre-op Assessment",
        "ac_2": "Safely Transfers Care",
        "ac_3": "Medication Administration",
        "ac_4": "Regional Technique",
        "ac_5": "Anesthesia Induction",
        "ac_6": "Airway Management",
        "ac_7": "Ventilatory Management",
        "ac_8": "Procedure(s) Performed",
        "ac_9": "Patient Positioning",
        "ac_10": "Anesthetic Maintenance",
        "ac_11": "Responds to Condition Changes",
        "ac_12": "Emergence Technique",
    }
    
    # PC Metric Definitions (Performance Categories / Behavior)
    PC_METRICS = {
        "pc_0": "Appropriate Intervention",
        "pc_1": "Appropriate Pain Control",
        "pc_2": "Receptive to Instruction",
        "pc_3": "Communicated Effectively",
        "pc_4": "Troubleshoots Effectively",
        "pc_5": "Calm/Professional Demeanor",
        "pc_6": "Recognizes Limitations",
        "pc_7": "Professionalism and Integrity",
        "pc_8": "Accountable for Care",
        "pc_9": "Documentation Reflects Care",
        "pc_10": "Follows Universal Precautions",
    }
    
    def __init__(self, parent_collection: str = "requests", parent_doc_id: Optional[str] = None):
        """
        Initialize the Evaluations Agent.
        
        Args:
            parent_collection: Name of the parent collection (default: "requests")
            parent_doc_id: Optional parent document ID. If None, will use a generated one.
        """
        self.parent_collection = parent_collection
        self.parent_doc_id = parent_doc_id
        
        # Load cases from cases.json
        self.cases = self._load_cases()
        
        # Load students from students.json
        self.students = self._load_students()
        
        # Load preceptors from sites.json
        self.preceptors = self._load_preceptors()
        
        # Load example comments and focus areas for reference
        self.comment_examples = self._load_comment_examples()
        
        # Initialize Vector Search Tool for case research
        self.vector_search = None
        if VECTOR_SEARCH_AVAILABLE:
            try:
                self.vector_search = VectorSearchTool()
                print("   - Vector Search Tool: ✅")
            except Exception as e:
                print(f"   - Vector Search Tool: ⚠️ Failed to initialize: {e}")
                self.vector_search = None
        
        # Initialize Gemini Agent for comment generation
        self.gemini_agent = None
        if GEMINI_AVAILABLE:
            try:
                # Try Flash first - faster and may have different safety filter behavior
                # If Flash still blocks, try switching to MODEL_GEMINI_PRO (may be less restrictive)
                self.gemini_agent = GeminiAgent(model_name=MODEL_GEMINI_FLASH)
                print("   - Gemini Agent (Flash): ✅")
            except Exception as e:
                print(f"   - Gemini Agent: ⚠️ Failed to initialize: {e}")
                self.gemini_agent = None
        
        # Initialize Firestore client
        if FIRESTORE_AVAILABLE:
            try:
                # Get project ID from environment
                project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
                
                if project_id:
                    self.db = firestore.Client(project=project_id)
                else:
                    self.db = firestore.Client()
                
                print(f"✅ Evaluations Agent initialized")
                print(f"   - Parent collection: {parent_collection}")
                print(f"   - Subcollection: agent_evaluations")
                print(f"   - Cases loaded: {len(self.cases)}")
                print(f"   - Students loaded: {len(self.students)}")
                print(f"   - Preceptors loaded: {len(self.preceptors)}")
            except Exception as e:
                print(f"⚠️ Firestore initialization failed: {e}")
                self.db = None
        else:
            self.db = None
            print("⚠️ Evaluations Agent initialized without Firestore support")
        
        # Initialize State Agent for state tracking (after Firestore is initialized)
        self.state_agent = None
        if STATE_AGENT_AVAILABLE and self.db:
            try:
                self.state_agent = StateAgent(firestore_db=self.db)
            except Exception as e:
                print(f"   - State Agent: ⚠️ Failed to initialize: {e}")
                self.state_agent = None
    
    def _load_cases(self) -> List[Dict[str, Any]]:
        """Load cases from JSON file"""
        try:
            with open("data/cases.json", "r") as f:
                data = json.load(f)
            
            # Handle different JSON structures
            if isinstance(data, dict):
                if 'procedures' in data:
                    return data['procedures']
                else:
                    case_list = list(data.values())
                    if case_list and isinstance(case_list[0], list):
                        return [item for sublist in case_list for item in sublist]
                    return case_list
            elif isinstance(data, list):
                return data
            else:
                print("⚠️ Invalid cases.json structure")
                return []
        except FileNotFoundError:
            print("⚠️ data/cases.json not found")
            return []
        except json.JSONDecodeError as e:
            print(f"⚠️ Error parsing data/cases.json: {e}")
            return []
    
    def _load_students(self) -> List[Dict[str, Any]]:
        """Load students from JSON file"""
        try:
            with open("data/students.json", "r") as f:
                data = json.load(f)
            
            # Handle different JSON structures
            if isinstance(data, dict):
                if 'students' in data:
                    return data['students']
                else:
                    return list(data.values())
            elif isinstance(data, list):
                return data
            else:
                print("⚠️ Invalid students.json structure")
                return []
        except FileNotFoundError:
            print("⚠️ data/students.json not found")
            return []
        except json.JSONDecodeError as e:
            print(f"⚠️ Error parsing data/students.json: {e}")
            return []
    
    def _load_preceptors(self) -> List[Dict[str, Any]]:
        """Load preceptors from sites.json file"""
        try:
            import os
            sites_path = "data/sites.json"
            if not os.path.exists(sites_path):
                print(f"⚠️ sites.json not found at {os.path.abspath(sites_path)}")
                return []
            
            with open(sites_path, "r") as f:
                data = json.load(f)
            
            # Handle different JSON structures
            if isinstance(data, dict):
                if 'preceptors' in data:
                    preceptors = data['preceptors']
                    print(f"✅ Loaded {len(preceptors)} preceptors from sites.json")
                    return preceptors
                else:
                    print(f"⚠️ sites.json does not contain 'preceptors' key")
                    return []
            elif isinstance(data, list):
                print(f"✅ Loaded {len(data)} preceptors from sites.json (list format)")
                return data
            else:
                print("⚠️ Invalid sites.json structure")
                return []
        except FileNotFoundError:
            print(f"⚠️ data/sites.json not found at {os.path.abspath('data/sites.json')}")
            return []
        except json.JSONDecodeError as e:
            print(f"⚠️ Error parsing data/sites.json: {e}")
            return []
        except Exception as e:
            print(f"⚠️ Unexpected error loading preceptors: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _load_comment_examples(self) -> List[Dict[str, str]]:
        """Load example comments and focus areas from JSON file"""
        try:
            with open("data/comments_example.json", "r") as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                if 'examples' in data:
                    return data['examples']
                else:
                    return list(data.values())
            elif isinstance(data, list):
                return data
            else:
                print("⚠️ Invalid comments_example.json structure")
                return []
        except FileNotFoundError:
            print("⚠️ data/comments_example.json not found")
            return []
        except json.JSONDecodeError as e:
            print(f"⚠️ Error parsing data/comments_example.json: {e}")
            return []
    
    def _select_random_student(self) -> Optional[Dict[str, Any]]:
        """Select a random student from available students"""
        if not self.students:
            return None
        return random.choice(self.students)
    
    def _select_preceptor(self, student: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Select a preceptor from sites.json.
        Optionally matches to student's hospital if available.
        
        Args:
            student: Optional student dictionary to match by hospital
        
        Returns:
            Preceptor dictionary from sites.json, or None if none available
        """
        if not self.preceptors or len(self.preceptors) == 0:
            print(f"⚠️ _select_preceptor: No preceptors available")
            return None
        
        print(f"📋 Selecting from {len(self.preceptors)} preceptors")
        
        # Try to match preceptor to student's hospital if student is provided
        if student:
            student_hospital = student.get('hospital', '')
            if student_hospital:
                # Extract hospital name from student's hospital field
                # Format is typically "HOSPITAL NAME, CITY, STATE"
                hospital_name_parts = student_hospital.split(',')
                if hospital_name_parts:
                    # Get the hospital name (first part)
                    student_hospital_name = hospital_name_parts[0].strip().upper()
                    print(f"   🔍 Trying to match student hospital: {student_hospital_name}")
                    
                    # Try to find a preceptor assigned to this hospital
                    matching_preceptors = []
                    for preceptor in self.preceptors:
                        assigned_sites = preceptor.get('assignedSites', [])
                        for site in assigned_sites:
                            site_name = site.get('hospitalName', '').upper()
                            # Check if hospital names match (partial match for flexibility)
                            if student_hospital_name in site_name or site_name in student_hospital_name:
                                matching_preceptors.append(preceptor)
                                print(f"   ✅ Found matching preceptor: {preceptor.get('firstName', '')} {preceptor.get('lastName', '')} at {site.get('hospitalName', '')}")
                                break
                    
                    # If we found matching preceptors, select randomly from them
                    if matching_preceptors:
                        selected = random.choice(matching_preceptors)
                        print(f"   ✅ Selected matching preceptor: {selected.get('firstName', '')} {selected.get('lastName', '')}")
                        return selected
        
        # If no match found or no student provided, select random preceptor
        selected = random.choice(self.preceptors)
        print(f"   ✅ Selected random preceptor: {selected.get('firstName', '')} {selected.get('lastName', '')}")
        return selected
    
    def _convert_class_standing_to_numeric(self, class_standing_str: str) -> int:
        """
        Convert class standing string to numeric value.
        
        Args:
            class_standing_str: String like "1st Year", "2nd Year", "3rd Year", "4th Year"
            
        Returns:
            Integer 1-4, or random 1-4 if conversion fails
        """
        if not class_standing_str:
            return random.randint(1, 4)
        
        class_standing_str_lower = class_standing_str.lower().strip()
        
        if "1st" in class_standing_str_lower or "first" in class_standing_str_lower or class_standing_str_lower == "1":
            return 1
        elif "2nd" in class_standing_str_lower or "second" in class_standing_str_lower or class_standing_str_lower == "2":
            return 2
        elif "3rd" in class_standing_str_lower or "third" in class_standing_str_lower or class_standing_str_lower == "3":
            return 3
        elif "4th" in class_standing_str_lower or "fourth" in class_standing_str_lower or class_standing_str_lower == "4":
            return 4
        else:
            # Try to extract number if present
            import re
            numbers = re.findall(r'\d+', class_standing_str)
            if numbers:
                num = int(numbers[0])
                if 1 <= num <= 4:
                    return num
            # Default fallback
            return random.randint(1, 4)
    
    def _select_random_case(self) -> Dict[str, Any]:
        """Select a random case from available cases"""
        if not self.cases:
            return {"code": "UNKNOWN", "name": "Unknown Case", "description": ""}
        return random.choice(self.cases)
    
    def _generate_preceptor_comment(
        self,
        case: Dict[str, Any],
        preceptee_name: str,
        class_standing: int,
        scores: Dict[str, int]
    ) -> str:
        """
        Generate a realistic preceptor comment based on case, class standing, and scores.
        Uses Vector Search to research case type and Gemini to generate unique, tailored comments.
        """
        case_name = case.get('name', 'this case')
        case_code = case.get('code', '')
        case_description = case.get('description', '')
        case_keywords = case.get('keywords', [])
        
        # Calculate average scores
        ac_values = [scores.get(f'ac_{i}', 70) for i in range(13)]
        pc_values = [scores.get(f'pc_{i}', 3) for i in range(11)]
        pc_values_for_avg = [v for v in pc_values if v > 0]
        
        avg_ac = sum(ac_values) / len(ac_values) if ac_values else 70
        avg_pc = sum(pc_values_for_avg) / len(pc_values_for_avg) if pc_values_for_avg else 3
        
        # Check if student is dangerous
        is_dangerous = any(scores.get(f'pc_{i}', 3) == -1 for i in range(11))
        
        # Determine performance level with class-standing-adjusted expectations
        # Higher class standing = higher expectations (stricter evaluation)
        performance_level = self._determine_performance_level_by_class_standing(
            avg_ac=avg_ac,
            avg_pc=avg_pc,
            class_standing=class_standing,
            is_dangerous=is_dangerous
        )
        
        # Use Gemini Flash for AI comment generation with simple prompts (no names to avoid filters)
        if self.gemini_agent:
            try:
                comment = self._generate_comment_with_ai(
                    case_name=case_name,
                    case_code=case_code,
                    case_description=case_description,
                    case_keywords=case_keywords,
                    preceptee_name=preceptee_name,
                    class_standing=class_standing,
                    performance_level=performance_level,
                    avg_ac=avg_ac,
                    avg_pc=avg_pc,
                    is_dangerous=is_dangerous,
                    scores=scores  # Pass scores for detailed breakdown
                )
                print(f"✅ AI-generated comment created for {preceptee_name}")
                return comment, performance_level
            except Exception as e:
                import traceback
                print(f"❌ AI comment generation CRITICAL FAILURE: {e}")
                print(f"❌ Traceback: {traceback.format_exc()}")
                print(f"❌ CANNOT use fallback templates - AI generation is REQUIRED")
                # DO NOT fall back to templates - raise error instead
                raise Exception(f"AI comment generation failed and cannot use fallback templates: {e}")
        else:
            raise Exception(f"Gemini Agent not available - AI generation is REQUIRED, cannot use template fallback")
    
    def _sanitize_content_for_safety_filters(self, text: str) -> str:
        """
        Sanitize content to avoid triggering Gemini safety filters.
        Removes or replaces words that commonly trigger safety filters.
        
        Args:
            text: Text to sanitize
            
        Returns:
            Sanitized text
        """
        if not text:
            return text
        
        # Words that commonly trigger safety filters (especially DANGEROUS_CONTENT)
        # Replace with safer alternatives
        replacements = {
            # Direct safety/harm words
            'dangerous': 'requires attention',
            'danger': 'concern',
            'unsafe': 'requires attention',
            'harmful': 'concerning',
            'harm': 'concern',
            'threat': 'concern',
            'threatening': 'concerning',
            'risky': 'challenging',
            'risk': 'consideration',
            'risks': 'considerations',
            
            # Extreme medical terms (that might trigger filters)
            'death': 'outcome',
            'dying': 'requires support',
            'dead': 'outcome',
            'fatal': 'serious',
            'lethal': 'serious',
            'kill': 'address',
            'killing': 'addressing',
            'mortality': 'outcome',
            'morbid': 'concerning',
            
            # Violence-related
            'violence': 'distress',
            'violent': 'distressed',
            'attack': 'episode',
            'assault': 'episode',
            
            # Other potentially problematic terms
            'critical': 'important',
            'emergency': 'urgent situation',
            'emergent': 'urgent',
            'trauma': 'injury',
            'traumatic': 'challenging',
            'shock': 'response',
            'bleeding': 'hemorrhage',
            'blood loss': 'hemorrhage',
            
            # Keep medical terms but make them less "alarming"
            'complication': 'consideration',
            'complications': 'considerations',
            'adverse': 'unexpected',
            'adverse event': 'unexpected response',
            
            # Additional problematic phrases
            'abrupt change': 'significant change',
            'sudden': 'rapid',
            'collapse': 'decline',
            'failure': 'challenge',
            'fail': 'challenge',
            'failed': 'challenged',
            'catastrophic': 'serious',
            'severe': 'significant',
            'severely': 'significantly',
            'take over': 'assisted with',
            'took over': 'assisted with',
            'taking over': 'assisting with',
            'tumor': 'lesion',
            'tumors': 'lesions',
            'malignancy': 'condition',
            'malignant': 'concerning',
            'cancer': 'condition',
            'cancerous': 'concerning',
            'lung removal': 'lung resection procedure',
            'removal': 'resection',
            'removed': 'resected',
            'remove': 'resect',
            'pneumonectomy': 'lung resection',
            'laparoscopic hysterectomy': 'abdominal surgery',
            'spinal fusion': 'spine surgery',
            'pediatric spinal fusion': 'pediatric spine surgery',
            'scoliosis': 'spinal condition',
            'laparoscopic': 'minimally invasive',
            'thoracotomy': 'chest surgery',
            'lobectomy': 'lung resection',
            'colectomy': 'intestinal surgery',
            'appendectomy': 'abdominal surgery',
            'cholecystectomy': 'abdominal surgery',
            'mastectomy': 'chest surgery',
            'prostatectomy': 'pelvic surgery',
            'nephrectomy': 'kidney surgery',
            'thyroidectomy': 'neck surgery',
            'gastrectomy': 'abdominal surgery',
            'esophagectomy': 'chest surgery',
            'pancreatectomy': 'abdominal surgery',
            'splenectomy': 'abdominal surgery',
            'cystectomy': 'pelvic surgery',
            'hysterectomy': 'abdominal surgery',
            'oophorectomy': 'abdominal surgery',
            'salpingectomy': 'abdominal surgery',
            'tumor removal': 'lesion resection',
            'tumor resection': 'lesion resection',
            'mass removal': 'lesion resection',
            'biopsy': 'tissue sampling',
            'excision': 'removal procedure',
            'stress': 'challenging situations',
            'pressure': 'demanding situations',
            'under stress': 'in challenging situations',
            'under pressure': 'in demanding situations',
            'needs improvement': 'developing skills',
            'needs_improvement': 'developing skills',
            'poor': 'early stage',
            'dangerous': 'requires attention',
        }
        
        # Apply replacements (case-insensitive)
        sanitized = text
        for word, replacement in replacements.items():
            # Replace whole words only (not parts of words)
            pattern = r'\b' + re.escape(word) + r'\b'
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        
        # Also remove any lines that contain certain problematic patterns
        lines = sanitized.split('\n')
        filtered_lines = []
        problematic_patterns = [
            r'\b(abrupt|sudden|collapse|failure|catastrophic|severe|death|dying|dead|fatal|lethal|kill|killing)\b',
            r'\b(violence|violent|attack|assault|harm|danger|threat)\b',
        ]
        
        for line in lines:
            # Skip lines that are too problematic
            skip_line = False
            for pattern in problematic_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    skip_line = True
                    break
            if not skip_line:
                filtered_lines.append(line)
        
        sanitized = '\n'.join(filtered_lines)
        
        # Limit length to avoid very long content that might have hidden triggers
        if len(sanitized) > 2000:
            sanitized = sanitized[:2000] + "... [content truncated]"
        
        return sanitized
    
    def _log_prompt_for_debugging(self, prompt: str, max_length: int = 2000):
        """
        Log prompt content for debugging safety filter issues.
        
        Args:
            prompt: Prompt to log
            max_length: Maximum length to log (to avoid huge logs)
        """
        prompt_preview = prompt[:max_length] + "..." if len(prompt) > max_length else prompt
        print(f"\n{'='*80}")
        print(f"📝 PROMPT BEING SENT TO GEMINI (first {max_length} chars):")
        print(f"{'='*80}")
        print(prompt_preview)
        print(f"{'='*80}\n")
    
    def _generate_comment_with_ai(
        self,
        case_name: str,
        case_code: str,
        case_description: str,
        case_keywords: List[str],
        preceptee_name: str,
        class_standing: int,
        performance_level: str,
        avg_ac: float,
        avg_pc: float,
        is_dangerous: bool,
        scores: Dict[str, int]
    ) -> str:
        """Generate comment using Gemini AI (Vector Search is optional but helpful)."""
        
        # Research the case type using Vector Search (optional - if not available, continue without it)
        # DISABLED: Vector Search content often contains words that trigger safety filters
        # Uncomment below if you want to use Vector Search (but be aware it may cause safety filter blocks)
        case_research = ""
        USE_VECTOR_SEARCH_FOR_COMMENTS = False  # Set to True to enable (may cause safety filter issues)
        
        if USE_VECTOR_SEARCH_FOR_COMMENTS and self.vector_search:
            try:
                # Search for anesthesia considerations for this specific case type
                search_query = f"anesthesia considerations for {case_name} procedure"
                if case_keywords:
                    search_query += f" {' '.join(case_keywords[:3])}"
                
                case_research = self.vector_search.search_for_context(
                    query=search_query,
                    num_results=3
                )
                if case_research:
                    print(f"✅ Found case research for {case_name}")
                    # Sanitize case research VERY aggressively - remove entire sections with problematic words
                    case_research = self._sanitize_content_for_safety_filters(case_research)
                    # If sanitization removed too much (less than 100 chars), skip it entirely
                    if len(case_research.strip()) < 100:
                        print(f"⚠️ Case research too problematic after sanitization, skipping")
                        case_research = ""
            except Exception as e:
                print(f"⚠️ Vector search failed: {e}")
                case_research = ""
        else:
            print(f"⚠️ Vector Search not available - proceeding without case research")
        
        # Sanitize case description and keywords before using in prompt
        case_description = self._sanitize_content_for_safety_filters(case_description or '')
        sanitized_keywords = [self._sanitize_content_for_safety_filters(kw) for kw in case_keywords] if case_keywords else []
        
        # Build prompt for Gemini
        year_names = {1: "first-year", 2: "second-year", 3: "third-year", 4: "fourth-year"}
        year_name = year_names.get(class_standing, f"year {class_standing}")
        
        # Context for expectations based on class standing
        expectations_context = {
            1: "Brand new to clinical rotations - learning basics, seeking supervision appropriately",
            2: "Building clinical skills - should show progression and independence",
            3: "Close to independent practitioner - should demonstrate near-independent decision-making and competence",
            4: "Should be independent practitioner - near graduation, expected to manage cases independently with minimal supervision"
        }
        expectation = expectations_context.get(class_standing, "Expected level")
        
        # Build metric context for the prompt
        ac_metrics_list = "\n".join([f"- {key}: {label}" for key, label in self.AC_METRICS.items()])
        pc_metrics_list = "\n".join([f"- {key}: {label}" for key, label in self.PC_METRICS.items()])
        
        # Get specific scores breakdown for context
        score_breakdown = []
        for i in range(13):
            ac_key = f"ac_{i}"
            score = scores.get(ac_key, 0)
            metric_name = self.AC_METRICS.get(ac_key, "Unknown")
            score_breakdown.append(f"{metric_name}: {score}/100")
        
        for i in range(11):
            pc_key = f"pc_{i}"
            score = scores.get(pc_key, 0)
            metric_name = self.PC_METRICS.get(pc_key, "Unknown")
            if score == -1:
                score_breakdown.append(f"{metric_name}: Performance Concern (-1)")
            elif score == 0:
                score_breakdown.append(f"{metric_name}: Not Applicable (0)")
            else:
                score_breakdown.append(f"{metric_name}: {score}/4 stars")
        
        # Get example comments and focus areas for reference
        # Try to find examples that match the case type, otherwise use random examples
        matching_examples = []
        other_examples = []
        
        if self.comment_examples:
            case_name_lower = case_name.lower()
            for ex in self.comment_examples:
                ex_case = ex.get('case', '').lower()
                # Check if example case matches current case (partial match)
                if ex_case and any(keyword in case_name_lower for keyword in ex_case.split()):
                    matching_examples.append(ex)
                elif ex_case and any(case_keyword.lower() in ex_case for case_keyword in case_keywords[:3]):
                    matching_examples.append(ex)
                else:
                    other_examples.append(ex)
        
        # Prefer matching examples, but include some random ones too
        examples_to_use = matching_examples[:2]  # Up to 2 matching examples
        remaining_slots = 3 - len(examples_to_use)
        if remaining_slots > 0 and other_examples:
            examples_to_use.extend(random.sample(other_examples, min(remaining_slots, len(other_examples))))
        
        # OPTION: Disable examples if they're causing filter issues - set to False to test
        USE_EXAMPLES = False  # DISABLED: Examples containing "take over" and other phrases trigger filters
        
        examples_text = ""
        if USE_EXAMPLES and examples_to_use:
            example_list = []
            for i, ex in enumerate(examples_to_use, 1):
                ex_case = ex.get('case', 'Unknown case')
                comment = ex.get('comment', '')
                focus_areas = ex.get('focus_areas', '')
                # Sanitize example comments and focus areas to avoid triggering filters
                comment = self._sanitize_content_for_safety_filters(comment)
                focus_areas = self._sanitize_content_for_safety_filters(focus_areas) if focus_areas else ''
                example_list.append(f"Example {i} (Case: {ex_case}):\nComment: {comment}\nFocus Areas: {focus_areas if focus_areas else '(empty)'}")
            examples_text = "\n\n" + "="*70 + "\nREAL PRECEPTOR EVALUATION EXAMPLES (use these as style reference):\n" + "="*70 + "\n\n" + "\n\n".join(example_list)
        
        # Sanitize example text as well before adding to prompt
        examples_text = self._sanitize_content_for_safety_filters(examples_text)
        
        # Limit case research length and sanitize aggressively
        if case_research:
            # Sanitize first, then limit length
            case_research = self._sanitize_content_for_safety_filters(case_research)
            # Further limit to avoid too much content
            if len(case_research) > 1500:
                case_research = case_research[:1500] + "... [content truncated for safety]"

        # Sanitize case_name for use in prompt
        sanitized_case_name = self._sanitize_content_for_safety_filters(case_name)

        # Use contextual prompt - brief and concise like real examples
        prompt = f"""Write a brief evaluation comment for a student during a {sanitized_case_name} case. 

Keep it to 1-3 sentences. Be specific about what you observed - their preparation, technical skills, how they handled challenges, or their response to instruction. Write in past tense, conversational style like a real preceptor note. No options or templates - just write the comment directly."""

        try:
            if not GEMINI_TYPES_AVAILABLE:
                raise Exception("Gemini API types not available - check imports")

            # Generate comment using Gemini - Use list format for safety settings (proven to work)
            # NOTE: Do NOT pass generation_config - it causes safety settings to be ignored!
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]

            # Retry logic - Never fall back to templates, keep trying with AI
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Log prompt for debugging (only on first attempt to avoid spam)
                    if attempt == 0:
                        self._log_prompt_for_debugging(prompt, max_length=3000)
                    
                    # Don't pass generation_config - it causes safety settings to be ignored!
                    response = self.gemini_agent.model.generate_content(
                        prompt,
                        safety_settings=safety_settings
                    )
                    
                                            # Check if response was blocked by safety filters BEFORE accessing response.text
                    if response.candidates and len(response.candidates) > 0:
                        candidate = response.candidates[0]
                        finish_reason = candidate.finish_reason
                        print(f"Finish reason: {finish_reason}")                        
                        # Check finish_reason - handle both enum and integer values
                        # finish_reason can be an enum, integer (2 = SAFETY, 3 = RECITATION), or string
                        is_safety = (
                            finish_reason == Candidate.FinishReason.SAFETY or
                            finish_reason == 2 or
                            str(finish_reason) == "SAFETY" or
                            (hasattr(finish_reason, 'value') and finish_reason.value == 2)
                        )
                        
                        if is_safety:
                            print(f"⚠️ Comment generation blocked by safety filters (attempt {attempt + 1}/{max_retries})")
                            
                            # Log the safety ratings to debug
                            if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                                print(f"   Safety ratings:")
                                for rating in candidate.safety_ratings:
                                    category = getattr(rating, 'category', 'unknown')
                                    probability = getattr(rating, 'probability', 'unknown')
                                    print(f"     {category}: {probability}")
                            
                            if attempt < max_retries - 1:
                                continue
                            else:
                                raise Exception(f"AI content blocked by safety filters after {max_retries} attempts - cannot use fallback templates")
                        
                        # Check for RECITATION block
                        is_recitation = (
                            finish_reason == Candidate.FinishReason.RECITATION or
                            finish_reason == 3 or
                            str(finish_reason) == "RECITATION" or
                            (hasattr(finish_reason, 'value') and finish_reason.value == 3)
                        )
                        
                        if is_recitation:
                            if attempt < max_retries - 1:
                                print(f"⚠️ Comment generation blocked by recitation filter (attempt {attempt + 1}/{max_retries}), retrying...")
                                prompt = prompt + "\n\nGenerate original content based on the provided information, not copying from sources."
                                continue
                            else:
                                raise Exception(f"Content blocked by recitation filter after {max_retries} attempts")
                    
                    # Only access response.text AFTER we've confirmed it's not blocked
                    if not response.candidates or len(response.candidates) == 0:
                        if attempt < max_retries - 1:
                            print(f"⚠️ No candidates in response (attempt {attempt + 1}/{max_retries}), retrying...")
                            continue
                        else:
                            raise Exception("No candidates returned from Gemini after retries")
                    
                    # Now safe to access response.text
                    if not response.text:
                        if attempt < max_retries - 1:
                            print(f"⚠️ Empty response (attempt {attempt + 1}/{max_retries}), retrying...")
                            continue
                        else:
                            raise Exception("Empty response from Gemini after retries")
                    
                    # Success!
                    comment = response.text.strip()

                    # Post-process: Add student name and case name AFTER generation (to avoid filter triggers)
                    original_length = len(comment)

                    # Add student name naturally into the comment
                    if preceptee_name:
                        # Replace generic references with student name
                        comment = comment.replace("a student", preceptee_name)
                        comment = comment.replace("the student", preceptee_name)
                        comment = comment.replace("students", f"students like {preceptee_name}")
                        comment = comment.replace("a trainee", preceptee_name)
                        comment = comment.replace("the trainee", preceptee_name)
                        
                        # If no student reference found, add at beginning
                        if preceptee_name not in comment:
                            comment = f"{preceptee_name} participated in a {sanitized_case_name} case. {comment}"
                    
                    # Add case name context if not already present
                    if sanitized_case_name and sanitized_case_name.lower() not in comment.lower():
                        comment = comment.replace("clinical case", f"{sanitized_case_name} case")
                        comment = comment.replace("the case", f"the {sanitized_case_name} case")
                        comment = comment.replace("a case", f"a {sanitized_case_name} case")
                    
                    # Limit comment length - keep it concise like real examples (max 500 chars)
                    if len(comment) > 500:
                        # Trim to reasonable length (keep first ~500 chars and add ellipsis if needed)
                        comment = comment[:500].rsplit('.', 1)[0] + '.'
                        print(f"🔄 Comment trimmed to {len(comment)} characters for conciseness")
                    
                    # Clean up the comment - remove any template language
                    comment = comment.replace('"', '').strip()
                    # Remove common template prefixes
                    prefixes_to_remove = [
                        'Comment:',
                        'Evaluation:',
                        'Here are a few options',
                        'Choose the one that best fits',
                        'Option 1',
                        'Option 2',
                        'Option 3',
                        '**Option',
                        '**',
                    ]
                    for prefix in prefixes_to_remove:
                        if comment.startswith(prefix):
                            # Remove prefix and any following text until the actual comment starts
                            lines = comment.split('\n')
                            # Find first line that doesn't start with common prefixes
                            for i, line in enumerate(lines):
                                if not any(line.strip().startswith(p) for p in ['**', 'Option', 'Here are', 'Choose']):
                                    comment = '\n'.join(lines[i:]).strip()
                                    break
                    
                    # Remove markdown formatting
                    comment = re.sub(r'\*\*([^*]+)\*\*', r'\1', comment)  # Remove **bold**
                    comment = re.sub(r'^\d+\.\s*', '', comment, flags=re.MULTILINE)  # Remove numbered lists
                    comment = comment.strip()
                    
                    # If still contains multiple options, take the first actual comment
                    if 'Option' in comment or '**Option' in comment:
                        # Split by options and take first real content
                        parts = re.split(r'Option \d+|^\*\*', comment, flags=re.MULTILINE)
                        for part in parts:
                            part = part.strip()
                            if part and len(part) > 50 and not part.startswith('('):
                                comment = part
                                break
                    
                    return comment
                    
                except TransportError as e:
                    print(f"⚠️ Network error (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        sleep_time = 2 ** attempt  # Exponential backoff
                        print(f"   Retrying in {sleep_time} seconds...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        raise Exception(f"Network error after {max_retries} attempts: {e}")
                
                except AttributeError as e:
                    # This catches the FinishReason bug and other API compatibility issues
                    print(f"❌ API compatibility error: {e}")
                    raise Exception(f"Gemini API version mismatch: {e}. Check that google-generativeai package is up to date.")
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"⚠️ Generation attempt {attempt + 1} failed: {e}, retrying...")
                        continue
                    else:
                        print(f"⚠️ All {max_retries} attempts failed")
                        raise Exception(f"Failed to generate AI comment after {max_retries} attempts: {e}")
            
        except Exception as e:
            print(f"⚠️ Gemini comment generation error: {e}")
            raise
    
    def _generate_template_comment(
        self,
        case_name: str,
        case_code: str,
        preceptee_name: str,
        class_standing: int,
        performance_level: str,
        case_keywords: List[str],
        avg_ac: float,
        avg_pc: float,
        scores: Dict[str, int]
    ) -> str:
        """Template-based comment generation - bypasses Gemini safety filters."""
        year_names = {1: "first-year", 2: "second-year", 3: "third-year", 4: "fourth-year"}
        year_name = year_names.get(class_standing, f"year {class_standing}")
        
        # Get case type description from keywords
        case_type_desc = ", ".join(case_keywords[:3]) if case_keywords else "anesthesia case"
        
        # Build narrative comment based on performance level
        if performance_level == "excellent":
            openings = [
                f"I had the pleasure of precepting {preceptee_name} during a {case_name} case.",
                f"During a recent {case_name} case, I observed {preceptee_name} demonstrating exceptional clinical skills.",
                f"{preceptee_name} participated in a {case_name} case and showed outstanding performance.",
            ]
            middles = [
                f"As a {year_name} student, {preceptee_name} demonstrated excellent preparation and understanding of {case_type_desc} procedures.",
                f"{preceptee_name} showed exceptional attention to detail, asking thoughtful questions throughout the case.",
                f"The student handled the {case_name} case with confidence and demonstrated strong clinical judgment.",
                f"{preceptee_name} was well-prepared for this case and showed excellent technical skills.",
            ]
            endings = [
                "This was impressive work for a student at this level. Continue seeking challenging cases.",
                "Well done - keep up the excellent work and continue building on these skills.",
                "Ready for more complex cases. Excellent performance.",
            ]
        elif performance_level == "good":
            openings = [
                f"I precepted {preceptee_name} during a {case_name} case.",
                f"During a {case_name} case, I observed {preceptee_name} showing strong clinical competency.",
                f"{preceptee_name} participated in a {case_name} case and performed well.",
            ]
            middles = [
                f"As a {year_name} student, {preceptee_name} demonstrated good understanding of {case_type_desc} procedures.",
                f"{preceptee_name} showed appropriate preparation and asked relevant questions during the case.",
                f"The student handled the {case_name} case competently and responded well to guidance.",
                f"{preceptee_name} was prepared for this case and demonstrated solid clinical skills.",
            ]
            endings = [
                "Good progress - continue building on these skills.",
                "Continue seeking hands-on practice with similar cases to further develop proficiency.",
                "Well done. Keep up the good work.",
            ]
        elif performance_level == "satisfactory":
            openings = [
                f"I observed {preceptee_name} during a {case_name} case.",
                f"During a recent {case_name} case, {preceptee_name} showed appropriate clinical skills.",
                f"{preceptee_name} participated in a {case_name} case.",
            ]
            middles = [
                f"As a {year_name} student, {preceptee_name} demonstrated basic understanding of {case_type_desc} procedures.",
                f"{preceptee_name} showed adequate preparation and asked questions when needed.",
                f"The student handled the {case_name} case with appropriate supervision.",
                f"{preceptee_name} participated appropriately in this case and is building foundational skills.",
            ]
            endings = [
                f"Continue to seek hands-on practice with {case_name} cases to build confidence.",
                f"Keep reviewing {case_name} anesthesia considerations and seek additional practice.",
                "Continue building foundational skills through practice.",
            ]
        elif performance_level == "needs_improvement":
            openings = [
                f"I precepted {preceptee_name} during a {case_name} case.",
                f"During a {case_name} case, {preceptee_name} showed areas for continued growth.",
                f"{preceptee_name} participated in a {case_name} case.",
            ]
            middles = [
                f"As a {year_name} student, {preceptee_name} demonstrated some understanding but needs further development in {case_type_desc} procedures.",
                f"{preceptee_name} showed limited preparation and would benefit from more case-specific study.",
                f"The student handled the {case_name} case but required frequent guidance and support.",
                f"{preceptee_name} participated in this case but needs more practice to build confidence.",
            ]
            endings = [
                f"Focus on {case_name} case preparation before the next similar case.",
                f"Review {case_name} anesthesia principles and seek additional practice opportunities.",
                "Continue to build foundational knowledge and seek supervision when needed.",
            ]
        elif performance_level == "poor":
            openings = [
                f"I precepted {preceptee_name} during a {case_name} case.",
                f"During a {case_name} case, {preceptee_name} demonstrated significant challenges.",
            ]
            middles = [
                f"As a {year_name} student, {preceptee_name} struggled with {case_type_desc} procedures.",
                f"{preceptee_name} showed insufficient preparation and required extensive guidance throughout the case.",
                f"The student had difficulty managing the {case_name} case and needs additional training.",
            ]
            endings = [
                f"Requires intensive remediation before managing {case_name} cases independently.",
                "Needs significant additional study and practice before continuing with similar cases.",
            ]
        else:  # dangerous
            openings = [
                f"⚠️ SAFETY CONCERN: I precepted {preceptee_name} during a {case_name} case.",
            ]
            middles = [
                f"{preceptee_name} demonstrated concerning safety behaviors during the {case_name} case that require immediate attention.",
                f"The student showed serious safety lapses during {case_name} that cannot be overlooked.",
            ]
            endings = [
                "REQUIRED ACTION: This student must undergo safety remediation before continuing clinical rotations.",
            ]
        
        # Build the comment
        opening = random.choice(openings)
        middle = random.choice(middles)
        ending = random.choice(endings)
        
        comment = f"{opening} {middle} {ending}"
        
        # Ensure minimum length (200-300 words target)
        if len(comment) < 200:
            # Add more detail about the case
            additional_detail = f" The {case_name} case involved {case_type_desc} considerations, and {preceptee_name} navigated the case with the expected level of supervision for a {year_name} student."
            comment = comment + additional_detail
        
        return comment.strip()
    
    def _generate_focus_areas(
        self,
        case: Dict[str, Any],
        scores: Dict[str, int],
        class_standing: int,
        performance_level: str,
        preceptee_name: Optional[str] = None
    ) -> str:
        """
        Generate focus areas - actionable guidance for future learning and improvement.
        These are areas the student should practice or learn more about for future clinical rotations.
        
        Args:
            case: Case dictionary
            scores: All evaluation scores
            class_standing: Student's year (1-4)
            performance_level: Determined performance level
            
        Returns:
            Focus areas string with actionable guidance, or empty string if nothing meaningful to add
        """
        case_name = case.get('name', 'this case')
        case_keywords = case.get('keywords', [])
        
        # Identify areas that need improvement based on low scores
        weak_areas = []
        for i in range(13):
            ac_key = f"ac_{i}"
            score = scores.get(ac_key, 0)
            metric_name = self.AC_METRICS.get(ac_key, "Unknown")
            # Identify areas scoring below 70
            if score < 70:
                weak_areas.append({
                    "metric": metric_name,
                    "score": score,
                    "key": ac_key
                })
        
        # Identify behavioral areas that need improvement
        weak_behaviors = []
        for i in range(11):
            pc_key = f"pc_{i}"
            score = scores.get(pc_key, 0)
            metric_name = self.PC_METRICS.get(pc_key, "Unknown")
            # Identify areas scoring below 3 stars (and not 0 or -1)
            if score > 0 and score < 3:
                weak_behaviors.append({
                    "metric": metric_name,
                    "score": score,
                    "key": pc_key
                })
        
        # Sometimes leave focus areas blank (if performance is excellent and no weak areas)
        if performance_level in ["excellent", "good"] and not weak_areas and not weak_behaviors:
            # 30% chance to leave blank if no issues
            if random.random() < 0.30:
                return ""
        
        # Use Gemini Flash for AI focus areas generation with simple prompts (no names)
        if self.gemini_agent:
            try:
                focus_areas = self._generate_focus_areas_with_ai(
                    case_name=case_name,
                    case_keywords=case_keywords,
                    weak_areas=weak_areas,
                    weak_behaviors=weak_behaviors,
                    class_standing=class_standing,
                    performance_level=performance_level,
                    preceptee_name=preceptee_name,
                    use_vector_search=False  # Don't use vector search for now
                )
                # Only return if we got valid content
                if focus_areas and len(focus_areas.strip()) > 0:
                    return focus_areas
                else:
                    print(f"⚠️ Focus areas generation returned empty, continuing without focus areas")
                    return ""
            except Exception as e:
                print(f"⚠️ AI focus areas generation failed: {e}")
                print(f"⚠️ Continuing evaluation without focus areas (returning empty string)")
                # Return empty string instead of failing entire evaluation
                return ""
        else:
            raise Exception(f"Gemini Agent not available - AI generation is REQUIRED for focus areas")
    
    def _generate_template_focus_areas(
        self,
        case_name: str,
        case_keywords: List[str],
        weak_areas: List[Dict[str, Any]],
        weak_behaviors: List[Dict[str, Any]],
        class_standing: int,
        performance_level: str,
        preceptee_name: Optional[str] = None
    ) -> str:
        """Template-based focus areas generation - bypasses Gemini safety filters."""
        year_names = {1: "first-year", 2: "second-year", 3: "third-year", 4: "fourth-year"}
        year_name = year_names.get(class_standing, f"year {class_standing}")
        
        focus_items = []
        
        # Add case-specific focus areas
        case_type_desc = ", ".join(case_keywords[:2]) if case_keywords else "anesthesia"
        
        if performance_level in ["excellent", "good"]:
            # Advanced focus areas for high performers
            case_focuses = [
                f"Continue to seek opportunities for complex {case_name} cases to further develop expertise.",
                f"Consider exploring advanced techniques in {case_type_desc} procedures.",
                f"Ready to mentor peers on {case_name} case management.",
            ]
            focus_items.append(random.choice(case_focuses))
        elif performance_level == "satisfactory":
            # Standard focus areas for satisfactory performance
            case_focuses = [
                f"Continue practicing {case_name} cases to build confidence and proficiency.",
                f"Review {case_type_desc} anesthesia principles and seek additional hands-on experience.",
                f"Focus on improving case preparation and planning for {case_name} procedures.",
            ]
            focus_items.append(random.choice(case_focuses))
        else:
            # Improvement-focused areas for lower performance
            case_focuses = [
                f"Review {case_name} case-specific anesthesia considerations before next similar case.",
                f"Study {case_type_desc} procedures and seek additional supervised practice.",
                f"Focus on improving preparation and understanding of {case_name} case management.",
            ]
            focus_items.append(random.choice(case_focuses))
        
        # Add focus areas based on weak AC metrics
        if weak_areas:
            weak_metric_names = [area['metric'] for area in weak_areas[:3]]  # Top 3 weak areas
            
            for metric_name in weak_metric_names:
                if "Airway" in metric_name:
                    focus_items.append(f"Practice airway management techniques and equipment preparation.")
                elif "Medication" in metric_name:
                    focus_items.append(f"Review medication administration protocols and dosing calculations.")
                elif "Pre-op" in metric_name or "Assessment" in metric_name:
                    focus_items.append(f"Improve pre-operative assessment skills and patient evaluation.")
                elif "Ventilatory" in metric_name or "Ventilation" in metric_name:
                    focus_items.append(f"Focus on ventilatory management and understanding of ventilation modes.")
                elif "Induction" in metric_name:
                    focus_items.append(f"Practice anesthesia induction techniques and patient monitoring.")
                elif "Emergence" in metric_name:
                    focus_items.append(f"Review emergence techniques and extubation criteria.")
                elif "Regional" in metric_name:
                    focus_items.append(f"Study regional anesthesia techniques and nerve anatomy.")
                elif "Positioning" in metric_name:
                    focus_items.append(f"Review patient positioning considerations and safety protocols.")
                elif "Room Readiness" in metric_name:
                    focus_items.append(f"Focus on procedural room setup and equipment preparation.")
                elif "Care Transfer" in metric_name or "Transfer" in metric_name:
                    focus_items.append(f"Practice safe patient care transfer and handoff communication.")
                else:
                    focus_items.append(f"Continue developing skills in {metric_name.lower()}.")
        
        # Add focus areas based on weak behavioral metrics
        if weak_behaviors:
            weak_behavior_names = [behavior['metric'] for behavior in weak_behaviors[:2]]  # Top 2 weak behaviors
            
            for behavior_name in weak_behavior_names:
                if "Instruction" in behavior_name or "Receptive" in behavior_name:
                    focus_items.append(f"Work on being more receptive to feedback and incorporating preceptor guidance.")
                elif "Communication" in behavior_name:
                    focus_items.append(f"Focus on improving communication with the team and preceptor.")
                elif "Troubleshoot" in behavior_name:
                    focus_items.append(f"Develop problem-solving skills and critical thinking in clinical situations.")
                elif "Calm" in behavior_name or "Professional" in behavior_name:
                    focus_items.append(f"Practice maintaining composure and professional demeanor during cases.")
                elif "Limitations" in behavior_name:
                    focus_items.append(f"Work on recognizing when to ask for help and understanding personal limitations.")
                elif "Accountable" in behavior_name:
                    focus_items.append(f"Focus on taking accountability for clinical decisions and patient care.")
                elif "Documentation" in behavior_name:
                    focus_items.append(f"Improve documentation accuracy and completeness.")
                elif "Universal Precautions" in behavior_name:
                    focus_items.append(f"Review and practice universal precautions and infection control protocols.")
                else:
                    focus_items.append(f"Continue developing {behavior_name.lower()} skills.")
        
        # If no specific weak areas, add general learning focus
        if not weak_areas and not weak_behaviors:
            general_focuses = [
                f"Continue building clinical experience with {case_type_desc} procedures.",
                f"Seek opportunities to observe and practice {case_name} cases.",
                f"Review anesthesia principles relevant to {case_name} procedures.",
            ]
            focus_items.append(random.choice(general_focuses))
        
        # Format as bullet points
        if focus_items:
            # Limit to 3-5 focus areas
            selected_items = focus_items[:5]
            focus_text = "\n".join([f"• {item}" for item in selected_items])
            return focus_text
        
        return ""
    
    def _generate_focus_areas_with_ai(
        self,
        case_name: str,
        case_keywords: List[str],
        weak_areas: List[Dict[str, Any]],
        weak_behaviors: List[Dict[str, Any]],
        class_standing: int,
        performance_level: str,
        preceptee_name: Optional[str] = None,
        use_vector_search: bool = True
    ) -> str:
        """Generate focus areas using AI with simple prompts (no names to avoid filters)."""
        
        # Extract weak areas and behaviors for prompt
        weak_areas_list = [area['metric'] for area in weak_areas[:3]]
        weak_behaviors_list = [behavior['metric'] for behavior in weak_behaviors[:2]]
        
        # Build prompt - brief and case-specific like real examples
        case_context = f" for a {case_name} case" if case_name else ""
        if weak_areas_list:
            areas_context = f" Focus on: {', '.join(weak_areas_list[:2])}"
        else:
            areas_context = ""
        
        prompt = f"List 2-3 very brief learning focus areas{case_context}{areas_context}. Each should be just a short phrase (1-10 words max) like 'Airway management with DL' or 'Spinal technique'. No explanations or descriptions."
        
        try:
            if not GEMINI_TYPES_AVAILABLE:
                raise Exception("Gemini API types not available - check imports")
            
            # Safety settings using list-of-dicts format (compatible with Gemini API)
            # NOTE: Do NOT pass generation_config - it causes safety settings to be ignored!
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]

            # Retry logic - same as comments (3 attempts)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Don't pass generation_config - it causes safety settings to be ignored!
                    response = self.gemini_agent.model.generate_content(
                        prompt,
                        safety_settings=safety_settings
                    )
                    
                    # Check finish_reason BEFORE accessing response.text (same as comments)
                    if response.candidates and len(response.candidates) > 0:
                        candidate = response.candidates[0]
                        finish_reason = candidate.finish_reason
                        
                        # Check if blocked - handle both enum and integer values
                        is_safety = (
                            finish_reason == Candidate.FinishReason.SAFETY or
                            finish_reason == 2 or
                            str(finish_reason) == "SAFETY" or
                            (hasattr(finish_reason, 'value') and finish_reason.value == 2)
                        )
                        
                        if is_safety:
                            if attempt < max_retries - 1:
                                print(f"⚠️ Focus areas blocked by safety filters (attempt {attempt + 1}/{max_retries}), retrying...")
                                continue
                            else:
                                print(f"⚠️ Focus areas blocked by safety filters after {max_retries} attempts")
                                return ""
                    
                    # Check for RECITATION block
                    is_recitation = (
                        finish_reason == Candidate.FinishReason.RECITATION or
                        finish_reason == 3 or
                        str(finish_reason) == "RECITATION" or
                        (hasattr(finish_reason, 'value') and finish_reason.value == 3)
                    )
                    
                    if is_recitation:
                        if attempt < max_retries - 1:
                            print(f"⚠️ Focus areas blocked by recitation filter (attempt {attempt + 1}/{max_retries}), retrying...")
                            prompt = prompt + "\n\nGenerate original content."
                            continue
                        else:
                            print(f"⚠️ Focus areas blocked by recitation filter after {max_retries} attempts")
                            return ""
                    
                    # Check if response.text is available
                    if not response.text:
                        if attempt < max_retries - 1:
                            print(f"⚠️ Empty response (attempt {attempt + 1}/{max_retries}), retrying...")
                            continue
                        else:
                            print(f"⚠️ Empty response after {max_retries} attempts")
                            return ""
                    
                    # Success!
                    focus_areas = response.text.strip()
                    
                    # Format as bullet points and clean up
                    if not focus_areas.startswith("•") and not focus_areas.startswith("-"):
                        lines = focus_areas.split('\n')
                        filtered_lines = []
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue
                            # Remove markdown formatting
                            line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)  # Remove **bold**
                            line = re.sub(r'^\d+\.\s*', '', line)  # Remove "1. "
                            line = re.sub(r'^\*\s*', '', line)  # Remove leading "* "
                            line = re.sub(r'^-\s*', '', line)  # Remove leading "- "
                            # Remove verbose prefixes
                            line = re.sub(r'^.*?:\s*', '', line)  # Remove "Title: " prefixes
                            # Skip lines that are too long or are explanations
                            if line and len(line) < 80 and not line.startswith('Here are') and not line.startswith('Focus:') and not line.startswith('List'):
                                # Further trim if still too long - keep only first phrase/sentence
                                if len(line) > 80:
                                    # Take first sentence or first 80 chars
                                    line = line.split('.')[0].strip()
                                    if len(line) > 80:
                                        line = line[:80].rsplit(',', 1)[0].strip()
                                filtered_lines.append(line)
                        focus_areas = '\n'.join([f"• {line}" if not line.startswith("•") else line for line in filtered_lines[:3]])  # Max 3 items
                    
                    # Limit total length - keep it concise (max 200 chars for 2-3 short items)
                    if len(focus_areas) > 200:
                        # Keep first few bullet points that fit
                        lines = focus_areas.split('\n')
                        result = []
                        total_len = 0
                        for line in lines:
                            if total_len + len(line) < 200:
                                result.append(line)
                                total_len += len(line) + 1
                            else:
                                break
                        focus_areas = '\n'.join(result)
                    
                    print(f"✅ Focus areas generated: {len(focus_areas)} chars")
                    return focus_areas
                    
                except ValueError as e:
                    # response.text throws ValueError when finish_reason is SAFETY or RECITATION
                    if attempt < max_retries - 1:
                        print(f"⚠️ ValueError accessing response.text (attempt {attempt + 1}/{max_retries}), retrying...")
                        continue
                    else:
                        print(f"⚠️ ValueError accessing response.text after {max_retries} attempts: {e}")
                        return ""
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"⚠️ Focus areas generation error (attempt {attempt + 1}/{max_retries}): {e}")
                        continue
                    else:
                        print(f"⚠️ Focus areas generation error after {max_retries} attempts: {e}")
                        return ""
            
            return ""
            
        except Exception as e:
            print(f"⚠️ Focus areas generation error: {e}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()[:500]}")
            return ""
    
    def _determine_performance_level_by_class_standing(
        self,
        avg_ac: float,
        avg_pc: float,
        class_standing: int,
        is_dangerous: bool
    ) -> str:
        """
        Determine performance level with adjusted expectations based on class standing.
        Higher class standing students have stricter evaluation criteria.
        
        Args:
            avg_ac: Average AC score
            avg_pc: Average PC score
            class_standing: Student's year (1-4)
            is_dangerous: Whether student has any dangerous flags
            
        Returns:
            Performance level string
        """
        if is_dangerous:
            return "dangerous"
        
        # Class standing 1 (Brand new to clinical rotations)
        # More lenient - students are learning basics
        if class_standing == 1:
            if avg_ac >= 85 and avg_pc >= 3.5:
                return "excellent"
            elif avg_ac >= 70 and avg_pc >= 3.0:
                return "good"
            elif avg_ac >= 50 and avg_pc >= 2.5:
                return "satisfactory"
            elif avg_ac >= 30:
                return "needs_improvement"
            else:
                return "poor"
        
        # Class standing 2 (Second year)
        # Moderate expectations - building skills
        elif class_standing == 2:
            if avg_ac >= 90 and avg_pc >= 3.5:
                return "excellent"
            elif avg_ac >= 80 and avg_pc >= 3.0:
                return "good"
            elif avg_ac >= 65 and avg_pc >= 2.5:
                return "satisfactory"
            elif avg_ac >= 45:
                return "needs_improvement"
            else:
                return "poor"
        
        # Class standing 3 (Close to independent practitioner)
        # Stricter expectations - should be near independent level
        elif class_standing == 3:
            if avg_ac >= 95 and avg_pc >= 3.7:
                return "excellent"
            elif avg_ac >= 85 and avg_pc >= 3.3:
                return "good"
            elif avg_ac >= 75 and avg_pc >= 3.0:
                return "satisfactory"
            elif avg_ac >= 60:
                return "needs_improvement"
            else:
                return "poor"
        
        # Class standing 4 (Should be independent practitioner)
        # Strictest expectations - near graduation, should be independent
        elif class_standing == 4:
            if avg_ac >= 98 and avg_pc >= 3.8:
                return "excellent"
            elif avg_ac >= 90 and avg_pc >= 3.5:
                return "good"
            elif avg_ac >= 80 and avg_pc >= 3.2:
                return "satisfactory"
            elif avg_ac >= 70:
                return "needs_improvement"
            else:
                return "poor"
        
        # Fallback (shouldn't happen, but handle gracefully)
        else:
            if avg_ac >= 90 and avg_pc >= 3.5:
                return "excellent"
            elif avg_ac >= 80 and avg_pc >= 3.0:
                return "good"
            elif avg_ac >= 70 and avg_pc >= 2.5:
                return "satisfactory"
            elif avg_ac >= 50:
                return "needs_improvement"
            else:
                return "poor"
    
    def _generate_random_string(self, length: int = 20) -> str:
        """Generate a random alphanumeric string"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    
    def _generate_random_email(self, name: str) -> str:
        """Generate a random email from a name"""
        domains = ["test.net", "example.com", "demo.org", "mail.com", "testmail.com"]
        name_lower = name.lower().replace(" ", "")
        return f"{name_lower}{random.randint(100, 999)}@{random.choice(domains)}"
    
    def _generate_random_phone(self) -> str:
        """Generate a random phone number"""
        return f"{random.randint(100, 999)}{random.randint(100, 999)}{random.randint(1000, 9999)}"
    
    def _generate_geopoint(self, site: Optional[Dict[str, Any]] = None) -> GeoPoint:
        """
        Generate a geopoint from site location or random US coordinates.
        
        Args:
            site: Optional site dictionary with city/state information
        
        Returns:
            GeoPoint with coordinates
        """
        if site:
            # Try to use site location if available
            city = site.get('city', '')
            state = site.get('state', '')
            
            # Approximate coordinates for common WA cities (sites.json uses WA state)
            # This is a simplified mapping - in production you might use a geocoding service
            wa_city_coords = {
                'MORTON': (46.5586, -122.2750),
                'FRIDAY HARBOR': (48.5347, -123.0171),
                'VANCOUVER': (45.6387, -122.6615),
                'CENTRALIA': (46.7162, -122.9543),
                'ABERDEEN': (46.9754, -123.8157),
                'MONROE': (47.8553, -121.9810),
                'RITZVILLE': (47.1267, -118.3798),
                'REDMOND': (47.6740, -122.1215),
                'SNOQUALMIE': (47.5292, -121.8255),
                'SPOKANE': (47.6588, -117.4260),
                'CHEWELAH': (48.2807, -117.7150),
                'COVINGTON': (47.3582, -122.1221),
                'PUYALLUP': (47.1854, -122.2929),
                'KETCHIKAN': (55.3422, -131.6461),
            }
            
            city_upper = city.upper()
            if city_upper in wa_city_coords:
                lat, lon = wa_city_coords[city_upper]
                # Add small random offset to avoid exact duplicates
                lat += random.uniform(-0.01, 0.01)
                lon += random.uniform(-0.01, 0.01)
                return GeoPoint(lat, lon)
        
        # Fallback to random coordinates in US (roughly)
        latitude = random.uniform(25.0, 49.0)
        longitude = random.uniform(-125.0, -66.0)
        return GeoPoint(latitude, longitude)
    
    def _generate_ac_scores_by_class_standing(self, class_standing: int) -> Dict[str, int]:
        """
        Generate AC scores based on class standing.
        
        Args:
            class_standing: 1-4 (student's year)
            
        Returns:
            Dictionary of AC scores (ac_0 through ac_12)
        """
        # Valid AC score options (increments of 10)
        all_options = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        
        # Define score ranges by class standing
        # Higher class standing (year) = better scores
        if class_standing == 1:
            # First year: 0-40 (lower scores for beginners)
            valid_options = [0, 10, 20, 30, 40]
        elif class_standing == 2:
            # Second year: 40-80 (medium scores)
            valid_options = [40, 50, 60, 70, 80]
        elif class_standing == 3:
            # Third year: 80-100 (higher scores)
            valid_options = [80, 90, 100]
        elif class_standing == 4:
            # Fourth year: 80-100 (highest scores for most experienced)
            valid_options = [80, 90, 100]
        else:
            # Fallback: use all options
            valid_options = all_options
        
        # Generate scores for all 13 AC fields
        ac_scores = {}
        for i in range(13):
            ac_scores[f"ac_{i}"] = random.choice(valid_options)
        
        return ac_scores
    
    def _is_pc_metric_applicable(self, pc_index: int, case: Dict[str, Any]) -> bool:
        """
        Determine if a PC metric is applicable to the given case type.
        Some metrics may not apply to certain case types.
        
        Args:
            pc_index: Index of PC metric (0-10)
            case: Case dictionary with name, code, keywords, etc.
            
        Returns:
            True if metric is applicable, False if not applicable
        """
        if not case:
            return True  # Default to applicable if no case info
        
        case_name_lower = case.get('name', '').lower()
        case_keywords = case.get('keywords', [])
        keywords_str = str(case_keywords).lower()
        
        # Example logic: Some metrics might not apply to certain case types
        # This is a simplified example - adjust based on actual PC metric meanings
        
        # For demo purposes, randomly make some metrics not applicable based on case type
        # Cases that are very short or simple might not have all metrics apply
        simple_cases = ['local', 'minor', 'simple', 'routine', 'brief']
        is_simple_case = any(keyword in case_name_lower for keyword in simple_cases)
        
        # Some metrics might not apply to pediatric cases if they're adult-specific
        # Some metrics might not apply to outpatient cases if they're OR-specific
        # This is a placeholder - adjust based on actual PC metric definitions
        
        # For now, return True for most cases (not applicable will be handled by probability)
        # But we can make certain metrics less likely for certain case types
        return True
    
    def _generate_pc_scores_by_case_and_behavior(self, case: Optional[Dict[str, Any]]) -> Dict[str, int]:
        """
        Generate PC scores based on case type and behavior expectations.
        PC scores are behavior-based and should mostly be 3-4 stars (90% should be 3 stars).
        
        Safety concerns are EXTREMELY RARE: Only 1 out of 30 evaluations (3.33%) should have any safety concern.
        When a safety concern occurs, it affects only 1-2 metrics, not all of them.
        
        Args:
            case: Case dictionary (optional) for determining applicability
            
        Returns:
            Dictionary of PC scores (pc_0 through pc_10)
        """
        pc_scores = {}
        
        # FIRST: Decide if this evaluation should have a safety concern at ALL
        # Only 1 out of 30 evaluations (3.33%) should have any safety concern
        has_safety_concern = random.random() < (1.0 / 30.0)  # ~3.33%
        
        # If this evaluation has a safety concern, assign -1 to 1-2 metrics only
        dangerous_metrics = []
        if has_safety_concern:
            # Assign dangerous rating to 1-2 metrics randomly
            num_dangerous = random.randint(1, 2)
            dangerous_indices = random.sample(range(11), num_dangerous)
            dangerous_metrics = dangerous_indices
        
        # Now generate scores for all metrics
        for i in range(11):
            # Check if this metric should be marked as dangerous
            if i in dangerous_metrics:
                pc_scores[f"pc_{i}"] = -1
                continue
            
            rand = random.random()
            
            # 5-10% chance for not applicable (0) - case-dependent
            if rand < 0.10:
                # Check if metric is truly not applicable to this case type
                if not self._is_pc_metric_applicable(i, case):
                    pc_scores[f"pc_{i}"] = 0
                else:
                    # Even if technically applicable, sometimes mark as not applicable
                    # (5% of applicable metrics can be marked as not applicable)
                    if random.random() < 0.05:
                        pc_scores[f"pc_{i}"] = 0
                    else:
                        # Generate star rating (90% should be 3 stars)
                        rating_rand = random.random()
                        if rating_rand < 0.90:
                            pc_scores[f"pc_{i}"] = 3
                        elif rating_rand < 0.95:
                            pc_scores[f"pc_{i}"] = 4
                        elif rating_rand < 0.98:
                            pc_scores[f"pc_{i}"] = 2
                        else:
                            pc_scores[f"pc_{i}"] = 1
            else:
                # For applicable metrics, generate star rating
                # 90% should be 3 stars, rest mostly 4, occasional 1-2
                rating_rand = random.random()
                if rating_rand < 0.90:
                    # 90% chance for 3 stars
                    pc_scores[f"pc_{i}"] = 3
                elif rating_rand < 0.95:
                    # 5% chance for 4 stars
                    pc_scores[f"pc_{i}"] = 4
                elif rating_rand < 0.98:
                    # 3% chance for 2 stars
                    pc_scores[f"pc_{i}"] = 2
                else:
                    # 2% chance for 1 star
                    pc_scores[f"pc_{i}"] = 1
        
        # Additional check: Some metrics might not apply based on case type
        # For example, pediatric-specific metrics don't apply to adult cases
        if case:
            case_name_lower = case.get('name', '').lower()
            
            # Example: If case doesn't involve certain procedures, some metrics might not apply
            # Adjust this logic based on actual PC metric meanings
            # For demo, randomly make 1-2 metrics not applicable if case is simple
            if 'simple' in case_name_lower or 'routine' in case_name_lower:
                # Make 1-2 random metrics not applicable
                not_applicable_count = random.randint(1, 2)
                applicable_indices = [i for i in range(11) if pc_scores.get(f"pc_{i}", 3) != -1]
                if len(applicable_indices) >= not_applicable_count:
                    for idx in random.sample(applicable_indices, not_applicable_count):
                        pc_scores[f"pc_{idx}"] = 0
        
        return pc_scores
    
    def generate_demo_evaluation(
        self,
        preceptee_name: Optional[str] = None,
        preceptor_name: Optional[str] = None,
        case_type: Optional[str] = None,
        class_standing: Optional[int] = None,
        app_version: str = "0.1.32"
    ) -> Dict[str, Any]:
        """
        Generate a fake demo evaluation document.
        
        Args:
            preceptee_name: Optional preceptee name (random if not provided)
            preceptor_name: Optional preceptor name (random if not provided)
            case_type: Optional case type (random if not provided)
            class_standing: Optional class standing (1-4, random if not provided)
            app_version: App version (default: "0.1.32")
        
        Returns:
            Evaluation data dictionary matching the structure from evaluation_example.text
        """
        # Select student from students.json if not provided
        selected_student = None
        if preceptee_name:
            # Try to find student by name
            selected_student = next((s for s in self.students if s.get('name') == preceptee_name), None)
        
        if not selected_student:
            # Select random student from students.json
            selected_student = self._select_random_student()
        
        if selected_student:
            # Use student data from students.json
            preceptee_name = selected_student.get('name', preceptee_name or 'Unknown Student')
            preceptee_user_id = selected_student.get('id', self._generate_random_string(28))
            student_class_standing_str = selected_student.get('class_standing', '')
            
            # Convert class standing string to numeric if not provided
            if class_standing is None:
                class_standing = self._convert_class_standing_to_numeric(student_class_standing_str)
        else:
            # Fallback to random name generation if no students available
            first_names = ["Drew", "Alex", "Jordan", "Taylor", "Casey", "Morgan", "Riley", "Quinn"]
            last_names = ["Timme", "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
            
            if not preceptee_name:
                preceptee_name = f"{random.choice(first_names)} {random.choice(last_names)}"
            
            preceptee_user_id = self._generate_random_string(28)
            if class_standing is None:
                class_standing = random.randint(1, 4)
        
        # Select preceptor from sites.json
        selected_preceptor = None
        
        # Only use preceptors from sites.json if available
        if not self.preceptors or len(self.preceptors) == 0:
            print(f"⚠️ No preceptors loaded from sites.json, cannot use preceptor selection")
        else:
            if preceptor_name:
                # Try to find preceptor by name match
                for preceptor in self.preceptors:
                    full_name = f"{preceptor.get('firstName', '')} {preceptor.get('lastName', '')}".strip()
                    if full_name.lower() == preceptor_name.lower() or preceptor_name.lower() in full_name.lower():
                        selected_preceptor = preceptor
                        print(f"✅ Found preceptor by name: {preceptor_name}")
                        break
            
            if not selected_preceptor:
                # Select preceptor from sites.json (optionally matching to student's hospital)
                selected_preceptor = self._select_preceptor(student=selected_student)
        
        # Select site from preceptor's assigned sites
        selected_site = None
        if selected_preceptor:
            # Use preceptor data from sites.json
            preceptor_first_name = selected_preceptor.get('firstName', '')
            preceptor_last_name = selected_preceptor.get('lastName', '')
            preceptor_name = f"{preceptor_first_name} {preceptor_last_name}".strip()
            preceptor_id = selected_preceptor.get('id', self._generate_random_string(28))
            preceptor_credentials = selected_preceptor.get('credentials', '')
            print(f"✅ Using preceptor from sites.json: {preceptor_name} ({preceptor_id})")
            
            # Select a site from the preceptor's assigned sites
            assigned_sites = selected_preceptor.get('assignedSites', [])
            if assigned_sites:
                print(f"   📍 Found {len(assigned_sites)} assigned sites for preceptor")
                # Try to match to student's hospital first
                if selected_student:
                    student_hospital = selected_student.get('hospital', '')
                    if student_hospital:
                        hospital_name_parts = student_hospital.split(',')
                        if hospital_name_parts:
                            student_hospital_name = hospital_name_parts[0].strip().upper()
                            # Try to find matching site
                            for site in assigned_sites:
                                site_name = site.get('hospitalName', '').upper()
                                if student_hospital_name in site_name or site_name in student_hospital_name:
                                    selected_site = site
                                    print(f"   ✅ Matched site to student hospital: {site.get('hospitalName', 'N/A')}")
                                    break
                
                # If no match found, use primarySite 90% of the time, otherwise random
                if not selected_site:
                    primary_sites = [s for s in assigned_sites if s.get('primarySite', False)]
                    # 90% chance to use primary site if available, 10% chance to pick randomly
                    if primary_sites and random.random() < 0.9:
                        selected_site = primary_sites[0]
                        print(f"   ✅ Using primary site (90% priority): {selected_site.get('hospitalName', 'N/A')}")
                    else:
                        selected_site = random.choice(assigned_sites)
                        print(f"   ✅ Selected random site from assignedSites: {selected_site.get('hospitalName', 'N/A')} (primarySite: {selected_site.get('primarySite', False)})")
            else:
                print(f"   ⚠️ Preceptor has no assigned sites")
        else:
            # Fallback to random generation if no preceptors available
            print(f"⚠️ Falling back to random preceptor generation (sites.json not available or empty)")
            first_names = ["Drew", "Alex", "Jordan", "Taylor", "Casey", "Morgan", "Riley", "Quinn"]
            last_names = ["Timme", "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
            
            if not preceptor_name:
                preceptor_name = f"{random.choice(first_names)} {random.choice(last_names)}"
            
            preceptor_id = self._generate_random_string(28)
            preceptor_credentials = ""
        
        request_id = self._generate_random_string(20)
        program_id = self._generate_random_string(20)
        doc_id = self._generate_random_string(20)
        
        # Generate timestamps
        now = datetime.now()
        request_date = now - timedelta(days=random.randint(1, 30))
        completion_date = now - timedelta(hours=random.randint(1, 24))
        
        # Select case from actual cases.json if not provided
        selected_case = None
        if not case_type:
            selected_case = self._select_random_case()
            # Use the case name directly (e.g., "ALIF with Posterior Fusion")
            case_type = selected_case.get('name', 'Unknown Case')
        else:
            # Try to find case by name if case_type is provided
            selected_case = next((c for c in self.cases if c.get('name') == case_type), None)
            if not selected_case:
                selected_case = self._select_random_case()
                # Update case_type to match the selected case
                case_type = selected_case.get('name', 'Unknown Case')
        
        # Class standing should already be set from student data above, but ensure it's set
        if class_standing is None:
            class_standing = random.randint(1, 4)
        
        # Generate evaluation scores
        # AC scores (ac_0 through ac_12): 0-100 in increments of 10 (0, 10, 20, ..., 100)
        # AC scores are correlated with class standing:
        # - class_standing 1: 0-40 (lower scores for first year students)
        # - class_standing 2: 40-80 (medium scores)
        # - class_standing 3: 80-100 (higher scores)
        # - class_standing 4: 80-100 (highest scores for most experienced)
        ac_scores = self._generate_ac_scores_by_class_standing(class_standing)
        
        # PC scores (pc_0 through pc_10): -1, 0, 1, 2, 3, 4
        # PC scores are behavior-based and should mostly be 3-4 stars
        # -1 = student is dangerous (EXTREMELY RARE: Only 1 out of 30 evaluations total, affects 1-2 metrics when it occurs)
        # 0 = not applicable (case-dependent, ~5-10% chance)
        # 1-4 = stars (90% should be 3 stars, rest mostly 4, occasional 1-2)
        pc_scores = self._generate_pc_scores_by_case_and_behavior(selected_case)
        
        # Combine scores for comment generation
        all_scores = {**ac_scores, **pc_scores}
        
        # Generate realistic preceptor comment based on case and performance
        # Comments should explain the case and how the student performed in that specific clinical rotation case
        preceptor_comment, performance_level = self._generate_preceptor_comment(
            case=selected_case or self._select_random_case(),
            preceptee_name=preceptee_name,
            class_standing=class_standing,
            scores=all_scores
        )
        
        # Generate focus areas - actionable guidance for future learning and improvement
        focus_areas = self._generate_focus_areas(
            case=selected_case or self._select_random_case(),
            scores=all_scores,
            class_standing=class_standing,
            performance_level=performance_level,
            preceptee_name=preceptee_name
        )
        
        # Build evaluation data
        evaluation_data = {
            **ac_scores,
            **pc_scores,
            "app_version": app_version,
            "case_type": case_type,
            "class_standing": class_standing,
            "comments": preceptor_comment,
            "completed": True,
            "completion_date": completion_date,
            "docId": doc_id,
            "focus_areas": focus_areas,
            "geopoint": self._generate_geopoint(site=selected_site),
            "n/a": [],  # Empty array field from example
            "preceptee_email": self._generate_random_email(preceptee_name),
            "preceptee_phone": self._generate_random_phone(),
            "preceptee_user_id": preceptee_user_id,
            "preceptee_user_name": preceptee_name,
            "preceptor_email": self._generate_random_email(preceptor_name),
            "preceptor_id": preceptor_id,
            "preceptor_name": preceptor_name,
            "preceptor_phone": self._generate_random_phone(),
            "program_id": program_id,
            "request_date": request_date,
            "request_id": request_id,
            "seen": random.choice([True, False])
        }
        
        # Add site information if available
        if selected_site:
            evaluation_data["hospital_id"] = selected_site.get('hospitalId', '')
            evaluation_data["hospital_name"] = selected_site.get('hospitalName', '')
            evaluation_data["hospital_city"] = selected_site.get('city', '')
            evaluation_data["hospital_state"] = selected_site.get('state', '')
            evaluation_data["primary_site"] = selected_site.get('primarySite', False)
        
        # Add preceptor credentials if available
        if selected_preceptor and preceptor_credentials:
            evaluation_data["preceptor_credentials"] = preceptor_credentials
        
        return evaluation_data
    
    def save_evaluation_to_firestore(
        self,
        evaluation_data: Dict[str, Any],
        parent_doc_id: Optional[str] = None,
        doc_id: Optional[str] = None,
        use_top_level_collection: bool = True
    ) -> str:
        """
        Save evaluation to Firestore.
        
        Args:
            evaluation_data: Evaluation data dictionary
            parent_doc_id: Optional parent document ID (only used if use_top_level_collection=False)
            doc_id: Optional document ID (auto-generated if not provided)
            use_top_level_collection: If True, save to top-level 'agent_evaluations' collection.
                                     If False, save to subcollection 'requests/{parent_doc_id}/agent_evaluations'
        
        Returns:
            Document ID of the saved evaluation
        """
        if not self.db:
            raise ValueError("Firestore client not initialized. Cannot save evaluation.")
        
        try:
            # Add metadata
            evaluation_data['created_at'] = SERVER_TIMESTAMP
            evaluation_data['modified_at'] = SERVER_TIMESTAMP
            evaluation_data['created_by'] = 'evaluations-agent'
            
            if use_top_level_collection:
                # Save to top-level collection: agent_evaluations/{doc_id}
                collection_ref = self.db.collection('agent_evaluations')
                
                if doc_id:
                    # Use provided doc ID
                    doc_ref = collection_ref.document(doc_id)
                    doc_ref.set(evaluation_data)
                    print(f"✅ Saved evaluation to Firestore: agent_evaluations/{doc_id}")
                    return doc_id
                else:
                    # Auto-generate doc ID
                    doc_ref = collection_ref.add(evaluation_data)[1]
                    doc_id = doc_ref.id
                    print(f"✅ Saved evaluation to Firestore: agent_evaluations/{doc_id}")
                    return doc_id
            else:
                # Use subcollection: parent_collection/{parent_doc_id}/agent_evaluations/{doc_id}
                final_parent_doc_id = parent_doc_id or self.parent_doc_id
                
                # If no parent doc ID provided, create/use a default one
                if not final_parent_doc_id:
                    # Use the request_id from evaluation_data as parent doc ID
                    final_parent_doc_id = evaluation_data.get('request_id', 'default_request')
                
                # Get subcollection reference
                parent_doc_ref = self.db.collection(self.parent_collection).document(final_parent_doc_id)
                subcollection_ref = parent_doc_ref.collection('agent_evaluations')
                
                if doc_id:
                    # Use provided doc ID
                    doc_ref = subcollection_ref.document(doc_id)
                    doc_ref.set(evaluation_data)
                    print(f"✅ Saved evaluation to Firestore: {self.parent_collection}/{final_parent_doc_id}/agent_evaluations/{doc_id}")
                    return doc_id
                else:
                    # Auto-generate doc ID
                    doc_ref = subcollection_ref.add(evaluation_data)[1]
                    doc_id = doc_ref.id
                    print(f"✅ Saved evaluation to Firestore: {self.parent_collection}/{final_parent_doc_id}/agent_evaluations/{doc_id}")
                    return doc_id
                
        except Exception as e:
            print(f"❌ Error saving evaluation to Firestore: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Failed to save evaluation to Firestore: {str(e)}")
    
    def create_and_save_demo_evaluation(
        self,
        preceptee_name: Optional[str] = None,
        preceptor_name: Optional[str] = None,
        case_type: Optional[str] = None,
        class_standing: Optional[int] = None,
        app_version: str = "0.1.32",
        parent_doc_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate and save a demo evaluation in one step.
        
        Args:
            preceptee_name: Optional preceptee name (random if not provided)
            preceptor_name: Optional preceptor name (random if not provided)
            case_type: Optional case type (random if not provided)
            class_standing: Optional class standing (1-4, random if not provided)
            app_version: App version (default: "0.1.32")
            parent_doc_id: Optional parent document ID
        
        Returns:
            Dictionary with evaluation data and Firestore document ID
        """
        # Update state to GENERATING
        if self.state_agent:
            self.state_agent.set_agent_state("evaluation_agent", StateAgent.STATE_ACTIVE)
        
        try:
            # Generate evaluation data
            evaluation_data = self.generate_demo_evaluation(
                preceptee_name=preceptee_name,
                preceptor_name=preceptor_name,
                case_type=case_type,
                class_standing=class_standing,
                app_version=app_version
            )
            
            # Save to Firestore
            firestore_doc_id = None
            if self.db:
                try:
                    firestore_doc_id = self.save_evaluation_to_firestore(
                        evaluation_data=evaluation_data,
                        parent_doc_id=parent_doc_id,
                        use_top_level_collection=True  # Save to top-level collection
                    )
                except Exception as e:
                    print(f"⚠️ Failed to save evaluation to Firestore: {e}")
                    # Update state to ERROR
                    if self.state_agent:
                        self.state_agent.set_agent_error("evaluation_agent", str(e))
            
            result = {
                **evaluation_data,
                "firestore_doc_id": firestore_doc_id,
                "firestore_parent_doc_id": parent_doc_id or self.parent_doc_id,
                "saved_to_firestore": firestore_doc_id is not None
            }
            
            # Update state to COMPLETED and store result
            if self.state_agent:
                self.state_agent.set_agent_result(
                    "evaluation_agent",
                    {"doc_id": firestore_doc_id, "case_type": evaluation_data.get("case_type")},
                    StateAgent.STATE_IDLE
                )
            
            return result
            
        except Exception as e:
            # Update state to ERROR
            if self.state_agent:
                self.state_agent.set_agent_error("evaluation_agent", str(e))
            raise


def test_direct_gemini():
    """Test Gemini directly without GeminiAgent wrapper"""
    import os
    import google.generativeai as genai
    from google.generativeai.types import HarmBlockThreshold, HarmCategory
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Configure directly
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ FAILED: GEMINI_API_KEY not found")
        return False
    
    genai.configure(api_key=api_key)
    
    # Create model directly
    model = genai.GenerativeModel('models/gemini-2.5-flash')

    # Safety settings using list-of-dicts format (compatible with Gemini API)
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    prompt = "Write a brief professional evaluation comment for a medical student's clinical training."

    try:
        print("🧪 Testing Gemini directly...")
        print(f"📝 Prompt: {prompt}")
        print(f"🔒 Safety settings: {safety_settings}")

        response = model.generate_content(
            prompt,
            safety_settings=safety_settings
        )

        # Check if response was blocked
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            print(f"✓ Finish reason: {candidate.finish_reason}")
            if hasattr(candidate, 'safety_ratings'):
                print(f"✓ Safety ratings: {candidate.safety_ratings}")

        print(f"✅ SUCCESS: {response.text[:200]}...")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        print(f"❌ Exception type: {type(e).__name__}")
        # Print the actual finish reason
        try:
            if hasattr(e, 'response'):
                print(f"Response: {e.response}")
        except:
            pass
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False


# Run the test if this file is executed directly
if __name__ == "__main__":
    test_direct_gemini()


# Convenience function for easy importing
def create_evaluations_agent(
    parent_collection: str = "requests",
    parent_doc_id: Optional[str] = None
) -> EvaluationsAgent:
    """
    Create an Evaluations Agent instance.
    
    Args:
        parent_collection: Name of the parent collection (default: "requests")
        parent_doc_id: Optional parent document ID
    
    Returns:
        EvaluationsAgent instance
    """
    return EvaluationsAgent(
        parent_collection=parent_collection,
        parent_doc_id=parent_doc_id
    )

