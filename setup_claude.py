"""
Writes the Webull MCP server entry into Claude Desktop's config file.
Run via setup_claude.bat, or directly: python setup_claude.py
"""
import glob
import json
import os
import shutil
import sys

here = os.path.dirname(os.path.abspath(__file__))
server_path = os.path.join(here, "mcp_server.py")


def _find_config_dir():
    """
    Locate Claude Desktop's config directory. The Microsoft Store build
    sandboxes it under LocalAppData\\Packages\\Claude_*; the standalone
    installer uses AppData\\Roaming\\Claude.
    """
    candidates = []
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        candidates += glob.glob(os.path.join(
            localappdata, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude"
        ))
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidates.append(os.path.join(appdata, "Claude"))

    # Prefer a directory that already exists; otherwise fall back to the first.
    for d in candidates:
        if os.path.isdir(d):
            return d
    return candidates[0] if candidates else os.path.join(appdata, "Claude")


config_dir  = _find_config_dir()
config_file = os.path.join(config_dir, "claude_desktop_config.json")

if not os.path.exists(server_path):
    print(f"ERROR: mcp_server.py not found at {server_path}")
    print("Run this from the Demo3 project folder.")
    sys.exit(1)

# Prefer Python 3.13 explicitly — the Webull SDK has pre-built wheels for it.
# Falls back to whatever python is on PATH if 3.13 isn't found.
import subprocess

def _find_python():
    for candidate in ["py -3.13", "python3.13"]:
        parts = candidate.split()
        try:
            result = subprocess.run(parts + ["--version"], capture_output=True, text=True)
            if result.returncode == 0 and "3.13" in result.stdout:
                # For "py -3.13", the command Claude Desktop needs is "py" with args ["-3.13", script]
                if parts[0] == "py":
                    return "py", ["-3.13"]
                return parts[0], []
        except FileNotFoundError:
            continue
    # Fall back to whatever python is available
    cmd = shutil.which("python") or shutil.which("python3")
    return cmd, []

python_exe, python_prefix_args = _find_python()
if not python_exe:
    print("ERROR: python not found on PATH. Install Python 3.13 from python.org first.")
    sys.exit(1)

os.makedirs(config_dir, exist_ok=True)

if os.path.exists(config_file):
    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)
else:
    config = {}

config.setdefault("mcpServers", {})
config["mcpServers"]["webull"] = {
    "command": python_exe,
    "args": python_prefix_args + [server_path],
}

with open(config_file, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)

print()
print("Done! Claude Desktop is now configured.")
print()
print(f"  Config : {config_file}")
print(f"  Server : {server_path}")
print(f"  Python : {python_exe} {' '.join(python_prefix_args)}")
print()
print("Next steps:")
print("  1. Make sure your .env file has WEBULL_APP_KEY, WEBULL_APP_SECRET,")
print("     WEBULL_REGION_ID, and WEBULL_ACCOUNT_ID filled in.")
print("  2. Restart Claude Desktop (fully quit and reopen).")
print("  3. Look for the hammer icon in Claude Desktop -- Webull tools will be listed.")
print('  4. Ask Claude: "Show me my current portfolio positions"')
print()
