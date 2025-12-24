# Railway Deployment Fix Script for Windows
# Run this in PowerShell from your project directory

Write-Host "🔧 MFS Literacy Platform - Railway Deployment Fix" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# Check if we're in the right directory
if (!(Test-Path "app.py")) {
    Write-Host "❌ Error: app.py not found!" -ForegroundColor Red
    Write-Host "Please run this script from your project directory" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Found project files" -ForegroundColor Green
Write-Host ""

# Remove database files
Write-Host "🗑️  Removing database files..." -ForegroundColor Yellow
Remove-Item -Path "*.db" -ErrorAction SilentlyContinue
Remove-Item -Path "*.db-journal" -ErrorAction SilentlyContinue
Write-Host "✅ Database files removed" -ForegroundColor Green
Write-Host ""

# Check if .gitignore exists
if (!(Test-Path ".gitignore")) {
    Write-Host "⚠️  .gitignore not found - creating one..." -ForegroundColor Yellow
    
    $gitignore = @"
# Python
__pycache__/
*.py[cod]
*`$py.class
*.so
.Python
venv/
.venv/
env/
ENV/
.env
*.db
*.db-journal

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Railway
.railway/

# Logs
*.log
logs/
"@
    
    $gitignore | Out-File -FilePath ".gitignore" -Encoding UTF8
    Write-Host "✅ .gitignore created" -ForegroundColor Green
} else {
    Write-Host "✅ .gitignore exists" -ForegroundColor Green
}
Write-Host ""

# Check Railway configuration files
Write-Host "📝 Checking Railway configuration..." -ForegroundColor Yellow

if (!(Test-Path "Procfile")) {
    "web: uvicorn app:app --host 0.0.0.0 --port `$PORT" | Out-File -FilePath "Procfile" -Encoding UTF8 -NoNewline
    Write-Host "✅ Created Procfile" -ForegroundColor Green
}

if (!(Test-Path "runtime.txt")) {
    "python-3.11.0" | Out-File -FilePath "runtime.txt" -Encoding UTF8 -NoNewline
    Write-Host "✅ Created runtime.txt" -ForegroundColor Green
}

if (!(Test-Path "railway.json")) {
    $railwayJson = @"
{
  "`$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "pip install -r requirements.txt"
  },
  "deploy": {
    "startCommand": "uvicorn app:app --host 0.0.0.0 --port `$PORT",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
"@
    $railwayJson | Out-File -FilePath "railway.json" -Encoding UTF8
    Write-Host "✅ Created railway.json" -ForegroundColor Green
}
Write-Host ""

# Git operations
Write-Host "📦 Preparing Git commit..." -ForegroundColor Yellow

git add .gitignore
git add Procfile
git add runtime.txt
git add railway.json
git add app.py
git add requirements.txt
git add static/
git add *.md

Write-Host "✅ Files staged for commit" -ForegroundColor Green
Write-Host ""

# Check git status
Write-Host "📊 Git Status:" -ForegroundColor Cyan
git status --short
Write-Host ""

# Commit
Write-Host "💾 Creating commit..." -ForegroundColor Yellow
git commit -m "Fix: Prepare for Railway deployment - add config files and .gitignore"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Commit created successfully" -ForegroundColor Green
} else {
    Write-Host "ℹ️  No changes to commit or commit already exists" -ForegroundColor Blue
}
Write-Host ""

# Push to GitHub
Write-Host "🚀 Pushing to GitHub..." -ForegroundColor Yellow
git push origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Pushed to GitHub successfully" -ForegroundColor Green
} else {
    Write-Host "⚠️  Push failed or nothing to push" -ForegroundColor Yellow
}
Write-Host ""

# Railway deployment options
Write-Host "=" -ForegroundColor Cyan
Write-Host "🚂 Railway Deployment Options:" -ForegroundColor Cyan
Write-Host "=" -ForegroundColor Cyan
Write-Host ""
Write-Host "Option 1: Deploy via Railway Dashboard (RECOMMENDED)" -ForegroundColor Green
Write-Host "  1. Go to: https://railway.app/new" -ForegroundColor White
Write-Host "  2. Click 'Deploy from GitHub repo'" -ForegroundColor White
Write-Host "  3. Select 'sidn405/ai-assessment'" -ForegroundColor White
Write-Host "  4. Railway will auto-deploy" -ForegroundColor White
Write-Host "  5. Add environment variables in Settings > Variables:" -ForegroundColor White
Write-Host "     - OPENAI_API_KEY" -ForegroundColor Yellow
Write-Host "     - SECRET_KEY" -ForegroundColor Yellow
Write-Host ""

Write-Host "Option 2: Try Railway CLI again" -ForegroundColor Green
Write-Host "  Run: railway up" -ForegroundColor White
Write-Host ""

Write-Host "Option 3: Link and deploy" -ForegroundColor Green
Write-Host "  Run: railway link" -ForegroundColor White
Write-Host "  Then: railway up" -ForegroundColor White
Write-Host ""

Write-Host "✅ Your repository is now clean and ready for deployment!" -ForegroundColor Green
Write-Host ""

# Check if Railway CLI is working
Write-Host "🔍 Checking Railway CLI..." -ForegroundColor Yellow
try {
    $railwayVersion = railway --version 2>&1
    Write-Host "✅ Railway CLI is installed: $railwayVersion" -ForegroundColor Green
    Write-Host ""
    Write-Host "Ready to deploy! Run:" -ForegroundColor Cyan
    Write-Host "  railway up" -ForegroundColor White
} catch {
    Write-Host "⚠️  Railway CLI not found or not working" -ForegroundColor Yellow
    Write-Host "Please use Option 1 (Railway Dashboard) for deployment" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "📖 For more help, see RAILWAY_TROUBLESHOOTING.md" -ForegroundColor Cyan