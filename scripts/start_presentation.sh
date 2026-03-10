#!/bin/bash
# Master startup script for presentation
# Run this from WSL to start the entire system

set -e

echo "=========================================="
echo "  Operation Sentinel - Presentation Demo"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running in WSL
if ! grep -qi microsoft /proc/version 2>/dev/null; then
    echo -e "${RED}ERROR: This script must be run in WSL${NC}"
    exit 1
fi

# Source environment variables (strip Windows CRLF before sourcing)
if [ -d "$HOME/workspace/LesnarAI" ]; then
    PROJECT_DIR="$HOME/workspace/LesnarAI"
else
    PROJECT_DIR="$HOME/lesnar/LesnarAI"
fi
ENV_FILE=""
if [ -f "$PROJECT_DIR/.env.secure" ]; then
    ENV_FILE="$PROJECT_DIR/.env.secure"
elif [ -f "$PROJECT_DIR/.env" ]; then
    ENV_FILE="$PROJECT_DIR/.env"
elif [ -f "$PROJECT_DIR/.env.example" ]; then
    ENV_FILE="$PROJECT_DIR/.env.example"
    echo -e "${YELLOW}Warning: Using .env.example (only acceptable for non-sensitive smoke tests)${NC}"
else
    echo -e "${RED}ERROR: No .env.secure, .env, or .env.example found in $PROJECT_DIR${NC}"
    exit 1
fi

# Create a clean temp copy without \r, then source it
CLEAN_ENV=$(mktemp)
sed 's/\r$//' "$ENV_FILE" > "$CLEAN_ENV"
set -a
source "$CLEAN_ENV"
set +a
rm -f "$CLEAN_ENV"
echo -e "${GREEN}Loaded $(basename $ENV_FILE)${NC}"

echo ""
echo -e "${YELLOW}[1/6] Checking Docker connectivity...${NC}"
if ! docker ps &>/dev/null; then
    echo -e "${RED}ERROR: Cannot connect to Docker. Make sure Docker Desktop is running with WSL integration enabled.${NC}"
    exit 1
fi
echo -e "${GREEN}Docker is accessible${NC}"
echo ""

echo -e "${YELLOW}[2/6] Starting backend services (TimescaleDB, Redis, Flask API)...${NC}"
cd "$PROJECT_DIR"
docker compose --env-file "$ENV_FILE" up -d
echo ""
echo "Waiting for backend to fully start..."
sleep 10
echo -e "${GREEN}Backend services started${NC}"
echo ""

echo -e "${YELLOW}[3/6] Verifying backend health...${NC}"
AUTH_HEADER=""
if [ -n "${LESNAR_PRESENTATION_USERNAME:-}" ] && [ -n "${LESNAR_PRESENTATION_PASSWORD:-}" ]; then
    AUTH_HEADER=$(python3 "$PROJECT_DIR/scripts/request_session_token.py" \
        --backend-url http://localhost:5000 \
        --username "$LESNAR_PRESENTATION_USERNAME" \
        --password "$LESNAR_PRESENTATION_PASSWORD" \
        --format header 2>/dev/null || true)
fi

API_KEY="${LESNAR_OPERATOR_API_KEY:-${LESNAR_ADMIN_API_KEY:-}}"
for i in {1..15}; do
    if [ -n "$AUTH_HEADER" ]; then
        HEALTH=$(curl -s -H "$AUTH_HEADER" http://localhost:5000/api/health 2>/dev/null || echo "")
    else
        HEALTH=$(curl -s -H "X-API-Key: $API_KEY" http://localhost:5000/api/health 2>/dev/null || echo "")
    fi
    if echo "$HEALTH" | grep -q '"status"'; then
        echo -e "${GREEN}Backend is healthy${NC}"
        break
    fi
    if [ $i -eq 15 ]; then
        echo -e "${RED}ERROR: Backend health check failed after 30s${NC}"
        echo "Debug: auth_header_present=$([ -n "$AUTH_HEADER" ] && echo yes || echo no)"
        echo "Debug: curl response=$HEALTH"
        echo "Debug: docker logs:"
        docker logs lesnarai-backend-1 --tail 10 2>&1
        exit 1
    fi
    sleep 2
done
echo ""

echo -e "${YELLOW}[4/6] Preparing obstacles world...${NC}"
if [ ! -f ~/PX4-Autopilot/Tools/simulation/gz/worlds/obstacles.sdf ]; then
    if [ -f "$PROJECT_DIR/obstacles.sdf" ]; then
        cp "$PROJECT_DIR/obstacles.sdf" ~/PX4-Autopilot/Tools/simulation/gz/worlds/obstacles.sdf
        echo -e "${GREEN}Obstacles world copied to PX4${NC}"
    else
        echo -e "${YELLOW}Warning: obstacles.sdf not found in project, skipping${NC}"
    fi
else
    echo -e "${GREEN}Obstacles world already in place${NC}"
fi
echo ""

echo -e "${YELLOW}[5/6] Creating dataset directory...${NC}"
mkdir -p "$PROJECT_DIR/dataset/px4_teacher"
echo -e "${GREEN}Dataset directory ready${NC}"
echo ""

echo -e "${YELLOW}[6/6] Killing any existing simulation processes...${NC}"
sudo killall -9 ruby gz gzserver gzclient px4 2>/dev/null || true
sleep 2
echo -e "${GREEN}Clean slate ready${NC}"
echo ""

echo "=========================================="
echo -e "${GREEN}System Ready for Presentation!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Start Gazebo with obstacles (in THIS terminal):"
echo "   cd $PROJECT_DIR"
echo "   gz sim -v4 -r obstacles.sdf &"
echo ""
echo "2. Wait 10-15 seconds for Gazebo GUI to load"
echo ""
echo "3. Start PX4 (in SAME terminal):"
echo "   sleep 10"
echo "   cd ~/PX4-Autopilot"
echo "   export PX4_GZ_MODEL=\"x500\""
echo "   PX4_GZ_STANDALONE=1 make px4_sitl gz_x500"
echo ""
echo "4. Start bridge (in NEW WSL terminal):"
echo "   cd $PROJECT_DIR"
echo "   source .venv-wsl/bin/activate"
echo "   python3 training/px4_teacher_collect_gz.py --duration 300"
echo ""
echo "5. View data in Adminer: http://localhost:8080"
echo "   Server: timescaledb | User: ${POSTGRES_USER:-lesnar} | Pass: ${POSTGRES_PASSWORD:-<check .env>}"
echo ""
echo "6. Test commands (Windows PowerShell or WSL):"
if [ -n "$AUTH_HEADER" ]; then
    echo "   curl -H \"$AUTH_HEADER\" http://localhost:5000/api/drones"
else
    echo "   export SESSION_HEADER=\"\$(python3 scripts/request_session_token.py --username <user> --password <pass>)\""
    echo "   curl -H \"\$SESSION_HEADER\" http://localhost:5000/api/drones"
fi
echo ""
