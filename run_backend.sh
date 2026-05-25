#!/bin/bash
# F1 策略助手 — 后端启动脚本
# 日志同时输出到终端和 logs/ 目录

cd "$(dirname "$0")"
export PYTHONPATH="$PWD"

mkdir -p logs

echo "=== F1 策略助手 后端启动 ==="
echo "日志目录: $PWD/logs"
echo "API 地址: http://localhost:8000"
echo "健康检查: http://localhost:8000/api/health"
echo ""

./venv/bin/uvicorn backend.main:app --reload --port 8000 --log-level info