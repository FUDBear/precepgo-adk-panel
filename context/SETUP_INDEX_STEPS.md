# Simple Steps to Create Vector Search Index

## Quick Summary

The ingestion might take a while (10-30 minutes). Here's the complete process:

## Step 1: Ingest Content (Generate Embeddings)

This creates embeddings from your Barash text files and uploads them to Cloud Storage.

```bash
# Run this - it will take 10-30 minutes depending on your content size
source venv/bin/activate
python3 ingest_barash_content.py
```

**What it does:**
- Chunks all 9 Barash section files
- Generates embeddings using Google's text-embedding-004
- Uploads to Cloud Storage (GCS)
- Creates a document cache

**Expected output:**
- Shows progress for each section
- Creates ~100-4000 chunks (depending on content)
- Uploads embeddings to GCS bucket
- Gives you a GCS URI like: `gs://precepgo-mentor-ai-vector-search/embeddings_*.json`

## Step 2: Create Index (Choose One Method)

### Method A: Python Script (Automated)

```bash
python3 create_vector_index.py
```

This will:
- Create the index (20-30 min)
- Create the endpoint (5-10 min)  
- Deploy index to endpoint (10-15 min)

### Method B: Cloud Console (Manual - Recommended for First Time)

1. **Create Index:**
   - Go to: https://console.cloud.google.com/vertex-ai/matching-engine/indexes?project=precepgo-mentor-ai
   - Click "CREATE INDEX"
   - Settings:
     - Name: `barash-clinical-anesthesia-index`
     - Algorithm: `Tree-AH`
     - Distance measure: `Dot Product`
     - Dimensions: `768`
     - Approximate neighbors: `10`
   - Click CREATE
   - Wait 20-30 minutes

2. **Add Embeddings to Index:**
   - Click on your index
   - Click "UPDATE INDEX" or "IMPORT DATA"
   - Select the embeddings file from GCS (the one created in Step 1)
   - Wait 10-20 minutes

3. **Create Endpoint:**
   - Go to: https://console.cloud.google.com/vertex-ai/matching-engine/index-endpoints?project=precepgo-mentor-ai
   - Click "CREATE ENDPOINT"
   - Name: `barash-clinical-anesthesia-endpoint`
   - Enable "Public endpoint"
   - Click CREATE
   - Wait 5-10 minutes

4. **Deploy Index:**
   - Click on your endpoint
   - Click "DEPLOY INDEX"
   - Select your index
   - Deployed index ID: `barash_deployed`
   - Machine type: `e2-standard-2`
   - Click DEPLOY
   - Wait 10-15 minutes

## Step 3: Test It

Once everything is set up:

```bash
# Test Vector Search directly
python3 vector_search_tool.py

# Test the integration
python3 test_vector_search_integration.py

# Start your server
python3 main.py
```

## Troubleshooting

### Ingestion is slow/hanging
- This is normal! Generating embeddings takes time
- Check progress - it should show "Processing document X/Y"
- If stuck, check your GEMINI_API_KEY has quota

### "Payload size exceeds limit"
- Already fixed! The code now truncates large chunks automatically

### Index creation fails
- Check you have proper GCP permissions
- Verify Vertex AI API is enabled: `gcloud services enable aiplatform.googleapis.com`

### Endpoint not working
- Make sure index is deployed to endpoint
- Check deployment status in Cloud Console
- Verify `deployed_index_id` is `barash_deployed`

## Status Check Commands

```bash
# Check if embeddings exist
python3 -c "from vertex_vector_db_service import VertexVectorSearchService; db = VertexVectorSearchService(); cache = db._load_document_cache(); print(f'Found {len(cache)} documents in cache')"

# Check if index exists
gcloud ai indexes list --region=us-central1 --filter="displayName:barash-clinical-anesthesia-index"

# Check if endpoint exists  
gcloud ai index-endpoints list --region=us-central1 --filter="displayName:barash-clinical-anesthesia-endpoint"
```

## Next Steps After Setup

Once the index is deployed and working:
1. ✅ Vector Search will automatically be used by `main.py`
2. ✅ No code changes needed - it's already integrated!
3. ✅ Test with: `python3 test_vector_search_integration.py`

