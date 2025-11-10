#!/usr/bin/env python3
"""
Test script to verify evaluation_agent works with ADK Runner API.
This will test the actual execution flow.
"""

import sys
import os
import asyncio

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

async def test_evaluation_agent_execution():
    """Test the evaluation agent execution"""
    print("🧪 Testing Evaluation Agent Execution")
    print("=" * 70)
    
    try:
        # Import ADK components
        print("\n📦 Step 1: Importing ADK components...")
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from agents.evaluations_agent import evaluation_agent
        import uuid
        
        print("✅ ADK Runner imported")
        print("✅ SessionService imported")
        print(f"✅ Evaluation agent imported: {evaluation_agent.name}")
        print(f"   Type: {type(evaluation_agent).__name__}")
        print(f"   Sub-agents: {len(evaluation_agent.sub_agents)}")
        
        # Create session service
        print("\n📦 Step 2: Creating session service...")
        session_service = InMemorySessionService()
        print("✅ Session service created")
        
        # Create runner
        print("\n📦 Step 3: Creating runner...")
        runner = Runner(
            app_name="test-precepgo-adk-panel",
            agent=evaluation_agent,
            session_service=session_service
        )
        print("✅ Runner created")
        
        # Check Runner.run signature
        print("\n📦 Step 4: Checking Runner.run signature...")
        import inspect
        sig = inspect.signature(runner.run)
        print(f"✅ Runner.run signature: {sig}")
        params = list(sig.parameters.keys())
        print(f"   Parameters: {params}")
        
        # Create session IDs
        print("\n📦 Step 5: Creating session IDs...")
        session_id = f"test-eval-{uuid.uuid4().hex[:8]}"
        user_id = "test-user"
        print(f"✅ Session ID: {session_id}")
        print(f"✅ User ID: {user_id}")
        
        # Run the agent
        print("\n🚀 Step 6: Running evaluation agent...")
        print(f"   Message: 'Create an evaluation'")
        print(f"   Using API: runner.run(user_id='{user_id}', session_id='{session_id}', message='Create an evaluation')")
        
        try:
            result = await runner.run(
                user_id=user_id,
                session_id=session_id,
                message="Create an evaluation"
            )
            print(f"✅ Agent execution completed!")
            print(f"   Result type: {type(result)}")
            print(f"   Result: {result}")
            
            # Get session to check state
            print("\n📦 Step 7: Checking session state...")
            session = await session_service.get_session(
                app_name="test-precepgo-adk-panel",
                user_id=user_id,
                session_id=session_id
            )
            
            if session and hasattr(session, 'state'):
                state_keys = list(session.state.keys())
                print(f"✅ Session state keys ({len(state_keys)}):")
                for key in sorted(state_keys):
                    value = session.state[key]
                    if isinstance(value, (dict, list)):
                        print(f"   - {key}: {type(value).__name__} ({len(value)} items)")
                    elif isinstance(value, str) and len(value) > 100:
                        print(f"   - {key}: {type(value).__name__} (length: {len(value)})")
                    else:
                        print(f"   - {key}: {value}")
                
                # Check for success indicators
                if 'evaluation_doc_id' in session.state:
                    doc_id = session.state['evaluation_doc_id']
                    print(f"\n✅ SUCCESS! Evaluation created!")
                    print(f"   Document ID: {doc_id}")
                    return True
                else:
                    print(f"\n⚠️  Warning: No evaluation_doc_id in state")
                    print(f"   This might mean the agent didn't complete all steps")
                    return False
            else:
                print(f"⚠️  Could not get session state")
                return False
                
        except TypeError as e:
            print(f"\n❌ TypeError: {e}")
            print(f"   This suggests the Runner.run() API signature is incorrect")
            print(f"   Expected parameters: {params}")
            import traceback
            traceback.print_exc()
            return False
        except Exception as e:
            print(f"\n❌ Error running agent: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("   Make sure google-adk is installed: pip install google-adk")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n" + "=" * 70)
    success = asyncio.run(test_evaluation_agent_execution())
    print("=" * 70)
    if success:
        print("✅ TEST PASSED - Evaluation agent works correctly!")
    else:
        print("❌ TEST FAILED - Check errors above")
    print("=" * 70)
    sys.exit(0 if success else 1)

