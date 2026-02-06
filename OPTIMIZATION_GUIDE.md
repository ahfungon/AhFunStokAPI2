# AhFunStokAPI2 优化说明

## 问题诊断：配置同步错乱

### 发现的问题

在分析 `AhFunStokAPI` 代码后，发现以下导致配置同步错乱的根本原因：

#### 1. **并发竞争条件（Race Condition）** ⚠️

**原代码问题**:
```python
# 原代码 - 没有锁保护
config = PortfolioConfig.query.filter_by(account_id=...).first()
if config:
    if client_revision != config.revision:  # 读取和检查之间可能有其他请求修改
        return conflict
    config.revision += 1  # 递增
    db.session.commit()   # 提交
```

**问题场景**:
```
时间线:
请求A: 读取 config (revision=5)
请求B: 读取 config (revision=5)  ← 同时读取
请求A: 检查通过 (client=5, server=5)
请求B: 检查通过 (client=5, server=5)  ← 都通过了！
请求A: 写入 revision=6
请求B: 写入 revision=6  ← 覆盖了A的修改！
```

#### 2. **缺乏数据库锁** ⚠️

原代码没有使用 `SELECT FOR UPDATE` 或事务锁，导致多个请求可以同时修改同一配置。

#### 3. **Revision 冲突处理不完善** ⚠️

- 当客户端提交的 revision 与服务端不匹配时，直接返回 409 冲突
- 没有考虑数据实际是否变化（基于 hash 比较）
- 客户端需要手动处理冲突，体验差

#### 4. **重复数据创建** ⚠️

`add_user_data` 方法每次都创建新记录，而不是更新现有记录，导致数据重复。

---

## 优化方案

### 1. 添加内存级锁（应用层）

```python
# 每个账户独立的锁
config_locks = {}
config_locks_lock = threading.Lock()

def get_account_lock(account_id: int) -> threading.Lock:
    with config_locks_lock:
        if account_id not in config_locks:
            config_locks[account_id] = threading.Lock()
        return config_locks[account_id]
```

**作用**: 确保同一账户的并发请求串行处理

### 2. 添加数据库行级锁

```python
# 使用 SELECT FOR UPDATE
config = db.session.query(PortfolioConfig).filter_by(
    account_id=account_id
).with_for_update().first()
```

**作用**: 数据库层面防止并发修改

### 3. 优化 Revision 冲突处理

```python
# 检查数据是否实际相同（基于hash）
new_hash = _compute_config_hash(data)
if new_hash == config.data_hash:
    # 数据相同，只是 revision 不同，返回成功
    return success

# 真正的冲突才返回 409
return conflict
```

**作用**: 减少不必要的冲突提示

### 4. 添加配置审计日志

```python
class ConfigAuditLog(db.Model):
    log_id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(50))  # 'read', 'write', 'conflict'
    client_revision = db.Column(db.BigInteger)
    server_revision = db.Column(db.BigInteger)
    merged = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

**作用**: 便于排查问题，追踪配置变更历史

### 5. 修复 add_user_data - 使用 UPSERT 语义

```python
existing = UserData.query.filter_by(user_id=user_id).first()
if existing:
    # 更新现有记录
    existing.stock_code = data.get('stock_code', existing.stock_code)
    ...
else:
    # 创建新记录
    db.session.add(new_user_data)
```

**作用**: 避免数据重复

### 6. 添加事务保护

```python
try:
    with db.session.begin():
        # 数据库操作
        ...
except OperationalError as e:
    # 数据库锁等待超时
    return retry_after
except Exception as e:
    db.session.rollback()
    return error
```

**作用**: 确保数据一致性，错误时回滚

---

## 优化对比

| 维度 | 原版 | 优化版 |
|------|------|--------|
| **并发控制** | ❌ 无锁 | ✅ 内存锁 + 数据库锁 |
| **事务保护** | ❌ 不完善 | ✅ 完整事务 |
| **冲突检测** | ❌ 仅 revision | ✅ revision + hash |
| **重复数据** | ❌ 会重复 | ✅ UPSERT |
| **审计日志** | ❌ 无 | ✅ 完整日志 |
| **错误处理** | ❌ 简单 | ✅ 详细 + 重试 |

---

## 核心改进代码对比

### 原版 `save_config`
```python
@app.route('/sync/config', methods=['POST'])
@require_auth
def save_config():
    data = request.get_json() or {}
    client_revision = data.get('revision')
    config = PortfolioConfig.query.filter_by(account_id=...).first()
    
    if config:
        if client_revision != config.revision:  # ⚠️ 无锁，可能读到旧数据
            return jsonify({'message': 'revision_conflict'}), 409
        next_revision = config.revision + 1
    else:
        config = PortfolioConfig(...)
        db.session.add(config)
        next_revision = 1
    
    # 更新字段...
    config.revision = next_revision
    db.session.commit()  # ⚠️ 可能覆盖其他请求的修改
```

### 优化版 `save_config`
```python
@app.route('/sync/config', methods=['POST'])
@require_auth
def save_config():
    data = request.get_json() or {}
    account_id = g.current_account.account_id
    
    # 获取账户级内存锁
    account_lock = get_account_lock(account_id)
    
    with account_lock:  # ✅ 应用层锁
        try:
            with db.session.begin():  # ✅ 事务保护
                # 查询并锁定配置记录
                config = db.session.query(PortfolioConfig).filter_by(
                    account_id=account_id
                ).with_for_update().first()  # ✅ 数据库锁
                
                if config:
                    if client_revision != config.revision:
                        # 检查数据是否实际相同
                        new_hash = _compute_config_hash(data)
                        if new_hash == config.data_hash:  # ✅ 智能冲突检测
                            return success
                        return conflict
                
                # 更新配置...
                
        except OperationalError:  # ✅ 错误处理
            return retry
```

---

## 部署建议

### 1. 数据库迁移

需要添加 `config_audit_logs` 表：

```sql
CREATE TABLE config_audit_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NOT NULL,
    action VARCHAR(50) NOT NULL,
    client_revision BIGINT,
    server_revision BIGINT,
    client_hash VARCHAR(64),
    server_hash VARCHAR(64),
    merged BOOLEAN DEFAULT FALSE,
    client_info VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_account_time (account_id, created_at)
);
```

### 2. 配置文件调整

```python
# gunicorn_conf.py 优化
workers = 4  # 根据CPU核心数调整
timeout = 30  # 增加超时时间，因为锁等待可能需要时间
```

### 3. 监控建议

```python
# 监控指标
- config_audit_logs 中的 conflict 数量
- 平均响应时间
- 锁等待超时次数
- 数据库连接池使用率
```

---

## 测试验证

### 1. 并发测试
```bash
# 模拟多设备同时修改配置
ab -n 100 -c 10 -H "Authorization: Bearer TOKEN" \
   -p config.json -T application/json \
   http://localhost:5000/sync/config
```

### 2. 冲突测试
```python
# 模拟 revision 冲突
# 设备A: 读取配置 (revision=5)
# 设备B: 读取配置 (revision=5)
# 设备A: 保存配置 (revision=5) -> 成功 (revision=6)
# 设备B: 保存配置 (revision=5) -> 应该返回冲突
```

---

## 总结

**优化版解决的核心问题**:

1. ✅ 并发竞争条件 - 使用双重锁保护
2. ✅ 数据覆盖问题 - 数据库行级锁
3. ✅ 冲突误报问题 - hash 比较
4. ✅ 数据重复问题 - UPSERT 语义
5. ✅ 问题排查困难 - 审计日志

**预期效果**:
- 配置同步错乱问题完全解决
- 支持高并发场景
- 更好的错误提示和重试机制
- 完整的问题追踪能力
