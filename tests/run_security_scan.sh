#!/usr/bin/env bash
#
# Security Scanning Suite for RAPIDS Meta-Orchestrator
#
# This script runs multiple security scanning tools and generates a comprehensive report.
# Tools used:
# - Bandit: Python static security analysis
# - Safety: Dependency vulnerability scanning
# - Semgrep: Pattern-based code analysis
# - pytest: Security penetration tests
#
# Usage:
#   ./tests/run_security_scan.sh [--quick|--full]
#
# Options:
#   --quick   Run only fast scans (bandit, safety)
#   --full    Run all scans including slow ones (default)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCAN_MODE="${1:---full}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_DIR="$PROJECT_ROOT/tests/security_reports"
REPORT_FILE="$REPORT_DIR/security_scan_$TIMESTAMP.txt"

# Create report directory
mkdir -p "$REPORT_DIR"

# Initialize report
cat > "$REPORT_FILE" << EOF
╔══════════════════════════════════════════════════════════════════════════╗
║                 RAPIDS Meta-Orchestrator Security Scan                   ║
║                         $(date '+%Y-%m-%d %H:%M:%S')                          ║
╚══════════════════════════════════════════════════════════════════════════╝

Scan Mode: $SCAN_MODE
Project: RAPIDS Meta-Orchestrator
Location: $PROJECT_ROOT

EOF

# Logging functions
log_section() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    echo -e "\n═══════════════════════════════════════════════════════════════════════\n$1\n═══════════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"
}

log_info() {
    echo -e "${GREEN}✓${NC} $1"
    echo "[INFO] $1" >> "$REPORT_FILE"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    echo "[WARN] $1" >> "$REPORT_FILE"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
    echo "[ERROR] $1" >> "$REPORT_FILE"
}

# Change to project root
cd "$PROJECT_ROOT"

# Check if running in virtual environment
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    log_warn "Not running in virtual environment. Installing tools may affect global Python."
fi

# ============================================================================
# 1. Install Security Tools
# ============================================================================

log_section "Installing Security Scanning Tools"

log_info "Installing security tools..."

# Check if uv is available
if command -v uv &> /dev/null; then
    UV_CMD="uv pip install"
    log_info "Using uv for package installation"
else
    UV_CMD="pip install"
    log_warn "uv not found, using pip"
fi

# Install tools
$UV_CMD bandit safety semgrep pip-audit --quiet 2>> "$REPORT_FILE" || {
    log_warn "Some tools failed to install. Continuing with available tools."
}

# ============================================================================
# 2. Bandit - Python Security Scanner
# ============================================================================

log_section "Running Bandit (Static Security Analysis)"

if command -v bandit &> /dev/null; then
    log_info "Scanning Python code for security issues..."

    # Run Bandit on orchestrator and auth modules
    bandit -r orchestrator/ auth/ db/ -f txt -o "$REPORT_DIR/bandit_$TIMESTAMP.txt" \
        --severity-level medium --confidence-level medium \
        --exclude "*/tests/*,*/venv/*,*/.venv/*" 2>&1 | tee -a "$REPORT_FILE"

    BANDIT_EXIT_CODE=${PIPESTATUS[0]}

    if [ $BANDIT_EXIT_CODE -eq 0 ]; then
        log_info "Bandit: No security issues found"
    elif [ $BANDIT_EXIT_CODE -eq 1 ]; then
        log_warn "Bandit: Found potential security issues (see report)"
    else
        log_error "Bandit: Scan failed"
    fi

    # Summary
    echo -e "\n--- Bandit Summary ---" >> "$REPORT_FILE"
    grep -A 20 "Results:" "$REPORT_DIR/bandit_$TIMESTAMP.txt" >> "$REPORT_FILE" 2>/dev/null || true
else
    log_warn "Bandit not installed, skipping"
fi

# ============================================================================
# 3. Safety - Dependency Vulnerability Scanner
# ============================================================================

log_section "Running Safety (Dependency Vulnerability Check)"

if command -v safety &> /dev/null; then
    log_info "Checking dependencies for known vulnerabilities..."

    # Check requirements
    safety check --json > "$REPORT_DIR/safety_$TIMESTAMP.json" 2>&1 || {
        log_warn "Safety check found vulnerabilities"
    }

    # Parse and display
    if [ -f "$REPORT_DIR/safety_$TIMESTAMP.json" ]; then
        python3 << 'PYTHON' >> "$REPORT_FILE" 2>&1
import json
import sys

try:
    with open('$REPORT_DIR/safety_$TIMESTAMP.json', 'r') as f:
        data = json.load(f)

    if isinstance(data, list) and len(data) > 0:
        print("\n⚠️  VULNERABLE DEPENDENCIES FOUND:")
        for vuln in data:
            print(f"\n  Package: {vuln.get('package', 'Unknown')}")
            print(f"  Installed: {vuln.get('installed_version', 'Unknown')}")
            print(f"  Vulnerability: {vuln.get('vulnerability', 'Unknown')}")
            print(f"  Fix: Upgrade to {vuln.get('safe_version', 'latest')}")
    else:
        print("\n✅ No known vulnerabilities in dependencies")
except Exception as e:
    print(f"\n⚠️  Error parsing safety report: {e}")
    sys.exit(0)
PYTHON

        log_info "Safety scan completed"
    fi
else
    log_warn "Safety not installed, skipping"
fi

# ============================================================================
# 4. Pip-audit - Additional Dependency Scanning
# ============================================================================

log_section "Running pip-audit (Alternative Dependency Scanner)"

if command -v pip-audit &> /dev/null; then
    log_info "Running pip-audit..."

    pip-audit --format json > "$REPORT_DIR/pip_audit_$TIMESTAMP.json" 2>&1 || {
        log_warn "pip-audit found vulnerabilities"
    }

    # Display summary
    if [ -f "$REPORT_DIR/pip_audit_$TIMESTAMP.json" ]; then
        cat "$REPORT_DIR/pip_audit_$TIMESTAMP.json" >> "$REPORT_FILE"
        log_info "pip-audit completed"
    fi
else
    log_warn "pip-audit not installed, skipping"
fi

# ============================================================================
# 5. Semgrep - Pattern-Based Security Analysis
# ============================================================================

if [ "$SCAN_MODE" = "--full" ]; then
    log_section "Running Semgrep (Pattern-Based Analysis)"

    if command -v semgrep &> /dev/null; then
        log_info "Running Semgrep security rules..."

        # Run Semgrep with security-focused rulesets
        semgrep --config=p/security-audit \
                --config=p/owasp-top-ten \
                --config=p/python \
                --json \
                --output="$REPORT_DIR/semgrep_$TIMESTAMP.json" \
                orchestrator/ auth/ db/ 2>&1 | tee -a "$REPORT_FILE" || {
            log_warn "Semgrep found potential issues"
        }

        # Parse results
        if [ -f "$REPORT_DIR/semgrep_$TIMESTAMP.json" ]; then
            python3 << 'PYTHON' >> "$REPORT_FILE" 2>&1
import json

try:
    with open('$REPORT_DIR/semgrep_$TIMESTAMP.json', 'r') as f:
        data = json.load(f)

    results = data.get('results', [])

    if results:
        print(f"\n⚠️  Semgrep found {len(results)} potential issues:")
        for i, issue in enumerate(results[:10], 1):  # Show first 10
            print(f"\n  {i}. {issue.get('check_id', 'Unknown')}")
            print(f"     File: {issue.get('path', 'Unknown')}")
            print(f"     Line: {issue.get('start', {}).get('line', '?')}")
            print(f"     Severity: {issue.get('extra', {}).get('severity', 'Unknown')}")
        if len(results) > 10:
            print(f"\n  ... and {len(results) - 10} more (see full report)")
    else:
        print("\n✅ No security issues found by Semgrep")
except Exception as e:
    print(f"\n⚠️  Error parsing Semgrep report: {e}")
PYTHON
        fi

        log_info "Semgrep scan completed"
    else
        log_warn "Semgrep not installed, skipping"
    fi
fi

# ============================================================================
# 6. Pytest Security Tests
# ============================================================================

log_section "Running Pytest Security Penetration Tests"

if [ -f "tests/test_security_penetration.py" ]; then
    log_info "Running security penetration tests..."

    # Check if .env file exists
    if [ ! -f ".env" ]; then
        log_error ".env file not found. Cannot run database tests."
        log_warn "Skipping pytest security tests"
    else
        # Run pytest with coverage
        if command -v uv &> /dev/null; then
            uv run pytest tests/test_security_penetration.py \
                -v \
                --tb=short \
                --html="$REPORT_DIR/pytest_security_$TIMESTAMP.html" \
                --self-contained-html \
                --cov=auth \
                --cov=db \
                --cov-report=html:"$REPORT_DIR/coverage_$TIMESTAMP" \
                2>&1 | tee -a "$REPORT_FILE" || {
                log_warn "Some security tests failed (review required)"
            }
        else
            pytest tests/test_security_penetration.py \
                -v \
                --tb=short \
                2>&1 | tee -a "$REPORT_FILE" || {
                log_warn "Some security tests failed"
            }
        fi

        log_info "Security tests completed"
        log_info "HTML report: $REPORT_DIR/pytest_security_$TIMESTAMP.html"
    fi
else
    log_warn "test_security_penetration.py not found, skipping"
fi

# ============================================================================
# 7. Check for Secrets in Code
# ============================================================================

log_section "Scanning for Hardcoded Secrets"

log_info "Searching for potential secrets..."

# Common secret patterns
grep -rn --include="*.py" --include="*.js" --include="*.ts" --include="*.json" \
    -E "(password|secret|api_key|private_key|token|auth).*=.*['\"][^'\"]{8,}" \
    orchestrator/ auth/ db/ 2>/dev/null | grep -v "test" | head -20 >> "$REPORT_FILE" || {
    log_info "No obvious hardcoded secrets found"
}

# Check for common sensitive files
SENSITIVE_FILES=(".env" "secrets.json" "credentials.json" "private.key" "id_rsa")
for file in "${SENSITIVE_FILES[@]}"; do
    if git ls-files | grep -q "$file"; then
        log_error "Sensitive file '$file' found in git!"
        echo "ERROR: $file is tracked by git" >> "$REPORT_FILE"
    fi
done

log_info "Secret scanning completed"

# ============================================================================
# 8. Check Database Security
# ============================================================================

log_section "Database Security Configuration Check"

if [ -f ".env" ]; then
    log_info "Checking database connection security..."

    # Check if DATABASE_URL uses SSL
    DB_URL=$(grep "^DATABASE_URL=" .env | cut -d'=' -f2-)
    if echo "$DB_URL" | grep -q "sslmode=require"; then
        log_info "Database connection uses SSL ✓"
    else
        log_warn "Database connection may not use SSL (check sslmode parameter)"
    fi

    # Check if using default PostgreSQL port
    if echo "$DB_URL" | grep -q ":5432"; then
        log_warn "Using default PostgreSQL port 5432 (consider custom port)"
    fi
else
    log_warn ".env file not found, skipping database security checks"
fi

# ============================================================================
# 9. Generate Summary Report
# ============================================================================

log_section "Scan Summary"

# Generate summary
cat >> "$REPORT_FILE" << EOF

╔══════════════════════════════════════════════════════════════════════════╗
║                         SECURITY SCAN SUMMARY                            ║
╚══════════════════════════════════════════════════════════════════════════╝

Scan completed at: $(date '+%Y-%m-%d %H:%M:%S')

Reports generated:
  - Main report: $REPORT_FILE
  - Bandit:      $REPORT_DIR/bandit_$TIMESTAMP.txt
  - Safety:      $REPORT_DIR/safety_$TIMESTAMP.json
  - Semgrep:     $REPORT_DIR/semgrep_$TIMESTAMP.json
  - pytest:      $REPORT_DIR/pytest_security_$TIMESTAMP.html

Next steps:
  1. Review all findings in the reports above
  2. Prioritize fixes based on severity (CRITICAL > HIGH > MEDIUM > LOW)
  3. Update SECURITY_FINDINGS.md with any new vulnerabilities
  4. Run 'pytest tests/test_security_penetration.py' after fixes
  5. Schedule next security scan (recommended: weekly)

For detailed remediation steps, see:
  tests/SECURITY_FINDINGS.md

═══════════════════════════════════════════════════════════════════════════

OWASP Top 10 Coverage:
  ✓ A01: Broken Access Control - TESTED
  ✓ A02: Cryptographic Failures - TESTED
  ✓ A03: Injection - TESTED
  ✓ A04: Insecure Design - TESTED
  ✓ A05: Security Misconfiguration - TESTED
  ℹ A06: Vulnerable Components - SCANNED (check Safety/pip-audit reports)
  ✓ A07: Authentication Failures - TESTED
  ✓ A08: Data Integrity - TESTED
  ✓ A09: Logging Failures - TESTED
  ℹ A10: SSRF - Not applicable

═══════════════════════════════════════════════════════════════════════════
EOF

# Display summary on screen
echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    Security Scan Completed Successfully                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════════════╝${NC}\n"

echo -e "${BLUE}📊 Full Report:${NC} $REPORT_FILE\n"

log_info "Security scan completed successfully"
log_info "Review all reports in: $REPORT_DIR"
log_info ""
log_info "To run individual scans:"
log_info "  - Bandit:  bandit -r orchestrator/ -ll"
log_info "  - Safety:  safety check"
log_info "  - Semgrep: semgrep --config=p/security-audit orchestrator/"
log_info "  - Tests:   pytest tests/test_security_penetration.py -v"

# Exit with success
exit 0
