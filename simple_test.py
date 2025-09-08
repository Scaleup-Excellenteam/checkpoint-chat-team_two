import os

# Test if .env file is being read
print("Testing .env file loading...")

# Check if .env file exists
if os.path.exists('.env'):
    print("[OK] .env file found")
    
    # Read .env manually to verify content
    with open('.env', 'r') as f:
        lines = f.readlines()
    
    print(f"[OK] .env contains {len(lines)} lines")
    
    # Show first few variables
    for line in lines[:5]:
        if '=' in line and not line.startswith('#'):
            print(f"  {line.strip()}")
else:
    print("[ERROR] .env file not found")

# Test environment variables
os.environ['TEST_VAR'] = 'test_value'
print(f"[OK] Environment variable test: {os.getenv('TEST_VAR')}")

print("\nConfiguration files status:")
print(f"[OK] config.py exists: {os.path.exists('server/config.py')}")
print(f"[OK] .env.example exists: {os.path.exists('.env.example')}")