"""
PrecepGo ADK Panel - Agents
Google ADK compliant agents for CRNA education automation.
"""

# Import ADK agents
from agents.evaluations_agent import evaluation_agent
from agents.notification_agent import notification_agent
from agents.scenario_agent import scenario_agent
from agents.time_agent import time_agent
from agents.site_agent import site_agent
from agents.coa_agent import coa_agent
from agents.root_agent import root_agent, safety_pipeline

# Export all ADK agents
__all__ = [
    "root_agent",
    "safety_pipeline",
    "evaluation_agent",
    "notification_agent",
    "scenario_agent",
    "time_agent",
    "site_agent",
    "coa_agent",
]
