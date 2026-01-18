# Lark OAuth認証サーバー

株式会社カクシン - Manus連携用のLark OAuth認証サーバーです。

## 機能

- Lark OAuth 2.0認証フロー
- Refresh Token取得
- タスクAPI用のアクセストークン取得

## 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|----------|
| `LARK_APP_ID` | LarkアプリのApp ID | cli_a9e1728ef7b8de1a |
| `LARK_APP_SECRET` | LarkアプリのApp Secret | (設定済み) |
| `BASE_URL` | デプロイ先のベースURL | (自動検出) |
| `PORT` | サーバーポート | 3000 |

## デプロイ

### Railway

1. このリポジトリをRailwayにデプロイ
2. 環境変数 `BASE_URL` を設定（例: `https://your-app.railway.app`）
3. Lark Developer ConsoleでリダイレクトURLを追加: `{BASE_URL}/callback`

### ローカル実行

```bash
pip install -r requirements.txt
python app.py
```

## 使い方

1. デプロイしたURLにアクセス
2. 「Larkでログイン」をクリック
3. Larkで認証
4. 表示されたRefresh TokenをManusに伝える

## 注意事項

- Refresh Tokenは約7日間有効
- 毎日の実行で自動更新されます
- 365日後には再認証が必要です
