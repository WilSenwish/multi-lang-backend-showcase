#!/usr/bin/env bash
# bench/http-bench.sh
# 一键压测 00-hello-http 场景的 5 种语言服务
#
# 依赖: wrk (brew install wrk)
# 使用前请先启动对应语言的服务

set -e

# 压测参数 (可调整)
THREADS=4
CONNECTIONS=100
DURATION=30

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo "========================================"
echo "  Multi-Lang-Backend-Showcase 压测脚本"
echo "  wrk 参数: threads=$THREADS, connections=$CONNECTIONS, duration=${DURATION}s"
echo "========================================"
echo ""

# 检查 wrk 是否安装
if ! command -v wrk &> /dev/null; then
    echo -e "${RED}错误: wrk 未安装${NC}"
    echo "  macOS: brew install wrk"
    echo "  Linux: sudo apt install wrk (或从源码编译)"
    exit 1
fi

# 定义服务
declare -A SERVICES=(
    ["Java (SpringBoot)"]="http://localhost:8080/hello?name=bench"
    ["Go (net/http)"]="http://localhost:8081/hello?name=bench"
    ["Python (FastAPI)"]="http://localhost:8082/hello?name=bench"
    ["Rust (axum)"]="http://localhost:8083/hello?name=bench"
    ["TS-Node (fastify)"]="http://localhost:8084/hello?name=bench"
)

# 检查服务是否存活
echo -e "${YELLOW}检查服务存活...${NC}"
for name in "${!SERVICES[@]}"; do
    url="${SERVICES[$name]}"
    port=$(echo "$url" | grep -oP ':\K\d+')
    if curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -q "200"; then
        echo -e "  ${GREEN}✓${NC} $name (port $port)"
    else
        echo -e "  ${RED}✗${NC} $name (port $port) - 未启动，跳过"
        unset "SERVICES[$name]"
    fi
done
echo ""

if [ ${#SERVICES[@]} -eq 0 ]; then
    echo -e "${RED}没有可用的服务，请先启动至少一个！${NC}"
    exit 1
fi

# 压测
echo -e "${CYAN}开始压测 (Ctrl+C 可中断)...${NC}"
echo ""

for name in "${!SERVICES[@]}"; do
    url="${SERVICES[$name]}"
    echo "────────────────────────────────────────"
    echo -e "${GREEN}>>> $name${NC}"
    echo "    URL: $url"
    echo "────────────────────────────────────────"
    wrk -t$THREADS -c$CONNECTIONS -d${DURATION}s "$url"
    echo ""
done

echo "========================================"
echo " 压测完成！"
echo "========================================"
