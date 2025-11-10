"""
State Agent
Coordinates and tracks the state of all agents in the system.
Manages agent states in Firestore collection 'agent_states' document 'all_states'.
"""

import os
import time
import threading
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

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

# ADK imports for automated mode - lazy imports to avoid startup failures
ADK_IMPORTS_AVAILABLE = False
Runner = None
InMemorySessionService = None

try:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    ADK_IMPORTS_AVAILABLE = True
except ImportError as e:
    ADK_IMPORTS_AVAILABLE = False
    print(f"⚠️ ADK Runner imports failed (will use lazy import): {e}")

# ADK agents will be imported lazily when needed
ADK_AVAILABLE = False


class StateAgent:
    """
    Agent state coordinator.
    Manages and tracks the state of all agents in the system.
    """
    
    # Agent state constants - simplified to only IDLE and ACTIVE
    STATE_IDLE = "IDLE"
    STATE_ACTIVE = "ACTIVE"
    
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
        self.automated_mode_duration = None  # None means run indefinitely until manually stopped
        self.automated_mode_lock = threading.Lock()
        
        # ADK Runner for executing agents programmatically (lazy initialization)
        self.adk_runner = None
        self.adk_session_service = None
        self.adk_agent_map = {}  # Will be populated lazily when ADK agents are imported
        self._adk_initialized = False
        
        print(f"✅ State Agent initialized")
        print(f"   - Firestore: {'Available' if self.db else 'Not available'}")
        print(f"   - Collection: {self.collection_name}/{self.document_id}")
        print(f"   - ADK: Will initialize lazily when needed")
        print(f"   - Automated mode: Available")
    
    def _initialize_states(self):
        """Initialize the states document if it doesn't exist"""
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                # Create document with default states - all agents start as IDLE
                default_states = {
                    "evaluation_agent_state": self.STATE_IDLE,
                    "scenario_agent_state": self.STATE_IDLE,
                    "time_agent_state": self.STATE_IDLE,
                    "image_agent_state": self.STATE_IDLE,
                    "notification_agent_state": self.STATE_IDLE,
                    "coa_agent_state": self.STATE_IDLE,
                    "site_agent_state": self.STATE_IDLE,
                    "evaluation_agent_last_activity": None,
                    "scenario_agent_last_activity": None,
                    "time_agent_last_activity": None,
                    "image_agent_last_activity": None,
                    "notification_agent_last_activity": None,
                    "coa_agent_last_activity": None,
                    "site_agent_last_activity": None,
                    "evaluation_agent_last_result": None,
                    "scenario_agent_last_result": None,
                    "time_agent_last_result": None,
                    "image_agent_last_result": None,
                    "notification_agent_last_result": None,
                    "coa_agent_last_result": None,
                    "site_agent_last_result": None,
                    # Initialize logs arrays for each agent
                    "evaluation_agent_logs": [],
                    "scenario_agent_logs": [],
                    "time_agent_logs": [],
                    "image_agent_logs": [],
                    "notification_agent_logs": [],
                    "coa_agent_logs": [],
                    "site_agent_logs": [],
                    # Initialize last run time and next run time tracking
                    "evaluation_agent_last_run_time": None,
                    "evaluation_agent_next_run_time": None,
                    "scenario_agent_last_run_time": None,
                    "scenario_agent_next_run_time": None,
                    "time_agent_last_run_time": None,
                    "time_agent_next_run_time": None,
                    "image_agent_last_run_time": None,
                    "image_agent_next_run_time": None,
                    "notification_agent_last_run_time": None,
                    "notification_agent_next_run_time": None,
                    "coa_agent_last_run_time": None,
                    "coa_agent_next_run_time": None,
                    "site_agent_last_run_time": None,
                    "site_agent_next_run_time": None,
                    "automated_mode": self.AUTOMATED_MODE_OFF,
                    "automated_mode_start_time": None,
                    "automated_mode_end_time": None,
                    "created_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now(),
                    "updated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
                }
                doc_ref.set(default_states)
                print(f"✅ Initialized {self.collection_name}/{self.document_id} with default states")
            else:
                # Ensure logs arrays exist for existing documents
                doc_data = doc.to_dict()
                agents = ["evaluation_agent", "scenario_agent", "time_agent", "image_agent", 
                         "notification_agent", "coa_agent", "site_agent"]
                update_needed = False
                update_data = {}
                
                for agent_name in agents:
                    logs_key = f"{agent_name}_logs"
                    if logs_key not in doc_data or doc_data[logs_key] is None:
                        update_data[logs_key] = []
                        update_needed = True
                    
                    # Ensure last_run_time and next_run_time fields exist
                    last_run_key = f"{agent_name}_last_run_time"
                    next_run_key = f"{agent_name}_next_run_time"
                    if last_run_key not in doc_data or doc_data[last_run_key] is None:
                        update_data[last_run_key] = None
                        update_needed = True
                    if next_run_key not in doc_data or doc_data[next_run_key] is None:
                        update_data[next_run_key] = None
                        update_needed = True
                
                if update_needed:
                    doc_ref.update(update_data)
                    print(f"✅ Added missing logs arrays and run time tracking to {self.collection_name}/{self.document_id}")
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
            state: New state (e.g., STATE_IDLE, STATE_ACTIVE)
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
            # Add timeout to prevent hanging - use get() with timeout
            # Note: Firestore Python client doesn't have built-in timeout, but we can catch exceptions
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            else:
                return {}
        except Exception as e:
            print(f"⚠️ Failed to get all states: {e}")
            # Return empty dict instead of raising - allows endpoint to continue
            return {}
    
    def get_agent_last_run_time(self, agent_name: str) -> Optional[datetime]:
        """
        Get the last run time for an agent from Firestore.
        
        Args:
            agent_name: Name of the agent
        
        Returns:
            Last run time as datetime (timezone-naive UTC), or None if not found
        """
        if not self.db:
            return None
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            
            if doc.exists:
                last_run_key = f"{agent_name}_last_run_time"
                last_run_value = doc.to_dict().get(last_run_key)
                
                if last_run_value is None:
                    return None
                
                # Handle Firestore Timestamp - use to_datetime() method if available
                if hasattr(last_run_value, 'to_datetime'):
                    dt = last_run_value.to_datetime()
                    # Convert to UTC and make timezone-naive
                    if dt.tzinfo:
                        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                    return dt
                elif hasattr(last_run_value, 'seconds'):
                    # Firestore Timestamp-like object - use UTC
                    from google.cloud.firestore_v1 import Timestamp
                    if isinstance(last_run_value, Timestamp):
                        dt = last_run_value.to_datetime()
                        if dt.tzinfo:
                            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                        return dt
                    else:
                        # Fallback: use UTC timestamp
                        dt = datetime.utcfromtimestamp(last_run_value.seconds)
                        return dt
                # Handle dict with seconds
                elif isinstance(last_run_value, dict) and 'seconds' in last_run_value:
                    dt = datetime.utcfromtimestamp(last_run_value['seconds'])
                    return dt
                # Handle datetime
                elif isinstance(last_run_value, datetime):
                    dt = last_run_value
                    # Convert to UTC and make timezone-naive
                    if dt.tzinfo:
                        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                    return dt
                
            return None
        except Exception as e:
            print(f"⚠️ Failed to get last run time for {agent_name}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_agent_next_run_time(self, agent_name: str) -> Optional[datetime]:
        """
        Get the next run time for an agent from Firestore.
        Public method that wraps _get_agent_next_run_time.
        
        Args:
            agent_name: Name of the agent
        
        Returns:
            Next run time as datetime, or None if not found
        """
        return self._get_agent_next_run_time(agent_name)
    
    def _calculate_next_run_time(self, agent_name: str, last_run_time: Optional[datetime] = None) -> Optional[datetime]:
        """
        Calculate the next run time for an agent based on its schedule.
        
        Args:
            agent_name: Name of the agent
            last_run_time: Optional last run time (defaults to now if None)
        
        Returns:
            Next run time as datetime, or None if cannot be calculated
        """
        if last_run_time is None:
            last_run_time = datetime.utcnow()
        
        # Agent schedules from AGENT_RUNTIMES.md
        # Safety Agent = notification_agent (Run right after Evaluation Agent runs)
        # Scenario Agent (Run after Safety Agent runs)
        # Evaluation Agent (Run every 5 mins)
        # Site Agent (Run every 1 hours)
        # COA Agent (Run every 2 hours)
        # Time Agent (Run right after COA Agent runs)
        schedules = {
            "evaluation_agent": timedelta(minutes=5),  # Run every 5 mins
            "site_agent": timedelta(hours=1),  # Run every 1 hours
            "coa_agent": timedelta(hours=2),  # Run every 2 hours
            # These are handled specially - they run after other agents
            "notification_agent": None,  # Safety Agent: Runs right after Evaluation Agent
            "scenario_agent": None,  # Runs after Safety Agent (notification_agent)
            "time_agent": None,  # Manual execution only - removed from automated scheduling
            "image_agent": None,  # No schedule specified, runs on demand
        }
        
        # For agents with fixed schedules
        if agent_name in schedules and schedules[agent_name] is not None:
            return last_run_time + schedules[agent_name]
        
        # For agents that run after other agents (dependent agents)
        # These are scheduled dynamically when their parent agent completes
        # For now, return None - they'll be scheduled in set_agent_result
        if agent_name == "notification_agent":
            # Notification Agent runs right after Evaluation Agent completes
            # This is handled in set_agent_result when evaluation_agent completes
            return None
        
        if agent_name == "scenario_agent":
            # Scenario Agent runs right after Notification Agent completes
            # This is handled in set_agent_result when notification_agent completes
            return None
        
        if agent_name == "time_agent":
            # Time Agent is manual execution only - removed from automated scheduling
            return None
        
        # For image_agent or unknown agents, return None (no schedule)
        return None
    
    def _get_agent_next_run_time(self, agent_name: str) -> Optional[datetime]:
        """
        Get the next run time for an agent from Firestore.
        
        Args:
            agent_name: Name of the agent
        
        Returns:
            Next run time as datetime (timezone-naive UTC), or None if not found
        """
        if not self.db:
            return None
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            
            if doc.exists:
                next_run_key = f"{agent_name}_next_run_time"
                next_run_value = doc.to_dict().get(next_run_key)
                
                if next_run_value is None:
                    return None
                
                # Handle Firestore Timestamp - use to_datetime() method if available
                if hasattr(next_run_value, 'to_datetime'):
                    dt = next_run_value.to_datetime()
                    # Convert to UTC and make timezone-naive
                    if dt.tzinfo:
                        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                    return dt
                elif hasattr(next_run_value, 'seconds'):
                    # Firestore Timestamp-like object - use UTC
                    from google.cloud.firestore_v1 import Timestamp
                    if isinstance(next_run_value, Timestamp):
                        dt = next_run_value.to_datetime()
                        if dt.tzinfo:
                            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                        return dt
                    else:
                        # Fallback: use UTC timestamp
                        dt = datetime.utcfromtimestamp(next_run_value.seconds)
                        return dt
                # Handle dict with seconds
                elif isinstance(next_run_value, dict) and 'seconds' in next_run_value:
                    dt = datetime.utcfromtimestamp(next_run_value['seconds'])
                    return dt
                # Handle datetime
                elif isinstance(next_run_value, datetime):
                    dt = next_run_value
                    # Convert to UTC and make timezone-naive
                    if dt.tzinfo:
                        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                    return dt
                
            return None
        except Exception as e:
            print(f"⚠️ Failed to get next run time for {agent_name}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
            state: Optional state to set (defaults to STATE_IDLE)
        
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
            
            # Update last run time and calculate next run time
            now = datetime.utcnow()  # Use UTC for consistency with Firestore timestamps
            update_data[f"{agent_name}_last_run_time"] = SERVER_TIMESTAMP if SERVER_TIMESTAMP else now
            next_run_time = self._calculate_next_run_time(agent_name, now)
            if next_run_time:
                update_data[f"{agent_name}_next_run_time"] = next_run_time
            
            # Set state if provided, otherwise default to IDLE (work is done)
            if state:
                update_data[f"{agent_name}_state"] = state
            else:
                update_data[f"{agent_name}_state"] = self.STATE_IDLE
            
            doc_ref.update(update_data)
            print(f"✅ Stored result for {agent_name}")
            
            # If this agent completion triggers another agent, schedule that agent immediately
            # State Agent handles all scheduling - this is the single source of truth
            if agent_name == "evaluation_agent":
                # Notification Agent runs right after Evaluation Agent completes
                notification_next_run = datetime.utcnow() + timedelta(seconds=5)  # Run in 5 seconds
                doc_ref.update({
                    "notification_agent_next_run_time": notification_next_run
                })
                self.append_agent_log("notification_agent", f"Scheduled to run after evaluation_agent completes")
                print(f"📅 Scheduled notification_agent to run at {notification_next_run}")
            elif agent_name == "notification_agent":
                # Scenario Agent runs right after Notification Agent completes
                scenario_next_run = datetime.utcnow() + timedelta(seconds=5)  # Run in 5 seconds
                doc_ref.update({
                    "scenario_agent_next_run_time": scenario_next_run
                })
                self.append_agent_log("scenario_agent", f"Scheduled to run after notification_agent completes")
                print(f"📅 Scheduled scenario_agent to run at {scenario_next_run}")
            # Note: time_agent is manual execution only - no longer scheduled automatically after coa_agent
            
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
                f"{agent_name}_state": self.STATE_IDLE,  # Set to IDLE after error (work is done)
                f"{agent_name}_last_error": error_data,
                f"{agent_name}_last_activity": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now(),
                "updated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
            }
            
            # Update last run time and calculate next run time even on error
            # This ensures the agent will retry on its schedule
            now = datetime.utcnow()  # Use UTC for consistency with Firestore timestamps
            update_data[f"{agent_name}_last_run_time"] = SERVER_TIMESTAMP if SERVER_TIMESTAMP else now
            next_run_time = self._calculate_next_run_time(agent_name, now)
            if next_run_time:
                update_data[f"{agent_name}_next_run_time"] = next_run_time
            
            doc_ref.update(update_data)
            print(f"⚠️ {agent_name} error recorded, state set to IDLE: {error_message}")
            if next_run_time:
                print(f"📅 {agent_name} will retry at {next_run_time}")
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
    
    def append_agent_log(
        self,
        agent_name: str,
        message: str,
        max_entries: int = 200
    ) -> bool:
        """
        Append a log entry to an agent's logs array.
        Automatically maintains max_entries limit by removing oldest entries.
        
        Args:
            agent_name: Name of the agent (e.g., "evaluation_agent", "scenario_agent")
            message: Log message to append
            max_entries: Maximum number of log entries to keep (default: 200)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            print(f"⚠️ Cannot append log for {agent_name}: Firestore not available")
            return False
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                print(f"⚠️ Document {self.collection_name}/{self.document_id} does not exist")
                return False
            
            # Get current logs
            logs_key = f"{agent_name}_logs"
            current_logs = doc.to_dict().get(logs_key, [])
            if current_logs is None:
                current_logs = []
            
            # Create log entry with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] {message}"
            
            # Append new log entry
            current_logs.append(log_entry)
            
            # Trim to max_entries (keep most recent)
            if len(current_logs) > max_entries:
                current_logs = current_logs[-max_entries:]
            
            # Update document
            doc_ref.update({
                logs_key: current_logs,
                "updated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
            })
            
            return True
            
        except Exception as e:
            print(f"⚠️ Failed to append log for {agent_name}: {e}")
            return False
    
    def get_agent_logs(
        self,
        agent_name: str,
        limit: Optional[int] = None
    ) -> List[str]:
        """
        Get log entries for an agent.
        
        Args:
            agent_name: Name of the agent
            limit: Optional limit on number of log entries to return (most recent first)
        
        Returns:
            List of log entries (most recent last)
        """
        if not self.db:
            return []
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            
            if doc.exists:
                logs_key = f"{agent_name}_logs"
                logs = doc.to_dict().get(logs_key, [])
                if logs is None:
                    return []
                
                # Return most recent entries if limit specified
                if limit and limit > 0:
                    return logs[-limit:]
                return logs
            else:
                return []
        except Exception as e:
            print(f"⚠️ Failed to get logs for {agent_name}: {e}")
            return []
    
    def clear_agent_logs(self, agent_name: str) -> bool:
        """
        Clear all logs for an agent.
        
        Args:
            agent_name: Name of the agent
        
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc_ref.update({
                f"{agent_name}_logs": [],
                "updated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
            })
            return True
        except Exception as e:
            print(f"⚠️ Failed to clear logs for {agent_name}: {e}")
            return False
    
    def start_automated_mode(self, duration_minutes: Optional[int] = None) -> bool:
        """
        Start automated mode - agents will run automatically.
        
        Args:
            duration_minutes: How long to run automated mode (None = run indefinitely until manually stopped)
        
        Returns:
            True if started successfully, False otherwise
        """
        with self.automated_mode_lock:
            if self.automated_mode_active:
                print("⚠️ Automated mode is already running")
                return False
            
            self.automated_mode_active = True
            self.automated_mode_start_time = datetime.now()
            self.automated_mode_duration = duration_minutes * 60 if duration_minutes else None
            
            # Update Firestore
            if self.db:
                try:
                    doc_ref = self.db.collection(self.collection_name).document(self.document_id)
                    update_data = {
                        "automated_mode": self.AUTOMATED_MODE_ON,
                        "automated_mode_start_time": SERVER_TIMESTAMP if SERVER_TIMESTAMP else self.automated_mode_start_time,
                        "updated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
                    }
                    # Only set end_time if duration is specified
                    if self.automated_mode_duration:
                        update_data["automated_mode_end_time"] = SERVER_TIMESTAMP if SERVER_TIMESTAMP else (self.automated_mode_start_time + timedelta(seconds=self.automated_mode_duration))
                    else:
                        update_data["automated_mode_end_time"] = None  # No end time = runs indefinitely
                    
                    doc_ref.update(update_data)
                except Exception as e:
                    print(f"⚠️ Failed to update automated mode in Firestore: {e}")
            
            if duration_minutes:
                print(f"🤖 Automated mode STARTED - will run for {duration_minutes} minutes")
                # Start timer to stop automated mode
                self.automated_mode_timer = threading.Timer(
                    self.automated_mode_duration,
                    self._stop_automated_mode_timer
                )
                self.automated_mode_timer.start()
            else:
                print(f"🤖 Automated mode STARTED - will run indefinitely until manually stopped")
                self.automated_mode_timer = None  # No timer = runs forever
            
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
    
    def _initialize_adk(self):
        """Lazy initialization of ADK agents - only called when needed"""
        if self._adk_initialized:
            return True
        
        if not ADK_IMPORTS_AVAILABLE or not Runner or not InMemorySessionService:
            print("⚠️ ADK Runner not available - automated mode will use legacy agents")
            return False
        
        try:
            # Lazy import ADK agents
            from agent import root_agent
            from agents.evaluations_agent import evaluation_agent
            from agents.notification_agent import notification_agent
            from agents.scenario_agent import scenario_agent
            from agents.time_agent import time_agent
            
            # Initialize session service and runner
            self.adk_session_service = InMemorySessionService()
            self.adk_runner = Runner(
                app_name="precepgo-adk-panel-automated",
                agent=root_agent,
                session_service=self.adk_session_service
            )
            
            # Map agent names to ADK agent instances and prompts
            self.adk_agent_map = {
                "evaluation_agent": (evaluation_agent, "Create an evaluation"),
                "notification_agent": (notification_agent, "Check for dangerous ratings and send notifications"),
                "scenario_agent": (scenario_agent, "Generate a learning scenario"),
                "time_agent": (time_agent, "Calculate time savings"),
                # Note: site_agent and coa_agent are not yet converted to ADK
                # They will need to be converted or handled differently
            }
            
            self._adk_initialized = True
            print("✅ ADK Runner and agents initialized successfully")
            return True
        except ImportError as e:
            print(f"⚠️ ADK agent imports failed: {e}")
            return False
        except Exception as e:
            print(f"⚠️ Failed to initialize ADK: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _should_agent_run(self, agent_name: str) -> bool:
        """
        Check if an agent should run based on its next_run_time.
        SIMPLIFIED: State Agent is the single source of truth for scheduling.
        
        Args:
            agent_name: Name of the agent
        
        Returns:
            True if agent should run now, False otherwise
        """
        if not self.db:
            return False
        
        try:
            # Don't run if already ACTIVE
            agent_state = self.get_agent_state(agent_name)
            if agent_state == self.STATE_ACTIVE:
                return False
            
            # Get next run time from Firestore
            next_run_time = self._get_agent_next_run_time(agent_name)
            now = datetime.utcnow()
            
            # If no next_run_time set, this is the first run - schedule it now
            if next_run_time is None:
                # Check if agent has run before
                last_run_time = self.get_agent_last_run_time(agent_name)
                
                if last_run_time is None:
                    # First time running - run immediately and schedule next
                    print(f"🔄 {agent_name} first run - executing now")
                    return True
                else:
                    # Has run before but no next_run_time - calculate it
                    next_run_time = self._calculate_next_run_time(agent_name, last_run_time)
                    if next_run_time and self.db:
                        try:
                            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
                            doc_ref.update({
                                f"{agent_name}_next_run_time": next_run_time
                            })
                            print(f"📅 Scheduled {agent_name} for {next_run_time}")
                        except Exception as e:
                            print(f"⚠️ Failed to set next_run_time for {agent_name}: {e}")
                    # Don't run now if we just scheduled it
                    return False
            
            # Check if it's time to run
            should_run = now >= next_run_time
            if should_run:
                print(f"⏰ {agent_name} is due (scheduled: {next_run_time}, now: {now})")
            return should_run
            
        except Exception as e:
            print(f"⚠️ Error checking if {agent_name} should run: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _run_agent(self, agent_name: str) -> bool:
        """
        Run a single agent using ADK Runner API.
        All agents run through this method using Google ADK.
        
        Args:
            agent_name: Name of the agent to run
        
        Returns:
            True if agent ran successfully, False otherwise
        """
        # Lazy initialize ADK if not already done
        if not self._adk_initialized:
            if not self._initialize_adk():
                self.set_agent_error(agent_name, "ADK initialization failed")
                return False
        
        if not self.adk_runner:
            self.set_agent_error(agent_name, "ADK Runner not available")
            return False
        
        try:
            # Set state to ACTIVE before running
            self.set_agent_state(agent_name, self.STATE_ACTIVE)
            self.append_agent_log(agent_name, f"Triggered by State Agent scheduler (ADK)")
            
            # Get ADK agent and prompt from map
            if agent_name not in self.adk_agent_map:
                # Handle legacy agents that aren't converted yet
                if agent_name in ["site_agent", "coa_agent"]:
                    self.set_agent_error(agent_name, f"{agent_name} not yet converted to ADK - skipping")
                    return False
                else:
                    self.set_agent_error(agent_name, f"Unknown agent: {agent_name}")
                    return False
            
            adk_agent, prompt = self.adk_agent_map[agent_name]
            
            user_id = "automated-scheduler"
            app_name = f"precepgo-adk-panel-{agent_name}"
            
            # Create a Runner for this specific ADK agent
            agent_runner = Runner(
                app_name=app_name,
                agent=adk_agent,
                session_service=self.adk_session_service
            )
            
            # Run ADK agent programmatically using correct API
            # Import Content and Part for message formatting
            from google.genai import types
            
            # Create Content object for new_message
            new_message = types.Content(
                role="user",
                parts=[types.Part(text=prompt)]
            )
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                print(f"🚀 Running {agent_name} via ADK with message: '{prompt}'")
                
                # run_async() returns an async generator, consume it
                async def run_agent_async():
                    # Create session FIRST before running
                    session = await self.adk_session_service.create_session(
                        app_name=app_name,
                        user_id=user_id,
                        state={}
                    )
                    
                    result = None
                    async for event in agent_runner.run_async(
                        user_id=session.user_id,
                        session_id=session.id,
                        new_message=new_message
                    ):
                        result = event  # Collect the last event
                    
                    # Get updated session to check state
                    session = await self.adk_session_service.get_session(
                        app_name=app_name,
                        user_id=user_id,
                        session_id=session.id
                    )
                    return result, session
                
                result, session = loop.run_until_complete(run_agent_async())
            finally:
                loop.close()
            
            # Extract result from ADK response
            # ADK returns a response object - we need to check if it succeeded
            if result:
                # Check session state for success indicators
                if session and hasattr(session, 'state'):
                    # Check for document IDs or success indicators in state
                    if 'evaluation_doc_id' in session.state:
                        doc_id = session.state['evaluation_doc_id']
                        print(f"✅ {agent_name} created evaluation: {doc_id}")
                    elif 'notification_doc_id' in session.state:
                        doc_id = session.state['notification_doc_id']
                        print(f"✅ {agent_name} created notification: {doc_id}")
                    elif 'scenario_doc_id' in session.state:
                        doc_id = session.state['scenario_doc_id']
                        print(f"✅ {agent_name} created scenario: {doc_id}")
                
                # Store result
                result_data = {
                    "agent_name": agent_name,
                    "session_id": session_id,
                    "completed_at": datetime.utcnow().isoformat(),
                    "status": "success"
                }
                self.set_agent_result(agent_name, result_data)
                print(f"✅ {agent_name} completed via ADK")
                return True
            else:
                self.set_agent_error(agent_name, "ADK agent returned no result")
                return False
                
        except Exception as e:
            print(f"❌ {agent_name} error: {e}")
            import traceback
            traceback.print_exc()
            self.set_agent_error(agent_name, str(e))
            return False
    
    def _automated_mode_loop(self):
        """
        CENTRAL SCHEDULER LOOP - Uses Google ADK agents.
        This loop checks all agents' schedules every 5 seconds and triggers them when due.
        All agents run through ADK Runner API - no legacy code.
        """
        print("🔄 Starting State Agent central scheduler (ADK)...")
        print("📋 Using Google ADK agents for all execution")
        print("⏰ Checking schedules every 5 seconds")
        
        # Start time for the automated mode session
        start_time = time.time()
        
        # List of all agents to check (in priority order)
        # Schedules match AGENT_RUNTIMES.md:
        # - Evaluation Agent: Every 5 mins
        # - Site Agent: Every 1 hour
        # - COA Agent: Every 2 hours
        # - Notification Agent (Safety): After evaluation_agent
        # - Scenario Agent: After notification_agent
        # - Time Agent: Manual execution only (removed from automated scheduling)
        all_agents = [
            "evaluation_agent",    # Every 5 minutes
            "site_agent",          # Every 1 hour
            "coa_agent",           # Every 2 hours
            "notification_agent",  # After evaluation_agent (Safety Agent)
            "scenario_agent",      # After notification_agent
            # time_agent removed - manual execution only
        ]
        
        while self.automated_mode_active:
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            # Check if we've exceeded the total duration (only if duration is set)
            if self.automated_mode_duration and elapsed_time >= self.automated_mode_duration:
                print(f"⏰ Automated mode duration ({self.automated_mode_duration / 60:.1f} min) reached, stopping...")
                self._stop_automated_mode_timer()
                break
            
            try:
                # Check each agent's schedule - State Agent decides when to run
                agents_run_this_cycle = []
                for agent_name in all_agents:
                    if self._should_agent_run(agent_name):
                        agents_run_this_cycle.append(agent_name)
                        print(f"\n{'='*60}")
                        print(f"⏰ {agent_name} is due to run (Elapsed: {elapsed_time / 60:.1f} min)")
                        print(f"{'='*60}")
                        
                        # Run the agent via ADK Runner
                        self._run_agent(agent_name)
                
                if agents_run_this_cycle:
                    print(f"✅ This cycle ran: {', '.join(agents_run_this_cycle)}")
                else:
                    # Only log every 30 seconds to reduce noise
                    if int(elapsed_time) % 30 < 5:
                        print(f"⏳ Checking schedules... (Elapsed: {elapsed_time / 60:.1f} min)")
                
                # Sleep for 5 seconds before checking again (faster checks for better responsiveness)
                time.sleep(5)
                
            except Exception as e:
                print(f"❌ Error in State Agent scheduler: {e}")
                import traceback
                traceback.print_exc()
                # Continue loop despite errors
                time.sleep(5)
        
        print("🛑 State Agent central scheduler stopped")


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

