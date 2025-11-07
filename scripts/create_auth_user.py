'''
Description: 创建认证用户脚本
Author: zyq
Date: 2025-09-29 16:29:10
LastEditors: zyq
LastEditTime: 2025-11-07 16:23:13
'''
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from core.storage.mongo_storage import MongoStorage
from core.auth.user_storage import AuthUserStorage
from core.config import load_app_config

def create_auth_user(business_name: str):
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
    
    # 检查用户是否已存在
    username = f"{business_name}_auth_user"
    try:
        existing_user = user_storage.get_user_by_username(username)
        if existing_user:
            print(f"⚠️  业务 '{business_name}' 的认证用户已存在!")
            print("=" * 50)
            print(f"👤 用户名: {existing_user.username}")
            print(f"🆔 用户ID: {existing_user.user_id}")
            print(f"📊 状态: {existing_user.status}")
            print(f"⏰ 创建时间: {existing_user.created_at}")
            print(f"🔐 最后登录: {existing_user.last_login or '从未登录'}")
            print("=" * 50)
            print("💡 如需重新创建，请联系系统管理员删除现有用户")
            return
    except Exception:
        # 用户不存在，继续创建
        pass
    
    # 使用简化的全权限
    permissions = ["*"]
    print(f"📋 使用权限: 全部服务权限")
    
    # 创建用户
    try:
        user, password = user_storage.create_user(business_name, permissions)
        
        print("\n✅ 认证用户创建成功!")
        print("=" * 50)
        print(f"🏢 业务名称: {business_name}")
        print(f"👤 用户名: {user.username}")
        print(f"🔑 密码: {password}")
        print(f"🆔 用户ID: {user.user_id}")
        print(f"📜 权限: 全部服务权限")
        print(f"⏰ 创建时间: {user.created_at}")
        print("=" * 50)
        print("\n⚠️  请妥善保管以上信息，密码不会再次显示!")
        print("💡 业务方可使用以上用户名和密码调用认证接口获取token")
        print("💡 测试登录命令:")
        print(f'curl -X POST "http://localhost:20000/auth/login" \\')
        print(f'  -H "Content-Type: application/json" \\')
        print(f'  -d \'{{"username": "{user.username}", "password": "{password}"}}\'')
        
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
            permissions = user.get('permissions', [])
            perm_display = "全部服务权限" if permissions == ["*"] else ', '.join(permissions) if permissions else "无权限"
            
            print(f"{status_emoji} {user.get('username')}")
            print(f"   用户ID: {user.get('user_id')}")
            print(f"   权限: {perm_display}")
            print(f"   状态: {user.get('status')}")
            print(f"   创建时间: {user.get('created_at')}")
            print(f"   最后登录: {user.get('last_login', '从未登录')}")
            print("-" * 80)
            
    except Exception as e:
        print(f"❌ 获取用户列表失败: {str(e)}")

def main():
    parser = argparse.ArgumentParser(
        description="AI服务平台认证用户管理工具", 
        epilog="""
使用示例:
  创建用户: python scripts/create_auth_user.py create myapp
  列出用户: python scripts/create_auth_user.py list
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 创建用户命令
    create_parser = subparsers.add_parser("create", help="创建认证用户")
    create_parser.add_argument("business_name", help="业务名称 (如: law_ai, finance_ai)")
    
    # 列出用户命令
    list_parser = subparsers.add_parser("list", help="列出所有认证用户")
    
    args = parser.parse_args()
    
    if args.command == "create":
        create_auth_user(args.business_name)
    elif args.command == "list":
        list_auth_users()
    else:
        parser.print_help()
        print("\n💡 常用命令:")
        print("  python scripts/create_auth_user.py create myapp")
        print("  python scripts/create_auth_user.py list")

if __name__ == "__main__":
    main()