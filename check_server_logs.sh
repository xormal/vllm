#!/bin/bash
# Script to check vLLM server logs for errors

SERVER="alex@192.168.228.43"

echo "========================================"
echo "Checking vLLM Server Logs"
echo "========================================"
echo ""

echo "1. Checking last 100 lines of journalctl:"
echo "----------------------------------------"
ssh ${SERVER} "journalctl -u vllm -n 100 --no-pager" 2>/dev/null || echo "journalctl not available"

echo ""
echo "2. Checking for error messages:"
echo "----------------------------------------"
ssh ${SERVER} "journalctl -u vllm -n 500 --no-pager | grep -i 'error\|exception\|traceback\|failed' | tail -20" 2>/dev/null || echo "No errors found or journalctl not available"

echo ""
echo "3. Checking vLLM process:"
echo "----------------------------------------"
ssh ${SERVER} "ps aux | grep vllm | grep -v grep"

echo ""
echo "4. Checking if model is generating:"
echo "----------------------------------------"
ssh ${SERVER} "journalctl -u vllm -n 200 --no-pager | grep -i 'reasoning\|output\|delta\|completed' | tail -10" 2>/dev/null || echo "No generation logs found"

echo ""
echo "Done!"
