#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 SWAG MCP Quick Installer${NC}"
echo "=============================="

# Check for required commands
for cmd in docker curl; do
    if ! command -v $cmd &> /dev/null; then
        echo -e "${RED}❌ Error: $cmd is not installed${NC}"
        exit 1
    fi
done

# Check if docker compose (v2) or docker-compose (v1) is available
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo -e "${RED}❌ Error: Docker Compose is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Prerequisites check passed${NC}\n"

# Download configuration files
echo "📥 Downloading configuration files..."
curl -sO https://raw.githubusercontent.com/jmagar/swag-mcp/main/docker-compose.yaml || {
    echo -e "${RED}❌ Failed to download docker-compose.yaml${NC}"
    exit 1
}

# Handle existing .env file
if [ -f .env ]; then
    echo -e "${YELLOW}⚠️  Existing .env file detected${NC}"
    echo "Options:"
    echo "  1) Keep existing configuration (update/restart only)"
    echo "  2) Start fresh with new configuration (backup existing)"
    read -p "Choose [1-2]: " env_choice

    case $env_choice in
        1)
            echo -e "${GREEN}✅ Keeping existing .env configuration${NC}"
            # Skip all configuration steps
            SKIP_CONFIG=true
            ;;
        2)
            echo "Backing up existing .env to .env.backup"
            mv .env .env.backup
            curl -sO https://raw.githubusercontent.com/jmagar/swag-mcp/main/.env.example || {
                echo -e "${RED}❌ Failed to download .env.example${NC}"
                exit 1
            }
            mv .env.example .env
            SKIP_CONFIG=false
            ;;
        *)
            echo -e "${RED}Invalid choice. Exiting.${NC}"
            exit 1
            ;;
    esac
else
    # No existing .env, download fresh
    curl -sO https://raw.githubusercontent.com/jmagar/swag-mcp/main/.env.example || {
        echo -e "${RED}❌ Failed to download .env.example${NC}"
        exit 1
    }
    mv .env.example .env
    SKIP_CONFIG=false
fi

echo -e "${GREEN}✅ Configuration files ready${NC}\n"

# Skip configuration if keeping existing .env
if [ "$SKIP_CONFIG" = true ]; then
    echo "📋 Using existing configuration from .env"

    # Display existing configuration details
    EXISTING_PROXY=$(grep "^SWAG_MCP_PROXY_CONFS_PATH=" .env | cut -d'=' -f2)
    EXISTING_LOG=$(grep "^SWAG_MCP_LOG_DIRECTORY=" .env | cut -d'=' -f2)
    EXISTING_PORT=$(grep "^SWAG_MCP_PORT=" .env | cut -d'=' -f2)

    echo ""
    echo "Current settings:"
    echo -e "${GREEN}📁 Proxy-confs:${NC} $EXISTING_PROXY"
    if [ -d "$EXISTING_PROXY" ]; then
        EXISTING_CONF_COUNT=$(find "$EXISTING_PROXY" -maxdepth 1 -name "*.conf" ! -name "*.conf.sample" 2>/dev/null | wc -l)
        echo -e "${GREEN}   Active configs:${NC} $EXISTING_CONF_COUNT .conf files"
    fi
    echo -e "${GREEN}📝 Log directory:${NC} $EXISTING_LOG"
    echo -e "${GREEN}🌐 Service port:${NC} $EXISTING_PORT"
    echo ""
else
    # Auto-discover SWAG proxy-confs location
    echo "🔍 Searching for SWAG installation..."

    # Method 1: Check running containers
    SWAG_CONTAINERS=$(docker ps --format '{{.Names}}' | grep -i swag || true)

    if [ -n "$SWAG_CONTAINERS" ]; then
        echo "Found SWAG container(s): $SWAG_CONTAINERS"

        for container in $SWAG_CONTAINERS; do
            # Get all mounted volumes for this container
            MOUNTS=$(docker inspect "$container" --format '{{range .Mounts}}{{.Source}}:{{.Destination}}{{"\n"}}{{end}}' 2>/dev/null || true)

            # Look for proxy-confs in the mounts
            while IFS=':' read -r source dest; do
                if [[ "$dest" == *"proxy-confs"* ]] || [[ "$source" == *"proxy-confs"* ]]; then
                    # Check if source path exists and contains .conf files
                    if [ -d "$source" ] && ls "$source"/*.conf* &>/dev/null; then
                        PROXY_CONFS="$source"
                        break 2
                    fi
                fi
            done <<< "$MOUNTS"

            # Also check common paths relative to container volumes
            VOLUME_PATHS=$(docker inspect "$container" --format '{{range .Mounts}}{{.Source}}{{"\n"}}{{end}}' 2>/dev/null || true)
            for vol_path in $VOLUME_PATHS; do
                # Check parent directory for proxy-confs
                PARENT_DIR=$(dirname "$vol_path")
                if [ -d "$PARENT_DIR/proxy-confs" ] && ls "$PARENT_DIR/proxy-confs"/*.conf* &>/dev/null; then
                    PROXY_CONFS="$PARENT_DIR/proxy-confs"
                    break 2
                fi
                # Check subdirectories
                if [ -d "$vol_path/nginx/proxy-confs" ] && ls "$vol_path/nginx/proxy-confs"/*.conf* &>/dev/null; then
                    PROXY_CONFS="$vol_path/nginx/proxy-confs"
                    break 2
                fi
            done
        done
    fi

    # Method 2: Check common locations if not found
    if [ -z "$PROXY_CONFS" ]; then
        COMMON_PATHS=(
            "/mnt/appdata/swag/nginx/proxy-confs"
            "/mnt/user/appdata/swag/nginx/proxy-confs"
            "/volume1/docker/swag/nginx/proxy-confs"
            "/config/nginx/proxy-confs"
            "./proxy-confs"
            "$HOME/swag/nginx/proxy-confs"
        )

        for path in "${COMMON_PATHS[@]}"; do
            if [ -d "$path" ] && ls "$path"/*.conf* &>/dev/null; then
                PROXY_CONFS="$path"
                echo "Found proxy-confs at common location: $path"
                break
            fi
        done
    fi

    # Handle proxy-confs path
    if [ -n "$PROXY_CONFS" ]; then
        # Count active .conf files (excluding .conf.sample)
        CONF_COUNT=$(find "$PROXY_CONFS" -maxdepth 1 -name "*.conf" ! -name "*.conf.sample" 2>/dev/null | wc -l)
        echo -e "${GREEN}✅ Found proxy-confs at: $PROXY_CONFS${NC}"
        echo -e "${GREEN}   📊 Active configurations: $CONF_COUNT .conf files${NC}"
        read -p "Use this path? [Y/n]: " response

        if [[ ! "$response" =~ ^[Nn]$ ]]; then
            sed -i.bak "s|SWAG_MCP_PROXY_CONFS_PATH=.*|SWAG_MCP_PROXY_CONFS_PATH=$PROXY_CONFS|" .env
            echo -e "${GREEN}✅ Proxy-confs path configured${NC}"
        else
            read -p "Enter the path to your SWAG proxy-confs directory: " CUSTOM_PATH
            sed -i.bak "s|SWAG_MCP_PROXY_CONFS_PATH=.*|SWAG_MCP_PROXY_CONFS_PATH=$CUSTOM_PATH|" .env
            PROXY_CONFS="$CUSTOM_PATH"
        fi
    else
        echo -e "${YELLOW}⚠️  Could not auto-detect SWAG proxy-confs location${NC}"
        read -p "Enter the path to your SWAG proxy-confs directory: " CUSTOM_PATH
        sed -i.bak "s|SWAG_MCP_PROXY_CONFS_PATH=.*|SWAG_MCP_PROXY_CONFS_PATH=$CUSTOM_PATH|" .env
        PROXY_CONFS="$CUSTOM_PATH"
    fi

    # Count configs if we haven't already
    if [ -d "$PROXY_CONFS" ] && [ -z "$CONF_COUNT" ]; then
        CONF_COUNT=$(find "$PROXY_CONFS" -maxdepth 1 -name "*.conf" ! -name "*.conf.sample" 2>/dev/null | wc -l)
        echo -e "${GREEN}   📊 Active configurations: $CONF_COUNT .conf files${NC}"
    fi

    # Create log directory
    echo ""
    echo "📁 Setting up log directory..."
    LOG_DIR="/mnt/appdata/swag-mcp/logs"
    read -p "Use default log directory ($LOG_DIR)? [Y/n]: " response

    if [[ "$response" =~ ^[Nn]$ ]]; then
        read -p "Enter log directory path: " LOG_DIR
    fi

    # Update log directory in .env
    sed -i.bak "s|SWAG_MCP_LOG_DIRECTORY=.*|SWAG_MCP_LOG_DIRECTORY=$LOG_DIR|" .env

    # Create the log directory if it doesn't exist
    if [ ! -d "$LOG_DIR" ]; then
        echo "Creating log directory: $LOG_DIR"
        mkdir -p "$LOG_DIR" 2>/dev/null || {
            echo -e "${YELLOW}⚠️  Could not create log directory. You may need to create it manually or with sudo.${NC}"
        }
    fi

    # Check port availability
    echo ""
    echo "🔍 Checking port availability..."

    # Get the configured port from .env
    CONFIGURED_PORT=$(grep "^SWAG_MCP_PORT=" .env | cut -d'=' -f2)
    PORT=${CONFIGURED_PORT:-8000}

    # Function to check if port is in use
    is_port_in_use() {
        local port=$1
        # Try multiple methods to check port
        if command -v lsof &> /dev/null; then
            lsof -Pi :$port -sTCP:LISTEN -t &>/dev/null
        elif command -v netstat &> /dev/null; then
            netstat -tuln | grep -q ":$port "
        elif command -v ss &> /dev/null; then
            ss -tuln | grep -q ":$port "
        else
            # Fallback: try to connect to the port
            timeout 1 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/$port" &>/dev/null
        fi
    }

    # Find available port
    ORIGINAL_PORT=$PORT
    while is_port_in_use $PORT; do
        echo -e "${YELLOW}⚠️  Port $PORT is in use${NC}"
        ((PORT++))
    done

    if [ "$PORT" != "$ORIGINAL_PORT" ]; then
        echo -e "${GREEN}✅ Found available port: $PORT${NC}"
        sed -i.bak "s/SWAG_MCP_PORT=.*/SWAG_MCP_PORT=$PORT/" .env
    else
        echo -e "${GREEN}✅ Port $PORT is available${NC}"
    fi

    # Clean up backup files
    rm -f .env.bak
fi  # End of SKIP_CONFIG check

# Summary
echo ""
echo "📋 Configuration Summary:"
echo "========================="
FINAL_PROXY_PATH=$(grep "^SWAG_MCP_PROXY_CONFS_PATH=" .env | cut -d'=' -f2)
FINAL_LOG_DIR=$(grep "^SWAG_MCP_LOG_DIRECTORY=" .env | cut -d'=' -f2)
FINAL_PORT=$(grep "^SWAG_MCP_PORT=" .env | cut -d'=' -f2)

echo -e "${GREEN}📁 Proxy-confs path:${NC} $FINAL_PROXY_PATH"
if [ -d "$FINAL_PROXY_PATH" ]; then
    FINAL_CONF_COUNT=$(find "$FINAL_PROXY_PATH" -maxdepth 1 -name "*.conf" ! -name "*.conf.sample" 2>/dev/null | wc -l)
    echo -e "${GREEN}   Active configs:${NC} $FINAL_CONF_COUNT .conf files"
fi
echo -e "${GREEN}📝 Log directory:${NC} $FINAL_LOG_DIR"
echo -e "${GREEN}🌐 Service port:${NC} $FINAL_PORT"
echo ""

read -p "Proceed with deployment? [Y/n]: " response
if [[ "$response" =~ ^[Nn]$ ]]; then
    echo "Deployment cancelled. You can run 'docker compose up -d' later to start."
    exit 0
fi

# Deploy
echo ""
echo "🚀 Deploying SWAG MCP..."
$DOCKER_COMPOSE pull
$DOCKER_COMPOSE up -d

# Check if container started successfully
sleep 3
if $DOCKER_COMPOSE ps | grep -q "swag-mcp.*running"; then
    PORT=$(grep "^SWAG_MCP_PORT=" .env | cut -d'=' -f2)
    LOG_DIR=$(grep "^SWAG_MCP_LOG_DIRECTORY=" .env | cut -d'=' -f2)
    PROXY_PATH=$(grep "^SWAG_MCP_PROXY_CONFS_PATH=" .env | cut -d'=' -f2)

    echo ""
    echo -e "${GREEN}✨ SWAG MCP successfully deployed!${NC}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}🌐 Service running on port:${NC} $PORT"
    echo -e "${GREEN}📁 Managing configs in:${NC} $PROXY_PATH"
    echo -e "${GREEN}📝 Logs stored in:${NC} $LOG_DIR"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "🔧 Quick Commands:"
    echo "  Access URL:  http://localhost:$PORT"
    echo "  View logs:   $DOCKER_COMPOSE logs -f swag-mcp"
    echo "  Edit config: nano .env"
    echo "  Update:      $DOCKER_COMPOSE pull && $DOCKER_COMPOSE up -d"
    echo ""
    echo "Next steps:"
    echo "1. Check the service: curl http://localhost:$PORT/health"
    echo "2. Configure Claude Desktop to use the MCP server"
    echo "3. Start creating your proxy configurations!"
else
    echo -e "${RED}❌ Container failed to start. Check logs with: $DOCKER_COMPOSE logs swag-mcp${NC}"
    exit 1
fi
