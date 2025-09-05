# Token-Efficient Formatting System

## Overview

Docker MCP implements a sophisticated token-efficient formatting system that provides human-readable output optimized for CLI usage while maintaining full structured data access. This system leverages FastMCP's `ToolResult` architecture to deliver dual-format responses.

## Architecture

### Dual Content Strategy

Every MCP tool response includes two complementary formats:

1. **Human-readable content**: Token-efficient formatted text optimized for readability
2. **Structured content**: Complete JSON data for programmatic access

```python
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

return ToolResult(
    content=[TextContent(type="text", text=formatted_output)],  # Human-readable
    structured_content=raw_data                                 # Machine-readable
)
```

### Service Layer Pattern

The formatting system follows a consistent pattern across all services:

```python
class ServiceName:
    async def operation_method(self, params) -> ToolResult:
        # 1. Perform operation
        raw_data = await self.get_data(params)

        # 2. Format for humans
        formatted_lines = self._format_operation_summary(raw_data)

        # 3. Return dual format
        return ToolResult(
            content=[TextContent(type="text", text="\n".join(formatted_lines))],
            structured_content=raw_data
        )
```

## Formatting Implementations

### Port Mappings (`docker_hosts ports`)

**Token Efficiency Strategy**: Group ports by container to eliminate repetition

**Before (Raw JSON)**:
```json
[
  {"container_name": "swag", "host_port": "2002", "container_port": "22", "protocol": "TCP"},
  {"container_name": "swag", "host_port": "443", "container_port": "443", "protocol": "TCP"},
  // ... 82 more entries
]
```

**After (Formatted)**:
```
Port Usage on squirts
Found 82 exposed ports across 41 containers

Protocols: TCP: 78, UDP: 4
Port ranges: System: 14, User: 68, Dynamic: 0

PORT MAPPINGS:
  swag [swag]: 2002→22/tcp, 443→443/tcp, 80→80/tcp
  adguard [adguard]: 3000→3000/tcp, 53→53/tcp, 53→53/udp, 3010→80/tcp
```

**Implementation**:
```python
def _format_port_mapping_details(self, port_mappings: list[dict[str, Any]]) -> list[str]:
    # Group ports by container for efficient display
    by_container = {}
    for mapping in port_mappings:
        container_key = mapping['container_name']
        if container_key not in by_container:
            by_container[container_key] = {'ports': [], 'compose_project': ''}

        port_str = f"{mapping['host_port']}→{mapping['container_port']}/{mapping['protocol'].lower()}"
        by_container[container_key]['ports'].append(port_str)

    # Display grouped by container
    for container_name, data in sorted(by_container.items()):
        ports_str = ', '.join(data['ports'])
        project_info = f" [{data['compose_project']}]" if data['compose_project'] else ""
        lines.append(f"  {container_name}{project_info}: {ports_str}")
```

### Host Listings (`docker_hosts list`)

**Token Efficiency Strategy**: Aligned table format with symbols

**Formatted Output**:
```
Docker Hosts (7 configured)
Host         Address              ZFS Dataset
------------ -------------------- --- --------------------
tootie       tootie:29229         ✓   cache/appdata
shart        SHART:22             ✓   backup/appdata
squirts      squirts:22           ✓   rpool/appdata
vivobook-wsl vivobook-wsl:22      ✗   -
```

**Implementation**:
```python
def list_docker_hosts(self) -> dict[str, Any]:
    # Create human-readable summary for efficient display
    summary_lines = [
        f"Docker Hosts ({len(hosts)} configured)",
        f"{'Host':<12} {'Address':<20} {'ZFS':<3} {'Dataset':<20}",
        f"{'-'*12:<12} {'-'*20:<20} {'-'*3:<3} {'-'*20:<20}",
    ]

    for host_data in hosts:
        zfs_indicator = "✓" if host_data.get('zfs_capable') else "✗"
        address = f"{host_data['hostname']}:{host_data['port']}"
        dataset = host_data.get('zfs_dataset', '-') or '-'

        summary_lines.append(
            f"{host_data['host_id']:<12} {address:<20} {zfs_indicator:<3} {dataset[:20]:<20}"
        )

    return {
        "success": True,
        "hosts": hosts,
        "count": len(hosts),
        "summary": "\n".join(summary_lines)  # Formatted content
    }
```

### Container Listings (`docker_container list`)

**Token Efficiency Strategy**: Compact single-line format with status indicators

**Formatted Output**:
```
Docker Containers on squirts
Showing 20 of 41 containers

  Container                 Ports                Project
  ------------------------- -------------------- ---------------
● swag-mcp | 8012 | swag-mcp
● syslog-ng | 514,601+6 | syslog-mcp
○ elasticsearch | - | syslog-mcp
```

**Key Features**:
- Status indicators: `●` (running), `○` (stopped), `◐` (restarting)
- Port compression: Show first 3 ports, then `+N` for overflow
- Project truncation for space efficiency
- Pagination info

**Implementation**:
```python
def _format_container_summary(self, container: dict[str, Any]) -> list[str]:
    status_indicator = "●" if container["state"] == "running" else "○"

    # Extract first 3 host ports for compact display
    ports = container.get("ports", [])
    if ports:
        host_ports = []
        for port in ports[:3]:
            if ":" in port and "→" in port:
                host_port = port.split(":")[1].split("→")[0]
                host_ports.append(host_port)
        ports_display = ",".join(host_ports)
        if len(ports) > 3:
            ports_display += f"+{len(ports)-3}"
    else:
        ports_display = "-"

    # Truncate names for alignment
    name = container["name"][:25]
    project = container.get("compose_project", "-")[:15]

    return [f"{status_indicator} {name} | {ports_display} | {project}"]
```

### Stack Listings (`docker_compose list`)

**Token Efficiency Strategy**: Status summary with service counts

**Formatted Output**:
```
Docker Compose Stacks on squirts (28 total)
Status breakdown: running: 27, partial: 1

  Stack                     Status     Services
  ------------------------- ---------- ---------------
● swag-mcp                  running    [1] swag-mcp
◐ syslog-mcp                partial    [3] syslog-ng,elasticsearch...
● authelia                  running    [3] authelia,authelia-redis...
```

**Key Features**:
- Status summary at top
- Status indicators with partial state support
- Service count `[N]` with first 2 service names
- Overflow indication with `...`

**Implementation**:
```python
def _format_stacks_list(self, result: dict[str, Any], host_id: str) -> list[str]:
    stacks = result["stacks"]

    # Count stacks by status
    status_counts = {}
    for stack in stacks:
        status = stack.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    status_summary = ", ".join(f"{status}: {count}" for status, count in status_counts.items())

    summary_lines = [
        f"Docker Compose Stacks on {host_id} ({len(stacks)} total)",
        f"Status breakdown: {status_summary}",
        "",
        f"{'':1} {'Stack':<25} {'Status':<10} {'Services':<15}",
    ]

    for stack in stacks:
        status_indicator = {"running": "●", "partial": "◐", "stopped": "○"}.get(
            stack.get("status", "unknown"), "?"
        )
        services = stack.get("services", [])
        services_display = f"[{len(services)}] {','.join(services[:2])}" if services else "[0]"
        if len(services) > 2:
            services_display += "..."

        summary_lines.append(
            f"{status_indicator} {stack['name']:<25} {stack.get('status', 'unknown'):<10} {services_display:<15}"
        )
```

### Logs Formatting (containers/stacks)

Token Efficiency Strategy: Provide a compact header with counts and a small preview; keep full logs only in structured_content.

Formatted Output (container logs):
```
Container Logs for swag on squirts
Lines returned: 100 (requested: 100)
truncated: False | follow: False

Preview (first 5):
  [..] line 1
  [..] line 2
  [..] line 3
  [..] line 4
  [..] line 5

Preview (last 5):
  [..]
```

Implementation: ContainerService.handle_action(LOGS) and StackService.handle_action(LOGS) return ToolResult(content=formatted, structured_content={'logs': [...]}).

### Host CRUD Summaries (docker_hosts add/edit/remove/test_connection)

Token Efficiency Strategy: One‑line or two‑line confirmations with key fields and ✓/✗ indicators; preserve full details in structured_content.

Examples:
```
Host added: prod (prod.example.com)
SSH: docker@prod.example.com:22 | tested: ✓

Host updated: prod
Fields: ssh_user, ssh_port, zfs_capable

Host removed: prod (prod.example.com)

SSH OK: prod prod.example.com:22
Docker: 24.0.6
```

### Compose Discover Summary (docker_compose discover)

Token Efficiency Strategy: Top‑level counts and suggested path with short previews of locations and stacks.

Formatted Output:
```
Compose Discovery on squirts
Stacks found: 12 | Locations: 2
Suggested compose_path: /mnt/user/compose

Top locations:
  /mnt/user/compose: 10 stacks
  /srv/compose: 2 stacks

Stacks:
  swag-mcp: /mnt/user/compose/swag-mcp
  syslog-mcp: /mnt/user/compose/syslog-mcp
  ...
```

### Cleanup Summaries (docker_hosts cleanup)

Token Efficiency Strategy: For check, show reclaimable totals and level estimates. For actions, summarize reclaimed space by resource.

Formatted Output:
```
Docker Cleanup (check) on squirts
Total reclaimable: 5.2 GB (23%)

Levels:
  safe: 1.1 GB (4%)
  moderate: 3.7 GB (16%)
  aggressive: 5.2 GB (23%)

Docker Cleanup (safe) on squirts

Reclaimed:
  containers: 512MB
  networks: 0B
  build cache: 1.3GB
```

Schedule Operations:
```
Cleanup Schedules (2 total, 1 active)
ID                         Host         Type      Freq     Time  En
-------------------------- ------------ --------- -------- ----- --
prod_safe_daily            prod         safe      daily    02:00 ✓
test_moderate_weekly       test         moderate  weekly   03:30 ✗
```

Implementation: HostService.handle_action(CLEANUP) wraps schedule and cleanup results in ToolResult with formatted summaries.

### Host Discover Summary (docker_hosts discover)

Token Efficiency Strategy: Aligned table for multi‑host discovery and compact per‑host summaries; preserve all structured discovery details.

Formatted Output (single host):
```
Host Discovery on squirts
Compose paths: 3 | Appdata paths: 2 | ZFS: ✓
ZFS dataset: rpool/appdata

Compose paths:
  /mnt/user/compose/swag-mcp
  /mnt/user/compose/syslog-mcp
  ...

Appdata paths:
  /mnt/user/appdata
```

Formatted Output (all hosts):
```
Host Discovery (all)
Hosts: 5 | ZFS-capable: 3 | Total paths: 27 | Recommendations: 8

Host         OK ZFS Paths Recs
------------ -- --- ----- ----
prod         ✓  ✓   12    4
test         ✓  ✗   3     1
edge         ✗  ✗   0     0
```

Implementation: HostService.handle_action(DISCOVER) wraps results in ToolResult with either a per‑host summary or a cross‑host table and preserves `structured_content` (including `helpful_guidance`).

## Technical Implementation

### ToolResult Flow

The critical breakthrough was fixing the service layer's `handle_action` methods that were stripping away the formatted content:

**❌ Before (Broken)**:
```python
async def handle_action(self, action, **params) -> dict[str, Any]:
    result = await self.list_containers(host_id)
    # This strips away the formatted content!
    if hasattr(result, "structured_content"):
        return result.structured_content
    return result
```

**✅ After (Fixed)**:
```python
async def handle_action(self, action, **params) -> ToolResult | dict[str, Any]:
    result = await self.list_containers(host_id)
    # Preserve the full ToolResult with both content types
    return result
```

### Server Integration

Updated all server tool methods to handle both return types:

```python
async def docker_hosts(self, action, **params) -> ToolResult | dict[str, Any]:
    return await self.host_service.handle_action(action, **params)

async def docker_container(self, action, **params) -> ToolResult | dict[str, Any]:
    return await self.container_service.handle_action(action, **params)

async def docker_compose(self, action, **params) -> ToolResult | dict[str, Any]:
    return await self.stack_service.handle_action(action, **params)
```

### FastMCP Integration

FastMCP automatically handles `ToolResult` objects according to the MCP specification:

- **Object-like results** (`dict`, Pydantic models) → Always become structured content
- **ToolResult objects** → Preserve both content and structured_content fields
- **Backward compatibility** → Traditional content blocks maintained

## Design Principles

### 1. Show ALL Data
Never hide information from users. Token efficiency comes from better formatting, not data reduction.

**Example**: Port listings show all 82 ports, just grouped efficiently by container.

### 2. Scannable Formatting
Use visual hierarchy and alignment to make information easy to scan:

- **Headers** with counts: `"Docker Hosts (7 configured)"`
- **Status indicators**: `●`, `○`, `◐`, `✓`, `✗`
- **Aligned tables** with proper column spacing
- **Overflow indicators**: `+3`, `...`

### 3. Context Preservation
Include relevant context without redundancy:

- **Project context**: `[swag-mcp]`
- **Summary statistics**: `"Status breakdown: running: 27, partial: 1"`
- **Pagination info**: `"Showing 20 of 41 containers"`

### 4. Consistent Patterns
Apply the same formatting conventions across all tools:

- Status indicators always use the same symbols
- Truncation rules are consistent (25 chars for names, etc.)
- Table alignment follows the same patterns
- Overflow handling uses consistent notation

## Token Efficiency Metrics

### Before vs After Comparison

**Port Mappings Example** (82 ports):
- **Before**: ~15,000 tokens (verbose JSON)
- **After**: ~2,800 tokens (grouped format)
- **Savings**: ~81% reduction

**Host Listings Example** (7 hosts):
- **Before**: ~1,200 tokens (verbose JSON)
- **After**: ~380 tokens (table format)
- **Savings**: ~68% reduction

**Container Listings Example** (41 containers):
- **Before**: ~8,500 tokens (verbose JSON)
- **After**: ~1,900 tokens (single-line format)
- **Savings**: ~78% reduction

### Efficiency Techniques

1. **Grouping**: Combine related data (ports by container)
2. **Symbols**: Use `●`, `✓` instead of words like "running", "enabled"
3. **Truncation**: Intelligent trimming with overflow indicators
4. **Alignment**: Fixed-width columns reduce formatting tokens
5. **Compression**: Show counts `[3]` instead of listing all items

## Usage Examples

### Port Management
```bash
# See all ports in grouped format
docker_hosts ports squirts

# Check specific port availability
docker_hosts ports squirts --port 8080
```

### Container Operations
```bash
# List containers with status and ports
docker_container list squirts

# Get detailed container info (still returns ToolResult)
docker_container info squirts container_id
```

### Stack Management
```bash
# View all stacks with status breakdown
docker_compose list squirts

# Deploy with formatted feedback
docker_compose deploy squirts my-stack "$(cat docker-compose.yml)"
```

## Development Guidelines

### Adding New Formatting

When implementing new formatting for additional tools:

1. **Create formatting methods** following the `_format_*_summary` pattern
2. **Return ToolResult** with both content types
   - When augmenting an existing ToolResult, preserve its content and update only `structured_content`
3. **Follow token efficiency principles**
4. **Test with real data** to verify token savings
5. **Update handle_action** to preserve ToolResult

### Testing Formatting

```python
# Unit test formatting methods directly
def test_format_port_mappings():
    service = ContainerService(config, context_manager)
    port_data = [{"container_name": "test", "host_port": "8080", ...}]
    formatted = service._format_port_mapping_details(port_data)
    assert "test: 8080→8080/tcp" in "\n".join(formatted)

# Integration test ToolResult preservation
async def test_list_containers_returns_toolresult():
    result = await container_service.list_containers("squirts")
    assert isinstance(result, ToolResult)
    assert result.content  # Human-readable
    assert result.structured_content  # Machine-readable
```

## Benefits

### For CLI Users
- **Faster scanning**: Information density optimized for human reading
- **Less scrolling**: Compact format reduces terminal output
- **Better context**: Grouped and summarized data tells the story
- **Visual clarity**: Consistent symbols and alignment

### For Programmatic Access
- **Complete data**: Full JSON structure preserved
- **Backward compatibility**: Existing integrations continue working
- **Flexible consumption**: Choose formatted or structured based on needs

### For Token Efficiency
- **Significant savings**: 68-81% reduction in common operations
- **Scalable**: Efficiency improves with larger datasets
- **Maintained functionality**: No loss of information or capability

## Future Enhancements

### Potential Improvements
1. **Configurable verbosity**: Allow users to choose detail levels
2. **Color support**: Add ANSI colors for better visual distinction
3. **Custom formatting**: User-defined formatting templates
4. **Interactive mode**: Progressive disclosure of details
5. **Export formats**: CSV, JSON, YAML output options

### Monitoring
- Track token usage metrics over time
- Gather user feedback on formatting preferences
- Identify additional opportunities for efficiency gains
- Monitor performance impact of formatting operations

This token-efficient formatting system demonstrates that CLI tools can be both human-friendly and resource-efficient without sacrificing functionality or data completeness.
