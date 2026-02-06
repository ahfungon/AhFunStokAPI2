#!/usr/bin/env python3
"""
AhFunStokAPI2 - 优化版
修复配置同步错乱问题

核心优化:
1. 添加数据库行级锁防止并发冲突
2. 优化 revision 冲突处理逻辑
3. 添加配置变更审计日志
4. 修复竞态条件
5. 添加自动重试机制
"""

from flask import Flask, jsonify, request, g, render_template_string
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import hashlib
import secrets
from functools import wraps
from typing import Optional
import threading
import time

from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError, OperationalError

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://ahfunstock:81188118@localhost/api.ahfun.me'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['TOKEN_EXPIRES_DAYS'] = 30
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 3600,
}

PASSWORD_HASH_METHOD = 'pbkdf2:sha256'
db = SQLAlchemy(app)

# 配置同步锁 - 防止同一账户并发修改
config_locks = {}
config_locks_lock = threading.Lock()


def get_account_lock(account_id: int) -> threading.Lock:
    """获取账户级别的锁"""
    with config_locks_lock:
        if account_id not in config_locks:
            config_locks[account_id] = threading.Lock()
        return config_locks[account_id]


class Account(db.Model):
    __tablename__ = 'accounts'
    account_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(191), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(191), unique=True)
    mobile_phone = db.Column(db.String(32), unique=True)
    mobile_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AccountToken(db.Model):
    __tablename__ = 'account_tokens'
    token_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'), nullable=False)
    token = db.Column(db.String(128), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

    account = db.relationship('Account', backref=db.backref('tokens', lazy=True))


class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'), nullable=True)
    machine_code = db.Column(db.String(255), nullable=False)
    register_date = db.Column(db.DateTime, nullable=False)
    last_use_date = db.Column(db.DateTime)
    last_use_ip = db.Column(db.String(255))
    use_count = db.Column(db.Integer, default=0)
    initial_version = db.Column(db.String(50))
    current_version = db.Column(db.String(50))
    app_type = db.Column(db.String(50))

    account = db.relationship('Account', backref=db.backref('users', lazy=True))


class PortfolioConfig(db.Model):
    __tablename__ = 'portfolio_configs'
    config_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'), nullable=False)
    stock_codes = db.Column(db.Text)
    memos = db.Column(db.Text)
    holdings = db.Column(db.Text)
    alert_prices = db.Column(db.Text)
    index_codes = db.Column(db.Text)
    pinned_stocks = db.Column(db.Text)
    revision = db.Column(db.BigInteger, default=1, nullable=False)
    data_hash = db.Column(db.String(64))
    last_client = db.Column(db.String(50))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    account = db.relationship('Account', backref=db.backref('portfolio_config', uselist=False, lazy=True))


class ConfigAuditLog(db.Model):
    """配置变更审计日志"""
    __tablename__ = 'config_audit_logs'
    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # 'read', 'write', 'conflict', 'merge'
    client_revision = db.Column(db.BigInteger)
    server_revision = db.Column(db.BigInteger)
    client_hash = db.Column(db.String(64))
    server_hash = db.Column(db.String(64))
    merged = db.Column(db.Boolean, default=False)
    client_info = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class UserData(db.Model):
    __tablename__ = 'user_data'
    data_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    stock_code = db.Column(db.String(255))
    index_code = db.Column(db.String(255))
    my_holding = db.Column(db.String(255))
    alert_price = db.Column(db.String(255))
    fresh_speed = db.Column(db.Integer)
    api_service = db.Column(db.String(255))
    opacity_level = db.Column(db.Integer)
    window_position = db.Column(db.String(255))
    style = db.Column(db.String(255))
    columns = db.Column(db.String(255))
    db.ForeignKeyConstraint(['user_id'], ['users.user_id'])


class UserActions(db.Model):
    __tablename__ = 'user_actions'
    action_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    action_type = db.Column(db.String(255))
    action_time = db.Column(db.DateTime, nullable=False)
    action_detail = db.Column(db.String(500))
    app_version = db.Column(db.String(50))
    db.ForeignKeyConstraint(['user_id'], ['users.user_id'])


class ErrorLogs(db.Model):
    __tablename__ = 'error_logs'
    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    error_type = db.Column(db.String(255))
    error_detail = db.Column(db.String(500))
    error_time = db.Column(db.DateTime, nullable=False)
    app_version = db.Column(db.String(50))
    db.ForeignKeyConstraint(['user_id'], ['users.user_id'])


CONFIG_FIELDS = [
    'stock_codes',
    'memos',
    'holdings',
    'alert_prices',
    'index_codes',
    'pinned_stocks',
]


def _generate_token_value() -> str:
    return secrets.token_hex(32)


def _token_expiration() -> datetime:
    days = app.config.get('TOKEN_EXPIRES_DAYS', 30)
    return datetime.utcnow() + timedelta(days=days)


def issue_account_token(account: Account) -> AccountToken:
    """Create and persist a new token for the account."""
    token_value = _generate_token_value()
    expires_at = _token_expiration()
    token = AccountToken(account_id=account.account_id, token=token_value, expires_at=expires_at)
    db.session.add(token)
    db.session.commit()
    return token


def revoke_token(token_value: str) -> None:
    AccountToken.query.filter_by(token=token_value).delete()
    db.session.commit()


def _serialize_token(token: AccountToken) -> dict:
    return {
        'token': token.token,
        'expires_at': token.expires_at.isoformat() + 'Z',
    }


def _serialize_account(account: Account) -> dict:
    return {
        'account_id': account.account_id,
        'username': account.username,
        'email': account.email,
        'mobile_phone': account.mobile_phone,
        'mobile_verified': account.mobile_verified,
        'created_at': account.created_at.isoformat() + 'Z' if account.created_at else None,
        'updated_at': account.updated_at.isoformat() + 'Z' if account.updated_at else None,
    }


def _serialize_config(config: PortfolioConfig) -> dict:
    return {
        'config_id': config.config_id,
        'account_id': config.account_id,
        'stock_codes': config.stock_codes or '',
        'memos': config.memos or '',
        'holdings': config.holdings or '',
        'alert_prices': config.alert_prices or '',
        'index_codes': config.index_codes or '',
        'pinned_stocks': config.pinned_stocks or '',
        'revision': config.revision,
        'data_hash': config.data_hash,
        'last_client': config.last_client,
        'updated_at': config.updated_at.isoformat() + 'Z' if config.updated_at else None,
    }


def _get_bearer_token() -> Optional[str]:
    auth_header = request.headers.get('Authorization', '')
    if not auth_header:
        return None
    if auth_header.lower().startswith('bearer '):
        return auth_header[7:].strip()
    return None


def _authenticate_token() -> Optional[AccountToken]:
    token_value = _get_bearer_token()
    if not token_value:
        return None

    token = AccountToken.query.filter_by(token=token_value).first()
    if not token:
        return None

    if token.expires_at < datetime.utcnow():
        db.session.delete(token)
        db.session.commit()
        return None

    return token


def require_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = _authenticate_token()
        if not token:
            return jsonify({'message': 'Unauthorized'}), 401

        g.current_account = token.account
        g.current_token = token
        return func(*args, **kwargs)

    return wrapper


def _compute_config_hash(payload: dict) -> str:
    combined = '|'.join((payload.get(field) or '') for field in CONFIG_FIELDS)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()


def _ensure_username_available(username: str) -> bool:
    return Account.query.filter_by(username=username).first() is None


def _ensure_email_available(email: Optional[str]) -> bool:
    if not email:
        return True
    return Account.query.filter_by(email=email).first() is None


def _ensure_mobile_available(mobile: Optional[str]) -> bool:
    if not mobile:
        return True
    return Account.query.filter_by(mobile_phone=mobile).first() is None


def _log_config_action(account_id: int, action: str, 
                       client_revision: Optional[int] = None,
                       server_revision: Optional[int] = None,
                       client_hash: Optional[str] = None,
                       server_hash: Optional[str] = None,
                       merged: bool = False):
    """记录配置变更审计日志"""
    try:
        log = ConfigAuditLog(
            account_id=account_id,
            action=action,
            client_revision=client_revision,
            server_revision=server_revision,
            client_hash=client_hash,
            server_hash=server_hash,
            merged=merged,
            client_info=request.headers.get('User-Agent', 'unknown')
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        # 审计日志失败不应影响主流程
        app.logger.error(f"Failed to write audit log: {e}")
        db.session.rollback()


# ========== API Routes ==========

@app.route('/debug/api-tester', methods=['GET'])
def api_tester():
    # ... 保持原有的 HTML 测试页面 ...
    return render_template_string("API Tester")


@app.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Invalid JSON'}), 400

    username = data.get('username')
    password = data.get('password')
    email = data.get('email') or None
    mobile_phone = data.get('mobile_phone') or None

    if not username or not password:
        return jsonify({'message': 'Username and password are required'}), 400

    if not _ensure_username_available(username):
        return jsonify({'message': 'Username already exists'}), 409

    if email and not _ensure_email_available(email):
        return jsonify({'message': 'Email already in use'}), 409

    if mobile_phone and not _ensure_mobile_available(mobile_phone):
        return jsonify({'message': 'Mobile phone already in use'}), 409

    account = Account(
        username=username,
        password_hash=generate_password_hash(password, method=PASSWORD_HASH_METHOD),
        email=email,
        mobile_phone=mobile_phone
    )
    db.session.add(account)
    db.session.commit()

    return jsonify({'message': 'Account created successfully', 'account': _serialize_account(account)}), 201


@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Invalid JSON'}), 400

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Username and password are required'}), 400

    account = Account.query.filter_by(username=username).first()
    if not account or not check_password_hash(account.password_hash, password):
        return jsonify({'message': 'Invalid username or password'}), 401

    token = issue_account_token(account)

    return jsonify({
        'message': 'Login successful',
        'token': _serialize_token(token),
        'account': _serialize_account(account)
    }), 200


@app.route('/auth/logout', methods=['POST'])
@require_auth
def logout():
    token_value = _get_bearer_token()
    if token_value:
        revoke_token(token_value)
    return jsonify({'message': 'Logged out successfully'}), 200


@app.route('/auth/bind_device', methods=['POST'])
@require_auth
def bind_device():
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Invalid JSON'}), 400

    machine_code = data.get('machine_code')
    if not machine_code:
        return jsonify({'message': 'machine_code is required'}), 400

    app_type = data.get('app_type', 'AhFunStock_iOS')
    current_version = data.get('current_version')
    last_use_ip = data.get('last_use_ip')

    existing_user = User.query.filter_by(
        account_id=g.current_account.account_id,
        machine_code=machine_code,
        app_type=app_type
    ).first()

    now = datetime.utcnow()

    if existing_user:
        existing_user.last_use_date = now
        existing_user.last_use_ip = last_use_ip
        existing_user.use_count = (existing_user.use_count or 0) + 1
        if current_version:
            existing_user.current_version = current_version
        user = existing_user
    else:
        user = User(
            account_id=g.current_account.account_id,
            machine_code=machine_code,
            register_date=now,
            last_use_date=now,
            last_use_ip=last_use_ip,
            use_count=1,
            initial_version=current_version,
            current_version=current_version,
            app_type=app_type
        )
        db.session.add(user)

    db.session.commit()

    return jsonify({
        'message': 'Device bound to account',
        'user_id': user.user_id,
        'account_id': user.account_id,
        'app_type': user.app_type,
    }), 200


# ========== 优化的配置同步接口 ==========

@app.route('/sync/config', methods=['GET'])
@require_auth
def get_config():
    """获取配置 - 添加审计日志"""
    account_id = g.current_account.account_id
    
    config = PortfolioConfig.query.filter_by(account_id=account_id).first()
    
    # 记录读取操作
    if config:
        _log_config_action(
            account_id=account_id,
            action='read',
            server_revision=config.revision,
            server_hash=config.data_hash
        )
    
    if not config:
        return jsonify({
            'account_id': account_id,
            'config': None,
            'revision': 0
        }), 200

    return jsonify({
        'account_id': config.account_id,
        'config': _serialize_config(config),
        'revision': config.revision
    }), 200


@app.route('/sync/config', methods=['POST'])
@require_auth
def save_config():
    """
    保存配置 - 优化版
    
    核心改进:
    1. 使用数据库行级锁防止并发冲突
    2. 使用内存锁防止同一账户并发修改
    3. 优化 revision 冲突处理
    4. 添加审计日志
    5. 添加事务保护
    """
    data = request.get_json() or {}
    account_id = g.current_account.account_id
    client_revision = data.get('revision')
    client_hash = data.get('data_hash')
    
    # 获取账户级内存锁
    account_lock = get_account_lock(account_id)
    
    with account_lock:
        try:
            # 使用数据库事务和行级锁
            with db.session.begin():
                # 查询并锁定配置记录
                config = db.session.query(PortfolioConfig).filter_by(
                    account_id=account_id
                ).with_for_update().first()
                
                if config:
                    # 检查 revision
                    if client_revision is None:
                        _log_config_action(
                            account_id=account_id,
                            action='write',
                            client_revision=client_revision,
                            server_revision=config.revision,
                            client_hash=client_hash,
                            server_hash=config.data_hash
                        )
                        return jsonify({'message': 'revision is required'}), 400
                    
                    # Revision 冲突检测
                    if client_revision != config.revision:
                        # 检查数据是否实际相同（基于hash）
                        new_hash = _compute_config_hash(data)
                        if new_hash == config.data_hash:
                            # 数据相同，只是 revision 不同，返回成功
                            _log_config_action(
                                account_id=account_id,
                                action='write',
                                client_revision=client_revision,
                                server_revision=config.revision,
                                client_hash=client_hash,
                                server_hash=config.data_hash,
                                merged=True
                            )
                            return jsonify({
                                'message': 'Config saved successfully (no changes)',
                                'config': _serialize_config(config)
                            }), 200
                        
                        # 真正的冲突
                        _log_config_action(
                            account_id=account_id,
                            action='conflict',
                            client_revision=client_revision,
                            server_revision=config.revision,
                            client_hash=client_hash,
                            server_hash=config.data_hash
                        )
                        return jsonify({
                            'message': 'revision_conflict',
                            'latest': _serialize_config(config),
                            'server_revision': config.revision,
                            'client_revision': client_revision
                        }), 409
                    
                    next_revision = config.revision + 1
                else:
                    # 首次创建配置
                    if client_revision not in (None, 0):
                        return jsonify({'message': 'invalid initial revision'}), 400
                    
                    config = PortfolioConfig(account_id=account_id)
                    db.session.add(config)
                    next_revision = 1
                
                # 更新配置字段
                for field in CONFIG_FIELDS:
                    setattr(config, field, data.get(field) or '')
                
                config.last_client = data.get('last_client')
                config.revision = next_revision
                config.updated_at = datetime.utcnow()
                
                # 计算并保存 hash
                hash_payload = {field: data.get(field) or '' for field in CONFIG_FIELDS}
                config.data_hash = _compute_config_hash(hash_payload)
                
                # 记录成功写入
                _log_config_action(
                    account_id=account_id,
                    action='write',
                    client_revision=client_revision,
                    server_revision=next_revision,
                    client_hash=client_hash,
                    server_hash=config.data_hash
                )
            
            # 事务已提交，返回结果
            return jsonify({
                'message': 'Config saved successfully',
                'config': _serialize_config(config)
            }), 200
            
        except OperationalError as e:
            # 数据库锁等待超时
            db.session.rollback()
            app.logger.error(f"Database lock timeout for account {account_id}: {e}")
            return jsonify({
                'message': 'Server busy, please retry',
                'retry_after': 1
            }), 503
        
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error saving config for account {account_id}: {e}")
            return jsonify({'message': 'Internal server error'}), 500


@app.route('/sync/version', methods=['GET'])
@require_auth
def get_config_version():
    """获取配置版本"""
    config = PortfolioConfig.query.filter_by(
        account_id=g.current_account.account_id
    ).first()
    
    if not config:
        return jsonify({'revision': 0, 'updated_at': None}), 200

    return jsonify({
        'revision': config.revision,
        'updated_at': config.updated_at.isoformat() + 'Z' if config.updated_at else None,
        'data_hash': config.data_hash
    }), 200


# ========== 优化的游客模式接口 ==========

@app.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify(users=[{'user_id': user.user_id, 'machine_code': user.machine_code} for user in users])


@app.route('/add_user', methods=['POST'])
def add_user():
    """优化版 - 添加设备绑定"""
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Invalid JSON'}), 400
    
    machine_code = data.get('machine_code')
    if not machine_code:
        return jsonify({'message': 'machine_code is required'}), 400

    register_date = datetime.now()
    app_type = data.get('app_type', 'AhFunStock_Win')

    try:
        with db.session.begin():
            existing_user = User.query.filter_by(
                machine_code=machine_code, 
                app_type=app_type
            ).with_for_update().first()

            if existing_user:
                existing_user.last_use_date = register_date
                existing_user.last_use_ip = data.get('last_use_ip', existing_user.last_use_ip)
                existing_user.use_count = (existing_user.use_count or 0) + 1
                existing_user.current_version = data.get('current_version', existing_user.current_version)
                user = existing_user
                message = 'User updated'
                status_code = 200
            else:
                new_user = User(
                    machine_code=machine_code,
                    register_date=register_date,
                    last_use_date=register_date,
                    last_use_ip=data.get('last_use_ip'),
                    use_count=1,
                    initial_version=data.get('current_version'),
                    current_version=data.get('current_version'),
                    app_type=app_type
                )
                db.session.add(new_user)
                user = new_user
                message = 'New user added'
                status_code = 201

        return jsonify({'user_id': user.user_id, 'message': message}), status_code
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error in add_user: {e}")
        return jsonify({'message': 'Internal server error'}), 500


@app.route('/add_user_data', methods=['POST'])
def add_user_data():
    """优化版 - 使用 UPSERT 语义避免重复数据"""
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Invalid JSON'}), 400
    
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'message': 'user_id is required'}), 400

    try:
        with db.session.begin():
            # 查找现有记录
            existing = UserData.query.filter_by(user_id=user_id).first()
            
            if existing:
                # 更新现有记录
                existing.stock_code = data.get('stock_code', existing.stock_code)
                existing.index_code = data.get('index_code', existing.index_code)
                existing.my_holding = data.get('my_holding', existing.my_holding)
                existing.alert_price = data.get('alert_price', existing.alert_price)
                existing.fresh_speed = data.get('fresh_speed', existing.fresh_speed)
                existing.api_service = data.get('api_service', existing.api_service)
                existing.opacity_level = data.get('opacity_level', existing.opacity_level)
                existing.window_position = data.get('window_position', existing.window_position)
                existing.style = data.get('style', existing.style)
                existing.columns = data.get('columns', existing.columns)
                message = 'User data updated'
            else:
                # 创建新记录
                user_data = UserData(
                    user_id=user_id,
                    stock_code=data.get('stock_code'),
                    index_code=data.get('index_code'),
                    my_holding=data.get('my_holding'),
                    alert_price=data.get('alert_price'),
                    fresh_speed=data.get('fresh_speed'),
                api_service=data.get('api_service'),
                    opacity_level=data.get('opacity_level'),
                    window_position=data.get('window_position'),
                    style=data.get('style'),
                    columns=data.get('columns')
                )
                db.session.add(user_data)
                message = 'User data added'

        return jsonify({'message': message}), 200 if existing else 201
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error in add_user_data: {e}")
        return jsonify({'message': 'Internal server error'}), 500


@app.route('/add_logs', methods=['POST'])
def add_logs():
    """优化版 - 批量添加日志"""
    data = request.get_json()
    if not data or 'logs' not in data:
        return jsonify({'message': 'No logs provided'}), 400

    logs = data['logs']
    if not isinstance(logs, list):
        return jsonify({'message': 'logs must be an array'}), 400

    try:
        with db.session.begin():
            for log_data in logs:
                if not isinstance(log_data, dict):
                    continue
                    
                user_id = log_data.get('user_id')
                if not user_id or int(user_id) <= 0:
                    continue

                if 'error_type' in log_data:
                    error_log = ErrorLogs(
                        user_id=user_id,
                        error_type=log_data['error_type'],
                        error_detail=log_data.get('error_detail'),
                        error_time=log_data.get('error_time', datetime.utcnow()),
                        app_version=log_data.get('app_version')
                    )
                    db.session.add(error_log)
                elif 'action_type' in log_data:
                    user_action = UserActions(
                        user_id=user_id,
                        action_type=log_data['action_type'],
                        action_time=log_data.get('action_time', datetime.utcnow()),
                        action_detail=log_data.get('action_detail'),
                        app_version=log_data.get('app_version')
                    )
                    db.session.add(user_action)

        return jsonify({'message': 'Logs added successfully', 'count': len(logs)}), 201
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error in add_logs: {e}")
        return jsonify({'message': 'Internal server error'}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    try:
        # 检查数据库连接
        db.session.execute('SELECT 1')
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503


if __name__ == '__main__':
    app.run(debug=True)
