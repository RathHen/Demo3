@echo off
echo Installing Webull Dashboard dependencies for Python 3.13...
echo.

echo [1/4] Upgrading pip and setuptools...
py -3.13 -m pip install --upgrade pip setuptools
if errorlevel 1 goto :fail

echo.
echo [2/4] Installing Flask, MCP, and keyring...
py -3.13 -m pip install Flask python-dotenv "mcp>=1.0.0" "keyring>=25.0.0"
if errorlevel 1 goto :fail

echo.
echo [3/4] Installing Webull SDK core and market data...
py -3.13 -m pip install webull-python-sdk-core webull-python-sdk-mdata
if errorlevel 1 goto :fail

echo.
echo [4/4] Installing Webull trade SDK (skipping unused gRPC streaming dependency)...
py -3.13 -m pip install webull-python-sdk-trade-events-core --no-deps
py -3.13 -m pip install webull-python-sdk-trade --no-deps
if errorlevel 1 goto :fail

echo.
echo =========================================
echo  All dependencies installed successfully!
echo =========================================
echo.
echo Next: run store_credentials.bat to save your Webull API keys,
echo then run setup_claude.bat to configure Claude Desktop.
echo.
pause
goto :eof

:fail
echo.
echo ERROR: Installation failed. See output above.
pause
exit /b 1
