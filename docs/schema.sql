-- AhFunStokAPI 数据库初始化脚本
-- 适用于本地开发环境，执行前请确认数据库连接及权限

-- 1. 数据库创建（如已存在可跳过）
CREATE DATABASE IF NOT EXISTS `api.ahfun.me`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `api.ahfun.me`;

-- 2. 账号表：记录注册账号信息
CREATE TABLE IF NOT EXISTS `accounts` (
  `account_id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '账号 ID',
  `username` VARCHAR(191) NOT NULL COMMENT '用户名（唯一）',
  `password_hash` VARCHAR(255) NOT NULL COMMENT '密码哈希',
  `email` VARCHAR(191) DEFAULT NULL COMMENT '邮箱',
  `mobile_phone` VARCHAR(32) DEFAULT NULL COMMENT '手机号',
  `mobile_verified` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '手机号是否验证',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`account_id`),
  UNIQUE KEY `uk_accounts_username` (`username`),
  UNIQUE KEY `uk_accounts_email` (`email`),
  UNIQUE KEY `uk_accounts_mobile` (`mobile_phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录账号信息';

-- 3. Access Token 表：保存账号登录态
CREATE TABLE IF NOT EXISTS `account_tokens` (
  `token_id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Token ID',
  `account_id` INT UNSIGNED NOT NULL COMMENT '关联账号 ID',
  `token` VARCHAR(128) NOT NULL COMMENT 'Token 值',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `expires_at` DATETIME NOT NULL COMMENT '过期时间',
  PRIMARY KEY (`token_id`),
  UNIQUE KEY `uk_account_tokens_token` (`token`),
  KEY `idx_account_tokens_account` (`account_id`),
  CONSTRAINT `fk_account_tokens_account`
    FOREIGN KEY (`account_id`) REFERENCES `accounts`(`account_id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='账号级 Token 表';

-- 4. 账号配置表：记录账号级同步配置
CREATE TABLE IF NOT EXISTS `portfolio_configs` (
  `config_id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '配置 ID',
  `account_id` INT UNSIGNED NOT NULL COMMENT '关联账号 ID',
  `stock_codes` TEXT COMMENT '股票列表',
  `memos` TEXT COMMENT '备注信息',
  `holdings` TEXT COMMENT '持仓数据',
  `alert_prices` TEXT COMMENT '预警设置',
  `index_codes` TEXT COMMENT '指数列表',
  `pinned_stocks` TEXT COMMENT '置顶股票',
  `revision` BIGINT NOT NULL DEFAULT 1 COMMENT '版本号',
  `data_hash` VARCHAR(64) DEFAULT NULL COMMENT '数据校验 Hash',
  `last_client` VARCHAR(50) DEFAULT NULL COMMENT '最近写入客户端',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
  PRIMARY KEY (`config_id`),
  UNIQUE KEY `uk_configs_account` (`account_id`),
  KEY `idx_configs_revision` (`revision`),
  CONSTRAINT `fk_portfolio_configs_account`
    FOREIGN KEY (`account_id`) REFERENCES `accounts`(`account_id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='账号级同步配置存储';

-- 5. 用户表：记录客户端设备信息
CREATE TABLE IF NOT EXISTS `users` (
  `user_id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户 ID',
  `account_id` INT UNSIGNED DEFAULT NULL COMMENT '关联账号 ID',
  `machine_code` VARCHAR(255) NOT NULL COMMENT '设备机器码',
  `register_date` DATETIME NOT NULL COMMENT '首次注册时间',
  `last_use_date` DATETIME DEFAULT NULL COMMENT '最近使用时间',
  `last_use_ip` VARCHAR(255) DEFAULT NULL COMMENT '最近使用 IP',
  `use_count` INT DEFAULT 0 COMMENT '使用次数',
  `initial_version` VARCHAR(50) DEFAULT NULL COMMENT '首次使用版本',
  `current_version` VARCHAR(50) DEFAULT NULL COMMENT '当前使用版本',
  `app_type` VARCHAR(50) DEFAULT NULL COMMENT '客户端类型（iOS/Mac/Win 等）',
  PRIMARY KEY (`user_id`),
  KEY `idx_users_machine_type` (`machine_code`, `app_type`),
  KEY `idx_users_account` (`account_id`),
  CONSTRAINT `fk_users_account`
    FOREIGN KEY (`account_id`) REFERENCES `accounts`(`account_id`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='设备/用户登记表';

-- 6. 用户配置表：记录每次上传的配置信息
CREATE TABLE IF NOT EXISTS `user_data` (
  `data_id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '配置记录 ID',
  `user_id` INT UNSIGNED NOT NULL COMMENT '关联用户 ID',
  `stock_code` VARCHAR(255) DEFAULT NULL COMMENT '股票代码串',
  `index_code` VARCHAR(255) DEFAULT NULL COMMENT '指数代码串',
  `my_holding` VARCHAR(255) DEFAULT NULL COMMENT '持仓信息',
  `alert_price` VARCHAR(255) DEFAULT NULL COMMENT '预警设置',
  `fresh_speed` INT DEFAULT NULL COMMENT '刷新频率',
  `api_service` VARCHAR(255) DEFAULT NULL COMMENT '使用数据源',
  `opacity_level` INT DEFAULT NULL COMMENT '透明度设置',
  `window_position` VARCHAR(255) DEFAULT NULL COMMENT '窗口位置',
  `style` VARCHAR(255) DEFAULT NULL COMMENT '界面样式',
  `columns` VARCHAR(255) DEFAULT NULL COMMENT '列配置',
  PRIMARY KEY (`data_id`),
  KEY `idx_user_data_user` (`user_id`),
  CONSTRAINT `fk_user_data_user`
    FOREIGN KEY (`user_id`) REFERENCES `users`(`user_id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户上传的详细配置记录';

-- 7. 用户行为表：记录客户端行为日志
CREATE TABLE IF NOT EXISTS `user_actions` (
  `action_id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '行为 ID',
  `user_id` INT UNSIGNED NOT NULL COMMENT '关联用户 ID',
  `action_type` VARCHAR(255) NOT NULL COMMENT '行为类型',
  `action_time` DATETIME NOT NULL COMMENT '行为发生时间',
  `action_detail` VARCHAR(500) DEFAULT NULL COMMENT '行为详情',
  `app_version` VARCHAR(50) DEFAULT NULL COMMENT '应用版本',
  PRIMARY KEY (`action_id`),
  KEY `idx_user_actions_user_time` (`user_id`, `action_time`),
  CONSTRAINT `fk_user_actions_user`
    FOREIGN KEY (`user_id`) REFERENCES `users`(`user_id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户行为日志';

-- 8. 错误日志表：记录客户端错误信息
CREATE TABLE IF NOT EXISTS `error_logs` (
  `log_id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '错误日志 ID',
  `user_id` INT UNSIGNED NOT NULL COMMENT '关联用户 ID',
  `error_type` VARCHAR(255) NOT NULL COMMENT '错误类型',
  `error_detail` VARCHAR(500) DEFAULT NULL COMMENT '错误详情',
  `error_time` DATETIME NOT NULL COMMENT '错误时间',
  `app_version` VARCHAR(50) DEFAULT NULL COMMENT '应用版本',
  PRIMARY KEY (`log_id`),
  KEY `idx_error_logs_user_time` (`user_id`, `error_time`),
  CONSTRAINT `fk_error_logs_user`
    FOREIGN KEY (`user_id`) REFERENCES `users`(`user_id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户端错误日志';

-- 7. 结束
-- 执行完成后，可运行 python from app import db; db.create_all() 验证表结构一致性

