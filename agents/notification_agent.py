"""
Notification Agent
Monitors agent_evaluations collection for negative evaluations (-1 ratings)
and saves notification records to Firestore.
Runs every 15 minutes.
"""

import os
import threading
import time
import html
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Import dependencies
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    print("⚠️ Firestore not available for Notification Agent")

try:
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP
except ImportError:
    SERVER_TIMESTAMP = None

try:
    from agents.state_agent import StateAgent
    STATE_AGENT_AVAILABLE = True
except ImportError:
    STATE_AGENT_AVAILABLE = False
    print("⚠️ State Agent not available")


class NotificationAgent:
    """
    Agent for monitoring evaluations and saving notification records.
    Checks for dangerous ratings (-1) and saves notification records to Firestore.
    """
    
    def __init__(
        self,
        check_interval_minutes: int = 15,
        firestore_db=None
    ):
        """
        Initialize the Notification Agent.
        
        Args:
            check_interval_minutes: How often to check for new evaluations (default: 15)
            firestore_db: Optional Firestore database client
        """
        self.check_interval = check_interval_minutes * 60  # Convert to seconds
        
        # Initialize Firestore
        if firestore_db:
            self.db = firestore_db
        elif FIRESTORE_AVAILABLE:
            try:
                project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
                if project_id:
                    self.db = firestore.Client(project=project_id)
                else:
                    self.db = firestore.Client()
            except Exception as e:
                print(f"⚠️ Firestore initialization failed: {e}")
                self.db = None
        else:
            self.db = None
        
        # Initialize State Agent
        self.state_agent = None
        if STATE_AGENT_AVAILABLE and self.db:
            try:
                self.state_agent = StateAgent(firestore_db=self.db)
            except Exception as e:
                print(f"⚠️ State Agent initialization failed: {e}")
        
        # Background thread control
        self.running = False
        self.thread = None
        
        print(f"✅ Notification Agent initialized")
        print(f"   - Check interval: {check_interval_minutes} minutes")
        print(f"   - Firestore: {'Available' if self.db else 'Not available'}")
        print(f"   - Notification tracking: agent_notifications collection")
    
    def _has_notification_been_sent(self, evaluation_doc_id: str) -> bool:
        """
        Check if a notification has already been sent for this evaluation.
        
        Args:
            evaluation_doc_id: Document ID of the evaluation
        
        Returns:
            True if notification already sent, False otherwise
        """
        if not self.db:
            return False
        
        try:
            notifications_ref = self.db.collection('agent_notifications')
            # Query for notifications with this evaluation_doc_id
            query = notifications_ref.where('evaluation_doc_id', '==', evaluation_doc_id).limit(1)
            results = list(query.stream())
            return len(results) > 0
        except Exception as e:
            print(f"⚠️ Error checking notification history: {e}")
            return False
    
    def _generate_email_html(self, evaluation_data: Dict[str, Any], evaluation_doc_id: str, negative_fields: List[str]) -> str:
        """
        Generate HTML email content for a single negative evaluation.
        
        Args:
            evaluation_data: Evaluation data dictionary
            evaluation_doc_id: Document ID of the evaluation
            negative_fields: List of PC metric fields that were negative
        
        Returns:
            HTML string containing the email content
        """
        # Escape HTML to prevent XSS attacks
        preceptee_name = html.escape(str(evaluation_data.get("preceptee_user_name", "Unknown")))
        preceptor_name = html.escape(str(evaluation_data.get("preceptor_name", "Unknown")))
        case_type = html.escape(str(evaluation_data.get("case_type", "Unknown")))
        request_id = html.escape(str(evaluation_data.get("request_id", "N/A")))
        comments = html.escape(str(evaluation_data.get("comments", "")))
        
        # Metric names mapping
        metric_names = {
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
            "pc_10": "Follows Universal Precautions"
        }
        
        # Build HTML email content
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 0; }}
                .header {{ background-color: #dc3545; color: white; padding: 20px; }}
                .content {{ padding: 20px; }}
                .explanation {{ background-color: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #ffc107; margin-bottom: 20px; }}
                .evaluation-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .info-row {{ margin: 8px 0; }}
                .info-label {{ font-weight: bold; color: #495057; }}
                .negative-metrics {{ background-color: #f8d7da; padding: 15px; border-radius: 5px; border-left: 4px solid #dc3545; margin-bottom: 20px; }}
                .negative-field {{ color: #dc3545; font-weight: bold; }}
                .metric-item {{ margin: 8px 0; padding: 8px; background-color: white; border-radius: 3px; }}
                .preceptor-comment {{ background-color: #e7f3ff; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; margin-top: 20px; }}
                .comment-text {{ margin-top: 10px; font-style: italic; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 2px solid #dee2e6; color: #6c757d; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>⚠️ Negative Evaluation Alert</h2>
            </div>
            <div class="content">
                <div class="explanation">
                    <h3>🚨 Important Notification</h3>
                    <p>This is an automated notification from the PrecepGo evaluation system.</p>
                    <p><strong>A student has received a negative evaluation rating (Dangerous/Safety Concern) from their preceptor.</strong></p>
                    <p>This requires immediate attention from the program administrator. Please review the details below and take appropriate action.</p>
                </div>
                
                <div class="evaluation-info">
                    <h3>📋 Evaluation Information</h3>
                    <div class="info-row">
                        <span class="info-label">Student Name:</span> {preceptee_name}
                    </div>
                    <div class="info-row">
                        <span class="info-label">Preceptor Name:</span> {preceptor_name}
                    </div>
                    <div class="info-row">
                        <span class="info-label">Case Type:</span> {case_type}
                    </div>
                    <div class="info-row">
                        <span class="info-label">Document ID:</span> {evaluation_doc_id}
                    </div>
                    <div class="info-row">
                        <span class="info-label">Request ID:</span> {request_id}
                    </div>
                    <div class="info-row">
                        <span class="info-label">Notification Generated:</span> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    </div>
                </div>
                
                <div class="negative-metrics">
                    <h3>⚠️ Negative Ratings Received</h3>
                    <p>The following performance metrics received a rating of <strong class="negative-field">-1 (DANGEROUS)</strong>:</p>
        """
        
        # Add each negative metric
        for field in negative_fields:
            metric_name = metric_names.get(field, field)
            html_content += f"""
                    <div class="metric-item">
                        <strong>{metric_name}</strong> <span class="negative-field">({field}) - DANGEROUS</span>
                    </div>
            """
        
        html_content += """
                </div>
        """
        
        # Add preceptor comments if available
        if comments:
            # Convert newlines to <br> tags for HTML display
            comments_html = comments.replace('\n', '<br>')
            html_content += f"""
                <div class="preceptor-comment">
                    <h3>💬 Preceptor's Comments</h3>
                    <div class="comment-text">
                        {comments_html}
                    </div>
                </div>
            """
        else:
            html_content += """
                <div class="preceptor-comment">
                    <h3>💬 Preceptor's Comments</h3>
                    <div class="comment-text">
                        <em>No additional comments provided by the preceptor.</em>
                    </div>
                </div>
            """
        
        html_content += f"""
                <div class="footer">
                    <p><strong>Action Required:</strong> Please review this evaluation immediately and contact the preceptor and student as appropriate.</p>
                    <p>This is an automated notification. For questions or concerns, please contact the PrecepGo system administrator.</p>
                    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_content.strip()
    
    def _save_notification_record(self, evaluation_doc_id: str, evaluation_data: Dict[str, Any], negative_fields: List[str]) -> bool:
        """
        Save a record of the notification sent to Firestore.
        
        Args:
            evaluation_doc_id: Document ID of the evaluation
            evaluation_data: Evaluation data dictionary
            negative_fields: List of PC metric fields that were negative
        
        Returns:
            True if saved successfully, False otherwise
        """
        if not self.db:
            return False
        
        try:
            # Generate HTML email content
            email_html = self._generate_email_html(evaluation_data, evaluation_doc_id, negative_fields)
            
            notifications_ref = self.db.collection('agent_notifications')
            
            notification_record = {
                'evaluation_doc_id': evaluation_doc_id,
                'preceptee_name': evaluation_data.get('preceptee_user_name', 'Unknown'),
                'preceptor_name': evaluation_data.get('preceptor_name', 'Unknown'),
                'case_type': evaluation_data.get('case_type', 'Unknown'),
                'request_id': evaluation_data.get('request_id', 'N/A'),
                'negative_fields': negative_fields,
                'email': email_html,  # HTML email content
                'notification_sent_at': SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now(),
                'evaluation_timestamp': evaluation_data.get('timestamp'),
                'created_at': SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
            }
            
            # Add notification document
            notifications_ref.add(notification_record)
            print(f"✅ Saved notification record for evaluation {evaluation_doc_id}")
            return True
        except Exception as e:
            print(f"⚠️ Failed to save notification record: {e}")
            return False
    
    def check_for_negative_evaluations(self) -> List[Dict[str, Any]]:
        """
        Check Firestore for evaluations with -1 ratings (dangerous).
        
        Returns:
            List of evaluation documents with negative ratings
        """
        if not self.db:
            print("⚠️ Cannot check evaluations: Firestore not available")
            return []
        
        negative_evaluations = []
        
        try:
            # Query all evaluations in agent_evaluations collection
            evaluations_ref = self.db.collection('agent_evaluations')
            evaluations = evaluations_ref.stream()
            
            for eval_doc in evaluations:
                eval_data = eval_doc.to_dict()
                eval_id = eval_doc.id
                
                # Check if we've already sent a notification for this evaluation
                if self._has_notification_been_sent(eval_id):
                    continue
                
                # Check all PC metrics for -1 (dangerous rating)
                has_negative_rating = False
                negative_fields = []
                
                for i in range(11):  # pc_0 through pc_10
                    pc_key = f"pc_{i}"
                    if eval_data.get(pc_key) == -1:
                        has_negative_rating = True
                        # Get the metric name
                        metric_name = f"pc_{i}"
                        negative_fields.append(metric_name)
                
                if has_negative_rating:
                    negative_evaluations.append({
                        "doc_id": eval_id,
                        "evaluation": eval_data,
                        "negative_fields": negative_fields
                    })
        
        except Exception as e:
            print(f"⚠️ Error checking evaluations: {e}")
        
        return negative_evaluations
    
    def send_notification_email(self, evaluations: List[Dict[str, Any]]) -> bool:
        """
        Placeholder for email notification (disabled - will use different email service).
        
        Args:
            evaluations: List of evaluation dictionaries with negative ratings
        
        Returns:
            True (email sending disabled)
        """
        # Email sending disabled - will use different email service
        # Notifications are still saved to Firestore
        return True
    
    def process_notifications(self):
        """Check for negative evaluations and send notifications."""
        # Update state to PROCESSING
        if self.state_agent:
            self.state_agent.set_agent_state("notification_agent", StateAgent.STATE_ACTIVE)
        
        try:
            # Check for negative evaluations
            negative_evaluations = self.check_for_negative_evaluations()
            
            if negative_evaluations:
                print(f"🔔 Found {len(negative_evaluations)} negative evaluation(s)")
                
                # Save notification records to Firestore
                for eval_info in negative_evaluations:
                    eval_id = eval_info["doc_id"]
                    eval_data = eval_info["evaluation"]
                    negative_fields = eval_info["negative_fields"]
                    self._save_notification_record(eval_id, eval_data, negative_fields)
                
                # Update state with result
                if self.state_agent:
                    self.state_agent.set_agent_result(
                        "notification_agent",
                        {
                            "notifications_sent": len(negative_evaluations),
                            "timestamp": datetime.now().isoformat()
                        },
                        StateAgent.STATE_IDLE
                    )
            else:
                # No negative evaluations found
                if self.state_agent:
                    self.state_agent.set_agent_state("notification_agent", StateAgent.STATE_IDLE)
        
        except Exception as e:
            print(f"⚠️ Error processing notifications: {e}")
            if self.state_agent:
                self.state_agent.set_agent_error("notification_agent", str(e))
    
    def _should_check_immediately(self) -> bool:
        """
        Check if we should run an immediate check based on last activity timestamp.
        Returns True if it's been more than 5 minutes since last check.
        
        Returns:
            True if should check immediately, False otherwise
        """
        if not self.state_agent:
            return False
        
        try:
            all_states = self.state_agent.get_all_states()
            last_activity = all_states.get('notification_agent_last_activity')
            
            if not last_activity:
                # No previous activity, check immediately
                print("⏰ No previous check found, running immediate check")
                return True
            
            # Convert Firestore timestamp to datetime
            last_check_time = None
            
            # Handle Firestore Timestamp object
            if hasattr(last_activity, 'seconds'):
                last_check_time = datetime.fromtimestamp(last_activity.seconds, tz=timezone.utc)
            # Handle dictionary with seconds key (from cleaned JSON)
            elif isinstance(last_activity, dict) and 'seconds' in last_activity:
                last_check_time = datetime.fromtimestamp(last_activity['seconds'], tz=timezone.utc)
            # Handle datetime object
            elif isinstance(last_activity, datetime):
                last_check_time = last_activity
                # Ensure timezone-aware
                if last_check_time.tzinfo is None:
                    last_check_time = last_check_time.replace(tzinfo=timezone.utc)
            else:
                # Unknown format, check immediately to be safe
                print(f"⚠️ Unknown timestamp format: {type(last_activity)}, running immediate check")
                return True
            
            # Calculate time difference
            now = datetime.now(timezone.utc)
            if last_check_time.tzinfo is None:
                last_check_time = last_check_time.replace(tzinfo=timezone.utc)
            
            time_diff = (now - last_check_time).total_seconds()
            minutes_since_last_check = time_diff / 60
            
            # Check if more than 5 minutes (300 seconds)
            should_check = minutes_since_last_check > 5
            
            if should_check:
                print(f"⏰ Last check was {minutes_since_last_check:.1f} minutes ago, running immediate check")
            else:
                print(f"⏰ Last check was {minutes_since_last_check:.1f} minutes ago, waiting for next scheduled check")
            
            return should_check
            
        except Exception as e:
            print(f"⚠️ Error checking last activity: {e}")
            import traceback
            traceback.print_exc()
            # On error, check immediately to be safe
            return True
    
    def _run_loop(self):
        """Background thread loop that checks every interval."""
        print(f"🔄 Notification Agent monitoring started (checking every {self.check_interval // 60} minutes)")
        
        # Check immediately on startup if it's been more than 5 minutes since last check
        if self._should_check_immediately():
            print("🚀 Running immediate check on startup...")
            try:
                self.process_notifications()
            except Exception as e:
                print(f"⚠️ Error in immediate check: {e}")
        
        while self.running:
            try:
                self.process_notifications()
            except Exception as e:
                print(f"⚠️ Error in notification loop: {e}")
            
            # Wait for next check
            time.sleep(self.check_interval)
    
    def start(self):
        """Start the background monitoring thread."""
        if self.running:
            print("⚠️ Notification Agent is already running")
            return
        
        if not self.db:
            print("⚠️ Cannot start Notification Agent: Firestore not available")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print(f"✅ Notification Agent started (checking every {self.check_interval // 60} minutes)")
    
    def stop(self):
        """Stop the background monitoring thread."""
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("🛑 Notification Agent stopped")


# Convenience function for easy importing
def create_notification_agent(
    firestore_db=None
) -> NotificationAgent:
    """
    Create a Notification Agent instance.
    
    Args:
        firestore_db: Optional Firestore database client
    
    Returns:
        NotificationAgent instance
    """
    return NotificationAgent(
        firestore_db=firestore_db
    )

