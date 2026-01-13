# Security Policy

## Supported Versions

We actively support security updates for the latest version of this project.

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public issue. Instead, please report it via one of the following methods:

1. **Email**: [Your email address]
2. **GitHub Security Advisory**: Use GitHub's private vulnerability reporting feature if available

Please include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond within 48 hours and work with you to address the issue.

## Security Best Practices

### API Key Management

**NEVER commit API keys or secrets to the repository.**

1. **Use Environment Variables**: All API keys must be stored in a `.env` file (which is gitignored)
2. **Use `.env.example`**: Create a template file showing required variables without actual values
3. **Validate Before Committing**: Run `python check_secrets.py` before committing code
4. **Review Pull Requests**: Always check PRs for accidentally committed secrets

### Running Security Checks

Before committing code, run:

```bash
python check_secrets.py
```

This will:
- Verify `.env` is in `.gitignore`
- Scan source files for potential hardcoded secrets
- Validate configuration

### If You Accidentally Commit a Secret

1. **Immediately rotate/revoke the exposed secret**
2. **Remove it from git history**:
   ```bash
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch .env" \
     --prune-empty --tag-name-filter cat -- --all
   ```
3. **Force push** (coordinate with team first!)
4. **Notify team members** to update their local copies

### Pre-commit Hooks

Consider setting up a pre-commit hook to automatically run security checks:

```bash
# Install pre-commit (optional)
pip install pre-commit

# Create .git/hooks/pre-commit
#!/bin/sh
python check_secrets.py
if [ $? -ne 0 ]; then
    echo "Security check failed. Commit aborted."
    exit 1
fi
```

## Security Features

- ✅ Environment variable-based configuration
- ✅ `.env` file excluded from version control
- ✅ Error message sanitization (API keys redacted)
- ✅ Automated secret scanning script
- ✅ Configuration validation

## Known Limitations

- The NYS Senate API requires API keys as URL query parameters, which may appear in server logs
- This is a limitation of the API, not our implementation

## Dependencies

We regularly update dependencies to address security vulnerabilities. Check `requirements.txt` for current versions.
