#!/usr/bin/env python3
"""
Test script for evaluation_agent to verify it works with ADK Runner API.
"""

import sys
import os
import asyncio

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

async def test_evaluation_agent():
    """Test the evaluation agent with ADK Runner"""
    print("🧪 Testing Evaluation Agent with ADK Runner API")
    print("=" * 60)
    
    try:
        # Import ADK components
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from agents.evaluations_agent import evaluation_agent
        import uuid
        
        print("✅ ADK imports successful")
        print(f"✅ Evaluation agent loaded: {evaluation_agent.name}")
        print(f"✅ Agent type: {type(evaluation_agent).__name__}")
        print(f"✅ Sub-agents: {len(evaluation_agent.sub_agents) if hasattr(evaluation_agent, 'sub_agents') else 'N/A'}")
        
        # Create session service
        session_service = InMemorySessionService()
        print("✅ Session service created")
        
        # Create session
        session_id = f"test-eval-{uuid.uuid4().hex[:8]}"
        session = await session_service.create_session(
            app_name="test-precepgo-adk-panel",
            user_id="test-user",
            session_id=session_id
        )
        print(f"✅ Session created: {session_id}")
        
        # Create runner
        runner = Runner(
            app_name="test-precepgo-adk-panel",
            agent=evaluation_agent,
            session_service=session_service
        )
        print("✅ Runner created")
        
        # Test Runner.run signature
        import inspect
        sig = inspect.signature(runner.run)
        print(f"✅ Runner.run signature: {sig}")
        
        # Run the agent
        print("\n🚀 Running evaluation agent...")
        print("Prompt: 'Create an evaluation'")
        
        try:
            result = await runner.run(
                prompt="Create an evaluation",
                session=session
            )
            print(f"\n✅ Agent execution completed!")
            print(f"Result type: {type(result)}")
            print(f"Result: {result}")
            
            # Check session state
            if hasattr(session, 'state'):
                print(f"\n📊 Session state keys: {list(session.state.keys())}")
                if 'evaluation_doc_id' in session.state:
                    print(f"✅ Evaluation saved! Doc ID: {session.state['evaluation_doc_id']}")
                if 'selected_case' in session.state:
                    print(f"✅ Case selected: {session.state['selected_case'].get('name', 'N/A')}")
                if 'selected_student' in session.state:
                    print(f"✅ Student selected: {session.state['selected_student'].get('name', 'N/A')}")
            
            return True
            
        except Exception as e:
            print(f"\n❌ Error running agent: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure google-adk is installed: pip install google-adk")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_evaluation_agent())
    sys.exit(0 if success else 1)

