@echo off
REM MFS Literacy Platform - Windows Startup Script

echo.
echo 🎓 MFS Literacy Assessment Platform
echo ====================================
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔄 Activating virtual environment...
call venv\Scripts\activate

REM Check if .env file exists
if not exist ".env" (
    echo ⚠️  No .env file found!
    echo 📝 Creating .env from template...
    copy .env.example .env
    echo.
    echo ⚠️  IMPORTANT: Edit .env file and add your OpenAI API key!
    echo    Then run this script again.
    pause
    exit
)

REM Install dependencies if needed
if not exist "venv\Lib\site-packages\fastapi\" (
    echo 📦 Installing dependencies...
    pip install -r requirements.txt
)

echo.
echo 🚀 Starting MFS Literacy Platform...
echo 📍 Server will be available at: http://localhost:8000
echo.
echo Default Admin Login:
echo   Email: admin@mfs.org
echo   Password: admin123
echo.
echo Press Ctrl+C to stop the server
echo.

REM Start the application
python app.py