@echo off
title FUMA ISAK LMS Launcher
echo ===================================================
echo   FUMA ISAK LMS: Web Server va Telegram Bot Launch
echo ===================================================
echo.
echo 1. Django Web Server ishga tushmoqda...
start "Django Web Server" cmd /k "call .venv\Scripts\activate && python manage.py runserver"

echo 2. Telegram Polling Bot ishga tushmoqda...
start "Telegram Bot" cmd /k "call .venv\Scripts\activate && python manage.py run_telegram_bot"

echo.
echo ===================================================
echo   Ikkala xizmat ham alohida oynalarda ishga tushdi!
echo   Oynalarni yopmang.
echo ===================================================
echo.
pause
