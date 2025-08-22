'''
Description: 创建认证用户脚本
Author: zyq
Date: 2025-01-21
'''
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from core.storage.mongo_storage import MongoStorage
from core.auth.user_storage import AuthUserStorage
from core.config import load_app_config

# 预定义权限模板
PERMISSION_TEMPLATES = {
    "basic": ["chat.single_turn", "chat.multi_turn"],
    "premium": ["chat.*", "document.*"],
    "admin": ["chat.*", "document.*", "retrieval.*", "admin.*"],
    "chat_only": ["chat.single_turn", "chat.multi_turn", "chat.models"],
    "document_only": ["document.upload", "document.process", "document.download"]
}

def create_auth_user(business_name: str, permission_template: str = "basic", custom_permissions: list = None):
    """创建认证用户"""
    print(f"🚀 正在为业务 '{business_name}' 创建认证用户...")
    
    # 加载配置
    try:
        config = load_app_config()
    except Exception as e:
        print(f"❌ 配置加载失败: {str(e)}")
        return
    
    # 初始化数据库连接
    try:
        mongo_storage = MongoStorage(
            db_name=config.mongo_database
        )
        user_storage = AuthUserStorage(mongo_storage)
    except Exception as e:
        print(f"❌ 数据库连接失败: {str(e)}")
        return
    
    # 确定权限
    if custom_permissions:
        permissions = custom_permissions
        print(f"📋 使用自定义权限: {permissions}")
    elif permission_template in PERMISSION_TEMPLATES:
        permissions = PERMISSION_TEMPLATES[permission_template]
        print(f"📋 使用权限模板 '{permission_template}': {permissions}")
    else:
        print(f"❌ 未知的权限模板: {permission_template}")
        print(f"💡 可用模板: {', '.join(PERMISSION_TEMPLATES.keys())}")
        return
    
    # 创建用户
    try:
        user, password = user_storage.create_user(business_name, permissions)
        
        print("\n✅ 认证用户创建成功!")
        print("=" * 50)
        print(f"🏢 业务名称: {business_name}")
        print(f"👤 用户名: {user.username}")
        print(f"🔑 密码: {password}")
        print(f"🆔 用户ID: {user.user_id}")
        print(f"📜 权限列表: {', '.join(user.permissions)}")
        print(f"⏰ 创建时间: {user.created_at}")
        print("=" * 50)
        print("\n⚠️  请妥善保管以上信息，密码不会再次显示!")
        print("💡 业务方可使用以上用户名和密码调用认证接口获取token")
        
    except ValueError as e:
        print(f"❌ 创建失败: {str(e)}")
    except Exception as e:
        print(f"❌ 系统错误: {str(e)}")

def list_auth_users():
    """列出所有认证用户"""
    print("📋 正在获取认证用户列表...")
    
    try:
        config = load_app_config()
        mongo_storage = MongoStorage(
            db_name=config.mongo_database
        )
        
        # 直接查询数据库
        collection = mongo_storage.db["auth_users"]
        users = list(collection.find({}, {"password_hash": 0}))
        
        if not users:
            print("📭 暂无认证用户")
            return
        
        print(f"\n📊 共找到 {len(users)} 个认证用户:")
        print("=" * 80)
        for user in users:
            status_emoji = "✅" if user.get("status") == "active" else "❌"
            print(f"{status_emoji} {user.get('username')}")
            print(f"   用户ID: {user.get('user_id')}")
            print(f"   权限: {', '.join(user.get('permissions', []))}")
            print(f"   状态: {user.get('status')}")
            print(f"   创建时间: {user.get('created_at')}")
            print(f"   最后登录: {user.get('last_login', '从未登录')}")
            print("-" * 80)
            
    except Exception as e:
        print(f"❌ 获取用户列表失败: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="AI服务平台认证用户管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 创建用户命令
    create_parser = subparsers.add_parser("create", help="创建认证用户")
    create_parser.add_argument("business_name", help="业务名称 (如: law_ai, finance_ai)")
    create_parser.add_argument(
        "--template", 
        choices=list(PERMISSION_TEMPLATES.keys()),
        default="basic",
        help="权限模板 (默认: basic)"
    )
    create_parser.add_argument(
        "--permissions", 
        nargs="+",
        help="自定义权限列表 (会覆盖模板)"
    )
    
    # 列出用户命令
    list_parser = subparsers.add_parser("list", help="列出所有认证用户")
    
    args = parser.parse_args()
    
    if args.command == "create":
        create_auth_user(
            business_name=args.business_name,
            permission_template=args.template,
            custom_permissions=args.permissions
        )
    elif args.command == "list":
        list_auth_users()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()