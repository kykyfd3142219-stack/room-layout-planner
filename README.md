# 部屋レイアウトシミュレーター

ブラウザだけで動く、家具・壁要素レイアウト用のシングルページアプリです。

## できること
- 部屋サイズ（幅/奥行き）の変更
- 固定表示の「使い始めの3ステップ」導線と上部ファイル操作バー（折りたたみ対応）
- 部屋テンプレート（6畳 / 8畳正方形 / ワンルーム標準）のワンクリック適用
- 部屋形状（四隅カット）の変更
- 家具のカテゴリ別追加・移動・回転・複製（階段を含む）
- デフォルトは1階のみ。2階 / ロフト / ベランダは追加して同時表示・直接編集（表示/非表示・ロック対応）
- 壁要素（窓/引き戸/スライドドア/テレビプラグ/物置/クローゼット）の配置
- 引き戸の開閉に必要なスペース表示、スライドドアのスライド必要部位表示
- 選択中オブジェクトの数値編集（名前 / 位置 / サイズ / 角度）
- グリッド間隔切替（5/10/25cm）とスナップON/OFF
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
