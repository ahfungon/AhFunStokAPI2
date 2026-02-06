-- AhFunStokAPI2 数据库迁移脚本
-- 添加 config_audit_logs 表

CREATE TABLE IF NOT EXISTS `config_audit_logs` (
    `log_id` INT AUTO_INCREMENT PRIMARY KEY,
    `account_id` INT NOT NULL,
    `action` VARCHAR(50) NOT NULL COMMENT '操作类型: read, write, conflict, merge',
    `client_revision` BIGINT DEFAULT NULL COMMENT '客户端提交的 revision',
    `server_revision` BIGINT DEFAULT NULL COMMENT '服务器当前的 revision',
    `client_hash` VARCHAR(64) DEFAULT NULL COMMENT '客户端数据 hash',
    `server_hash` VARCHAR(64) DEFAULT NULL COMMENT '服务器数据 hash',
    `merged` BOOLEAN DEFAULT FALSE COMMENT '是否自动合并',
    `client_info` VARCHAR(255) DEFAULT NULL COMMENT '客户端信息 (User-Agent)',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_account_time` (`account_id`, `created_at`),
    INDEX `idx_action` (`action`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='配置变更审计日志';

-- 添加索引优化（如果原表没有）
ALTER TABLE `portfolio_configs` 
ADD INDEX IF NOT EXISTS `idx_account_revision` (`account_id`, `revision`);

ALTER TABLE `portfolio_configs`
ADD INDEX IF NOT EXISTS `idx_updated_at` (`updated_at`);

-- 查看审计日志的示例查询
-- SELECT * FROM config_audit_logs WHERE account_id = 1 ORDER BY created_at DESC LIMIT 100;

-- 统计冲突数量的查询
-- SELECT 
--     DATE(created_at) as date,
--     action,
--     COUNT(*) as count
-- FROM config_audit_logs
-- GROUP BY DATE(created_at), action
-- ORDER BY date DESC;
