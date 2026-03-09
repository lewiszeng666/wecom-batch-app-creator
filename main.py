"""
main.py
企业微信批量创建应用工具 - 主入口

入参（均可通过命令行覆盖 config.json 中的默认值）：
  --corp-id       企业微信 CORP_ID（默认 ww95aca10dfcf3d6e2）
  --member        可见范围成员名（默认 曾君亮）
  --count         创建数量
  --ip            OpenClaw 公网 IP（默认 101.35.102.240）
  --config        配置文件路径（默认 config.json）
  --visible       有头模式（可观察浏览器操作过程，调试用）

出参（保存到 output/app_configs.json）：
  CORP_ID、AgentId、Secret（xxx，需手工填入）、Token、EncodingAESKey

用法示例：
    # 使用默认配置
    python main.py

    # 指定 OpenClaw IP（最常用的覆盖参数）
    python main.py --ip 1.2.3.4

    # 指定创建数量 + IP
    python main.py --count 5 --ip 1.2.3.4

    # 有头模式调试
    python main.py --count 1 --visible

    # 完整覆盖所有参数
    python main.py --corp-id wwXXXXXXXX --member 张三 --count 3 --ip 1.2.3.4
"""

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

from batch_creator import BatchAppCreator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("batch_creator.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

DEFAULT_CORP_ID = "ww95aca10dfcf3d6e2"
DEFAULT_MEMBER = "曾君亮"
DEFAULT_OPENCLAW_IP = "101.35.102.240"


def main():
    parser = argparse.ArgumentParser(
        description="企业微信批量创建应用工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python main.py                          # 使用 config.json 默认配置
  python main.py --ip 1.2.3.4            # 指定 OpenClaw 公网 IP
  python main.py --count 5 --ip 1.2.3.4  # 创建 5 个应用
  python main.py --count 1 --visible     # 有头模式测试
        """,
    )
    parser.add_argument(
        "--corp-id",
        default=None,
        metavar="CORP_ID",
        help=f"企业微信 CORP_ID（默认 {DEFAULT_CORP_ID}）",
    )
    parser.add_argument(
        "--member",
        default=None,
        metavar="MEMBER_NAME",
        help=f"应用可见范围成员名（默认 {DEFAULT_MEMBER}）",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        metavar="N",
        help="批量创建数量（覆盖 config.json 中的 create_count）",
    )
    parser.add_argument(
        "--ip",
        default=None,
        metavar="OPENCLAW_IP",
        help=f"OpenClaw 公网 IP（默认 {DEFAULT_OPENCLAW_IP}）",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        metavar="PATH",
        help="配置文件路径（默认 config.json）",
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="有头模式：显示浏览器操作过程（调试用）",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        dest="no_headless",
        help="关闭 headless 模式（本地调试推荐，可观察浏览器操作）",
    )
    args = parser.parse_args()

    # ── 加载配置文件 ──
    config_path = args.config
    if not Path(config_path).exists():
        # 如果 config.json 不存在，从 config.example.json 生成默认配置
        if Path("config.example.json").exists():
            with open("config.example.json", "r", encoding="utf-8") as f:
                config = json.load(f)
            logger.info("config.json 不存在，使用 config.example.json 默认值")
        else:
            logger.error(f"配置文件不存在: {config_path}")
            logger.error("请复制 config.example.json 为 config.json 并填写配置")
            sys.exit(1)
    else:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    # ── 命令行参数覆盖配置文件 ──
    if args.corp_id:
        config["corp_id"] = args.corp_id
    if args.member:
        config["visible_member"] = args.member
    if args.count:
        config["create_count"] = args.count
    if args.ip:
        config["openclaw_ip"] = args.ip
    if args.visible or args.no_headless:
        config["headless"] = False

    # ── 填充默认值（如果配置文件中也没有）──
    config.setdefault("corp_id", DEFAULT_CORP_ID)
    config.setdefault("visible_member", DEFAULT_MEMBER)
    config.setdefault("openclaw_ip", DEFAULT_OPENCLAW_IP)
    config.setdefault("create_count", 1)
    config.setdefault("app_name_prefix", "openclaw")
    config.setdefault("app_description", "与openclaw通信通道")
    config.setdefault("logo_path", "openclaw_logo.png")
    config.setdefault("output_file", "output/app_configs.json")
    config.setdefault("headless", True)
    config.setdefault("browser_data_dir", "browser_data")

    # ── 检查 Logo 文件 ──
    logo_path = config["logo_path"]
    if not Path(logo_path).exists():
        logger.error(f"Logo 文件不存在: {logo_path}")
        logger.error("请确保 openclaw_logo.png 在当前目录（已包含在仓库中）")
        sys.exit(1)

    # ── 检查浏览器会话 ──
    browser_data_dir = config["browser_data_dir"]
    if not Path(browser_data_dir).exists() or not any(Path(browser_data_dir).iterdir()):
        logger.error(f"浏览器会话目录为空: {browser_data_dir}")
        logger.error("请先运行 python save_cookie.py 完成扫码登录")
        sys.exit(1)

    # ── 打印配置摘要 ──
    webhook_url = f"http://{config['openclaw_ip']}:3000/wecom"
    print("\n" + "═" * 60)
    print("  企业微信批量创建应用工具")
    print("═" * 60)
    print(f"  CORP_ID:       {config['corp_id']}")
    print(f"  可见范围:      {config['visible_member']}")
    print(f"  创建数量:      {config['create_count']}")
    print(f"  OpenClaw IP:   {config['openclaw_ip']}")
    print(f"  Webhook URL:   {webhook_url}")
    print(f"  应用名称规则:  N号{config['app_name_prefix']}（N 从 1 开始）")
    print(f"  应用介绍:      {config['app_description']}")
    print(f"  无头模式:      {config['headless']}")
    print(f"  输出文件:      {config['output_file']}")
    print("═" * 60 + "\n")

    # ── 将最终配置写入临时文件（避免修改原 config.json）──
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(config, tmp, ensure_ascii=False, indent=2)
    tmp.close()
    effective_config_path = tmp.name

    # ── 执行批量创建 ──
    creator = BatchAppCreator(config_path=effective_config_path)
    try:
        results = creator.run()
        print(f"\n✅ 全部完成，成功创建 {len(results)} 个应用")
        print(f"📄 详细配置: {config['output_file']}")
        print("\n⚠️  下一步：请在企微 App 查看各应用 Secret，填入 output/app_configs.json 的 'secret' 字段\n")
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("用户中断，已保存已创建的应用配置")
        sys.exit(0)
    finally:
        # 清理临时配置文件
        Path(effective_config_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
