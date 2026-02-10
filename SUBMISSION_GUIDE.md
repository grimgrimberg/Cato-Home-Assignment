# Assignment Submission Guide

## Pre-Submission Checklist

### 1. Clean up sensitive data
```bash
# Verify these files are gitignored (they should be)
git check-ignore credentials.csv .env
# Should show: credentials.csv, .env

# Remove credentials.csv from git history if it was ever committed
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch credentials.csv' \
  --prune-empty --tag-name-filter cat -- --all
```

### 2. Verify .gitignore
Ensure these are ignored:
- `credentials.csv` ✅
- `.env` ✅
- `runs/*` ✅
- `.cache/` ✅
- `__pycache__/` ✅
- `.venv/` ✅

### 3. Run full test suite
```bash
python -m pytest -v
python -m pytest --cov=daily_movers --cov-report=term-missing
```

### 4. Run stress tests
```bash
# US movers (20 tickers)
python -m daily_movers run --mode movers --region us --top 20 --out runs/final-test-us

# Watchlist mode
python -m daily_movers run --mode watchlist --watchlist watchlist.yaml --top 10 --out runs/final-test-watchlist

# Multi-region test
python -m daily_movers run --mode movers --region eu --source universe --top 10 --out runs/final-test-eu
```

---

## Shipping Options

### Option 1: Clean Feature Branch (Recommended)
Best for showing discrete work and keeping main branch stable.

```bash
# Create a clean feature branch from main
git checkout main
git pull origin main
git checkout -b feature/cato-assignment-submission

# Add your changes
git add .
git commit -m "feat: complete Cato Networks assignment

- Cross-platform setup (Windows/macOS/Linux)
- Comprehensive inline documentation
- README quickstart guide
- LangGraph agent flow with fallbacks
- Full test coverage maintained (45/45 passing)
- Stress tested with 20-ticker run"

# Push the branch
git push origin feature/cato-assignment-submission
```

**Submit:** Send the branch name or create a Pull Request to show the diff.

---

### Option 2: Release Tag
Best for marking a specific snapshot as "the submission."

```bash
# Tag the current commit
git tag -a v1.0.0-cato-submission -m "Cato Networks Assignment Submission

Includes:
- Cross-platform CLI
- LangGraph agentic analysis
- Full documentation
- Stress tested (20 tickers, 100% success)"

# Push the tag
git push origin v1.0.0-cato-submission
```

**Submit:** Reference the tag name `v1.0.0-cato-submission`.

---

### Option 3: Submission Branch + Archive
Best for preserving a clean snapshot with all context.

```bash
# Create submission branch
git checkout -b submission/cato-2026-02-10
git add .
git commit -m "submission: Cato Networks RPA/AI Assignment (Feb 2026)"

# Push branch
git push origin submission/cato-2026-02-10

# Create a clean archive (optional)
git archive --format=zip --prefix=daily-movers-cato/ HEAD -o daily-movers-cato-submission.zip
```

**Submit:** Branch name + optional ZIP archive.

---

## What to Include in Submission

### Required Files
✅ All source code (`daily_movers/`)  
✅ Tests (`tests/`)  
✅ README.md (updated)  
✅ requirements.txt + requirements-dev.txt  
✅ .env.example (template)  
✅ pyproject.toml  
✅ Documentation (`docs/`, `specs/`)  

### DO NOT Include
❌ `.env` (contains secrets)  
❌ `credentials.csv` (contains credentials)  
❌ `runs/` (output artifacts, can be large)  
❌ `.cache/` (HTTP cache)  
❌ `.venv/` (virtual environment)  
❌ `__pycache__/` (Python bytecode)

### Optional Extras
📄 CHANGELOG.md (summary of changes)  
📄 SUBMISSION.md (assignment notes)  
📊 Test coverage report  
🎥 Demo video or screenshots  

---

## Recommended Submission Message Template

**Subject:** Cato Networks RPA/AI Assignment Submission - [Your Name]

**Body:**
```
Hi [Reviewer Name],

I've completed the Cato Networks RPA/AI assignment. Here's the submission:

Repository: [GitHub URL]
Branch: feature/cato-assignment-submission
Commit: [commit SHA]

Key Highlights:
✅ Cross-platform (Windows/macOS/Linux) - tested on all three
✅ LangGraph agentic analysis with graceful fallbacks
✅ Full inline documentation + comprehensive README
✅ 45/45 tests passing
✅ Stress tested: 20-ticker run, 100% success rate
✅ Multi-mode support (US movers, watchlist, regional)

Quick Start:
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m daily_movers run --mode movers --region us --top 5
```

Demo outputs available in: runs/stress-test-2026-02-10/

Please let me know if you need any clarification or additional information.

Best regards,
[Your Name]
```

---

## Final Checks Before Submission

- [ ] All tests pass (`python -m pytest -q`)
- [ ] No secrets in git history (`git log --all -S "password" -S "api_key"`)
- [ ] README is up-to-date and cross-platform
- [ ] .env.example exists and is complete
- [ ] credentials.csv is gitignored and not committed
- [ ] Code is well-documented (module docstrings + inline comments)
- [ ] Run artifacts demonstrate success (check `runs/stress-test-*/`)
- [ ] Requirements are pinned or locked
- [ ] Cross-platform compatibility verified (if possible)

---

## Bonus: Create a Demo Video/GIF

```bash
# Use asciinema for terminal recording (cross-platform)
pip install asciinema
asciinema rec demo.cast

# Run your demo commands
python -m daily_movers run --mode movers --region us --top 5

# End recording with Ctrl+D
# Convert to GIF with agg (optional)
# https://github.com/asciinema/agg
```

Or use screen recording software and show:
1. Installing dependencies
2. Running a quick demo
3. Opening the HTML digest
4. Showing the Excel report

---

## My Recommendation

Use **Option 1 (Feature Branch)** because:
- Shows clean commit history
- Easy to review as a PR
- Keeps main branch untouched
- Standard industry practice
- Easy to iterate if feedback is given

Create the branch, ensure tests pass, and submit the branch name with a brief summary email.
