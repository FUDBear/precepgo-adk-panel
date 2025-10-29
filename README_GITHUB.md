# 🏥 PrecepGo ADK Panel - Medical Question Generator

> Automated research agent for CRNA education powered by Google Gemini API and Barash Clinical Anesthesia

## 🎯 Google ADK Hackathon Project

This project uses **Google's Gemini 2.5 Pro API** to automatically analyze medical textbook chapters and generate high-quality multiple choice questions for CRNA (Certified Registered Nurse Anesthetist) students.

## ✨ Features

- 🤖 **Scheduled Research Agent** - Automatically analyzes Barash chapters every 5 minutes
- 📚 **Deep Content Analysis** - Uses Gemini 2.5 Pro to perform deep research on medical content
- 📝 **20 MCQ Questions** - Generates questions following Bloom's Taxonomy (30% recall, 50% application, 20% higher-order)
- 🎯 **Grounded in Facts** - Only uses actual textbook content (no hallucinations)
- 🖥️ **Live Dashboard** - Web interface to monitor research and view generated questions
- 🔄 **Auto-Updates** - Questions refresh automatically on the dashboard

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Google Cloud account
- Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd precepgo-adk-panel

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up authentication
./setup_gcloud_auth.sh

# Set your Gemini API key
export GEMINI_API_KEY="your-api-key-here"
```

### Run Locally

```bash
python main.py
```

Visit: **http://localhost:8080/dashboard**

### Deploy to Google Cloud Run

```bash
gcloud run deploy precepgo-adk-panel \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest
```

## 📖 How It Works

1. **Scheduled Task** - Every 5 minutes, the agent selects a chapter from Barash Section 2
2. **Content Retrieval** - Fetches chapter content from MCP server or local file
3. **AI Analysis** - Gemini 2.5 Pro analyzes the content and generates 20 questions
4. **Quality Assurance** - Questions follow educational best practices and Bloom's Taxonomy
5. **Auto-Save** - Saves to `Questions.md` with metadata and timestamps
6. **Dashboard Display** - Shows questions in real-time on the web dashboard

## 🎓 Question Quality

Each question set includes:
- **6 Foundational questions** - Testing recall and understanding
- **10 Application questions** - Testing clinical reasoning and analysis
- **4 Higher-Order questions** - Testing evaluation and synthesis

All questions are:
- ✅ Grounded in actual Barash textbook content
- ✅ Include plausible distractors
- ✅ Provide detailed explanations with citations
- ✅ Cover breadth of chapter material

## 📊 Source Material

**Barash, Cullen, and Stoelting's Clinical Anesthesia, 9th Edition**
- Section 2: Basic Science and Fundamentals
- 6 Chapters
- 130,791 total words

### Chapters Covered:
1. Genomic Basis of Perioperative Precision Medicine
2. Experimental Design and Statistics
3. Inflammation, Wound Healing, and Infection
4. The Allergic Response
5. Mechanisms of Anesthesia and Consciousness
6. Basic Principles of Clinical Pharmacology

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python)
- **AI**: Google Gemini 2.5 Pro API
- **Deployment**: Google Cloud Run
- **Data**: MCP (Model Context Protocol) server + local files
- **Images**: Vertex AI Imagen 3 (optional)

## 📁 Project Structure

```
precepgo-adk-panel/
├── main.py                  # Main FastAPI application
├── data/
│   ├── Section 2 - Basic Science and Fundamental's.txt
│   ├── concepts.json
│   └── patient_templates.json
├── Questions.md             # Generated questions (auto-updated)
├── requirements.txt         # Python dependencies
├── Dockerfile              # For Cloud Run deployment
├── setup_gcloud_auth.sh    # Google Cloud setup script
└── docs/
    ├── SCHEDULED_RESEARCH.md
    ├── QUICK_START_RESEARCH.md
    └── GEMINI_SETUP.md
```

## 🔐 Environment Variables

```bash
# Required for question generation
export GEMINI_API_KEY="your-gemini-api-key"

# Optional - for MCP server integration
export MCP_URL="https://your-mcp-server.run.app"

# Optional - for Google Cloud
export GOOGLE_CLOUD_PROJECT="precepgo-mentor-ai"
```

## 📡 API Endpoints

- `GET /` - Health check
- `GET /dashboard` - Web dashboard
- `GET /research/status` - Check research agent status
- `POST /research/trigger` - Manually trigger question generation
- `GET /research/questions` - Get generated Questions.md content
- `POST /mentor/create-question` - Generate single concept question

## 🎨 Features

### Scheduled Research
- Runs automatically every 5 minutes
- Cycles through all Barash Section 2 chapters
- Generates fresh questions each cycle
- Logs all activity for monitoring

### Live Dashboard
- Real-time status updates
- Manual trigger capability
- View generated questions inline
- Auto-refreshing every 30 seconds

### Question Generation
- Deep AI analysis of medical content
- Follows educational best practices
- Includes detailed rationales
- Cites source material

## 📝 Example Output

See `Questions.md` for the latest generated questions!

## 🤝 Contributing

This is a Google ADK Hackathon project. Contributions welcome!

## 📄 License

Educational use - Barash content copyright © Wolters Kluwer

## 🙏 Acknowledgments

- Barash, Cullen, and Stoelting's Clinical Anesthesia, 9th Edition
- Google Gemini API
- Google ADK (Agent Development Kit)
- FastAPI framework

---

**Built for the Google ADK Hackathon** 🚀  
**Powered by Gemini 2.5 Pro** 🤖  
**Educational Excellence** 🎓

