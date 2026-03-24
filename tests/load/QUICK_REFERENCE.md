# Load Test Suite - Quick Reference

## 🚀 Quick Start

```bash
# Install dependencies
make install

# Run quick smoke test (2 min)
make quick

# Run specific scenario
make rampup      # 10 min ramp-up test
make sustained   # 30 min sustained load
make spike       # 10 min spike test
make stress      # 15 min stress test

# Run all scenarios
make all
```

## 📊 Common Commands

### Running Tests

```bash
# Quick test with custom settings
./run_load_test.sh quick --users 100 --time 5m

# Headless mode (no web UI)
./run_load_test.sh rampup --headless

# Custom backend URL
./run_load_test.sh spike --host http://production:9403
```

### Monitoring

```bash
# Real-time performance monitor
make monitor

# Or directly
python monitor_performance.py --interval 2.0
```

### Analysis

```bash
# View latest test results
make reports

# Detailed analysis
python analyze_results.py --detailed

# Generate JSON report
python analyze_results.py --json summary.json
```

### Test Data Management

```bash
# Setup test data
make setup

# Cleanup test data
make cleanup

# Manual setup
python setup_test_data.py --workspaces 5 --projects 10
```

## 🎯 Performance Targets

| Metric | Target | Critical |
|--------|--------|----------|
| RPS | ≥ 1000 | ≥ 500 |
| P95 Latency | < 300ms | < 500ms |
| P99 Latency | < 500ms | < 1000ms |
| Error Rate | < 1% | < 5% |

## 📈 Test Scenarios

| Scenario | Duration | Max Users | Purpose |
|----------|----------|-----------|---------|
| `quick` | 2 min | 50 | Smoke test |
| `rampup` | 10 min | 1000 | Gradual load increase |
| `sustained` | 30 min | 800 | Stability testing |
| `spike` | 10 min | 1500 | Burst resilience |
| `stress` | 15 min | 2500 | Find breaking point |

## 🔧 Distributed Testing

For higher load, run in distributed mode:

```bash
# Terminal 1: Start master
make distributed-master

# Terminal 2-N: Start workers
make distributed-worker
```

## 🐛 Troubleshooting

### Backend not responding
```bash
# Check backend
curl http://127.0.0.1:9403/health

# Restart backend
cd orchestrator/backend
uv run uvicorn main:app --host 127.0.0.1 --port 9403
```

### Connection errors
```bash
# Increase file descriptor limit
ulimit -n 10000
```

### High error rates
1. Check backend logs
2. Monitor database connections
3. Reduce user count
4. Increase timeouts

## 📝 File Structure

```
tests/load/
├── locustfile.py           # Main Locust test definitions
├── run_load_test.sh        # Test runner script
├── scenarios/              # Scenario configurations
│   ├── rampup.json
│   ├── sustained.json
│   ├── spike.json
│   └── stress.json
├── setup_test_data.py      # Test data setup
├── cleanup_test_data.py    # Test data cleanup
├── monitor_performance.py  # Real-time monitor
├── analyze_results.py      # Results analyzer
├── reports/                # Test reports (gitignored)
├── Makefile               # Make targets
└── README.md              # Full documentation
```

## 🎨 Locust Web UI

Access during test execution:
```
http://localhost:8089
```

Features:
- Real-time charts
- Request statistics
- Failure tracking
- User count control

## 📚 Learn More

- Full documentation: [README.md](README.md)
- Locust docs: https://docs.locust.io/
- Project docs: ../../README.md
