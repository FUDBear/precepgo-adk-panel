# Barash Clinical Anesthesia Integration Guide

## 🎉 What's New

Your PrecepGo ADK Panel now includes **129,283 words** of content from Barash, Cullen, and Stoelting's Clinical Anesthesia, Section 2: Basic Science and Fundamentals!

## 📚 Available Barash Content

### Chapter 6: Genomic Basis of Perioperative Precision Medicine
- Perioperative genomics and biomarkers
- Pharmacogenomics and genetic variability in drug response
- Genetic susceptibility to adverse perioperative outcomes
- Precision medicine approaches

### Chapter 7: Experimental Design and Statistics
- Randomized controlled trials
- Statistical methods and analysis
- Meta-analysis and systematic reviews
- Evidence-based medicine principles

### Chapter 8: Inflammation, Wound Healing, and Infection
- Surgical site infection prevention
- Wound oxygenation and perfusion
- Antibiotic prophylaxis timing and selection
- Hand hygiene and infection control

### Chapter 9: The Allergic Response
- Anaphylaxis recognition and treatment
- Drug-induced allergic reactions
- IgE-mediated and non-IgE-mediated mechanisms
- Perioperative management of allergies

### Chapter 10: Mechanisms of Anesthesia and Consciousness
- GABAa receptors and molecular targets
- Minimum alveolar concentration (MAC)
- Meyer-Overton rule and lipid vs. protein theories
- Ion channels and synaptic transmission

### Chapter 11: Basic Principles of Clinical Pharmacology
- Pharmacokinetics and pharmacodynamics
- Drug distribution and elimination
- Cytochrome P450 interactions
- Target-controlled infusions
- Context-sensitive half-times
- Opioid-hypnotic synergy

## 🚀 Quick Start

### 1. Start the Server

```bash
cd "/Users/joshuaburleson/Documents/App Development/precepgo-adk-panel"
source venv/bin/activate
MCP_URL=https://precepgo-data-mcp-g4y4qz5rfa-uw.a.run.app python3 main.py
```

### 2. Access the Dashboard

Open your browser to: **http://localhost:8080/dashboard**

### 3. Generate Questions

1. Select a Barash concept from the dropdown (organized by chapter)
2. Choose student level (junior/senior)
3. Click "Generate Question"
4. Review the question, answer options, and comprehensive rationale

## 🔐 Optional: Enable Image Generation

To enable AI-generated clinical images using Google's Imagen 3:

### Step 1: Run the Setup Script

```bash
./setup_gcloud_auth.sh
```

This will:
- Check if gcloud CLI is installed
- Configure authentication
- Set the correct Google Cloud project

### Step 2: Restart the Server

After authentication, restart the server and image generation will be enabled.

### Manual Setup (Alternative)

If the script doesn't work, you can manually configure authentication:

```bash
# Install gcloud CLI if needed
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth application-default login

# Set project
gcloud config set project precepgo-mentor-ai

# Initialize Vertex AI
gcloud services enable aiplatform.googleapis.com
```

## 📖 How It Works

### RAG (Retrieval-Augmented Generation) Pipeline

1. **Retrieve**: When you request a question, the system searches the MCP server for relevant Barash content
2. **Extract**: The system extracts key facts, guidelines, and safety considerations
3. **Generate**: Creates a clinically relevant vignette with:
   - Appropriate patient demographics
   - Realistic scenario matching the concept
   - Evidence-based answer options
   - Comprehensive rationale citing Barash content

### Enhanced Rationales

Each generated question includes:
- **Direct citations** from Barash textbook chapters
- **Key clinical facts** from the retrieved content
- **Evidence-based guidelines** when available
- **Safety considerations** specific to the scenario
- **Source attribution** showing which Barash chapter was used

## 🧪 Testing the Integration

### Example API Call

```bash
curl -X POST http://localhost:8080/mentor/create-question \
  -H "Content-Type: application/json" \
  -d '{
    "concept": "GABAa receptors and anesthetic action",
    "level": "senior"
  }'
```

### Example Barash Concepts to Try

1. **Pharmacogenomics**: `"pharmacogenomics in anesthesia"`
2. **MAC**: `"minimum alveolar concentration"`
3. **Drug Interactions**: `"cytochrome P450 interactions"`
4. **Anaphylaxis**: `"anaphylaxis recognition and treatment"`
5. **Wound Healing**: `"wound oxygenation and perfusion"`
6. **Statistics**: `"randomized controlled trials"`

## 📊 Knowledge Base Stats

- **Total Books**: 4
- **Total Words**: 130,791
- **Barash Content**: 129,283 words (99% of total!)
- **Chapters Available**: 6 chapters from Section 2

## 🔍 MCP Server Endpoints

Your production MCP server provides:

- `GET /` - Health check
- `GET /mcp/books` - List all books
- `POST /mcp/search` - Search across all books
- `GET /mcp/stats` - Knowledge base statistics

## 🎯 Best Practices

1. **Choose Specific Concepts**: Use the detailed Barash concepts for more focused questions
2. **Match Level to Complexity**: Senior-level concepts work best with senior student level
3. **Review Rationales**: The rationales now include specific Barash citations - great for learning!
4. **Test Different Scenarios**: Each generation creates unique patient scenarios

## 🐛 Troubleshooting

### Server Won't Start
- Ensure virtual environment is activated: `source venv/bin/activate`
- Check MCP_URL is set: `echo $MCP_URL`
- View server logs: `tail -f server.log`

### Questions Don't Include Barash Content
- Verify MCP server is accessible: `curl https://precepgo-data-mcp-g4y4qz5rfa-uw.a.run.app/`
- Check server logs for MCP connection warnings
- Try more specific concepts from the dropdown

### Image Generation Doesn't Work
- This is expected without Google Cloud authentication
- Run `./setup_gcloud_auth.sh` to configure
- Questions will still generate without images

## 📈 Future Enhancements

- [ ] Add more Barash sections (Sections 3-8)
- [ ] Implement difficulty ratings for questions  
- [ ] Add explanation videos for complex concepts
- [ ] Export questions to question banks
- [ ] Track which concepts students struggle with

## 🙏 Acknowledgments

Content from: **Barash, Cullen, and Stoelting's Clinical Anesthesia, 9th Edition**
- Chapter 6: Genomic Basis of Perioperative Precision Medicine
- Chapter 7: Experimental Design and Statistics  
- Chapter 8: Inflammation, Wound Healing, and Infection
- Chapter 9: The Allergic Response
- Chapter 10: Mechanisms of Anesthesia and Consciousness
- Chapter 11: Basic Principles of Clinical Pharmacology

