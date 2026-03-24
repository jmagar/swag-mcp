# MCP OAuth Gateway for SWAG MCP — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the `mcp-oauth-dynamicclient` auth service behind SWAG (replacing Traefik) to provide OAuth 2.1 authentication for the SWAG MCP server at `swag.tootie.tv`.

**Architecture:** The auth service (`mcp-oauth-dynamicclient`) runs as a standalone FastAPI container with its own Redis instance, all on the `jakenet` Docker network. SWAG handles TLS termination and routing. The auth service lives at `mcp-auth.tootie.tv` and provides OAuth 2.1 endpoints (RFC 7591 dynamic client registration, PKCE, GitHub login). SWAG MCP at `swag.tootie.tv` gets an `auth_request` directive that validates Bearer tokens against the auth service's `/verify` endpoint before allowing access to `/mcp`.

**Tech Stack:** mcp-oauth-dynamicclient (FastAPI/Authlib/PyJWT), Redis 7 Alpine, SWAG nginx, Docker Compose

---

## Current State

- **SWAG MCP** runs at `swag.tootie.tv` → `100.75.111.118:8012` (container `swag-mcp`)
- **SWAG** runs on `jakenet` at `10.6.0.100`, owns ports 80/443
- **Authelia** runs at `auth.tootie.tv` → `100.75.111.118:9091` (so we use `mcp-auth.tootie.tv` for the OAuth service)
- **jakenet** is the shared Docker network (10.6.0.0/16)
- The OAuth gateway repo is cloned at `/mnt/compose/mcp-oauth-gateway/` with submodule `mcp-oauth-dynamicclient` initialized
- GitHub OAuth App: Client ID `Ov23li8LttLMCh1kQgQM`, allowed user `jmagar`

## Key Decisions

1. **No Traefik** — SWAG handles all routing/TLS
2. **Dedicated Redis** — New `mcp-oauth-redis` container (not sharing authelia-redis)
3. **Subdomain** — `mcp-auth.tootie.tv` for the OAuth service
4. **Network** — Containers join `jakenet` so SWAG can reach them
5. **CORS** — Must be handled in the auth service itself (not Traefik), since SWAG doesn't have Traefik's CORS middleware. We add `CORSMiddleware` to the FastAPI app.

---

### Task 1: Create GitHub OAuth App Callback URL

**Files:** None (GitHub web UI)

**Step 1: Verify/update GitHub OAuth App**

Go to https://github.com/settings/developers and ensure the OAuth App has:
- **Homepage URL:** `https://mcp-auth.tootie.tv`
- **Authorization callback URL:** `https://mcp-auth.tootie.tv/callback`

If the app was created for a different domain, update it now. The callback URL is critical — GitHub redirects here after user authorization.

**Step 2: Confirm**

Verify the Client ID matches: `Ov23li8LttLMCh1kQgQM`

---

### Task 2: Generate Secrets and Create `.env` File

**Files:**
- Create: `/mnt/compose/mcp-oauth-gateway/.env`

**Step 1: Generate JWT secret (32+ chars)**

```bash
openssl rand -hex 32
```

Save the output — this becomes `GATEWAY_JWT_SECRET`.

**Step 2: Generate RSA key pair for RS256 JWT signing**

```bash
openssl genrsa 2048 | base64 -w 0
```

Save the output — this becomes `JWT_PRIVATE_KEY_B64`.

**Step 3: Generate Redis password**

```bash
openssl rand -hex 24
```

Save the output — this becomes `REDIS_PASSWORD`.

**Step 4: Write the `.env` file**

```bash
# /mnt/compose/mcp-oauth-gateway/.env

# Domain
BASE_DOMAIN=tootie.tv
ACME_EMAIL=jmagar@gmail.com

# GitHub OAuth
GITHUB_CLIENT_ID=Ov23li8LttLMCh1kQgQM
GITHUB_CLIENT_SECRET=4c343ecd9d93baad9992f3fb2d955a4486351b3e

# JWT
GATEWAY_JWT_SECRET=<generated-hex-32>
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY_B64=<generated-base64-rsa-key>

# Redis
REDIS_PASSWORD=<generated-hex-24>
REDIS_URL=redis://:${REDIS_PASSWORD}@mcp-oauth-redis:6379/0

# Access Control
ALLOWED_GITHUB_USERS=jmagar

# Token Lifetimes
ACCESS_TOKEN_LIFETIME=86400
REFRESH_TOKEN_LIFETIME=2592000
SESSION_TIMEOUT=3600
CLIENT_LIFETIME=7776000

# MCP Protocol
MCP_PROTOCOL_VERSION=2025-06-18
MCP_CORS_ORIGINS=https://swag.tootie.tv,https://mcp-auth.tootie.tv,https://claude.ai
```

**Step 5: Verify no secrets in git**

```bash
cd /mnt/compose/mcp-oauth-gateway && grep -r "4c343ecd" . --include="*.yml" --include="*.yaml" --include="*.md" | grep -v .env
```

Expected: no output (secrets only in `.env`)

---

### Task 3: Create Standalone Docker Compose (No Traefik)

**Files:**
- Create: `/mnt/compose/mcp-oauth-gateway/docker-compose.swag.yml`

This replaces the original `docker-compose.yml` which includes Traefik. We only need `auth` + `redis`.

**Step 1: Write the compose file**

```yaml
# /mnt/compose/mcp-oauth-gateway/docker-compose.swag.yml
# MCP OAuth Gateway — SWAG Edition (no Traefik)
# Auth service + Redis only, routed through SWAG

services:
  mcp-oauth-auth:
    build:
      context: .
      dockerfile: auth/Dockerfile
    container_name: mcp-oauth-auth
    restart: unless-stopped
    networks:
      jakenet:
    volumes:
      - ./logs/auth:/logs
    environment:
      - LOG_FILE=/logs/auth.log
      - GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID}
      - GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET}
      - JWT_SECRET=${GATEWAY_JWT_SECRET}
      - JWT_ALGORITHM=${JWT_ALGORITHM}
      - JWT_PRIVATE_KEY_B64=${JWT_PRIVATE_KEY_B64}
      - BASE_DOMAIN=${BASE_DOMAIN}
      - REDIS_URL=redis://:${REDIS_PASSWORD}@mcp-oauth-redis:6379/0
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - ACCESS_TOKEN_LIFETIME=${ACCESS_TOKEN_LIFETIME}
      - REFRESH_TOKEN_LIFETIME=${REFRESH_TOKEN_LIFETIME}
      - SESSION_TIMEOUT=${SESSION_TIMEOUT}
      - CLIENT_LIFETIME=${CLIENT_LIFETIME}
      - ALLOWED_GITHUB_USERS=${ALLOWED_GITHUB_USERS}
      - MCP_PROTOCOL_VERSION=${MCP_PROTOCOL_VERSION}
      - MCP_CORS_ORIGINS=${MCP_CORS_ORIGINS}
    depends_on:
      mcp-oauth-redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "-s", "http://localhost:8000/.well-known/oauth-authorization-server"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  mcp-oauth-redis:
    image: redis:7-alpine
    container_name: mcp-oauth-redis
    restart: unless-stopped
    networks:
      jakenet:
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --save 60 1
      --save 300 10
      --save 900 100
      --appendonly yes
    volumes:
      - mcp-oauth-redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "--no-auth-warning", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

networks:
  jakenet:
    external: true

volumes:
  mcp-oauth-redis-data:
```

**Step 2: Verify the build context**

```bash
ls /mnt/compose/mcp-oauth-gateway/auth/Dockerfile
ls /mnt/compose/mcp-oauth-gateway/mcp-oauth-dynamicclient/src/mcp_oauth_dynamicclient/
```

Expected: both paths exist

**Step 3: Commit compose file**

```bash
cd /mnt/compose/mcp-oauth-gateway
git add docker-compose.swag.yml
git commit -m "feat: add SWAG-compatible compose (no Traefik)"
```

---

### Task 4: Add CORS Middleware to Auth Service

**Files:**
- Modify: `/mnt/compose/mcp-oauth-gateway/mcp-oauth-dynamicclient/src/mcp_oauth_dynamicclient/server.py`

The original auth service relies on Traefik for CORS. Since we're using SWAG, we need CORS in the app itself.

**Step 1: Add CORSMiddleware import and configuration**

In `server.py`, after the line `# CORS is handled by Traefik middleware - no need to configure here` (line ~279), replace with:

```python
    # CORS configuration - required when not behind Traefik
    import os
    cors_origins_str = os.environ.get("MCP_CORS_ORIGINS", "*")
    cors_origins = [o.strip() for o in cors_origins_str.split(",")]

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "MCP-Protocol-Version", "Mcp-Session-Id", "Last-Event-ID"],
        expose_headers=["MCP-Protocol-Version", "Mcp-Session-Id"],
    )
```

**Step 2: Build and verify**

```bash
cd /mnt/compose/mcp-oauth-gateway
docker compose -f docker-compose.swag.yml build mcp-oauth-auth
```

Expected: successful build

---

### Task 5: Build and Start the Auth Stack

**Files:** None (Docker operations)

**Step 1: Create log directory**

```bash
mkdir -p /mnt/compose/mcp-oauth-gateway/logs/auth
```

**Step 2: Start the stack**

```bash
cd /mnt/compose/mcp-oauth-gateway
docker compose -f docker-compose.swag.yml up -d
```

**Step 3: Verify containers are running and healthy**

```bash
docker ps --filter name=mcp-oauth --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected: both `mcp-oauth-auth` and `mcp-oauth-redis` running, auth showing healthy

**Step 4: Test the auth service directly**

```bash
# Get the container IP on jakenet
docker inspect mcp-oauth-auth --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'

# Hit the well-known endpoint
curl -s http://<container-ip>:8000/.well-known/oauth-authorization-server | python3 -m json.tool
```

Expected: JSON response with OAuth metadata including issuer, authorization_endpoint, token_endpoint, etc.

**Step 5: Verify the /verify endpoint exists**

```bash
curl -s -o /dev/null -w "%{http_code}" http://<container-ip>:8000/verify
```

Expected: 401 (no token provided, but endpoint exists)

---

### Task 6: Create SWAG Proxy Config for mcp-auth.tootie.tv

**Files:**
- Create: `/mnt/appdata/swag/nginx/proxy-confs/mcp-auth.subdomain.conf`

This routes all OAuth traffic to the auth service container.

**Step 1: Write the nginx config**

```nginx
## MCP OAuth Gateway Auth Service
# OAuth 2.1 Authorization Server for MCP services
# Service: mcp-oauth-auth
# Domain: mcp-auth.tootie.tv

server {
    listen 443 ssl;
    listen [::]:443 ssl;

    server_name mcp-auth.tootie.tv;

    include /config/nginx/ssl.conf;

    client_max_body_size 0;

    # Upstream: mcp-oauth-auth container on jakenet
    set $upstream_app mcp-oauth-auth;
    set $upstream_port 8000;
    set $upstream_proto http;

    # OAuth endpoints (public, no auth required)
    # /register - RFC 7591 Dynamic Client Registration
    # /authorize - OAuth 2.1 Authorization
    # /token - Token exchange
    # /callback - GitHub OAuth callback
    # /revoke - Token revocation
    # /verify - Token verification (used by nginx auth_request)
    # /.well-known/* - OAuth/OIDC discovery

    location / {
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;

        # Pass all OAuth-relevant headers
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    # Health check
    location /health {
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;

        proxy_connect_timeout 5s;
        proxy_send_timeout 10s;
        proxy_read_timeout 10s;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }
}
```

**Step 2: Verify SWAG can resolve the container**

```bash
docker exec swag ping -c 1 mcp-oauth-auth
```

Expected: successful ping (both on jakenet)

NOTE: If SWAG can't resolve `mcp-oauth-auth` by container name, use the jakenet IP address instead. Get it with:
```bash
docker inspect mcp-oauth-auth --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```

**Step 3: Reload SWAG nginx**

```bash
docker exec swag nginx -t && docker exec swag nginx -s reload
```

Expected: `nginx: configuration file /etc/nginx/nginx.conf test is successful`

**Step 4: Test external access**

```bash
curl -s https://mcp-auth.tootie.tv/.well-known/oauth-authorization-server | python3 -m json.tool
```

Expected: OAuth metadata JSON with correct issuer URL

---

### Task 7: Update swag.tootie.tv Config with OAuth Token Validation

**Files:**
- Modify: `/mnt/appdata/swag/nginx/proxy-confs/swag-mcp.subdomain.conf`

Add `auth_request` to the `/mcp` location block so that Bearer tokens are validated against the auth service before requests reach SWAG MCP.

**Step 1: Add auth_request internal location**

Add this block before the `location /mcp` block (after the security headers, around line 43):

```nginx
    # OAuth 2.1 token verification via mcp-oauth-auth service
    # This is the nginx equivalent of Traefik's ForwardAuth
    location = /_oauth_verify {
        internal;
        include /config/nginx/resolver.conf;

        proxy_pass http://mcp-oauth-auth:8000/verify;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Original-URI $request_uri;
        proxy_set_header X-Original-Method $request_method;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization $http_authorization;
    }
```

**Step 2: Add auth_request directive to /mcp location**

Inside `location /mcp {`, right after the origin validation block and before the resolver include (around line 66), add:

```nginx
        # OAuth 2.1 Bearer token validation
        auth_request /_oauth_verify;
        auth_request_set $auth_status $upstream_status;
```

**Step 3: Keep OAuth endpoints unprotected**

The existing `/.well-known/*`, `/register`, `/authorize`, `/token`, `/revoke` locations should remain WITHOUT `auth_request` — they are public OAuth flow endpoints.

**Step 4: Test nginx config**

```bash
docker exec swag nginx -t
```

Expected: successful

**Step 5: Reload SWAG**

```bash
docker exec swag nginx -s reload
```

**Step 6: Verify unauthenticated /mcp returns 401**

```bash
curl -s -o /dev/null -w "%{http_code}" https://swag.tootie.tv/mcp
```

Expected: 401 (no Bearer token)

**Step 7: Verify health endpoint still works (no auth)**

```bash
curl -s https://swag.tootie.tv/health
```

Expected: 200 with health status

---

### Task 8: Update SWAG MCP OAuth Metadata Endpoints

**Files:**
- Modify: `/mnt/appdata/swag/nginx/proxy-confs/swag-mcp.subdomain.conf`

The `.well-known/oauth-protected-resource` endpoint on swag.tootie.tv must point clients to the auth server. Currently it proxies to the SWAG MCP backend (which doesn't implement OAuth). We need it to either:
- (A) Return a static JSON response from nginx, or
- (B) Proxy to the auth service

Option A is simpler and spec-compliant:

**Step 1: Replace the `/.well-known/oauth-protected-resource` location**

```nginx
    # MCP 2025-06-18: OAuth Protected Resource Metadata (RFC 9728)
    # Points clients to the authorization server at mcp-auth.tootie.tv
    location = /.well-known/oauth-protected-resource {
        default_type application/json;
        add_header Cache-Control "public, max-age=3600" always;
        add_header Access-Control-Allow-Origin $http_origin always;
        add_header Access-Control-Allow-Methods "GET, OPTIONS" always;
        return 200 '{
            "resource": "https://swag.tootie.tv",
            "authorization_servers": ["https://mcp-auth.tootie.tv"],
            "scopes_supported": ["mcp:read", "mcp:write"],
            "bearer_methods_supported": ["header"]
        }';
    }
```

**Step 2: Update the `/.well-known/oauth-authorization-server` location**

Proxy this to the auth service instead of SWAG MCP:

```nginx
    # OAuth Authorization Server Metadata — proxy to auth service
    location = /.well-known/oauth-authorization-server {
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;

        add_header Cache-Control "public, max-age=3600" always;

        proxy_pass http://mcp-oauth-auth:8000/.well-known/oauth-authorization-server;
    }
```

**Step 3: Similarly update `/register`, `/authorize`, `/token`, `/revoke`, `/callback`**

These OAuth flow endpoints should proxy to the auth service:

```nginx
    # OAuth 2.1 endpoints — proxy to auth service
    location = /register {
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;
        proxy_pass http://mcp-oauth-auth:8000/register;
    }

    location = /authorize {
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;
        proxy_pass http://mcp-oauth-auth:8000/authorize;
    }

    location = /token {
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;
        add_header Cache-Control "no-store" always;
        proxy_pass http://mcp-oauth-auth:8000/token;
    }

    location = /revoke {
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;
        add_header Cache-Control "no-store" always;
        proxy_pass http://mcp-oauth-auth:8000/revoke;
    }

    location = /callback {
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;
        proxy_pass http://mcp-oauth-auth:8000/callback;
    }

    location = /success {
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;
        proxy_pass http://mcp-oauth-auth:8000/success;
    }
```

**Step 4: Reload and verify**

```bash
docker exec swag nginx -t && docker exec swag nginx -s reload
```

**Step 5: Test the full OAuth discovery chain**

```bash
# Protected resource metadata
curl -s https://swag.tootie.tv/.well-known/oauth-protected-resource | python3 -m json.tool

# Authorization server metadata (proxied from auth service)
curl -s https://swag.tootie.tv/.well-known/oauth-authorization-server | python3 -m json.tool
```

Expected: Both return valid JSON. The protected resource points to `mcp-auth.tootie.tv` as the authorization server.

---

### Task 9: End-to-End OAuth Flow Test

**Files:** None (manual testing)

**Step 1: Dynamic client registration**

```bash
curl -s -X POST https://mcp-auth.tootie.tv/register \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "swag-mcp-test",
    "redirect_uris": ["https://swag.tootie.tv/callback"],
    "grant_types": ["authorization_code"],
    "response_types": ["code"],
    "scope": "mcp:read mcp:write",
    "token_endpoint_auth_method": "client_secret_post"
  }' | python3 -m json.tool
```

Expected: JSON with `client_id`, `client_secret`, `registration_access_token`

Save the `client_id` and `client_secret`.

**Step 2: Start authorization flow**

Open in browser:
```
https://mcp-auth.tootie.tv/authorize?response_type=code&client_id=<CLIENT_ID>&redirect_uri=https://swag.tootie.tv/callback&scope=mcp:read%20mcp:write&state=test123&code_challenge=<PKCE_CHALLENGE>&code_challenge_method=S256
```

This should redirect to GitHub for login, then back with an authorization code.

**Step 3: Exchange code for token**

```bash
curl -s -X POST https://mcp-auth.tootie.tv/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=<AUTH_CODE>&client_id=<CLIENT_ID>&client_secret=<CLIENT_SECRET>&redirect_uri=https://swag.tootie.tv/callback&code_verifier=<PKCE_VERIFIER>"
```

Expected: JSON with `access_token`, `refresh_token`, `token_type: Bearer`

**Step 4: Access SWAG MCP with token**

```bash
curl -s https://swag.tootie.tv/mcp \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: 2025-06-18" \
  -d '{"jsonrpc": "2.0", "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}, "id": 1}'
```

Expected: 200 with MCP initialize response (not 401)

**Step 5: Confirm unauthenticated is rejected**

```bash
curl -s -o /dev/null -w "%{http_code}" https://swag.tootie.tv/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}'
```

Expected: 401

---

### Task 10: Commit and Document

**Files:**
- Commit all changes in `/mnt/compose/mcp-oauth-gateway/`

**Step 1: Commit docker-compose and .env.example**

```bash
cd /mnt/compose/mcp-oauth-gateway
# Don't commit .env (has secrets), only commit compose
git add docker-compose.swag.yml
git commit -m "feat: SWAG-compatible deployment without Traefik"
```

**Step 2: Update memory**

Save a memory noting:
- MCP OAuth Gateway deployed at `mcp-auth.tootie.tv`
- Uses `mcp-oauth-dynamicclient` + Redis on `jakenet`
- SWAG validates tokens via `auth_request` to `/verify`
- GitHub OAuth with user `jmagar` whitelisted
- Compose file: `/mnt/compose/mcp-oauth-gateway/docker-compose.swag.yml`
