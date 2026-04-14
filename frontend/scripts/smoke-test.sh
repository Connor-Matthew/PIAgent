#!/bin/bash
set -e

echo "=== PIAgent Smoke Test ==="
echo ""

# 1. Check backend health
echo "1. Checking backend health..."
curl -sf http://localhost:8000/api/workflows > /dev/null && echo "   ✓ Backend is up"

# 2. Check frontend dev server
echo "2. Checking frontend dev server..."
curl -sf http://localhost:5173/ > /dev/null && echo "   ✓ Frontend dev server is up"

# 3. Check API proxy
echo "3. Checking Vite API proxy..."
WORKFLOWS=$(curl -sf http://localhost:5173/api/workflows)
echo "   ✓ Proxy works: $(echo "$WORKFLOWS" | wc -c | xargs) bytes received"

# 4. Create a workflow
echo "4. Creating test workflow..."
WF=$(curl -sf -X POST http://localhost:5173/api/workflows \
  -H "Content-Type: application/json" \
  -d '{"name":"Smoke Test","graph":{"nodes":[{"id":"start","type":"start","data":{}}],"edges":[]}}')
WF_ID=$(echo "$WF" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "   ✓ Created workflow: $WF_ID"

# 5. Run the workflow
echo "5. Running workflow..."
RUN=$(curl -sf -X POST "http://localhost:5173/api/workflows/$WF_ID/run" \
  -H "Content-Type: application/json" \
  -d '{"input":"hello smoke test"}')
RUN_ID=$(echo "$RUN" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
STATUS=$(echo "$RUN" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
echo "   ✓ Run completed: $RUN_ID (status: $STATUS)"

# 6. Cleanup
echo "6. Cleaning up..."
curl -sf -X DELETE "http://localhost:5173/api/workflows/$WF_ID" > /dev/null
echo "   ✓ Deleted test workflow"

echo ""
echo "=== All smoke tests passed! ==="
