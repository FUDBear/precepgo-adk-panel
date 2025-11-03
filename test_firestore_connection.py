#!/usr/bin/env python3
"""
Test script to verify Firestore permissions and connection
"""

import os
from google.cloud import firestore
from dotenv import load_dotenv

load_dotenv()

project_id = os.getenv('FIREBASE_PROJECT_ID') or os.getenv('GOOGLE_CLOUD_PROJECT') or 'auth-demo-90be0'
collection_name = 'agent_scenarios'

print("=" * 80)
print(" Firestore Connection Test ")
print("=" * 80)
print()

print(f"📋 Project ID: {project_id}")
print(f"📋 Collection: {collection_name}")
print()

try:
    # Create client
    db = firestore.Client(project=project_id)
    print("✅ Firestore client created")
    
    # Test write permission
    print()
    print("🔍 Testing write permission...")
    test_ref = db.collection(collection_name).document('_test_write')
    test_ref.set({
        'test': True,
        'timestamp': firestore.SERVER_TIMESTAMP,
        'message': 'Testing write access'
    })
    print("✅ Write test successful!")
    
    # Test read permission
    print()
    print("🔍 Testing read permission...")
    test_doc = test_ref.get()
    if test_doc.exists:
        print(f"✅ Read test successful! Data: {test_doc.to_dict()}")
    
    # Clean up test document
    print()
    print("🧹 Cleaning up test document...")
    test_ref.delete()
    print("✅ Test document deleted")
    
    print()
    print("=" * 80)
    print("✅ ALL TESTS PASSED!")
    print("=" * 80)
    print()
    print("Your Firestore setup is working correctly!")
    print(f"Scenarios will be saved to: {collection_name}")
    
except Exception as e:
    print()
    print("=" * 80)
    print("❌ ERROR OCCURRED")
    print("=" * 80)
    print()
    print(f"Error: {e}")
    print()
    print("This usually means:")
    print("1. Missing IAM permissions - You need 'Cloud Datastore User' role")
    print("2. Wrong project ID - Check your FIREBASE_PROJECT_ID in .env")
    print("3. Credentials not set up - Run: gcloud auth application-default login")
    print()
    print("To grant permissions:")
    print("  gcloud projects add-iam-policy-binding auth-demo-90be0 \\")
    print("    --member=user:YOUR_EMAIL@gmail.com \\")
    print("    --role=roles/datastore.user")

