#!/usr/bin/env bash
#
# RAPIDS Load Test Runner
# Runs predefined load test scenarios against the orchestrator
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORTS_DIR="${SCRIPT_DIR}/reports"
SCENARIOS_DIR="${SCRIPT_DIR}/scenarios"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create reports directory if it doesn't exist
mkdir -p "${REPORTS_DIR}"

print_banner() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║         RAPIDS Meta-Orchestrator Load Test Runner               ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_usage() {
    cat << EOF
Usage: $0 <scenario> [options]

Scenarios:
  rampup      - Gradual load increase (10 min)
  sustained   - Constant high load (30 min)
  spike       - Sudden traffic spikes (10 min)
  stress      - Push beyond capacity (15 min)
  quick       - Quick smoke test (2 min)
  all         - Run all scenarios sequentially

Options:
  --host URL       Backend URL (default: http://127.0.0.1:9403)
  --users N        Number of users (overrides scenario default)
  --time DURATION  Run time (overrides scenario default)
  --headless       Run without web UI
  --distributed    Run in distributed mode (master)

Examples:
  $0 rampup
  $0 sustained --host http://localhost:9403
  $0 spike --users 2000
  $0 quick --headless

EOF
}

check_dependencies() {
    if ! command -v locust &> /dev/null; then
        echo -e "${RED}Error: Locust is not installed${NC}"
        echo "Install with: pip install locust"
        exit 1
    fi

    if ! command -v uv &> /dev/null; then
        echo -e "${YELLOW}Warning: UV is not installed (recommended)${NC}"
    fi
}

check_backend() {
    local host="$1"
    echo -e "${BLUE}Checking backend availability at ${host}...${NC}"

    if curl -sf "${host}/health" > /dev/null; then
        echo -e "${GREEN}✓ Backend is healthy${NC}"
        return 0
    else
        echo -e "${RED}✗ Backend is not responding at ${host}${NC}"
        echo "Please start the backend first:"
        echo "  cd orchestrator/backend"
        echo "  uv run uvicorn main:app --host 127.0.0.1 --port 9403"
        return 1
    fi
}

run_scenario() {
    local scenario="$1"
    local host="${2:-http://127.0.0.1:9403}"
    local extra_args="${3:-}"

    local scenario_file="${SCENARIOS_DIR}/${scenario}.json"

    if [[ ! -f "${scenario_file}" ]]; then
        echo -e "${RED}Error: Scenario '${scenario}' not found${NC}"
        exit 1
    fi

    echo -e "${BLUE}Running ${scenario} scenario...${NC}"

    # Read scenario configuration
    local users=$(jq -r '.stages[-1].users' "${scenario_file}")
    local spawn_rate=$(jq -r '.stages[-1].spawn_rate' "${scenario_file}")
    local run_time=$(jq -r '.duration_seconds' "${scenario_file}")

    # Convert seconds to Locust time format (e.g., 600s or 10m)
    if [[ ${run_time} -ge 60 ]]; then
        run_time="$((run_time / 60))m"
    else
        run_time="${run_time}s"
    fi

    local report_html="${REPORTS_DIR}/${scenario}_$(date +%Y%m%d_%H%M%S).html"
    local report_csv="${REPORTS_DIR}/${scenario}_$(date +%Y%m%d_%H%M%S)"

    echo -e "${YELLOW}Configuration:${NC}"
    echo "  Users: ${users}"
    echo "  Spawn Rate: ${spawn_rate}/s"
    echo "  Duration: ${run_time}"
    echo "  Report: ${report_html}"
    echo ""

    # Run Locust
    locust -f "${SCRIPT_DIR}/locustfile.py" \
        --host="${host}" \
        --users="${users}" \
        --spawn-rate="${spawn_rate}" \
        --run-time="${run_time}" \
        --html="${report_html}" \
        --csv="${report_csv}" \
        ${extra_args}

    echo -e "${GREEN}✓ Test complete. Report saved to: ${report_html}${NC}"
}

run_quick_test() {
    local host="${1:-http://127.0.0.1:9403}"

    echo -e "${BLUE}Running quick smoke test...${NC}"

    local report_html="${REPORTS_DIR}/quick_$(date +%Y%m%d_%H%M%S).html"

    locust -f "${SCRIPT_DIR}/locustfile.py" \
        --host="${host}" \
        --users=50 \
        --spawn-rate=10 \
        --run-time=2m \
        --html="${report_html}" \
        --headless

    echo -e "${GREEN}✓ Quick test complete${NC}"
}

run_all_scenarios() {
    local host="${1:-http://127.0.0.1:9403}"

    echo -e "${YELLOW}Running all scenarios sequentially...${NC}"

    for scenario in rampup sustained spike stress; do
        run_scenario "${scenario}" "${host}" "--headless"
        echo ""
        echo -e "${BLUE}Waiting 30s before next scenario...${NC}"
        sleep 30
    done

    echo -e "${GREEN}✓ All scenarios complete${NC}"
}

# Main script
main() {
    print_banner

    if [[ $# -eq 0 ]]; then
        print_usage
        exit 1
    fi

    check_dependencies

    local scenario="$1"
    shift

    local host="http://127.0.0.1:9403"
    local extra_args=""

    # Parse options
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --host)
                host="$2"
                shift 2
                ;;
            --users)
                extra_args="${extra_args} --users=$2"
                shift 2
                ;;
            --time)
                extra_args="${extra_args} --run-time=$2"
                shift 2
                ;;
            --headless)
                extra_args="${extra_args} --headless"
                shift
                ;;
            --distributed)
                extra_args="${extra_args} --master"
                shift
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                print_usage
                exit 1
                ;;
        esac
    done

    # Check backend health
    if ! check_backend "${host}"; then
        exit 1
    fi

    # Run the requested scenario
    case "${scenario}" in
        rampup|sustained|spike|stress)
            run_scenario "${scenario}" "${host}" "${extra_args}"
            ;;
        quick)
            run_quick_test "${host}"
            ;;
        all)
            run_all_scenarios "${host}"
            ;;
        *)
            echo -e "${RED}Unknown scenario: ${scenario}${NC}"
            print_usage
            exit 1
            ;;
    esac
}

main "$@"
