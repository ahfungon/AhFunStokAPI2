# AhFunStokAPI 升级工作日志

> 用于记录每次迭代的工作内容、进度与备注。请保持时间倒序更新。

---

## 2025-08-?? （猫酱初始化）
- 创建 `docs/README.md`，整理 AhFunStokAPI 升级需求、架构与里程碑。
- 规划账号体系、同步 API、验证码登录及实时方案。
- 建立 `docs/WORKLOG.md` 作为后续迭代记录载体。

## 2025-08-?? （猫酱）
- 创建 `docs/schema.sql`，整理现有 ORM 对应的建库脚本，便于初始化与后续维护。
- 验证 MySQL 环境安装情况，确认可登录并查询系统库。
- 在 `AhFunStockShared` 增加 API 环境配置与共享的 `UserApiService`，Mac 端调用移交至 Shared。
- 新增 `UserSessionManager`、`ConfigurationSyncService`，统一 Mac/iOS 端 `add_user` 与配置同步逻辑，数据字段与 Windows 版保持一致。

## 2025-11-09 （猫酱）
- 完成事项：
  - 新增 `docs/migrations/2025-11-09_add_accounts.sql`，提供 `accounts` 表与 `users.account_id` 外键的增量升级脚本。
  - 更新 `docs/schema.sql`，同步纳入账号表、外键及相关索引。
  - 调整 `docs/README.md` 数据库设计与实施计划，明确“账号表 + 设备表”双层结构与后续行动项。
- 进展/备注：
  - 账号体系数据库侧准备完成，可在现有环境执行脚本实现平滑升级。
  - 后续需补充账号注册/登录接口实现与客户端绑定流程。

---

（后续请按以下格式追加）

## YYYY-MM-DD （处理人）
- 完成事项：
  - ...
- 进展/备注：
  - ...


