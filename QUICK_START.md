# 🚀 Quick Start Guide - Barash-Only Question Generator

## ⚡ Start in 30 Seconds

```bash
cd "/Users/joshuaburleson/Documents/App Development/precepgo-adk-panel"
source venv/bin/activate
MCP_URL=https://precepgo-data-mcp-g4y4qz5rfa-uw.a.run.app python3 main.py
```

Then open: **http://localhost:8080/dashboard**

---

## 📚 What You're Using

**Content**: Barash Section 2 ONLY (129,283 words)
- Ch.6: Genomic Medicine
- Ch.7: Statistics & Research
- Ch.8: Wound Healing
- Ch.9: Allergic Responses
- Ch.10: Anesthesia Mechanisms
- Ch.11: Clinical Pharmacology

---

## ✨ What's Special

✅ **100% Barash Content** - No mock data
✅ **Proper Citations** - Every rationale cites Barash
✅ **Smart Search** - Finds relevant content automatically
✅ **60+ Scenarios** - Matched to Barash chapters
✅ **28 Concepts** - All verified working

---

## 🎯 Try These Concepts

**Easy Wins** (High success rate):
- Pharmacogenomics in Anesthesia
- Cytochrome P450 Interactions  
- Minimum Alveolar Concentration
- Anaphylaxis Recognition and Treatment
- Pharmacokinetics and Pharmacodynamics

**Advanced** (More specific):
- Target-Controlled Infusions
- Context-Sensitive Half-Time
- Opioid-Hypnotic Synergy
- Meyer-Overton Rule
- Ion Channels and Anesthesia

---

## 📖 Example Output

**Input**: "cytochrome P450 interactions", senior level

**Output**:
```
Question: 61yo male for warfarin management perioperatively...
Scenario: Barash Ch.11 specific scenario
Rationale: Includes direct Barash facts + citation
Source: Barash, Cullen, and Stoelting's Clinical Anesthesia
```

---

## ⚠️ Important Notes

### ✅ DO:
- Use concepts from the dashboard dropdown
- All 28 concepts are verified Barash Section 2 content
- Questions will have proper citations

### ❌ DON'T:
- Use concepts not in the dropdown
- Expect other textbook content (we only have Barash Section 2)
- Worry about mock content (it's disabled!)

---

## 🔧 Optional: Enable Images

```bash
./setup_gcloud_auth.sh
```

Enables AI-generated clinical images with Imagen 3.

---

## 📞 Need Help?

**Server logs**:
```bash
tail -f server.log
```

**Test MCP server**:
```bash
curl https://precepgo-data-mcp-g4y4qz5rfa-uw.a.run.app/mcp/stats
```

**Health check**:
```bash
curl http://localhost:8080/health
```

---

## 🎓 For Students

Every question you generate:
- ✅ Comes from Barash Clinical Anesthesia
- ✅ Includes proper academic citations
- ✅ Uses evidence-based content
- ✅ Can be traced to specific chapters
- ✅ Represents gold-standard medical education

---

**Start generating Barash-based questions now!**
**http://localhost:8080/dashboard**

