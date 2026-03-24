# Security Testing Quick Reference

**Quick commands for running security tests and scans on the RAPIDS Meta-Orchestrator.**

---

## 🚀 Quick Start

```bash
# Run all security tests (takes ~60 seconds)
uv run pytest tests/test_security_penetration.py -v

# Run automated security scan (takes ~5 minutes)
./tests/run_security_scan.sh
```

---

## 📋 Common Commands

### Run Specific Test Categories

```bash
# Authentication & Authorization
uv run pytest tests/test_security_penetration.py::TestBrokenAccessControl -v

# SQL Injection
uv run pytest tests/test_security_penetration.py::TestInjectionAttacks -v

# Password & Encryption
uv run pytest tests/test_security_penetration.py::TestCryptographicFailures -v

# JWT Token Security
uv run pytest tests/test_security_penetration.py::TestJWTTokenManipulation -v

# Input Validation
uv run pytest tests/test_security_penetration.py::TestInputValidation -v

# Tenant Isolation
uv run pytest tests/test_security_penetration.py::TestTenantIsolation -v
```

### Run with Coverage

```bash
# Generate HTML coverage report
uv run pytest tests/test_security_penetration.py \
  --cov=auth \
  --cov=db \
  --cov-report=html \
  --cov-report=term

# Open coverage report
open htmlcov/index.html
```

### Run Individual Security Scans

```bash
# Static security analysis
bandit -r orchestrator/ auth/ db/ -ll

# Dependency vulnerabilities
safety check

# Pattern-based analysis
semgrep --config=p/security-audit orchestrator/

# CVE database check
pip-audit
```

---

## 🔍 Debugging Failed Tests

```bash
# Run with full traceback
uv run pytest tests/test_security_penetration.py -v --tb=long

# Run single test with debugging
uv run pytest tests/test_security_penetration.py::TestName::test_name -vvs

# Stop on first failure
uv run pytest tests/test_security_penetration.py -x

# Show print statements
uv run pytest tests/test_security_penetration.py -s
```

---

## 📊 View Reports

```bash
# List all security reports
ls -lht tests/security_reports/

# View latest security scan
cat tests/security_reports/security_scan_*.txt | tail -100

# Open pytest HTML report
open tests/security_reports/pytest_security_*.html

# View Bandit results
cat tests/security_reports/bandit_*.txt
```

---

## 🛠️ Before Committing

```bash
# Run quick security checks
bandit -r orchestrator/ auth/ db/ -ll -q
pytest tests/test_security_penetration.py -q --tb=no

# Check for secrets
git diff | grep -iE "(password|secret|api_key|token).*=.*['\"]"
```

---

## 🔧 Environment Setup

```bash
# Ensure .env exists
cp .env.example .env

# Generate JWT secret
echo "JWT_SECRET=$(openssl rand -hex 32)" >> .env

# Verify database connection
psql $DATABASE_URL -c "SELECT 1"
```

---

## 📚 Documentation Links

| Document | Purpose |
|----------|---------|
| `SECURITY_FINDINGS.md` | Detailed vulnerability report with remediation |
| `SECURITY_README.md` | Complete testing guide and best practices |
| `IMPLEMENTATION_SUMMARY.md` | Feature overview and status |
| `test_security_penetration.py` | Source code with inline comments |

---

## 🚨 Critical Findings

**Fix these immediately before production:**

1. **No Rate Limiting** → Implement `slowapi` or `fastapi-limiter`
2. **Weak Password Policy** → Add password complexity validation
3. **Null Byte Input** → Add input validation middleware

See `SECURITY_FINDINGS.md` for full remediation steps.

---

## ✅ Pre-Production Checklist

```bash
# 1. Run all security tests
uv run pytest tests/test_security_penetration.py -v

# 2. Run full security scan
./tests/run_security_scan.sh --full

# 3. Check dependencies
safety check
pip-audit

# 4. Verify environment
grep "JWT_SECRET" .env  # Must be 32+ chars
grep "DEBUG" .env       # Must be false in production

# 5. Review findings
cat SECURITY_FINDINGS.md

# 6. Update dependencies
uv pip list --outdated
```

---

## 📈 CI/CD Integration

**GitHub Actions:**

```yaml
- name: Security Tests
  run: |
    uv run pytest tests/test_security_penetration.py -v
    ./tests/run_security_scan.sh --quick
```

**Pre-commit Hook:**

```bash
# .git/hooks/pre-commit
pytest tests/test_security_penetration.py -q
```

---

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| `Database connection failed` | Check `.env` file and PostgreSQL running |
| `JWT_SECRET not set` | Run `echo "JWT_SECRET=$(openssl rand -hex 32)" >> .env` |
| `Tests are slow` | Run specific test classes instead of all |
| `Import errors` | Run `uv sync` to install dependencies |
| `Permission denied on script` | Run `chmod +x tests/run_security_scan.sh` |

---

## 📞 Quick Help

```bash
# Test help
pytest tests/test_security_penetration.py --help

# Bandit help
bandit --help

# Safety help
safety --help

# View this reference
cat tests/SECURITY_QUICK_REF.md
```

---

**Last Updated:** 2026-03-24
**For detailed documentation, see:** `SECURITY_README.md`
