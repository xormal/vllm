#!/bin/bash
# Diagnostic script for vLLM server issue

SERVER="192.168.228.43"
USER="alex"
VLLM_PATH="/mnt/d1/work/VLLM/vllm"

echo "========================================="
echo "vLLM Server Diagnostic Script"
echo "========================================="
echo ""

echo "1. Checking file modifications..."
ssh ${USER}@${SERVER} "cd ${VLLM_PATH} && head -10 vllm/entrypoints/openai/protocol.py | grep 'from __future__'"
if [ $? -eq 0 ]; then
    echo "   ✓ from __future__ import annotations is present"
else
    echo "   ✗ from __future__ import annotations NOT FOUND"
fi

ssh ${USER}@${SERVER} "cd ${VLLM_PATH} && grep 'tools: list\[Any\]' vllm/entrypoints/openai/protocol.py"
if [ $? -eq 0 ]; then
    echo "   ✓ tools: list[Any] is present"
else
    echo "   ✗ tools: list[Any] NOT FOUND"
fi

echo ""
echo "2. Checking Python cache..."
CACHE_COUNT=$(ssh ${USER}@${SERVER} "find ${VLLM_PATH}/vllm/entrypoints/openai -name '*.pyc' -o -name '__pycache__' | wc -l")
echo "   Found $CACHE_COUNT cached files/directories"
if [ "$CACHE_COUNT" -gt "0" ]; then
    echo "   ⚠️  Python cache exists - this may cause issues!"
    echo "   Run: ssh ${USER}@${SERVER} 'cd ${VLLM_PATH} && find . -name \"*.pyc\" -delete && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true'"
fi

echo ""
echo "3. Checking vLLM process..."
ssh ${USER}@${SERVER} "ps aux | grep -i 'vllm' | grep -v grep | head -5"

echo ""
echo "4. Getting last 50 lines of logs..."
echo "   Attempting journalctl..."
ssh ${USER}@${SERVER} "journalctl -u vllm -n 50 --no-pager 2>/dev/null || echo 'journalctl not available'"

echo ""
echo "5. Testing endpoint..."
RESPONSE=$(curl -s -X POST http://${SERVER}:8000/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-oss-120b",
    "input": "test",
    "stream": false,
    "tools": [{
      "type": "function",
      "function": {
        "name": "test_tool",
        "parameters": {"type": "object"}
      }
    }]
  }')

echo "Response:"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"

if echo "$RESPONSE" | grep -q "Subscripted generics"; then
    echo ""
    echo "   ✗ ERROR STILL PRESENT"
    echo ""
    echo "========================================="
    echo "RECOMMENDED ACTIONS:"
    echo "========================================="
    echo "1. Clear Python cache on server:"
    echo "   ssh ${USER}@${SERVER} 'cd ${VLLM_PATH} && find . -name \"*.pyc\" -delete && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true'"
    echo ""
    echo "2. Get full traceback from server logs:"
    echo "   ssh ${USER}@${SERVER}"
    echo "   # Then on server:"
    echo "   journalctl -u vllm -n 200 --no-pager | grep -A 30 'Traceback'"
    echo "   # OR check log file:"
    echo "   tail -200 /var/log/vllm/*.log | grep -A 30 'Traceback'"
    echo ""
    echo "3. Restart vLLM with debug logging:"
    echo "   ssh ${USER}@${SERVER}"
    echo "   export VLLM_LOGGING_LEVEL=DEBUG"
    echo "   # restart vllm"
else
    echo "   ✓ Request succeeded!"
fi

echo ""
echo "========================================="
echo "Diagnostic complete"
echo "========================================="
