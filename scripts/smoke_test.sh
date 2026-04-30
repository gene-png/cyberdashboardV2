#!/usr/bin/env bash
set -e

PORT=5005
BASE="http://localhost:$PORT"
DB_FILE="/tmp/zt_smoke_$$.db"

export FLASK_SECRET_KEY="smoke-test-secret"
export DATABASE_URL="sqlite:///$DB_FILE"

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
  rm -f "$DB_FILE"
}
trap cleanup EXIT

echo "Starting Flask on port $PORT..."
.venv/bin/python -c "
import os
os.environ['FLASK_SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'smoke')
os.environ['DATABASE_URL'] = os.environ.get('DATABASE_URL', 'sqlite:////tmp/smoke.db')
from app import create_app
app = create_app()
app.run(host='127.0.0.1', port=$PORT, use_reloader=False)
" &
SERVER_PID=$!

# Wait for server to be ready
for i in $(seq 1 30); do
  if curl -sf "$BASE/login" > /dev/null 2>&1; then
    echo "Server ready."
    break
  fi
  sleep 0.2
done

check() {
  local url="$1"
  local expected="${2:-200}"
  local actual
  actual=$(curl -s -o /dev/null -w "%{http_code}" "$url")
  if [ "$actual" = "$expected" ]; then
    echo "  OK $actual $url"
  else
    echo "  FAIL expected $expected got $actual for $url"
    exit 1
  fi
}

echo "Checking routes..."
check "$BASE/login" "200"
check "$BASE/" "302"              # Redirect to login (unauthenticated)
check "$BASE/admin/unlock" "302"  # Redirect to login (unauthenticated)
check "$BASE/assessments/nonexistent" "302"  # Redirect to login

echo ""
echo "All routes OK. Smoke test PASSED."
