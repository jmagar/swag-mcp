"""Previously contained discriminated union command models.

As of the refactor to follow the Docker-MCP pattern, these models have been
replaced with a flat parameter structure using SwagAction enum and individual
parameters in the tool signature.

The discriminated union approach was causing MCP validation issues because
FastMCP was serializing complex types as JSON strings instead of objects.

The new approach uses:
- SwagAction enum for actions (see models/enums.py)
- Flat parameter structure in the tool function
- Individual parameter validation in the tool logic
- Consistent dict[str, Any] return types

This provides better MCP compatibility while maintaining type safety.
"""

# This file is kept for reference but contains no active code.
# All command-related functionality has moved to:
# - swag_mcp/models/enums.py (SwagAction enum)
# - swag_mcp/tools/swag.py (flat parameter structure)
# - swag_mcp/models/config.py (request models for service layer)
