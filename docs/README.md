## 5. API 接口（阶段拆分）

### 5.1 Auth
| Endpoint | Method | 描述 | 阶段 |
| --- | --- | --- | --- |
| `/auth/register` | POST | 用户名/密码注册 | B |
| `/auth/login` | POST | 登录并返回 Token | B |
| `/auth/refresh` | POST | 刷新 Token | B |
| `/auth/logout` | POST | 注销会话 | B |
| `/auth/request_sms` | POST | 发送短信验证码 | C |
| `/auth/login_sms` | POST | 短信验证码登录/注册 | C |

### 5.2 Sync
| Endpoint | Method | 描述 | 阶段 |
| --- | --- | --- | --- |
| `/sync/config` | GET | 获取账号最新配置（含 revision） | B |
| `/sync/config` | POST | 提交配置并更新 revision | B |
| `/sync/version` | GET | 返回最新 revision，供轮询 | B |
| `/sync/history` | GET | 查询历史版本 | C |
| `/add_user_data` | POST | 旧接口兼容（保留） | A |

### 5.3 Device / Push（阶段 C）
- `POST /devices/register`：登记设备、push_token。
- `POST /devices/unregister`：设备下线。
- `POST /push/test`：调试推送。

## 6. 实现策略（阶段化）

### Stage A · 兼容期（已完成/维护中）
1. 统一三端写入逻辑，验证 `add_user` / `add_user_data`。
2. 计划优化 `/add_user` 返回结构（补充 `user_id`）。

### Stage B · 账号体系 + 配置读写
1. **数据库扩展**：新增 `accounts` 表、`users.account_id` 外键；创建 `portfolio_configs`、迁移脚本；为 `user_data` 设计迁移或保留策略。
2. **后端接口**：实现 `/auth/register/login/refresh/logout`、`/sync/config`（GET/POST）、`/sync/version`。
3. **冲突控制**：定义 `revision`、`updated_at`、`last_client`；发生冲突返回 `409`。
4. **客户端改造**：添加登录 UI、token 存储、启动拉取、保存时调用新接口；保留旧接口作为降级。

### Stage C · 扩展能力
5. 手机验证码登录：`/auth/request_sms`、`/auth/login_sms`，引入短信供应商与风控。
6. 历史记录与回滚：`portfolio_history`、`/sync/history`。
7. 实时通知：轮询 + APNs/FCM 推送或 WebSocket/SSE；结合 `user_devices` 管理在线设备。
8. 运维增强：行为日志（`user_actions`）、异常告警、备份恢复流程。

## 7. 时间规划（更新）

| 阶段 | 目标 | 工期（预估） |
| --- | --- | --- |
| M1 | 数据库扩展 & 迁移脚本（users/portfolio_configs） | 0.5 周 |
| M2 | 账号体系实现（注册/登录/Token） | 1 周 |
| M3 | 配置同步 API（GET/POST + revision） | 1 周 |
| M4 | 客户端联调（三端登录 + 拉取 + 提交） | 1 周 |
| M5 | 历史版本 & 冲突处理 | 0.5 周 |
| M6 | 实时通知方案（轮询 → Push/WebSocket） | 0.5 周 |
| M7 | 短信/多因素登录（可选） | 0.5 周 |
| M8 | 运维、监控、部署完善 | 0.5 周 |

> 可根据人力与业务优先级调整顺序，确保阶段 B 能最快落地账号驱动的同步体验。

## 8. 下一步行动
1. **后端**
   - 落地 `accounts` / `users.account_id` 迁移（`docs/migrations/2025-11-09_add_accounts.sql` 已提供初版脚本）。
   - 补充 `/add_user` 的 `user_id` 返回，减少前端兜底。
   - 原型实现 `/auth/*`、`/sync/config`，并编写接口文档。
2. **客户端**
   - 规划最简登录流程（UI/UX+token 存储）。
   - Shared 层支持新接口的 token 与 revision 处理。
   - 制定从旧接口到新接口的过渡方案（灰度切换/回退）。
3. **测试与运维**
   - 整理测试用例（登录、同步、冲突、离线）。
   - 评估日志与告警方案，准备备份/回滚策略。
   - 规划部署脚本与环境差异（Dev/Prod）。

---

> 文档会随着阶段推进持续调整。当前版本聚焦于“账号驱动配置同步”的落地任务，请根据实际进度同步维护 `docs/README.md` 与 `docs/WORKLOG.md`。猫酱随时待命喵～
# AhFunStokAPI 升级需求文档

## 1. 项目背景与当前进展
- **总体目标**：在保留现有 `/add_user`、`/add_user_data` 的基础上，构建“账号驱动”的配置同步能力，为 iOS / macOS / Windows 提供统一的云端配置。
- **现状总结**：
  - Windows 端已上线使用 `add_user_data` 上传配置。
  - 2025-11 完成 Shared 接口整合，Mac/iOS 现已可通过同一逻辑写入配置，并验证落库成功。
  - 尚缺账号登录、配置拉取、版本控制等能力。
- **阶段目标**：
  1. **阶段 A（已完成）**：三端统一写入能力、数据库基础脚手架。
  2. **阶段 B（进行中）**：实现账号注册/登录、配置 GET/POST、revision 与冲突控制。
  3. **阶段 C（规划中）**：设备管理、历史记录、实时通知等增量能力。

## 2. 总体设计（更新版）
- **服务端架构**：
  - Flask + Gunicorn 提供 REST API。
  - MySQL 存储账号、配置、历史记录。
  - Redis（可选）承担缓存、验证码、队列等职责。
- **客户端**：iPhone / macOS / Windows 通过 Shared SDK / REST 封装调用，统一处理 token、revision、冲突。
- **阶段策略**：
  - **兼容阶段**：继续接收 `/add_user`、`/add_user_data`，保障旧版本正常上报。
  - **过渡阶段**：新增 `/auth/*`、`/sync/config`，客户端逐步迁移至“登录 + 配置拉取”模式。
  - **增强阶段**：增加设备管理、历史版本、实时通知等高级能力。

## 3. 功能规划（分阶段）

### 阶段 A · 兼容（已完成/维护中）
- 保持 `/add_user`、`/add_user_data` 与现有客户端兼容。
- Shared 框架统一了 Mac/iOS 的写入逻辑，并验证数据库落库成功。
- 下一步将补充 `/add_user` 返回 `user_id`，减少前端兜底逻辑。

### 阶段 B · 账号体系 + 配置读写（当前重点）
- **账号体系**：
  - `POST /auth/register`、`/auth/login`、`/auth/refresh`、`/auth/logout`。
  - 密码哈希（bcrypt/passlib）、token（JWT 或 session + refresh）。
- **配置同步**：
  - `GET /sync/config` 拉取配置；`POST /sync/config` 更新配置。
  - 设计 `revision`、`updated_at`、`last_client` 用于冲突检测与追踪。
  - `GET /sync/version` 支持低频轮询。
- **冲突策略**：
  - 客户端提交时携带 `revision`；
  - 发生冲突返回 `409` + 最新版本信息，由客户端决定覆盖或提示。
- **客户端改造**：
  - 增加登录页、token 管理、启动时拉取云端配置。
  - 修改本地保存/上传逻辑为 `POST /sync/config`。

### 阶段 C · 扩展能力（规划中）
- **手机验证码登录**：`/auth/request_sms`、`/auth/login_sms`，结合短信服务与风控策略。
- **历史记录**：`/sync/history`、`portfolio_history` 表，支持版本回滚。
- **设备管理**：`/devices/register`、`/devices/unregister`、设备在线统计、推送 token 管理。
- **实时通知**：先以轮询 + 推送（APNs/FCM）为主，必要时扩展 WebSocket / SSE。
- **运维能力**：行为日志（`user_actions`）、异常告警、备份恢复等。

## 4. 数据库设计（更新版）

### 4.1 accounts（账号主表）
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| account_id | INT PK | 账号 ID |
| username | VARCHAR(191) | 唯一用户名，非空 |
| password_hash | VARCHAR(255) | 密码哈希（BCrypt 等） |
| email | VARCHAR(191) | 可选，唯一索引 |
| mobile_phone | VARCHAR(32) | 可选，唯一索引 |
| mobile_verified | TINYINT | 手机号是否验证 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### 4.2 users（设备登记表，支持游客/多端）
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| user_id | INT PK | 设备记录 ID |
| account_id | INT FK | 关联账号，可空；游客模式为 NULL |
| machine_code | VARCHAR | 设备机器码 |
| register_date | DATETIME | 首次登记时间 |
| last_use_date | DATETIME | 最近使用时间 |
| last_use_ip | VARCHAR | 最近使用 IP |
| use_count | INT | 使用次数 |
| initial_version | VARCHAR | 首次使用版本 |
| current_version | VARCHAR | 当前使用版本 |
| app_type | VARCHAR | 客户端类型（iOS/Mac/Win 等） |

### 4.3 portfolio_configs（账号级配置表，阶段 B）
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| config_id | INT PK |
| account_id | INT FK | 关联账号 |
| stock_codes | TEXT |
| memos | TEXT |
| holdings | TEXT |
| alert_prices | TEXT |
| index_codes | TEXT |
| pinned_stocks | TEXT |
| revision | BIGINT |
| data_hash | VARCHAR | 配置摘要校验 |
| last_client | VARCHAR | 最近写入客户端 |
| updated_at | DATETIME |

### 4.4 portfolio_history（可选）
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| history_id | INT PK |
| config_id | INT FK | 对应配置 |
| account_id | INT FK | 冗余账号，便于查询 |
| revision | BIGINT |
| snapshot | JSON/TEXT |
| operator | VARCHAR | 操作客户端/用户 |
| created_at | DATETIME |

### 4.5 user_devices（阶段 C 拓展）
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| device_id | INT PK |
| account_id | INT FK | 关联账号 |
| user_id | INT FK | 关联设备记录 |
| platform | VARCHAR | 平台（iOS/Mac/Win 等） |
| push_token | VARCHAR | 推送 Token |
| last_seen | DATETIME | 最近在线时间 |
