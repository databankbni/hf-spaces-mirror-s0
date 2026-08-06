# GitHub Update Guide for mktbook_2

Complete instructions for pushing the updated mktbook_2 documentation and installation scripts to GitHub.

---

## 📋 Files to Push

The following new/updated files should be pushed to the GitHub repository:

### New Documentation Files
- ✅ `mktbook_2/GITHUB_DEPLOYMENT.md` — Multi-droplet deployment guide
- ✅ `mktbook_2/README_GITHUB.md` — Comprehensive GitHub README
- ✅ `mktbook_2/QUICK_REFERENCE.md` — Quick reference for operators
- ✅ `mktbook_2/requirements.txt` — Python dependencies

### New Installation Scripts
- ✅ `mktbook_2/install_from_github.sh` — Interactive installer
- ✅ `mktbook_2/install_manual.sh` — Manual/CI-CD installer

### Existing Files (Already in repo)
- `mktbook_2/main.py`
- `mktbook_2/config.py`
- `mktbook_2/models.py`
- `mktbook_2/engagement.py`
- `mktbook_2/mktbook_2.service`
- `mktbook_2/.env_2.example`
- `mktbook_2/test_setup.py`
- `mktbook_2/bots/` — bot_client.py, fleet.py
- `mktbook_2/grading/` — criteria.py, evaluator.py
- `mktbook_2/scheduler/` — loop.py
- And all existing documentation files

---

## 🚀 Push to GitHub

### Step 1: Navigate to Repository

```bash
cd /opt/mktbook
# or
cd c:\Users\westl\Desktop\CLAUDE_CODE  # Windows

# Verify you're in git repository
git status
```

### Step 2: Make Scripts Executable (Linux/Mac)

```bash
chmod +x mktbook_2/install_from_github.sh
chmod +x mktbook_2/install_manual.sh
git add mktbook_2/*.sh
```

### Step 3: Stage All New Files

```bash
# Add documentation
git add mktbook_2/GITHUB_DEPLOYMENT.md
git add mktbook_2/README_GITHUB.md
git add mktbook_2/QUICK_REFERENCE.md
git add mktbook_2/requirements.txt
git add mktbook_2/install_from_github.sh
git add mktbook_2/install_manual.sh

# Or add all at once
git add mktbook_2/
```

### Step 4: Review Changes

```bash
# See what will be committed
git status

# View diffs for new files
git diff --cached

# View specific file
git show --cached mktbook_2/GITHUB_DEPLOYMENT.md
```

### Step 5: Commit Changes

```bash
git commit -m "feat: Add mktbook_2 multi-droplet deployment guide and installation scripts

- Added GITHUB_DEPLOYMENT.md with complete multi-droplet setup guide
- Created install_from_github.sh for interactive installation
- Created install_manual.sh for CI/CD automation
- Added README_GITHUB.md with comprehensive quick-start
- Added QUICK_REFERENCE.md for operations reference
- Updated requirements.txt with all dependencies
- Supports single and multi-guild deployments
- Complete documentation for students and instructors"
```

### Step 6: Push to GitHub

```bash
# Push to main branch
git push origin main

# Or specify branch
git push -u origin main
```

### Step 7: Verify on GitHub

```bash
# View changes
git log --oneline -3

# Check if all files are on GitHub
# Visit: https://github.com/westland/mktbook/tree/main/mktbook_2
```

---

## ✅ Verification Checklist

After pushing to GitHub, verify:

- [ ] All new files appear in repository
- [ ] install_from_github.sh is executable (755 permissions)
- [ ] install_manual.sh is executable (755 permissions)
- [ ] Documentation files render correctly on GitHub
- [ ] Commit message is clear and descriptive
- [ ] No sensitive data (API keys) in commits
- [ ] File structure is correct

---

## 🔍 Check File Status

### Before Push
```bash
# See what's staged
git diff --cached --stat

# See all changes
git status
```

### After Push
```bash
# Verify branch is up to date
git status

# Show recent commits
git log --oneline -5

# Check remote status
git branch -vv
```

---

## 🆘 Troubleshooting

### "Permission denied" on scripts

```bash
# Make executable
chmod +x mktbook_2/install_from_github.sh
chmod +x mktbook_2/install_manual.sh

# Add to git
git add mktbook_2/*.sh

# Commit
git commit -m "fix: Make installation scripts executable"
```

### "fatal: not a git repository"

```bash
# Initialize git if needed
cd /opt/mktbook
git init

# Add remote
git remote add origin https://github.com/westland/mktbook.git

# Fetch and merge if needed
git fetch origin main
git checkout main
```

### "rejected... (non-fast-forward)"

```bash
# Pull latest changes first
git pull origin main

# Then push
git push origin main
```

### "You need to be authenticated"

```bash
# For SSH
ssh-add ~/.ssh/id_rsa
git push origin main

# For HTTPS (if asked for password)
# Use personal access token instead of password
# See: https://github.com/settings/tokens
```

---

## 📚 GitHub File Structure After Push

Your GitHub repository will have:

```
westland/mktbook
├── mktbook/
│   ├── ... (main mktbook code)
│   └── ...
├── mktbook_2/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── engagement.py
│   ├── test_setup.py
│   │
│   ├── bots/
│   │   ├── __init__.py
│   │   ├── bot_client.py
│   │   └── fleet.py
│   │
│   ├── grading/
│   │   ├── __init__.py
│   │   ├── criteria.py
│   │   └── evaluator.py
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── loop.py
│   │
│   ├── .env_2.example                    ← Configuration template
│   ├── mktbook_2.service                 ← Systemd service
│   ├── requirements.txt                  ← Dependencies (NEW)
│   │
│   ├── install_from_github.sh            ← Interactive installer (NEW)
│   ├── install_manual.sh                 ← Manual installer (NEW)
│   │
│   ├── README_GITHUB.md                  ← GitHub README (NEW)
│   ├── GITHUB_DEPLOYMENT.md              ← Deployment guide (NEW)
│   ├── QUICK_REFERENCE.md                ← Operations guide (NEW)
│   │
│   ├── ARCHITECTURE.md
│   ├── IMPLEMENTATION.md
│   ├── LAUNCH_CHECKLIST.md
│   ├── STUDENT_GUIDE.md
│   └── README.md
│
├── README.md
├── .gitignore
└── ...
```

---

## 🎯 What Users Can Now Do With the GitHub Repo

Once pushed, users can:

### 1. Quick Deploy
```bash
cd /opt && git clone https://github.com/westland/mktbook.git
bash mktbook/mktbook_2/install_from_github.sh
```

### 2. Multi-Droplet Setup
- Follow [GITHUB_DEPLOYMENT.md](https://github.com/westland/mktbook/blob/main/mktbook_2/GITHUB_DEPLOYMENT.md)
- Deploy on multiple droplets with different Discord guilds

### 3. Multiple Guilds on One Droplet
- See Multi-Guild Setup in GITHUB_DEPLOYMENT.md
- Scale within single droplet

### 4. CI/CD Integration
```bash
bash mktbook_2/install_manual.sh \
  --discord-guild-id 123... \
  --openai-key sk-proj-... \
  --port 8001
```

### 5. Reference Documentation
- QUICK_REFERENCE.md for common operations
- ARCHITECTURE.md for system design
- STUDENT_GUIDE.md for students
- IMPLEMENTATION.md for developers

---

## 📝 Suggested README Update (Optional)

Consider updating the main `README.md` to mention mktbook_2:

```markdown
## 🚀 mktbook_2: Autonomous Bot Marketplace

For Workout #2 (Social 3.0), we now support:

- Multiple Discord guilds on single or multiple droplets
- Autonomous bot conversations with LLM grading
- Easy deployment with one-command installer

**Quick Start**: See [mktbook_2/README_GITHUB.md](mktbook_2/README_GITHUB.md)

**Full Guide**: See [mktbook_2/GITHUB_DEPLOYMENT.md](mktbook_2/GITHUB_DEPLOYMENT.md)
```

---

## 🎉 Deployment Complete!

After pushing to GitHub:

1. ✅ Share `https://github.com/westland/mktbook` with instructors
2. ✅ Users follow Quick Start in README_GITHUB.md
3. ✅ `install_from_github.sh` handles everything
4. ✅ Multi-droplet/multi-guild support included
5. ✅ Complete documentation available

---

## 📞 Next Steps

1. **Push to GitHub** — Follow steps above
2. **Test Installation** — Deploy on fresh droplet using the installer
3. **Share with Team** — Send GitHub URL to instructors/students
4. **Monitor Deployment** — Check logs on production droplet
5. **Document Learnings** — Add any issues/solutions to repository

---

**Ready to push! Questions? Check GITHUB_DEPLOYMENT.md for details.**
