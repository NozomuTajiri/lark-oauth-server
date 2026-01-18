#!/usr/bin/env python3
"""
Lark OAuth認証サーバー + トークン管理API
- OAuth認証フローでRefresh Tokenを取得
- トークンの中央管理（サーバー側で保持・更新）
- ManusからAPIでAccess Tokenを取得可能
"""

import os
import json
import secrets
import requests
import threading
from datetime import datetime
from flask import Flask, redirect, request, jsonify, render_template_string

app = Flask(__name__)

# 環境変数から設定を読み込み
APP_ID = os.environ.get('LARK_APP_ID', 'cli_a9e1728ef7b8de1a')
APP_SECRET = os.environ.get('LARK_APP_SECRET', '6Ud29oTpbCShuNQZpKWzO8Ntdo5B4mbK')
BASE_URL = os.environ.get('BASE_URL', '')
API_KEY = os.environ.get('API_KEY', 'kakushin-manus-lark-2026')  # API認証用キー

# OAuth URLs
AUTH_URL = "https://accounts.larksuite.com/open-apis/authen/v1/authorize"
TOKEN_URL = "https://open.larksuite.com/open-apis/authen/v2/oauth/token"
LARK_API_BASE = "https://open.larksuite.com/open-apis"

# スコープ
SCOPES = "offline_access task:task:read task:task:write im:message im:chat docx:document drive:drive wiki:wiki bitable:app contact:user.base:readonly"

# トークンストア（本番環境ではRedis等を推奨）
# スレッドセーフにするためのロック
token_lock = threading.Lock()
token_store = {
    'refresh_token': os.environ.get('INITIAL_REFRESH_TOKEN', ''),
    'access_token': '',
    'access_token_expires_at': 0,
    'updated_at': ''
}
state_store = {}

# ========================================
# HTMLテンプレート
# ========================================

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Lark OAuth認証 - 株式会社カクシン</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .container {
            text-align: center;
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            max-width: 500px;
            width: 90%;
        }
        h1 { color: #333; margin-bottom: 10px; font-size: 24px; }
        .subtitle { color: #666; margin-bottom: 30px; font-size: 14px; }
        .description {
            color: #555;
            margin-bottom: 30px;
            line-height: 1.6;
            text-align: left;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
        }
        a.button {
            display: inline-block;
            padding: 15px 40px;
            background: linear-gradient(135deg, #3370ff 0%, #2860e0 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        a.button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(51, 112, 255, 0.4);
        }
        .footer { margin-top: 30px; color: #999; font-size: 12px; }
        .status-box {
            background: #e8f5e9;
            border-left: 4px solid #4caf50;
            padding: 15px;
            margin: 20px 0;
            text-align: left;
            border-radius: 0 8px 8px 0;
        }
        .status-box.warning {
            background: #fff3e0;
            border-left-color: #ff9800;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 Lark OAuth認証</h1>
        <p class="subtitle">株式会社カクシン - Manus連携</p>
        
        {% if has_token %}
        <div class="status-box">
            <strong>✅ 認証済み</strong><br>
            最終更新: {{ updated_at }}<br>
            Manusから自動的にアクセス可能です。
        </div>
        {% else %}
        <div class="status-box warning">
            <strong>⚠️ 未認証</strong><br>
            下のボタンから認証してください。
        </div>
        {% endif %}
        
        <div class="description">
            <strong>このページについて：</strong><br>
            ManusがLarkの各機能にアクセスするための認証を行います。<br><br>
            <strong>取得する権限：</strong><br>
            • タスク確認・作成・更新<br>
            • メッセージ送信・読み取り<br>
            • ドキュメント編集<br>
            • ベース編集<br>
            • オフラインアクセス
        </div>
        
        <a href="{{ auth_url }}" class="button">Larkでログイン{% if has_token %}（再認証）{% endif %}</a>
        
        <p class="footer">認証後、トークンはサーバーに自動保存されます。<br>Manusは自動的にアクセス可能になります。</p>
    </div>
</body>
</html>
"""

SUCCESS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>認証成功 - Lark OAuth</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }
        .container {
            text-align: center;
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            max-width: 600px;
            width: 90%;
        }
        h1 { color: #28a745; margin-bottom: 20px; }
        .info-box {
            background: #e7f3ff;
            border-left: 4px solid #3370ff;
            padding: 15px;
            margin: 20px 0;
            text-align: left;
            border-radius: 0 8px 8px 0;
        }
        .success-box {
            background: #e8f5e9;
            border-left: 4px solid #4caf50;
            padding: 15px;
            margin: 20px 0;
            text-align: left;
            border-radius: 0 8px 8px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>✅ 認証成功！</h1>
        
        <div class="success-box">
            <strong>🎉 トークンがサーバーに保存されました</strong><br><br>
            Manusは自動的にLarkにアクセスできるようになりました。<br>
            手動でトークンをコピーする必要はありません。
        </div>
        
        <div class="info-box">
            <strong>📋 次のステップ：</strong><br>
            Manusに「Larkのタスクを取得して」などと指示するだけで、<br>
            自動的にLarkにアクセスします。
        </div>
        
        <p style="color: #666; font-size: 14px;">
            Access Token有効期限: {{ access_expires }}秒（約2時間）<br>
            Refresh Token有効期限: {{ refresh_expires }}秒（約7日間）<br>
            ※ トークンは自動更新されます
        </p>
    </div>
</body>
</html>
"""

ERROR_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>エラー - Lark OAuth</title>
    <meta charset="utf-8">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);
        }
        .container {
            text-align: center;
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            max-width: 500px;
        }
        h1 { color: #dc3545; }
        .error-box {
            background: #f8d7da;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            text-align: left;
            word-break: break-all;
        }
        a { color: #3370ff; text-decoration: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>❌ エラーが発生しました</h1>
        <div class="error-box">{{ error_message }}</div>
        <p><a href="/">トップページに戻る</a></p>
    </div>
</body>
</html>
"""

# ========================================
# ヘルパー関数
# ========================================

def get_redirect_uri():
    """リダイレクトURIを取得"""
    if BASE_URL:
        return f"{BASE_URL}/callback"
    return request.url_root.rstrip('/') + '/callback'

def refresh_access_token():
    """Refresh Tokenを使ってAccess Tokenを更新"""
    global token_store
    
    with token_lock:
        refresh_token = token_store.get('refresh_token')
        if not refresh_token:
            return None, "Refresh Tokenがありません。認証が必要です。"
        
        try:
            response = requests.post(
                TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": APP_ID,
                    "client_secret": APP_SECRET
                }
            )
            result = response.json()
            
            if result.get('code') == 0 or 'access_token' in result:
                # 新しいトークンを保存
                token_store['access_token'] = result['access_token']
                token_store['refresh_token'] = result['refresh_token']
                token_store['access_token_expires_at'] = datetime.now().timestamp() + result.get('expires_in', 7200)
                token_store['updated_at'] = datetime.now().isoformat()
                
                return result['access_token'], None
            else:
                error_msg = result.get('error_description', result.get('msg', str(result)))
                return None, f"トークン更新失敗: {error_msg}"
                
        except Exception as e:
            return None, f"トークン更新エラー: {str(e)}"

def get_valid_access_token():
    """有効なAccess Tokenを取得（必要に応じて更新）"""
    global token_store
    
    with token_lock:
        # 現在のAccess Tokenが有効か確認（5分のマージン）
        if token_store.get('access_token') and token_store.get('access_token_expires_at', 0) > datetime.now().timestamp() + 300:
            return token_store['access_token'], None
    
    # 更新が必要
    return refresh_access_token()

def verify_api_key():
    """APIキーを検証"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        provided_key = auth_header[7:]
        return provided_key == API_KEY
    
    # クエリパラメータでも許可
    provided_key = request.args.get('api_key', '')
    return provided_key == API_KEY

# ========================================
# Webルート（認証フロー）
# ========================================

@app.route('/')
def index():
    """トップページ - 認証開始"""
    state = secrets.token_urlsafe(16)
    state_store['state'] = state
    
    redirect_uri = get_redirect_uri()
    
    auth_params = {
        'client_id': APP_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': SCOPES,
        'state': state
    }
    
    auth_url = f"{AUTH_URL}?" + "&".join([f"{k}={requests.utils.quote(str(v))}" for k, v in auth_params.items()])
    
    has_token = bool(token_store.get('refresh_token'))
    updated_at = token_store.get('updated_at', '未設定')
    
    return render_template_string(INDEX_HTML, auth_url=auth_url, has_token=has_token, updated_at=updated_at)

@app.route('/callback')
def callback():
    """OAuth コールバック"""
    global token_store
    
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    if error:
        return render_template_string(ERROR_HTML, error_message=f"認証エラー: {error}")
    
    if not code:
        return render_template_string(ERROR_HTML, error_message="認証コードが取得できませんでした。")
    
    if state != state_store.get('state'):
        return render_template_string(ERROR_HTML, error_message="状態が一致しません。")
    
    redirect_uri = get_redirect_uri()
    
    token_data = {
        'grant_type': 'authorization_code',
        'client_id': APP_ID,
        'client_secret': APP_SECRET,
        'code': code,
        'redirect_uri': redirect_uri
    }
    
    try:
        response = requests.post(TOKEN_URL, json=token_data)
        result = response.json()
        
        if result.get('code') != 0 and result.get('code') != '0':
            error_msg = result.get('error_description', result.get('msg', json.dumps(result)))
            return render_template_string(ERROR_HTML, error_message=f"トークン取得エラー: {error_msg}")
        
        # トークンをサーバーに保存
        with token_lock:
            token_store['access_token'] = result.get('access_token', '')
            token_store['refresh_token'] = result.get('refresh_token', '')
            token_store['access_token_expires_at'] = datetime.now().timestamp() + result.get('expires_in', 7200)
            token_store['updated_at'] = datetime.now().isoformat()
        
        return render_template_string(
            SUCCESS_HTML,
            access_expires=result.get('expires_in', 'N/A'),
            refresh_expires=result.get('refresh_token_expires_in', 'N/A')
        )
        
    except Exception as e:
        return render_template_string(ERROR_HTML, error_message=f"エラーが発生しました: {str(e)}")

# ========================================
# API エンドポイント（Manus用）
# ========================================

@app.route('/api/token', methods=['GET'])
def api_get_token():
    """
    Access Tokenを取得するAPI
    Manusはこのエンドポイントを呼び出してトークンを取得
    """
    if not verify_api_key():
        return jsonify({'error': 'Unauthorized', 'message': 'Invalid API key'}), 401
    
    access_token, error = get_valid_access_token()
    
    if error:
        return jsonify({
            'error': 'TokenError',
            'message': error,
            'need_reauth': True,
            'auth_url': request.url_root.rstrip('/')
        }), 401
    
    return jsonify({
        'access_token': access_token,
        'expires_at': token_store.get('access_token_expires_at'),
        'updated_at': token_store.get('updated_at')
    })

@app.route('/api/status', methods=['GET'])
def api_status():
    """認証状態を確認するAPI"""
    if not verify_api_key():
        return jsonify({'error': 'Unauthorized'}), 401
    
    has_token = bool(token_store.get('refresh_token'))
    
    return jsonify({
        'authenticated': has_token,
        'updated_at': token_store.get('updated_at', ''),
        'auth_url': request.url_root.rstrip('/')
    })

@app.route('/api/tasks', methods=['GET'])
def api_get_tasks():
    """
    Larkタスクを取得するAPI（プロキシ）
    Manusはこのエンドポイントを呼び出すだけでタスクを取得可能
    """
    if not verify_api_key():
        return jsonify({'error': 'Unauthorized'}), 401
    
    access_token, error = get_valid_access_token()
    if error:
        return jsonify({'error': 'TokenError', 'message': error, 'need_reauth': True}), 401
    
    # Lark APIを呼び出し
    page_size = request.args.get('page_size', '50')
    page_token = request.args.get('page_token', '')
    
    params = {'page_size': page_size}
    if page_token:
        params['page_token'] = page_token
    
    try:
        response = requests.get(
            f"{LARK_API_BASE}/task/v2/tasks",
            headers={'Authorization': f'Bearer {access_token}'},
            params=params
        )
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': 'APIError', 'message': str(e)}), 500

@app.route('/api/chats', methods=['GET'])
def api_get_chats():
    """チャット一覧を取得するAPI"""
    if not verify_api_key():
        return jsonify({'error': 'Unauthorized'}), 401
    
    access_token, error = get_valid_access_token()
    if error:
        return jsonify({'error': 'TokenError', 'message': error, 'need_reauth': True}), 401
    
    page_size = request.args.get('page_size', '50')
    
    try:
        response = requests.get(
            f"{LARK_API_BASE}/im/v1/chats",
            headers={'Authorization': f'Bearer {access_token}'},
            params={'page_size': page_size}
        )
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': 'APIError', 'message': str(e)}), 500

@app.route('/api/messages/<chat_id>', methods=['GET'])
def api_get_messages(chat_id):
    """特定チャットのメッセージを取得するAPI"""
    if not verify_api_key():
        return jsonify({'error': 'Unauthorized'}), 401
    
    access_token, error = get_valid_access_token()
    if error:
        return jsonify({'error': 'TokenError', 'message': error, 'need_reauth': True}), 401
    
    page_size = request.args.get('page_size', '50')
    
    try:
        response = requests.get(
            f"{LARK_API_BASE}/im/v1/messages",
            headers={'Authorization': f'Bearer {access_token}'},
            params={
                'container_id_type': 'chat',
                'container_id': chat_id,
                'page_size': page_size
            }
        )
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': 'APIError', 'message': str(e)}), 500

@app.route('/api/lark/<path:endpoint>', methods=['GET', 'POST'])
def api_lark_proxy(endpoint):
    """
    汎用Lark APIプロキシ
    任意のLark APIエンドポイントを呼び出し可能
    """
    if not verify_api_key():
        return jsonify({'error': 'Unauthorized'}), 401
    
    access_token, error = get_valid_access_token()
    if error:
        return jsonify({'error': 'TokenError', 'message': error, 'need_reauth': True}), 401
    
    url = f"{LARK_API_BASE}/{endpoint}"
    
    try:
        if request.method == 'GET':
            response = requests.get(
                url,
                headers={'Authorization': f'Bearer {access_token}'},
                params=request.args
            )
        else:
            response = requests.post(
                url,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                },
                json=request.json
            )
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': 'APIError', 'message': str(e)}), 500

@app.route('/health')
def health():
    """ヘルスチェック"""
    return jsonify({
        'status': 'ok',
        'authenticated': bool(token_store.get('refresh_token')),
        'updated_at': token_store.get('updated_at', '')
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=False)
