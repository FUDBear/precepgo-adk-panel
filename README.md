# 🏥 PrecepGo ADK Panel - Barash Medical Question Generator

**Powered by Barash, Cullen, and Stoelting's Clinical Anesthesia, 9th Edition**

A FastAPI service that generates evidence-based medical questions exclusively from **Barash Section 2: Basic Science and Fundamentals** (129,283 words across 6 chapters).

## 📚 Content Source

**Barash Section 2 Chapters (EXCLUSIVE):**
- Chapter 6: Genomic Basis of Perioperative Precision Medicine
- Chapter 7: Experimental Design and Statistics
- Chapter 8: Inflammation, Wound Healing, and Infection
- Chapter 9: The Allergic Response
- Chapter 10: Mechanisms of Anesthesia and Consciousness
- Chapter 11: Basic Principles of Clinical Pharmacology

**Total Knowledge Base**: 130,791 words (99% Barash content)

## 🚀 Quick Start

### 1. Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Start the Server
```bash
MCP_URL=https://precepgo-data-mcp-g4y4qz5rfa-uw.a.run.app python3 main.py
```

### 3. Open Dashboard
**Browser**: http://localhost:8080/dashboard

**API Health Check**: http://localhost:8080/health

## ✨ Features

### 🎯 Barash-Only Content
- **100% Barash Section 2** - No mock content fallback
- **Smart Search** - Automatically finds relevant Barash content
- **Verified Concepts** - All 28 dashboard concepts tested and working

### 📖 Enhanced Questions
- **Evidence-based** - Direct citations to Barash chapters
- **Clinical Scenarios** - 60+ Barash-specific scenarios
- **Proper Attribution** - Every rationale cites source material
- **Key Facts** - Extracts important points from textbook

### 🎓 Educational Quality
- **Authoritative Source** - Gold-standard Barash textbook
- **Comprehensive** - 129,283 words of expert content
- **Traceable** - Students can reference exact chapters

## 📝 Example Usage

### API Request:
```bash
curl -X POST http://localhost:8080/mentor/create-question \
  -H "Content-Type: application/json" \
  -d '{
    "concept": "pharmacogenomics in anesthesia",
    "level": "senior"
  }'
```

### Response:
```json
{
  "ok": true,
  "question": {
    "concept": "pharmacogenomics in anesthesia",
    "scenario": "coronary artery bypass grafting with genetic risk factors",
    "patient": {...},
    "question": "[Clinical vignette from Barash]",
    "answer": "[Evidence-based answer]",
    "rationale": "[With Barash citations]"
  }
}
```

## 🔐 Optional: Enable AI Images

To enable Imagen 3 clinical image generation:

```bash
./setup_gcloud_auth.sh
```

This configures Google Cloud authentication for Vertex AI.

## 📚 Available Concepts

All concepts from **Barash Section 2** organized by chapter:

- **Ch.6 Genomics**: Pharmacogenomics, Genetic Variability, Biomarkers
- **Ch.7 Statistics**: RCTs, Meta-Analysis, Statistical Methods  
- **Ch.8 Wound Healing**: Infection Prevention, Tissue Oxygenation, Antibiotics
- **Ch.9 Allergic**: Anaphylaxis, Drug Allergies, Latex Management
- **Ch.10 Mechanisms**: GABAa, MAC, Meyer-Overton, Ion Channels
- **Ch.11 Pharmacology**: PK/PD, CYP450, TCI, Drug Synergy

See dashboard dropdown for complete list!

## 📖 Documentation

- **BARASH_INTEGRATION.md** - Complete integration guide
- **BARASH_ONLY_VERIFICATION.md** - Verification test results
- **IMPROVEMENTS_SUMMARY.md** - Detailed changelog
- **TEST_RESULTS.md** - Comprehensive test examples

## 🏗️ Architecture

```
User Request
    ↓
Dashboard/API
    ↓
ADK Agent (with RAG)
    ↓
MCP Server (Barash Content) → Smart Search → Keyword Extraction
    ↓
Question Generator
    ↓
Enhanced Rationale (with Barash citations)
```

## ⚙️ Configuration

### Environment Variables:
- `MCP_URL` - Required. Points to production MCP server with Barash content

### MCP Server:
- **Production**: https://precepgo-data-mcp-g4y4qz5rfa-uw.a.run.app
- **Books**: 4 total (Barash + 3 others)
- **Primary Source**: Barash Section 2 (129,283 words)

## 🧪 Testing

All concepts verified working:
```bash
# Test specific concept
curl -X POST http://localhost:8080/mentor/create-question \
  -H "Content-Type: application/json" \
  -d '{"concept": "cytochrome P450 interactions", "level": "senior"}'
```

## 🎯 Content Quality

- ✅ **Authoritative**: Barash textbook only
- ✅ **Evidence-based**: Proper citations
- ✅ **Comprehensive**: 129,283 words
- ✅ **Educational**: Traceable to source chapters
- ✅ **Clinical**: Realistic scenarios from textbook

## 📞 Support

**Issues?** Check logs:
```bash
tail -f server.log
```

**MCP Server Status**:
```bash
curl https://precepgo-data-mcp-g4y4qz5rfa-uw.a.run.app/mcp/stats
```

---

**Last Updated**: October 28, 2025  
**Version**: 2.0 - Barash Section 2 Exclusive  
**Content**: 129,283 words from Barash Clinical Anesthesia, 9th Ed.
