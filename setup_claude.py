"""
Writes the Webull MCP server entry into Claude Desktop's config file.
Run via setup_claude.bat, or directly: python setup_claude.py
"""
import json
import os
import shutil
import sys

here = os.path.dirname(os.path.abspath(__file__))
server_path = os.path.join(here, "mcp_server.py")

config_dir  = os.path.join(os.environ["APPDATA"], "Claude")
config_file = os.path.join(config_dir, "claude_desktop_config.json")

if not os.path.exists(server_path):
    print(f"ERROR: mcp_server.py not found at {server_path}")
    print("Run this from the Demo3 project folder.")
    sys.exit(1)

python_cmd = shutil.which("python") or shutil.which("python3")
if not python_cmd:
    print("ERROR: python not found on PATH. Install Python 3.8+ first.")
    sys.exit(1)

os.makedirs(config_dir, exist_ok=True)

if os.path.exists(config_file):
    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)
else:
    config = {}

config.setdefault("mcpServers", {})
config["mcpServers"]["webull"] = {
    "command": python_cmd,
    "args": [server_path],
}

with open(config_file, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)

print()
print("Done! Claude Desktop is now configured.")
print()
print(f"  Config : {config_file}")
print(f"  Server : {server_path}")
print(f"  Python : {python_cmd}")
print()
print("Next steps:")
print("  1. Make sure your .env file has WEBULL_APP_KEY, WEBULL_APP_SECRET,")
print("     WEBULL_REGION_ID, and WEBULL_ACCOUNT_ID filled in.")
print("  2. Restart Claude Desktop (fully quit and reopen).")
print("  3. Look for the hammer icon in Claude Desktop -- Webull tools will be listed.")
print('  4. Ask Claude: "Show me my current portfolio positions"')
print()
