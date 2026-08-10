#!/usr/bin/env bash
set -euo pipefail

EXAMPLE_DIR="${1:-examples/langgraph_demo_agent}"

echo "Running AgentScope Dev Preflight Checks..."

# 1. Check Docker
echo -n "1. Checking Docker... "
if ! command -v docker &> /dev/null; then
    echo "FAILED"
    echo "Error: Docker command not found. Please install Docker."
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "FAILED"
    echo "Error: Docker daemon is not running."
    echo "Please start Docker Desktop (or 'sudo systemctl start docker') and try again."
    exit 1
fi
echo "OK"

# 2. Check Port 8000
echo -n "2. Checking port 8000... "
LISTENERS=$(lsof -i :8000 -sTCP:LISTEN -t 2>/dev/null || ss -tlnp 'sport = :8000' 2>/dev/null | grep -oP 'pid=\K[0-9]+' || true)

if [ -n "$LISTENERS" ]; then
    echo "CONFLICT"
    for PID in $LISTENERS; do
        PNAME=$(ps -p "$PID" -o comm= 2>/dev/null || echo "unknown")
        echo "  Found process $PNAME (PID: $PID) listening on port 8000."
        read -rp "  Kill this process? (y/n): " ANSWER
        if [ "$ANSWER" = "y" ]; then
            kill -9 "$PID" 2>/dev/null && echo "  Killed process $PID." || echo "  Failed to kill $PID (try sudo)."
        else
            echo "  Port 8000 is still in use. Backend startup may fail."
        fi
    done
else
    echo "OK (Free)"
fi

# 3. Check Python Dependencies
echo -n "3. Checking Python dependencies for $EXAMPLE_DIR... "
REQ_FILE="$EXAMPLE_DIR/requirements.txt"

if [ -f "$REQ_FILE" ]; then
    MISSING=0
    while IFS= read -r line; do
        # Skip empty lines and comments
        [[ -z "$line" || "$line" == \#* ]] && continue
        # Extract package name (before >= or ==)
        PKG=$(echo "$line" | sed 's/[><=].*//' | tr '-' '_')
        if ! python -c "import $PKG" 2>/dev/null; then
            echo ""
            echo "  Missing: $line"
            MISSING=1
        fi
    done < "$REQ_FILE"

    if [ "$MISSING" -eq 1 ]; then
        echo "FAILED"
        echo "Please run: pip install -r $REQ_FILE"
        exit 1
    else
        echo "OK"
    fi
else
    echo "SKIPPED (No requirements.txt found)"
fi

echo "Preflight complete! You are ready to run the demo."
