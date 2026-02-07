from flask import Flask, jsonify, request, g
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import hashlib
import secrets
from functools import wraps
from typing import Optional

app = Flask(__name__)
# MySQL 配置 - 原版（无锁）
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://ahfunstock:81188118@localhost:3306/api.ahfun.me?unix_socket=/tmp/mysql.sock'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['TOKEN_EXPIRES_DAYS'] = 30

db = SQLAlchemy(app)

# 模型定义
class Account(db.Model):
    __tablename__ = 'accounts'
    account_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(191), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(191), unique=True)
    mobile_phone = db.Column(db.String(32), unique=True)
    mobile_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class AccountToken(db.Model):
    __tablename__ = 'account_tokens'
    token_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'), nullable=False)
    token = db.Column(db.String(128), unique=True, nullable=False)
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
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    account = db.relationship('Account', backref=db.backref('portfolio_config', uselist=False, lazy=True))

CONFIG_FIELDS = ['stock_codes', 'memos', 'holdings', 'alert_prices', 'index_codes', 'pinned_stocks']

def _generate_token_value():
    return secrets.token_hex(32)

def _token_expiration():
    return datetime.utcnow() + timedelta(days=30)

def _compute_config_hash(payload):
    combined = '|'.join((payload.get(field) or '') for field in CONFIG_FIELDS)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

def _get_bearer_token():
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

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'version': 'original', 'database': 'mysql', 'timestamp': datetime.utcnow().isoformat() + 'Z'}), 200

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
    return jsonify({'message': 'Login successful', 'token': token.token}), 200

# ===== 原版 save_config - 无锁 =====
@app.route('/sync/config', methods=['POST'])
@require_auth
def save_config():
    """原版 - 无锁保护"""
    data = request.get_json() or {}
    client_revision = data.get('revision')
    
    # ⚠️ 原版：没有锁，直接查询
    config = PortfolioConfig.query.filter_by(account_id=g.current_account.account_id).first()
    
    if config:
        if client_revision is None:
            return jsonify({'message': 'revision is required'}), 400
        # ⚠️ 危险点：这里可能读到旧数据
        if client_revision != config.revision:
            return jsonify({
                'message': 'revision_conflict',
                'server_revision': config.revision,
                'client_revision': client_revision
            }), 409
        next_revision = config.revision + 1
    else:
        if client_revision not in (None, 0):
            return jsonify({'message': 'invalid initial revision'}), 400
        config = PortfolioConfig(account_id=g.current_account.account_id)
        db.session.add(config)
        next_revision = 1
    
    for field in CONFIG_FIELDS:
        setattr(config, field, data.get(field) or '')
    config.revision = next_revision
    config.updated_at = datetime.utcnow()
    config.data_hash = _compute_config_hash(data)
    
    # ⚠️ 危险点：提交时可能覆盖其他请求的修改
    db.session.commit()
    
    return jsonify({'message': 'Config saved', 'revision': next_revision}), 200

@app.route('/sync/config', methods=['GET'])
@require_auth
def get_config():
    config = PortfolioConfig.query.filter_by(account_id=g.current_account.account_id).first()
    return jsonify({
        'account_id': g.current_account.account_id,
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✓ 原版数据库已初始化 (MySQL)")
    app.run(debug=True, port=5001)
