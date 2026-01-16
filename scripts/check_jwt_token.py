'''
Description: JWT过期与有效性检查脚本
Author: zyq
Date: 2026-01-12 16:52:30
LastEditors: zyq
LastEditTime: 2026-01-12 17:16:00
'''
import sys
import argparse
import time
import datetime
from pathlib import Path

import jwt

# 将项目根目录加入路径，便于读取配置
sys.path.append(str(Path(__file__).parent.parent))

from core.config import load_app_config


def main():
    parser = argparse.ArgumentParser(
        description="解码JWT并对比过期时间与主机UTC时间的工具",
    )
    parser.add_argument("token", help="待校验的JWT字符串")
    parser.add_argument(
        "--secret",
        help="可选，覆盖配置文件中的jwt_secret_key",
        default=None,
    )
    args = parser.parse_args()

    # 加载配置获取密钥
    try:
        config = load_app_config()
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return

    secret_key = args.secret or config.jwt_secret_key
    if not secret_key:
        print("❌ 未获取到JWT密钥，请检查配置或通过 --secret 传入")
        return

    now = datetime.datetime.now(datetime.timezone.utc)

    # 先忽略过期校验，解码完整payload
    try:
        payload = jwt.decode(
            args.token,
            secret_key,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
    except Exception as e:
        print(f"❌ Token解码失败: {e}")
        return

    print("🧾 Token Payload:")
    print(payload)

    exp = payload.get("exp")
    if exp is None:
        print("⚠️ payload中缺少exp字段，无法计算过期时间")
        return

    try:
        exp_dt = datetime.datetime.fromtimestamp(exp, datetime.timezone.utc)
    except Exception as e:
        print(f"⚠️ 解析exp为时间失败: {e}")
        return

    remaining_seconds = exp - time.time()
    status = "未过期" if remaining_seconds > 0 else "已过期"

    print(f"⏰ 当前主机UTC时间: {now.isoformat()}")
    print(f"📅 Token过期时间(UTC): {exp_dt.isoformat()}")
    print(f"⌛ 剩余秒数: {remaining_seconds:.2f}（{status}）")

    # 严格校验签名与过期
    try:
        jwt.decode(args.token, secret_key, algorithms=["HS256"])
        print("✅ 校验通过：签名有效且未过期")
    except jwt.ExpiredSignatureError:
        print("❌ 校验失败：Token已过期")
    except jwt.InvalidTokenError as e:
        print(f"❌ 校验失败：Token无效，原因={e}")


if __name__ == "__main__":
    main()
