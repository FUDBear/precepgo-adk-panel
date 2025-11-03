"""
Evaluations Agent
Independent agent for generating demo evaluation data and saving to Firestore.
Handles creation of fake evaluation documents in the 'agent_evaluations' subcollection.
"""

import os
import json
import random
import string
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP, GeoPoint

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
    from gemini_agent import GeminiAgent, MODEL_GEMINI_PRO
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
                self.gemini_agent = GeminiAgent(model_name=MODEL_GEMINI_PRO)
                print("   - Gemini Agent: ✅")
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
        
        # Use Gemini with Vector Search for enhanced comment generation
        if self.gemini_agent and self.vector_search:
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
                return comment, performance_level
            except Exception as e:
                print(f"⚠️ AI comment generation failed: {e}, falling back to template-based comments")
                # Fall through to template-based generation
        
        # Fallback to template-based comments if AI is not available
        comment = self._generate_template_comment(
            case_name=case_name,
            case_code=case_code,
            preceptee_name=preceptee_name,
            class_standing=class_standing,
            performance_level=performance_level,
            case_keywords=case_keywords
        )
        return comment, performance_level
    
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
        """Generate comment using Vector Search and Gemini AI."""
        
        # Research the case type using Vector Search
        case_research = ""
        if self.vector_search:
            try:
                # Search for anesthesia considerations for this specific case type
                search_query = f"anesthesia considerations for {case_name} procedure"
                if case_keywords:
                    search_query += f" {' '.join(case_keywords[:3])}"
                
                case_research = self.vector_search.search_for_context(
                    query=search_query,
                    num_results=3
                )
            except Exception as e:
                print(f"⚠️ Vector search failed: {e}")
                case_research = ""
        
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
                score_breakdown.append(f"{metric_name}: DANGEROUS (-1)")
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
        
        examples_text = ""
        if examples_to_use:
            example_list = []
            for i, ex in enumerate(examples_to_use, 1):
                ex_case = ex.get('case', 'Unknown case')
                comment = ex.get('comment', '')
                focus_areas = ex.get('focus_areas', '')
                example_list.append(f"Example {i} (Case: {ex_case}):\nComment: {comment}\nFocus Areas: {focus_areas if focus_areas else '(empty)'}")
            examples_text = "\n\n" + "="*70 + "\nREAL PRECEPTOR EVALUATION EXAMPLES (use these as style reference):\n" + "="*70 + "\n\n" + "\n\n".join(example_list)
        
        prompt = f"""You are an experienced anesthesia preceptor writing an evaluation comment for a {year_name} student nurse anesthetist.

Student Context:
- Student Name: {preceptee_name}
- Class Standing: {class_standing} ({year_name})
- Expectation Level: {expectation}
- Performance Level: {performance_level}

Case Information:
- Case Name: {case_name} ({case_code})
- Case Description: {case_description or 'Not provided'}
- Keywords: {', '.join(case_keywords) if case_keywords else 'None'}

Evaluation Metrics Explained:
The evaluation includes two types of metrics:

1. AC Metrics (Anesthesia Competency) - Scored 0-100 in increments of 10:
{ac_metrics_list}

2. PC Metrics (Performance Categories / Behavior) - Scored -1, 0, or 1-4 stars:
{pc_metrics_list}
   (-1 = Dangerous/Unsafe, 0 = Not Applicable, 1-4 = Star rating)

Student Performance:
- Average AC Score: {avg_ac:.1f}/100
- Average PC Score: {avg_pc:.1f}/4
- Safety Concern: {"YES - Student demonstrated dangerous behaviors" if is_dangerous else "No safety concerns"}

Detailed Score Breakdown:
{chr(10).join(score_breakdown[:15])}  # Show first 15 metrics for context

{case_research if case_research else ''}

{examples_text if examples_text else ''}

Write a professional, realistic preceptor evaluation comment that:
1. **MATCHES THE STYLE OF THE EXAMPLES ABOVE** - These are real preceptor evaluations, so your comment should sound exactly like them
2. **EXPLAINS THE CASE**: Briefly describe what this {case_name} case involves and key anesthesia considerations (mention case name ONCE at the beginning)
3. **DESCRIBES PERFORMANCE**: Explain how {preceptee_name} performed specifically during THIS case with rich, detailed observations
4. **IS CREATIVE AND EXPANSIVE**: Write 4-6 sentences with varied language - be descriptive and specific
5. **AVOID REPETITION**: Do NOT repeat the case name multiple times - mention it once, then use pronouns ("this case", "the procedure", "the surgery")
6. **OBSERVE SPECIFIC BEHAVIORS**: Reference specific observations like:
   - How the student responded to stress/pressure during surgery
   - OR preparation and room readiness (what they checked, how they set up)
   - Communication with the team (surgeon, circulating nurse, etc.)
   - Anticipation of needs (having medications ready, preparing backup plans)
   - Handling of unexpected events or complications
   - Demonstration of knowledge and clinical reasoning
7. **BE SPECIFIC TO METRICS**: Reference specific metrics where relevant (e.g., "demonstrated strong airway management" or "needs improvement in medication administration")
8. **CASE-SPECIFIC DETAILS**: Reference specific aspects of {case_name} that were relevant (e.g., positioning challenges, hemodynamic considerations, airway concerns)
9. Reflects the EXPECTATION LEVEL for a {year_name} student: {expectation}
10. Evaluates performance STRICTLY relative to their class standing - {"higher class standing students should be evaluated more harshly" if class_standing >= 3 else "lower class standing students are learning basics"}
11. Reflects the {performance_level} performance level appropriately for their year
12. Does NOT use generic phrases like "recommend additional case preparation" or "review fundamental principles"
13. Focuses on THIS SPECIFIC CASE and how the student handled it - not general advice
14. {"For advanced students (3rd-4th year), be more critical - they should be near independent practitioner level" if class_standing >= 3 else "For beginning students (1st-2nd year), be supportive but educational"}
15. {"Includes a prominent safety warning if this is a dangerous case" if is_dangerous else ""}
16. **CRITICAL**: Study the example comments above carefully - they are REAL preceptor evaluations. Match their:
    - Tone (conversational, natural, sometimes brief, sometimes expansive)
    - Style (specific observations, not generic statements)
    - Structure (flow naturally, mention specific events or behaviors)
    - Language (preceptor-like, not academic)

Write ONLY the comment text, no preamble or labels. Make it creative, expansive, and detailed with specific observations that match the real examples above:"""

        try:
            import google.generativeai as genai
            
            # Generate comment using Gemini
            generation_config = genai.types.GenerationConfig(
                temperature=0.8,  # Higher temperature for more creativity and variety
                top_p=0.95,
                top_k=50,
                max_output_tokens=600,  # Increased for more expansive comments
            )
            
            response = self.gemini_agent.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            comment = response.text.strip()
            
            # Clean up the comment
            comment = comment.replace('"', '').strip()
            if comment.startswith('Comment:'):
                comment = comment.replace('Comment:', '').strip()
            if comment.startswith('Evaluation:'):
                comment = comment.replace('Evaluation:', '').strip()
            
            return comment
            
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
        case_keywords: List[str]
    ) -> str:
        """Fallback template-based comment generation."""
        year_names = {1: "first-year", 2: "second-year", 3: "third-year", 4: "fourth-year"}
        year_name = year_names.get(class_standing, f"year {class_standing}")
        
        # Template-based generation (simplified, used only if AI unavailable)
        opening_statements = {
            "excellent": [
                f"{preceptee_name} demonstrated exceptional clinical skills during the {case_name} case.",
                f"Outstanding performance by {preceptee_name} during the {case_name} procedure.",
                f"{preceptee_name} showed excellent clinical judgment and technical proficiency during {case_name}.",
            ],
            "good": [
                f"{preceptee_name} showed strong clinical competency during the {case_name} case.",
                f"Solid performance by {preceptee_name} during the {case_name} procedure.",
                f"{preceptee_name} demonstrated good clinical skills during {case_name}.",
            ],
            "satisfactory": [
                f"{preceptee_name} performed adequately during the {case_name} case.",
                f"{preceptee_name} showed appropriate clinical skills for a {year_name} student during {case_name}.",
            ],
            "needs_improvement": [
                f"{preceptee_name} participated in the {case_name} case and showed areas for continued growth.",
                f"As a {year_name} student, {preceptee_name} demonstrated understanding but needs further development in {case_name}.",
            ],
            "poor": [
                f"{preceptee_name} struggled significantly during the {case_name} case and requires additional training.",
            ],
            "dangerous": [
                f"⚠️ SAFETY CONCERN: {preceptee_name} demonstrated concerning safety behaviors during the {case_name} case that require immediate attention.",
            ]
        }
        
        closings = {
            "excellent": [
                "Continue to seek challenging cases.",
                "Well done - keep up the excellent work.",
                "Ready for more complex cases.",
            ],
            "good": [
                "Continue building on these skills.",
                "Good progress - keep it up.",
            ],
            "satisfactory": [
                f"Continue to seek hands-on practice with {case_name} cases.",
                f"Keep reviewing {case_name} anesthesia considerations.",
            ],
            "needs_improvement": [
                f"Focus on {case_name} case preparation before next similar case.",
                f"Review {case_name} anesthesia principles and seek additional practice.",
            ],
            "poor": [
                f"Requires intensive remediation before managing {case_name} cases independently.",
            ],
            "dangerous": [
                "REQUIRED ACTION: This student must undergo safety remediation before continuing clinical rotations.",
            ]
        }
        
        opening = random.choice(opening_statements.get(performance_level, [f"{preceptee_name} participated in the {case_name} case."]))
        closing = random.choice(closings.get(performance_level, [""]))
        
        return f"{opening} {closing}".strip()
    
    def _generate_focus_areas(
        self,
        case: Dict[str, Any],
        scores: Dict[str, int],
        class_standing: int,
        performance_level: str
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
        
        # Use Vector Search to get case-specific learning opportunities (at least 1/3 of the time)
        use_vector_search = random.random() < 0.67  # 2/3 of the time use vector search
        
        # Use AI to generate focus areas if available
        if self.gemini_agent and (self.vector_search and use_vector_search or not self.vector_search):
            try:
                return self._generate_focus_areas_with_ai(
                    case_name=case_name,
                    case_keywords=case_keywords,
                    weak_areas=weak_areas,
                    weak_behaviors=weak_behaviors,
                    class_standing=class_standing,
                    performance_level=performance_level,
                    use_vector_search=use_vector_search and self.vector_search is not None
                )
            except Exception as e:
                print(f"⚠️ AI focus areas generation failed: {e}, using template-based")
                # Fall through to template
        
        # Fallback to template-based focus areas
        return self._generate_focus_areas_template(
            case_name=case_name,
            weak_areas=weak_areas,
            weak_behaviors=weak_behaviors,
            performance_level=performance_level
        )
    
    def _generate_focus_areas_with_ai(
        self,
        case_name: str,
        case_keywords: List[str],
        weak_areas: List[Dict[str, Any]],
        weak_behaviors: List[Dict[str, Any]],
        class_standing: int,
        performance_level: str,
        use_vector_search: bool = True
    ) -> str:
        """Generate focus areas using AI based on performance."""
        
        year_names = {1: "first-year", 2: "second-year", 3: "third-year", 4: "fourth-year"}
        year_name = year_names.get(class_standing, f"year {class_standing}")
        
        # Research case-specific learning opportunities using Vector Search
        case_research = ""
        if use_vector_search and self.vector_search:
            try:
                # Search for specific learning points or complications related to this case type
                search_query = f"complications and challenges for {case_name} anesthesia"
                if case_keywords:
                    search_query += f" {' '.join(case_keywords[:2])}"
                
                case_research = self.vector_search.search_for_context(
                    query=search_query,
                    num_results=2
                )
            except Exception as e:
                print(f"⚠️ Vector search for focus areas failed: {e}")
        
        weak_areas_str = "\n".join([f"- {area['metric']} (scored {area['score']}/100)" for area in weak_areas[:5]])
        weak_behaviors_str = "\n".join([f"- {behavior['metric']} (scored {behavior['score']}/4 stars)" for behavior in weak_behaviors[:3]])
        
        # Get example focus areas for reference - try to match case type
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
        
        examples_text = ""
        if examples_to_use:
            example_list = []
            for i, ex in enumerate(examples_to_use, 1):
                ex_case = ex.get('case', 'Unknown case')
                comment = ex.get('comment', '')
                focus_areas = ex.get('focus_areas', '')
                example_list.append(f"Example {i} (Case: {ex_case}):\nComment: {comment}\nFocus Areas: {focus_areas if focus_areas else '(empty)'}")
            examples_text = "\n\n" + "="*70 + "\nREAL PRECEPTOR FOCUS AREAS EXAMPLES (use these as style reference):\n" + "="*70 + "\n\n" + "\n\n".join(example_list)
        
        prompt = f"""You are an experienced anesthesia preceptor providing guidance for a {year_name} student nurse anesthetist.

Case: {case_name}
Performance Level: {performance_level}

Areas needing improvement:
{weak_areas_str if weak_areas_str else "None identified"}

Behavioral areas needing improvement:
{weak_behaviors_str if weak_behaviors_str else "None identified"}

{case_research if case_research else ''}

{examples_text if examples_text else ''}

**CRITICAL**: Study the example focus areas above carefully - they are REAL preceptor evaluations. Match their style exactly.

Generate 1-3 specific, actionable focus areas for this student to practice or learn more about for FUTURE clinical rotations. These should:
1. **MATCH THE STYLE OF THE EXAMPLES ABOVE** - These are real preceptor focus areas, so yours should sound exactly like them
2. Be actionable and specific (e.g., "Practice calculating dosing for pediatric patients" not "Study pharmacology")
3. Address areas where the student needs growth based on their performance
4. Help them avoid mistakes in future rotations
5. Be relevant to their {year_name} level
6. Be concise (1-2 sentences each, separated by semicolons)
7. Focus on PRACTICAL skills they can improve, not abstract concepts
8. Reference specific metrics that were weak (if applicable)
9. **DO NOT simply restate the case name** - avoid generic phrases like "Review [case name] anesthesia considerations"
10. Be specific about WHAT to practice or learn (e.g., "Practice rapid sequence induction techniques" not "Review RSI")
11. Sound like it's coming from an actual preceptor - natural, conversational, not academic
12. Use the case research above to identify specific learning opportunities if available
13. **STYLE**: Match the tone and style of the example focus areas above - they are natural, specific, and actionable
14. Look at how the examples handle empty focus areas - sometimes they're empty, sometimes they're very specific

**IMPORTANT**: If you cannot generate meaningful, specific focus areas that add value beyond restating the obvious, return an empty string "".

Format as a single string with focus areas separated by semicolons (not a list). If nothing meaningful to add, return empty string.

Write ONLY the focus areas (or empty string), no preamble or labels:"""

        try:
            import google.generativeai as genai
            
            generation_config = genai.types.GenerationConfig(
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                max_output_tokens=300,
            )
            
            response = self.gemini_agent.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            focus_areas = response.text.strip()
            
            # Clean up
            focus_areas = focus_areas.replace('"', '').strip()
            if focus_areas.startswith('Focus Areas:'):
                focus_areas = focus_areas.replace('Focus Areas:', '').strip()
            if focus_areas.startswith('Focus areas:'):
                focus_areas = focus_areas.replace('Focus areas:', '').strip()
            if focus_areas.startswith('Focus Area:'):
                focus_areas = focus_areas.replace('Focus Area:', '').strip()
            
            # Check if it's just restating the case name - if so, return empty
            case_name_lower = case_name.lower()
            if case_name_lower in focus_areas.lower() and len(focus_areas.split()) < 10:
                # If it's just a short mention of the case name, likely too generic
                return ""
            
            return focus_areas
            
        except Exception as e:
            print(f"⚠️ Gemini focus areas generation error: {e}")
            raise
    
    def _generate_focus_areas_template(
        self,
        case_name: str,
        weak_areas: List[Dict[str, Any]],
        weak_behaviors: List[Dict[str, Any]],
        performance_level: str
    ) -> str:
        """Template-based focus areas generation."""
        
        focus_list = []
        
        # Add focus areas based on weak performance metrics
        if weak_areas:
            for area in weak_areas[:3]:  # Top 3 weak areas
                metric_name = area['metric']
                if metric_name == "Airway Management":
                    focus_list.append("Practice difficult airway algorithms and backup plans")
                elif metric_name == "Medication Administration":
                    focus_list.append("Review medication dosing calculations and administration protocols")
                elif metric_name == "Regional Technique":
                    focus_list.append("Practice regional anesthesia techniques and anatomy")
                elif metric_name == "Ventilatory Management":
                    focus_list.append("Review ventilator settings and management strategies")
                elif metric_name == "Pre-op Assessment":
                    focus_list.append("Improve preoperative assessment skills and patient evaluation")
                elif metric_name == "Responds to Condition Changes":
                    focus_list.append("Practice recognizing and responding to hemodynamic changes")
                elif metric_name == "Anesthesia Induction":
                    focus_list.append("Review induction techniques and patient safety considerations")
                else:
                    focus_list.append(f"Practice {metric_name.lower()}")
        
        if weak_behaviors:
            for behavior in weak_behaviors[:2]:  # Top 2 weak behaviors
                metric_name = behavior['metric']
                if metric_name == "Troubleshoots Effectively":
                    focus_list.append("Develop problem-solving skills for clinical scenarios")
                elif metric_name == "Communicated Effectively":
                    focus_list.append("Improve communication with team members and patients")
                elif metric_name == "Recognizes Limitations":
                    focus_list.append("Practice recognizing when to seek help")
        
        # Only add case-specific focus if we have weak areas or behaviors
        # Otherwise, leave blank to avoid generic restatements
        if not focus_list:
            return ""
        
        # Join with semicolons
        return "; ".join(focus_list) if focus_list else ""
    
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
    
    def _generate_geopoint(self) -> GeoPoint:
        """Generate a random geopoint"""
        # Random coordinates in US (roughly)
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
        
        Args:
            case: Case dictionary (optional) for determining applicability
            
        Returns:
            Dictionary of PC scores (pc_0 through pc_10)
        """
        pc_scores = {}
        
        for i in range(11):
            rand = random.random()
            
            # 1/8 (12.5%) chance for dangerous (-1)
            if rand < 0.125:
                pc_scores[f"pc_{i}"] = -1
            # 5-10% chance for not applicable (0) - case-dependent
            elif rand < 0.225:  # Adjusted upper bound: 0.125 + 0.10 = 0.225
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
        
        # Generate preceptor name if not provided
        first_names = ["Drew", "Alex", "Jordan", "Taylor", "Casey", "Morgan", "Riley", "Quinn"]
        last_names = ["Timme", "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
        
        if not preceptor_name:
            preceptor_name = f"{random.choice(first_names)} {random.choice(last_names)}"
        
        # Generate IDs
        preceptor_id = self._generate_random_string(28)
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
        # -1 = student is dangerous (1/8 = 12.5% per field)
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
            performance_level=performance_level
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
            "geopoint": self._generate_geopoint(),
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
            self.state_agent.set_agent_state("evaluation_agent", StateAgent.STATE_GENERATING)
        
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
                    StateAgent.STATE_COMPLETED
                )
            
            return result
            
        except Exception as e:
            # Update state to ERROR
            if self.state_agent:
                self.state_agent.set_agent_error("evaluation_agent", str(e))
            raise


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

