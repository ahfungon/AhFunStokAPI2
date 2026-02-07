#!/usr/bin/env python3
"""
MySQL 版本并发测试
"""

import requests
import time
import threading
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
        resp = requests.post(f"{self.base_url}/auth/register", json={
            "username": username,
            "password": password
        })
        if resp.status_code not in [201, 409]:
            print(f"[{self.name}] 注册失败: {resp.text}")
            return False
            
        resp = requests.post(f"{self.base_url}/auth/login", json={
            "username": username,
            "password": password
        })
        if resp.status_code != 200:
            print(f"[{self.name}] 登录失败: {resp.text}")
            return False
            
        data = resp.json()
        self.token = data['token']
        print(f"[{self.name}] 登录成功")
        return True
    
    def get_config(self):
        resp = requests.get(
            f"{self.base_url}/sync/config",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        return resp.json() if resp.status_code == 200 else None
    
    def save_config(self, revision, data):
        payload = {"revision": revision, **data}
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
        
        results = {'success': 0, 'conflict': 0, 'error': 0, 'revisions': []}
        
        def write_task(thread_id):
            config_data = self.get_config()
            current_revision = config_data.get('revision', 0) if config_data else 0
            
            new_data = {
                'stock_codes': f'sh60000{thread_id},sz00000{thread_id}',
                'memos': f'Thread-{thread_id}-Memo',
                'holdings': f'{thread_id}00*10.{thread_id}',
                'alert_prices': f'{thread_id}0/{thread_id}1/{thread_id}2',
                'index_codes': 'sh000001,sz399001',
                'pinned_stocks': f'sh60000{thread_id}'
            }
            
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
        final_config = self.get_config()
        final_revision = final_config.get('revision', 0) if final_config else 0
        
        print(f"\n[{self.name}] 测试结果:")
        print(f"  成功: {results['success']}")
        print(f"  冲突: {results['conflict']}")
        print(f"  错误: {results['error']}")
        print(f"  耗时: {elapsed:.2f}s")
        print(f"  最终 revision: {final_revision}")
        
        return results, final_config


def main():
    print("="*70)
    print("AhFunStokAPI MySQL 并发测试")
    print("="*70)
    
    print("\n\n>>> 测试原版（无锁）")
    original_test = ConfigSyncTest(ORIGINAL_URL, "原版")
    if original_test.register_and_login("test_mysql_1", "test123"):
        orig_results, orig_final = original_test.concurrent_write_test(num_threads=10)
    
    time.sleep(1)
    
    print("\n\n>>> 测试优化版（有锁）")
    optimized_test = ConfigSyncTest(OPTIMIZED_URL, "优化版")
    if optimized_test.register_and_login("test_mysql_2", "test123"):
        opt_results, opt_final = optimized_test.concurrent_write_test(num_threads=10)
    
    print("\n\n" + "="*70)
    print("测试总结")
    print("="*70)
    print(f"\n原版（无锁）:")
    print(f"  成功: {orig_results.get('success', 0)}")
    print(f"  冲突: {orig_results.get('conflict', 0)}")
    print(f"  错误: {orig_results.get('error', 0)}")
    
    print(f"\n优化版（有锁）:")
    print(f"  成功: {opt_results.get('success', 0)}")
    print(f"  冲突: {opt_results.get('conflict', 0)}")
    print(f"  错误: {opt_results.get('error', 0)}")


if __name__ == '__main__':
    main()
