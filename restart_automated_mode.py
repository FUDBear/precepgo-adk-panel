#!/usr/bin/env python3
"""
Restart Automated Mode
Fixes desync between Firestore and in-memory state by stopping and starting automated mode.
"""

import requests
import time
import sys

# Configuration
BASE_URL = "http://localhost:8080"  # ADK Panel server port

def stop_automated_mode():
    """Stop automated mode to clear stale state"""
    print("🛑 Stopping automated mode...")
    try:
        response = requests.post(f"{BASE_URL}/agents/automated-mode/stop", timeout=10)
        result = response.json()

        if result.get("ok"):
            print(f"✅ {result.get('message', 'Stopped successfully')}")
            return True
        else:
            print(f"⚠️ {result.get('detail', 'Failed to stop')}")
            # Even if it says "not running", that's OK - we just want to ensure it's stopped
            return True
    except Exception as e:
        print(f"❌ Error stopping automated mode: {e}")
        return False

def start_automated_mode():
    """Start automated mode fresh"""
    print("🚀 Starting automated mode...")
    try:
        response = requests.post(f"{BASE_URL}/agents/automated-mode/start", timeout=10)
        result = response.json()

        if result.get("ok"):
            duration = result.get("duration_minutes", 15)
            print(f"✅ {result.get('message', 'Started successfully')}")
            print(f"⏰ Automated mode will run for {duration} minutes")
            return True
        else:
            print(f"❌ {result.get('detail', 'Failed to start')}")
            return False
    except Exception as e:
        print(f"❌ Error starting automated mode: {e}")
        return False

def get_status():
    """Check current automated mode status"""
    print("📊 Checking automated mode status...")
    try:
        response = requests.get(f"{BASE_URL}/agents/automated-mode/status", timeout=10)
        result = response.json()

        if result.get("ok"):
            is_active = result.get("active", False)
            mode = result.get("automated_mode", "UNKNOWN")

            print(f"   - In-memory active: {is_active}")
            print(f"   - Firestore mode: {mode}")

            if result.get("start_time"):
                print(f"   - Start time: {result.get('start_time')}")
            if result.get("end_time"):
                print(f"   - End time: {result.get('end_time')}")

            return is_active
        else:
            print(f"⚠️ {result.get('detail', 'Failed to get status')}")
            return False
    except Exception as e:
        print(f"❌ Error getting status: {e}")
        print(f"⚠️ Is the server running at {BASE_URL}?")
        return False

def main():
    """Main execution"""
    print("="*60)
    print("🔧 Automated Mode Restart Script")
    print("="*60)
    print()

    # Check initial status
    print("STEP 1: Check current status")
    get_status()
    print()

    # Stop automated mode
    print("STEP 2: Stop automated mode (clear stale state)")
    if not stop_automated_mode():
        print("❌ Failed to stop. Exiting.")
        sys.exit(1)
    print()

    # Wait a moment
    print("⏳ Waiting 2 seconds...")
    time.sleep(2)
    print()

    # Start automated mode
    print("STEP 3: Start automated mode fresh")
    if not start_automated_mode():
        print("❌ Failed to start. Exiting.")
        sys.exit(1)
    print()

    # Wait a moment
    print("⏳ Waiting 2 seconds...")
    time.sleep(2)
    print()

    # Check final status
    print("STEP 4: Verify automated mode is running")
    is_active = get_status()
    print()

    if is_active:
        print("="*60)
        print("✅ SUCCESS! Automated mode is now running properly")
        print("="*60)
        print()
        print("📋 What happens next:")
        print("   - State Agent scheduler checks all agents every 5 seconds")
        print("   - evaluation_agent runs every 5 minutes")
        print("   - time_agent runs every 5 minutes")
        print("   - site_agent runs every 1 hour")
        print("   - coa_agent runs every 2 hours")
        print("   - notification_agent runs after evaluation_agent completes")
        print("   - scenario_agent runs after notification_agent completes")
        print()
        print("⏰ Mode will auto-stop after 15 minutes")
        print("   (or call /agents/automated-mode/stop to stop manually)")
    else:
        print("="*60)
        print("❌ FAILED - Automated mode is not running")
        print("="*60)
        print()
        print("🔍 Troubleshooting:")
        print("   1. Check if the server is running at", BASE_URL)
        print("   2. Check server logs for errors")
        print("   3. Verify state_agent initialized successfully on startup")
        sys.exit(1)

if __name__ == "__main__":
    main()
