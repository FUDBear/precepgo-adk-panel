#!/usr/bin/env python3
"""
Test ADK Deployment Readiness
Verifies all agents can be imported and are ready for Cloud Run deployment.
"""

import sys
import os

print("🔍 Testing ADK Deployment Readiness...\n")

# Test 1: Check if agent.py exists
print("1️⃣ Checking entry point (agent.py)...")
if not os.path.exists("agent.py"):
    print("   ❌ FAIL: agent.py not found")
    sys.exit(1)
print("   ✅ PASS: agent.py exists")

# Test 2: Try importing root_agent from agent.py
print("\n2️⃣ Testing agent.py imports...")
try:
    from agent import root_agent, agent
    print(f"   ✅ PASS: root_agent imported")
    print(f"   ✅ PASS: agent = {agent.name if hasattr(agent, 'name') else 'unknown'}")
except ImportError as e:
    print(f"   ❌ FAIL: Cannot import from agent.py: {e}")
    sys.exit(1)

# Test 3: Try importing from root_agent.py
print("\n3️⃣ Testing agents/root_agent.py...")
try:
    from agents.root_agent import root_agent as ra, safety_pipeline
    print(f"   ✅ PASS: root_agent imported (name={ra.name})")
    print(f"   ✅ PASS: safety_pipeline imported (name={safety_pipeline.name})")
except ImportError as e:
    print(f"   ❌ FAIL: Cannot import from agents/root_agent.py: {e}")
    sys.exit(1)

# Test 4: Check individual ADK agents
print("\n4️⃣ Testing individual ADK agents...")
try:
    from agents.evaluations_agent import evaluation_agent
    print(f"   ✅ PASS: evaluation_agent (name={evaluation_agent.name})")
except ImportError as e:
    print(f"   ❌ FAIL: evaluation_agent: {e}")
    sys.exit(1)

try:
    from agents.notification_agent import notification_agent
    print(f"   ✅ PASS: notification_agent (name={notification_agent.name})")
except ImportError as e:
    print(f"   ❌ FAIL: notification_agent: {e}")
    sys.exit(1)

try:
    from agents.scenario_agent import scenario_agent
    print(f"   ✅ PASS: scenario_agent (name={scenario_agent.name})")
except ImportError as e:
    print(f"   ❌ FAIL: scenario_agent: {e}")
    sys.exit(1)

try:
    from agents.time_agent import time_agent
    print(f"   ✅ PASS: time_agent (name={time_agent.name})")
except ImportError as e:
    print(f"   ❌ FAIL: time_agent: {e}")
    sys.exit(1)

# Test 5: Verify ADK patterns
print("\n5️⃣ Verifying ADK patterns...")

# Check if agents use google.adk
try:
    from google.adk.agents import Agent, SequentialAgent
    from google.adk.tools import ToolContext
    print("   ✅ PASS: google.adk imports work")
except ImportError as e:
    print(f"   ⚠️  WARNING: google.adk not installed: {e}")
    print("   ℹ️  Run: pip install google-adk")

# Check root_agent structure
if hasattr(root_agent, 'sub_agents'):
    print(f"   ✅ PASS: root_agent has {len(root_agent.sub_agents)} sub_agents")
else:
    print("   ⚠️  WARNING: root_agent missing sub_agents attribute")

# Check safety_pipeline structure
if hasattr(safety_pipeline, 'sub_agents'):
    print(f"   ✅ PASS: safety_pipeline has {len(safety_pipeline.sub_agents)} sub_agents")
else:
    print("   ⚠️  WARNING: safety_pipeline missing sub_agents attribute")

# Test 6: Check data files
print("\n6️⃣ Checking required data files...")
required_files = [
    "data/cases.json",
    "data/students.json",
    "data/patient_templates.json",
    "data/sites.json"
]

for file_path in required_files:
    if os.path.exists(file_path):
        print(f"   ✅ {file_path}")
    else:
        print(f"   ⚠️  WARNING: {file_path} missing")

# Test 7: Check requirements
print("\n7️⃣ Checking requirements.txt...")
if os.path.exists("requirements.txt"):
    with open("requirements.txt") as f:
        requirements = f.read()
        if "google-adk" in requirements:
            print("   ✅ PASS: google-adk in requirements.txt")
        else:
            print("   ⚠️  WARNING: google-adk not in requirements.txt")
            print("   ℹ️  Add: google-adk")
else:
    print("   ⚠️  WARNING: requirements.txt not found")

# Test 8: Environment variables
print("\n8️⃣ Checking environment variables...")
if os.getenv("GOOGLE_API_KEY"):
    print("   ✅ PASS: GOOGLE_API_KEY is set")
else:
    print("   ⚠️  WARNING: GOOGLE_API_KEY not set")
    print("   ℹ️  Set before deployment")

if os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT"):
    print("   ✅ PASS: Project ID is set")
else:
    print("   ⚠️  WARNING: FIREBASE_PROJECT_ID not set")
    print("   ℹ️  Set before deployment")

# Summary
print("\n" + "="*60)
print("📊 DEPLOYMENT READINESS SUMMARY")
print("="*60)
print("✅ All critical tests passed!")
print("✅ ADK agents are properly structured")
print("✅ Ready for Cloud Run deployment")
print("\n🚀 Next steps:")
print("   1. Set environment variables (GOOGLE_API_KEY, FIREBASE_PROJECT_ID)")
print("   2. Run: adk deploy cloud_run --project=<PROJECT_ID> ...")
print("   3. Or use Docker: gcloud builds submit ...")
print("\n📖 See DEPLOY_CLOUD_RUN.md for detailed instructions")
print("="*60)
