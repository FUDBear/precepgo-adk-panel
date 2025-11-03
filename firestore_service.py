"""
Firestore Service for Agent Scenarios
Handles reading and writing scenarios to Firestore collection 'agent_scenarios'
"""

import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP


class FirestoreScenarioService:
    """
    Service for managing scenarios in Firestore.
    Uses Application Default Credentials (ADC) which automatically works in Cloud Run.
    """
    
    def __init__(self, collection_name: str = "agent_scenarios", project_id: Optional[str] = None):
        """
        Initialize Firestore client.
        
        Args:
            collection_name: Name of the Firestore collection
            project_id: Google Cloud project ID (defaults to env var or auto-detected)
        """
        try:
            # Get project ID from parameter, environment variable, or auto-detect
            # Priority: FIREBASE_PROJECT_ID > GOOGLE_CLOUD_PROJECT > gcloud config
            if project_id:
                self.project_id = project_id
            else:
                # Check FIREBASE_PROJECT_ID first (for Firestore)
                self.project_id = os.getenv("FIREBASE_PROJECT_ID")
                
                # Fallback to GOOGLE_CLOUD_PROJECT
                if not self.project_id:
                    self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
                
                # If not in env, try to detect from gcloud config
                if not self.project_id:
                    try:
                        import subprocess
                        result = subprocess.run(
                            ["gcloud", "config", "get-value", "project"],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            self.project_id = result.stdout.strip()
                    except Exception:
                        pass
            
            # Check for service account key file (for service account authentication)
            service_account_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            
            # Initialize Firestore client with project ID
            if self.project_id:
                self.db = firestore.Client(project=self.project_id)
                auth_method = "service account key" if service_account_key else "Application Default Credentials"
                print(f"✅ Firestore client initialized for project: {self.project_id}, collection: {collection_name}")
                print(f"   Authentication: {auth_method}")
            else:
                # Fallback to auto-detection
                self.db = firestore.Client()
                auth_method = "service account key" if service_account_key else "Application Default Credentials"
                print(f"✅ Firestore client initialized (auto-detected project), collection: {collection_name}")
                print(f"   Authentication: {auth_method}")
            
            self.collection_name = collection_name
            
        except Exception as e:
            print(f"⚠️ Firestore initialization failed: {e}")
            print("⚠️ Make sure you have:")
            print("   1. Set GOOGLE_CLOUD_PROJECT environment variable, OR")
            print("   2. Set up Application Default Credentials:")
            print("      gcloud auth application-default login")
            print("   3. Or ensure Cloud Run service account has Firestore permissions")
            raise
    
    def save_scenario(self, scenario_data: Dict[str, Any], doc_id: Optional[str] = None) -> str:
        """
        Save a scenario to Firestore.
        
        Args:
            scenario_data: Scenario data dictionary
            doc_id: Optional document ID (auto-generated if not provided)
            
        Returns:
            Document ID of the saved scenario
        """
        try:
            # Add metadata for audit trail
            scenario_data['created_at'] = SERVER_TIMESTAMP
            scenario_data['modified_at'] = SERVER_TIMESTAMP
            scenario_data['modified_by'] = 'precepgo-agent'
            
            # Get collection reference
            collection_ref = self.db.collection(self.collection_name)
            
            if doc_id:
                # Update existing document
                doc_ref = collection_ref.document(doc_id)
                scenario_data['modified_at'] = SERVER_TIMESTAMP
                doc_ref.set(scenario_data, merge=True)
                print(f"✅ Updated scenario in Firestore: {doc_id}")
                return doc_id
            else:
                # Create new document with auto-generated ID
                doc_ref = collection_ref.add(scenario_data)[1]
                doc_id = doc_ref.id
                print(f"✅ Saved scenario to Firestore: {doc_id}")
                return doc_id
                
        except Exception as e:
            print(f"❌ Error saving scenario to Firestore: {e}")
            raise Exception(f"Failed to save scenario to Firestore: {str(e)}")
    
    def get_scenario(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a scenario by document ID.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Scenario data dictionary or None if not found
        """
        try:
            doc_ref = self.db.collection(self.collection_name).document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            else:
                return None
                
        except Exception as e:
            print(f"❌ Error reading scenario from Firestore: {e}")
            raise Exception(f"Failed to read scenario from Firestore: {str(e)}")
    
    def list_scenarios(
        self, 
        limit: int = 50, 
        order_by: str = "created_at",
        order_direction: str = "DESCENDING"
    ) -> List[Dict[str, Any]]:
        """
        List scenarios from Firestore.
        
        Args:
            limit: Maximum number of scenarios to return
            order_by: Field to order by (default: created_at)
            order_direction: "ASCENDING" or "DESCENDING"
            
        Returns:
            List of scenario dictionaries
        """
        try:
            collection_ref = self.db.collection(self.collection_name)
            
            # Order by specified field
            if order_direction.upper() == "DESCENDING":
                query = collection_ref.order_by(order_by, direction=firestore.Query.DESCENDING).limit(limit)
            else:
                query = collection_ref.order_by(order_by, direction=firestore.Query.ASCENDING).limit(limit)
            
            docs = query.stream()
            
            scenarios = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                scenarios.append(data)
            
            print(f"✅ Retrieved {len(scenarios)} scenarios from Firestore")
            return scenarios
            
        except Exception as e:
            print(f"❌ Error listing scenarios from Firestore: {e}")
            raise Exception(f"Failed to list scenarios from Firestore: {str(e)}")
    
    def delete_scenario(self, doc_id: str) -> bool:
        """
        Delete a scenario from Firestore.
        
        Args:
            doc_id: Document ID
            
        Returns:
            True if deleted successfully
        """
        try:
            doc_ref = self.db.collection(self.collection_name).document(doc_id)
            doc_ref.delete()
            print(f"✅ Deleted scenario from Firestore: {doc_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error deleting scenario from Firestore: {e}")
            raise Exception(f"Failed to delete scenario from Firestore: {str(e)}")
    
    def get_scenarios_by_case(self, case_code: str) -> List[Dict[str, Any]]:
        """
        Get scenarios filtered by case code.
        
        Args:
            case_code: Case code to filter by
            
        Returns:
            List of matching scenarios
        """
        try:
            collection_ref = self.db.collection(self.collection_name)
            query = collection_ref.where('case.code', '==', case_code).limit(20)
            
            docs = query.stream()
            scenarios = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                scenarios.append(data)
            
            return scenarios
            
        except Exception as e:
            print(f"❌ Error querying scenarios by case: {e}")
            raise Exception(f"Failed to query scenarios: {str(e)}")
    
    def get_scenarios_by_patient(self, patient_name: str) -> List[Dict[str, Any]]:
        """
        Get scenarios filtered by patient name.
        
        Args:
            patient_name: Patient name to filter by
            
        Returns:
            List of matching scenarios
        """
        try:
            collection_ref = self.db.collection(self.collection_name)
            query = collection_ref.where('patient.name', '==', patient_name).limit(20)
            
            docs = query.stream()
            scenarios = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                scenarios.append(data)
            
            return scenarios
            
        except Exception as e:
            print(f"❌ Error querying scenarios by patient: {e}")
            raise Exception(f"Failed to query scenarios: {str(e)}")


# Global instance
_firestore_service_instance: Optional[FirestoreScenarioService] = None


def get_firestore_service(project_id: Optional[str] = None, force_refresh: bool = False) -> Optional[FirestoreScenarioService]:
    """
    Get or create Firestore service instance.
    
    Args:
        project_id: Optional project ID override (defaults to env var or auto-detected)
        force_refresh: If True, recreate the service instance even if cached
    
    Returns:
        FirestoreScenarioService instance or None if unavailable
    """
    global _firestore_service_instance
    
    # Force refresh if requested or if project_id is provided and different
    if force_refresh or (project_id and _firestore_service_instance and hasattr(_firestore_service_instance, 'project_id') and _firestore_service_instance.project_id != project_id):
        _firestore_service_instance = None
    
    if _firestore_service_instance is None:
        try:
            # Use provided project_id, or check environment variable
            # Priority: FIREBASE_PROJECT_ID > GOOGLE_CLOUD_PROJECT
            if not project_id:
                project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
            
            _firestore_service_instance = FirestoreScenarioService(project_id=project_id)
        except Exception as e:
            print(f"⚠️ Firestore service not available: {e}")
            return None
    return _firestore_service_instance

