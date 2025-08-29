# SWAG MCP Tool - Comprehensive Test Commands

This document contains a complete list of commands to test every action and parameter that the SWAG MCP tool supports.

## Prerequisites

Before running these tests, ensure:
- SWAG MCP server is running
- You have proper permissions to access SWAG configuration files
- Test domain names are available for health checks
- Backup directory exists for cleanup tests

## 1. LIST Action Commands

### Basic List Commands
```bash
# List all configurations (default)
swag list

# List all configurations explicitly
swag list all

# List only active configurations
swag list active

# List only sample configurations
swag list samples
```

### Edge Cases for List
```bash
# Invalid config type (should fail validation)
swag list invalid

# Empty parameter (should default to "all")
swag list ""
```

## 2. CREATE Action Commands

### Basic Create Commands
```bash
# Minimal create command
swag create jellyfin media.example.com jellyfin 8096

# Create with all default parameters
swag create plex media.example.com plex 32400

# Create with explicit http protocol
swag create sonarr tv.example.com sonarr 8989 http
```

### Create with Different Config Types
```bash
# Subdomain configuration (default)
swag create app1 app1.example.com app1 8080 http subdomain

# Subfolder configuration
swag create app2 example.com app2 8081 http subfolder

# MCP subdomain configuration
swag create app3 app3.example.com app3 8082 http mcp-subdomain

# MCP subfolder configuration
swag create app4 example.com app4 8083 http mcp-subfolder
```

### Create with Different Auth Methods
```bash
# No authentication
swag create public example.com public 8080 http subdomain none

# LDAP authentication
swag create ldap-app ldap.example.com ldap-app 8080 http subdomain ldap

# Authelia authentication (default)
swag create auth-app auth.example.com auth-app 8080 http subdomain authelia

# Authentik authentication
swag create authentik-app authentik.example.com authentik-app 8080 http subdomain authentik

# TinyAuth authentication
swag create tiny-app tiny.example.com tiny-app 8080 http subdomain tinyauth
```

### Create with HTTPS and QUIC
```bash
# HTTPS upstream
swag create secure-app secure.example.com secure-app 8443 https

# Enable QUIC support
swag create quic-app quic.example.com quic-app 8080 http subdomain authelia true

# HTTPS with QUIC
swag create https-quic https-quic.example.com https-quic 8443 https subdomain authelia true
```

### Create Edge Cases and Validation Tests
```bash
# Missing required parameters (should fail)
swag create
swag create onlyname
swag create name domain.com
swag create name domain.com app

# Invalid port numbers (should fail)
swag create test test.example.com test 0
swag create test test.example.com test 65536
swag create test test.example.com test -1

# Invalid service names (should fail)
swag create -invalid invalid.example.com app 8080
swag create invalid- invalid.example.com app 8080
swag create "" invalid.example.com app 8080

# Invalid domain names (should fail)
swag create test invalid..domain app 8080
swag create test .invalid.domain app 8080
swag create test invalid.domain. app 8080

# Invalid upstream app names (should fail)
swag create test test.example.com "" 8080
swag create test test.example.com -invalid 8080
```

## 3. VIEW Action Commands

### Basic View Commands
```bash
# View existing configuration
swag view jellyfin.subdomain.conf

# View configuration without .conf extension
swag view jellyfin.subdomain

# View different config types
swag view app.subfolder.conf
swag view sample.subdomain.conf.sample
```

### View Edge Cases
```bash
# Non-existent configuration (should fail)
swag view nonexistent.subdomain.conf

# Empty config name (should fail)
swag view ""

# Invalid config name patterns
swag view invalid..conf
swag view .invalid.conf
```

## 4. EDIT Action Commands

### Basic Edit Commands
```bash
# Edit with backup (default)
swag edit jellyfin.subdomain.conf "new configuration content"

# Edit without backup
swag edit jellyfin.subdomain.conf "new content" false

# Edit with explicit backup flag
swag edit jellyfin.subdomain.conf "new content" true
```

### Edit Edge Cases
```bash
# Missing required parameters (should fail)
swag edit
swag edit configname
swag edit "" "content"
swag edit "configname" ""

# Non-existent config file (should fail)
swag edit nonexistent.conf "content"
```

## 5. UPDATE Action Commands

### Port Updates
```bash
# Update port with backup (default)
swag update jellyfin.subdomain.conf port 8097

# Update port without backup
swag update jellyfin.subdomain.conf port 8097 false

# Update to different ports
swag update app.subdomain.conf port 80
swag update app.subdomain.conf port 443
swag update app.subdomain.conf port 65535
```

### Upstream Updates
```bash
# Update upstream app name
swag update app.subdomain.conf upstream newapp

# Update upstream with IP address
swag update app.subdomain.conf upstream 192.168.1.100

# Update upstream with complex name
swag update app.subdomain.conf upstream my-complex-app_name
```

### App Updates
```bash
# Update app only
swag update app.subdomain.conf app newapp

# Update app with port combination
swag update app.subdomain.conf app newapp:8080
```

### Update Edge Cases
```bash
# Missing required parameters (should fail)
swag update
swag update configname
swag update configname field
swag update "" field value
swag update configname "" value
swag update configname field ""

# Invalid field names (should fail)
swag update app.conf invalid_field value

# Invalid port values for port updates (should fail)
swag update app.conf port 0
swag update app.conf port 65536
swag update app.conf port -1
swag update app.conf port abc

# Non-existent config file (should fail)
swag update nonexistent.conf port 8080
```

## 6. CONFIG Action Commands

### Basic Config Commands
```bash
# View current configuration defaults
swag config
```

## 7. REMOVE Action Commands

### Basic Remove Commands
```bash
# Remove with backup (default)
swag remove jellyfin.subdomain.conf

# Remove without backup
swag remove jellyfin.subdomain.conf false

# Remove with explicit backup flag
swag remove jellyfin.subdomain.conf true
```

### Remove Edge Cases
```bash
# Missing required parameter (should fail)
swag remove

# Empty config name (should fail)
swag remove ""

# Non-existent config file (should fail)
swag remove nonexistent.conf

# Try to remove sample file (should fail based on validation pattern)
swag remove sample.subdomain.conf.sample
```

## 8. LOGS Action Commands

### Different Log Types
```bash
# Nginx error logs (default)
swag logs

# Nginx access logs
swag logs nginx-access

# Nginx error logs explicitly
swag logs nginx-error

# Fail2ban logs
swag logs fail2ban

# Let's Encrypt logs
swag logs letsencrypt

# Certificate renewal logs
swag logs renewal
```

### Different Line Counts
```bash
# Default line count (50)
swag logs nginx-error

# Minimum lines
swag logs nginx-error 1

# Various line counts
swag logs nginx-error 10
swag logs nginx-error 25
swag logs nginx-error 100
swag logs nginx-error 500

# Maximum lines
swag logs nginx-error 1000
```

### Logs with Different Log Types and Line Counts
```bash
# Access logs with custom line count
swag logs nginx-access 200

# Fail2ban logs with minimal lines
swag logs fail2ban 5

# Let's Encrypt logs with maximum lines
swag logs letsencrypt 1000
```

### Logs Edge Cases
```bash
# Invalid log type (should fail)
swag logs invalid-log

# Invalid line counts (should fail)
swag logs nginx-error 0
swag logs nginx-error 1001
swag logs nginx-error -1
```

## 9. CLEANUP_BACKUPS Action Commands

### Basic Cleanup Commands
```bash
# Cleanup with default retention (uses config default)
swag cleanup_backups

# Cleanup with zero retention (uses config default)
swag cleanup_backups 0

# Cleanup with specific retention periods
swag cleanup_backups 1
swag cleanup_backups 7
swag cleanup_backups 30
swag cleanup_backups 90
swag cleanup_backups 365
```

### Cleanup Edge Cases
```bash
# Very large retention period
swag cleanup_backups 9999

# Negative retention (should fail)
swag cleanup_backups -1
```

## 10. HEALTH_CHECK Action Commands

### Basic Health Check Commands
```bash
# Basic health check with defaults
swag health_check media.example.com

# Health check with custom timeout
swag health_check media.example.com 10

# Health check with custom timeout and redirects
swag health_check media.example.com 15 true

# Health check without following redirects
swag health_check media.example.com 30 false
```

### Health Check with Different Timeouts
```bash
# Minimum timeout
swag health_check example.com 1

# Various timeouts
swag health_check example.com 5
swag health_check example.com 15
swag health_check example.com 60
swag health_check example.com 120

# Maximum timeout
swag health_check example.com 300
```

### Health Check with Different Domains
```bash
# Subdomain health checks
swag health_check app.example.com
swag health_check media.mydomain.org
swag health_check service.local.dev

# IP address health checks (if supported)
swag health_check 192.168.1.100
swag health_check 10.0.0.50
```

### Health Check Edge Cases
```bash
# Missing required parameter (should fail)
swag health_check

# Empty domain (should fail)
swag health_check ""

# Invalid domain formats (should fail)
swag health_check invalid..domain
swag health_check .invalid.domain
swag health_check invalid.domain.

# Invalid timeout values (should fail)
swag health_check example.com 0
swag health_check example.com 301
swag health_check example.com -1
```

## Complex Testing Scenarios

### Full Workflow Tests
```bash
# 1. List existing configs
swag list all

# 2. Create new configuration
swag create testapp test.example.com testapp 8080

# 3. View the created configuration
swag view testapp.subdomain.conf

# 4. Update the port
swag update testapp.subdomain.conf port 8081

# 5. Health check the service
swag health_check test.example.com

# 6. Edit the configuration
swag edit testapp.subdomain.conf "modified content"

# 7. Remove the configuration
swag remove testapp.subdomain.conf

# 8. Cleanup old backups
swag cleanup_backups 7

# 9. Check logs
swag logs nginx-error 100
```

### Validation and Error Testing
```bash
# Test parameter validation
swag create invalid@name invalid.domain app 8080  # Should fail
swag update nonexistent.conf port 8080            # Should fail
swag view missing.conf                             # Should fail
swag health_check invalid..domain                  # Should fail
swag logs invalid-type                             # Should fail
```

## Expected Behaviors

### Success Cases
- Commands with valid parameters should execute successfully
- Backup files should be created when create_backup=true
- Health checks should return status codes and response times
- List commands should return appropriate configuration counts
- Log commands should return the requested number of lines

### Failure Cases
- Missing required parameters should return validation errors
- Invalid parameter values should be rejected
- Non-existent files should return appropriate error messages
- Out-of-range numeric values should be rejected

## Notes

1. **Parameter Order**: Parameters must be provided in the order specified in the function signature
2. **File Extensions**: Configuration names can be provided with or without .conf extension
3. **Backup Behavior**: Backup files are created with timestamps when create_backup=true
4. **Health Checks**: May fail if domains are not properly configured or accessible
5. **Log Types**: Different log types may not exist if corresponding services aren't configured
6. **Retention**: Zero retention days uses the server's default configuration value

## Testing Tips

1. Start with basic commands before testing edge cases
2. Verify prerequisite configurations exist before testing view/edit/remove commands
3. Use non-production domains for health check testing
4. Monitor backup directory growth during testing
5. Check actual log files exist before testing log commands
6. Test parameter validation systematically for each action
