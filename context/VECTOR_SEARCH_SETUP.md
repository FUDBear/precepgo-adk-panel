# Vertex AI Vector Search Setup Guide

Complete guide for setting up Google Cloud Vertex AI Vector Search for your Barash Clinical Anesthesia content.

## Overview

This system provides semantic search over your CRNA educational content using:
- **Google Cloud Vertex AI Vector Search** (Matching Engine) - Managed vector database
- **Google text-embedding-004** - State-of-the-art embedding model (768 dimensions)
- **Smart text chunking** - Intelligently splits content while preserving context
- **Full content coverage** - Indexes all 9 sections of Barash Clinical Anesthesia

## Architecture

```
┌─────────────────┐
│  Barash .txt    │
│  Files (9)      │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Ingestion      │  ← ingest_barash_content.py
│  Script         │    (Chunks text, generates embeddings)
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Cloud Storage  │  ← Stores embeddings as JSONL
│  (GCS Bucket)   │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Vertex AI      │  ← Builds vector index
│  Vector Search  │
│  Index          │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Index          │  ← Endpoint for queries
│  Endpoint       │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Your Agent     │  ← Queries via vector_search_tool.py
│  (main.py)      │
└─────────────────┘
```

## Prerequisites

1. **Google Cloud Project Setup**
   ```bash
   # Your project is already configured: precepgo-mentor-ai
   gcloud config set project precepgo-mentor-ai
   ```

2. **Enable Required APIs**
   ```bash
   # Enable Vertex AI API
   gcloud services enable aiplatform.googleapis.com

   # Enable Cloud Storage API
   gcloud services enable storage.googleapis.com

   # Enable Compute Engine API (for index deployment)
   gcloud services enable compute.googleapis.com
   ```

3. **Authentication**
   ```bash
   # Already configured via setup_gcloud_auth.sh
   # Verify your credentials
   gcloud auth list
   gcloud auth application-default login
   ```

4. **Install Dependencies**
   ```bash
   # Install new dependencies
   pip install -r requirements.txt
   ```

## Step-by-Step Setup

### Step 1: Prepare Your Environment

```bash
# Verify your Barash content is in place
ls -la "data/Barash, Cullen, and Stoelting's Clinical Anesthesia"

# Should show 9 section .txt files:
# Section 1 - Introduction and Overview.txt
# Section 2 - Basic Science and Fundamental's.txt
# Section 3 - Cardiac Anatonomy and Physiology.txt
# ... and so on
```

### Step 2: Run the Ingestion Script

```bash
# This will:
# - Load all 9 section files
# - Chunk them intelligently (1000 chars, 200 overlap)
# - Generate embeddings using text-embedding-004
# - Upload to Cloud Storage

python3 ingest_barash_content.py
```

**Expected output:**
```
============================================================================
 Barash Clinical Anesthesia Content Ingestion for Vertex AI Vector Search
============================================================================

🔧 Initializing Vertex AI Vector Search service...
✅ Initialized Vertex AI: precepgo-mentor-ai in us-central1
✅ Configured Google embeddings with model: models/text-embedding-004
✅ Using existing GCS bucket: precepgo-mentor-ai-vector-search

📊 Current Vector DB Stats:
   Project: precepgo-mentor-ai
   Location: us-central1
   Bucket: precepgo-mentor-ai-vector-search
   Cached documents: 0

🔧 Initializing content ingester...

📚 Processing 9 section files...

============================================================
Processing: Section 1 - Introduction and Overview
============================================================
✅ Loaded 776737 characters from Section 1 - Introduction and Overview.txt
✂️  Created 425 chunks from Section 1 - Introduction and Overview

[... continues for all 9 sections ...]

============================================================
✅ Total chunks created: 3847
============================================================

🚀 Starting ingestion of 3847 chunks...

📦 Processing in batches of 50...

--- Batch 1: Processing chunks 0 to 50 ---
📝 Generating embeddings for 50 documents...
   Processing document 1/50...
   Processing document 11/50...
   ...
✅ Uploaded embeddings to: gs://precepgo-mentor-ai-vector-search/embeddings_20251029_120000.json
✅ Added 50 documents to collection

[... continues for all batches ...]

============================================================================
✅ INGESTION COMPLETE!
============================================================================

📍 Embeddings uploaded to: gs://precepgo-mentor-ai-vector-search/embeddings_20251029_120000.json
```

**This process will take approximately:**
- Small dataset (<500 chunks): 5-10 minutes
- Medium dataset (500-2000 chunks): 10-20 minutes
- Large dataset (2000-4000 chunks): 20-40 minutes

### Step 3: Create Vector Search Index

You have two options:

#### Option A: Using Python API (Automated)

```python
from vertex_vector_db_service import VertexVectorSearchService

# Initialize service
db = VertexVectorSearchService()

# Create index (this will take 20-30 minutes)
index = db.create_index(wait=True)
print(f"Index created: {index.resource_name}")
```

#### Option B: Using Google Cloud Console (Manual - Recommended for first time)

1. Go to [Vertex AI Vector Search](https://console.cloud.google.com/vertex-ai/matching-engine/indexes)

2. Click **CREATE INDEX**

3. Configure the index:
   - **Name**: `barash-clinical-anesthesia-index`
   - **Region**: `us-central1`
   - **Dimensions**: `768` (for text-embedding-004)
   - **Update method**: Select appropriate option for your use case
   - **Distance measure**: `Dot Product`

4. **Algorithm config**:
   - Algorithm: `Tree-AH`
   - Leaf node embedding count: `500`
   - Leaf nodes to search percent: `7`
   - Approximate neighbors count: `10`

5. **Initial datapoints** (OPTIONAL for now):
   - You can skip this and update later
   - Or provide the GCS URI from Step 2

6. Click **CREATE**

7. **Wait for index creation** (20-30 minutes)

### Step 4: Update Index with Embeddings

If you didn't add initial datapoints in Step 3:

1. In the Cloud Console, find your index
2. Click **UPDATE INDEX**
3. **Add embeddings**:
   - Provide the GCS URI from Step 2 output
   - Format: `gs://precepgo-mentor-ai-vector-search/embeddings_TIMESTAMP.json`
4. Click **UPDATE**
5. Wait for index update to complete (10-20 minutes)

### Step 5: Create Index Endpoint

#### Option A: Using Python API

```python
from vertex_vector_db_service import VertexVectorSearchService

db = VertexVectorSearchService()

# Get existing index
index = db.get_or_create_index()

# Create endpoint
endpoint = db.create_endpoint(wait=True)
print(f"Endpoint created: {endpoint.resource_name}")
```

#### Option B: Using Cloud Console

1. Go to [Index Endpoints](https://console.cloud.google.com/vertex-ai/matching-engine/index-endpoints)

2. Click **CREATE INDEX ENDPOINT**

3. Configure:
   - **Name**: `barash-clinical-anesthesia-endpoint`
   - **Region**: `us-central1` (must match index region)
   - **Network**: Leave default or configure VPC if needed
   - **Public endpoint**: Enable

4. Click **CREATE**

5. Wait for endpoint creation (5-10 minutes)

### Step 6: Deploy Index to Endpoint

#### Option A: Using Python API

```python
from vertex_vector_db_service import VertexVectorSearchService

db = VertexVectorSearchService()

# Get index and endpoint
index = db.get_or_create_index()
endpoint = db.get_or_create_endpoint()

# Deploy
db.deploy_index_to_endpoint(
    deployed_index_id="barash_deployed",
    machine_type="e2-standard-2",
    min_replica_count=1,
    max_replica_count=1,
    wait=True
)
```

#### Option B: Using Cloud Console

1. Go to your endpoint
2. Click **DEPLOY INDEX**
3. Select your index: `barash-clinical-anesthesia-index`
4. Configure deployment:
   - **Deployed index ID**: `barash_deployed`
   - **Machine type**: `e2-standard-2` (or larger for better performance)
   - **Min replicas**: `1`
   - **Max replicas**: `1` (increase for auto-scaling)
5. Click **DEPLOY**
6. Wait for deployment (10-15 minutes)

### Step 7: Test Your Vector Search

```python
from vector_search_tool import VectorSearchTool

# Initialize tool
tool = VectorSearchTool()

# Test query
results = tool.search_for_context(
    query="What are the cardiovascular effects of propofol?",
    num_results=3
)

print(results)
```

**Expected output:**
```
🔍 Querying: 'What are the cardiovascular effects of propofol?'
✅ Loaded document cache with 3847 documents
✅ Found 3 results

# Relevant Content from Barash Clinical Anesthesia

Query: What are the cardiovascular effects of propofol?
Found 3 relevant sections:

======================================================================
[1] Section 4 - Anesthetic Drugs and Adjuvants
Topic: Intravenous Anesthetics | Chunk: 42 | Relevance: 0.856
======================================================================

Propofol causes dose-dependent cardiovascular depression primarily through...
[detailed content from textbook]

...
```

### Step 8: Integrate with Your Agent

Follow the guide in `integrate_vector_search.py`:

```python
# 1. Add import to main.py
from vector_search_tool import search_barash_content

# 2. Add tool function
async def search_barash_vector_db(query: str, num_results: int = 5) -> str:
    """ADK Tool: Search Barash using Vector Search"""
    return search_barash_content(query, num_results, format_for_llm=True)

# 3. Add to agent tools
tools=[
    get_medical_content,
    select_patient_for_concept,
    generate_medical_question,
    search_barash_vector_db  # NEW
],
```

## Cost Estimation

Based on Google Cloud pricing (us-central1):

### One-Time Setup Costs
- **Embedding Generation**:
  - ~4000 chunks × $0.00001/1K tokens ≈ $0.40

- **Index Creation**:
  - One-time build: ~$5-10

### Ongoing Costs (Monthly)

**Scenario 1: Development/Testing (Low volume)**
- Index deployment: e2-standard-2 × 1 replica = ~$50/month
- Storage (GCS): 100MB = ~$0.002/month
- Queries: 1000 queries/month = ~$0.50/month
- **Total: ~$50-55/month**

**Scenario 2: Production (Medium volume)**
- Index deployment: e2-standard-4 × 2 replicas = ~$200/month
- Storage: 100MB = ~$0.002/month
- Queries: 10,000 queries/month = ~$5/month
- **Total: ~$205/month**

**Cost Optimization Tips:**
1. Use smaller machine types for development (e2-standard-2)
2. Scale to 0 replicas when not in use (requires redeployment)
3. Use batch queries when possible
4. Consider reserved capacity for production

## Updating Content

When you update your Barash files:

```bash
# 1. Re-run ingestion (generates new embeddings with timestamp)
python3 ingest_barash_content.py

# 2. Update the index via Console or API
# Option A: Console
#   - Go to your index → UPDATE INDEX
#   - Add the new GCS URI

# Option B: API
from vertex_vector_db_service import VertexVectorSearchService
db = VertexVectorSearchService()
# ... update via API
```

## Troubleshooting

### Issue: "Index not found"
```bash
# List all indexes
gcloud ai indexes list --region=us-central1
```

### Issue: "Permission denied"
```bash
# Verify IAM roles
gcloud projects get-iam-policy precepgo-mentor-ai

# Required roles:
# - Vertex AI User
# - Storage Object Admin (for bucket)
```

### Issue: "Endpoint not responding"
- Check endpoint deployment status in console
- Verify index is deployed to endpoint
- Check deployed_index_id matches in code

### Issue: "Out of memory during embedding generation"
- Reduce batch size in `ingest_barash_content.py`
- Process sections one at a time

## Advanced Configuration

### Custom Chunking Strategy

Edit `ingest_barash_content.py`:

```python
ingester = BarashContentIngester(
    chunk_size=1500,      # Larger chunks
    chunk_overlap=300     # More overlap for context
)
```

### Performance Tuning

Increase endpoint capacity:

```python
db.deploy_index_to_endpoint(
    machine_type="e2-standard-16",  # More powerful
    min_replica_count=2,             # More replicas
    max_replica_count=5              # Auto-scale up to 5
)
```

### Section-Specific Indexes

Create separate indexes per section for isolation:

```python
db_section2 = VertexVectorSearchService(
    index_display_name="barash-section2-index",
    endpoint_display_name="barash-section2-endpoint"
)
```

## Monitoring

### Via Cloud Console

1. Go to [Vertex AI Vector Search](https://console.cloud.google.com/vertex-ai/matching-engine/indexes)
2. View metrics:
   - Query latency
   - Query throughput
   - Index size
   - Deployed replicas

### Via API

```python
from vertex_vector_db_service import VertexVectorSearchService

db = VertexVectorSearchService()
stats = db.get_stats()
print(stats)
```

## Next Steps

1. ✅ Complete all setup steps above
2. ✅ Test queries with `vector_search_tool.py`
3. ✅ Integrate with your agent in `main.py`
4. 🔄 Monitor usage and optimize costs
5. 🔄 Iterate on chunk sizes and search parameters
6. 🔄 Add more content sources as needed

## Resources

- [Vertex AI Vector Search Docs](https://cloud.google.com/vertex-ai/docs/vector-search/overview)
- [Text Embedding API](https://cloud.google.com/vertex-ai/docs/generative-ai/embeddings/get-text-embeddings)
- [Pricing Calculator](https://cloud.google.com/products/calculator)

## Support

If you encounter issues:

1. Check the logs: `python3 vector_search_tool.py`
2. Review Cloud Console for index/endpoint status
3. Verify all APIs are enabled
4. Check IAM permissions

---

**Created:** 2025-10-29
**Version:** 1.0
**Project:** precepgo-adk-panel
