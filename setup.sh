#!/usr/bin/env bash
# ============================================================
# setup.sh — 一键安装脚本（兼容 Ubuntu 22.04+ 受保护 Python）
# ============================================================
set -e

VENV_DIR="$(pwd)/.venv"

echo "════════════════════════════════════════"
echo "  wecom-batch-app-creator 环境安装"
echo "════════════════════════════════════════"

# 1. 检查 Python 版本（需要 3.9+）
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "❌ 未找到 Python，请先安装 python3"
    exit 1
fi
PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PY_VER 已找到: $PYTHON"

# 2. 创建虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 创建虚拟环境: $VENV_DIR"
    $PYTHON -m venv "$VENV_DIR"
else
    echo "✅ 虚拟环境已存在: $VENV_DIR"
fi

# 3. 激活虚拟环境并安装依赖
source "$VENV_DIR/bin/activate"
echo "📦 安装 Python 依赖..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ Python 依赖安装完成"

# 4. 安装 Playwright Chromium
echo "📦 安装 Playwright Chromium（首次约 200MB，请稍候）..."
playwright install chromium
echo "✅ Playwright Chromium 安装完成"

echo ""
echo "════════════════════════════════════════"
echo "  安装完成！使用方式："
echo "════════════════════════════════════════"
echo ""
echo "  # 激活虚拟环境"
echo "  source .venv/bin/activate"
echo ""
echo "  # 创建 3 个应用（默认配置）"
echo "  python main.py --count 3"
echo ""
echo "  # 指定 OpenClaw IP"
echo "  python main.py --count 3 --ip 101.35.102.240"
echo ""
echo "  # 指定可见范围成员"
echo "  python main.py --count 3 --member 张三"
echo ""
echo "  # 或修改 config.json 后直接运行"
echo "  python main.py"
echo ""
echo "  输出文件: output/app_configs.json"
echo "════════════════════════════════════════"
