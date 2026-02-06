#!/bin/bash
# MySQL 数据库连接脚本
# 使用方法: ./mysql_connect.sh [SQL命令]
# 如果不提供SQL命令，将进入交互式模式

MYSQL_BIN="/usr/local/mysql/bin/mysql"
DB_USER="ahfunstock"
DB_PASS="81188118"
DB_HOST="localhost"
DB_NAME="api.ahfun.me"

if [ $# -eq 0 ]; then
    # 交互式模式
    $MYSQL_BIN -u "$DB_USER" -p"$DB_PASS" -h "$DB_HOST" "$DB_NAME"
else
    # 执行SQL命令
    $MYSQL_BIN -u "$DB_USER" -p"$DB_PASS" -h "$DB_HOST" "$DB_NAME" -e "$@"
fi

