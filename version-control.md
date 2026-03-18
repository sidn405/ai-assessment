# Version Control Guide - Adding Grade Level Feature

## 🎯 Best Approach: Git Branch + Railway Preview Environment

This keeps your production safe while testing the new feature.

---

## Option 1: Feature Branch (Recommended) ⭐

### Step 1: Create Feature Branch

```powershell
# Navigate to project
cd C:\Users\sbsid\source\repos\AI_Assessment

# Make sure you're on main and up to date
git checkout main
git pull origin main

# Create new feature branch
git checkout -b feature/grade-level-registration

# Verify you're on the new branch
git branch
# Should show: * feature/grade-level-registration
```

### Step 2: Make Your Changes

```powershell
# Copy the new register.html
# (to static/register.html)

# Update app.py with the changes
# (UserCreate model + register endpoint)

# Check what you changed
git status
```

### Step 3: Commit to Feature Branch

```powershell
# Add changes
git add static/register.html app.py

# Commit with descriptive message
git commit -m "feat: Add grade level selection to registration

- Add grade level dropdown with 17 options (Pre-K to Professional)
- Auto-map grade to age_band and reading_level
- Update UserCreate model with grade_band and reading_level fields
- Update register endpoint to store new fields
- Add cache-busting headers to registration form

Version: 2.1.0
Previous: 2.0.0"

# Push to Railway
git push origin feature/grade-level-registration
```

### Step 4: Test on Railway Preview Environment

**Railway automatically creates a preview deployment for branches!**

1. Go to Railway Dashboard
2. Click your project
3. You should see a new deployment for `feature/grade-level-registration`
4. Railway will give you a preview URL like:
   ```
   https://ai-assessment-production-9113-feature-grade-level.up.railway.app
   ```

5. Test on this preview URL:
   - Register a new user with grade level
   - Verify it works
   - Check database

### Step 5: Merge to Production (When Ready)

```powershell
# Switch back to main
git checkout main

# Merge the feature branch
git merge feature/grade-level-registration

# Push to production
git push origin main

# Optional: Delete the feature branch
git branch -d feature/grade-level-registration
git push origin --delete feature/grade-level-registration
```

---

## Option 2: Git Tags (Version Releases)

### Tag Current Version First

```powershell
# Tag the current production version
git checkout main
git tag -a v2.0.0 -m "Production version before grade level feature"
git push origin v2.0.0
```

### Make Changes and Tag New Version

```powershell
# Make your changes
# ... (copy files, update code)

# Commit changes
git add .
git commit -m "Add grade level feature - v2.1.0"

# Tag new version
git tag -a v2.1.0 -m "Grade level registration feature
- Added grade level dropdown
- Adaptive learning based on grade
- Auto-mapping to age bands and reading levels"

# Push code and tags
git push origin main
git push origin v2.1.0
```

### Rollback If Needed

```powershell
# If something breaks, rollback to previous version
git checkout v2.0.0

# Or reset main to previous version
git reset --hard v2.0.0
git push origin main --force
```

---

## Option 3: Separate Railway Environment

### Create Staging Environment

1. **In Railway Dashboard:**
   - Click "New Project"
   - Connect same GitHub repo
   - Choose branch: `staging` or `develop`
   - Configure same environment variables
   - Connect a separate PostgreSQL database (for testing)

2. **Create staging branch:**
   ```powershell
   git checkout -b staging
   # Make your changes
   git push origin staging
   ```

3. **Test on staging environment**

4. **When ready, merge to main:**
   ```powershell
   git checkout main
   git merge staging
   git push origin main
   ```

---

## Option 4: Environment Variables for Feature Flags

Add a feature flag to toggle the grade level feature on/off.

### In app.py:

```python
# At the top with other environment variables
ENABLE_GRADE_LEVEL = os.getenv("ENABLE_GRADE_LEVEL", "false").lower() == "true"

# In register endpoint
if ENABLE_GRADE_LEVEL:
    # Use new registration with grade level
    cursor.execute(
        """INSERT INTO users (email, password_hash, full_name, role, age_band, grade_band, reading_level)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (user.email, password_hash.decode('utf-8'), user.full_name, final_role, 
         user.age_band, user.grade_band, user.reading_level)
    )
else:
    # Use old registration without grade level
    cursor.execute(
        """INSERT INTO users (email, password_hash, full_name, role, age_band)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (user.email, password_hash.decode('utf-8'), user.full_name, final_role, user.age_band)
    )
```

**Then in Railway:**
- Set `ENABLE_GRADE_LEVEL=true` when ready to enable
- Set `ENABLE_GRADE_LEVEL=false` to disable instantly

---

## 📝 Version Numbering Convention

Use Semantic Versioning (SemVer): `MAJOR.MINOR.PATCH`

**Current version: 2.0.0**
**New version: 2.1.0** (minor feature addition)

### Version History:
```
v1.0.0 - Initial release with basic literacy platform
v1.5.0 - Added placement tests
v2.0.0 - Phase 2: AI-generated content, adaptive learning
v2.1.0 - Grade level registration (← NEW)
```

### Update version in code:

**Add to app.py:**
```python
# Near the top with other config
APP_VERSION = "2.1.0"

@app.get("/api/version")
async def get_version():
    return {
        "version": APP_VERSION,
        "features": [
            "AI content generation",
            "Adaptive difficulty",
            "Grade-level personalization"
        ],
        "updated": "2025-03-18"
    }
```

---

## 🔄 Recommended Workflow (Production-Safe)

### 1. Create Feature Branch
```powershell
git checkout -b feature/grade-level-registration
```

### 2. Make Changes
```powershell
# Update files
# Test locally if possible
```

### 3. Commit & Push
```powershell
git add .
git commit -m "feat: Add grade level feature v2.1.0"
git push origin feature/grade-level-registration
```

### 4. Test on Railway Preview
- Railway auto-deploys the branch
- Test thoroughly on preview URL
- Fix any bugs on the feature branch

### 5. Tag the Current Production
```powershell
git checkout main
git tag -a v2.0.0 -m "Pre-grade-level version"
git push origin v2.0.0
```

### 6. Merge to Production
```powershell
git checkout main
git merge feature/grade-level-registration
git tag -a v2.1.0 -m "Grade level feature release"
git push origin main
git push origin v2.1.0
```

### 7. Rollback Plan (If Needed)
```powershell
# If v2.1.0 has issues:
git checkout main
git revert HEAD
# Or
git reset --hard v2.0.0
git push origin main --force
```

---

## 🎯 Quick Start: Safest Approach

**Use this exact sequence:**

```powershell
# 1. Save current state
cd C:\Users\sbsid\source\repos\AI_Assessment
git checkout main
git pull origin main
git tag -a v2.0.0 -m "Current production version"
git push origin v2.0.0

# 2. Create feature branch
git checkout -b feature/grade-level-v2.1

# 3. Make changes
# (Copy register.html, update app.py)

# 4. Commit
git add static/register.html app.py
git commit -m "feat: Grade level registration v2.1.0"

# 5. Push for testing
git push origin feature/grade-level-v2.1

# 6. Test on Railway preview URL
# (Railway will auto-create preview deployment)

# 7. When ready for production
git checkout main
git merge feature/grade-level-v2.1
git tag -a v2.1.0 -m "Grade level feature"
git push origin main
git push origin v2.1.0
```

**Benefits:**
- ✅ Production stays safe
- ✅ Can test thoroughly on preview
- ✅ Can rollback instantly if needed
- ✅ Clear version history
- ✅ Professional development workflow

---

## 📊 Railway Branch Deployments

Railway automatically deploys branches! Here's what happens:

**Main branch:**
- `https://ai-assessment-production-9113.up.railway.app`
- Your production site
- Stays untouched while you test

**Feature branch:**
- `https://ai-assessment-production-9113-feature-grade-level.up.railway.app`
- Automatic preview deployment
- Same database (or you can configure separate DB)
- Perfect for testing

**To use separate test database:**
1. Railway Dashboard → Add PostgreSQL
2. Name it "PostgreSQL-Staging"
3. Link to feature branch only
4. Test without affecting production data

---

## 🆘 Emergency Rollback

**If something breaks in production:**

```powershell
# Option 1: Quick revert last commit
git checkout main
git revert HEAD
git push origin main

# Option 2: Reset to previous version
git checkout main
git reset --hard v2.0.0
git push origin main --force

# Option 3: Redeploy old version in Railway
# Railway Dashboard → Deployments → Click v2.0.0 → "Redeploy"
```

---

**Recommended: Use Option 1 (Feature Branch)** - it's the industry standard and Railway supports it perfectly! 🚀