#!/bin/bash

# AI Backend Service 启动脚本

# 设置环境变量
export DIFY_URL=http://10.10.20.106:8891/v1

# 检查是否已经有服务在运行
if pgrep -f "python -m app" > /dev/null; then
    echo "服务已在运行中，PID: $(pgrep -f 'python -m app')"
    exit 1
fi

# 启动服务
echo "正在启动 AI Backend Service..."
echo "DIFY_URL: $DIFY_URL"
nohup env DIFY_URL=$DIFY_URL python -m app >> nohup.out 2>&1 &

# 获取进程ID
PID=$!
echo "服务已启动，PID: $PID"
echo "日志文件: nohup.out"

# 等待一下确认服务启动成功
sleep 2
if ps -p $PID > /dev/null; then
    echo "服务启动成功！"
    echo "查看日志: tail -f nohup.out"
    echo "停止服务: ./scripts/stop.sh"
else
    echo "服务启动失败，请检查日志文件 nohup.out"
    exit 1
fi