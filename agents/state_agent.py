"""
State Agent
Coordinates and tracks the state of all agents in the system.
Manages agent states in Firestore collection 'agent_states' document 'all_states'.
"""

import os
from datetime import datetime
from typing import Dict, Any, Optional

# Import dependencies
try:
    from firestore_service import get_firestore_service
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    print("⚠️ Firestore not available for State Agent")

try:
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP
except ImportError:
    SERVER_TIMESTAMP = None


class StateAgent:
    """
    Agent state coordinator.
    Manages and tracks the state of all agents in the system.
    """
    
    # Agent state constants
    STATE_IDLE = "IDLE"
    STATE_GENERATING = "GENERATING"
    STATE_COMPLETED = "COMPLETED"
    STATE_ERROR = "ERROR"
    STATE_PROCESSING = "PROCESSING"
    
    def __init__(self, firestore_db=None):
        """
        Initialize the State Agent.
        
        Args:
            firestore_db: Optional Firestore database client (will get from service if None)
        """
        self.collection_name = "agent_states"
        self.document_id = "all_states"
        
        # Initialize Firestore
        if firestore_db:
            self.db = firestore_db
        elif FIRESTORE_AVAILABLE:
            try:
                firestore_service = get_firestore_service(force_refresh=True)
                if firestore_service and hasattr(firestore_service, 'db'):
                    self.db = firestore_service.db
                else:
                    self.db = None
                    print("⚠️ State Agent initialized without Firestore support")
            except Exception as e:
                print(f"⚠️ State Agent Firestore initialization failed: {e}")
                self.db = None
        else:
            self.db = None
            print("⚠️ State Agent initialized without Firestore support")
        
        # Initialize default states if document doesn't exist
        if self.db:
            self._initialize_states()
        
        print(f"✅ State Agent initialized")
        print(f"   - Firestore: {'Available' if self.db else 'Not available'}")
        print(f"   - Collection: {self.collection_name}/{self.document_id}")
    
    def _initialize_states(self):
        """Initialize the states document if it doesn't exist"""
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                # Create document with default states
                default_states = {
                    "evaluation_agent_state": self.STATE_IDLE,
                    "scenario_agent_state": self.STATE_IDLE,
                    "evaluation_agent_last_activity": None,
                    "scenario_agent_last_activity": None,
                    "evaluation_agent_last_result": None,
                    "scenario_agent_last_result": None,
                    "created_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now(),
                    "updated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
                }
                doc_ref.set(default_states)
                print(f"✅ Initialized {self.collection_name}/{self.document_id} with default states")
        except Exception as e:
            print(f"⚠️ Failed to initialize states document: {e}")
    
    def set_agent_state(
        self,
        agent_name: str,
        state: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Set the state of an agent.
        
        Args:
            agent_name: Name of the agent (e.g., "evaluation_agent", "scenario_agent")
            state: New state (e.g., STATE_IDLE, STATE_GENERATING, etc.)
            metadata: Optional metadata to store with the state
        
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            print(f"⚠️ Cannot set state for {agent_name}: Firestore not available")
            return False
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            
            # Build update data
            update_data = {
                f"{agent_name}_state": state,
                f"{agent_name}_last_activity": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now(),
                "updated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
            }
            
            # Add metadata if provided
            if metadata:
                for key, value in metadata.items():
                    update_data[f"{agent_name}_{key}"] = value
            
            # Update document
            doc_ref.update(update_data)
            print(f"✅ Updated {agent_name} state to: {state}")
            return True
            
        except Exception as e:
            print(f"⚠️ Failed to set state for {agent_name}: {e}")
            return False
    
    def get_agent_state(self, agent_name: str) -> Optional[str]:
        """
        Get the current state of an agent.
        
        Args:
            agent_name: Name of the agent (e.g., "evaluation_agent", "scenario_agent")
        
        Returns:
            Current state string or None if not found
        """
        if not self.db:
            return None
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            
            if doc.exists:
                state_key = f"{agent_name}_state"
                return doc.to_dict().get(state_key)
            else:
                return None
        except Exception as e:
            print(f"⚠️ Failed to get state for {agent_name}: {e}")
            return None
    
    def get_all_states(self) -> Dict[str, Any]:
        """
        Get all agent states.
        
        Returns:
            Dictionary of all agent states
        """
        if not self.db:
            return {}
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            else:
                return {}
        except Exception as e:
            print(f"⚠️ Failed to get all states: {e}")
            return {}
    
    def set_agent_result(
        self,
        agent_name: str,
        result: Dict[str, Any],
        state: Optional[str] = None
    ) -> bool:
        """
        Store the result of an agent's last operation.
        
        Args:
            agent_name: Name of the agent
            result: Result dictionary to store
            state: Optional state to set (defaults to STATE_COMPLETED)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            
            update_data = {
                f"{agent_name}_last_result": result,
                f"{agent_name}_last_activity": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now(),
                "updated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
            }
            
            # Set state if provided
            if state:
                update_data[f"{agent_name}_state"] = state
            else:
                update_data[f"{agent_name}_state"] = self.STATE_COMPLETED
            
            doc_ref.update(update_data)
            print(f"✅ Stored result for {agent_name}")
            return True
            
        except Exception as e:
            print(f"⚠️ Failed to store result for {agent_name}: {e}")
            return False
    
    def set_agent_error(
        self,
        agent_name: str,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Set agent state to ERROR and store error information.
        
        Args:
            agent_name: Name of the agent
            error_message: Error message
            error_details: Optional error details dictionary
        
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            
            error_data = {
                "message": error_message,
                "timestamp": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
            }
            if error_details:
                error_data.update(error_details)
            
            update_data = {
                f"{agent_name}_state": self.STATE_ERROR,
                f"{agent_name}_last_error": error_data,
                f"{agent_name}_last_activity": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now(),
                "updated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
            }
            
            doc_ref.update(update_data)
            print(f"⚠️ Set {agent_name} state to ERROR: {error_message}")
            return True
            
        except Exception as e:
            print(f"⚠️ Failed to set error for {agent_name}: {e}")
            return False


# Convenience function for easy importing
def create_state_agent(firestore_db=None) -> StateAgent:
    """
    Create a State Agent instance.
    
    Args:
        firestore_db: Optional Firestore database client
    
    Returns:
        StateAgent instance
    """
    return StateAgent(firestore_db=firestore_db)

