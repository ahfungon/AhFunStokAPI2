-- 2025-11-09 新增 account_tokens 与 portfolio_configs 表
-- 需在 accounts 表创建后执行

START TRANSACTION;

CREATE TABLE IF NOT EXISTS `account_tokens` (
  `token_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_id` INT UNSIGNED NOT NULL,
  `token` VARCHAR(128) NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `expires_at` DATETIME NOT NULL,
  PRIMARY KEY (`token_id`),
  UNIQUE KEY `uk_account_tokens_token` (`token`),
  KEY `idx_account_tokens_account` (`account_id`),
  CONSTRAINT `fk_account_tokens_account`
    FOREIGN KEY (`account_id`) REFERENCES `accounts`(`account_id`)
    ON DELETE CASCADE
    ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `portfolio_configs` (
  `config_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_id` INT UNSIGNED NOT NULL,
  `stock_codes` TEXT,
  `memos` TEXT,
  `holdings` TEXT,
  `alert_prices` TEXT,
  `index_codes` TEXT,
  `pinned_stocks` TEXT,
  `revision` BIGINT NOT NULL DEFAULT 1,
  `data_hash` VARCHAR(64),
  `last_client` VARCHAR(50),
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`config_id`),
  UNIQUE KEY `uk_configs_account` (`account_id`),
  KEY `idx_configs_revision` (`revision`),
  CONSTRAINT `fk_portfolio_configs_account`
    FOREIGN KEY (`account_id`) REFERENCES `accounts`(`account_id`)
    ON DELETE CASCADE
    ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

COMMIT;

