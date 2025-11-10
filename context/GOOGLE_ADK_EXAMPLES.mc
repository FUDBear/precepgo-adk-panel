About this codelab
subjectLast updated Sep 29, 2025
account_circleWritten by a Googler
1. Introduction
Overview
In this codelab, you will deploy an ADK agent to Cloud Run as a backend service, and then deploy a gradio frontend for the ADK agent as a second Cloud Run service. This codelab shows how to require authentication to your ADK agent service and make authenticated calls to it from the gradio frontend service.

What you'll learn
How to deploy an ADK agent to Cloud Run
How to deploy a gradio app to Cloud Run
How to make authenticated service-to-service calls in Cloud Run

2. Enable APIs
First, set your Google Cloud project.


gcloud config set project <YOUR_PROJECT_ID>
You can confirm your Google Cloud project by running the following command:


gcloud config get-value project
This codelab requires enabling the following APIs:


gcloud services enable run.googleapis.com \
    compute.googleapis.com \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    aiplatform.googleapis.com

    3. Setup and Requirements
In this section, you'll create a couple of service accounts and grant them the appropriate IAM roles. Each cloud run service will have its own Service Account.

First, set environment variables for this codelab that will be used throughout this codelab.


export PROJECT_ID=<YOUR_PROJECT_ID>
export REGION=<YOUR_REGION>

export SERVICE_ACCOUNT_ADK="adk-agent-cr"
export SERVICE_ACCOUNT_ADDRESS_ADK=$SERVICE_ACCOUNT_ADK@$PROJECT_ID.iam.gserviceaccount.com

export SERVICE_ACCOUNT_GRADIO="adk-agent-gradio"
export SERVICE_ACCOUNT_ADDRESS_GRADIO=$SERVICE_ACCOUNT_GRADIO@$PROJECT_ID.iam.gserviceaccount.com

export AGENT_APP_NAME="multi_tool_agent"
Next, create the service account for the ADK agent.


gcloud iam service-accounts create $SERVICE_ACCOUNT_ADK \
--display-name="Service account for adk agent on cloud run"
And grant the ADK service account the "Vertex AI User" role


gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_ADDRESS_ADK" \
  --role="roles/aiplatform.user"
Now, create the service account for the Gradio frontend


gcloud iam service-accounts create $SERVICE_ACCOUNT_GRADIO \
  --display-name="Service account for gradio frontend cloud run"
And grant the Gradio frontend the Cloud Run invoker role, which will allow it to call the ADK agent hosted on Cloud Run.


gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_ADDRESS_GRADIO" \
  --role="roles/run.invoker"

  4. Create an ADK app
In the next step, you'll create the code for the ADK quickstart application.

Note: at the end of the lab, your file structure should look like the following:


- codelab-gradio-adk  <-- you'll deploy the ADK agent from here
  - gradio-frontend  <-- you'll deploy the gradio app from here
    - app.py
    - requirements.txt
  - multi_tool_agent
    - __init__.py
    - agent.py
    - requirements.txt
First, create a directory for the overall codelab


mkdir codelab-gradio-adk
cd codelab-gradio-adk
Now, create a directory for the ADK agent service.


mkdir multi_tool_agent && cd multi_tool_agent
Create a __init__.py file with the following contents:


from . import agent
Create a requirements.txt file:


google-adk
Create a file called agent.py


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
    model="gemini-2.5-flash",
    description=(
        "Agent to answer questions about the time and weather in a city."
    ),
    instruction=(
        "You are a helpful agent who can answer user questions about the time and weather in a city."
    ),
    tools=[get_weather, get_current_time],
)

5. Deploy the ADK agent
In this section, you'll deploy the ADK agent to Cloud Run. Then you'll verify the deployment worked using the dev web UI that's provided by ADK. Lastly, you'll require authenticated calls to this service.

Navigate to the parent folder.

NOTE: The ADK agent code must include the multi_tool_agent folder as its root folder.


cd ..
First, create the Cloud Run service:

NOTE: the --with_ui is optional to test with the Dev UI, as shown in an upcoming step:

NOTE: the -- command allows you to pass through command line flags to the underlying gcloud run deploy command.

NOTE: the uvx --from executes a command from the google-adk package. uvx will create a temporary virtual environment, install google-adk into it, run the specified command, and then tear down the environment.


uvx --from google-adk \
adk deploy cloud_run \
    --project=$PROJECT_ID \
    --region=$REGION \
    --service_name=adk-agent-cr \
    --with_ui \
    ./multi_tool_agent \
    -- \
    --service-account=$SERVICE_ACCOUNT_ADDRESS_ADK \
    --allow-unauthenticated
Next, save the URL as an env var that you will use in the second part of this codelab


AGENT_SERVICE_URL=$(gcloud run services describe adk-agent-cr --region $REGION --format 'value(status.url)')
Now, try the agent

Open the service URL in your web browser and ask, tell me about the weather in new york. You should see a response similar to "The weather in New York is sunny with a temperature of 25 degrees Celsius (77 degrees Fahrenheit)."

Lastly, Secure the agent

Let's now secure access to the agent. In the next section, you'll deploy a Cloud Run service that makes an authenticated call to this backend service.


gcloud run services remove-iam-policy-binding adk-agent-cr \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --region=$REGION

  6. Deploy a gradio front-end
In this step, you'll create a gradio frontend for your ADK agent

Note: You can have the gradio app in the same service as the ADK agent. This codelab provides 2 separate services to show how to make authenticated service to service calls in Cloud Run.

First, create an app alongside the multi_tool_agent folder


mkdir gradio-frontend && cd gradio-frontend
Next, create a requirements.txt file that contains the following


gradio
requests
google-auth
Now, create an app.py file


import gradio as gr
import requests
import json
import uuid
import os
import google.auth.transport.requests
import google.oauth2.id_token

# https://weather-time-service2-392295011265.us-west4.run.app
BASE_URL = os.environ.get("AGENT_SERVICE_URL")

# multi_tool_agent
APP_NAME = os.environ.get("AGENT_APP_NAME")

# Generate a unique user ID for each session of the Gradio app
USER_ID = f"gradio-user-{uuid.uuid4()}"

# API Endpoints
CREATE_SESSION_URL = f"{BASE_URL}/apps/{APP_NAME}/users/{USER_ID}/sessions"
RUN_SSE_URL = f"{BASE_URL}/run_sse"

def get_id_token():
    """Get an ID token to authenticate with the other Cloud Run service."""
    audience = BASE_URL
    request = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(request, audience)
    return id_token

def create_session() -> str | None:
    """Creates a new session and returns the session ID."""
    try:
        id_token = get_id_token()
        headers = {"Authorization": f"Bearer {id_token}"}
        response = requests.post(CREATE_SESSION_URL, headers=headers)
        response.raise_for_status()
        return response.json().get("id")
    except Exception as e:
        print(f"Error creating session: {e}")
        return None

def query_agent(prompt: str):
    """Sends a prompt to the agent and returns the streamed response."""
    session_id = create_session()
    if not session_id:
        return "Error: Could not create a session."

    id_token = get_id_token()
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {id_token}",
    }
    payload = {
        "app_name": APP_NAME,
        "user_id": USER_ID,
        "session_id": session_id,
        "new_message": {"role": "user", "parts": [{"text": prompt}]},
        "streaming": True
    }

    full_response = ""
    try:
        with requests.post(RUN_SSE_URL, headers=headers, json=payload, stream=True) as response:
            response.raise_for_status()
            for chunk in response.iter_lines():
                if chunk and chunk.decode('utf-8').startswith('data:'):
                    json_data = chunk.decode('utf-8')[len('data:'):].strip()
                    try:
                        data = json.loads(json_data)
                        text = data.get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text:
                            full_response = text
                    except json.JSONDecodeError:
                        pass # Ignore chunks that are not valid JSON
        return full_response
    except requests.exceptions.RequestException as e:
        return f"An error occurred: {e}"

iface = gr.Interface(
    fn=query_agent,
    inputs=gr.Textbox(lines=2, placeholder="e.g., What's the weather in new york?"),
    outputs="text",
    title="Weather and Time Agent",
    description="Ask a question about the weather or time in a specific location.",
)

if __name__ == "__main__":
    iface.launch()

    7. Deploy and test your gradio app
In this step, you'll deploy the front end gradio app to Cloud Run.

Make sure you are in the gradio app directory.


pwd
You should see codelab-gradio-adk/gradio-frontend

Now deploy your gradio app.

Note: although this gradio frontend service is a publicly available website, the backend service requires authentication. To illustrate why you might want to do this, you could add user authentication (e.g. Firebase Auth) to this frontend service and then only allow users who are signed in to make calls to the backend service.


gcloud run deploy my-adk-gradio-frontend \
--source . \
--region $REGION \
--allow-unauthenticated \
--set-env-vars AGENT_SERVICE_URL=$AGENT_SERVICE_URL,AGENT_APP_NAME=$AGENT_APP_NAME \
--service-account=$SERVICE_ACCOUNT_ADDRESS_GRADIO
once deployed, ask what's the weather in new york? and you should get a response similar to The weather in New York is sunny with a temperature of 25 degrees Celsius (77 degrees Fahrenheit).

8. Congratulations!
Congratulations for completing the codelab!

We recommend reviewing the documentation on hosting AI apps and agents documentation.

What we've covered
How to deploy an ADK agent to Cloud Run
How to deploy a gradio app to Cloud Run
How to make authenticated service-to-service calls in Cloud Run

9. Clean up
To avoid inadvertent charges, for example, if the Cloud Run services are inadvertently invoked more times than your monthly Cloud Run invokement allocation in the free tier, you can delete the Cloud Run service you created in Step 6.

To delete the Cloud Run services, go to the Cloud Run Cloud Console at https://console.cloud.google.com/run and delete the my-adk-gradio-frontend and adk-agent-cr services.

To delete the entire project, go to Manage Resources, select the project you created in Step 2, and choose Delete. If you delete the project, you'll need to change projects in your Cloud SDK. You can view the list of all available projects by running gcloud projects list.

Deploying Google-ADK Agent to Cloud Run
About this codelab
schedule
15 minutes
subject
Last updated November 7, 2025
account_circle
Written by Harisam Sharma, Smriti Naik
1. Introduction 
You will create an agent that can answer any query about the news and deploy it in Cloud Run. The news could be about any topic pertaining to only one location ‘Bengaluru'. Some of the queries can be:

Can you tell me about some latest news from Bengaluru?
Give me some recent news related to Bengaluru traffic.
You can deploy Agents on Cloud Run. We will create a simple agent that uses the model and a local tool, then deploy it.

What you will learn
How to set up a Google Cloud Project for Cloud Run.
How to build a simple AI agent using Google ADK.
How to define and use local tools within the agent.
How to package the agent using Docker.
How to deploy the agent as a service on Google Cloud Run.
How to interact with the deployed agent through a web UI.
What you will need
A gmail account
Chrome browser
2. Setup 
Ensure you have the Google Cloud Project with billing setup.
Clone the Github repository:

git clone https://github.com/abhishekr700/Cloud-Run-Day-Workshop-2025.git
Navigate into the directory for the 1st workshop:

cd Cloud-Run-Day-Workshop-2025/workshop1
3. Deploy the Agent to Cloud Run 
Once you have all the files ready in your Cloud Shell editor, execute the following commands in the Cloud Shell terminal to deploy the service to Cloud Run:


gcloud run deploy news-assistant-agent \
--source . \
--region $REGION \
--project $PROJECT_ID \
--allow-unauthenticated \
--set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=$GOOGLE_GENAI_USE_VERTEXAI,GOOGLE_API_KEY=$GOOGLE_API_KEY"
(Confirm the deployment by typing ‘Y' when/if prompted.)

4. Test the Agent 
Upon successful deployment, the Cloud Shell will output the URL for the deployed Cloud Run service.

Screenshot of Cloud Run service URL output

When you open the link, you can directly interact with your agent using the ADK web UI:

Screenshot of the ADK Web UI 

5. Cleanup 
To avoid incurring future charges, delete the Cloud Run service that you have created.


gcloud run services delete news-assistant-agent --region $REGION $GOOGLE_CLOUD_LOCATION  --quiet
6. Congratulations! 
You have successfully built and deployed an AI News Agent to Google Cloud Run!

About this codelab
subjectLast updated Nov 6, 2025
account_circleWritten by Mollie Pettit
1. Introduction
Overview
This lab teaches you how to orchestrate complex, multi-agent systems using the Google Agent Development Kit (Google ADK). You'll move from simple agent hierarchies to building automated, collaborative workflows.

What you'll build
You'll build two distinct multi-agent systems:

A simple travel planning agent that learns to transfer conversations between a "brainstorming" agent and an "attraction planning" agent.
A more advanced movie pitch generator that uses a "writer's room" of automated agents (like a researcher, screenwriter, and critic) to work together in a loop to create a full movie plot.
What you'll learn
How to create parent and sub-agent relationships.
How to write data to the session state from a tool.
How to read from the state using key templating (e.g., {my_key?}).
How to use a SequentialAgent for step-by-step workflows.
How to use a LoopAgent to create iterative refinement cycles.
How to use a ParallelAgent to run independent tasks concurrently.

2. Multi-Agent Systems
The Agent Development Kit (ADK) empowers developers to get more reliable, sophisticated, multi-step behaviors from generative models. Instead of one complex prompt, ADK lets you build a flow of multiple, simpler agents that collaborate on a problem by dividing the work.

This approach has several advantages over using a single, monolithic prompt:

Simpler Design: It's simpler to design and organize a flow of small, specialized agents than to engineer one large, complex prompt.
Reliability: Specialized agents are more reliable at their specific tasks than one large, complex agent.
Maintainability: It's easier to fix or improve a small, specialized agent without breaking other parts of the system.
Modularity: Agents built for one workflow can be easily reused in others.
The Hierarchical Agent Tree
Tree structure showing hierarchical agents

In ADK, you organize agents in a tree structure. This hierarchy is key to controlling the conversation's flow, as it limits which agent can "pass" the conversation to which other agent. This makes the system's behavior more predictable and easier to debug. Benefits include:

Intuitive Design: The structure is inspired by real-world teams, making it easier to reason about.
Controlled Flow: The hierarchy gives you precise control over task delegation, which helps in debugging. For example, the tree structure ensures the correct report-writing agent is called, even if you have two with similar descriptions.
The entire structure starts with the root_agent. This agent acts as a parent and can have one or more sub-agents, which in turn can also be parents to their own sub-agents, forming the tree.

3. Project setup
Google Account
If you don't already have a personal Google Account, you must create a Google Account.

Use a personal account instead of a work or school account.

Work and school accounts may have restrictions that prevent you from enabling the APIs needed for this lab.

Sign-in to the Google Cloud Console
Sign-in to the Google Cloud Console using a personal Google account.

Enable Billing
Redeem $5 Google Cloud credits (optional)
To run this workshop, you need a Billing Account with some credit. If you are planning to use your own billing, you can skip this step.

Click this link and sign in with a personal google account.You will see something like this:Click here for credits page
Click the CLICK HERE TO ACCESS YOUR CREDITS button.This will bring you to a page to set up your billing profileSet up billing profile page
Click Confirm
You are now connected to a Google Cloud Platform Trial Billing Account.

Screenshot of billing overview

Set up a personal billing account
If you set up billing using Google Cloud credits, you can skip this step.

To set up a personal billing account, go here to enable billing in the Cloud Console.

Some Notes:

Completing this lab should cost less than $1 USD in Cloud resources.
You can follow the steps at the end of this lab to delete resources to avoid further charges.
New users are eligible for the $300 USD Free Trial.
Create a project (optional)
If you do not have a current project you'd like to use for this labe, create a new project here.

4. Open Cloud Shell Editor
Click this link to navigate directly to Cloud Shell Editor
If prompted to authorize at any point today, click Authorize to continue.Click to authorize Cloud Shell
If the terminal doesn't appear at the bottom of the screen, open it:
Click View
Click TerminalOpen new terminal in Cloud Shell Editor
In the terminal, set your project with this command:

gcloud config set project [PROJECT_ID]
Example:

gcloud config set project lab-project-id-example
If you can't remember your project ID, you can list all your project IDs with:

gcloud projects list
Set project id in Cloud Shell Editor terminal
You should see this message:

Updated property [core/project].
If you see a WARNING and are asked Do you want to continue (Y/n)?, then you have likely entered the project ID incorrectly. Press n, press Enter, and try to run the gcloud config set project command again.

5. Enable APIs
To use the Vertex AI API and interact with the Gemini model, you need to enable the Vertex AI API in your Google Cloud project.

In the terminal, enable the API:

gcloud services enable aiplatform.googleapis.com
Here are the updated sections, replacing the manual file creation with instructions to clone the GitHub repository and install the dependencies.

Introduction to the Vertex AI SDK for Python
To interact with models hosted on Vertex AI from your Python application, you'll use the Vertex AI SDK for Python. This SDK simplifies the process of sending prompts, specifying model parameters, and receiving responses without needing to handle the complexities of the underlying API calls directly.

You can find comprehensive documentation for the Vertex AI SDK for Python here: Introduction to the Vertex AI SDK for Python | Google Cloud.

6. Set up the project environment
Clone the repo
In the terminal, clone the repository containing the starter files.

git clone --depth 1 https://github.com/GoogleCloudPlatform/devrel-demos.git
The --depth 1 flag clones only the latest version, which is faster.
In the terminal, navigate to the correct working directory for this lab.

cd devrel-demos/ai-ml/build-multiagent-systems-with-adk/adk_multiagent_systems
Activate a virtual environment
In the terminal, create and activate a virtual environment using uv:

uv venv
source .venv/bin/activate
In the terminal, install google-adk and the other dependencies from the requirements.txt file:

uv pip install -r requirements.txt
Review your file structure
Now that all your files are created, open the adk_multiagent_systems folder in the explorer to see the full structure.

In the Cloud Shell Editor menu, select File > Open Folder....
Cloud Shell Editor File menu with Open Folder selected
In the box that pops up, add the following folder information after your username: devrel-demos/ai-ml/build-multiagent-systems-with-adk/adk_multiagent_systems/. Click OK.
It should look something like this:
Open Folder dialog box with project path
The explorer panel on the left will refresh. You should now see your complete project structure, with the parent_and_subagents and workflow_agents sub-directories, ready for the next steps.
Explorer panel showing the open adk_multiagent_systems folder
If the terminal disappears when you do this, you can reopen it by clicking View and then Terminal in the top menu.

Set up environment variables
You are already in the adk_multiagent_systems directory. In the terminal, create a .env file to store your environment variables:

cloudshell edit .env
Paste the following into the .env file that opens in the editor:

GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT="[YOUR-PROJECT-ID]"
GOOGLE_CLOUD_LOCATION=global
MODEL="gemini-2.5-flash"
Replace [YOUR-PROJECT-ID] with your actual Google Cloud Project ID. (e.g. PROJECT_ID = "google-cloud-labs")
If you can't remember your project ID, run the following command in your terminal. It will show you a list of all your projects and their IDs.

gcloud projects list
In the terminal, copy this .env file into the sub-agent directories so they can also access the variables:

cp .env parent_and_subagents/.env
cp .env workflow_agents/.env
The file structure should now look like this:
Explorer panel showing the open adk_multiagent_systems folder

7. Explore transfers between parent, sub-agent, and peer agents
The conversation always starts with the root_agent. By default, a parent agent uses its sub-agents' description to decide when to transfer the conversation. You can also guide these transfers explicitly in the parent's instruction by using the sub-agents' name.

Let's test this.

In the Cloud Shell Editor, open adk_multiagent_systems/parent_and_subagents/agent.py. Notice the three agents in the agent.py file:
root_agent (named steering): Asks the user a question to decide which sub-agent to transfer to. Initially, it relies only on its sub-agents' description.
travel_brainstormer: Helps the user brainstorm destinations.
attractions_planner: Helps the user list things to do in a specific country.
Tip: To read an agent.py file in conversation-flow order, it's often easiest to start reading from the root_agent at the bottom and work your way up. This is because Python code requires that we define our sub-agents before we can add them to an agent.

Make travel_brainstormer and attractions_planner sub-agents of the root_agent by adding the following line to the creation of the root_agent:

    sub_agents=[travel_brainstormer, attractions_planner]
Note: The agent hierarchy is defined only by the parent's sub_agents list; sub-agents don't need a parent parameter.

In the terminal, chat with your agent:

cd ~/devrel-demos/ai-ml/build-multiagent-systems-with-adk/adk_multiagent_systems
adk run parent_and_subagents
At the [user]: prompt in the terminal, type:

hello
Example output (Yours may be a little different):

[steering]: Hi there! Do you already have a country in mind for your trip, or would you like some help deciding where to go?
Now, tell the agent in the terminal:

I could use some help deciding.
Example output (Yours may be a little different):

[travel_brainstormer]: Okay! To give you the best recommendations, I need to understand what you're looking for in a trip.
...
Notice the [travel_brainstormer] tag. The root_agent transferred control based only on the sub-agent's description.
At the user: prompt in the terminal, type exit and press ENTER to end the conversation.
Now let's be more explicit. In agent.py, add the following to the root_agent's instruction:

        If they need help deciding, send them to 'travel_brainstormer'.
        If they know what country they'd like to visit, send them to the 'attractions_planner'.
In the terminal, run the agent again:

adk run parent_and_subagents
At the [user]: prompt in the terminal, type:

hello
Reply with:

I would like to go to Japan.
Example output (Yours may be a little different):

[attractions_planner]: Okay, I can help you with that! Here are some popular attractions in Japan:
...
Notice the transfer to attractions_planner, as guided by your new instructions.
Now reply with:

Actually I don't know what country to visit.
Example output (Yours may be a little different):

[travel_brainstormer]: Okay! I can help you brainstorm some countries for travel...
Notice that you've been transferred to travel_brainstormer, a peer of attractions_planner. This is allowed by default.
If you'd like to prevent transferring, you could set disallow_transfer_to_peers=True on the attractions_planner agent.

At the user prompt, type exit to end the session.
Recap
In this section, you learned the fundamentals of agent hierarchy and conversation flow:

The conversation always starts with the root_agent.
A parent agent can automatically transfer to a sub-agent based on its description.
You can explicitly control this flow by giving the parent instruction to transfer to a sub-agent by its name.
By default, agents can transfer to their peer agents (siblings in the hierarchy).

8. Use session state to store and retrieve information
Every ADK conversation has a Session, which includes a session state dictionary. This state is accessible to all agents, making it the perfect way to pass information between them or maintain data (like a list) throughout the conversation.

To explore adding to and reading from state:

Return to the file adk_multiagent_systems/parent_and_subagents/agent.py
Paste the following function definition after the # Tools header:

def save_attractions_to_state(
tool_context: ToolContext,
attractions: List[str]
) -> dict[str, str]:
    """Saves the list of attractions to state["attractions"].

    Args:
        attractions [str]: a list of strings to add to the list of attractions

    Returns:
        None
    """
    # Load existing attractions from state. If none exist, start an empty list
    existing_attractions = tool_context.state.get("attractions", [])

    # Update the 'attractions' key with a combo of old and new lists.
    # When the tool is run, ADK will create an event and make
    # corresponding updates in the session's state.
    tool_context.state["attractions"] = existing_attractions + attractions

    # A best practice for tools is to return a status message in a return dict
    return {"status": "success"}
In this code, notice:
The function receives tool_context: ToolContext. This object is your gateway to the session.
The line tool_context.state["attractions"] = ... directly reads from and writes to the session's state dictionary. The ADK handles the rest.
Add the tool to the attractions_planner agent by adding the tools parameter:

    tools=[save_attractions_to_state]
Add the following bullet points to the attractions_planner agent's existing instruction:

        - When they reply, use your tool to save their selected attraction and then provide more possible attractions.
        - If they ask to view the list, provide a bulleted list of { attractions? } and then suggest some more.
Notice the section in curly braces: { attractions? }. This ADK feature, key templating, injects the value of the attractions key from the state into the agent's prompt. The ? makes it optional, preventing errors if the key doesn't exist yet.

Launch the Agent Development Kit Web UI with the following command in the terminal:

adk web
Output

INFO:     Started server process [2434]
INFO:     Waiting for application startup.
+-------------------------------------------------------+
| ADK Web Server started                                |
|                                                       |
| For local testing, access at http://localhost:8000.   |
+-------------------------------------------------------+

INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
Note: If port 8000 is in use, you can run on a different port, for example: adk web --port 8001. The port number input in the next steps will need to be updated to match.

In the Cloud Shell terminal, click the To view the web interface in a new tab, click the Web Preview button and select Change Port.
Web Preview menu
Input port number 8000 and click Change and Preview. A new browser tab will open with the ADK Dev UI.
Change port pop-up box with 8000 entered in text box
From the Select an agent dropdown on the left, choose parent_and_subagents.
Start the conversation with: hello
After the agent greets you, reply with:

I'd like to go to Egypt.
You should be transferred to the attractions_planner and provided a list of attractions.
Choose an attraction, for example:

I'll go to the Sphinx
You should get a response like: Okay, I've saved The Sphinx to your list...
Click the response tool box (marked with a check mark) to view the event created from the tool's response.
Notice that it includes an actions field which includes stateDelta describing the changes to the state.
Reply with another attraction from the agent's list.
On the left-hand navigation menu, click the "X" to exit the focus on the event you inspected earlier.
In the left-hand sidebar, click the State tab. You can now see the attractions array in the session's state, which should contain both of your selected items.Session State preview in the Web UI
Send this message to the agent:

What is on my list?
The agent should now read from the state and return your list.
When you are finished experimenting with the agent, close the web browser tab and press CTRL + C in the Cloud Shell Terminal to stop the server.
To store an agent's entire text response in the state, you can set an output_key parameter when you define the agent, and its entire output will be stored in the state dictionary under that field name.

Section Recap
In this section, you learned how to use the Session state to share data:

To write state: You write to the state dictionary from within a tool, using the tool_context.state object (e.g., tool_context.state["my_list"] = [...]).
To read state: You inject state data directly into an agent's instruction using key templating (e.g., Here is your list: {my_list?}).
To inspect state: You can monitor the session state live in the ADK Dev UI using the State tab.

9. Workflow Agents
So far, you've seen how a parent agent transfers to a sub-agent and then waits for the user. Workflow agents are different: they execute their sub-agents one after another in an automated flow, without waiting for user input.

This is perfect for automated, multi-step tasks like a "Plan and Execute" or "Draft and Revise" pipeline. ADK provides three built-in workflow agents to manage this:

SequentialAgent
LoopAgent
ParallelAgent
The rest of this lab will focus on building a multi-agent system using these three workflow agents.

You will build an agent that develops a pitch document for a new movie about a historical character. Your agents will handle research, iterative writing, and report generation.

In the end, your system will look like this:

Diagram of a film_concept_team multi-agent system

You will build this system one step at a time, starting with the simplest workflow.

10. Build a multi-agent system with a SequentialAgent
A SequentialAgent is a workflow agent that executes its sub-agents in a simple, linear sequence. Each agent in its sub_agents list is run one after the other, in order. This is perfect for pipelines where tasks must be performed in a specific order, like the movie-pitching agent you'll build now.

This first version will be structured like this:

Film_concept_team multi-agent system step 1

A root_agent (greeter) will welcome the user and get the movie subject.
It will then transfer to a SequentialAgent named film_concept_team, which will:
Run a researcher agent to get facts from Wikipedia.
Run a screenwriter agent to use those facts to write a plot.
Run a file_writer agent to save the final plot to a file.
Let's run it.

In the Cloud Shell Editor, open adk_multiagent_systems/workflow_agents/agent.py.
Read through this agent definition file. Because sub-agents must be defined before they can be assigned to a parent, to read the file in the order of the conversational flow, you can read the agents from the bottom of the file to the top.
Notice the append_to_state tool. This helper function lets agents append data to a list in the session state, which is how the researcher and screenwriter will pass their work.
Try out the agent. In the terminal, launch the web interface with live-reloading enabled:

cd ~/devrel-demos/ai-ml/build-multiagent-systems-with-adk/adk_multiagent_systems
adk web --reload_agents
Note: If port 8000 is in use, you can run on a different port, for example: adk web --reload_agents --port 8001.

In the Cloud Shell terminal, click the To view the web interface in a new tab, click the Web Preview button and select Change Port.
Web Preview menu
Input port number 8000 and click Change and Preview. A new browser tab will open with the ADK Dev UI.
Change port pop-up box with 8000 entered in text box
From the Select an agent dropdown, select workflow_agents.
Start the conversation with: hello. The greeter agent will respond.
When prompted, enter a historical figure. You can use one of these or your own:
Zhang Zhongjing
Ada Lovelace
Marcus Aurelius
The SequentialAgent will now take over. You will not see any intermediate messages. The researcher, screenwriter, and file_writer will run one after another. The agent will only respond when the entire sequence is complete.
If it fails, you can click + New Session in the upper right and try again.
Once the agent confirms the file is written, find and open the new .txt file in the movie_pitches directory in your Cloud Shell Editor to see the output.
In the ADK Dev UI, click on the last agent icon in the chat history to open the event view.
The event view shows a visual graph of the agent tree. You can see how the greeter called the film_concept_team, which then called each of its sub-agents in order.adk web graph
You can click the Request and Response tabs for any agent in the graph to inspect the exact data that was passed, including the session state.
Note: The quality of this agent's output is limited by its simple prompts. In a real-world system, you would provide much more rigorous instructions and examples to each agent to improve reliability.

Section Recap
In this section, you learned how to use a workflow agent:

A SequentialAgent executes its sub-agents one by one, in order, without waiting for user input between steps.
This is a "workflow" because the user talks to the root_agent, which then hands off the work to the SequentialAgent to complete.
Sub-agents in the sequence use the session state (e.g., { PLOT_OUTLINE? }) to access the work of previous agents.
You can use the event graph in the Dev UI to visualize and debug the entire agent-to-agent workflow.

11. Add a LoopAgent for iterative work
The LoopAgent is a workflow agent that runs its sub-agents in a sequence and then repeats, starting from the beginning. This "loop" continues until a condition is met, like reaching a max_iterations count or a sub-agent calling the built-in exit_loop tool.

It's useful for tasks that require iterative refinement. You will add this LoopAgent to create a "writer's room" for your movie pitch agent. This allows a researcher, screenwriter, and a new critic agent to work in a loop, improving the plot with each pass until the critic decides it's ready. This also helps the agent handle vaguer user inputs (like "an ancient doctor") by letting it research and refine an idea.

Film_concept_team multi-agent system step 2

To make these changes:

In adk_multiagent_systems/workflow_agents/agent.py, add the import for exit_loop (near the other google.adk imports):

from google.adk.tools import exit_loop
Add the new critic agent. This agent will review the plot. If it's good, it calls exit_loop. If not, it adds feedback to the state for the next loop.
Paste the following agent definition under the # Agents section:

critic = Agent(
    name="critic",
    model=model_name,
    description="Reviews the outline so that it can be improved.",
    instruction="""
    INSTRUCTIONS:
    Consider these questions about the PLOT_OUTLINE:
    - Does it meet a satisfying three-act cinematic structure?
    - Do the characters' struggles seem engaging?
    - Does it feel grounded in a real time period in history?
    - Does it sufficiently incorporate historical details from the RESEARCH?

    If the PLOT_OUTLINE does a good job with these questions, exit the writing loop with your 'exit_loop' tool.
    If significant improvements can be made, use the 'append_to_state' tool to add your feedback to the field 'CRITICAL_FEEDBACK'.
    Explain your decision and briefly summarize the feedback you have provided.

    PLOT_OUTLINE:
    { PLOT_OUTLINE? }

    RESEARCH:
    { research? }
    """,
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
    tools=[append_to_state, exit_loop]
)
Create the writers_room LoopAgent. This will contain the three agents that will work in the loop.
Paste the following code above the film_concept_team agent definition:

writers_room = LoopAgent(
    name="writers_room",
    description="Iterates through research and writing to improve a movie plot outline.",
    sub_agents=[
        researcher,
        screenwriter,
        critic
    ],
    max_iterations=5,
)
Note the max_iterations=5 parameter. This is a crucial safety rail to prevent infinite loops, even when you have an exit condition.

Update the film_concept_team SequentialAgent to use the new writers_room loop. Replace the researcher and screenwriter with the single writers_room agent.Replace your existing film_concept_team definition with this:

film_concept_team = SequentialAgent(
    name="film_concept_team",
    description="Write a film plot outline and save it as a text file.",
    sub_agents=[
        writers_room,
        file_writer
    ],
)
Return to the ADK Dev UI tab and click + New Session in the upper right.
Begin a new conversation with: hello
When prompted, give the agent a broader topic this time. Some ideas:
an industrial designer who made products for the masses
a cartographer (a map maker)
that guy who made crops yield more food
The agent will now work through the loop. In the ADK Dev UI, you will see the logs as the agents run multiple times (e.g., "[researcher]", "[screenwriter]", "[critic]", "[researcher]", "[screenwriter]", "[critic]...").
When the loop completes, the agent will write the file. Review the generated file in the adk_multiagent_systems/movie_pitches directory.
Inspect the event graph in the Dev UI to see the loop structure.
Section Recap
In this section, you learned how to use the LoopAgent:

A LoopAgent is a workflow agent that repeats its sequence of sub-agents, creating an "inner loop" for iterative tasks.
Agents inside the loop use the session state to pass work (e.g., PLOT_OUTLINE) and feedback (e.g., CRITICAL_FEEDBACK) to each other on subsequent passes.
The loop can be stopped by hitting a max_iterations limit or by an agent calling the exit_loop tool.

12. Use a ParallelAgent for "fan out and gather"
The ParallelAgent is a workflow agent that executes all its sub-agents at the same time (concurrently). This is valuable for tasks that can be divided into independent sub-tasks, like running two different research jobs.

You will use a ParallelAgent to create a "preproduction team" that works in parallel. One agent will research box office potential while another agent simultaneously brainstorms casting ideas. This is often called a "fan out and gather" pattern: the ParallelAgent "fans out" the work, and a later agent (our file_writer) "gathers" the results.

Film_concept_team multi-agent system step 3

Your final agent flow will be:

The greeter (root) starts the chat.
It transfers to the film_concept_team (SequentialAgent), which runs:
The writers_room (LoopAgent) to create the plot.
The new preproduction_team (ParallelAgent) to research box office and casting at the same time.
The file_writer to gather all the results and save the file.
To make these changes:

In adk_multiagent_systems/workflow_agents/agent.py, paste the new ParallelAgent and its sub-agents under the # Agents header.

box_office_researcher = Agent(
    name="box_office_researcher",
    model=model_name,
    description="Considers the box office potential of this film",
    instruction="""
    PLOT_OUTLINE:
    { PLOT_OUTLINE? }

    INSTRUCTIONS:
    Write a report on the box office potential of a movie like that described in PLOT_OUTLINE based on the reported box office performance of other recent films.
    """,
    output_key="box_office_report"
)

casting_agent = Agent(
    name="casting_agent",
    model=model_name,
    description="Generates casting ideas for this film",
    instruction="""
    PLOT_OUTLINE:
    { PLOT_OUTLINE? }

    INSTRUCTIONS:
    Generate ideas for casting for the characters described in PLOT_OUTLINE
    by suggesting actors who have received positive feedback from critics and/or
    fans when they have played similar roles.
    """,
    output_key="casting_report"
)

preproduction_team = ParallelAgent(
    name="preproduction_team",
    sub_agents=[
        box_office_researcher,
        casting_agent
    ]
)
Update the film_concept_team SequentialAgent's sub_agents list to include the new preproduction_team (between writers_room and file_writer).Replace your existing film_concept_team definition with this:

film_concept_team = SequentialAgent(
    name="film_concept_team",
    description="Write a film plot outline and save it as a text file.",
    sub_agents=[
        writers_room,
        preproduction_team,
        file_writer
    ],
)
Update the file_writer agent's instruction so it "gathers" the new reports from the state and adds them to the file.
Replace the instruction string for the file_writer with this:

    instruction="""
    INSTRUCTIONS:
    - Create a marketable, contemporary movie title suggestion for the movie described in the PLOT_OUTLINE.
    If a title has been suggested in PLOT_OUTLINE, you can use it, or replace it with a better one.
    - Use your 'write_file' tool to create a new txt file with the following arguments:
    - for a filename, use the movie title
    - Write to the 'movie_pitches' directory.
    - For the 'content' to write, include:
    - The PLOT_OUTLINE
    - The BOX_OFFICE_REPORT
    - The CASTING_REPORT

    PLOT_OUTLINE:
    { PLOT_OUTLINE? }

    BOX_OFFICE_REPORT:
    { box_office_report? }

    CASTING_REPORT:
    { casting_report? }
    """,
Return to the ADK Dev UI tab and click + New Session.
Enter hello to start the conversation.
When prompted, enter a new character idea. Some ideas:
that actress who invented the technology for wifi
an exciting chef
key players in the worlds fair exhibitions
When the agent completes its work, inspect the final file in the adk_multiagent_systems/movie_pitches directory. It should now contain the plot, the box office report, and the casting report all in one document.
Section Recap
In this section, you learned how to use the ParallelAgent:

A ParallelAgent "fans out" work, running all its sub-agents at the same time, rather than in a sequence.
This is highly efficient for tasks that don't depend on each other (like researching two different topics).
The results of parallel agents are "gathered" by a later agent. This is done by having the parallel agents save their work to the session state (using output_key), and having a final agent (like file_writer) read those keys.

13. Custom workflow agents
When the pre-defined workflow agents of SequentialAgent, LoopAgent, and ParallelAgent are insufficient for your needs, CustomAgent provides the flexibility to implement new workflow logic.

You can define patterns for flow control, conditional execution, or state management between sub-agents. This is useful for complex workflows, stateful orchestrations, or integrating custom business logic into the framework's orchestration layer.

Creation of a CustomAgent is out of the scope of this lab, but it is good to know that it exists if you need it!

14. Congratulations!
You have successfully built a sophisticated multi-agent system using the Google Agent Development Kit (ADK). You've progressed from a simple parent-child agent relationship to orchestrating complex, automated workflows that can research, write, and refine a creative project.

Recap
In this lab, you did the following:

Organized agents in a hierarchical tree with parent and sub-agent relationships.
Controlled agent-to-agent transfers, both automatically (using description) and explicitly (using instruction).
Used a tool to write data to the tool_context.state dictionary.
Used key templating (e.g., { PLOT_OUTLINE? }) to read from the session state and guide an agent's prompt.
Implemented a SequentialAgent to create a simple, step-by-step workflow (research -> write -> save).
Used a LoopAgent with a critic agent and the exit_loop tool to create an iterative refinement cycle.
Used a ParallelAgent to "fan out" independent tasks (like casting and box office research) to run concurrently.
Continued experimentation
There are many ways to build on what you've learned. Here are some ideas:

Add more agents: Try adding a new agent to your preproduction_team ParallelAgent. For example, you could create a marketing_agent that writes a tagline for the movie based on the PLOT_OUTLINE.
Add more tools: Give your researcher agent more tools. You could create a tool that uses a Google Search API to find information that isn't on Wikipedia.
Explore CustomAgent: The lab mentioned the CustomAgent for workflows that don't fit the standard templates. Try building one that, for example, conditionally runs an agent only if a specific key exists in the session state.