# 部屋レイアウトシミュレーター

ブラウザだけで動く、家具・壁要素レイアウト用のシングルページアプリです。

## できること
- 部屋サイズ（幅/奥行き）の変更
- 部屋形状（四隅カット）の変更
- 家具の追加・移動・回転
- 壁要素（窓/ドア/テレビプラグ/物置/クローゼット）の配置
- レイアウトの保存/読込（JSON）
- PNG書き出し
- Undo/Redo、キーボード操作（矢印 / R / Delete）

## ローカル起動
- `index.html` をブラウザで開くだけで動作します。

## 同一ネットワーク内で一時公開（すぐ共有したい場合）
1. ターミナルでこのフォルダに移動
2. `python3 -m http.server 8080 --bind 0.0.0.0` を実行
3. `http://<あなたのPCのIPアドレス>:8080/index.html` を共有

## 誰でもアクセスできるように公開する

### 1) GitHub Pages（無料）
1. GitHubにこのプロジェクトをpush
2. GitHubの `Settings` -> `Pages`
3. `Build and deployment` で `Deploy from a branch` を選択
4. Branch を `main`、フォルダを `/ (root)` に設定
5. 数分後に公開URLが発行されます

### 2) Netlify（無料プランあり）
1. Netlifyにログインして `Add new site` -> `Import an existing project`
2. GitHubリポジトリを接続
3. Build command は空欄、Publish directory は `.`（ルート）
4. Deploy を実行

### 3) Vercel（無料プランあり）
1. Vercelにログインし `Add New...` -> `Project`
2. GitHubリポジトリを選択
3. Framework Preset は `Other`
4. Build command は空欄、Output directory は空欄
5. Deploy を実行

## 運用メモ
- レイアウトはブラウザの `localStorage` に自動保存されます。
- 他端末共有は `レイアウト保存(JSON)` で書き出して、共有先で `レイアウト読込` を使ってください。
