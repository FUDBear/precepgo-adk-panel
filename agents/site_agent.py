"""
Site Agent
Analyzes evaluation data to generate site reports listing clinical sites, case types,
and preceptor information with student counts and case types they've precepted.
"""

import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Import dependencies
try:
    from gemini_agent import GeminiAgent, MODEL_GEMINI_PRO
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    MODEL_GEMINI_PRO = "models/gemini-2.5-pro"
    print("⚠️ Gemini Agent not available")

try:
    from agents.state_agent import StateAgent
    STATE_AGENT_AVAILABLE = True
except ImportError:
    STATE_AGENT_AVAILABLE = False
    print("⚠️ State Agent not available")

try:
    from firestore_service import get_firestore_service
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    print("⚠️ Firestore not available")


class SiteAgent:
    """
    Agent for generating site reports from evaluation data.
    Analyzes clinical sites, case types, and preceptor activity.
    """
    
    def __init__(self, firestore_db: Optional[Any] = None):
        """
        Initialize the Site Agent.
        
        Args:
            firestore_db: Optional Firestore database client
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
        
        # Initialize Gemini Agent for report generation
        self.gemini_agent = None
        if GEMINI_AVAILABLE:
            try:
                self.gemini_agent = GeminiAgent(model_name=MODEL_GEMINI_PRO)
            except Exception as e:
                print(f"⚠️ Gemini Agent initialization failed: {e}")
        
        # Collections
        self.evaluations_collection = "agent_evaluations"
        self.sites_collection = "agent_sites"
        
        print(f"✅ Site Agent initialized")
        print(f"   - Firestore: {'Available' if self.db else 'Not available'}")
        print(f"   - Gemini Agent: {'Available' if self.gemini_agent else 'Not available'}")
        print(f"   - State Agent: {'Available' if self.state_agent else 'Not available'}")
    
    def _load_students(self) -> List[Dict[str, Any]]:
        """Load students data to get site/hospital information"""
        try:
            import json
            with open("data/students.json", "r") as f:
                data = json.load(f)
                if isinstance(data, dict) and "students" in data:
                    return data["students"]
                elif isinstance(data, list):
                    return data
                else:
                    return []
        except FileNotFoundError:
            print("⚠️ data/students.json not found")
            return []
        except Exception as e:
            print(f"⚠️ Error loading students.json: {e}")
            return []
    
    def _fetch_all_evaluations(self) -> List[Dict[str, Any]]:
        """
        Fetch all evaluations from agent_evaluations collection.
        
        Returns:
            List of evaluation documents
        """
        if not self.db:
            print("❌ Firestore not available")
            return []
        
        try:
            evaluations_ref = self.db.collection(self.evaluations_collection)
            evaluations = []
            
            for doc in evaluations_ref.stream():
                eval_data = doc.to_dict()
                eval_data['doc_id'] = doc.id
                evaluations.append(eval_data)
            
            print(f"📊 Fetched {len(evaluations)} evaluations from {self.evaluations_collection}")
            return evaluations
        except Exception as e:
            print(f"❌ Error fetching evaluations: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _analyze_evaluations(self, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze evaluations to extract site and preceptor information.
        
        Args:
            evaluations: List of evaluation documents
            
        Returns:
            Dictionary with analyzed data
        """
        # Load students to get site/hospital mapping
        students = self._load_students()
        student_site_map = {}
        for student in students:
            student_id = student.get('id')
            student_name = student.get('name')
            hospital = student.get('hospital') or 'Unknown Hospital'
            if student_id:
                student_site_map[student_id] = hospital
            if student_name:
                student_site_map[student_name] = hospital
        
        # Site analysis: {site_name: {case_types: set, total_evaluations: int}}
        sites_data = defaultdict(lambda: {'case_types': set(), 'total_evaluations': 0, 'preceptors': set()})
        
        # Preceptor analysis: {preceptor_name: {students: set, case_types: set, total_evaluations: int}}
        preceptors_data = defaultdict(lambda: {'students': set(), 'case_types': set(), 'total_evaluations': 0})
        
        # Process each evaluation
        for eval_data in evaluations:
            # Get site/hospital from student
            preceptee_id = eval_data.get('preceptee_user_id') or eval_data.get('preceptee_user_name')
            site_name = student_site_map.get(preceptee_id, 'Unknown Site')
            
            # Get preceptor info
            preceptor_name = eval_data.get('preceptor_name', 'Unknown Preceptor')
            preceptor_id = eval_data.get('preceptor_id', '')
            
            # Get case type
            case_type = eval_data.get('case_type', 'Unknown Case')
            
            # Update site data
            sites_data[site_name]['case_types'].add(case_type)
            sites_data[site_name]['total_evaluations'] += 1
            sites_data[site_name]['preceptors'].add(preceptor_name)
            
            # Update preceptor data
            preceptor_key = f"{preceptor_name} ({preceptor_id})" if preceptor_id else preceptor_name
            preceptors_data[preceptor_key]['students'].add(preceptee_id if preceptee_id else 'Unknown')
            preceptors_data[preceptor_key]['case_types'].add(case_type)
            preceptors_data[preceptor_key]['total_evaluations'] += 1
        
        # Convert sets to lists for JSON serialization
        sites_summary = []
        for site_name, data in sites_data.items():
            sites_summary.append({
                'site_name': site_name,
                'case_types': sorted(list(data['case_types'])),
                'total_evaluations': data['total_evaluations'],
                'unique_preceptors': len(data['preceptors']),
                'preceptor_names': sorted(list(data['preceptors']))
            })
        
        preceptors_summary = []
        for preceptor_key, data in preceptors_data.items():
            # Extract name from key (handle format "Name (ID)")
            preceptor_name = preceptor_key.split(' (')[0]
            preceptors_summary.append({
                'preceptor_name': preceptor_name,
                'student_count': len(data['students']),
                'case_types': sorted(list(data['case_types'])),
                'total_evaluations': data['total_evaluations']
            })
        
        # Sort by total evaluations (descending)
        sites_summary.sort(key=lambda x: x['total_evaluations'], reverse=True)
        preceptors_summary.sort(key=lambda x: x['total_evaluations'], reverse=True)
        
        return {
            'sites': sites_summary,
            'preceptors': preceptors_summary,
            'total_evaluations': len(evaluations),
            'total_sites': len(sites_summary),
            'total_preceptors': len(preceptors_summary),
            'analyzed_at': datetime.now().isoformat()
        }
    
    def _generate_ai_report(self, analysis_data: Dict[str, Any]) -> str:
        """
        Generate an AI-powered site report using Gemini.
        
        Args:
            analysis_data: Analyzed data from evaluations
            
        Returns:
            Generated report text
        """
        if not self.gemini_agent:
            # Fallback to basic report
            return self._generate_basic_report(analysis_data)
        
        try:
            sites_text = "\n".join([
                f"- {site['site_name']}: {site['total_evaluations']} evaluations, "
                f"{len(site['case_types'])} case types, {site['unique_preceptors']} preceptors"
                for site in analysis_data['sites'][:20]  # Top 20 sites
            ])
            
            preceptors_text = "\n".join([
                f"- {preceptor['preceptor_name']}: {preceptor['total_evaluations']} evaluations, "
                f"{preceptor['student_count']} students, {len(preceptor['case_types'])} case types"
                for preceptor in analysis_data['preceptors'][:20]  # Top 20 preceptors
            ])
            
            prompt = f"""Generate a comprehensive site report for a CRNA program based on evaluation data.

**Summary Statistics:**
- Total Evaluations: {analysis_data['total_evaluations']}
- Total Clinical Sites: {analysis_data['total_sites']}
- Total Preceptors: {analysis_data['total_preceptors']}

**Clinical Sites Overview:**
{sites_text}

**Preceptor Overview:**
{preceptors_text}

Generate a professional site report that includes:
1. Executive Summary: Overview of the program's clinical sites and preceptor network
2. Clinical Sites Analysis: Detailed breakdown of each site including:
   - Case types performed at each site
   - Number of evaluations
   - Preceptor representation
   - Unique characteristics or specialties
3. Preceptor Analysis: Detailed breakdown of preceptors including:
   - Number of students precepted
   - Types of cases they've supervised
   - Experience level based on evaluation volume
   - Key strengths and specializations
4. Insights and Recommendations: AI-generated insights about the clinical training network,
   distribution of cases, preceptor utilization, and recommendations for program improvement

Write in a professional, analytical tone suitable for program administrators and accreditation review.
Include specific numbers and data points throughout the report."""

            response = self.gemini_agent.model.generate_content(prompt)
            
            if response and response.text:
                return response.text.strip()
            else:
                return self._generate_basic_report(analysis_data)
                
        except Exception as e:
            print(f"⚠️ Failed to generate AI report: {e}")
            return self._generate_basic_report(analysis_data)
    
    def _generate_basic_report(self, analysis_data: Dict[str, Any]) -> str:
        """
        Generate a basic report without AI (fallback).
        
        Args:
            analysis_data: Analyzed data from evaluations
            
        Returns:
            Basic report text
        """
        report_lines = [
            "# Site Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Executive Summary",
            f"- Total Evaluations: {analysis_data['total_evaluations']}",
            f"- Total Clinical Sites: {analysis_data['total_sites']}",
            f"- Total Preceptors: {analysis_data['total_preceptors']}",
            "",
            "## Clinical Sites",
        ]
        
        for site in analysis_data['sites']:
            report_lines.append(f"\n### {site['site_name']}")
            report_lines.append(f"- Total Evaluations: {site['total_evaluations']}")
            report_lines.append(f"- Unique Preceptors: {site['unique_preceptors']}")
            report_lines.append(f"- Case Types ({len(site['case_types'])}):")
            for case_type in site['case_types'][:10]:  # Limit to 10 case types
                report_lines.append(f"  - {case_type}")
            if len(site['case_types']) > 10:
                report_lines.append(f"  ... and {len(site['case_types']) - 10} more")
        
        report_lines.append("\n## Preceptors")
        
        for preceptor in analysis_data['preceptors']:
            report_lines.append(f"\n### {preceptor['preceptor_name']}")
            report_lines.append(f"- Students Precepted: {preceptor['student_count']}")
            report_lines.append(f"- Total Evaluations: {preceptor['total_evaluations']}")
            report_lines.append(f"- Case Types ({len(preceptor['case_types'])}):")
            for case_type in preceptor['case_types'][:10]:  # Limit to 10 case types
                report_lines.append(f"  - {case_type}")
            if len(preceptor['case_types']) > 10:
                report_lines.append(f"  ... and {len(preceptor['case_types']) - 10} more")
        
        return "\n".join(report_lines)
    
    def generate_site_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive site report from all evaluations.
        
        Returns:
            Dictionary with report data and Firestore document ID
        """
        if not self.db:
            return {
                "success": False,
                "error": "Firestore not available",
                "report_id": None
            }
        
        if not self.gemini_agent:
            print("⚠️ Gemini Agent not available, generating basic report")
        
        # Update state to GENERATING
        if self.state_agent:
            try:
                from agents.state_agent import StateAgent as SA
                self.state_agent.set_agent_state("site_agent", SA.STATE_GENERATING)
            except Exception as e:
                print(f"⚠️ Failed to update state: {e}")
        
        try:
            print("\n" + "="*60)
            print("🏥 Starting Site Report Generation")
            print("="*60)
            
            # Step 1: Fetch all evaluations
            print("📊 Fetching all evaluations...")
            evaluations = self._fetch_all_evaluations()
            
            if not evaluations:
                return {
                    "success": False,
                    "error": "No evaluations found",
                    "report_id": None
                }
            
            # Step 2: Analyze evaluations
            print("🔍 Analyzing evaluation data...")
            analysis_data = self._analyze_evaluations(evaluations)
            
            print(f"✅ Analysis complete:")
            print(f"   - Sites found: {analysis_data['total_sites']}")
            print(f"   - Preceptors found: {analysis_data['total_preceptors']}")
            print(f"   - Total evaluations: {analysis_data['total_evaluations']}")
            
            # Step 3: Generate AI report
            print("🤖 Generating AI-powered report...")
            report_text = self._generate_ai_report(analysis_data)
            
            # Step 4: Compile report data
            report_data = {
                'report_text': report_text,
                'analysis_data': analysis_data,
                'generated_at': SERVER_TIMESTAMP,
                'created_at': SERVER_TIMESTAMP,
                'total_evaluations_analyzed': len(evaluations),
                'report_version': '1.0'
            }
            
            # Step 5: Save to Firestore
            print("💾 Saving report to Firestore...")
            report_ref = self.db.collection(self.sites_collection).add(report_data)[1]
            report_id = report_ref.id
            
            print(f"✅ Report saved to Firestore: {self.sites_collection}/{report_id}")
            
            # Update state to COMPLETED
            if self.state_agent:
                try:
                    from agents.state_agent import StateAgent as SA
                    self.state_agent.set_agent_result(
                        "site_agent",
                        {
                            'report_id': report_id,
                            'total_sites': analysis_data['total_sites'],
                            'total_preceptors': analysis_data['total_preceptors'],
                            'total_evaluations': analysis_data['total_evaluations']
                        },
                        SA.STATE_COMPLETED
                    )
                except Exception as e:
                    print(f"⚠️ Failed to update state result: {e}")
            
            print("="*60 + "\n")
            
            return {
                "success": True,
                "report_id": report_id,
                "report_data": report_data,
                "analysis_summary": {
                    'total_sites': analysis_data['total_sites'],
                    'total_preceptors': analysis_data['total_preceptors'],
                    'total_evaluations': analysis_data['total_evaluations']
                }
            }
            
        except Exception as e:
            print(f"\n❌ Failed to generate site report: {e}")
            import traceback
            traceback.print_exc()
            
            # Update state to ERROR
            if self.state_agent:
                try:
                    self.state_agent.set_agent_error("site_agent", str(e))
                except Exception:
                    pass
            
            return {
                "success": False,
                "error": str(e),
                "error_details": traceback.format_exc(),
                "report_id": None
            }


# Convenience function for easy importing
def create_site_agent(firestore_db: Optional[Any] = None) -> SiteAgent:
    """
    Create and return a SiteAgent instance.
    
    Args:
        firestore_db: Optional Firestore database client
    
    Returns:
        SiteAgent instance
    """
    return SiteAgent(firestore_db=firestore_db)

