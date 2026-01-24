# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.x.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it by emailing the maintainers directly. Do not open a public GitHub issue for security vulnerabilities.

## Security Considerations

### Credential Storage

**Important:** This application handles sensitive credentials. Follow these guidelines:

1. **Never commit credentials** - All credential files (`credentials.json`, `*_token.json`, etc.) are in `.gitignore`
2. **Use environment variables** - Prefer environment variables over config files:
   ```bash
   export FAMILYSEARCH_USERNAME="your_username"
   export FAMILYSEARCH_PASSWORD="your_password"
   ```
3. **File permissions** - Ensure credential files have restricted permissions:
   ```bash
   chmod 600 data/credentials.json
   chmod 600 data/fs_token.json
   ```

### Gramps Database Security

The Gramps client reads Gramps' native database format which uses serialization:

- **Only use with trusted databases** - Native deserialization can execute arbitrary code
- **Disable in high-security environments** - Set `GRAMPS_DISABLE_NATIVE_DESERIALIZE=1` to reject native-serialized data
- **JSON fallback** - The client attempts JSON parsing first before native format

### OAuth Security

The FamilySearch OAuth implementation:

- Uses `http://localhost` for redirect URI (acceptable per RFC 8252 for loopback)
- Validates redirect URI is localhost-only to prevent open redirect attacks
- Port is configurable via `FAMILYSEARCH_OAUTH_PORT` environment variable

### Input Validation

All user inputs are validated:

- **Search parameters**: Length limits, character validation, year range checks
- **API responses**: Pydantic model validation
- **Shell scripts**: Whitelist-based command validation for git workflows

### Shell Execution

The publishing manager executes shell scripts for git workflows:

- Commands are validated against a whitelist
- Dangerous patterns (pipes, backticks, network commands) are blocked
- Heredoc content is properly handled
- All shell execution is logged for audit

### Logging

The application uses structured logging:

- Passwords and tokens are never logged
- Error messages are sanitized
- Debug logs may contain request/response data (disable in production)

## Security Checklist for Deployment

- [ ] Set restrictive file permissions on `data/` directory
- [ ] Use environment variables for credentials
- [ ] Review `.gitignore` includes all sensitive files
- [ ] Disable debug logging in production
- [ ] Set `GRAMPS_DISABLE_NATIVE_DESERIALIZE=1` if not using Gramps
- [ ] Keep dependencies updated (`uv sync --upgrade`)

## Dependencies

Run regular security audits:

```bash
# Check for known vulnerabilities
uv pip audit
```
