"""
PrecepGo ADK Panel - Main Entry Point
Google ADK compliant agent for CRNA education automation.

This is the entry point file that Google ADK looks for.
It exports the root_agent which coordinates all sub-agents.
"""

# Import the root agent
from agents.root_agent import root_agent, safety_pipeline

# Export for ADK
# ADK will look for 'root_agent' as the main agent to deploy
__all__ = ["root_agent", "safety_pipeline"]

# Make root_agent the default export
agent = root_agent
