#!/bin/bash
# Deploy Bug #5 and Bug #6 fixes to server

SERVER="alex@192.168.228.43"
VLLM_PATH="/mnt/d1/work/VLLM/vllm"
LOCAL_BASE="/Users/a0/Documents/py/VLLM/vllm/vllm/entrypoints/openai"

echo "========================================="
echo "Deploying Bug #5 and Bug #6 Fixes"
echo "========================================="
echo ""
echo "Fixes:"
echo "  Bug #5: response.function_call_arguments.delta format (dict)"
echo "  Bug #6: Standard OpenAI tool format support"
echo "  Runtime: FunctionTool instead of Tool TypeAlias"
echo ""

echo "1. Copying fixed files to server..."
echo "   - protocol.py"
scp "${LOCAL_BASE}/protocol.py" "${SERVER}:${VLLM_PATH}/vllm/entrypoints/openai/"
if [ $? -ne 0 ]; then
    echo "   ✗ Failed to copy protocol.py"
    exit 1
fi

echo "   - serving_responses.py"
scp "${LOCAL_BASE}/serving_responses.py" "${SERVER}:${VLLM_PATH}/vllm/entrypoints/openai/"
if [ $? -ne 0 ]; then
    echo "   ✗ Failed to copy serving_responses.py"
    exit 1
fi

echo "   - tool_parsers/utils.py"
scp "${LOCAL_BASE}/tool_parsers/utils.py" "${SERVER}:${VLLM_PATH}/vllm/entrypoints/openai/tool_parsers/"
if [ $? -eq 0 ]; then
    echo "   ✓ All files copied successfully"
else
    echo "   ✗ Failed to copy tool_parsers/utils.py"
    exit 1
fi

echo ""
echo "2. Clearing Python cache on server..."
ssh ${SERVER} "cd ${VLLM_PATH} && \
    find . -type f -name '*.pyc' -delete && \
    find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true && \
    echo '✓ Python cache cleared'"

echo ""
echo "3. Restarting vLLM service..."
ssh ${SERVER} "sudo systemctl restart vllm && sleep 3 && sudo systemctl status vllm | head -10"

echo ""
echo "========================================="
echo "Deployment Complete!"
echo "========================================="
echo ""
echo "Next: Run test to verify the fix works:"
echo "  python3 test_bug_5_and_6_verbose.py"
echo ""
echo "If error occurs, get logs with:"
echo "  ssh ${SERVER} 'journalctl -u vllm -n 200 --no-pager | grep -B 5 -A 50 Traceback'"
