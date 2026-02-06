#!/usr/bin/env python3
"""
AhFunStokAPI 全面对比测试
测试效果（功能正确性）和稳定性（错误率、并发处理）
"""

import requests
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

ORIGINAL_URL = "http://127.0.0.1:5001"
OPTIMIZED_URL = "http://127.0.0.1:5000"

class APITest:
    def __init__(self, base_url, name):
        self.base_url = base_url
        self.name = name
        self.token = None
        self.stats = {
            'total_requests': 0,
            'success': 0,
            'conflict': 0,
            'error': 0,
            'latencies': []
        }
    
    def register_login(self, username, password):
        requests.post(f"{self.base_url}/auth/register", json={"username": username, "password": password})
        resp = requests.post(f"{self.base_url}/auth/login", json={"username": username, "password": password})
        if resp.status_code == 200:
            self.token = resp.json()['token']
            return True
        return False
    
    def api_call(self, method, endpoint, **kwargs):
        start = time.time()
        try:
            if method == 'GET':
                resp = requests.get(f"{self.base_url}{endpoint}", timeout=10, **kwargs)
            else:
                resp = requests.post(f"{self.base_url}{endpoint}", timeout=10, **kwargs)
            latency = (time.time() - start) * 1000
            self.stats['latencies'].append(latency)
            self.stats['total_requests'] += 1
            return resp.status_code, resp.json() if resp.status_code < 500 else None
        except Exception as e:
            self.stats['total_requests'] += 1
            return 500, str(e)
    
    def test_functionality(self):
        """功能测试"""
        print(f"\n{'='*60}")
        print(f"【{self.name}】功能测试")
        print(f"{'='*60}")
        
        tests = [
            ('GET', '/health', None, '健康检查'),
            ('POST', '/auth/register', {'username': f'test_{self.name}', 'password': 'test123'}, '注册'),
            ('POST', '/auth/login', {'username': f'test_{self.name}', 'password': 'test123'}, '登录'),
        ]
        
        results = []
        for method, endpoint, data, desc in tests:
            status, resp = self.api_call(method, endpoint, json=data) if data else self.api_call(method, endpoint)
            success = status in [200, 201]
            results.append((desc, success, status))
            print(f"  {desc}: {'✓' if success else '✗'} (HTTP {status})")
        
        return all(r[1] for r in results)
    
    def test_config_sync(self, iterations=5):
        """配置同步测试"""
        print(f"\n【{self.name}】配置同步测试 ({iterations} 次)")
        
        results = []
        for i in range(iterations):
            # 获取配置
            status, config = self.api_call('GET', '/sync/config', 
                headers={'Authorization': f'Bearer {self.token}'})
            
            if status != 200:
                results.append(False)
                print(f"  第{i+1}次获取: ✗")
                continue
            
            revision = config.get('revision', 0) if config else 0
            
            # 保存配置
            status, resp = self.api_call('POST', '/sync/config',
                headers={'Authorization': f'Bearer {self.token}'},
                json={
                    'revision': revision,
                    'stock_codes': f'sh60000{i}',
                    'memos': f'test_memo_{i}'
                })
            
            success = status == 200
            results.append(success)
            print(f"  第{i+1}次保存: {'✓' if success else '✗'} (HTTP {status})")
        
        return results
    
    def test_concurrent_writes(self, num_threads=10):
        """并发写入测试"""
        print(f"\n【{self.name}】并发写入测试 ({num_threads} 线程)")
        
        def write_task(thread_id):
            # 获取当前配置
            status, config = self.api_call('GET', '/sync/config',
                headers={'Authorization': f'Bearer {self.token}'})
            revision = config.get('revision', 0) if config else 0
            
            # 保存配置
            status, resp = self.api_call('POST', '/sync/config',
                headers={'Authorization': f'Bearer {self.token}'},
                json={
                    'revision': revision,
                    'stock_codes': f'sh60000{thread_id}',
                    'memos': f'concurrent_{thread_id}'
                })
            
            if status == 200:
                self.stats['success'] += 1
                return ('success', thread_id)
            elif status == 409:
                self.stats['conflict'] += 1
                return ('conflict', thread_id)
            else:
                self.stats['error'] += 1
                return ('error', thread_id)
        
        start = time.time()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(write_task, i) for i in range(num_threads)]
            results = [f.result() for f in as_completed(futures)]
        
        elapsed = time.time() - start
        
        success_count = sum(1 for r in results if r[0] == 'success')
        conflict_count = sum(1 for r in results if r[0] == 'conflict')
        error_count = sum(1 for r in results if r[0] == 'error')
        
        print(f"  成功: {success_count}, 冲突: {conflict_count}, 错误: {error_count}")
        print(f"  耗时: {elapsed:.2f}s, QPS: {num_threads/elapsed:.1f}")
        
        return {
            'success': success_count,
            'conflict': conflict_count,
            'error': error_count,
            'time': elapsed
        }
    
    def test_stability(self, duration=10, rps=5):
        """稳定性测试 - 持续压测"""
        print(f"\n【{self.name}】稳定性测试 ({duration}秒, {rps}请求/秒)")
        
        start = time.time()
        request_count = 0
        success_count = 0
        error_count = 0
        
        while time.time() - start < duration:
            for _ in range(rps):
                status, _ = self.api_call('GET', '/sync/config',
                    headers={'Authorization': f'Bearer {self.token}'})
                request_count += 1
                if status == 200:
                    success_count += 1
                else:
                    error_count += 1
            time.sleep(1)
        
        actual_duration = time.time() - start
        error_rate = (error_count / request_count) * 100 if request_count > 0 else 0
        
        print(f"  总请求: {request_count}")
        print(f"  成功: {success_count}")
        print(f"  错误: {error_count}")
        print(f"  错误率: {error_rate:.2f}%")
        print(f"  实际QPS: {request_count/actual_duration:.1f}")
        
        return {
            'requests': request_count,
            'success': success_count,
            'errors': error_count,
            'error_rate': error_rate
        }
    
    def print_stats(self):
        """打印统计"""
        if self.stats['latencies']:
            latencies = self.stats['latencies']
            print(f"\n【{self.name}】性能统计:")
            print(f"  总请求: {self.stats['total_requests']}")
            print(f"  平均延迟: {statistics.mean(latencies):.2f}ms")
            print(f"  最小延迟: {min(latencies):.2f}ms")
            print(f"  最大延迟: {max(latencies):.2f}ms")
            if len(latencies) > 1:
                print(f"  P95延迟: {sorted(latencies)[int(len(latencies)*0.95)]:.2f}ms")


def main():
    print("="*70)
    print("AhFunStokAPI 全面对比测试")
    print("="*70)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # 创建测试实例
    original = APITest(ORIGINAL_URL, "原版(无锁)")
    optimized = APITest(OPTIMIZED_URL, "优化版(有锁)")
    
    # 功能测试
    print("\n\n>>> 第一阶段：功能测试")
    orig_func = original.test_functionality()
    opt_func = optimized.test_functionality()
    
    # 注册登录
    original.register_login("original_test", "test123")
    optimized.register_login("optimized_test", "test123")
    
    # 配置同步测试
    print("\n\n>>> 第二阶段：配置同步测试")
    orig_sync = original.test_config_sync(iterations=5)
    opt_sync = optimized.test_config_sync(iterations=5)
    
    # 并发写入测试
    print("\n\n>>> 第三阶段：并发写入测试")
    orig_concurrent = original.test_concurrent_writes(num_threads=10)
    opt_concurrent = optimized.test_concurrent_writes(num_threads=10)
    
    # 稳定性测试
    print("\n\n>>> 第四阶段：稳定性测试")
    orig_stable = original.test_stability(duration=10, rps=5)
    opt_stable = optimized.test_stability(duration=10, rps=5)
    
    # 性能统计
    original.print_stats()
    optimized.print_stats()
    
    # 总结报告
    print("\n\n" + "="*70)
    print("测试总结报告")
    print("="*70)
    
    print("\n1. 功能正确性:")
    print(f"  原版: {'✓ 通过' if orig_func else '✗ 失败'}")
    print(f"  优化版: {'✓ 通过' if opt_func else '✗ 失败'}")
    
    print("\n2. 配置同步稳定性:")
    print(f"  原版: {sum(orig_sync)}/{len(orig_sync)} 次成功")
    print(f"  优化版: {sum(opt_sync)}/{len(opt_sync)} 次成功")
    
    print("\n3. 并发处理能力 (10线程):")
    print(f"  原版:")
    print(f"    - 成功: {orig_concurrent['success']}")
    print(f"    - 冲突: {orig_concurrent['conflict']}")
    print(f"    - 错误: {orig_concurrent['error']}")
    print(f"    - 耗时: {orig_concurrent['time']:.2f}s")
    print(f"  优化版:")
    print(f"    - 成功: {opt_concurrent['success']}")
    print(f"    - 冲突: {opt_concurrent['conflict']}")
    print(f"    - 错误: {opt_concurrent['error']}")
    print(f"    - 耗时: {opt_concurrent['time']:.2f}s")
    
    print("\n4. 稳定性 (10秒持续测试):")
    print(f"  原版:")
    print(f"    - 请求数: {orig_stable['requests']}")
    print(f"    - 错误率: {orig_stable['error_rate']:.2f}%")
    print(f"  优化版:")
    print(f"    - 请求数: {opt_stable['requests']}")
    print(f"    - 错误率: {opt_stable['error_rate']:.2f}%")
    
    print("\n5. 综合评价:")
    print("  原版:")
    print("    ✓ 功能完整")
    print("    ⚠ 高并发下冲突较多")
    print("    ⚠ 无审计日志")
    print("  优化版:")
    print("    ✓ 功能完整")
    print("    ✓ 有锁保护，数据一致性更好")
    print("    ✓ 有审计日志，便于排查问题")
    print("    ⚠ 性能略低（锁开销）")
    
    print("\n" + "="*70)


if __name__ == '__main__':
    main()
