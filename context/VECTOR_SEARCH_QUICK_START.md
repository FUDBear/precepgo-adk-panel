# Vector Search Quick Start

Fast setup guide for Vertex AI Vector Search with your Barash content.

## TL;DR - 3 Commands to Get Started

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Ingest content (generates embeddings)
python3 ingest_barash_content.py

# 3. Test it (after setting up index + endpoint in Cloud Console)
python3 vector_search_tool.py
```

## What You Get

- ✅ Semantic search across all 9 Barash sections (~700 pages)
- ✅ Google's text-embedding-004 model (768 dimensions)
- ✅ 3800+ intelligently chunked text segments
- ✅ Context-aware search results for your agent

## 5-Minute Setup (After Ingestion)

### 1. Create Index (Cloud Console)

https://console.cloud.google.com/vertex-ai/matching-engine/indexes

- Name: `barash-clinical-anesthesia-index`
- Region: `us-central1`
- Dimensions: `768`
- Distance: `Dot Product`
- Algorithm: `Tree-AH`

⏱️ Takes 20-30 minutes

### 2. Create Endpoint

https://console.cloud.google.com/vertex-ai/matching-engine/index-endpoints

- Name: `barash-clinical-anesthesia-endpoint`
- Region: `us-central1`
- Public endpoint: ✅

⏱️ Takes 5-10 minutes

### 3. Deploy Index to Endpoint

- Select your endpoint
- Click DEPLOY INDEX
- Choose your index
- Deployed ID: `barash_deployed`
- Machine: `e2-standard-2`

⏱️ Takes 10-15 minutes

### 4. Query!

```python
from vector_search_tool import VectorSearchTool

tool = VectorSearchTool()
results = tool.search_for_context(
    "What are the cardiovascular effects of propofol?",
    num_results=5
)
print(results)
```

## Key Files

| File | Purpose |
|------|---------|
| `vertex_vector_db_service.py` | Core service for Vertex AI Vector Search |
| `ingest_barash_content.py` | Loads and chunks Barash files, generates embeddings |
| `vector_search_tool.py` | Simple query interface for agents |
| `integrate_vector_search.py` | Integration guide for main.py |
| `VECTOR_SEARCH_SETUP.md` | Complete documentation |

## Integration with Agent (main.py)

```python
# Add to imports
from vector_search_tool import search_barash_content

# Add tool function
async def search_barash_vector_db(query: str, num_results: int = 5) -> str:
    return search_barash_content(query, num_results, format_for_llm=True)

# Add to agent tools list
tools=[
    get_medical_content,
    select_patient_for_concept,
    generate_medical_question,
    search_barash_vector_db  # ← Add this
]
```

## Example Queries

```python
# Pharmacology
"What are the pharmacokinetics of remifentanil?"

# Procedures
"How should anesthesia be managed for laparoscopic surgery?"

# Monitoring
"What are the perioperative monitoring requirements for cardiac surgery?"

# Complications
"How do you manage malignant hyperthermia?"

# Physiology
"Explain the cardiovascular response to pneumoperitoneum"
```

## Cost Summary

**Development:** ~$50-55/month
- e2-standard-2 × 1 replica
- ~1000 queries/month

**Production:** ~$205/month
- e2-standard-4 × 2 replicas
- ~10,000 queries/month

## Common Issues

### "No module named 'vertex_vector_db_service'"
```bash
# Make sure you're in the right directory
cd /Users/joshuaburleson/Documents/App\ Development/precepgo-adk-panel
python3 vector_search_tool.py
```

### "GEMINI_API_KEY environment variable not set"
```bash
# Check your .env file
cat .env | grep GEMINI_API_KEY
```

### "Index not found"
```bash
# List all indexes
gcloud ai indexes list --region=us-central1
```

### "Endpoint not responding"
- Verify index is deployed to endpoint in Cloud Console
- Check `deployed_index_id` matches `"barash_deployed"`

## Next Steps

1. ✅ Run `ingest_barash_content.py`
2. ✅ Create index in Cloud Console
3. ✅ Create endpoint in Cloud Console
4. ✅ Deploy index to endpoint
5. ✅ Test with `vector_search_tool.py`
6. ✅ Integrate with `main.py`

## Full Documentation

See `VECTOR_SEARCH_SETUP.md` for complete details.

---

**Need Help?**
- Check logs: `python3 vector_search_tool.py`
- Verify setup: `python3 -c "from vertex_vector_db_service import VertexVectorSearchService; db = VertexVectorSearchService(); print(db.get_stats())"`
