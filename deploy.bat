@echo off
REM ============================================
REM Discord Audio Bot - Deployment Script
REM Deploys the bot to Raspberry Pi via SSH
REM ============================================

setlocal enabledelayedexpansion

REM Configuration - Edit these variables
set "PI_HOST=192.168.2.68"
set "PI_USER=rahel"
set "REMOTE_DIR=/home/rahel/discord-audio-bot"

REM Check for --simple flag
set "SIMPLE_MODE=0"
if "%1"=="--simple" set "SIMPLE_MODE=1"

if "%SIMPLE_MODE%"=="1" (
    echo.
    echo ========================================
    echo Discord Audio Bot - Quick Deployment
    echo ========================================
    echo.
    echo Target: %PI_USER%@%PI_HOST%
    echo Remote directory: %REMOTE_DIR%
    echo.

    echo [1/2] Copying bot file...
    scp discord_audio_bot.py .env requirements.txt test_audio.py %PI_USER%@%PI_HOST%:%REMOTE_DIR%/
    if errorlevel 1 (
        echo [ERROR] Failed to copy bot file.
        exit /b 1
    )



    echo.
    echo ========================================
    echo Quick Deployment Complete!
    echo ========================================
    echo.
    echo The bot has been updated and restarted.
    echo.
    echo View logs: ssh %PI_USER%@%PI_HOST% "sudo journalctl -u discord-audio -f"
    echo.

    pause
    exit /b 0
)

echo.
echo ========================================
echo Discord Audio Bot Deployment
echo ========================================
echo.

REM Prompt for configuration if not set
if "%PI_HOST%"=="raspberrypi.local" (
    set /p PI_HOST="Enter Raspberry Pi hostname or IP [raspberrypi.local]: " || set PI_HOST=raspberrypi.local
)

if "%PI_USER%"=="pi" (
    set /p PI_USER="Enter SSH username [pi]: " || set PI_USER=pi
)

echo.
echo Target: %PI_USER%@%PI_HOST%
echo Remote directory: %REMOTE_DIR%
echo.

REM Check if .env file exists locally
if not exist ".env" (
    echo [WARNING] No .env file found locally!
    echo.
    echo Please create a .env file with your configuration:
    echo   - DISCORD_TOKEN=your_token_here
    echo   - ELEVENLABS_API_KEY=your_key_here
    echo.
    echo You can copy .env.example to .env and fill in your values.
    echo.
    set /p continue="Continue anyway? (y/N): "
    if /i not "!continue!"=="y" (
        echo Deployment cancelled.
        exit /b 1
    )
)

echo [1/6] Creating remote directory...
ssh %PI_USER%@%PI_HOST% "mkdir -p %REMOTE_DIR%/logs"
if errorlevel 1 (
    echo [ERROR] Failed to create remote directory. Check SSH connection.
    exit /b 1
)

echo [2/6] Copying Python bot file...
scp discord_audio_bot.py %PI_USER%@%PI_HOST%:%REMOTE_DIR%/
if errorlevel 1 (
    echo [ERROR] Failed to copy bot file.
    exit /b 1
)

echo [3/6] Copying requirements.txt...
scp requirements.txt %PI_USER%@%PI_HOST%:%REMOTE_DIR%/
if errorlevel 1 (
    echo [ERROR] Failed to copy requirements.txt.
    exit /b 1
)

echo [4/6] Copying .env file...
if exist ".env" (
    scp .env %PI_USER%@%PI_HOST%:%REMOTE_DIR%/
    if errorlevel 1 (
        echo [ERROR] Failed to copy .env file.
        exit /b 1
    )
) else (
    echo [SKIP] No .env file to copy.
)

echo [5/6] Preparing systemd service file...
REM Create a temporary service file with correct paths
powershell -Command "(Get-Content discord-audio.service) -replace '/home/pi/discord-audio-bot', '%REMOTE_DIR%' -replace 'User=pi', 'User=%PI_USER%' -replace 'Group=pi', 'Group=%PI_USER%' | Set-Content discord-audio.service.tmp"

scp discord-audio.service.tmp %PI_USER%@%PI_HOST%:/tmp/discord-audio.service
if errorlevel 1 (
    echo [ERROR] Failed to copy service file.
    del discord-audio.service.tmp
    exit /b 1
)
del discord-audio.service.tmp

echo [6/6] Running remote setup...
REM Replace REMOTE_DIR placeholder in the script
powershell -Command "(Get-Content remote_setup.sh -Raw) -replace 'REMOTE_DIR_PLACEHOLDER', '%REMOTE_DIR%' | Set-Content -NoNewline remote_setup_tmp.sh"

REM Copy and execute the setup script
scp remote_setup_tmp.sh %PI_USER%@%PI_HOST%:/tmp/setup_script.sh
if errorlevel 1 (
    echo [ERROR] Failed to copy setup script.
    del remote_setup_tmp.sh
    exit /b 1
)

ssh %PI_USER%@%PI_HOST% "bash /tmp/setup_script.sh && rm /tmp/setup_script.sh"
del remote_setup_tmp.sh

if errorlevel 1 (
    echo.
    echo [ERROR] Remote setup failed!
    echo Check the error messages above.
    exit /b 1
)

echo.
echo ========================================
echo Deployment Complete!
echo ========================================
echo.
echo The bot is now running on your Raspberry Pi.
echo.
echo Useful commands:
echo   - Check status:   ssh %PI_USER%@%PI_HOST% "sudo systemctl status discord-audio"
echo   - View logs:      ssh %PI_USER%@%PI_HOST% "sudo journalctl -u discord-audio -f"
echo   - Restart bot:    ssh %PI_USER%@%PI_HOST% "sudo systemctl restart discord-audio"
echo   - Stop bot:       ssh %PI_USER%@%PI_HOST% "sudo systemctl stop discord-audio"
echo.

pause
