Build a multi-tool agent¶
This quickstart guides you through installing the Agent Development Kit (ADK), setting up a basic agent with multiple tools, and running it locally either in the terminal or in the interactive, browser-based dev UI.

This quickstart assumes a local IDE (VS Code, PyCharm, IntelliJ IDEA, etc.) with Python 3.9+ or Java 17+ and terminal access. This method runs the application entirely on your machine and is recommended for internal development.

1. Set up Environment & Install ADK¶

Python
Java
Create & Activate Virtual Environment (Recommended):


# Create
python -m venv .venv
# Activate (each new terminal)
# macOS/Linux: source .venv/bin/activate
# Windows CMD: .venv\Scripts\activate.bat
# Windows PowerShell: .venv\Scripts\Activate.ps1
Install ADK:


pip install google-adk

2. Create Agent Project¶
Project structure¶

Python
Java
You will need to create the following project structure:


parent_folder/
    multi_tool_agent/
        __init__.py
        agent.py
        .env
Create the folder multi_tool_agent:


mkdir multi_tool_agent/
Note for Windows users

When using ADK on Windows for the next few steps, we recommend creating Python files using File Explorer or an IDE because the following commands (mkdir, echo) typically generate files with null bytes and/or incorrect encoding.

__init__.py¶
Now create an __init__.py file in the folder:


echo "from . import agent" > multi_tool_agent/__init__.py
Your __init__.py should now look like this:

multi_tool_agent/__init__.py

from . import agent
agent.py¶
Create an agent.py file in the same folder:


OS X & Linux
Windows

touch multi_tool_agent/agent.py

Copy and paste the following code into agent.py:

multi_tool_agent/agent.py

import datetime
from zoneinfo import ZoneInfo
from google.adk.agents import Agent

def get_weather(city: str) -> dict:
    """Retrieves the current weather report for a specified city.

    Args:
        city (str): The name of the city for which to retrieve the weather report.

    Returns:
        dict: status and result or error msg.
    """
    if city.lower() == "new york":
        return {
            "status": "success",
            "report": (
                "The weather in New York is sunny with a temperature of 25 degrees"
                " Celsius (77 degrees Fahrenheit)."
            ),
        }
    else:
        return {
            "status": "error",
            "error_message": f"Weather information for '{city}' is not available.",
        }


def get_current_time(city: str) -> dict:
    """Returns the current time in a specified city.

    Args:
        city (str): The name of the city for which to retrieve the current time.

    Returns:
        dict: status and result or error msg.
    """

    if city.lower() == "new york":
        tz_identifier = "America/New_York"
    else:
        return {
            "status": "error",
            "error_message": (
                f"Sorry, I don't have timezone information for {city}."
            ),
        }

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    report = (
        f'The current time in {city} is {now.strftime("%Y-%m-%d %H:%M:%S %Z%z")}'
    )
    return {"status": "success", "report": report}


root_agent = Agent(
    name="weather_time_agent",
    model="gemini-2.0-flash",
    description=(
        "Agent to answer questions about the time and weather in a city."
    ),
    instruction=(
        "You are a helpful agent who can answer user questions about the time and weather in a city."
    ),
    tools=[get_weather, get_current_time],
)
.env¶
Create a .env file in the same folder:


OS X & Linux
Windows

touch multi_tool_agent/.env

More instructions about this file are described in the next section on Set up the model.


intro_components.png

3. Set up the model¶
Your agent's ability to understand user requests and generate responses is powered by a Large Language Model (LLM). Your agent needs to make secure calls to this external LLM service, which requires authentication credentials. Without valid authentication, the LLM service will deny the agent's requests, and the agent will be unable to function.

Model Authentication guide

For a detailed guide on authenticating to different models, see the Authentication guide. This is a critical step to ensure your agent can make calls to the LLM service.


Gemini - Google AI Studio
Gemini - Google Cloud Vertex AI
Gemini - Google Cloud Vertex AI with Express Mode
Get an API key from Google AI Studio.
When using Python, open the .env file located inside (multi_tool_agent/) and copy-paste the following code.

multi_tool_agent/.env

GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=PASTE_YOUR_ACTUAL_API_KEY_HERE
When using Java, define environment variables:

terminal

export GOOGLE_GENAI_USE_VERTEXAI=FALSE
export GOOGLE_API_KEY=PASTE_YOUR_ACTUAL_API_KEY_HERE
Replace PASTE_YOUR_ACTUAL_API_KEY_HERE with your actual API KEY.


4. Run Your Agent¶

Python
Java
Using the terminal, navigate to the parent directory of your agent project (e.g. using cd ..):


parent_folder/      <-- navigate to this directory
    multi_tool_agent/
        __init__.py
        agent.py
        .env
There are multiple ways to interact with your agent:


Dev UI (adk web)
Terminal (adk run)
API Server (adk api_server)
Authentication Setup for Vertex AI Users

If you selected "Gemini - Google Cloud Vertex AI" in the previous step, you must authenticate with Google Cloud before launching the dev UI.

Run this command and follow the prompts:


gcloud auth application-default login
Note: Skip this step if you're using "Gemini - Google AI Studio".

Run the following command to launch the dev UI.


adk web
Note for Windows users

When hitting the _make_subprocess_transport NotImplementedError, consider using adk web --no-reload instead.

Step 1: Open the URL provided (usually http://localhost:8000 or http://127.0.0.1:8000) directly in your browser.

Step 2. In the top-left corner of the UI, you can select your agent in the dropdown. Select "multi_tool_agent".

Troubleshooting

If you do not see "multi_tool_agent" in the dropdown menu, make sure you are running adk web in the parent folder of your agent folder (i.e. the parent folder of multi_tool_agent).

Step 3. Now you can chat with your agent using the textbox:

adk-web-dev-ui-chat.png

Step 4. By using the Events tab at the left, you can inspect individual function calls, responses and model responses by clicking on the actions:

adk-web-dev-ui-function-call.png

On the Events tab, you can also click the Trace button to see the trace logs for each event that shows the latency of each function calls:

adk-web-dev-ui-trace.png

Step 5. You can also enable your microphone and talk to your agent:

Model support for voice/video streaming

In order to use voice/video streaming in ADK, you will need to use Gemini models that support the Live API. You can find the model ID(s) that supports the Gemini Live API in the documentation:

Google AI Studio: Gemini Live API
Vertex AI: Gemini Live API
You can then replace the model string in root_agent in the agent.py file you created earlier (jump to section). Your code should look something like:


root_agent = Agent(
    name="weather_time_agent",
    model="replace-me-with-model-id", #e.g. gemini-2.0-flash-live-001
    ...
adk-web-dev-ui-audio.png



📝 Example prompts to try¶
What is the weather in New York?
What is the time in New York?
What is the weather in Paris?
What is the time in Paris?
🎉 Congratulations!¶
You've successfully created and interacted with your first agent using ADK

Agents¶
Supported in ADKPythonGoJava
In the Agent Development Kit (ADK), an Agent is a self-contained execution unit designed to act autonomously to achieve specific goals. Agents can perform tasks, interact with users, utilize external tools, and coordinate with other agents.

The foundation for all agents in ADK is the BaseAgent class. It serves as the fundamental blueprint. To create functional agents, you typically extend BaseAgent in one of three main ways, catering to different needs – from intelligent reasoning to structured process control.

Types of agents in ADK

Core Agent Categories¶
ADK provides distinct agent categories to build sophisticated applications:

LLM Agents (LlmAgent, Agent): These agents utilize Large Language Models (LLMs) as their core engine to understand natural language, reason, plan, generate responses, and dynamically decide how to proceed or which tools to use, making them ideal for flexible, language-centric tasks. Learn more about LLM Agents...

Workflow Agents (SequentialAgent, ParallelAgent, LoopAgent): These specialized agents control the execution flow of other agents in predefined, deterministic patterns (sequence, parallel, or loop) without using an LLM for the flow control itself, perfect for structured processes needing predictable execution. Explore Workflow Agents...

Custom Agents: Created by extending BaseAgent directly, these agents allow you to implement unique operational logic, specific control flows, or specialized integrations not covered by the standard types, catering to highly tailored application requirements. Discover how to build Custom Agents...

Choosing the Right Agent Type¶
The following table provides a high-level comparison to help distinguish between the agent types. As you explore each type in more detail in the subsequent sections, these distinctions will become clearer.

Feature	LLM Agent (LlmAgent)	Workflow Agent	Custom Agent (BaseAgent subclass)
Primary Function	Reasoning, Generation, Tool Use	Controlling Agent Execution Flow	Implementing Unique Logic/Integrations
Core Engine	Large Language Model (LLM)	Predefined Logic (Sequence, Parallel, Loop)	Custom Code
Determinism	Non-deterministic (Flexible)	Deterministic (Predictable)	Can be either, based on implementation
Primary Use	Language tasks, Dynamic decisions	Structured processes, Orchestration	Tailored requirements, Specific workflows
Agents Working Together: Multi-Agent Systems¶
While each agent type serves a distinct purpose, the true power often comes from combining them. Complex applications frequently employ multi-agent architectures where:

LLM Agents handle intelligent, language-based task execution.
Workflow Agents manage the overall process flow using standard patterns.
Custom Agents provide specialized capabilities or rules needed for unique integrations.
Understanding these core types is the first step toward building sophisticated, capable AI applications with ADK.