#!/bin/bash
# 快速查询数据库脚本
# 使用方法: ./query_db.sh "SQL查询语句"

MYSQL_BIN="/usr/local/mysql/bin/mysql"
DB_USER="ahfunstock"
DB_PASS="81188118"
DB_HOST="localhost"
DB_NAME="api.ahfun.me"

if [ -z "$1" ]; then
    echo "使用方法: $0 \"SQL查询语句\""
    echo ""
    echo "示例:"
    echo "  $0 \"SELECT * FROM accounts;\""
    echo "  $0 \"SELECT account_id, stock_codes, revision FROM portfolio_configs WHERE account_id=1;\""
    echo ""
    echo "或者直接进入交互模式:"
    echo "  $MYSQL_BIN -u $DB_USER -p$DB_PASS -h $DB_HOST $DB_NAME"
    exit 1
fi

$MYSQL_BIN -u "$DB_USER" -p"$DB_PASS" -h "$DB_HOST" "$DB_NAME" -e "$1"

