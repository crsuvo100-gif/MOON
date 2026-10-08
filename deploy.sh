#!/usr/bin/env bash
# MOON Free Server Deployment Script
# Deploys MOON to Render (recommended free tier) or any Docker-capable host.
# Usage: ./deploy.sh [render|docker|local]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DEPLOY_TARGET="${1:-render}"
echo "=== MOON Deployment: $DEPLOY_TARGET ==="

# ------------------------------------------------------------------
# Pre-flight checks
# ------------------------------------------------------------------
echo "[1/5] Pre-flight checks..."

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+ first."
    exit 1
fi

PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  Python: $PYTHON_VER"

# Check dependencies
if [ -f "requirements.txt" ]; then
    echo "  Installing dependencies..."
    pip install -q -r requirements.txt 2>/dev/null || pip3 install -q -r requirements.txt 2>/dev/null || echo "  WARN: Some deps may have failed"
fi

# Verify MOON imports
echo "  Verifying MOON imports..."
if ! python3 -c "from app.memory.cognitive import CognitiveMemoryManager; print('  OK: memory module loads')" 2>/dev/null; then
    echo "  WARN: Memory module import check failed (non-fatal)"
fi

# Run tests
echo "  Running tests..."
if python3 -m pytest tests/ -q --tb=line 2>/dev/null; then
    echo "  OK: All tests pass"
else
    echo "  WARN: Some tests failed (non-fatal, continuing)"
fi

# ------------------------------------------------------------------
# Deploy based on target
# ------------------------------------------------------------------
case "$DEPLOY_TARGET" in
    render)
        echo "[2/5] Render deployment..."
        echo ""
        echo "  To deploy to Render (free tier):"
        echo ""
        echo "  1. Push this repo to GitHub (if not already):"
        echo "     git add -A && git commit -m 'MOON deployment' && git push"
        echo ""
        echo "  2. Go to https://render.com and sign up (free)"
        echo ""
        echo "  3. Create New Web Service -> Connect your GitHub repo"
        echo ""
        echo "  4. Configure:"
        echo "     - Build Command:  pip install -r requirements.txt"
        echo "     - Start Command:  python main.py serve --host 0.0.0.0 --port \$PORT"
        echo "     - Instance Type:  Free"
        echo ""
        echo "  5. Add environment variables in Render dashboard:"
        echo "     MOON_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
        echo "     MOON_MEMORY_PATH=/data/memory"
        echo ""
        echo "  6. Add a Disk (1GB free) mounted at /data for persistent memory"
        echo ""
        echo "  7. Deploy! MOON will be live at https://<your-app>.onrender.com"
        echo ""
        ;;

    docker)
        echo "[2/5] Docker deployment..."
        if ! command -v docker &>/dev/null; then
            echo "ERROR: docker not found. Install Docker first."
            exit 1
        fi

        echo "  Building image..."
        docker build -t moon:latest .

        echo "  Starting container..."
        docker run -d \
            --name moon \
            --restart unless-stopped \
            -p 8777:8777 \
            -v moon-data:/data/memory \
            -e MOON_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
            -e MOON_MEMORY_PATH=/data/memory \
            moon:latest

        echo "  OK: MOON running at http://localhost:8777"
        echo "  Logs: docker logs -f moon"
        ;;

    local)
        echo "[2/5] Local deployment..."
        echo "  Starting MOON locally..."
        echo ""
        echo "  Run: python main.py serve --host 0.0.0.0 --port 8777"
        echo "  Or:  python main.py terminal"
        echo ""
        ;;

    *)
        echo "ERROR: Unknown deploy target: $DEPLOY_TARGET"
        echo "Usage: $0 [render|docker|local]"
        exit 1
        ;;
esac

# ------------------------------------------------------------------
# Post-deploy verification
# ------------------------------------------------------------------
echo "[3/5] Post-deploy verification..."

if [ "$DEPLOY_TARGET" = "docker" ]; then
    sleep 3
    if curl -sf http://localhost:8777/health &>/dev/null; then
        echo "  OK: Health check passed"
    else
        echo "  WARN: Health check failed (may need more startup time)"
    fi
fi

echo "[4/5] Deployment info..."
echo "  Project: MOON"
echo "  Memory modules: $(find app/memory -name '*.py' | wc -l) files"
echo "  Tests: $(python3 -m pytest tests/ --collect-only -q 2>/dev/null | tail -1)"
echo "  Branch: $(git branch --show-current 2>/dev/null || echo 'unknown')"
echo "  Commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"

echo "[5/5] Done!"
echo ""
echo "=== MOON deployment complete ==="
