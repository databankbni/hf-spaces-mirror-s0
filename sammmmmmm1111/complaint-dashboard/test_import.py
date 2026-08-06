import sys
import os

# Print current directory and sys.path for debugging
print("Current directory:", os.getcwd())
print("\nPython path:")
for p in sys.path:
    print(f"  {p}")

# Check if action_lookup.py exists
action_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "action_lookup.py")
print(f"\nChecking action_lookup.py at: {action_path}")
print(f"Exists: {os.path.exists(action_path)}")

# Now try importing
print("\nTrying to import...")
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import action_lookup
    print(f"✓ Successfully imported action_lookup")
    print(f"  Available attributes: {[attr for attr in dir(action_lookup) if not attr.startswith('_')]}")
    
    # Test each function
    print("\nTesting functions:")
    
    # Test 1
    res = action_lookup.get_resolution("UPI", "Amount Debited but Payment Failed")
    print(f"✓ get_resolution works: {res}")
    
    # Test 2
    dec = action_lookup.get_decision("UPI", "Amount Debited but Payment Failed")
    print(f"✓ get_decision works: {dec}")
    
    # Test 3
    acts = action_lookup.get_actions("UPI", "Amount Debited but Payment Failed")
    print(f"✓ get_actions works: {acts}")
    
    print("\n✅ All imports and functions work!")
    
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
    import traceback
    print("\nStack trace:")
    traceback.print_exc()
