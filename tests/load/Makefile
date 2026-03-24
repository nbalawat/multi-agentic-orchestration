# RAPIDS Load Test Suite Makefile

.PHONY: help install quick rampup sustained spike stress all setup cleanup monitor reports clean

BACKEND_URL ?= http://127.0.0.1:9403
REPORTS_DIR = reports

help: ## Show this help message
	@echo "RAPIDS Load Test Suite"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install load testing dependencies
	@echo "📦 Installing dependencies..."
	uv pip install -r requirements.txt
	@echo "✅ Dependencies installed"

check: ## Check if backend is running
	@echo "🔍 Checking backend at $(BACKEND_URL)..."
	@curl -sf $(BACKEND_URL)/health > /dev/null && echo "✅ Backend is healthy" || (echo "❌ Backend is not running" && exit 1)

quick: check ## Run quick smoke test (2 min)
	@echo "🚀 Running quick smoke test..."
	./run_load_test.sh quick --host $(BACKEND_URL)

rampup: check ## Run ramp-up scenario (10 min)
	@echo "🚀 Running ramp-up scenario..."
	./run_load_test.sh rampup --host $(BACKEND_URL)

sustained: check ## Run sustained load scenario (30 min)
	@echo "🚀 Running sustained load scenario..."
	./run_load_test.sh sustained --host $(BACKEND_URL)

spike: check ## Run spike test scenario (10 min)
	@echo "🚀 Running spike test scenario..."
	./run_load_test.sh spike --host $(BACKEND_URL)

stress: check ## Run stress test scenario (15 min)
	@echo "🚀 Running stress test scenario..."
	./run_load_test.sh stress --host $(BACKEND_URL)

all: check ## Run all scenarios sequentially
	@echo "🚀 Running all scenarios..."
	./run_load_test.sh all --host $(BACKEND_URL)

setup: ## Setup test data (workspaces, projects, features)
	@echo "📊 Setting up test data..."
	python setup_test_data.py --host $(BACKEND_URL) --workspaces 5 --projects 10 --features 5

cleanup: ## Cleanup test data
	@echo "🧹 Cleaning up test data..."
	python cleanup_test_data.py --host $(BACKEND_URL) --dry-run
	@read -p "Proceed with deletion? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		python cleanup_test_data.py --host $(BACKEND_URL); \
	fi

monitor: ## Start performance monitor
	@echo "📊 Starting performance monitor..."
	python monitor_performance.py --host $(BACKEND_URL)

reports: ## Open the latest HTML report
	@echo "📈 Opening latest report..."
	@latest=$$(ls -t $(REPORTS_DIR)/*.html 2>/dev/null | head -1); \
	if [ -z "$$latest" ]; then \
		echo "❌ No reports found in $(REPORTS_DIR)"; \
		exit 1; \
	else \
		echo "Opening: $$latest"; \
		open "$$latest" || xdg-open "$$latest" || echo "Please open manually: $$latest"; \
	fi

clean: ## Clean up reports directory
	@echo "🧹 Cleaning reports directory..."
	rm -rf $(REPORTS_DIR)/*
	@echo "✅ Reports cleaned"

# Advanced targets

distributed-master: ## Run Locust master for distributed testing
	@echo "🎛️  Starting Locust master..."
	locust -f locustfile.py --master --host $(BACKEND_URL)

distributed-worker: ## Run Locust worker for distributed testing
	@echo "🔧 Starting Locust worker..."
	locust -f locustfile.py --worker --master-host=127.0.0.1

headless-quick: check ## Run headless quick test
	@echo "🤖 Running headless quick test..."
	locust -f locustfile.py --host $(BACKEND_URL) --users 50 --spawn-rate 10 --run-time 2m --headless --html $(REPORTS_DIR)/headless_quick.html

# Development targets

dev-setup: install setup ## Full development setup (install + test data)
	@echo "✅ Development setup complete"

dev-test: quick ## Quick development test
	@echo "✅ Development test complete"

# CI/CD targets

ci-test: check headless-quick ## CI-friendly test (headless, quick)
	@echo "✅ CI test complete"

ci-full: check ## CI-friendly full test suite (headless)
	@echo "🚀 Running CI full test suite..."
	./run_load_test.sh rampup --host $(BACKEND_URL) --headless
	@echo "⏸️  Waiting 30s..."
	@sleep 30
	./run_load_test.sh spike --host $(BACKEND_URL) --headless
	@echo "✅ CI full test complete"
