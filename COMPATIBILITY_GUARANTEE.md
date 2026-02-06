# AhFunStokAPI2 兼容性保证说明

## 兼容性分析

### ✅ 完全向后兼容

| 项目 | 原版 | 优化版 | 兼容性 |
|------|------|--------|--------|
| **accounts 表** | ✅ | ✅ 未修改 | 100% 兼容 |
| **account_tokens 表** | ✅ | ✅ 未修改 | 100% 兼容 |
| **portfolio_configs 表** | ✅ | ✅ 未修改 | 100% 兼容 |
| **users 表** | ✅ | ✅ 未修改 | 100% 兼容 |
| **user_data 表** | ✅ | ✅ 未修改 | 100% 兼容 |
| **user_actions 表** | ✅ | ✅ 未修改 | 100% 兼容 |
| **error_logs 表** | ✅ | ✅ 未修改 | 100% 兼容 |
| **config_audit_logs 表** | ❌ 无 | ✅ 新增 | 不影响旧版 |

### 结论
**优化版只新增了一个表，所有原有表结构完全一致，完全向后兼容！**

---

## 迁移方案（保证兼容性）

### 方案一：安全迁移（推荐）

```bash
# 1. 备份数据库
mysqldump -u ahfunstock -p api.ahfun.me > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. 执行迁移（只新增 audit 表，不影响其他表）
mysql -u ahfunstock -p api.ahfun.me < migration_20250207_add_audit_logs.sql

# 3. 验证
mysql -u ahfunstock -p -e "SHOW TABLES FROM api.ahfun.me;"
```

### 方案二：零停机迁移

```bash
# 1. 主库备份
mysqldump --single-transaction -u ahfunstock -p api.ahfun.me > backup.sql

# 2. 创建从库（如使用主从架构）
# ...

# 3. 在从库执行迁移测试
mysql -u ahfunstock -p api_test < migration_20250207_add_audit_logs.sql

# 4. 切换流量到新版本
# ...

# 5. 验证无误后，主库执行迁移
```

---

## 版本切换策略

### 场景1：新版本有问题，需要回滚到旧版本

```bash
# 完全安全！因为新版本只是新增了 audit 表
# 旧版本代码完全不会访问 audit 表

# 直接切换回旧版本代码即可：
git checkout AhFunStokAPI  # 或部署旧版本
# 不需要修改数据库！
```

**原因**：
- 旧版本代码不访问 `config_audit_logs` 表
- 新增表不影响旧版本运行
- 原有数据完全不受影响

### 场景2：灰度发布

```
步骤:
1. 数据库迁移（新增 audit 表）
2. 10% 流量切换到新版本
3. 监控 error_logs 和 config_audit_logs
4. 确认无问题后，100% 流量切换
5. 如有问题，随时回滚到旧版本
```

---

## 数据一致性保证

### 原有数据

| 表名 | 数据影响 | 说明 |
|------|---------|------|
| accounts | ✅ 无影响 | 用户名、密码等完全保留 |
| account_tokens | ✅ 无影响 | 登录态完全保留 |
| portfolio_configs | ✅ 无影响 | 配置数据完全保留 |
| users | ✅ 无影响 | 设备信息完全保留 |
| user_data | ✅ 无影响 | 用户数据完全保留 |

### 新增数据

| 表名 | 用途 | 旧版本可见性 |
|------|------|-------------|
| config_audit_logs | 审计日志 | ❌ 不可见（不影响） |

---

## API 兼容性

### 接口对比

| 接口 | 原版 | 优化版 | 兼容性 |
|------|------|--------|--------|
| `POST /auth/register` | ✅ | ✅ | 100% |
| `POST /auth/login` | ✅ | ✅ | 100% |
| `POST /auth/logout` | ✅ | ✅ | 100% |
| `POST /auth/bind_device` | ✅ | ✅ | 100% |
| `GET /sync/config` | ✅ | ✅ 增强 | 100% |
| `POST /sync/config` | ✅ | ✅ 增强 | 100% |
| `GET /sync/version` | ✅ | ✅ 增强 | 100% |
| `GET /users` | ✅ | ✅ | 100% |
| `POST /add_user` | ✅ | ✅ 优化 | 100% |
| `POST /add_user_data` | ✅ | ✅ 优化 | 100% |
| `POST /add_logs` | ✅ | ✅ 优化 | 100% |
| `GET /health` | ❌ | ✅ 新增 | 不影响旧版 |
| `GET /debug/api-tester` | ✅ | ✅ | 100% |

### 关键改进（不影响兼容性）

**POST /sync/config 优化**:
```python
# 原版返回
{
    "message": "Config saved successfully",
    "config": {...}
}

# 优化版返回（相同格式，内部逻辑增强）
{
    "message": "Config saved successfully",
    "config": {...}
}
```

**冲突处理优化**:
```python
# 原版冲突返回
{
    "message": "revision_conflict",
    "latest": {...}
}

# 优化版冲突返回（相同格式）
{
    "message": "revision_conflict",
    "latest": {...},
    "server_revision": 6,  # 新增字段，但旧版不解析也不影响
    "client_revision": 5
}
```

---

## 部署检查清单

### 部署前

- [ ] 数据库备份完成
- [ ] 迁移脚本测试通过
- [ ] 新旧版本 API 响应对比测试

### 部署中

- [ ] 执行迁移脚本（只新增 audit 表）
- [ ] 部署新版本代码
- [ ] 验证 /health 接口
- [ ] 验证登录功能
- [ ] 验证配置同步功能

### 部署后

- [ ] 监控 error_logs
- [ ] 检查 config_audit_logs 是否有记录
- [ ] 确认无异常后，保留 24 小时观察期

### 回滚准备

- [ ] 保留旧版本代码包
- [ ] 保留数据库备份
- [ ] 确认回滚流程（直接切回旧代码即可）

---

## 常见问题

### Q1: 迁移后旧版本还能运行吗？

**答**: ✅ 完全可以！

旧版本代码：
- 不访问新增的 `config_audit_logs` 表
- 原有表结构完全一致
- 原有数据完全不受影响

### Q2: 如果新版本有问题，如何回滚？

**答**: 非常简单！

```bash
# 1. 停止新版本服务
pkill -f gunicorn

# 2. 启动旧版本服务
cd /path/to/AhFunStokAPI
gunicorn -c gunicorn_conf.py app:app

# 完成！不需要修改数据库
```

### Q3: 用户数据会丢失吗？

**答**: ✅ 不会！

- 所有用户数据在原有表中
- 优化版只新增审计日志表
- 不涉及任何数据迁移

### Q4: 需要客户端配合升级吗？

**答**: ✅ 不需要！

- API 接口完全兼容
- 返回数据格式一致
- 客户端无感知

---

## 总结

| 维度 | 兼容性 |
|------|--------|
| **数据库结构** | ✅ 100% 兼容（只新增表） |
| **API 接口** | ✅ 100% 兼容（返回格式一致） |
| **数据完整性** | ✅ 100% 保留 |
| **回滚能力** | ✅ 随时可回滚 |
| **客户端兼容性** | ✅ 无需升级 |

**结论：AhFunStokAPI2 完全向后兼容，可安全部署！**
