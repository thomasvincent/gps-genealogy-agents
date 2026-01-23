# Troubleshooting Guide

## Common Installation Issues

### RocksDB Installation Failure

**Symptom**: `ImportError: No module named 'rocksdb'`

**Solution**:
- **macOS**: `brew install rocksdb && pip install python-rocksdb`
- **Ubuntu/Debian**: `apt-get install librocksdb-dev && pip install python-rocksdb`
- **Windows**: Use WSL2 or Docker

### Gramps Integration Issues

**Symptom**: `gramps.cli` not found

**Solution**: Install Gramps separately:
```bash
# Ubuntu
sudo apt-get install gramps

# macOS
brew install gramps
```

## Runtime Issues

### LLM API Rate Limits

**Symptom**: `429 Too Many Requests` errors

**Solution**: 
1. Check rate limits in adapter config
2. Increase `rate_limit.requests_per_second` in `.env`
3. Implement exponential backoff

### Memory Issues with Large Crawls

**Symptom**: Process killed or OOM errors

**Solution**:
1. Reduce `max_pages` in source configurations
2. Increase system memory
3. Use pagination for large result sets

### Production Environment Errors

**Symptom**: `RuntimeError: RocksDB is required in production environments`

**Solution**:
This error occurs when the `ENVIRONMENT` variable is set to `production` but RocksDB is not installed.

1. Install RocksDB:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install librocksdb-dev
   pip install python-rocksdb
   
   # macOS
   brew install rocksdb
   pip install python-rocksdb
   ```

2. Or change environment to development for testing:
   ```bash
   export ENVIRONMENT=development
   ```

### Cache Issues

**Symptom**: Stale LLM responses or unexpected behavior

**Solution**:
1. Clear the LLM cache:
   ```bash
   rm -rf .llm_cache/
   ```

2. Set cache directory in environment:
   ```bash
   export CACHE_DIR=/path/to/cache
   ```

## Getting Help

- **GitHub Issues**: https://github.com/thomasvincent/gps-genealogy-agents/issues
- **Discussions**: https://github.com/thomasvincent/gps-genealogy-agents/discussions
