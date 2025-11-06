"""
COA Compliance Agent
Tracks COA Standard D requirements for CRNA students by mapping evaluation metrics
to COA standards and generating compliance reports.
"""

import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Import dependencies
try:
    from agents.state_agent import StateAgent
    STATE_AGENT_AVAILABLE = True
except ImportError:
    STATE_AGENT_AVAILABLE = False
    print("⚠️ State Agent not available")

# AC and PC Metric Definitions (matching evaluations_agent.py)
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

# Combined metric lookup
ALL_METRICS = {**AC_METRICS, **PC_METRICS}


class COAComplianceAgent:
    """
    Agent for tracking COA Standard D compliance for CRNA students.
    Maps evaluation metrics to COA standards and generates compliance reports.
    """
    
    def __init__(self, firestore_db=None, mapping_file_path: Optional[str] = None):
        """
        Initialize the COA Compliance Agent.
        
        Args:
            firestore_db: Optional Firestore database client
            mapping_file_path: Path to the COA mapping DOCX file
        """
        # Initialize Firestore
        if firestore_db:
            self.db = firestore_db
        else:
            try:
                project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
                if project_id:
                    self.db = firestore.Client(project=project_id)
                else:
                    self.db = firestore.Client()
            except Exception as e:
                print(f"⚠️ Firestore initialization failed: {e}")
                self.db = None
        
        # Initialize State Agent
        self.state_agent = None
        if STATE_AGENT_AVAILABLE and self.db:
            try:
                self.state_agent = StateAgent(firestore_db=self.db)
            except Exception as e:
                print(f"⚠️ State Agent initialization failed: {e}")
        
        # COA mapping file path
        self.mapping_file_path = mapping_file_path or os.getenv(
            "COA_MAPPING_FILE_PATH",
            "/mnt/user-data/uploads/Standard_D_Mapping_to_Clinical_Evaluations__1_.docx"
        )
        
        # Load COA standards from standards.json
        self.coa_mapping = self._load_coa_mapping()
        
        # Load students
        self.students = self._load_students()
        
        print(f"✅ COA Compliance Agent initialized")
        print(f"   - COA standards loaded: {len(self.coa_mapping)}")
        print(f"   - Students loaded: {len(self.students)}")
        print(f"   - Firestore: {'Available' if self.db else 'Not available'}")
    
    def _load_coa_mapping(self) -> Dict[str, Dict[str, Any]]:
        """
        Load COA standards mapping from standards.json.
        
        Returns:
            Dictionary mapping standard ID to standard data with metrics
        """
        try:
            with open("data/standards.json", "r") as f:
                data = json.load(f)
                
            # Handle both {"standards": [...]} and direct list formats
            if isinstance(data, dict) and "standards" in data:
                standards_list = data["standards"]
            elif isinstance(data, list):
                standards_list = data
            else:
                print("⚠️ Unexpected standards.json format")
                return {}
            
            # Create mapping: {standard_id: {standard, metrics, ...}}
            mapping = {}
            for standard_data in standards_list:
                standard_id = standard_data.get("id")
                if not standard_id:
                    continue
                
                mapping[standard_id] = {
                    "id": standard_id,
                    "standard": standard_data.get("standard", ""),
                    "evaluation_metrics": standard_data.get("evaluation_metrics", [])
                }
            
            print(f"✅ Loaded {len(mapping)} COA standards from standards.json")
            return mapping
            
        except FileNotFoundError:
            print("⚠️ data/standards.json not found")
            return {}
        except json.JSONDecodeError as e:
            print(f"⚠️ Error parsing data/standards.json: {e}")
            return {}
        except Exception as e:
            print(f"⚠️ Error loading COA mapping: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _map_metric_name_to_field(self, metric_name: str) -> Optional[str]:
        """
        Map metric name from standards.json to actual evaluation field name.
        
        Examples:
            "pc_01" -> "pc_0"
            "pc_11" -> "pc_10" (pc_0 through pc_10 = 11 fields)
            "perf_01" -> "pc_0" (perf maps to pc)
            "ac_01" -> "ac_0"
        
        Args:
            metric_name: Metric name from standards.json (e.g., "pc_01", "perf_05")
        
        Returns:
            Actual evaluation field name (e.g., "pc_0", "ac_0") or None if invalid
        """
        # Handle pc_## format (pc_01 through pc_13)
        if metric_name.startswith("pc_"):
            try:
                num = int(metric_name.split("_")[1])
                if 1 <= num <= 13:
                    # pc_01 -> pc_0, pc_02 -> pc_1, ..., pc_13 -> pc_12
                    return f"pc_{num - 1}"
            except (ValueError, IndexError):
                pass
        
        # Handle perf_## format (perf_01 through perf_11) - maps to pc_0 through pc_10
        elif metric_name.startswith("perf_"):
            try:
                num = int(metric_name.split("_")[1])
                if 1 <= num <= 11:
                    # perf_01 -> pc_0, perf_02 -> pc_1, ..., perf_11 -> pc_10
                    return f"pc_{num - 1}"
            except (ValueError, IndexError):
                pass
        
        # Handle ac_## format (ac_01 through ac_13)
        elif metric_name.startswith("ac_"):
            try:
                num = int(metric_name.split("_")[1])
                if 1 <= num <= 13:
                    # ac_01 -> ac_0, ac_02 -> ac_1, ..., ac_13 -> ac_12
                    return f"ac_{num - 1}"
            except (ValueError, IndexError):
                pass
        
        return None
    
    def _load_students(self) -> List[Dict[str, Any]]:
        """Load students from data/students.json"""
        try:
            with open("data/students.json", "r") as f:
                data = json.load(f)
                # Handle both {"students": [...]} and [...] formats
                if isinstance(data, dict) and "students" in data:
                    return data["students"]
                elif isinstance(data, list):
                    return data
                else:
                    print("⚠️ Unexpected students.json format")
                    return []
        except FileNotFoundError:
            print("⚠️ data/students.json not found")
            return []
        except json.JSONDecodeError as e:
            print(f"⚠️ Error parsing data/students.json: {e}")
            return []
    
    def _get_student_evaluations(self, student_id: str, student_name: str) -> List[Dict[str, Any]]:
        """
        Get all evaluations for a specific student from Firestore.
        Queries by both student_id and student_name for efficiency.
        
        Args:
            student_id: Student ID
            student_name: Student name
        
        Returns:
            List of evaluation documents
        """
        if not self.db:
            return []
        
        evaluations = []
        try:
            evaluations_ref = self.db.collection('agent_evaluations')
            
            # Query by student_id first (more efficient)
            query_by_id = evaluations_ref.where('preceptee_user_id', '==', student_id).stream()
            for eval_doc in query_by_id:
                eval_data = eval_doc.to_dict()
                eval_data['doc_id'] = eval_doc.id
                evaluations.append(eval_data)
            
            # Also query by student_name (in case some evaluations only have name)
            query_by_name = evaluations_ref.where('preceptee_user_name', '==', student_name).stream()
            for eval_doc in query_by_name:
                eval_data = eval_doc.to_dict()
                eval_data['doc_id'] = eval_doc.id
                # Avoid duplicates (check if doc_id already in evaluations)
                if not any(e.get('doc_id') == eval_doc.id for e in evaluations):
                    evaluations.append(eval_data)
            
            return evaluations
        except Exception as e:
            print(f"⚠️ Error querying evaluations for student {student_id} ({student_name}): {e}")
            return []
    
    def _normalize_metric_value(self, value: Any) -> float:
        """
        Normalize metric value to a number for comparison.
        
        Args:
            value: Metric value (could be int, str, etc.)
        
        Returns:
            Numeric value (0 if invalid)
        """
        if value is None:
            return 0.0
        
        try:
            if isinstance(value, (int, float)):
                return float(value)
            elif isinstance(value, str):
                # Try to parse string numbers
                return float(value.strip())
            else:
                return 0.0
        except (ValueError, TypeError):
            return 0.0
    
    def _check_metric_score(self, evaluation: Dict[str, Any], metric_key: str) -> bool:
        """
        Check if a metric has a score > 0 in the evaluation.
        
        Args:
            evaluation: Evaluation document dictionary
            metric_key: Metric key (e.g., "ac_0", "pc_5")
        
        Returns:
            True if metric score > 0, False otherwise
        """
        value = evaluation.get(metric_key)
        score = self._normalize_metric_value(value)
        return score > 0
    
    def _calculate_compliance(self, student: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate COA compliance for a single student.
        Generates scores for each COA standard based on evaluation metrics.
        
        Args:
            student: Student dictionary from students.json
        
        Returns:
            Compliance report dictionary with standard scores
        """
        student_id = student.get("id")
        student_name = student.get("name", "Unknown")
        class_standing = student.get("class_standing", "Unknown")
        
        # Get all evaluations for this student
        evaluations = self._get_student_evaluations(student_id, student_name)
        
        # Track scores for each standard: {standard_id: score_count}
        standard_scores = {}
        
        # Initialize all standards with 0 scores
        for standard_id, standard_data in self.coa_mapping.items():
            standard_scores[standard_id] = 0
        
        # Process each evaluation
        for evaluation in evaluations:
            # Check each COA standard
            for standard_id, standard_data in self.coa_mapping.items():
                evaluation_metrics = standard_data.get("evaluation_metrics", [])
                
                # Check if any of the mapped metrics have score > 0
                for metric_name in evaluation_metrics:
                    # Map metric name to actual evaluation field
                    field_name = self._map_metric_name_to_field(metric_name)
                    if field_name and self._check_metric_score(evaluation, field_name):
                        # This evaluation contributes +1 to this standard
                        standard_scores[standard_id] += 1
                        break  # Only count once per evaluation per standard
        
        # Generate simple score objects: {"id": "coa_standard_005", "score": 592}
        standard_score_list = [
            {
                "id": standard_id,
                "score": score
            }
            for standard_id, score in standard_scores.items()
        ]
        
        # Calculate totals
        total_standards = len(self.coa_mapping)
        total_score = sum(standard_scores.values())
        
        return {
            "student_id": student_id,
            "student_name": student_name,
            "class_standing": class_standing,
            "total_standards": total_standards,
            "total_score": total_score,
            "standard_scores": standard_score_list,
            "evaluations_processed": len(evaluations),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agent": "COA Compliance Agent"
        }
    
    def generate_reports(self, student_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Generate COA compliance reports for all students.
        Creates a single consolidated report with all students' standard scores.
        
        Args:
            student_ids: Optional list of student IDs to process (if None, processes all)
        
        Returns:
            Consolidated report dictionary with all students' standard scores
        """
        # Update state to GENERATING
        if self.state_agent:
            self.state_agent.set_agent_state("coa_agent", StateAgent.STATE_GENERATING)
        
        try:
            # Filter students if IDs provided
            students_to_process = self.students
            if student_ids:
                students_to_process = [
                    s for s in self.students
                    if s.get("id") in student_ids
                ]
            
            print(f"📊 Generating COA compliance reports for {len(students_to_process)} student(s)...")
            
            # Aggregate scores across all students: {standard_id: total_score}
            aggregated_scores = {}
            
            # Initialize all standards with 0 scores
            for standard_id in self.coa_mapping.keys():
                aggregated_scores[standard_id] = 0
            
            # Process each student
            student_reports = []
            for student in students_to_process:
                try:
                    student_report = self._calculate_compliance(student)
                    student_reports.append(student_report)
                    
                    # Aggregate scores for each standard
                    for score_obj in student_report.get("standard_scores", []):
                        standard_id = score_obj.get("id")
                        score = score_obj.get("score", 0)
                        if standard_id in aggregated_scores:
                            aggregated_scores[standard_id] += score
                    
                    print(f"✅ Processed {student_report['student_name']} ({student_report['student_id']})")
                    print(f"   Evaluations: {student_report['evaluations_processed']}, Total Score: {student_report['total_score']}")
                    
                except Exception as e:
                    print(f"⚠️ Error generating report for student {student.get('id')}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Generate simple score objects: {"id": "coa_standard_005", "score": 592}
            standard_score_list = [
                {
                    "id": standard_id,
                    "score": score
                }
                for standard_id, score in aggregated_scores.items()
            ]
            
            # Create consolidated report
            consolidated_report = {
                "students_processed": len(student_reports),
                "total_standards": len(self.coa_mapping),
                "standard_scores": standard_score_list,
                "student_reports": student_reports,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "agent": "COA Compliance Agent"
            }
            
            # Save consolidated report to Firestore and get document ID
            doc_id = None
            if self.db:
                doc_id = self._save_consolidated_report_to_firestore(consolidated_report)
                if doc_id:
                    consolidated_report['firestore_doc_id'] = doc_id
            
            # Update state to COMPLETED
            if self.state_agent:
                self.state_agent.set_agent_result(
                    "coa_agent",
                    {
                        "reports_generated": len(student_reports),
                        "students_processed": len(students_to_process),
                        "total_standards": len(self.coa_mapping)
                    },
                    StateAgent.STATE_COMPLETED
                )
            
            return consolidated_report
            
        except Exception as e:
            # Update state to ERROR
            if self.state_agent:
                self.state_agent.set_agent_error("coa_agent", str(e))
            raise
    
    def _save_consolidated_report_to_firestore(self, report: Dict[str, Any]) -> str:
        """
        Save consolidated COA compliance report to Firestore.
        Creates a new document with an auto-generated ID each time.
        
        Args:
            report: Consolidated report dictionary
        
        Returns:
            Document ID of saved report
        """
        if not self.db:
            return None
        
        try:
            collection_ref = self.db.collection('agent_coa_reports')
            
            # Add timestamp
            report['created_at'] = SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
            
            # Create new document with auto-generated ID
            doc_ref = collection_ref.add(report)
            
            # doc_ref is a tuple (timestamp, DocumentReference)
            # Extract the document ID from the DocumentReference
            doc_id = doc_ref[1].id
            
            print(f"✅ Saved consolidated COA report to Firestore: agent_coa_reports/{doc_id}")
            return doc_id
            
        except Exception as e:
            print(f"⚠️ Failed to save consolidated report to Firestore: {e}")
            import traceback
            traceback.print_exc()
            return None


# Convenience function for easy importing
def create_coa_agent(firestore_db=None, mapping_file_path: Optional[str] = None) -> COAComplianceAgent:
    """
    Create a COA Compliance Agent instance.
    
    Args:
        firestore_db: Optional Firestore database client
        mapping_file_path: Optional path to COA mapping DOCX file
    
    Returns:
        COAComplianceAgent instance
    """
    return COAComplianceAgent(firestore_db=firestore_db, mapping_file_path=mapping_file_path)

