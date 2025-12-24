#!/bin/bash

# MFS Literacy Platform - Startup Script

echo "🎓 MFS Literacy Assessment Platform"
echo "===================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found!"
    echo "📝 Creating .env from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file and add your OpenAI API key!"
    echo "   Then run this script again."
    exit 1
fi

# Install dependencies if needed
if [ ! -f "venv/lib/python*/site-packages/fastapi" ]; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

# Check if OpenAI API key is set
if grep -q "sk-your-openai-api-key-here" .env; then
    echo "⚠️  WARNING: OpenAI API key not configured!"
    echo "   Edit .env file and add your actual API key."
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "🚀 Starting MFS Literacy Platform..."
echo "📍 Server will be available at: http://localhost:8000"
echo ""
echo "Default Admin Login:"
echo "  Email: admin@mfs.org"
echo "  Password: admin123"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the application
python app.py