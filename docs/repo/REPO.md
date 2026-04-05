# Repository Structure -- swag-mcp

Standard layout for the swag-mcp repository.

## Directory tree

```
swag-mcp/
  .claude-plugin/
    plugin.json              Claude Code plugin manifest
  .codex-plugin/
    plugin.json              Codex CLI plugin manifest
  .github/
    workflows/
      test.yml               CI: lint, typecheck, test
      docker-publish.yml     Docker image publish
      publish-pypi.yml       PyPI package publish
      dependencies.yml       Dependency updates
  assets/
    icon.png                 Plugin icon
    logo.svg                 Plugin logo
  config/
    mcporter.json            Live test tool contract
    nginx/
      mcp.conf               MCP location-level nginx overrides
      oauth.conf             OAuth 2.1 server-level nginx endpoints
  docs/                      Documentation (this tree)
  hooks/
    hooks.json               Claude Code session hook definitions
    scripts/
      sync-env.sh            Sync userConfig to .env
      fix-env-perms.sh       Fix .env permissions
      ensure-gitignore.sh    Verify gitignore patterns
      ensure-ignore-files.sh Verify dockerignore patterns
  scripts/
    lint-plugin.sh           Plugin contract checker
    smoke-test.sh            Smoke test script
  skills/
    swag/
      SKILL.md               Client-facing skill definition
  swag_mcp/                  Python package
    __init__.py
    __main__.py              Module entry point
    server.py                FastMCP server and startup
    core/
      config.py              Pydantic settings (SwagConfig)
      constants.py           Constants (patterns, defaults, paths)
      container.py           DI container
      logging_config.py      Dual logging setup
    middleware/
      __init__.py            Middleware setup and ordering
      error_handling.py      Error handling, retry, security sanitization
      rate_limiting.py       Rate limiting (sliding window)
      request_logging.py     Request audit logging
      timing.py              Performance timing
    models/
      config.py              Pydantic request/response models
      enums.py               SwagAction, BackupSubAction enums
    plugins/
      base.py                Plugin base class
    services/
      swag_manager.py        Orchestrator (delegates to sub-managers)
      backup_manager.py      Backup operations
      config_operations.py   Create, read, edit, remove
      config_updaters.py     Field-level updates
      errors.py              Service error types
      file_operations.py     File I/O, transactions, locking
      filesystem.py          FilesystemBackend protocol + LocalFilesystem
      health_monitor.py      HTTP health checks
      mcp_operations.py      MCP location block operations
      resource_manager.py    Resource and sample queries
      ssh_filesystem.py      SSH/SFTP backend (asyncssh)
      template_manager.py    Jinja2 rendering
      validation.py          Input validation service
    tools/
      swag.py                Tool registration (swag + swag_help)
      handlers/
        backups.py           Backup action handler
        configs.py           Config action handlers (list, create, view, edit, remove, update)
        health.py            Health check handler
        logs.py              Logs action handler
    utils/
      async_utils.py         Async helpers
      error_codes.py         Error code definitions
      error_handlers.py      Error handler utilities
      error_messages.py      Error message templates
      formatters.py          String formatting helpers
      mcp_cache.py           MCP response caching
      mcp_streaming.py       Streaming resource utilities
      mcp_token_optimizer.py Token optimization
      token_efficient_formatter.py  Compact output formatting
      tool_decorators.py     Tool error handling decorator
      tool_helpers.py        Action logging and validation helpers
      uri.py                 SSH URI parser
      validators.py          Input validators
  templates/
    mcp.subdomain.conf.j2   Jinja2 nginx config template
  tests/                     Test suite
  .env.example               Environment template
  CHANGELOG.md               Release history
  CLAUDE.md                  Claude memory reference
  Dockerfile                 Multi-stage Docker build
  Justfile                   Task runner recipes
  docker-compose.yaml        Container orchestration
  gemini-extension.json      Gemini extension manifest
  install.sh                 Installation script
  pyproject.toml             Python project config
  server.json                MCP registry entry
```
