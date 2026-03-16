# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take the security of Port Authority seriously. If you discover a security vulnerability, please follow these steps:

### How to Report

1. **Do NOT** open a public issue on GitHub
2. Email security concerns to: your.email@example.com
3. Include the following information:
   - Type of vulnerability
   - Full paths of source file(s) related to the vulnerability
   - Step-by-step instructions to reproduce
   - Proof-of-concept or exploit code (if possible)
   - Impact of the vulnerability

### What to Expect

- **Acknowledgment**: You'll receive an acknowledgment within 48 hours
- **Assessment**: We'll assess the vulnerability and determine its severity
- **Fix**: If confirmed, we'll work on a fix and coordinate disclosure with you
- **Credit**: You'll receive credit for the discovery (unless you prefer to remain anonymous)

### Security Best Practices

When using Port Authority:

1. **Local Development Only**: This tool is designed for local development environments
2. **Database Security**: The SQLite database (`~/.port-authority.db`) contains project metadata
3. **API Security**: The HTTP server (port 7600) binds to localhost only by default
4. **LAN Exposure**: If using the `lan_exposed` flag, ensure your network is trusted

### Scope

Port Authority is a development tool intended to run on local machines. The following are **out of scope**:

- Production deployments
- Cloud-hosted instances
- Attacks requiring physical access
- Social engineering attacks

Thank you for helping keep Port Authority and its users safe!
