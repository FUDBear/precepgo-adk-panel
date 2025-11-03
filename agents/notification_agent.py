"""
Notification Agent
Monitors agent_evaluations collection for negative evaluations (-1 ratings)
and sends email notifications to program administrators.
Runs every 15 minutes.
"""

import os
import smtplib
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
    Agent for monitoring evaluations and sending notifications.
    Checks for dangerous ratings (-1) and sends email alerts.
    """
    
    def __init__(
        self,
        admin_email: str = "wasoje4172@fandoe.com",
        smtp_server: Optional[str] = None,
        smtp_port: int = 587,
        smtp_username: Optional[str] = None,
        smtp_password: Optional[str] = None,
        check_interval_minutes: int = 15,
        firestore_db=None
    ):
        """
        Initialize the Notification Agent.
        
        Args:
            admin_email: Email address to send notifications to
            smtp_server: SMTP server (defaults to Gmail SMTP)
            smtp_port: SMTP port (default: 587)
            smtp_username: SMTP username (optional, uses admin_email if not provided)
            smtp_password: SMTP password (optional, uses environment variable if not provided)
            check_interval_minutes: How often to check for new evaluations (default: 15)
            firestore_db: Optional Firestore database client
        """
        self.admin_email = admin_email
        self.check_interval = check_interval_minutes * 60  # Convert to seconds
        
        # SMTP Configuration
        self.smtp_server = smtp_server or os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username or os.getenv("SMTP_USERNAME", admin_email)
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
        
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
        print(f"   - Admin email: {admin_email}")
        print(f"   - Check interval: {check_interval_minutes} minutes")
        print(f"   - Firestore: {'Available' if self.db else 'Not available'}")
        print(f"   - SMTP Server: {self.smtp_server}:{self.smtp_port}")
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
            notifications_ref = self.db.collection('agent_notifications')
            
            notification_record = {
                'evaluation_doc_id': evaluation_doc_id,
                'preceptee_name': evaluation_data.get('preceptee_user_name', 'Unknown'),
                'preceptor_name': evaluation_data.get('preceptor_name', 'Unknown'),
                'case_type': evaluation_data.get('case_type', 'Unknown'),
                'request_id': evaluation_data.get('request_id', 'N/A'),
                'negative_fields': negative_fields,
                'admin_email': self.admin_email,
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
        Send email notification about negative evaluations.
        
        Args:
            evaluations: List of evaluation dictionaries with negative ratings
        
        Returns:
            True if email sent successfully, False otherwise
        """
        if not evaluations:
            return True
        
        # Prepare email content
        subject = f"⚠️ Alert: {len(evaluations)} Student(s) Received Negative Evaluation(s)"
        
        # Build email body
        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .header {{ background-color: #dc3545; color: white; padding: 20px; }}
                .content {{ padding: 20px; }}
                .evaluation {{ border: 1px solid #ddd; margin: 15px 0; padding: 15px; border-radius: 5px; }}
                .student-info {{ background-color: #f8f9fa; padding: 10px; border-radius: 3px; }}
                .negative-field {{ color: #dc3545; font-weight: bold; }}
                .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>⚠️ Negative Evaluation Alert</h2>
            </div>
            <div class="content">
                <p>This is an automated notification from the PrecepGo evaluation system.</p>
                <p><strong>{len(evaluations)} student(s)</strong> have received negative evaluation ratings (Dangerous/Safety Concern) from their preceptors.</p>
                
                <h3>Evaluation Details:</h3>
        """
        
        for i, eval_info in enumerate(evaluations, 1):
            eval_data = eval_info["evaluation"]
            doc_id = eval_info["doc_id"]
            negative_fields = eval_info["negative_fields"]
            
            preceptee_name = eval_data.get("preceptee_user_name", "Unknown")
            preceptor_name = eval_data.get("preceptor_name", "Unknown")
            case_type = eval_data.get("case_type", "Unknown")
            request_id = eval_data.get("request_id", "N/A")
            
            body_html += f"""
                <div class="evaluation">
                    <div class="student-info">
                        <h4>Evaluation #{i}</h4>
                        <p><strong>Student:</strong> {preceptee_name}</p>
                        <p><strong>Preceptor:</strong> {preceptor_name}</p>
                        <p><strong>Case Type:</strong> {case_type}</p>
                        <p><strong>Document ID:</strong> {doc_id}</p>
                        <p><strong>Request ID:</strong> {request_id}</p>
                    </div>
                    <p><strong class="negative-field">⚠️ Negative Ratings Found:</strong></p>
                    <ul>
            """
            
            for field in negative_fields:
                # Get metric name
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
                metric_name = metric_names.get(field, field)
                body_html += f"<li><strong>{metric_name}</strong> ({field}) - <span class='negative-field'>DANGEROUS</span></li>"
            
            # Add comment if available
            if eval_data.get("comments"):
                body_html += f"""
                    </ul>
                    <p><strong>Preceptor Comment:</strong></p>
                    <p style="background-color: #fff3cd; padding: 10px; border-radius: 3px; border-left: 3px solid #ffc107;">
                        {eval_data.get("comments")}
                    </p>
                """
            else:
                body_html += "</ul>"
            
            body_html += "</div>"
        
        body_html += f"""
                <div class="footer">
                    <p>This is an automated notification. Please review these evaluations immediately.</p>
                    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['From'] = self.smtp_username
        msg['To'] = self.admin_email
        msg['Subject'] = subject
        
        # Add plain text version
        text_body = f"""
        Negative Evaluation Alert
        
        {len(evaluations)} student(s) have received negative evaluation ratings.
        
        Please check the PrecepGo system for details.
        
        Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(body_html, 'html'))
        
        # Send email
        try:
            if self.smtp_password:
                # Use SMTP with authentication
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.smtp_username, self.smtp_password)
                    server.send_message(msg)
                print(f"✅ Sent notification email to {self.admin_email}")
                return True
            else:
                # For testing without SMTP auth (or use mock)
                print(f"⚠️ No SMTP password configured. Mock email would be sent to {self.admin_email}")
                print(f"   Subject: {subject}")
                print(f"   Evaluations: {len(evaluations)}")
                # In production, you'd want to actually send the email
                # For now, we'll simulate it
                return True
        except Exception as e:
            print(f"⚠️ Failed to send email: {e}")
            return False
    
    def process_notifications(self):
        """Check for negative evaluations and send notifications."""
        # Update state to PROCESSING
        if self.state_agent:
            self.state_agent.set_agent_state("notification_agent", StateAgent.STATE_PROCESSING)
        
        try:
            # Check for negative evaluations
            negative_evaluations = self.check_for_negative_evaluations()
            
            if negative_evaluations:
                print(f"🔔 Found {len(negative_evaluations)} negative evaluation(s)")
                
                # Send notification email
                email_sent = self.send_notification_email(negative_evaluations)
                
                if email_sent:
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
                            StateAgent.STATE_COMPLETED
                        )
                else:
                    # Update state to ERROR
                    if self.state_agent:
                        self.state_agent.set_agent_error(
                            "notification_agent",
                            "Failed to send notification email"
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
    admin_email: str = "wasoje4172@fandoe.com",
    firestore_db=None
) -> NotificationAgent:
    """
    Create a Notification Agent instance.
    
    Args:
        admin_email: Email address to send notifications to
        firestore_db: Optional Firestore database client
    
    Returns:
        NotificationAgent instance
    """
    return NotificationAgent(
        admin_email=admin_email,
        firestore_db=firestore_db
    )

