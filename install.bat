@echo off
echo Installing Webull Dashboard dependencies for Python 3.13...
echo.

echo [1/5] Upgrading pip and wheel...
py -3.13 -m pip install --upgrade pip wheel
if errorlevel 1 goto :fail

echo.
echo [2/5] Installing setuptools (kept under 81 so pkg_resources stays available)...
py -3.13 -m pip install "setuptools<81"
if errorlevel 1 goto :fail

echo.
echo [3/5] Installing Flask, MCP, and keyring...
py -3.13 -m pip install Flask python-dotenv "mcp>=1.0.0" "keyring>=25.0.0"
if errorlevel 1 goto :fail

echo.
echo [4/5] Installing runtime libraries (modern grpcio with a prebuilt wheel)...
py -3.13 -m pip install grpcio protobuf paho-mqtt jmespath cachetools requests six urllib3 cryptography
if errorlevel 1 goto :fail

echo.
echo [5/5] Installing Webull SDK packages without their broken grpcio pin...
py -3.13 -m pip install --no-deps webull-python-sdk-core webull-python-sdk-quotes-core webull-python-sdk-mdata webull-python-sdk-trade-events-core webull-python-sdk-trade
if errorlevel 1 goto :fail

echo.
echo =========================================
echo  All dependencies installed successfully!
echo =========================================
echo.
echo Verifying the Webull SDK imports...
py -3.13 -c "from webull.core.client import ApiClient; from webull.trade.trade_client import TradeClient; from webull.data.data_client import DataClient; print('Webull SDK imports OK')"
if errorlevel 1 (
  echo.
  echo WARNING: imports failed - tell Claude the error above.
  pause
  exit /b 1
)

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
