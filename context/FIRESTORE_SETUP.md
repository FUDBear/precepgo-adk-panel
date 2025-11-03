# Firestore Access Solutions

## Problem

You're authenticated as `bytebauble@gmail.com` but trying to grant permissions to `308lovechild@gmail.com`. The authenticated account doesn't have permission to modify IAM policies on the Firebase project.

## Solutions

### Option 1: Switch to the Project Owner Account (Easiest)

If `308lovechild@gmail.com` is the account that created the Firebase project:

```bash
# Switch to the correct account
gcloud auth login 308lovechild@gmail.com

# Then grant permissions
gcloud projects add-iam-policy-binding auth-demo-90be0 \
  --member="user:308lovechild@gmail.com" \
  --role="roles/datastore.user"
```

### Option 2: Use Firebase Console (GUI Method)

1. Go to: https://console.firebase.google.com/project/auth-demo-90be0/settings/iam
2. Click "Add member"
3. Add `308lovechild@gmail.com` with role: **Cloud Datastore User**
4. Or use **Editor** role (includes Datastore access)

### Option 3: Use Service Account (Best for Production)

Create a service account that your agent can use:

```bash
# Create service account
gcloud iam service-accounts create precepgo-agent \
  --project=auth-demo-90be0 \
  --display-name="PrecepGo Agent Service Account"

# Grant Firestore access
gcloud projects add-iam-policy-binding auth-demo-90be0 \
  --member="serviceAccount:precepgo-agent@auth-demo-90be0.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# Create and download key
gcloud iam service-accounts keys create service-account-key.json \
  --iam-account=precepgo-agent@auth-demo-90be0.iam.gserviceaccount.com

# Set environment variable
export GOOGLE_APPLICATION_CREDENTIALS="./service-account-key.json"
```

Then update your code to use the service account key file.

### Option 4: Ask Project Owner

If you're not the project owner, ask the owner to grant you permissions via Firebase Console or:

```bash
# Owner runs this:
gcloud projects add-iam-policy-binding auth-demo-90be0 \
  --member="user:308lovechild@gmail.com" \
  --role="roles/datastore.user"
```

## Verify Setup

After granting permissions, test:

```bash
python3 test_firestore_connection.py
```

## For Cloud Run Deployment

When deploying to Cloud Run, use Option 3 (Service Account) and grant the Cloud Run service account:

```bash
# Get Cloud Run service account (usually auto-created)
CLOUD_RUN_SA="YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com"

# Grant Firestore access
gcloud projects add-iam-policy-binding auth-demo-90be0 \
  --member="serviceAccount:${CLOUD_RUN_SA}" \
  --role="roles/datastore.user"
```
