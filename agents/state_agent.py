"""
State Agent
Coordinates and tracks the state of all agents in the system.
Manages agent states in Firestore collection 'agent_states' document 'all_states'.
"""

import os
import time
import threading
from datetime import datetime, timedelta
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

# Agent imports for automated mode - use lazy imports to avoid circular dependencies
EVALUATIONS_AGENT_AVAILABLE = True  # Will check dynamically
SCENARIO_AGENT_AVAILABLE = True  # Will check dynamically

# Don't import at module level to avoid circular imports
# We'll import them dynamically in the methods when needed


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
    
    # Automated mode constants
    AUTOMATED_MODE_OFF = "OFF"
    AUTOMATED_MODE_ON = "ON"
    
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
        
        # Automated mode tracking
        self.automated_mode_active = False
        self.automated_mode_timer = None
        self.automated_mode_start_time = None
        self.automated_mode_duration = 15 * 60  # 15 minutes in seconds
        self.automated_mode_lock = threading.Lock()
        
        # Agent instances for automated mode (lazy initialization)
        self._evaluations_agent = None
        self._scenario_agent = None
        
        print(f"✅ State Agent initialized")
        print(f"   - Firestore: {'Available' if self.db else 'Not available'}")
        print(f"   - Collection: {self.collection_name}/{self.document_id}")
        print(f"   - Automated mode: Available")
    
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
                    "time_agent_state": self.STATE_IDLE,
                    "evaluation_agent_last_activity": None,
                    "scenario_agent_last_activity": None,
                    "time_agent_last_activity": None,
                    "evaluation_agent_last_result": None,
                    "scenario_agent_last_result": None,
                    "time_agent_last_result": None,
                    "automated_mode": self.AUTOMATED_MODE_OFF,
                    "automated_mode_start_time": None,
                    "automated_mode_end_time": None,
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
    
    def get_agent_result(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the last result of an agent's operation.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Result dictionary or None if not found
        """
        if not self.db:
            return None
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            
            if doc.exists:
                result_key = f"{agent_name}_last_result"
                return doc.to_dict().get(result_key)
            else:
                return None
        except Exception as e:
            print(f"⚠️ Failed to get result for {agent_name}: {e}")
            return None
    
    def get_agent_error(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the last error of an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Error dictionary or None if not found
        """
        if not self.db:
            return None
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            
            if doc.exists:
                error_key = f"{agent_name}_last_error"
                return doc.to_dict().get(error_key)
            else:
                return None
        except Exception as e:
            print(f"⚠️ Failed to get error for {agent_name}: {e}")
            return None
    
    def start_automated_mode(self, duration_minutes: int = 15) -> bool:
        """
        Start automated mode - agents will run automatically for specified duration.
        
        Args:
            duration_minutes: How long to run automated mode (default: 15 minutes)
        
        Returns:
            True if started successfully, False otherwise
        """
        with self.automated_mode_lock:
            if self.automated_mode_active:
                print("⚠️ Automated mode is already running")
                return False
            
            self.automated_mode_active = True
            self.automated_mode_start_time = datetime.now()
            self.automated_mode_duration = duration_minutes * 60
            
            # Update Firestore
            if self.db:
                try:
                    doc_ref = self.db.collection(self.collection_name).document(self.document_id)
                    doc_ref.update({
                        "automated_mode": self.AUTOMATED_MODE_ON,
                        "automated_mode_start_time": SERVER_TIMESTAMP if SERVER_TIMESTAMP else self.automated_mode_start_time,
                        "automated_mode_end_time": SERVER_TIMESTAMP if SERVER_TIMESTAMP else (self.automated_mode_start_time + timedelta(seconds=self.automated_mode_duration)),
                        "updated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
                    })
                except Exception as e:
                    print(f"⚠️ Failed to update automated mode in Firestore: {e}")
            
            print(f"🤖 Automated mode STARTED - will run for {duration_minutes} minutes")
            
            # Start timer to stop automated mode
            self.automated_mode_timer = threading.Timer(
                self.automated_mode_duration,
                self._stop_automated_mode_timer
            )
            self.automated_mode_timer.start()
            
            # Start agent coordination loop in background thread
            agent_thread = threading.Thread(target=self._automated_mode_loop, daemon=True)
            agent_thread.start()
            
            return True
    
    def stop_automated_mode(self) -> bool:
        """
        Stop automated mode manually.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        with self.automated_mode_lock:
            if not self.automated_mode_active:
                print("⚠️ Automated mode is not running")
                return False
            
            return self._stop_automated_mode_timer()
    
    def _stop_automated_mode_timer(self) -> bool:
        """Internal method to stop automated mode."""
        with self.automated_mode_lock:
            if not self.automated_mode_active:
                return False
            
            self.automated_mode_active = False
            
            # Cancel timer if still running
            if self.automated_mode_timer:
                self.automated_mode_timer.cancel()
                self.automated_mode_timer = None
            
            # Update Firestore
            if self.db:
                try:
                    doc_ref = self.db.collection(self.collection_name).document(self.document_id)
                    doc_ref.update({
                        "automated_mode": self.AUTOMATED_MODE_OFF,
                        "automated_mode_end_time": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now(),
                        "updated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
                    })
                except Exception as e:
                    print(f"⚠️ Failed to update automated mode in Firestore: {e}")
            
            elapsed = (datetime.now() - self.automated_mode_start_time).total_seconds() / 60 if self.automated_mode_start_time else 0
            print(f"🛑 Automated mode STOPPED (ran for {elapsed:.1f} minutes)")
            
            return True
    
    def is_automated_mode_active(self) -> bool:
        """Check if automated mode is currently active."""
        return self.automated_mode_active
    
    def _get_evaluations_agent(self):
        """Get or create EvaluationsAgent instance."""
        if self._evaluations_agent is None:
            try:
                from agents.evaluations_agent import EvaluationsAgent
                self._evaluations_agent = EvaluationsAgent()
            except ImportError as e:
                print(f"⚠️ Evaluations Agent import failed: {e}")
                self._evaluations_agent = None
            except Exception as e:
                print(f"⚠️ Failed to create EvaluationsAgent: {e}")
                self._evaluations_agent = None
        return self._evaluations_agent
    
    def _get_scenario_agent(self):
        """Get or create ClinicalScenarioAgent instance."""
        if self._scenario_agent is None:
            try:
                from agents.scenario_agent import ClinicalScenarioAgent
                # ClinicalScenarioAgent loads cases and patient_templates automatically if None
                self._scenario_agent = ClinicalScenarioAgent(cases=None, patient_templates=None)
            except ImportError as e:
                print(f"⚠️ Scenario Agent import failed: {e}")
                self._scenario_agent = None
            except Exception as e:
                print(f"⚠️ Failed to create ClinicalScenarioAgent: {e}")
                import traceback
                traceback.print_exc()
                self._scenario_agent = None
        return self._scenario_agent
    
    def _automated_mode_loop(self):
        """
        Main loop for automated mode - runs agents on separate 5-minute timers.
        Runs until automated_mode_active is False.
        """
        print("🔄 Starting automated mode loop...")
        
        # Individual timers for each agent (5 minutes = 300 seconds)
        agent_interval = 5 * 60  # 5 minutes
        
        # Track last run times for each agent
        eval_last_run = None
        scenario_last_run = None
        
        # Start time for the automated mode session
        start_time = time.time()
        
        while self.automated_mode_active:
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            # Check if we've exceeded the total duration (15 minutes)
            if elapsed_time >= self.automated_mode_duration:
                print(f"⏰ Automated mode duration ({self.automated_mode_duration / 60:.1f} min) reached, stopping...")
                self._stop_automated_mode_timer()
                break
            
            try:
                # Check if evaluation agent should run (every 5 minutes)
                should_run_eval = (
                    eval_last_run is None or 
                    (current_time - eval_last_run) >= agent_interval
                )
                
                if should_run_eval:
                    eval_state = self.get_agent_state("evaluation_agent")
                    if eval_state == self.STATE_COMPLETED:
                        self.set_agent_state("evaluation_agent", self.STATE_IDLE)
                        eval_state = self.STATE_IDLE
                    
                    if eval_state == self.STATE_IDLE:
                        print(f"\n{'='*60}")
                        print(f"📝 Running Evaluation Agent (Timer: {elapsed_time / 60:.1f} min elapsed)")
                        print(f"{'='*60}")
                        try:
                            eval_agent = self._get_evaluations_agent()
                            if eval_agent:
                                self.set_agent_state("evaluation_agent", self.STATE_GENERATING)
                                result = eval_agent.create_and_save_demo_evaluation()
                                self.set_agent_result("evaluation_agent", {
                                    "doc_id": result.get('firestore_doc_id'),
                                    "case_type": result.get('case_type'),
                                    "student": result.get('preceptee_user_name')
                                })
                                print(f"✅ Evaluation generated: {result.get('case_type')} for {result.get('preceptee_user_name')}")
                                eval_last_run = time.time()
                            else:
                                print("⚠️ Evaluations Agent not available")
                        except Exception as e:
                            print(f"❌ Evaluation Agent error: {e}")
                            self.set_agent_error("evaluation_agent", str(e))
                            eval_last_run = time.time()  # Still update timer even on error
                
                # Check if scenario agent should run (every 5 minutes, offset from eval)
                should_run_scenario = (
                    scenario_last_run is None or 
                    (current_time - scenario_last_run) >= agent_interval
                )
                
                if should_run_scenario:
                    scenario_state = self.get_agent_state("scenario_agent")
                    if scenario_state == self.STATE_COMPLETED:
                        self.set_agent_state("scenario_agent", self.STATE_IDLE)
                        scenario_state = self.STATE_IDLE
                    
                    if scenario_state == self.STATE_IDLE:
                        print(f"\n{'='*60}")
                        print(f"📋 Running Scenario Agent (Timer: {elapsed_time / 60:.1f} min elapsed)")
                        print(f"{'='*60}")
                        try:
                            scenario_agent = self._get_scenario_agent()
                            if scenario_agent:
                                self.set_agent_state("scenario_agent", self.STATE_GENERATING)
                                result = scenario_agent.generate_scenario()
                                self.set_agent_result("scenario_agent", {
                                    "case": result.get('case', {}).get('name'),
                                    "patient": result.get('patient', {}).get('full_name')
                                })
                                print(f"✅ Scenario generated: {result.get('case', {}).get('name')} for {result.get('patient', {}).get('full_name')}")
                                scenario_last_run = time.time()
                            else:
                                print("⚠️ Scenario Agent not available")
                        except Exception as e:
                            print(f"❌ Scenario Agent error: {e}")
                            self.set_agent_error("scenario_agent", str(e))
                            scenario_last_run = time.time()  # Still update timer even on error
                
                # Sleep for 10 seconds before checking again
                time.sleep(10)
                
            except Exception as e:
                print(f"❌ Error in automated mode loop: {e}")
                import traceback
                traceback.print_exc()
                # Continue loop despite errors
                time.sleep(10)
        
        print("🛑 Automated mode loop stopped")


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

