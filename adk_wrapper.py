"""
ADK Agent Wrapper
Provides lazy loading of ADK agents for FastAPI integration.
Prevents import errors if ADK isn't available.
"""

from typing import Optional, Dict, Any

# Lazy-loaded ADK agents
_root_agent = None
_safety_pipeline = None
_evaluation_agent = None
_notification_agent = None
_scenario_agent = None
_time_agent = None

ADK_AVAILABLE = False


def _load_adk_agents():
    """Lazy load ADK agents only when needed."""
    global _root_agent, _safety_pipeline, _evaluation_agent
    global _notification_agent, _scenario_agent, _time_agent, ADK_AVAILABLE

    if _root_agent is not None:
        return  # Already loaded

    try:
        from agents.root_agent import root_agent, safety_pipeline
        from agents.evaluations_agent import evaluation_agent
        from agents.notification_agent import notification_agent
        from agents.scenario_agent import scenario_agent
        from agents.time_agent import time_agent

        _root_agent = root_agent
        _safety_pipeline = safety_pipeline
        _evaluation_agent = evaluation_agent
        _notification_agent = notification_agent
        _scenario_agent = scenario_agent
        _time_agent = time_agent

        ADK_AVAILABLE = True
        print("✅ ADK agents loaded successfully")

    except ImportError as e:
        print(f"⚠️ ADK agents not available: {e}")
        ADK_AVAILABLE = False


def get_root_agent():
    """Get the root ADK agent (lazy loaded)."""
    _load_adk_agents()
    return _root_agent


def get_safety_pipeline():
    """Get the safety pipeline workflow (lazy loaded)."""
    _load_adk_agents()
    return _safety_pipeline


def get_evaluation_agent():
    """Get the evaluation agent (lazy loaded)."""
    _load_adk_agents()
    return _evaluation_agent


def get_notification_agent():
    """Get the notification agent (lazy loaded)."""
    _load_adk_agents()
    return _notification_agent


def get_scenario_agent():
    """Get the scenario agent (lazy loaded)."""
    _load_adk_agents()
    return _scenario_agent


def get_time_agent():
    """Get the time agent (lazy loaded)."""
    _load_adk_agents()
    return _time_agent


def is_adk_available() -> bool:
    """Check if ADK agents are available."""
    _load_adk_agents()
    return ADK_AVAILABLE


async def run_adk_agent(agent, message: str) -> Dict[str, Any]:
    """
    Run an ADK agent with a message.

    Args:
        agent: The ADK agent to run
        message: The message to send to the agent

    Returns:
        Dict with agent response
    """
    if not agent:
        return {
            "error": "ADK agent not available",
            "message": "ADK agents failed to load"
        }

    try:
        # ADK agents are executed by the framework
        # For now, we just return agent info
        return {
            "status": "success",
            "agent_name": agent.name if hasattr(agent, 'name') else "unknown",
            "message": f"ADK agent {agent.name} is ready",
            "note": "Use 'adk run .' or 'adk web' for full ADK interaction"
        }
    except Exception as e:
        return {
            "error": str(e),
            "message": "Failed to run ADK agent"
        }


# Export all functions
__all__ = [
    "get_root_agent",
    "get_safety_pipeline",
    "get_evaluation_agent",
    "get_notification_agent",
    "get_scenario_agent",
    "get_time_agent",
    "is_adk_available",
    "run_adk_agent"
]
