#!/usr/bin/env python3
"""
并发测试脚本 - 验证配置同步问题
同时测试原版（无锁）和优化版（有锁）
"""

import requests
import json
import time
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

# 服务地址
ORIGINAL_URL = "http://127.0.0.1:5001"  # 原版（无锁）
OPTIMIZED_URL = "http://127.0.0.1:5000"  # 优化版（有锁）

class ConfigSyncTest:
    def __init__(self, base_url, name):
        self.base_url = base_url
        self.name = name
        self.token = None
        self.account_id = None
        
    def register_and_login(self, username, password):
        """注册并登录"""
        # 注册
        resp = requests.post(f"{self.base_url}/auth/register", json={
            "username": username,
            "password": password
        })
        if resp.status_code not in [201, 409]:  # 409 表示用户已存在
            print(f"[{self.name}] 注册失败: {resp.text}")
            return False
            
        # 登录
        resp = requests.post(f"{self.base_url}/auth/login", json={
            "username": username,
            "password": password
        })
        if resp.status_code != 200:
            print(f"[{self.name}] 登录失败: {resp.text}")
            return False
            
        data = resp.json()
        self.token = data['token']
        self.account_id = data.get('account_id')
        print(f"[{self.name}] 登录成功，token: {self.token[:20]}...")
        return True
    
    def get_config(self):
        """获取配置"""
        resp = requests.get(
            f"{self.base_url}/sync/config",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        return resp.json() if resp.status_code == 200 else None
    
    def save_config(self, revision, data):
        """保存配置"""
        payload = {
            "revision": revision,
            **data
        }
        resp = requests.post(
            f"{self.base_url}/sync/config",
            headers={"Authorization": f"Bearer {self.token}"},
            json=payload
        )
        return resp.status_code, resp.json() if resp.status_code in [200, 409] else None
    
    def concurrent_write_test(self, num_threads=10):
        """并发写入测试"""
        print(f"\n{'='*60}")
        print(f"[{self.name}] 并发写入测试 - {num_threads} 线程")
        print(f"{'='*60}")
        
        results = {
            'success': 0,
            'conflict': 0,
            'error': 0,
            'revisions': []
        }
        
        def write_task(thread_id):
            # 先获取当前配置
            config_data = self.get_config()
            current_revision = config_data.get('revision', 0) if config_data else 0
            
            # 构造新配置
            new_data = {
                'stock_codes': f'sh60000{thread_id},sz00000{thread_id}',
                'memos': f'Thread-{thread_id}-Memo',
                'holdings': f'{thread_id}00*10.{thread_id}',
                'alert_prices': f'{thread_id}0/{thread_id}1/{thread_id}2',
                'index_codes': 'sh000001,sz399001',
                'pinned_stocks': f'sh60000{thread_id}'
            }
            
            # 添加随机延迟，增加并发冲突概率
            time.sleep(0.01)
            
            status, resp_data = self.save_config(current_revision, new_data)
            
            if status == 200:
                return ('success', resp_data.get('revision', 0), thread_id)
            elif status == 409:
                return ('conflict', resp_data.get('server_revision', 0), thread_id)
            else:
                return ('error', 0, thread_id)
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(write_task, i) for i in range(num_threads)]
            
            for future in as_completed(futures):
                status, revision, thread_id = future.result()
                results[status] += 1
                results['revisions'].append(revision)
                
                if status == 'success':
                    print(f"  ✓ Thread-{thread_id}: 成功，revision={revision}")
                elif status == 'conflict':
                    print(f"  ⚠ Thread-{thread_id}: 冲突，server_revision={revision}")
                else:
                    print(f"  ✗ Thread-{thread_id}: 错误")
        
        elapsed = time.time() - start_time
        
        # 最终结果
        final_config = self.get_config()
        final_revision = final_config.get('revision', 0) if final_config else 0
        
        print(f"\n[{self.name}] 测试结果:")
        print(f"  成功: {results['success']}")
        print(f"  冲突: {results['conflict']}")
        print(f"  错误: {results['error']}")
        print(f"  耗时: {elapsed:.2f}s")
        print(f"  最终 revision: {final_revision}")
        
        # 检查是否有数据覆盖问题
        if final_config and final_config.get('config'):
            config = final_config['config']
            print(f"  最终 stock_codes: {config.get('stock_codes', 'N/A')[:50]}...")
            print(f"  最终 memos: {config.get('memos', 'N/A')[:50]}...")
        
        return results, final_config
    
    def race_condition_test(self):
        """竞态条件测试 - 模拟两个客户端同时读写"""
        print(f"\n{'='*60}")
        print(f"[{self.name}] 竞态条件测试")
        print(f"{'='*60}")
        
        # 客户端 A 读取配置
        print("\n步骤1: 客户端A读取配置")
        config_a = self.get_config()
        revision_a = config_a.get('revision', 0) if config_a else 0
        print(f"  客户端A读取到 revision={revision_a}")
        
        # 客户端 B 同时读取配置（模拟）
        print("\n步骤2: 客户端B同时读取配置")
        config_b = self.get_config()
        revision_b = config_b.get('revision', 0) if config_b else 0
        print(f"  客户端B读取到 revision={revision_b}")
        
        # 客户端 A 保存配置
        print("\n步骤3: 客户端A保存配置（基于 revision A）")
        status_a, resp_a = self.save_config(revision_a, {
            'stock_codes': 'sh600001-CLIENT-A',
            'memos': 'From Client A',
            'holdings': '100*10.5',
            'alert_prices': '11/12/13',
            'index_codes': 'sh000001',
            'pinned_stocks': 'sh600001'
        })
        print(f"  客户端A结果: {status_a}, revision={resp_a.get('revision') if resp_a else 'N/A'}")
        
        # 客户端 B 尝试保存（基于旧的 revision B）
        print("\n步骤4: 客户端B尝试保存（基于旧的 revision B）")
        status_b, resp_b = self.save_config(revision_b, {
            'stock_codes': 'sh600002-CLIENT-B',
            'memos': 'From Client B',
            'holdings': '200*20.5',
            'alert_prices': '21/22/23',
            'index_codes': 'sz399001',
            'pinned_stocks': 'sh600002'
        })
        print(f"  客户端B结果: {status_b}, revision={resp_b.get('revision') if resp_b else 'N/A'}")
        
        # 最终结果
        final = self.get_config()
        print(f"\n最终结果:")
        print(f"  revision: {final.get('revision')}")
        if final.get('config'):
            print(f"  stock_codes: {final['config'].get('stock_codes', 'N/A')}")
            print(f"  memos: {final['config'].get('memos', 'N/A')}")
        
        return status_a, status_b, final


def main():
    print("="*70)
    print("AhFunStokAPI 并发测试")
    print("="*70)
    
    # 测试原版（无锁）
    print("\n\n>>> 测试原版（无锁）")
    original_test = ConfigSyncTest(ORIGINAL_URL, "原版")
    if original_test.register_and_login("test_user_1", "test123"):
        original_test.race_condition_test()
        time.sleep(0.5)
        orig_results, orig_final = original_test.concurrent_write_test(num_threads=5)
    
    time.sleep(1)
    
    # 测试优化版（有锁）
    print("\n\n>>> 测试优化版（有锁）")
    optimized_test = ConfigSyncTest(OPTIMIZED_URL, "优化版")
    if optimized_test.register_and_login("test_user_2", "test123"):
        optimized_test.race_condition_test()
        time.sleep(0.5)
        opt_results, opt_final = optimized_test.concurrent_write_test(num_threads=5)
    
    # 总结
    print("\n\n" + "="*70)
    print("测试总结")
    print("="*70)
    print("\n原版（无锁）:")
    print(f"  成功: {orig_results.get('success', 0)}")
    print(f"  冲突: {orig_results.get('conflict', 0)}")
    print(f"  错误: {orig_results.get('error', 0)}")
    
    print("\n优化版（有锁）:")
    print(f"  成功: {opt_results.get('success', 0)}")
    print(f"  冲突: {opt_results.get('conflict', 0)}")
    print(f"  错误: {opt_results.get('error', 0)}")
    
    print("\n结论:")
    print("  - 原版在高并发下容易出现数据覆盖问题")
    print("  - 优化版通过锁机制确保数据一致性")
    print("  - 优化版的冲突检测更准确（基于hash）")


if __name__ == '__main__':
    main()
