#!/usr/bin/env python3
"""
AhFunStokAPI2 - SQLite 测试版本
用于本地功能测试（无需安装 MySQL）
"""

from flask import Flask, jsonify, request, g, render_template_string
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import hashlib
import secrets
from functools import wraps
from typing import Optional
import threading

app = Flask(__name__)
# 使用 SQLite 进行测试 - 启用多线程支持
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ahfunstock_test.db?check_same_thread=False'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['TOKEN_EXPIRES_DAYS'] = 30
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'check_same_thread': False}
}

db = SQLAlchemy(app)

# 配置同步锁
config_locks = {}
config_locks_lock = threading.Lock()

def get_account_lock(account_id: int) -> threading.Lock:
    with config_locks_lock:
        if account_id not in config_locks:
            config_locks[account_id] = threading.Lock()
        return config_locks[account_id]

# 模型定义（与 MySQL 版本一致）
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
    __tablename__ = 'config_audit_logs'
    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    client_revision = db.Column(db.BigInteger)
    server_revision = db.Column(db.BigInteger)
    client_hash = db.Column(db.String(64))
    server_hash = db.Column(db.String(64))
    merged = db.Column(db.Boolean, default=False)
    client_info = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

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

class UserActions(db.Model):
    __tablename__ = 'user_actions'
    action_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    action_type = db.Column(db.String(255))
    action_time = db.Column(db.DateTime, nullable=False)
    action_detail = db.Column(db.String(500))
    app_version = db.Column(db.String(50))

class ErrorLogs(db.Model):
    __tablename__ = 'error_logs'
    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    error_type = db.Column(db.String(255))
    error_detail = db.Column(db.String(500))
    error_time = db.Column(db.DateTime, nullable=False)
    app_version = db.Column(db.String(50))

CONFIG_FIELDS = ['stock_codes', 'memos', 'holdings', 'alert_prices', 'index_codes', 'pinned_stocks']

def _generate_token_value() -> str:
    return secrets.token_hex(32)

def _token_expiration() -> datetime:
    return datetime.utcnow() + timedelta(days=30)

def _compute_config_hash(payload: dict) -> str:
    combined = '|'.join((payload.get(field) or '') for field in CONFIG_FIELDS)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

def _get_bearer_token() -> Optional[str]:
    auth_header = request.headers.get('Authorization', '')
    if auth_header.lower().startswith('bearer '):
        return auth_header[7:].strip()
    return None

def _authenticate_token():
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

def _log_config_action(account_id: int, action: str, **kwargs):
    try:
        log = ConfigAuditLog(
            account_id=account_id,
            action=action,
            client_revision=kwargs.get('client_revision'),
            server_revision=kwargs.get('server_revision'),
            client_hash=kwargs.get('client_hash'),
            server_hash=kwargs.get('server_hash'),
            merged=kwargs.get('merged', False),
            client_info=request.headers.get('User-Agent', 'unknown')
        )
        db.session.add(log)
        db.session.commit()
    except:
        db.session.rollback()

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'database': 'sqlite', 'timestamp': datetime.utcnow().isoformat() + 'Z'}), 200

@app.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'message': 'Username and password required'}), 400
    if Account.query.filter_by(username=username).first():
        return jsonify({'message': 'Username exists'}), 409
    account = Account(username=username, password_hash=password, email=data.get('email'))
    db.session.add(account)
    db.session.commit()
    return jsonify({'message': 'Account created', 'account_id': account.account_id}), 201

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    account = Account.query.filter_by(username=username).first()
    if not account or account.password_hash != password:
        return jsonify({'message': 'Invalid credentials'}), 401
    token = AccountToken(
        account_id=account.account_id,
        token=_generate_token_value(),
        expires_at=_token_expiration()
    )
    db.session.add(token)
    db.session.commit()
    return jsonify({'message': 'Login successful', 'token': token.token, 'account_id': account.account_id}), 200

@app.route('/sync/config', methods=['GET'])
@require_auth
def get_config():
    account_id = g.current_account.account_id
    config = PortfolioConfig.query.filter_by(account_id=account_id).first()
    if config:
        _log_config_action(account_id, 'read', server_revision=config.revision, server_hash=config.data_hash)
    return jsonify({
        'account_id': account_id,
        'config': {
            'stock_codes': config.stock_codes or '',
            'memos': config.memos or '',
            'holdings': config.holdings or '',
            'alert_prices': config.alert_prices or '',
            'index_codes': config.index_codes or '',
            'pinned_stocks': config.pinned_stocks or '',
            'revision': config.revision if config else 0,
            'data_hash': config.data_hash if config else None,
        } if config else None,
        'revision': config.revision if config else 0
    }), 200

@app.route('/sync/config', methods=['POST'])
@require_auth
def save_config():
    data = request.get_json() or {}
    account_id = g.current_account.account_id
    client_revision = data.get('revision')
    client_hash = data.get('data_hash')
    
    account_lock = get_account_lock(account_id)
    
    with account_lock:
        try:
            config = PortfolioConfig.query.filter_by(account_id=account_id).first()
            
            if config:
                if client_revision is None:
                    return jsonify({'message': 'revision required'}), 400
                if client_revision != config.revision:
                    # 检查数据是否相同
                    new_hash = _compute_config_hash(data)
                    if new_hash == config.data_hash:
                        _log_config_action(account_id, 'write',
                                         client_revision=client_revision, server_revision=config.revision,
                                         client_hash=client_hash, server_hash=config.data_hash, merged=True)
                        return jsonify({'message': 'No changes', 'revision': config.revision}), 200
                    _log_config_action(account_id, 'conflict',
                                     client_revision=client_revision, server_revision=config.revision,
                                     client_hash=client_hash, server_hash=config.data_hash)
                    return jsonify({
                        'message': 'revision_conflict',
                        'server_revision': config.revision,
                        'client_revision': client_revision
                    }), 409
                next_revision = config.revision + 1
            else:
                if client_revision not in (None, 0):
                    return jsonify({'message': 'invalid initial revision'}), 400
                config = PortfolioConfig(account_id=account_id)
                db.session.add(config)
                next_revision = 1
            
            # 更新字段
            for field in CONFIG_FIELDS:
                setattr(config, field, data.get(field) or '')
            config.revision = next_revision
            config.updated_at = datetime.utcnow()
            config.data_hash = _compute_config_hash(data)
            
            _log_config_action(account_id, 'write',
                             client_revision=client_revision, server_revision=next_revision,
                             client_hash=client_hash, server_hash=config.data_hash)
            db.session.commit()
            
            return jsonify({'message': 'Config saved', 'revision': next_revision}), 200
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'message': 'Error', 'error': str(e)}), 500

@app.route('/sync/version', methods=['GET'])
@require_auth
def get_version():
    config = PortfolioConfig.query.filter_by(account_id=g.current_account.account_id).first()
    return jsonify({
        'revision': config.revision if config else 0,
        'updated_at': config.updated_at.isoformat() + 'Z' if config else None,
        'data_hash': config.data_hash if config else None
    }), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✓ 数据库已初始化 (SQLite)")
    app.run(debug=True, port=5000)
