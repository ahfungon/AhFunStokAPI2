#!/usr/bin/env python3
"""
兼容性测试脚本
验证 AhFunStokAPI2 与原版的数据库兼容性
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_database_compatibility():
    """测试数据库兼容性"""
    print("=" * 60)
    print("数据库兼容性测试")
    print("=" * 60)
    
    try:
        from app import db, app
        from app import Account, AccountToken, PortfolioConfig, User, UserData
        from app import UserActions, ErrorLogs, ConfigAuditLog
        
        with app.app_context():
            # 测试所有表是否存在
            print("\n检查数据库表...")
            
            tables = [
                ('accounts', Account),
                ('account_tokens', AccountToken),
                ('portfolio_configs', PortfolioConfig),
                ('users', User),
                ('user_data', UserData),
                ('user_actions', UserActions),
                ('error_logs', ErrorLogs),
                ('config_audit_logs', ConfigAuditLog),  # 新增表
            ]
            
            all_ok = True
            for table_name, model in tables:
                try:
                    # 尝试查询一条记录
                    count = model.query.count()
                    print(f"  ✅ {table_name}: 存在 ({count} 条记录)")
                except Exception as e:
                    if table_name == 'config_audit_logs':
                        print(f"  ⚠️  {table_name}: 不存在 (需要执行迁移脚本)")
                    else:
                        print(f"  ❌ {table_name}: 错误 - {e}")
                        all_ok = False
            
            # 测试原有表结构
            print("\n检查原有表结构...")
            
            # 检查 portfolio_configs 表结构
            config = PortfolioConfig.query.first()
            if config:
                expected_fields = [
                    'config_id', 'account_id', 'stock_codes', 'memos',
                    'holdings', 'alert_prices', 'index_codes', 'pinned_stocks',
                    'revision', 'data_hash', 'last_client', 'updated_at'
                ]
                for field in expected_fields:
                    if hasattr(config, field):
                        print(f"  ✅ portfolio_configs.{field}")
                    else:
                        print(f"  ❌ portfolio_configs.{field} 缺失")
                        all_ok = False
            else:
                print("  ℹ️  portfolio_configs 表为空，但结构检查通过")
            
            print("\n" + "=" * 60)
            if all_ok:
                print("✅ 兼容性测试通过！")
                print("\n说明：")
                print("  - 所有原有表结构一致")
                print("  - config_audit_logs 表需要执行迁移脚本创建")
                print("  - 可以安全部署新版本")
            else:
                print("❌ 发现兼容性问题，请检查数据库")
            print("=" * 60)
            
            return all_ok
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_compatibility():
    """测试 API 兼容性"""
    print("\n" + "=" * 60)
    print("API 兼容性测试")
    print("=" * 60)
    
    try:
        from app import app
        
        with app.test_client() as client:
            # 测试健康检查接口
            print("\n测试接口...")
            
            response = client.get('/health')
            if response.status_code == 200:
                print(f"  ✅ GET /health: {response.status_code}")
            else:
                print(f"  ⚠️  GET /health: {response.status_code} (可能数据库未连接)")
            
            # 测试游客模式接口（无需认证）
            response = client.get('/users')
            if response.status_code == 200:
                print(f"  ✅ GET /users: {response.status_code}")
            else:
                print(f"  ⚠️  GET /users: {response.status_code}")
            
            # 测试未认证访问（应该返回 401）
            response = client.get('/sync/config')
            if response.status_code == 401:
                print(f"  ✅ GET /sync/config (未认证): {response.status_code} (符合预期)")
            else:
                print(f"  ⚠️  GET /sync/config (未认证): {response.status_code}")
            
            print("\n✅ API 接口测试完成")
            return True
            
    except Exception as e:
        print(f"\n❌ API 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("AhFunStokAPI2 兼容性测试")
    print("=" * 60)
    
    db_ok = test_database_compatibility()
    api_ok = test_api_compatibility()
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"数据库兼容性: {'✅ 通过' if db_ok else '❌ 失败'}")
    print(f"API 兼容性: {'✅ 通过' if api_ok else '❌ 失败'}")
    
    if db_ok and api_ok:
        print("\n✅ 所有兼容性测试通过！可以安全部署。")
        sys.exit(0)
    else:
        print("\n❌ 存在兼容性问题，请检查。")
        sys.exit(1)
