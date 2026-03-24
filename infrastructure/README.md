# Infrastructure Configuration

This directory contains all infrastructure configuration for deploying the RAPIDS Meta-Orchestrator.

## Directory Structure

```
infrastructure/
├── nginx/                      # Nginx reverse proxy configuration
│   ├── nginx.conf             # Main production config
│   ├── frontend.conf          # Frontend SPA serving config
│   └── ssl/                   # SSL/TLS certificates (not in git)
│
├── prometheus/                 # Prometheus monitoring
│   ├── prometheus.yml         # Prometheus configuration
│   └── alerts/                # Alert rules
│       └── rapids.yml         # RAPIDS alert definitions
│
├── grafana/                    # Grafana dashboards
│   ├── datasources.yml        # Prometheus datasource config
│   ├── dashboards.yml         # Dashboard provisioning
│   └── dashboards/            # Dashboard JSON definitions (to be added)
│
└── scripts/                    # Deployment and maintenance scripts
    ├── deploy.sh              # Main deployment script
    ├── backup.sh              # Database backup script
    └── rollback.sh            # Rollback script
```

## Quick Start

### Deploy to Production

```bash
# Ensure .env.production is configured
./scripts/deploy.sh production
```

### Create Backup

```bash
./scripts/backup.sh
```

### Rollback Deployment

```bash
./scripts/rollback.sh production
```

## Configuration Files

### Nginx

- **`nginx.conf`**: Main reverse proxy configuration
  - Reverse proxy to backend API
  - WebSocket support
  - Rate limiting (10 req/s per IP, 100 req/s global)
  - Static file serving for Vue SPA
  - Grafana/Prometheus proxy routes

- **`frontend.conf`**: Standalone frontend config (for multi-container setup)
  - Serves built Vue 3 SPA
  - SPA routing (all routes → index.html)
  - Asset caching (1 year for static assets)

**TLS Setup:**
```bash
# Generate SSL certificate with Let's Encrypt
sudo certbot certonly --standalone -d yourdomain.com

# Copy to infrastructure/nginx/ssl/
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem infrastructure/nginx/ssl/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem infrastructure/nginx/ssl/

# Uncomment HTTPS server block in nginx.conf
```

### Prometheus

- **`prometheus.yml`**: Main configuration
  - Scrape configs for all services
  - 15-second scrape interval
  - 30-day retention
  - External labels (cluster, environment)

- **`alerts/rapids.yml`**: Alert definitions
  - **Critical**: Error rate > 5%, latency > 2s, DB pool > 90%, disk > 95%, service down
  - **Warning**: Error rate > 1%, latency > 500ms, DB pool > 80%, disk > 90%, high costs

**Adding New Metrics:**
```yaml
# Edit prometheus.yml
scrape_configs:
  - job_name: 'new-service'
    static_configs:
      - targets: ['new-service:9999']
```

### Grafana

- **`datasources.yml`**: Configures Prometheus as default datasource
- **`dashboards.yml`**: Auto-imports dashboards from `dashboards/` directory

**Creating Dashboards:**
1. Access Grafana: `http://localhost/grafana`
2. Create dashboard in UI
3. Export as JSON
4. Save to `infrastructure/grafana/dashboards/`
5. Restart Grafana to auto-import

### Scripts

All scripts are executable (`chmod +x`) and include:
- Input validation
- Pre-flight checks
- Colored output
- Error handling
- Health verification

**deploy.sh**:
- Validates environment config
- Builds frontend
- Pulls Docker images
- Runs migrations
- Deploys services
- Runs health checks

**backup.sh**:
- Creates PostgreSQL dump (compressed)
- Uploads to S3 (if configured)
- Cleans old backups (7 days local, 30 days S3)
- Can run via cron job

**rollback.sh**:
- Three strategies:
  1. Docker image rollback (fastest)
  2. Git commit rollback (medium)
  3. Database restore (slowest, most complete)
- Interactive prompts for safety
- Automatic health verification

## Environment Variables

Required in `.env.production`:

```bash
# Database
POSTGRES_USER=rapids
POSTGRES_PASSWORD=<strong-password>
POSTGRES_DB=rapids_orchestrator

# Application
ANTHROPIC_API_KEY=<api-key>
JWT_SECRET_KEY=<random-secret>
ALLOWED_ORIGINS=https://yourdomain.com

# Monitoring
GRAFANA_ADMIN_PASSWORD=<strong-password>

# Optional: Backups
AWS_ACCESS_KEY_ID=<aws-key>
AWS_SECRET_ACCESS_KEY=<aws-secret>
S3_BACKUP_BUCKET=rapids-backups
```

## Docker Compose

Main compose file: `docker-compose.production.yml` (in project root)

Services:
- **postgres**: PostgreSQL 16 database
- **fastapi-backend**: Python FastAPI application
- **nginx**: Reverse proxy + static files
- **prometheus**: Metrics collection
- **grafana**: Dashboards and visualization
- **postgres-exporter**: PostgreSQL metrics for Prometheus
- **node-exporter**: System metrics (CPU, memory, disk)

**Start all services:**
```bash
docker compose -f docker-compose.production.yml up -d
```

**View logs:**
```bash
docker compose -f docker-compose.production.yml logs -f
```

**Restart a service:**
```bash
docker compose -f docker-compose.production.yml restart <service-name>
```

## Monitoring

### Access Dashboards

- **Grafana**: http://localhost/grafana
  - User: `admin`
  - Password: From `.env.production`

- **Prometheus**: http://localhost/prometheus
  - Query metrics
  - Test alert rules
  - View targets

### Key Metrics

**Application:**
- `http_requests_total` - Request count by endpoint, status
- `http_request_duration_seconds` - Request latency histogram
- `active_agents` - Number of active Claude agents
- `agent_execution_seconds` - Agent execution time
- `ai_tokens_used_total` - AI token consumption

**Database:**
- `db_connection_pool_size` - Connection pool usage
- `pg_stat_database_*` - Database statistics
- `pg_locks_*` - Lock information

**System:**
- `node_cpu_seconds_total` - CPU usage
- `node_memory_*` - Memory metrics
- `node_filesystem_*` - Disk usage
- `node_network_*` - Network I/O

### Alert Channels

Configure in `prometheus/alertmanager.yml` (optional):
- Email via SMTP
- Slack webhooks
- PagerDuty integration

## Security

### Hardening Checklist

- [ ] Strong passwords for all services
- [ ] JWT secret is random and secure
- [ ] HTTPS enabled with valid certificate
- [ ] Firewall allows only ports 22, 80, 443
- [ ] Database port (5432) not exposed externally
- [ ] SSH key-based authentication only
- [ ] Regular security updates
- [ ] Secrets not in git (use .env files)
- [ ] Prometheus/Grafana access restricted

### Firewall (UFW)

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

## Maintenance

### Weekly

```bash
# Security updates
sudo apt update && sudo apt upgrade -y

# Docker cleanup
docker system prune -f

# Review logs
docker compose -f docker-compose.production.yml logs --tail=1000 | grep ERROR
```

### Monthly

```bash
# Test backup restore in staging
./scripts/backup.sh
# Restore in staging environment to verify

# Review and rotate logs
find /var/log -name "*.log" -mtime +30 -delete

# Update Docker images
docker compose -f docker-compose.production.yml pull
docker compose -f docker-compose.production.yml up -d
```

### Quarterly

```bash
# Review and update alert thresholds
# Review security audit logs
# Capacity planning review
# Disaster recovery drill
```

## Troubleshooting

### Service won't start
```bash
docker compose -f docker-compose.production.yml logs <service>
docker compose -f docker-compose.production.yml restart <service>
```

### High memory usage
```bash
docker stats
free -h
# Consider upgrading server or optimizing services
```

### Disk space issues
```bash
df -h
docker system df
docker system prune -a  # Warning: removes all unused images
```

### Database connection errors
```bash
docker exec rapids-postgres pg_isready -U rapids
docker compose -f docker-compose.production.yml restart postgres
```

## Additional Resources

- [Deployment Guide](../.rapids/deploy/deployment.md)
- [CI/CD Pipeline](../.rapids/deploy/pipeline.md)
- [Architecture Documentation](../.rapids/analysis/architecture.md)
- [Project README](../README.md)

## Support

For issues or questions:
- Check logs: `docker compose logs -f`
- Review documentation in `.rapids/deploy/`
- Open GitHub issue
- Contact DevOps team
