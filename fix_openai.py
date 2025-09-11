#!/usr/bin/env python3
"""
Fix OpenAI library installation
"""

import subprocess
import sys

def fix_openai():
    print("🔧 Fixing OpenAI library installation...")
    
    try:
        # First, uninstall current version
        print("1️⃣ Uninstalling current OpenAI library...")
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "openai", "-y"], check=True)
        
        # Clear pip cache
        print("2️⃣ Clearing pip cache...")
        subprocess.run([sys.executable, "-m", "pip", "cache", "purge"], check=True)
        
        # Install latest version
        print("3️⃣ Installing latest OpenAI library...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "openai"], check=True)
        
        # Verify installation
        print("4️⃣ Verifying installation...")
        import openai
        print(f"✅ OpenAI library updated to version: {openai.__version__}")
        
        # Test basic functionality
        print("5️⃣ Testing basic functionality...")
        from openai import OpenAI
        
        # Just test client creation without API call
        try:
            client = OpenAI(api_key="test-key")
            print("✅ Client creation works!")
        except Exception as e:
            if "api_key" in str(e).lower():
                print("✅ Client creation works (API key validation expected)")
            else:
                print(f"❌ Client creation still has issues: {str(e)}")
        
        print("\n🎉 OpenAI library should be fixed now!")
        print("💡 Now try running: python simple_test.py")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during pip operations: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    fix_openai()