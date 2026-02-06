-- 2025-11-09 新增账号体系相关表结构
-- 适用于现有 AhFunStokAPI 数据库的增量升级

START TRANSACTION;

-- 1. 创建 accounts 表（如不存在）
CREATE TABLE IF NOT EXISTS `accounts` (
  `account_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(191) NOT NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  `email` VARCHAR(191) DEFAULT NULL,
  `mobile_phone` VARCHAR(32) DEFAULT NULL,
  `mobile_verified` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`account_id`),
  UNIQUE KEY `uk_accounts_username` (`username`),
  UNIQUE KEY `uk_accounts_email` (`email`),
  UNIQUE KEY `uk_accounts_mobile` (`mobile_phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. 在 users 表中新增 account_id 字段（如不存在）
ALTER TABLE `users`
  ADD COLUMN `account_id` INT UNSIGNED NULL AFTER `user_id`;

-- 3. 为 account_id 建立索引与外键（若未创建过）
ALTER TABLE `users`
  ADD INDEX `idx_users_account` (`account_id`);

ALTER TABLE `users`
  ADD CONSTRAINT `fk_users_account`
  FOREIGN KEY (`account_id`)
  REFERENCES `accounts` (`account_id`)
  ON DELETE SET NULL
  ON UPDATE CASCADE;

COMMIT;

