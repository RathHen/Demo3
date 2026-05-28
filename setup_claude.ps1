# Configure Claude Desktop to use the Webull MCP server.
# Run once, then restart Claude Desktop.
#
# If you get an execution policy error, run this in PowerShell first:
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
#
# Or bypass it for just this script:
#   powershell -ExecutionPolicy Bypass -File setup_claude.ps1

$serverPath = Join-Path $PSScriptRoot "mcp_server.py"
$configDir  = Join-Path $env:APPDATA "Claude"
$configFile = Join-Path $configDir "claude_desktop_config.json"

if (-not (Test-Path $serverPath)) {
    Write-Host "ERROR: mcp_server.py not found at $serverPath" -ForegroundColor Red
    Write-Host "Run this script from the Demo3 project folder." -ForegroundColor Red
    exit 1
}

# Find python on PATH
$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $pythonCmd) {
    $pythonCmd = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source
}
if (-not $pythonCmd) {
    Write-Host "ERROR: python not found on PATH. Install Python 3.8+ first." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $configDir | Out-Null

# Load existing config or start fresh
if (Test-Path $configFile) {
    $config = Get-Content $configFile -Raw | ConvertFrom-Json
} else {
    $config = [PSCustomObject]@{}
}

if (-not $config.PSObject.Properties["mcpServers"]) {
    $config | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{})
}

# Add / overwrite the webull entry
$config.mcpServers | Add-Member -NotePropertyName "webull" -NotePropertyValue ([PSCustomObject]@{
    command = $pythonCmd
    args    = @($serverPath)
}) -Force

$config | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $configFile

Write-Host ""
Write-Host "Done! Claude Desktop is now configured." -ForegroundColor Green
Write-Host ""
Write-Host "  Config : $configFile"
Write-Host "  Server : $serverPath"
Write-Host "  Python : $pythonCmd"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Make sure your .env file has WEBULL_APP_KEY, WEBULL_APP_SECRET,"
Write-Host "     WEBULL_REGION_ID, and WEBULL_ACCOUNT_ID filled in."
Write-Host "  2. Restart Claude Desktop (fully quit and reopen)."
Write-Host "  3. In Claude Desktop, look for the hammer icon — Webull tools will be listed."
Write-Host "  4. Ask Claude: 'Show me my current portfolio positions'"
Write-Host ""
