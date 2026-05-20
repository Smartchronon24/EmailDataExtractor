import asyncio
import json
from unittest.mock import AsyncMock, patch
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the function we want to test
from stage0_agent import stage0_deduplicate

async def run_diagnostic():
    print("[Test] Starting Stage 0 Diagnostic...")
    
    # Mocking the Ollama response so we don't need the server running for this test
    mock_response = {
        'message': {
            'content': '{"decision": "DUPLICATE", "reasoning": "Diagnostic Test: Exact match simulated."}'
        }
    }
    
    test_email = {
        "subject": "Diagnostic Test Email",
        "body": "This is a test body with INV-12345",
        "sender": "test@example.com",
        "conv_id": "conv_123",
        "msg_id": "msg_456"
    }

    print("\n--- Testing Logic Flow ---")
    with patch('ollama.AsyncClient.chat', new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_response
        
        try:
            result = await stage0_deduplicate(**test_email)
            print("\nLogic Test Passed!")
            print(f"Result: {result}")
            
            # Verify the structure matches what app.py expects
            if result and result.get('decision') in ['DUPLICATE', 'NEW']:
                print("Guard Rail Check: app.py will correctly handle this decision.")
            else:
                print("Guard Rail Check: Result structure is unexpected.")
                
        except Exception as e:
            print(f"Logic Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_diagnostic())
