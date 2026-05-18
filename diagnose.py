import sys
import os

print("--- DIAGNOSTIC START ---")
try:
    print("Checking config...")
    import config
    print("✓ Config OK")
    
    print("Checking database...")
    import database
    print("✓ Database OK")
    
    print("Checking agent_utils...")
    import agent_utils
    print("✓ Agent Utils OK")
    
    print("Checking processor...")
    import processor
    print("✓ Processor OK")
    
    print("Checking main...")
    import main
    print("✓ Main OK")
    
    print("Checking stage0_agent...")
    import stage0_agent
    print("✓ Stage0 OK")
    
    print("All modules imported successfully.")
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
print("--- DIAGNOSTIC END ---")
