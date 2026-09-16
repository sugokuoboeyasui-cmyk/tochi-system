# 八幡西区 土地情報 監視・カスタム検索システム

北九州市八幡西区（町上津役西およびその周辺エリア：春日台・沖田・塔野・大平 等）の
売地情報を **ニフティ不動産** と **ふれんず（福岡県宅建協会）** から自動収集し、
現場目線でチェックできる「注意タグ」付きで一覧・検索できるシステムです。

サーバー代 **0円**・完全無料の構成で稼働します。

| 役割 | 使用サービス |
|---|---|
| 定期スクレイピング・通知 | GitHub Actions（無料枠） |
| データ保存 | Google スプレッドシート（無料） |
| 検索・閲覧UI | Streamlit Community Cloud（無料） |

---

## 1. 全体構成

```
tochi-system/
├── scraper.py                  # 巡回スクレイピング・シート書き込み・メール通知
├── app.py                      # Streamlit 検索ダッシュボード
├── requirements.txt            # 依存パッケージ
├── .env.example                # ローカル実行用の環境変数テンプレート
├── .github/workflows/scrape.yml  # 1時間毎の自動巡回設定
└── README.md                   # このファイル
```

処理の流れ：

1. GitHub Actions が1時間ごとに `scraper.py` を実行
2. 対象サイトを巡回し、物件情報＋注意タグを抽出
3. Googleスプレッドシートの既存物件IDと比較し、**新着物件のみ**追記
4. 新着があればGmail経由でメール通知
5. `app.py`（Streamlit）がスプレッドシートを読み込み、検索・一覧表示

---

## 2. 事前準備（初めての方向け・詳細手順）

### 2-1. Google Cloud Console でサービスアカウントを作成する

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセスし、Googleアカウントでログイン
2. 画面上部の「プロジェクトを選択」→「新しいプロジェクト」を作成（例：`tochi-system`）
3. 左メニュー「APIとサービス」→「ライブラリ」を開き、以下の2つのAPIをそれぞれ検索して **有効化**
   - `Google Sheets API`
   - `Google Drive API`
4. 左メニュー「APIとサービス」→「認証情報」→「認証情報を作成」→「サービスアカウント」を選択
5. サービスアカウント名（例：`tochi-scraper`）を入力して「作成して続行」→ ロールは省略可 →「完了」
6. 作成されたサービスアカウントの一覧から対象をクリックし、「キー」タブ →「鍵を追加」→「新しい鍵を作成」
7. 形式は **JSON** を選択して「作成」→ JSONキーファイルが自動的にダウンロードされます
   - このファイルは **絶対に公開・コミットしないでください**
   - サービスアカウントのメールアドレス（例：`tochi-scraper@xxxx.iam.gserviceaccount.com`）を控えておきます

### 2-2. Googleスプレッドシートを作成し、サービスアカウントに共有する

1. [Googleスプレッドシート](https://sheets.google.com/) で新規シートを作成（例：「八幡西区_土地情報」）
2. シート名（タブ名）を分かりやすく変更（例：`物件データ`）。この名前を後で `WORKSHEET_NAME` に設定します
3. 右上の「共有」ボタンをクリックし、手順2-1で控えたサービスアカウントのメールアドレスを
   **編集者権限** で追加
4. ブラウザのアドレスバーに表示されるURLからスプレッドシートIDを控えます
   ```
   https://docs.google.com/spreadsheets/d/【ここがスプレッドシートID】/edit
   ```

### 2-3. Gmail のアプリパスワードを発行する（メール通知用）

1. [Googleアカウント管理](https://myaccount.google.com/security) にアクセス
2. 「2段階認証プロセス」を有効化（未設定の場合は先に設定）
3. 「アプリ パスワード」を検索・選択し、任意の名前（例：`tochi-system`）で新規作成
4. 表示された16桁のパスワードを控えます（これが `SMTP_APP_PASSWORD` になります）
   - 通常のGoogleログインパスワードではメール送信できません。必ずアプリパスワードを使用してください

---

## 3. ローカルでの動作確認

### 3-1. セットアップ

```powershell
# 仮想環境の作成（任意）
python -m venv venv
venv\Scripts\activate

# 依存パッケージのインストール
pip install -r requirements.txt
```

### 3-2. 環境変数の設定

1. `.env.example` を `.env` にコピー
2. 手順2-1でダウンロードしたJSONキーファイルを `service_account.json` として
   プロジェクト直下に配置（またはパスを `GOOGLE_SERVICE_ACCOUNT_FILE` に指定）
3. `.env` の各項目を実際の値に書き換える
   - `SPREADSHEET_ID` : 手順2-2で控えたスプレッドシートID
   - `WORKSHEET_NAME` : シートのタブ名（例：`物件データ`）
   - `SMTP_USER` / `SMTP_APP_PASSWORD` / `MAIL_TO` : Gmailアカウント情報

> ⚠️ `.env` と `service_account.json` は `.gitignore` に追加し、
> 絶対にGitリポジトリにコミットしないでください。

### 3-3. スクレイパーの実行

```powershell
python scraper.py
```

正常に動作すると、コンソールに巡回ログが表示され、
新着物件があればスプレッドシートへの追記とメール送信が行われます。

### 3-4. ダッシュボードの起動

```powershell
streamlit run app.py
```

ブラウザで `http://localhost:8501` が自動的に開き、検索ダッシュボードが表示されます。

---

## 4. GitHub Actions への登録（自動巡回の設定）

### 4-1. GitHubリポジトリの作成

1. GitHub上で新規リポジトリを作成
2. 本プロジェクト一式（`.env` と `service_account.json` を除く）をpush

```powershell
git init
git add .
git commit -m "Initial commit: 八幡西区土地情報監視システム"
git branch -M main
git remote add origin https://github.com/【あなたのアカウント】/【リポジトリ名】.git
git push -u origin main
```

### 4-2. GitHub Secrets の登録

リポジトリの `Settings` → `Secrets and variables` → `Actions` → `New repository secret` から、
以下のSecretsを1つずつ登録してください。

| Secret名 | 設定する値 |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | サービスアカウントJSONファイルの**中身をそのまま**貼り付け（1行のJSON文字列） |
| `SPREADSHEET_ID` | GoogleスプレッドシートのID |
| `WORKSHEET_NAME` | シートのタブ名（例：`物件データ`） |
| `TARGET_AREAS` | `町上津役西,春日台,沖田,塔野,大平` など（任意） |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | 送信に使うGmailアドレス |
| `SMTP_APP_PASSWORD` | 手順2-3で発行したアプリパスワード |
| `MAIL_FROM` | 送信元アドレス（`SMTP_USER`と同じでOK） |
| `MAIL_TO` | 通知を受け取りたいメールアドレス |

> `GOOGLE_SERVICE_ACCOUNT_JSON` は、JSONファイルをテキストエディタで開き、
> 中身（`{ "type": "service_account", ... }` 全体）をそのままコピー＆ペーストしてください。

### 4-3. 動作確認

1. リポジトリの `Actions` タブを開く
2. 「八幡西区 売地情報 定期巡回」ワークフローを選択
3. `Run workflow` ボタンから手動実行して、正常終了することを確認
4. 以降は `cron: '0 * * * *'` の設定により **1時間ごと** に自動実行されます

---

## 5. Streamlit Community Cloud へのデプロイ

1. [Streamlit Community Cloud](https://streamlit.io/cloud) にGitHubアカウントでログイン
2. 「New app」→ 対象のGitHubリポジトリ・ブランチ（`main`）・メインファイル（`app.py`）を指定してデプロイ
3. デプロイ後、アプリの `Settings` → `Secrets` に以下を **TOML形式** で登録

```toml
SPREADSHEET_ID = "あなたのスプレッドシートID"
WORKSHEET_NAME = "物件データ"
GOOGLE_SERVICE_ACCOUNT_JSON = '''{"type": "service_account", "project_id": "...", ...}'''
```

> JSONの中身を `'''` で囲んだ複数行文字列として貼り付けると、改行を含んでいても安全に読み込めます。

4. 保存すると自動的にアプリが再起動し、ブラウザ・スマホから
   `https://【アプリ名】.streamlit.app` のURLでダッシュボードにアクセスできるようになります。

---

## 6. カスタマイズのヒント

- **監視エリアの追加・変更**: `.env` / GitHub Secrets の `TARGET_AREAS` を編集してください
  （現状はエリア名のリストとしてのみ利用し、フィルタ自体はスプレッドシートの「所在地」列から
  `app.py` がユニーク値を自動抽出します）。
- **注意タグのキーワード追加**: `scraper.py` 内の `CAUTION_KEYWORDS` リストに追記してください。
- **巡回頻度の変更**: `.github/workflows/scrape.yml` の `cron` 式を変更してください
  （例：30分毎にしたい場合は `*/30 * * * *`）。
- **サイト構造が変わってデータが取得できなくなった場合**:
  1. 対象サイトの物件一覧ページをブラウザで開き、F12キーで開発者ツールを起動
  2. 物件1件分を囲む要素（`<li>` や `<div>` など）のクラス名を確認
  3. `scraper.py` の `NIFTY_ITEM_SELECTORS` / `FUREINS_ITEM_SELECTORS` などの
     セレクタ定数の先頭に、確認した新しいセレクタを追加してください
     （複数候補を上から順に試すフォールバック方式のため、既存の設定を壊さず追加できます）。

---

## 7. 注意事項・免責

- 本システムは学習・業務効率化目的のスクレイピングです。各サイトの利用規約・
  `robots.txt` を遵守し、過度なアクセスを行わないよう `time.sleep` による
  アクセス間隔（2〜3秒）を必ず設けています。
- サイトのリニューアルにより取得できるデータ項目が変化・欠落する場合があります。
  その際は「6. カスタマイズのヒント」を参考にセレクタを調整してください。
- 取得した情報の正確性は元ポータルサイトの公開情報に依存します。
  重要な意思決定の際は必ず元サイト・不動産会社へ確認してください。

#   t o c h i - s y s t e m  
 