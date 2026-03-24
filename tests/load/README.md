# RAPIDS Meta-Orchestrator Load Test Suite

Comprehensive load and performance testing suite for the RAPIDS Meta-Orchestrator using Locust.

## 🎯 Performance Targets

- **Target RPS**: 1,000 requests/second
- **P95 Latency**: < 300ms
- **P99 Latency**: < 500ms
- **Error Rate**: < 1%

## 📋 Prerequisites

1. **Python 3.12+** with Locust installed
2. **Backend running** at `http://127.0.0.1:9403`
3. **PostgreSQL database** accessible and initialized

### Installation

```bash
# Install Locust and dependencies
uv pip install locust jq

# Or with regular pip
pip install locust
```

## 🚀 Quick Start

### Run a Quick Smoke Test

```bash
./run_load_test.sh quick
```

This runs a 2-minute test with 50 users to verify basic functionality.

### Run a Specific Scenario

```bash
# Ramp-up test (10 minutes)
./run_load_test.sh rampup

# Sustained load test (30 minutes)
./run_load_test.sh sustained

# Spike test (10 minutes)
./run_load_test.sh spike

# Stress test (15 minutes)
./run_load_test.sh stress
```

### Run All Scenarios

```bash
./run_load_test.sh all
```

This runs all scenarios sequentially with 30-second pauses between them.

## 📊 Test Scenarios

### 1. Ramp-Up Scenario (`rampup`)

**Purpose**: Test system behavior under gradually increasing load.

**Duration**: 10 minutes

**Load Profile**:
- Warm-up: 50 users (2 min)
- Ramp to 200 users (3 min)
- Ramp to 500 users (3 min)
- Peak at 1,000 users (2 min)

**Use Case**: Verify the system can handle gradual traffic growth.

### 2. Sustained Load Scenario (`sustained`)

**Purpose**: Test system stability under constant high load.

**Duration**: 30 minutes

**Load Profile**:
- Ramp-up to 100 users (2 min)
- Sustained 800 users (26 min)

**Use Case**: Detect memory leaks, connection pool exhaustion, and resource degradation over time.

### 3. Spike Test Scenario (`spike`)

**Purpose**: Test system resilience during sudden traffic spikes.

**Duration**: 10 minutes

**Load Profile**:
- Baseline: 100 users (2 min)
- **SPIKE**: Jump to 1,500 users in 1 minute
- Hold spike: 1,500 users (3 min)
- Drop back to baseline (1 min)
- Recovery: 100 users (3 min)

**Use Case**: Verify the system can handle sudden traffic bursts and recover gracefully.

### 4. Stress Test Scenario (`stress`)

**Purpose**: Find the breaking point of the system.

**Duration**: 15 minutes

**Load Profile**:
- Baseline: 200 users (2 min)
- Normal peak: 1,000 users (3 min)
- Stress level 1: 1,500 users (3 min)
- Stress level 2: 2,000 users (3 min)
- Maximum stress: 2,500 users (4 min)

**Use Case**: Identify system limits and failure modes.

## 🎭 User Types

The load tests simulate three different user types with different behaviors:

### ReadOnlyUser (70% of traffic)

**Characteristics**:
- High frequency (0.1-0.5s wait time)
- Read-only operations
- Simulates dashboards and monitoring tools

**Operations**:
- Health checks
- Get orchestrator status
- List agents
- Get events
- Project dashboard queries

### MixedUser (20% of traffic)

**Characteristics**:
- Medium frequency (0.5-2.0s wait time)
- Mix of read and write operations
- Simulates normal user activity

**Operations**:
- All read operations
- Workspace operations
- Project queries

### HeavyUser (10% of traffic)

**Characteristics**:
- Lower frequency (1.0-3.0s wait time)
- Resource-intensive operations
- Simulates power users

**Operations**:
- Workspace creation
- Project onboarding
- Feature DAG operations

## 📈 Monitoring and Reports

### Real-Time Monitoring

During test execution, access the Locust Web UI:

```
http://localhost:8089
```

The UI provides:
- Real-time RPS and response time charts
- Request statistics by endpoint
- Error rates and failure reasons
- Current user count

### HTML Reports

After each test run, an HTML report is generated in the `reports/` directory:

```
reports/
├── rampup_20260324_143022.html
├── sustained_20260324_150045.html
├── spike_20260324_153512.html
└── stress_20260324_160234.html
```

### CSV Reports

Raw data is exported to CSV files for custom analysis:

```
reports/
├── rampup_20260324_143022_stats.csv
├── rampup_20260324_143022_stats_history.csv
├── rampup_20260324_143022_failures.csv
└── ...
```

## 🔧 Advanced Usage

### Custom Configuration

```bash
# Override number of users
./run_load_test.sh rampup --users 2000

# Override duration
./run_load_test.sh sustained --time 60m

# Change backend URL
./run_load_test.sh spike --host http://production.example.com:9403

# Run headless (no web UI)
./run_load_test.sh rampup --headless
```

### Distributed Load Testing

For higher load, run Locust in distributed mode:

**Terminal 1 (Master)**:
```bash
locust -f locustfile.py --master --host http://127.0.0.1:9403
```

**Terminal 2-N (Workers)**:
```bash
locust -f locustfile.py --worker --master-host=127.0.0.1
```

### Manual Locust Execution

```bash
# Interactive mode with Web UI
locust -f locustfile.py --host http://127.0.0.1:9403

# Headless mode
locust -f locustfile.py \
  --host http://127.0.0.1:9403 \
  --users 1000 \
  --spawn-rate 50 \
  --run-time 10m \
  --headless \
  --html reports/custom_report.html
```

## 📊 Key Metrics to Monitor

### Application Metrics

- **Response Time**:
  - P50 (median)
  - P95 (95th percentile) - **Target: < 300ms**
  - P99 (99th percentile) - **Target: < 500ms**

- **Throughput**:
  - Requests per second (RPS) - **Target: >= 1000**
  - Requests per endpoint

- **Error Rate**:
  - Total error percentage - **Target: < 1%**
  - Errors by endpoint
  - Error types (timeouts, 5xx, connection errors)

### System Metrics

Monitor these on the backend server during load tests:

- **CPU Usage**: Should stay below 80%
- **Memory Usage**: Monitor for leaks
- **Database Connections**: Check pool utilization
- **WebSocket Connections**: Monitor connection stability

### Database Metrics

- **Connection Pool**: Utilization and wait times
- **Query Performance**: Slow query log
- **Lock Contention**: Table locks and deadlocks

## 🐛 Troubleshooting

### Backend Not Responding

```bash
# Check if backend is running
curl http://127.0.0.1:9403/health

# Start backend if needed
cd orchestrator/backend
uv run uvicorn main:app --host 127.0.0.1 --port 9403
```

### High Error Rates

1. **Check backend logs**: Look for exceptions and errors
2. **Monitor database**: Check for connection pool exhaustion
3. **Reduce load**: Lower user count to find stable threshold
4. **Check timeouts**: Increase timeout settings if needed

### Connection Errors

```bash
# Check system limits
ulimit -n  # Should be at least 10000

# Increase if needed
ulimit -n 10000
```

### Memory Issues

```bash
# Monitor backend memory
ps aux | grep uvicorn

# Check for memory leaks in test logs
grep -i "memory" reports/*.csv
```

## 📝 Test Data Management

### Setup Test Data

Before running extensive load tests, pre-populate the database:

```python
# Create test workspaces and projects
python scripts/setup_test_data.py --workspaces 10 --projects 50
```

### Cleanup Test Data

After load testing:

```python
# Clean up test data
python scripts/cleanup_test_data.py --prefix "load_test_"
```

## 🎯 Performance Tuning Tips

### Database Optimization

```sql
-- Increase connection pool size
ALTER SYSTEM SET max_connections = 200;

-- Enable query caching
ALTER SYSTEM SET shared_buffers = '256MB';

-- Analyze tables
ANALYZE orchestrator_agents;
ANALYZE workspace_projects;
```

### Backend Optimization

```python
# In main.py, increase connection pool
await database.init_pool(
    database_url=config.DATABASE_URL,
    min_size=10,
    max_size=100
)
```

### System Optimization

```bash
# Increase file descriptor limit
echo "* soft nofile 65536" >> /etc/security/limits.conf
echo "* hard nofile 65536" >> /etc/security/limits.conf

# Increase TCP connection limit
sysctl -w net.core.somaxconn=1024
sysctl -w net.ipv4.tcp_max_syn_backlog=1024
```

## 📚 Additional Resources

- [Locust Documentation](https://docs.locust.io/)
- [Performance Testing Best Practices](https://docs.locust.io/en/stable/running-distributed.html)
- [HTTP Load Testing Guide](https://www.blazemeter.com/blog/jmeter-vs-locust)

## 🤝 Contributing

To add new test scenarios:

1. Create a new scenario JSON file in `scenarios/`
2. Update the `run_load_test.sh` script
3. Document the scenario in this README
4. Test the scenario locally

## 📄 License

Private — All rights reserved.
