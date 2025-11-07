"""
Time Savings Analytics Agent
Tracks time savings achieved by AI agents vs manual processes.
Calculates analytics, generates insights, and provides reporting.
"""

import os
import json
import time
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Gemini API imports
try:
    import google.generativeai as genai
    from gemini_agent import GeminiAgent, MODEL_GEMINI_FLASH
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini not available for Time Savings Agent")

# Import dependencies
try:
    from firestore_service import get_firestore_service
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    print("⚠️ Firestore not available for Time Savings Agent")


class TaskType(str, Enum):
    """Task types that can be tracked"""
    EVALUATION_COMPLETION = "evaluation_completion"
    ADMIN_REVIEW = "admin_review"
    PROBLEM_IDENTIFICATION = "problem_identification"
    TEST_GENERATION = "test_generation"
    COA_COMPLIANCE_CHECK = "coa_compliance_check"
    SCENARIO_GENERATION = "scenario_generation"
    NOTIFICATION_CHECK = "notification_check"


class Timeframe(str, Enum):
    """Time periods for analytics"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    SEMESTER = "semester"
    ALL_TIME = "all_time"


def _load_task_benchmarks() -> Dict[str, Dict[str, Any]]:
    """
    Load task time benchmarks from JSON file.
    
    Returns:
        Dictionary mapping task IDs to benchmark data
    """
    try:
        benchmarks_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'task-time-benchmarks.json')
        benchmarks_path = os.path.normpath(benchmarks_path)
        
        with open(benchmarks_path, 'r') as f:
            data = json.load(f)
        
        # Create a dictionary mapping taskId to benchmark data
        benchmarks = {}
        for benchmark in data.get('taskBenchmarks', []):
            benchmarks[benchmark['taskId']] = benchmark
        
        print(f"✅ Loaded {len(benchmarks)} task benchmarks from JSON")
        return benchmarks
    except FileNotFoundError:
        print(f"⚠️ Benchmarks file not found at {benchmarks_path}, using defaults")
        return {}
    except Exception as e:
        print(f"⚠️ Failed to load benchmarks: {e}")
        return {}


def _get_task_id_mapping(task_type: TaskType) -> str:
    """
    Map TaskType enum to taskId in benchmarks JSON.
    
    Args:
        task_type: TaskType enum value
    
    Returns:
        taskId string from benchmarks JSON
    """
    mapping = {
        TaskType.EVALUATION_COMPLETION: "evaluation_completion",
        TaskType.ADMIN_REVIEW: "admin_review_filing",
        TaskType.PROBLEM_IDENTIFICATION: "problem_identification",
        TaskType.TEST_GENERATION: "test_question_generation",
        TaskType.COA_COMPLIANCE_CHECK: "coa_standards_compliance",
        TaskType.SCENARIO_GENERATION: "scenario_generation",  # Fixed: now maps to correct benchmark
        TaskType.NOTIFICATION_CHECK: "notification_check",  # Fixed: now maps to correct benchmark
    }
    return mapping.get(task_type, "evaluation_completion")


# Load benchmarks at module level
_TASK_BENCHMARKS = _load_task_benchmarks()


def _get_baseline_time(task_type: TaskType) -> float:
    """
    Get baseline manual time for a task type from benchmarks.
    
    Args:
        task_type: TaskType enum value
    
    Returns:
        Baseline manual time in minutes
    """
    task_id = _get_task_id_mapping(task_type)
    benchmark = _TASK_BENCHMARKS.get(task_id)
    
    if benchmark and 'manualTime' in benchmark:
        return benchmark['manualTime'].get('averageMinutes', 0)
    
    # Fallback to realistic hardcoded values if benchmark not found (should rarely be used)
    fallback = {
        TaskType.EVALUATION_COMPLETION: 50.0,  # Realistic: 50 min manual
        TaskType.ADMIN_REVIEW: 25.0,  # Realistic: 25 min manual
        TaskType.PROBLEM_IDENTIFICATION: 85.0,  # Realistic: 85 min manual
        TaskType.TEST_GENERATION: 35.0,  # Realistic: 35 min manual
        TaskType.COA_COMPLIANCE_CHECK: 65.0,  # Realistic: 65 min manual
        TaskType.SCENARIO_GENERATION: 140.0,  # Realistic: 140 min manual
        TaskType.NOTIFICATION_CHECK: 45.0,  # Realistic: 45 min manual
    }
    return fallback.get(task_type, 0)


def _get_ai_assisted_time(task_type: TaskType) -> float:
    """
    Get AI-assisted time for a task type from benchmarks.
    
    Args:
        task_type: TaskType enum value
    
    Returns:
        AI-assisted time in minutes
    """
    task_id = _get_task_id_mapping(task_type)
    benchmark = _TASK_BENCHMARKS.get(task_id)
    
    if benchmark and 'aiAssistedTime' in benchmark:
        return benchmark['aiAssistedTime'].get('averageMinutes', 0)
    
    # Fallback if benchmark not found
    return 0


def _get_expected_time_savings(task_type: TaskType) -> float:
    """
    Get expected time savings for a task type from benchmarks.
    
    Args:
        task_type: TaskType enum value
    
    Returns:
        Expected time savings in minutes
    """
    task_id = _get_task_id_mapping(task_type)
    benchmark = _TASK_BENCHMARKS.get(task_id)
    
    if benchmark and 'timeSavingsMinutes' in benchmark:
        return benchmark['timeSavingsMinutes']
    
    # Calculate from baseline and AI-assisted times
    baseline = _get_baseline_time(task_type)
    ai_assisted = _get_ai_assisted_time(task_type)
    return max(0, baseline - ai_assisted)


# Role-based hourly rates (in dollars) - more realistic
HOURLY_RATES = {
    "admin": 35,
    "faculty": 50,
    "preceptor": 45,
    "program_director": 65,
}

# Weighted average for general calculations (based on task distribution)
# Tasks are roughly: 40% admin, 30% faculty, 20% preceptor, 10% program_director
AVERAGE_HOURLY_RATE = (35 * 0.4 + 50 * 0.3 + 45 * 0.2 + 65 * 0.1)  # ~43.75/hr
HOURS_PER_WEEK = 40  # Full-time equivalent


class TimeSavingsAgent:
    """
    Agent for tracking and analyzing time savings from AI automation.
    """
    
    def __init__(self, firestore_db=None, state_agent=None):
        """
        Initialize the Time Savings Agent.
        
        Args:
            firestore_db: Optional Firestore database client
            state_agent: Optional StateAgent instance for tracking agent state
        """
        self.collection_name = "time_savings_tasks"
        self.baselines_collection = "time_savings_baselines"
        self.summaries_collection = "time_savings_summaries"
        self.estimates_collection = "agent_time"
        self.estimates_document = "time_saved"
        
        # Store state agent reference
        self.state_agent = state_agent
        
        # Initialize Firestore
        if firestore_db:
            self.db = firestore_db
        elif FIRESTORE_AVAILABLE:
            try:
                firestore_service = get_firestore_service(force_refresh=True)
                if firestore_service and hasattr(firestore_service, 'db'):
                    self.db = firestore_service.db
                else:
                    project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
                    if project_id:
                        self.db = firestore.Client(project=project_id)
                    else:
                        self.db = firestore.Client()
            except Exception as e:
                print(f"⚠️ Time Savings Agent Firestore initialization failed: {e}")
                self.db = None
        else:
            self.db = None
        
        # Initialize Gemini Agent for insights
        self.gemini_agent = None
        if GEMINI_AVAILABLE:
            try:
                self.gemini_agent = GeminiAgent(model_name=MODEL_GEMINI_FLASH)
                print("   - Gemini Agent: ✅")
            except Exception as e:
                print(f"   - Gemini Agent: ⚠️ Failed to initialize: {e}")
                self.gemini_agent = None
        
        # Initialize baselines if they don't exist
        if self.db:
            self._initialize_baselines()
            # Write initial analytics data to time_saved document
            try:
                self._write_initial_analytics()
            except Exception as e:
                print(f"⚠️ Failed to write initial analytics: {e}")
        
        # Scheduled analytics tracking
        self.scheduled_analytics_running = False
        self.scheduled_analytics_thread = None
        self.scheduled_analytics_interval = 60 * 60  # 1 hour in seconds
        
        print(f"✅ Time Savings Agent initialized")
        print(f"   - Firestore: {'Available' if self.db else 'Not available'}")
        print(f"   - Gemini Insights: {'Available' if self.gemini_agent else 'Not available'}")
    
    def _initialize_baselines(self):
        """Initialize baseline benchmarks in Firestore if they don't exist"""
        if not self.db:
            return
        
        try:
            baselines_ref = self.db.collection(self.baselines_collection).document("defaults")
            baselines_doc = baselines_ref.get()
            
            if not baselines_doc.exists:
                baseline_data = {}
                # Load benchmarks from JSON
                for task_type in TaskType:
                    task_id = _get_task_id_mapping(task_type)
                    benchmark = _TASK_BENCHMARKS.get(task_id)
                    
                    if benchmark:
                        baseline_data[task_type.value] = {
                            "average_manual_time_minutes": benchmark['manualTime'].get('averageMinutes', 0),
                            "ai_assisted_time_minutes": benchmark['aiAssistedTime'].get('averageMinutes', 0),
                            "expected_time_savings_minutes": benchmark.get('timeSavingsMinutes', 0),
                            "source": "task-time-benchmarks.json",
                            "updated_at": SERVER_TIMESTAMP
                        }
                    else:
                        # Fallback
                        baseline_data[task_type.value] = {
                            "average_manual_time_minutes": _get_baseline_time(task_type),
                            "ai_assisted_time_minutes": _get_ai_assisted_time(task_type),
                            "expected_time_savings_minutes": _get_expected_time_savings(task_type),
                            "source": "fallback",
                            "updated_at": SERVER_TIMESTAMP
                        }
                
            print(f"✅ Initialized baseline benchmarks")
        except Exception as e:
            print(f"⚠️ Failed to initialize baselines: {e}")
    
    def _write_initial_analytics(self):
        """
        Write initial analytics data to time_saved document on initialization.
        This ensures the document exists with all required fields.
        """
        if not self.db:
            return
        
        try:
            # Calculate all timeframes
            all_time_savings = self.calculate_savings(Timeframe.ALL_TIME, update_time_saved=False)
            daily_savings = self.calculate_savings(Timeframe.DAILY, update_time_saved=False)
            weekly_savings = self.calculate_savings(Timeframe.WEEKLY, update_time_saved=False)
            monthly_savings = self.calculate_savings(Timeframe.MONTHLY, update_time_saved=False)
            semester_savings = self.calculate_savings(Timeframe.SEMESTER, update_time_saved=False)
            
            # Generate insights if available
            insights = None
            if self.gemini_agent:
                try:
                    insights = self.generate_insights(all_time_savings)
                except Exception as e:
                    print(f"⚠️ Failed to generate initial insights: {e}")
            
            # Write all analytics data
            self._write_analytics_to_time_saved(
                all_time_savings=all_time_savings,
                daily_savings=daily_savings,
                weekly_savings=weekly_savings,
                monthly_savings=monthly_savings,
                semester_savings=semester_savings,
                insights=insights
            )
            
            print("✅ Initial analytics data written to time_saved document")
        except Exception as e:
            print(f"⚠️ Failed to write initial analytics: {e}")
            import traceback
            traceback.print_exc()
    
    def log_task_start(
        self,
        task_type: TaskType,
        user_id: str,
        is_ai_assisted: bool = True,
        agent_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log the start of a task and return a task ID for tracking.
        
        Args:
            task_type: Type of task being performed
            user_id: ID of the user performing the task
            is_ai_assisted: Whether AI is assisting (default: True)
            agent_name: Name of the agent performing the task (optional)
            metadata: Additional metadata about the task (optional)
        
        Returns:
            Task ID string for tracking completion
        """
        if not self.db:
            # Return a dummy ID if Firestore isn't available
            return f"dummy_{int(time.time())}"
        
        try:
            task_data = {
                "task_type": task_type.value,
                "user_id": user_id,
                "is_ai_assisted": is_ai_assisted,
                "agent_name": agent_name or "unknown",
                "start_time": SERVER_TIMESTAMP,
                "status": "in_progress",
                "metadata": metadata or {}
            }
            
            doc_ref = self.db.collection(self.collection_name).document()
            task_id = doc_ref.id
            doc_ref.set(task_data)
            
            print(f"📊 Task started: {task_type.value} (ID: {task_id[:8]}...)")
            return task_id
            
        except Exception as e:
            print(f"⚠️ Failed to log task start: {e}")
            return f"error_{int(time.time())}"
    
    def log_task_complete(
        self,
        task_id: str,
        duration_minutes: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log the completion of a task.
        
        Args:
            task_id: Task ID returned from log_task_start
            duration_minutes: Optional duration override (if not provided, calculated from start_time)
            metadata: Additional metadata about completion (optional)
        
        Returns:
            True if logged successfully, False otherwise
        """
        if not self.db:
            return False
        
        try:
            task_ref = self.db.collection(self.collection_name).document(task_id)
            task_doc = task_ref.get()
            
            if not task_doc.exists:
                print(f"⚠️ Task {task_id} not found")
                return False
            
            task_data = task_doc.to_dict()
            
            # Calculate duration if not provided
            if duration_minutes is None:
                start_time = task_data.get("start_time")
                if isinstance(start_time, datetime):
                    duration_seconds = (datetime.now() - start_time).total_seconds()
                    duration_minutes = duration_seconds / 60.0
                else:
                    duration_minutes = 0.0
            
            # Get baseline time for comparison
            task_type = TaskType(task_data.get("task_type"))
            baseline_minutes = _get_baseline_time(task_type)
            expected_savings_minutes = _get_expected_time_savings(task_type)
            
            # Estimate time saved using Gemini Flash (only if AI-assisted)
            time_saved_minutes = 0.0
            estimated_by_gemini = False
            if task_data.get("is_ai_assisted", False):
                # Use Gemini Flash to estimate time saved
                gemini_estimate = self._estimate_time_saved_with_gemini(
                    task_type=task_type,
                    duration_minutes=duration_minutes,
                    baseline_minutes=baseline_minutes,
                    expected_savings_minutes=expected_savings_minutes,
                    agent_name=task_data.get("agent_name", "unknown"),
                    metadata=task_data.get("metadata", {})
                )
                
                if gemini_estimate is not None:
                    time_saved_minutes = gemini_estimate
                    estimated_by_gemini = True
                else:
                    # Fallback: Use expected savings from benchmarks if actual duration is close to AI-assisted time
                    ai_assisted_minutes = _get_ai_assisted_time(task_type)
                    # If duration is close to AI-assisted time, use expected savings
                    if abs(duration_minutes - ai_assisted_minutes) <= 2.0:
                        time_saved_minutes = expected_savings_minutes
                    else:
                        # Otherwise calculate from baseline
                        time_saved_minutes = max(0, baseline_minutes - duration_minutes)
            
            # Update task document
            update_data = {
                "end_time": SERVER_TIMESTAMP,
                "status": "completed",
                "duration_minutes": duration_minutes,
                "baseline_minutes": baseline_minutes,
                "time_saved_minutes": time_saved_minutes,
                "time_saved_hours": time_saved_minutes / 60.0,
                "estimated_by_gemini": estimated_by_gemini,
            }
            
            if metadata:
                if "metadata" in task_data:
                    task_data["metadata"].update(metadata)
                else:
                    update_data["metadata"] = metadata
            
            task_ref.update(update_data)
            
            print(f"✅ Task completed: {task_data.get('task_type')} - Saved {time_saved_minutes:.1f} minutes")
            
            # Write estimate to agent_time/time_saved document
            if time_saved_minutes > 0:
                try:
                    self._write_time_saved_estimate(
                        task_type=task_type,
                        time_saved_minutes=time_saved_minutes,
                        duration_minutes=duration_minutes,
                        baseline_minutes=baseline_minutes,
                        agent_name=task_data.get("agent_name", "unknown"),
                        user_id=task_data.get("user_id", "unknown"),
                        estimated_by_gemini=estimated_by_gemini
                    )
                except Exception as e:
                    print(f"⚠️ Failed to write time saved estimate: {e}")
            
            # Trigger summary update (async, don't block)
            try:
                self._update_summaries_async(task_data, time_saved_minutes)
            except Exception as e:
                print(f"⚠️ Failed to update summaries: {e}")
            
            return True
            
        except Exception as e:
            print(f"⚠️ Failed to log task completion: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _estimate_time_saved_with_gemini(
        self,
        task_type: TaskType,
        duration_minutes: float,
        baseline_minutes: float,
        expected_savings_minutes: float,
        agent_name: str,
        metadata: Dict[str, Any]
    ) -> Optional[float]:
        """
        Use Gemini Flash to estimate time saved based on task details.
        
        Args:
            task_type: Type of task performed
            duration_minutes: Actual time taken
            baseline_minutes: Baseline manual time estimate
            agent_name: Name of the agent that performed the task
            metadata: Additional metadata about the task
        
        Returns:
            Estimated time saved in minutes, or None if estimation fails
        """
        if not self.gemini_agent:
            return None
        
        try:
            prompt = f"""You are analyzing time savings for a nursing education program. Estimate how much time was saved by using AI automation versus manual processes.

Task Type: {task_type.value.replace('_', ' ').title()}
Agent Used: {agent_name}
Actual Duration: {duration_minutes:.1f} minutes
Baseline Manual Time: {baseline_minutes:.1f} minutes
Expected Time Savings (from benchmarks): {expected_savings_minutes:.1f} minutes

Task Details:
{json.dumps(metadata, indent=2) if metadata else 'No additional details'}

Consider:
- The complexity of the task
- How much AI automation helped vs manual work
- Typical manual processes for this type of task
- The baseline estimate of {baseline_minutes:.1f} minutes for manual work
- The expected savings of {expected_savings_minutes:.1f} minutes based on benchmarks

Respond with ONLY a single number representing the estimated time saved in minutes (e.g., "12.5" or "8.2"). 
Do not include any text, explanations, or formatting - just the number."""

            response = self.gemini_agent.model.generate_content(prompt)
            
            if response and response.text:
                # Extract number from response
                text = response.text.strip()
                # Remove any non-numeric characters except decimal point
                numbers = re.findall(r'\d+\.?\d*', text)
                if numbers:
                    estimated_minutes = float(numbers[0])
                    # Ensure it's reasonable (between 0 and baseline)
                    estimated_minutes = max(0, min(estimated_minutes, baseline_minutes))
                    print(f"🤖 Gemini Flash estimated {estimated_minutes:.1f} minutes saved")
                    return estimated_minutes
                else:
                    print(f"⚠️ Could not parse Gemini estimate: {text}")
                    return None
            else:
                return None
                
        except Exception as e:
            print(f"⚠️ Failed to estimate time saved with Gemini: {e}")
            return None
    
    def _write_time_saved_estimate(
        self,
        task_type: TaskType,
        time_saved_minutes: float,
        duration_minutes: float,
        baseline_minutes: float,
        agent_name: str,
        user_id: str,
        estimated_by_gemini: bool
    ):
        """
        Write time saved estimate to agent_time/time_saved document in Firestore.
        This document accumulates all time savings estimates.
        
        Args:
            task_type: Type of task performed
            time_saved_minutes: Estimated time saved
            duration_minutes: Actual duration
            baseline_minutes: Baseline manual time
            agent_name: Name of the agent
            user_id: User ID
            estimated_by_gemini: Whether estimate came from Gemini
        """
        if not self.db:
            return
        
        try:
            doc_ref = self.db.collection(self.estimates_collection).document(self.estimates_document)
            doc = doc_ref.get()
            
            estimate_entry = {
                "task_type": task_type.value,
                "time_saved_minutes": time_saved_minutes,
                "time_saved_hours": time_saved_minutes / 60.0,
                "duration_minutes": duration_minutes,
                "baseline_minutes": baseline_minutes,
                "agent_name": agent_name,
                "user_id": user_id,
                "estimated_by_gemini": estimated_by_gemini,
                "timestamp": SERVER_TIMESTAMP,
            }
            
            if doc.exists:
                # Update existing document - append to estimates array
                current_data = doc.to_dict()
                estimates = current_data.get("estimates", [])
                estimates.append(estimate_entry)
                
                # Update totals
                total_minutes = current_data.get("total_minutes_saved", 0.0) + time_saved_minutes
                total_hours = total_minutes / 60.0
                total_tasks = current_data.get("total_tasks", 0) + 1
                
                # Update breakdowns
                task_breakdown = current_data.get("task_breakdown", {})
                task_breakdown[task_type.value] = task_breakdown.get(task_type.value, 0) + 1
                
                agent_breakdown = current_data.get("agent_breakdown", {})
                agent_breakdown[agent_name] = agent_breakdown.get(agent_name, 0.0) + time_saved_minutes
                
                # Update document - ensure all fields exist
                update_data = {
                    "estimates": estimates,
                    "total_minutes_saved": total_minutes,
                    "total_hours_saved": total_hours,
                    "total_tasks": total_tasks,
                    "task_breakdown": task_breakdown,
                    "agent_breakdown": agent_breakdown,
                    "last_updated": SERVER_TIMESTAMP,
                }
                
                # Only update these if they don't exist (to preserve analytics data)
                if "fte_equivalent" not in current_data:
                    update_data["fte_equivalent"] = total_hours / (HOURS_PER_WEEK * 4.33)
                if "cost_savings" not in current_data:
                    update_data["cost_savings"] = total_hours * AVERAGE_HOURLY_RATE
                if "top_agent" not in current_data and agent_breakdown:
                    update_data["top_agent"] = max(agent_breakdown.items(), key=lambda x: x[1])[0]
                
                doc_ref.update(update_data)
            else:
                # Create new document with estimate entry
                doc_ref.set({
                    "estimates": [estimate_entry],
                    "total_minutes_saved": time_saved_minutes,
                    "total_hours_saved": time_saved_minutes / 60.0,
                    "total_tasks": 1,
                    "task_breakdown": {task_type.value: 1},
                    "agent_breakdown": {agent_name: time_saved_minutes},
                    "fte_equivalent": (time_saved_minutes / 60.0) / (HOURS_PER_WEEK * 4.33),
                    "cost_savings": (time_saved_minutes / 60.0) * AVERAGE_HOURLY_RATE,
                    "top_agent": agent_name,
                    "created_at": SERVER_TIMESTAMP,
                    "last_updated": SERVER_TIMESTAMP,
                })
            
            print(f"📝 Wrote time saved estimate to {self.estimates_collection}/{self.estimates_document}")
            
        except Exception as e:
            print(f"⚠️ Failed to write time saved estimate: {e}")
            import traceback
            traceback.print_exc()
    
    def _get_last_scheduled_run_time(self) -> Optional[datetime]:
        """
        Get the last scheduled run time from agent_time/time_saved document.
        
        Returns:
            datetime of last run (timezone-naive), or None if never run
        """
        if not self.db:
            return None
        
        try:
            doc_ref = self.db.collection(self.estimates_collection).document(self.estimates_document)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                last_run = data.get("last_scheduled_run")
                
                if last_run:
                    # Handle Firestore Timestamp
                    if hasattr(last_run, 'to_datetime'):
                        # Convert Firestore Timestamp to datetime
                        dt = last_run.to_datetime()
                        # Convert to UTC and make timezone-naive
                        if dt.tzinfo:
                            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                        return dt
                    elif isinstance(last_run, datetime):
                        # Already a datetime, make it timezone-naive
                        if last_run.tzinfo:
                            return last_run.astimezone(timezone.utc).replace(tzinfo=None)
                        return last_run
                    elif hasattr(last_run, 'seconds'):
                        # Firestore Timestamp-like object
                        from google.cloud.firestore_v1 import Timestamp
                        if isinstance(last_run, Timestamp):
                            dt = last_run.to_datetime()
                            if dt.tzinfo:
                                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                            return dt
                        else:
                            dt = datetime.fromtimestamp(last_run.seconds)
                            return dt.replace(tzinfo=None) if dt.tzinfo else dt
                
            return None
        except Exception as e:
            print(f"⚠️ Failed to get last scheduled run time: {e}")
            return None
    
    def _update_last_scheduled_run_time(self):
        """
        Update the last_scheduled_run timestamp in agent_time/time_saved document.
        """
        if not self.db:
            return
        
        try:
            doc_ref = self.db.collection(self.estimates_collection).document(self.estimates_document)
            doc = doc_ref.get()
            
            if doc.exists:
                doc_ref.update({
                    "last_scheduled_run": SERVER_TIMESTAMP,
                })
            else:
                # Create document with last_scheduled_run if it doesn't exist
                doc_ref.set({
                    "last_scheduled_run": SERVER_TIMESTAMP,
                    "created_at": SERVER_TIMESTAMP,
                })
            
            print(f"📝 Updated last_scheduled_run timestamp")
        except Exception as e:
            print(f"⚠️ Failed to update last scheduled run time: {e}")
    
    def _write_analytics_to_time_saved(
        self,
        all_time_savings: Dict[str, Any],
        daily_savings: Dict[str, Any],
        weekly_savings: Dict[str, Any],
        monthly_savings: Dict[str, Any],
        semester_savings: Dict[str, Any],
        insights: Optional[str] = None
    ):
        """
        Write all analytics data to the time_saved document in Firestore.
        This includes all timeframes and insights.
        
        Args:
            all_time_savings: Analytics for all time
            daily_savings: Analytics for daily timeframe
            weekly_savings: Analytics for weekly timeframe
            monthly_savings: Analytics for monthly timeframe
            semester_savings: Analytics for semester timeframe
            insights: Optional AI-generated insights
        """
        if not self.db:
            return
        
        try:
            doc_ref = self.db.collection(self.estimates_collection).document(self.estimates_document)
            doc = doc_ref.get()
            
            # Prepare complete analytics data
            analytics_data = {
                "all_time": all_time_savings,
                "daily": daily_savings,
                "weekly": weekly_savings,
                "monthly": monthly_savings,
                "semester": semester_savings,
                "insights": insights,
                "last_analytics_run": SERVER_TIMESTAMP,
                "last_analytics_run_iso": datetime.now().isoformat(),
            }
            
            if doc.exists:
                # Update existing document with analytics data
                # Use merge=False to ensure we overwrite and include all fields
                current_data = doc.to_dict()
                
                # Preserve estimates array if it exists
                estimates = current_data.get("estimates", [])
                
                # Update with all analytics data
                doc_ref.set({
                    "analytics": analytics_data,
                    "total_minutes_saved": all_time_savings.get('total_hours_saved', 0) * 60,
                    "total_hours_saved": all_time_savings.get('total_hours_saved', 0),
                    "fte_equivalent": all_time_savings.get('fte_equivalent', 0),
                    "cost_savings": all_time_savings.get('cost_savings', 0),
                    "total_tasks": all_time_savings.get('total_tasks', 0),
                    "task_breakdown": all_time_savings.get('task_breakdown', {}),
                    "agent_breakdown": all_time_savings.get('agent_breakdown', {}),
                    "top_agent": all_time_savings.get('top_agent'),
                    "estimates": estimates,  # Preserve existing estimates
                    "last_scheduled_run": current_data.get("last_scheduled_run"),  # Preserve if exists
                    "created_at": current_data.get("created_at", SERVER_TIMESTAMP),  # Preserve original creation time
                    "last_updated": SERVER_TIMESTAMP,
                })  # set() replaces entire document, ensuring all fields are written
            else:
                # Create new document with analytics data
                doc_ref.set({
                    "analytics": analytics_data,
                    "total_minutes_saved": all_time_savings.get('total_hours_saved', 0) * 60,
                    "total_hours_saved": all_time_savings.get('total_hours_saved', 0),
                    "fte_equivalent": all_time_savings.get('fte_equivalent', 0),
                    "cost_savings": all_time_savings.get('cost_savings', 0),
                    "total_tasks": all_time_savings.get('total_tasks', 0),
                    "task_breakdown": all_time_savings.get('task_breakdown', {}),
                    "agent_breakdown": all_time_savings.get('agent_breakdown', {}),
                    "top_agent": all_time_savings.get('top_agent'),
                    "estimates": [],  # Initialize empty estimates array
                    "created_at": SERVER_TIMESTAMP,
                    "last_updated": SERVER_TIMESTAMP,
                })
            
            print(f"📝 Wrote complete analytics data to {self.estimates_collection}/{self.estimates_document}")
            
        except Exception as e:
            print(f"⚠️ Failed to write analytics to time_saved: {e}")
            import traceback
            traceback.print_exc()
    
    def _should_run_scheduled_analytics(self) -> bool:
        """
        Check if scheduled analytics should run (if an hour has passed since last run).
        
        Returns:
            True if should run, False otherwise
        """
        if not self.db:
            return False
        
        last_run = self._get_last_scheduled_run_time()
        
        if last_run is None:
            # Never run before, run immediately
            print("🕐 Scheduled analytics: First run, executing now")
            return True
        
        # Calculate time since last run
        # Ensure both datetimes are timezone-naive for comparison
        now = datetime.now()
        
        # Convert last_run to timezone-naive if it has timezone info
        if last_run.tzinfo is not None:
            # Convert to UTC and remove timezone info
            if hasattr(last_run, 'astimezone'):
                last_run = last_run.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                # If it's a Firestore Timestamp that was converted, it might already be naive
                # Try to extract just the datetime part
                last_run = datetime(
                    last_run.year, last_run.month, last_run.day,
                    last_run.hour, last_run.minute, last_run.second,
                    last_run.microsecond
                )
        
        time_diff = (now - last_run).total_seconds()
        hours_since_last_run = time_diff / 3600.0
        
        if hours_since_last_run >= 1.0:
            print(f"🕐 Scheduled analytics: {hours_since_last_run:.2f} hours since last run, executing now")
            return True
        else:
            minutes_until_next = (1.0 - hours_since_last_run) * 60
            print(f"🕐 Scheduled analytics: {hours_since_last_run:.2f} hours since last run, next run in {minutes_until_next:.1f} minutes")
            return False
    
    def run_scheduled_analytics(self):
        """
        Run scheduled analytics calculation and update last run time.
        This calculates savings for the current hour and updates the time_saved document.
        Also updates state_agent and writes all analytics data to time_saved document.
        """
        if not self.db:
            print("⚠️ Cannot run scheduled analytics: Firestore not available")
            return
        
        # Update state to PROCESSING
        if self.state_agent:
            try:
                from agents.state_agent import StateAgent
                self.state_agent.set_agent_state("time_agent", StateAgent.STATE_ACTIVE)
            except Exception as e:
                print(f"⚠️ Failed to update state_agent: {e}")
        
        try:
            print("\n" + "="*60)
            print("🔄 Running Scheduled Time Savings Analytics")
            print("="*60)
            
            # Calculate savings for all timeframes
            all_time_savings = self.calculate_savings(Timeframe.ALL_TIME)
            daily_savings = self.calculate_savings(Timeframe.DAILY)
            weekly_savings = self.calculate_savings(Timeframe.WEEKLY)
            monthly_savings = self.calculate_savings(Timeframe.MONTHLY)
            semester_savings = self.calculate_savings(Timeframe.SEMESTER)
            
            print(f"📊 Analytics Results (All Time):")
            print(f"   - Total Hours Saved: {all_time_savings.get('total_hours_saved', 0):.2f}")
            print(f"   - FTE Equivalent: {all_time_savings.get('fte_equivalent', 0):.2f}")
            print(f"   - Cost Savings: ${all_time_savings.get('cost_savings', 0):,.2f}")
            print(f"   - Total Tasks: {all_time_savings.get('total_tasks', 0)}")
            
            # Generate insights for all-time data
            insights = None
            if self.gemini_agent:
                try:
                    insights = self.generate_insights(all_time_savings)
                except Exception as e:
                    print(f"⚠️ Failed to generate insights: {e}")
            
            # Write all analytics data to time_saved document
            self._write_analytics_to_time_saved(
                all_time_savings=all_time_savings,
                daily_savings=daily_savings,
                weekly_savings=weekly_savings,
                monthly_savings=monthly_savings,
                semester_savings=semester_savings,
                insights=insights
            )
            
            # Update last scheduled run time
            self._update_last_scheduled_run_time()
            
            # Update state_agent with result
            if self.state_agent:
                try:
                    from agents.state_agent import StateAgent
                    result_data = {
                        "total_hours_saved": all_time_savings.get('total_hours_saved', 0),
                        "fte_equivalent": all_time_savings.get('fte_equivalent', 0),
                        "cost_savings": all_time_savings.get('cost_savings', 0),
                        "total_tasks": all_time_savings.get('total_tasks', 0),
                        "last_run": datetime.now().isoformat()
                    }
                    self.state_agent.set_agent_result(
                        "time_agent",
                        result_data,
                        StateAgent.STATE_IDLE
                    )
                except Exception as e:
                    print(f"⚠️ Failed to update state_agent result: {e}")
            
            print("✅ Scheduled analytics completed")
            print("="*60 + "\n")
            
        except Exception as e:
            print(f"⚠️ Error running scheduled analytics: {e}")
            import traceback
            traceback.print_exc()
            
            # Update state to ERROR
            if self.state_agent:
                try:
                    from agents.state_agent import StateAgent
                    self.state_agent.set_agent_error("time_agent", str(e))
                except Exception:
                    pass
    
    def _scheduled_analytics_loop(self):
        """
        Background thread loop that runs analytics every hour.
        """
        print("🔄 Scheduled Time Savings Analytics started (running every hour)")
        
        # Check if we should run immediately on startup
        if self._should_run_scheduled_analytics():
            try:
                self.run_scheduled_analytics()
            except Exception as e:
                print(f"⚠️ Error in initial scheduled analytics run: {e}")
        
        while self.scheduled_analytics_running:
            try:
                # Sleep for a short interval and check if it's time to run
                # Check every 5 minutes to be responsive
                check_interval = 5 * 60  # 5 minutes
                
                for _ in range(12):  # 12 * 5 minutes = 60 minutes
                    if not self.scheduled_analytics_running:
                        break
                    time.sleep(check_interval)
                    
                    # Check if an hour has passed since last run
                    if self._should_run_scheduled_analytics():
                        self.run_scheduled_analytics()
                        break  # Reset the loop after running
                
            except Exception as e:
                print(f"⚠️ Error in scheduled analytics loop: {e}")
                import traceback
                traceback.print_exc()
                # Continue loop despite errors
                time.sleep(60)  # Wait a minute before retrying
        
        print("🛑 Scheduled Time Savings Analytics stopped")
    
    def start_scheduled_analytics(self):
        """
        Start the scheduled analytics background thread.
        Analytics will run once per hour from server start.
        """
        if self.scheduled_analytics_running:
            print("⚠️ Scheduled analytics is already running")
            return
        
        if not self.db:
            print("⚠️ Cannot start scheduled analytics: Firestore not available")
            return
        
        self.scheduled_analytics_running = True
        self.scheduled_analytics_thread = threading.Thread(
            target=self._scheduled_analytics_loop,
            daemon=True
        )
        self.scheduled_analytics_thread.start()
        print(f"✅ Scheduled Time Savings Analytics started (will run every hour)")
    
    def stop_scheduled_analytics(self):
        """
        Stop the scheduled analytics background thread.
        """
        if not self.scheduled_analytics_running:
            return
        
        self.scheduled_analytics_running = False
        if self.scheduled_analytics_thread:
            self.scheduled_analytics_thread.join(timeout=10)
        print("🛑 Scheduled Time Savings Analytics stopped")
    
    def _update_summaries_async(self, task_data: Dict[str, Any], time_saved_minutes: float):
        """Update summary documents asynchronously (called after task completion)"""
        if not self.db or time_saved_minutes <= 0:
            return
        
        try:
            now = datetime.now()
            task_type = task_data.get("task_type")
            user_id = task_data.get("user_id")
            agent_name = task_data.get("agent_name", "unknown")
            
            # Update daily summary
            daily_key = f"{now.year}-{now.month:02d}-{now.day:02d}"
            daily_ref = self.db.collection(self.summaries_collection).document(f"daily_{daily_key}")
            daily_doc = daily_ref.get()
            
            if daily_doc.exists:
                daily_data = daily_doc.to_dict()
                daily_ref.update({
                    "total_tasks": firestore.Increment(1),
                    "total_hours_saved": firestore.Increment(time_saved_minutes / 60.0),
                    "tasks_by_type." + task_type: firestore.Increment(1),
                    "tasks_by_agent." + agent_name: firestore.Increment(1),
                    "updated_at": SERVER_TIMESTAMP
                })
            else:
                daily_ref.set({
                    "date": daily_key,
                    "timeframe": Timeframe.DAILY.value,
                    "total_tasks": 1,
                    "total_hours_saved": time_saved_minutes / 60.0,
                    "tasks_by_type": {task_type: 1},
                    "tasks_by_agent": {agent_name: 1},
                    "created_at": SERVER_TIMESTAMP,
                    "updated_at": SERVER_TIMESTAMP
                })
            
            # Update weekly summary
            week_start = now - timedelta(days=now.weekday())
            weekly_key = f"{week_start.year}-W{week_start.isocalendar()[1]}"
            weekly_ref = self.db.collection(self.summaries_collection).document(f"weekly_{weekly_key}")
            weekly_doc = weekly_ref.get()
            
            if weekly_doc.exists:
                weekly_ref.update({
                    "total_tasks": firestore.Increment(1),
                    "total_hours_saved": firestore.Increment(time_saved_minutes / 60.0),
                    "tasks_by_type." + task_type: firestore.Increment(1),
                    "tasks_by_agent." + agent_name: firestore.Increment(1),
                    "updated_at": SERVER_TIMESTAMP
                })
            else:
                weekly_ref.set({
                    "period": weekly_key,
                    "timeframe": Timeframe.WEEKLY.value,
                    "total_tasks": 1,
                    "total_hours_saved": time_saved_minutes / 60.0,
                    "tasks_by_type": {task_type: 1},
                    "tasks_by_agent": {agent_name: 1},
                    "created_at": SERVER_TIMESTAMP,
                    "updated_at": SERVER_TIMESTAMP
                })
            
        except Exception as e:
            print(f"⚠️ Failed to update summaries: {e}")
    
    def calculate_savings(self, timeframe: Timeframe, user_id: Optional[str] = None, update_time_saved: bool = False) -> Dict[str, Any]:
        """
        Calculate time savings by analyzing documents created by agents in the given timeframe.
        Counts documents from each agent collection and multiplies by expected time savings.
        
        Args:
            timeframe: Time period to analyze
            user_id: Optional user ID to filter by (not currently used for document counting)
            update_time_saved: If True, also update the time_saved document with this calculation
        
        Returns:
            Dictionary with savings report
        """
        if not self.db:
            return {
                "total_hours_saved": 0.0,
                "fte_equivalent": 0.0,
                "cost_savings": 0.0,
                "task_breakdown": {},
                "top_agent": None,
                "insights": "Firestore not available"
            }
        
        try:
            # Calculate timeframe filter
            now = datetime.now()
            if timeframe == Timeframe.DAILY:
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif timeframe == Timeframe.WEEKLY:
                start_time = now - timedelta(days=7)
            elif timeframe == Timeframe.MONTHLY:
                start_time = now - timedelta(days=30)
            elif timeframe == Timeframe.SEMESTER:
                start_time = now - timedelta(days=120)  # ~4 months
            else:  # ALL_TIME
                start_time = None
            
            # Count documents created by each agent
            task_counts = {}
            agent_counts = {}
            
            # Map collections to task types and agent names
            collection_mappings = [
                {
                    'collection': 'agent_evaluations',
                    'task_type': TaskType.EVALUATION_COMPLETION,
                    'agent_name': 'evaluations_agent',
                    'description': 'evaluations'
                },
                {
                    'collection': 'agent_scenarios',
                    'task_type': TaskType.SCENARIO_GENERATION,
                    'agent_name': 'scenario_agent',
                    'description': 'scenarios'
                },
                {
                    'collection': 'agent_coa_reports',
                    'task_type': TaskType.COA_COMPLIANCE_CHECK,
                    'agent_name': 'coa_agent',
                    'description': 'COA reports'
                },
                {
                    'collection': 'agent_notifications',
                    'task_type': TaskType.NOTIFICATION_CHECK,
                    'agent_name': 'notification_agent',
                    'description': 'notifications'
                },
            ]
            
            # Count documents in each collection
            for mapping in collection_mappings:
                count = self._count_documents_in_timeframe(mapping['collection'], start_time)
                if count > 0:
                    task_counts[mapping['task_type'].value] = count
                    agent_counts[mapping['agent_name']] = count
                    print(f"📊 Found {count} {mapping['description']} in {mapping['collection']}")
            
            # Also check if evaluations represent additional admin review tasks
            # Each evaluation might also represent an admin review and filing task
            eval_count = task_counts.get(TaskType.EVALUATION_COMPLETION.value, 0)
            if eval_count > 0:
                # Add admin review as a separate task (each evaluation gets reviewed)
                admin_review_count = eval_count
                task_counts[TaskType.ADMIN_REVIEW.value] = admin_review_count
                if 'evaluations_agent' not in agent_counts:
                    agent_counts['evaluations_agent'] = 0
                # Admin review is typically done by admin staff, but we'll attribute it to the system
                print(f"📊 Counting {admin_review_count} admin reviews (one per evaluation)")
            
            # Problem identification might be represented by notifications
            # Each notification represents identifying a problem
            notification_count = task_counts.get(TaskType.NOTIFICATION_CHECK.value, 0)
            if notification_count > 0:
                # Notifications already represent problem identification
                # But we could also count it separately if needed
                problem_id_count = notification_count
                task_counts[TaskType.PROBLEM_IDENTIFICATION.value] = problem_id_count
                print(f"📊 Counting {problem_id_count} problem identifications (from notifications)")
            
            # Calculate time savings from counts
            total_hours_saved = 0.0
            total_tasks = 0
            task_breakdown = {}
            agent_breakdown = {}
            
            for task_type_str, count in task_counts.items():
                task_type = TaskType(task_type_str)
                expected_savings_minutes = _get_expected_time_savings(task_type)
                hours_saved = (expected_savings_minutes * count) / 60.0
                
                total_hours_saved += hours_saved
                total_tasks += count
                task_breakdown[task_type_str] = count
                
                # Map agent name from task type
                agent_name = None
                if task_type == TaskType.EVALUATION_COMPLETION:
                    agent_name = 'evaluations_agent'
                elif task_type == TaskType.ADMIN_REVIEW:
                    agent_name = 'evaluations_agent'  # Admin review happens with evaluations
                elif task_type == TaskType.PROBLEM_IDENTIFICATION:
                    agent_name = 'notification_agent'  # Problem identification via notifications
                elif task_type == TaskType.SCENARIO_GENERATION:
                    agent_name = 'scenario_agent'
                elif task_type == TaskType.COA_COMPLIANCE_CHECK:
                    agent_name = 'coa_agent'
                elif task_type == TaskType.NOTIFICATION_CHECK:
                    agent_name = 'notification_agent'
                elif task_type == TaskType.TEST_GENERATION:
                    agent_name = 'evaluations_agent'  # Could be generated from evaluations
                
                if agent_name:
                    if agent_name not in agent_breakdown:
                        agent_breakdown[agent_name] = 0.0
                    agent_breakdown[agent_name] += hours_saved
            
            # Calculate metrics
            fte_equivalent = total_hours_saved / (HOURS_PER_WEEK * 4.33)  # Average weeks per month
            cost_savings = total_hours_saved * AVERAGE_HOURLY_RATE
            
            # Find top agent
            top_agent = None
            if agent_breakdown:
                top_agent = max(agent_breakdown.items(), key=lambda x: x[1])[0]
            
            print(f"💰 Calculated savings: {total_hours_saved:.2f} hours, {total_tasks} tasks")
            
            result = {
                "timeframe": timeframe.value,
                "total_hours_saved": round(total_hours_saved, 2),
                "fte_equivalent": round(fte_equivalent, 2),
                "cost_savings": round(cost_savings, 2),
                "total_tasks": total_tasks,
                "task_breakdown": task_breakdown,
                "agent_breakdown": {k: round(v, 2) for k, v in agent_breakdown.items()},
                "top_agent": top_agent,
                "average_hourly_rate": AVERAGE_HOURLY_RATE,
            }
            
            # If update_time_saved flag is set, write to time_saved document
            if update_time_saved:
                # Get all timeframes for complete analytics
                all_time_savings = self.calculate_savings(Timeframe.ALL_TIME, update_time_saved=False)
                daily_savings = self.calculate_savings(Timeframe.DAILY, update_time_saved=False)
                weekly_savings = self.calculate_savings(Timeframe.WEEKLY, update_time_saved=False)
                monthly_savings = self.calculate_savings(Timeframe.MONTHLY, update_time_saved=False)
                semester_savings = self.calculate_savings(Timeframe.SEMESTER, update_time_saved=False)
                
                # Generate insights
                insights = None
                if self.gemini_agent:
                    try:
                        insights = self.generate_insights(all_time_savings)
                    except Exception as e:
                        print(f"⚠️ Failed to generate insights: {e}")
                
                # Write all analytics data
                self._write_analytics_to_time_saved(
                    all_time_savings=all_time_savings,
                    daily_savings=daily_savings,
                    weekly_savings=weekly_savings,
                    monthly_savings=monthly_savings,
                    semester_savings=semester_savings,
                    insights=insights
                )
            
            return result
            
        except Exception as e:
            print(f"⚠️ Failed to calculate savings: {e}")
            import traceback
            traceback.print_exc()
            return {
                "error": str(e),
                "total_hours_saved": 0.0,
                "fte_equivalent": 0.0,
                "cost_savings": 0.0,
            }
    
    def _count_documents_in_timeframe(self, collection_name: str, start_time: Optional[datetime]) -> int:
        """
        Count documents in a collection created after start_time.
        
        Args:
            collection_name: Name of the Firestore collection
            start_time: Optional datetime to filter documents created after this time
        
        Returns:
            Count of documents
        """
        try:
            query = self.db.collection(collection_name)
            
            if start_time:
                # Try multiple timestamp field names
                # Some collections use created_at, others might use timestamp
                try:
                    query = query.where("created_at", ">=", start_time)
                    docs = list(query.stream())
                    if docs:
                        return len(docs)
                except Exception:
                    pass
                
                # Try timestamp field
                try:
                    query = query.where("timestamp", ">=", start_time)
                    docs = list(query.stream())
                    if docs:
                        return len(docs)
                except Exception:
                    pass
                
                # If time filtering fails, get all and filter client-side
                # (not ideal but works as fallback)
                all_docs = list(self.db.collection(collection_name).stream())
                count = 0
                for doc in all_docs:
                    doc_data = doc.to_dict()
                    doc_time = None
                    # Try different timestamp fields
                    for field in ['created_at', 'timestamp', 'createdAt', 'date']:
                        if field in doc_data:
                            doc_time = doc_data[field]
                            break
                    
                    if doc_time:
                        if isinstance(doc_time, datetime):
                            if doc_time >= start_time:
                                count += 1
                        elif hasattr(doc_time, 'seconds'):  # Firestore Timestamp
                            from google.cloud.firestore_v1 import Timestamp
                            if isinstance(doc_time, Timestamp):
                                doc_datetime = doc_time.to_datetime()
                            else:
                                doc_datetime = datetime.fromtimestamp(doc_time.seconds)
                            if doc_datetime >= start_time:
                                count += 1
                        else:
                            # If no timestamp, include it (better to overcount than undercount)
                            count += 1
                
                return count
            else:
                # No time filter - count all documents
                docs = list(query.stream())
                return len(docs)
            
        except Exception as e:
            print(f"⚠️ Failed to count documents in {collection_name}: {e}")
            import traceback
            traceback.print_exc()
            return 0
    
    def generate_insights(self, data: Dict[str, Any]) -> str:
        """
        Generate AI-powered insights using Gemini.
        
        Args:
            data: Savings data dictionary
        
        Returns:
            Natural language insights string
        """
        if not self.gemini_agent:
            return "AI insights not available. Gemini agent not initialized."
        
        try:
            prompt = f"""Analyze this time savings data for a nursing education program:

Time Period: {data.get('timeframe', 'unknown')}
Total Hours Saved: {data.get('total_hours_saved', 0):.1f} hours
FTE Equivalent: {data.get('fte_equivalent', 0):.2f}
Cost Savings: ${data.get('cost_savings', 0):,.0f}
Total Tasks Automated: {data.get('total_tasks', 0)}

Task Breakdown:
{json.dumps(data.get('task_breakdown', {}), indent=2)}

Agent Breakdown (hours saved):
{json.dumps(data.get('agent_breakdown', {}), indent=2)}

Top Agent: {data.get('top_agent', 'N/A')}

Provide 3-4 actionable insights about:
1. Efficiency gains and trends
2. Which agents provide the most value
3. Optimization opportunities
4. Impact on the program

Format as bullet points, professional but accessible language. Keep each insight to 1-2 sentences."""

            response = self.gemini_agent.model.generate_content(prompt)
            
            if response and response.text:
                return response.text.strip()
            else:
                return "Failed to generate insights."
                
        except Exception as e:
            print(f"⚠️ Failed to generate insights: {e}")
            return f"Error generating insights: {str(e)}"
    
    def generate_report(
        self,
        format_type: str = "summary",
        timeframe: Timeframe = Timeframe.MONTHLY,
        user_id: Optional[str] = None,
        include_insights: bool = True
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive savings report.
        
        Args:
            format_type: "summary" or "detailed"
            timeframe: Time period to analyze
            user_id: Optional user ID to filter by
            include_insights: Whether to include AI-generated insights
        
        Returns:
            Report dictionary
        """
        savings_data = self.calculate_savings(timeframe, user_id)
        
        report = {
            "format": format_type,
            "timeframe": timeframe.value,
            "generated_at": datetime.now().isoformat(),
            "metrics": {
                "total_hours_saved": savings_data.get("total_hours_saved", 0),
                "fte_equivalent": savings_data.get("fte_equivalent", 0),
                "cost_savings": savings_data.get("cost_savings", 0),
                "total_tasks": savings_data.get("total_tasks", 0),
            },
            "breakdown": {
                "by_task_type": savings_data.get("task_breakdown", {}),
                "by_agent": savings_data.get("agent_breakdown", {}),
            },
            "top_agent": savings_data.get("top_agent"),
        }
        
        if format_type == "detailed":
            # Add more detailed breakdowns
            report["detailed_metrics"] = savings_data
        
        if include_insights and self.gemini_agent:
            # Generate insights asynchronously (in real implementation, might want to cache)
            try:
                insights = self.generate_insights(savings_data)
                report["insights"] = insights
            except Exception as e:
                report["insights"] = f"Failed to generate insights: {str(e)}"
        
        return report


# Convenience function for easy importing
def create_time_savings_agent(firestore_db=None, state_agent=None) -> TimeSavingsAgent:
    """
    Create and return a TimeSavingsAgent instance.
    
    Args:
        firestore_db: Optional Firestore database client
        state_agent: Optional StateAgent instance for tracking agent state
    
    Returns:
        TimeSavingsAgent instance
    """
    return TimeSavingsAgent(firestore_db=firestore_db, state_agent=state_agent)


def test_realistic_benchmarks():
    """
    Test that realistic benchmarks are loaded correctly.
    This verifies the new benchmarks are being used instead of fallback values.
    """
    print("\n" + "="*60)
    print("🧪 Testing Realistic Benchmarks")
    print("="*60)
    
    # Test evaluation completion - should save 42 minutes (not 12)
    eval_savings = _get_expected_time_savings(TaskType.EVALUATION_COMPLETION)
    eval_baseline = _get_baseline_time(TaskType.EVALUATION_COMPLETION)
    eval_ai = _get_ai_assisted_time(TaskType.EVALUATION_COMPLETION)
    print(f"\n✅ Evaluation Completion:")
    print(f"   Baseline: {eval_baseline:.1f} min manual")
    print(f"   AI-assisted: {eval_ai:.1f} min")
    print(f"   Time saved: {eval_savings:.1f} min ({eval_savings/60:.2f} hours)")
    assert eval_savings == 42, f"Expected 42 minutes saved, got {eval_savings}"
    
    # Test problem identification - should save 83 minutes (not 7)
    problem_savings = _get_expected_time_savings(TaskType.PROBLEM_IDENTIFICATION)
    problem_baseline = _get_baseline_time(TaskType.PROBLEM_IDENTIFICATION)
    problem_ai = _get_ai_assisted_time(TaskType.PROBLEM_IDENTIFICATION)
    print(f"\n✅ Problem Identification:")
    print(f"   Baseline: {problem_baseline:.1f} min manual")
    print(f"   AI-assisted: {problem_ai:.1f} min")
    print(f"   Time saved: {problem_savings:.1f} min ({problem_savings/60:.2f} hours)")
    assert problem_savings == 83, f"Expected 83 minutes saved, got {problem_savings}"
    
    # Test scenario generation - should save 128 minutes (not 27)
    scenario_savings = _get_expected_time_savings(TaskType.SCENARIO_GENERATION)
    scenario_baseline = _get_baseline_time(TaskType.SCENARIO_GENERATION)
    scenario_ai = _get_ai_assisted_time(TaskType.SCENARIO_GENERATION)
    print(f"\n✅ Scenario Generation:")
    print(f"   Baseline: {scenario_baseline:.1f} min manual")
    print(f"   AI-assisted: {scenario_ai:.1f} min")
    print(f"   Time saved: {scenario_savings:.1f} min ({scenario_savings/60:.2f} hours)")
    assert scenario_savings == 128, f"Expected 128 minutes saved, got {scenario_savings}"
    
    # Test admin review - should save 23 minutes
    admin_savings = _get_expected_time_savings(TaskType.ADMIN_REVIEW)
    admin_baseline = _get_baseline_time(TaskType.ADMIN_REVIEW)
    admin_ai = _get_ai_assisted_time(TaskType.ADMIN_REVIEW)
    print(f"\n✅ Admin Review:")
    print(f"   Baseline: {admin_baseline:.1f} min manual")
    print(f"   AI-assisted: {admin_ai:.1f} min")
    print(f"   Time saved: {admin_savings:.1f} min ({admin_savings/60:.2f} hours)")
    
    # Test COA compliance - should save 62 minutes
    coa_savings = _get_expected_time_savings(TaskType.COA_COMPLIANCE_CHECK)
    coa_baseline = _get_baseline_time(TaskType.COA_COMPLIANCE_CHECK)
    coa_ai = _get_ai_assisted_time(TaskType.COA_COMPLIANCE_CHECK)
    print(f"\n✅ COA Compliance Check:")
    print(f"   Baseline: {coa_baseline:.1f} min manual")
    print(f"   AI-assisted: {coa_ai:.1f} min")
    print(f"   Time saved: {coa_savings:.1f} min ({coa_savings/60:.2f} hours)")
    
    # Test notification check - should save 44 minutes
    notification_savings = _get_expected_time_savings(TaskType.NOTIFICATION_CHECK)
    notification_baseline = _get_baseline_time(TaskType.NOTIFICATION_CHECK)
    notification_ai = _get_ai_assisted_time(TaskType.NOTIFICATION_CHECK)
    print(f"\n✅ Notification Check:")
    print(f"   Baseline: {notification_baseline:.1f} min manual")
    print(f"   AI-assisted: {notification_ai:.1f} min")
    print(f"   Time saved: {notification_savings:.1f} min ({notification_savings/60:.2f} hours)")
    
    print("\n" + "="*60)
    print("✅ All realistic benchmarks loaded correctly!")
    print(f"   - Evaluation completion: {eval_savings} min saved ({eval_savings/60:.2f} hours)")
    print(f"   - Problem identification: {problem_savings} min saved ({problem_savings/60:.2f} hours)")
    print(f"   - Scenario generation: {scenario_savings} min saved ({scenario_savings/60:.2f} hours)")
    print(f"   - Admin review: {admin_savings} min saved ({admin_savings/60:.2f} hours)")
    print(f"   - COA compliance: {coa_savings} min saved ({coa_savings/60:.2f} hours)")
    print(f"   - Notification check: {notification_savings} min saved ({notification_savings/60:.2f} hours)")
    print("="*60 + "\n")
    
    return True


if __name__ == "__main__":
    # Run test if script is executed directly
    test_realistic_benchmarks()

