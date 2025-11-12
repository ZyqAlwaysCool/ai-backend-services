#!/bin/bash

# AI Backend Service 停止脚本

echo "正在停止 AI Backend Service..."

# 查找并终止进程
PIDS=$(pgrep -f "python -m app")

if [ -z "$PIDS" ]; then
    echo "没有找到运行中的服务进程"
    exit 0
fi

echo "找到以下进程:"
echo "$PIDS"

# 优雅地停止进程
echo "正在发送 SIGTERM 信号..."
for PID in $PIDS; do
    kill -TERM $PID
    echo "已向进程 $PID 发送停止信号"
done

# 等待进程停止
echo "等待进程停止..."
sleep 3

# 检查进程是否仍在运行
REMAINING_PIDS=$(pgrep -f "python -m app")
if [ -n "$REMAINING_PIDS" ]; then
    echo "仍有进程在运行，强制终止..."
    for PID in $REMAINING_PIDS; do
        kill -KILL $PID
        echo "已强制终止进程 $PID"
    done
    sleep 1
fi

# 最终检查
FINAL_PIDS=$(pgrep -f "python -m app")
if [ -z "$FINAL_PIDS" ]; then
    echo "所有服务进程已成功停止"
else
    echo "警告：仍有进程未停止: $FINAL_PIDS"
    exit 1
fi