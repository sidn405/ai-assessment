# Complete Project Setup and Push Script
# Run this from your AI_Assessment directory in PowerShell

Write-Host ""
Write-Host "🚀 MFS Literacy Platform - Complete Setup & Deploy" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# Check current directory
$currentDir = (Get-Item -Path ".\").Name
Write-Host "📁 Current directory: $currentDir" -ForegroundColor Yellow

if ($currentDir -ne "AI_Assessment" -and $currentDir -ne "ai-assessment") {
    Write-Host "⚠️  Warning: You might not be in the correct directory" -ForegroundColor Yellow
    Write-Host "Expected: AI_Assessment or ai-assessment" -ForegroundColor Yellow
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne "y") { exit }
}
Write-Host ""

# Check what files exist
Write-Host "🔍 Checking which files exist..." -ForegroundColor Yellow
$requiredFiles = @("app.py", "requirements.txt", "README.md")
$missingFiles = @()

foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-Host "  ✅ $file" -ForegroundColor Green
    } else {
        Write-Host "  ❌ $file MISSING!" -ForegroundColor Red
        $missingFiles += $file
    }
}
Write-Host ""

if ($missingFiles.Count -gt 0) {
    Write-Host "❌ ERROR: Missing critical files!" -ForegroundColor Red
    Write-Host "Please download all the files I provided and place them in this directory:" -ForegroundColor Yellow
    Write-Host "  - app.py" -ForegroundColor White
    Write-Host "  - requirements.txt" -ForegroundColor White
    Write-Host "  - static/ folder with HTML files" -ForegroundColor White
    Write-Host "  - All .md files" -ForegroundColor White
    Write-Host ""
    Write-Host "After downloading, run this script again." -ForegroundColor Cyan
    exit 1
}

# Check if static folder exists
if (!(Test-Path "static")) {
    Write-Host "❌ ERROR: static/ folder not found!" -ForegroundColor Red
    Write-Host "Please create a 'static' folder and add these files:" -ForegroundColor Yellow
    Write-Host "  - index.html" -ForegroundColor White
    Write-Host "  - dashboard.html" -ForegroundColor White
    Write-Host "  - admin-dashboard.html" -ForegroundColor White
    exit 1
} else {
    Write-Host "✅ static/ folder exists" -ForegroundColor Green
    $htmlFiles = Get-ChildItem -Path "static" -Filter "*.html"
    Write-Host "  Found $($htmlFiles.Count) HTML files" -ForegroundColor Gray
}
Write-Host ""

# Clean up
Write-Host "🧹 Cleaning up unnecessary files..." -ForegroundColor Yellow
Remove-Item -Path "*.db" -ErrorAction SilentlyContinue
Remove-Item -Path "*.db-journal" -ErrorAction SilentlyContinue
Remove-Item -Path ".venv" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "venv" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "✅ Cleanup complete" -ForegroundColor Green
Write-Host ""

# Create .gitignore
Write-Host "📝 Creating .gitignore..." -ForegroundColor Yellow
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

# Testing
.pytest_cache/
.coverage
htmlcov/
"@

$gitignore | Out-File -FilePath ".gitignore" -Encoding UTF8
Write-Host "✅ .gitignore created" -ForegroundColor Green
Write-Host ""

# Create Procfile
Write-Host "📝 Creating Procfile..." -ForegroundColor Yellow
"web: uvicorn app:app --host 0.0.0.0 --port `$PORT" | Out-File -FilePath "Procfile" -Encoding ASCII -NoNewline
Write-Host "✅ Procfile created" -ForegroundColor Green
Write-Host ""

# Create railway.json
Write-Host "📝 Creating railway.json..." -ForegroundColor Yellow
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
Write-Host "✅ railway.json created" -ForegroundColor Green
Write-Host ""

# Create runtime.txt
Write-Host "📝 Creating runtime.txt..." -ForegroundColor Yellow
"python-3.11.0" | Out-File -FilePath "runtime.txt" -Encoding ASCII -NoNewline
Write-Host "✅ runtime.txt created" -ForegroundColor Green
Write-Host ""

# Check if .env.example exists, if not create it
if (!(Test-Path ".env.example")) {
    Write-Host "📝 Creating .env.example..." -ForegroundColor Yellow
    $envExample = @"
# MFS Literacy Platform Environment Variables
OPENAI_API_KEY=sk-your-openai-api-key-here
SECRET_KEY=your-secret-key-for-jwt-tokens
"@
    $envExample | Out-File -FilePath ".env.example" -Encoding UTF8
    Write-Host "✅ .env.example created" -ForegroundColor Green
}
Write-Host ""

# Git status before
Write-Host "📊 Current Git Status:" -ForegroundColor Cyan
git status --short
Write-Host ""

# Stage all files
Write-Host "📦 Staging ALL project files..." -ForegroundColor Yellow
git add -A
Write-Host "✅ Files staged" -ForegroundColor Green
Write-Host ""

# Show what will be committed
Write-Host "📋 Files to be committed:" -ForegroundColor Cyan
git status --short
Write-Host ""

# Confirm before committing
Write-Host "⚠️  IMPORTANT: Review the files above" -ForegroundColor Yellow
$proceed = Read-Host "Ready to commit and push to GitHub? (y/n)"

if ($proceed -ne "y") {
    Write-Host "❌ Aborted by user" -ForegroundColor Red
    exit
}
Write-Host ""

# Commit
Write-Host "💾 Creating commit..." -ForegroundColor Yellow
git commit -m "Complete project setup with all files for Railway deployment"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Commit created successfully" -ForegroundColor Green
} else {
    Write-Host "ℹ️  No new changes to commit" -ForegroundColor Blue
}
Write-Host ""

# Push to GitHub
Write-Host "🚀 Pushing to GitHub..." -ForegroundColor Yellow
Write-Host "This may take a moment..." -ForegroundColor Gray
git push origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Successfully pushed to GitHub!" -ForegroundColor Green
} else {
    Write-Host "❌ Push failed!" -ForegroundColor Red
    Write-Host "Please check your internet connection and GitHub authentication" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Verify on GitHub
Write-Host "🔍 Verifying files on GitHub..." -ForegroundColor Yellow
Write-Host "Opening your repository in browser..." -ForegroundColor Gray
Start-Process "https://github.com/sidn405/ai-assessment"
Write-Host ""
Write-Host "Please verify that you see:" -ForegroundColor Cyan
Write-Host "  ✓ app.py" -ForegroundColor White
Write-Host "  ✓ requirements.txt" -ForegroundColor White
Write-Host "  ✓ Procfile" -ForegroundColor White
Write-Host "  ✓ railway.json" -ForegroundColor White
Write-Host "  ✓ static/ folder with HTML files" -ForegroundColor White
Write-Host "  ✓ All .md documentation files" -ForegroundColor White
Write-Host ""

$filesVerified = Read-Host "Can you see all the files on GitHub? (y/n)"

if ($filesVerified -eq "y") {
    Write-Host ""
    Write-Host "🎉 SUCCESS! Your repository is ready!" -ForegroundColor Green
    Write-Host ""
    Write-Host "=" -ForegroundColor Cyan
    Write-Host "🚂 DEPLOY TO RAILWAY NOW:" -ForegroundColor Cyan
    Write-Host "=" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Method 1: Railway Dashboard (RECOMMENDED)" -ForegroundColor Green
    Write-Host "  1. Go to: https://railway.app/new" -ForegroundColor White
    Write-Host "  2. Click 'Deploy from GitHub repo'" -ForegroundColor White
    Write-Host "  3. Select 'sidn405/ai-assessment'" -ForegroundColor White
    Write-Host "  4. Wait for build to complete" -ForegroundColor White
    Write-Host "  5. Add environment variables:" -ForegroundColor White
    Write-Host "     Settings > Variables > Add:" -ForegroundColor Gray
    Write-Host "       OPENAI_API_KEY = your-key-here" -ForegroundColor Yellow
    Write-Host "       SECRET_KEY = (generate below)" -ForegroundColor Yellow
    Write-Host ""
    
    Write-Host "Method 2: Railway CLI" -ForegroundColor Green
    Write-Host "  Run: railway up" -ForegroundColor White
    Write-Host ""
    
    Write-Host "🔑 Generate your SECRET_KEY:" -ForegroundColor Cyan
    Write-Host 'python -c "import secrets; print(secrets.token_hex(32))"' -ForegroundColor White
    Write-Host ""
    
    $openRailway = Read-Host "Open Railway dashboard now? (y/n)"
    if ($openRailway -eq "y") {
        Start-Process "https://railway.app/new"
    }
    
} else {
    Write-Host ""
    Write-Host "⚠️  Files not visible on GitHub yet" -ForegroundColor Yellow
    Write-Host "This might take a few moments to sync. Try:" -ForegroundColor White
    Write-Host "  1. Refresh your GitHub page" -ForegroundColor White
    Write-Host "  2. Check: https://github.com/sidn405/ai-assessment" -ForegroundColor White
    Write-Host "  3. If still missing, run this script again" -ForegroundColor White
}

Write-Host ""
Write-Host "✅ Setup Complete!" -ForegroundColor Green
Write-Host ""