#!/usr/bin/env python3
"""
Lark OAuth認証サーバー
Refresh Tokenを取得するためのOAuth認証フローを実行します。
"""

import os
import json
import secrets
import requests
from flask import Flask, redirect, request, jsonify, render_template_string

app = Flask(__name__)

# 環境変数から設定を読み込み（デフォルト値付き）
APP_ID = os.environ.get('LARK_APP_ID', 'cli_a9e1728ef7b8de1a')
APP_SECRET = os.environ.get('LARK_APP_SECRET', '6Ud29oTpbCShuNQZpKWzO8Ntdo5B4mbK')
BASE_URL = os.environ.get('BASE_URL', '')  # デプロイ後に設定

# OAuth URLs
AUTH_URL = "https://accounts.larksuite.com/open-apis/authen/v1/authorize"
TOKEN_URL = "https://open.larksuite.com/open-apis/authen/v2/oauth/token"

# スコープ（offline_accessが必要）
SCOPES = "offline_access task:task:read"

# 状態管理（本番環境ではRedisなどを使用推奨）
state_store = {}

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
        h1 { 
            color: #333; 
            margin-bottom: 10px;
            font-size: 24px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
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
        .footer {
            margin-top: 30px;
            color: #999;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 Lark OAuth認証</h1>
        <p class="subtitle">株式会社カクシン - Manus連携</p>
        
        <div class="description">
            <strong>このページについて：</strong><br>
            ManusがLarkのタスクにアクセスするための認証を行います。<br><br>
            <strong>取得する権限：</strong><br>
            • タスクの読み取り（task:task:read）<br>
            • オフラインアクセス（offline_access）
        </div>
        
        <a href="{{ auth_url }}" class="button">Larkでログイン</a>
        
        <p class="footer">認証後、Refresh Tokenが表示されます。<br>そのトークンをManusに伝えてください。</p>
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
            max-width: 700px;
            width: 90%;
        }
        h1 { 
            color: #28a745; 
            margin-bottom: 20px;
        }
        .token-section {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            text-align: left;
        }
        .token-label {
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
            display: block;
        }
        .token-box {
            background: #fff;
            border: 1px solid #ddd;
            padding: 15px;
            border-radius: 4px;
            word-break: break-all;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 11px;
            max-height: 100px;
            overflow-y: auto;
            margin-bottom: 15px;
        }
        .copy-btn {
            background: #3370ff;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        .copy-btn:hover {
            background: #2860e0;
        }
        .info-box {
            background: #e7f3ff;
            border-left: 4px solid #3370ff;
            padding: 15px;
            margin: 20px 0;
            text-align: left;
            border-radius: 0 8px 8px 0;
        }
        .expiry {
            color: #666;
            font-size: 14px;
        }
        .instructions {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
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
        <p>Larkの認証が完了しました。以下のトークンをManusに伝えてください。</p>
        
        <div class="token-section">
            <span class="token-label">🔑 Access Token:</span>
            <div class="token-box" id="access-token">{{ access_token }}</div>
            <button class="copy-btn" onclick="copyToken('access-token')">コピー</button>
            <span class="expiry">有効期限: {{ access_expires }} 秒（約2時間）</span>
        </div>
        
        <div class="token-section">
            <span class="token-label">🔄 Refresh Token:</span>
            <div class="token-box" id="refresh-token">{{ refresh_token }}</div>
            <button class="copy-btn" onclick="copyToken('refresh-token')">コピー</button>
            <span class="expiry">有効期限: {{ refresh_expires }} 秒（約7日間）</span>
        </div>
        
        <div class="info-box">
            <strong>📋 Manusへの伝え方：</strong><br>
            「Refresh Tokenは [上記のトークン] です」とManusに伝えてください。<br>
            Manusが自動的にトークンを更新し、Larkタスクにアクセスできるようになります。
        </div>
        
        <div class="instructions">
            <strong>⚠️ 注意事項：</strong><br>
            • Refresh Tokenは7日間有効です（毎日の実行で自動更新されます）<br>
            • 365日後には再度このページで認証が必要です<br>
            • トークンは安全に保管してください
        </div>
    </div>
    
    <script>
        function copyToken(id) {
            const text = document.getElementById(id).innerText;
            navigator.clipboard.writeText(text).then(() => {
                alert('コピーしました！');
            });
        }
    </script>
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
        a {
            color: #3370ff;
            text-decoration: none;
        }
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

def get_redirect_uri():
    """リダイレクトURIを取得"""
    if BASE_URL:
        return f"{BASE_URL}/callback"
    # リクエストから推測
    return request.url_root.rstrip('/') + '/callback'

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
    
    return render_template_string(INDEX_HTML, auth_url=auth_url)

@app.route('/callback')
def callback():
    """OAuth コールバック"""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    if error:
        return render_template_string(ERROR_HTML, error_message=f"認証エラー: {error}")
    
    if not code:
        return render_template_string(ERROR_HTML, error_message="認証コードが取得できませんでした。")
    
    # 状態の検証
    if state != state_store.get('state'):
        return render_template_string(ERROR_HTML, error_message="状態が一致しません。セキュリティ上の理由により認証を中断しました。")
    
    redirect_uri = get_redirect_uri()
    
    # トークンを取得
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
        
        return render_template_string(
            SUCCESS_HTML,
            access_token=result.get('access_token', 'N/A'),
            refresh_token=result.get('refresh_token', 'N/A'),
            access_expires=result.get('expires_in', 'N/A'),
            refresh_expires=result.get('refresh_token_expires_in', 'N/A')
        )
        
    except Exception as e:
        return render_template_string(ERROR_HTML, error_message=f"エラーが発生しました: {str(e)}")

@app.route('/health')
def health():
    """ヘルスチェック"""
    return jsonify({'status': 'ok', 'app_id': APP_ID[:10] + '...'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=False)
