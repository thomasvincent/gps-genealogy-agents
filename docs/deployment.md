# Deployment Guide

## Environment Variables

### Required
- `ANTHROPIC_API_KEY`: Claude API key for LLM calls
- `OPENAI_API_KEY`: OpenAI API key (if using GPT-4)

### Optional
- `ENVIRONMENT`: `development` | `production` (default: `development`)
- `LOG_LEVEL`: `DEBUG` | `INFO` | `WARNING` | `ERROR` (default: `INFO`)
- `ROCKSDB_PATH`: Path to RocksDB data directory (default: `./data/rocksdb`)
- `CACHE_DIR`: LLM cache directory (default: `./.llm_cache`)

## Production Deployment

### Using Docker

```bash
# Build image
docker build -t gps-agents:latest .

# Run container
docker run -d \
  -e ENVIRONMENT=production \
  -e ANTHROPIC_API_KEY=your_key_here \
  -v /data/gps-agents:/app/data \
  gps-agents:latest
```

### API Key Management

**DO NOT** store API keys in environment variables in production.

**Recommended**: Use secrets management:

#### AWS Secrets Manager
```python
import boto3
client = boto3.client('secretsmanager')
secret = client.get_secret_value(SecretId='gps-agents/api-keys')
```

#### HashiCorp Vault
```python
import hvac
client = hvac.Client(url='https://vault.example.com')
secret = client.secrets.kv.v2.read_secret_version(path='gps-agents/api-keys')
```

## Monitoring

### Health Checks
- HTTP endpoint: `/health` (if using web service)
- Docker healthcheck: Runs `gps-agents --version`

### Metrics
- Prometheus metrics at `/metrics` (TODO: implement)
- Key metrics: API call rate, cache hit rate, processing time

## Scaling

### Horizontal Scaling
- Use Redis for distributed frontier queue
- PostgreSQL for shared state
- Neo4j cluster for graph storage

### Performance Tuning
- Increase RocksDB cache size
- Enable LLM response caching
- Batch database operations

## Production Checklist

- [ ] RocksDB installed and configured
- [ ] API keys stored in secrets manager
- [ ] Environment variables set correctly
- [ ] Data directories have proper permissions
- [ ] Monitoring and alerting configured
- [ ] Backup strategy in place
- [ ] Rate limiting configured for external APIs
- [ ] Privacy engine enabled for 100-year rule
- [ ] Log aggregation configured
- [ ] Health checks passing

## Security Considerations

### Database Security
- Use strong authentication for database connections
- Encrypt data at rest (RocksDB supports encryption)
- Regular backups of ledger data

### API Security
- Rotate API keys regularly
- Use separate keys for dev/staging/production
- Monitor API usage for anomalies

### Privacy Compliance
- Enable privacy engine for GDPR compliance
- Configure 100-year rule for living persons
- Implement data retention policies

## Troubleshooting

See [Troubleshooting Guide](troubleshooting.md) for common issues and solutions.
