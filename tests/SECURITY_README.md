# Security Testing Suite

This directory contains comprehensive security penetration tests and automated security scanning tools for the RAPIDS Meta-Orchestrator project.

## Overview

The security testing suite covers:

- **OWASP Top 10** vulnerabilities (2021 edition)
- **Authentication & Authorization** bypass attempts
- **SQL Injection** and other injection attacks
- **JWT Token Manipulation** and forgery
- **Tenant Isolation** (workspace/user data leakage)
- **Input Validation** and XSS protection
- **Cryptographic Security** (password hashing, token signing)
- **Rate Limiting** and DOS protection
- **Security Headers** and configuration

## Quick Start

### Run All Security Tests

```bash
# From project root
cd /Users/nbalawat/agentic-meta-orchestrator

# Run penetration tests
uv run pytest tests/test_security_penetration.py -v

# Run automated security scans
./tests/run_security_scan.sh
```

### Run Specific Test Categories

```bash
# Test authentication/authorization
uv run pytest tests/test_security_penetration.py::TestBrokenAccessControl -v

# Test SQL injection
uv run pytest tests/test_security_penetration.py::TestInjectionAttacks -v

# Test JWT security
uv run pytest tests/test_security_penetration.py::TestJWTTokenManipulation -v

# Test cryptographic security
uv run pytest tests/test_security_penetration.py::TestCryptographicFailures -v

# Test tenant isolation
uv run pytest tests/test_security_penetration.py::TestTenantIsolation -v
```

## Files in This Directory

```
tests/
├── test_security_penetration.py    # Main security test suite (pytest)
├── SECURITY_FINDINGS.md            # Detailed vulnerability report
├── SECURITY_README.md              # This file
├── run_security_scan.sh            # Automated security scanner
└── security_reports/               # Generated scan reports (gitignored)
    ├── bandit_*.txt
    ├── safety_*.json
    ├── semgrep_*.json
    ├── pytest_security_*.html
    └── security_scan_*.txt
```

## Test Suite Details

### OWASP Top 10 Coverage

| ID  | Category | Test Class | Status |
|-----|----------|------------|--------|
| A01 | Broken Access Control | `TestBrokenAccessControl` | ✅ Complete |
| A02 | Cryptographic Failures | `TestCryptographicFailures` | ✅ Complete |
| A03 | Injection | `TestInjectionAttacks` | ✅ Complete |
| A04 | Insecure Design | `TestInsecureDesign` | ✅ Complete |
| A05 | Security Misconfiguration | `TestSecurityMisconfiguration` | ⚠️ Partial |
| A06 | Vulnerable Components | N/A (use Safety/Bandit) | ℹ️ External |
| A07 | Auth Failures | `TestAuthenticationFailures` | ✅ Complete |
| A08 | Data Integrity | `TestJWTTokenManipulation` | ✅ Complete |
| A09 | Logging Failures | `TestSecurityLogging` | ⚠️ Partial |
| A10 | SSRF | N/A | ℹ️ Not Applicable |

### Test Classes

#### 1. TestBrokenAccessControl
Tests for authorization bypass and privilege escalation:
- Missing authorization headers
- Invalid tokens
- Expired tokens
- Tokens for non-existent users
- Inactive user tokens
- Cross-user access attempts

#### 2. TestCryptographicFailures
Tests for password storage and encryption:
- Password hashing with salt
- Constant-time password verification
- Passwords never in responses
- JWT signature verification
- JWT secret strength
- Token expiration

#### 3. TestInjectionAttacks
Tests for SQL and other injection vulnerabilities:
- SQL injection in login fields
- SQL injection in password fields
- Parameterized query validation
- NoSQL injection in JSONB fields
- Command injection protection

#### 4. TestInsecureDesign
Tests for design flaws:
- Account enumeration protection
- Rate limiting on login
- Password complexity requirements

#### 5. TestSecurityMisconfiguration
Tests for configuration issues:
- Error message leakage
- Debug mode in production
- CORS configuration
- Security headers

#### 6. TestAuthenticationFailures
Tests for session management:
- Session fixation protection
- Concurrent session handling
- Token invalidation on logout
- Token invalidation on password change

#### 7. TestJWTTokenManipulation
Advanced JWT security tests:
- Algorithm confusion attacks
- Missing expiration claims
- Token reuse for different users
- Signature tampering

#### 8. TestTenantIsolation
Multi-tenant security:
- Workspace data isolation
- User data access controls
- Cross-tenant data leakage prevention

#### 9. TestInputValidation
Input sanitization:
- Extremely long inputs
- Special characters
- Unicode attacks
- Null bytes
- Empty credentials

#### 10. TestXSSProtection
XSS and content injection:
- XSS payloads in display names
- HTML injection
- JavaScript injection

#### 11. TestDOSProtection
Denial of service:
- Bcrypt DOS protection
- Parallel request handling
- Resource exhaustion

## Automated Security Scanning

The `run_security_scan.sh` script runs multiple security tools:

### Tools Used

1. **Bandit** - Static security analysis for Python
   - Detects common security issues in code
   - Checks for hardcoded passwords, SQL injection risks, etc.

2. **Safety** - Dependency vulnerability scanner
   - Checks for known vulnerabilities in dependencies
   - Uses PyUp.io vulnerability database

3. **pip-audit** - Alternative dependency scanner
   - Cross-references with CVE database
   - Checks for outdated packages

4. **Semgrep** - Pattern-based code analysis
   - OWASP Top 10 rulesets
   - Python security patterns
   - Custom security rules

5. **pytest** - Dynamic security testing
   - Runs all penetration tests
   - Generates HTML coverage report

### Running Automated Scans

```bash
# Quick scan (Bandit + Safety only)
./tests/run_security_scan.sh --quick

# Full scan (all tools)
./tests/run_security_scan.sh --full
```

### Scan Reports

Reports are saved to `tests/security_reports/` with timestamps:

```
security_reports/
├── security_scan_20260324_143022.txt      # Main report
├── bandit_20260324_143022.txt              # Bandit findings
├── safety_20260324_143022.json             # Dependency vulnerabilities
├── semgrep_20260324_143022.json            # Pattern analysis
├── pip_audit_20260324_143022.json          # CVE checks
├── pytest_security_20260324_143022.html    # Test results (HTML)
└── coverage_20260324_143022/               # Code coverage
```

## CI/CD Integration

### GitHub Actions

Add to `.github/workflows/security.yml`:

```yaml
name: Security Tests

on:
  push:
    branches: [main, develop]
  pull_request:
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday

jobs:
  security-tests:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: uv sync

      - name: Run security tests
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test
          JWT_SECRET: ${{ secrets.JWT_SECRET_TEST }}
        run: |
          uv run pytest tests/test_security_penetration.py -v --tb=short

      - name: Run Bandit
        run: |
          uv pip install bandit
          bandit -r orchestrator/ auth/ db/ -ll

      - name: Check dependencies
        run: |
          uv pip install safety
          safety check --json

      - name: Upload security report
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: security-reports
          path: tests/security_reports/
```

### Pre-commit Hook

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Run quick security scan before commit

echo "🔒 Running security checks..."

# Run Bandit on changed Python files
CHANGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$')

if [ -n "$CHANGED_FILES" ]; then
    echo "$CHANGED_FILES" | xargs bandit -ll -q || {
        echo "❌ Bandit found security issues. Commit aborted."
        exit 1
    }
fi

# Check for secrets
if git diff --cached | grep -iE "(password|secret|api_key|private_key|token).*=.*['\"][^'\"]{8,}"; then
    echo "⚠️  Possible secret detected in staged files!"
    echo "Review carefully before committing."
    read -p "Continue with commit? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "✅ Security checks passed"
```

## Security Testing Best Practices

### 1. Run Tests Regularly

```bash
# Run before every commit
pytest tests/test_security_penetration.py -v

# Run full scan weekly
./tests/run_security_scan.sh --full

# Run in CI/CD pipeline on every PR
```

### 2. Keep Dependencies Updated

```bash
# Check for updates
uv pip list --outdated

# Update dependencies
uv pip install --upgrade-package <package-name>

# Re-run security tests after updates
pytest tests/test_security_penetration.py -v
```

### 3. Review Findings

- All findings are documented in `SECURITY_FINDINGS.md`
- Prioritize by severity: CRITICAL > HIGH > MEDIUM > LOW
- Create tickets for remediation
- Re-test after fixes

### 4. Monitor for New Vulnerabilities

```bash
# Set up automated dependency scanning
safety check --policy-file .safety-policy.json

# Use GitHub Dependabot
# Enable in repository settings

# Use Snyk for continuous monitoring
snyk monitor
```

## Common Issues and Solutions

### Issue: Database Connection Fails

```bash
# Ensure .env file exists
cp .env.example .env

# Update DATABASE_URL
# Check PostgreSQL is running
```

### Issue: JWT_SECRET Not Set

```bash
# Generate strong secret
openssl rand -hex 32

# Add to .env
echo "JWT_SECRET=$(openssl rand -hex 32)" >> .env
```

### Issue: Tests Are Slow

```bash
# Run only specific test classes
pytest tests/test_security_penetration.py::TestBrokenAccessControl -v

# Run in parallel
pytest tests/test_security_penetration.py -n auto
```

### Issue: Rate Limiting Tests Fail

The rate limiting tests will fail if rate limiting is not implemented. This is expected and documented in `SECURITY_FINDINGS.md` as a critical vulnerability to fix.

## Writing New Security Tests

### Example: Testing New Endpoint

```python
class TestNewEndpointSecurity:
    """Security tests for /api/new-endpoint"""

    async def test_requires_authentication(self, client):
        """Endpoint must require valid authentication."""
        resp = await client.get("/api/new-endpoint")
        assert resp.status_code == 401

    async def test_validates_input(self, client, test_user):
        """Endpoint must validate and sanitize input."""
        user, pw = test_user
        token = get_token(client, user.email, pw)

        # Test SQL injection
        resp = await client.post(
            "/api/new-endpoint",
            headers={"Authorization": f"Bearer {token}"},
            json={"param": "' OR '1'='1"}
        )

        # Should return 422 (validation error) or 400 (bad request)
        # NOT 500 (server error) or 200 (success)
        assert resp.status_code in [400, 422]

    async def test_enforces_authorization(self, client, test_user, test_user2):
        """User A must not access User B's resources."""
        user1, pw1 = test_user
        user2, pw2 = test_user2

        token1 = get_token(client, user1.email, pw1)

        # Try to access user2's resource with user1's token
        resp = await client.get(
            f"/api/new-endpoint/{user2.id}",
            headers={"Authorization": f"Bearer {token1}"}
        )

        # Should return 403 (Forbidden) or 404 (Not Found)
        assert resp.status_code in [403, 404]
```

## Resources

### OWASP Resources
- [OWASP Top 10 (2021)](https://owasp.org/Top10/)
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
- [OWASP Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
- [OWASP Cheat Sheets](https://cheatsheetseries.owasp.org/)

### Security Tools
- [Bandit](https://bandit.readthedocs.io/)
- [Safety](https://pyup.io/safety/)
- [Semgrep](https://semgrep.dev/)
- [OWASP ZAP](https://www.zaproxy.org/)
- [Snyk](https://snyk.io/)

### Python Security
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [PyCQA Security Guidelines](https://github.com/PyCQA/bandit)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)

## Contact

For security issues or questions:
- **Email:** security@rapids-meta-orchestrator.com
- **Bug Bounty:** (if applicable)
- **Security Policy:** See SECURITY.md in project root

## License

This security testing suite is part of the RAPIDS Meta-Orchestrator project and follows the same license.

---

**Last Updated:** 2026-03-24
**Next Review:** 2026-06-24 (Quarterly)
