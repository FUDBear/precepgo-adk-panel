# Quick Guide: Firebase Role Selection

## Setup Context:
- **Project Owner**: `308lovechild@gmail.com` (grants permissions)
- **Agent Account**: `bytebauble@gmail.com` (needs permissions)
- **Firebase Project**: `auth-demo-90be0`

## Steps to Grant Access:

1. **Select**: "Assign Firebase role(s)" (the 4th radio button option)
   
2. **Then choose**: "Cloud Datastore User" role from the dropdown

3. **Add member email**: `bytebauble@gmail.com`
   (This is the account your agent/server is using)

4. Click "Done"

This gives the agent account permission to read/write to Firestore without full project ownership.

## After Granting Permissions:

1. Make sure your agent is authenticated as `bytebauble@gmail.com`:
   ```bash
   gcloud auth application-default login
   # Login as bytebauble@gmail.com when prompted
   ```

2. Verify access:
   ```bash
   python3 test_firestore_connection.py
   ```

## Summary:
- **Who grants**: `308lovechild@gmail.com` (project owner, logged into Firebase Console)
- **Who receives**: `bytebauble@gmail.com` (agent account)
- **Role**: Cloud Datastore User
- **Collection**: `agent_scenarios`

