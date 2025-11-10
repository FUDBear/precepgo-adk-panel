#!/usr/bin/env python3
"""
Test script for Google ADK agents
Verifies that all ADK agents are properly configured and can be imported.
"""

import sys
import os

def test_imports():
    """Test that ADK can be imported"""
    print("=" * 60)
    print("Testing Google ADK Imports")
    print("=" * 60)
    
    try:
        from google.adk.agents import Agent, SequentialAgent
        from google.adk.tools import ToolContext
        print("✅ ADK imports successful")
        return True
    except ImportError as e:
        print(f"❌ ADK imports failed: {e}")
        print("\n💡 Install ADK with: pip install -r requirements-adk.txt")
        return False

def test_root_agent():
    """Test that root agent can be imported"""
    print("\n" + "=" * 60)
    print("Testing Root Agent Import")
    print("=" * 60)
    
    try:
        from agent import root_agent, safety_pipeline
        print(f"✅ Root agent loaded: {root_agent.name}")
        print(f"✅ Safety pipeline loaded: {safety_pipeline.name}")
        print(f"✅ Root agent has {len(root_agent.sub_agents)} sub-agents")
        return True
    except Exception as e:
        print(f"❌ Root agent import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_sub_agents():
    """Test that all sub-agents can be imported"""
    print("\n" + "=" * 60)
    print("Testing Sub-Agent Imports")
    print("=" * 60)
    
    agents_to_test = [
        ("evaluation_agent", "agents.evaluations_agent"),
        ("notification_agent", "agents.notification_agent"),
        ("scenario_agent", "agents.scenario_agent"),
        ("time_agent", "agents.time_agent"),
    ]
    
    all_passed = True
    for agent_name, module_path in agents_to_test:
        try:
            module = __import__(module_path, fromlist=[agent_name])
            agent = getattr(module, agent_name)
            print(f"✅ {agent_name} loaded: {agent.name}")
            all_passed = True
        except Exception as e:
            print(f"❌ {agent_name} import failed: {e}")
            all_passed = False
    
    return all_passed

def test_adk_patterns():
    """Test that agents follow ADK patterns"""
    print("\n" + "=" * 60)
    print("Testing ADK Patterns")
    print("=" * 60)
    
    try:
        from agent import root_agent
        from google.adk.agents import Agent, SequentialAgent
        
        # Check root agent
        if isinstance(root_agent, Agent):
            print("✅ Root agent uses Agent class")
        else:
            print("❌ Root agent does not use Agent class")
            return False
        
        # Check sub-agents
        for sub_agent in root_agent.sub_agents:
            if isinstance(sub_agent, (Agent, SequentialAgent)):
                print(f"✅ Sub-agent '{sub_agent.name}' uses ADK pattern")
            else:
                print(f"❌ Sub-agent '{sub_agent.name}' does not use ADK pattern")
                return False
        
        return True
    except Exception as e:
        print(f"❌ ADK pattern test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("Google ADK Agent Test Suite")
    print("=" * 60)
    print()
    
    results = []
    
    # Test 1: Imports
    results.append(("ADK Imports", test_imports()))
    
    # Test 2: Root Agent
    if results[0][1]:  # Only test if imports passed
        results.append(("Root Agent", test_root_agent()))
    
    # Test 3: Sub-agents
    if results[-1][1]:  # Only test if root agent passed
        results.append(("Sub-Agents", test_sub_agents()))
    
    # Test 4: ADK Patterns
    if results[-1][1]:  # Only test if sub-agents passed
        results.append(("ADK Patterns", test_adk_patterns()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 All tests passed! ADK agents are properly configured.")
        print("\n💡 Next steps:")
        print("   1. Run: adk run .")
        print("   2. Or: adk web")
        print("   3. Or: adk deploy cloud_run ...")
        return 0
    else:
        print("❌ Some tests failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

