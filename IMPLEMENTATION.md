# Claude Code Tips Collector — 実装指示書

## 概要

Claude Code の活用事例・Tips・ニュースを毎朝自動収集し、NotebookLM の Audio Overview でポッドキャストとして通勤中に聴くための GitHub Actions プロジェクトを構築してください。

### ゴール

- GitHub Actions のスケジュール実行（毎朝 JST 5:00）で、無料 API から Claude Code 関連情報を自動収集する
- 収集結果を NotebookLM に読み込ませやすい Markdown ファイルとしてリポジトリに自動コミットする
- 外部パッケージ不要（Python 標準ライブラリのみ）で動作すること
- 運用コストは完全無料であること

---

## ディレクトリ構成

以下の構成でプロジェクトを作成してください。

```
claude-tips-collector/
├── .github/
│   └── workflows/
│       └── daily-collect.yml    # GitHub Actions ワークフロー定義
├── scripts/
│   └── collect_tips.py          # メイン収集スクリプト（Python）
├── tips/
│   └── .gitkeep                 # 収集結果の出力先（空ディレクトリ保持用）
├── README.md                    # プロジェクト説明
└── .gitignore
```

---

## 1. GitHub Actions ワークフロー

ファイルパス: `.github/workflows/daily-collect.yml`

### 要件

- トリガー
  - `schedule`: cron `0 20 * * *`（UTC 20:00 = JST 05:00、毎日実行）
  - `workflow_dispatch`: 手動実行ボタンも用意する（テスト・デバッグ用）
- 権限: `permissions: contents: write`（コミットとプッシュに必要）
- タイムアウト: `timeout-minutes: 10`
- ランナー: `ubuntu-latest`

### ステップ

1. `actions/checkout@v4` でリポジトリをチェックアウト
2. `actions/setup-python@v5` で Python 3.12 をセットアップ
3. `python scripts/collect_tips.py` を実行
   - 環境変数 `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`（Actions が自動提供するため Secret 登録不要）
   - 環境変数 `OUTPUT_DIR: tips`
4. 収集結果を自動コミットしてプッシュ
   - git ユーザー名: `github-actions[bot]`
   - git メールアドレス: `github-actions[bot]@users.noreply.github.com`
   - コミットメッセージのフォーマット: `📡 Daily tips: ${DATE}`（DATE は JST の `%Y-%m-%d`）
   - `git diff --cached --quiet` で変更がある場合のみコミットする（空コミット防止）

### 注意事項

- `pip install` ステップは不要（標準ライブラリのみ使用するため）
- `GITHUB_TOKEN` は Actions が自動提供するビルトインシークレットなので、ユーザーによる Secret 登録は不要

---

## 2. メイン収集スクリプト

ファイルパス: `scripts/collect_tips.py`

### 基本方針

- Python 3.12 対応、標準ライブラリのみ使用（`urllib`, `json`, `os`, `sys`, `time`, `datetime`）
- 外部パッケージ（`requests`, `beautifulsoup4` 等）は一切使わない
- 各収集関数は独立しており、1つが失敗しても他は続行する
- API レート制限を考慮し、各リクエスト間に `time.sleep()` を入れる

### 定数・設定

```python
JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST)
YESTERDAY = TODAY - timedelta(days=1)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # 無くても動作する
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "tips")
```

### 共通ユーティリティ関数

#### `fetch_json(url, headers=None, retries=2)`

- `urllib.request` で URL から JSON を取得する
- User-Agent ヘッダーを `ClaudeTipsCollector/1.0` に設定する
- タイムアウトは 15 秒
- 失敗時はリトライ（指数バックオフ: `time.sleep(2 ** attempt)`）
- 全リトライ失敗時は `None` を返す（例外は握りつぶす）
- エラーは `stderr` に警告出力する

#### `truncate(text, max_len=300)`

- 文字列を `max_len` で切り詰め、超過時は末尾に `...` を付加
- 改行文字は半角スペースに置換

#### `gh_headers()`

- `GITHUB_TOKEN` が設定されていれば `{"Authorization": "token {TOKEN}"}` を返す
- 未設定なら空の dict を返す

### 収集関数（全8つ）

各関数は `list[dict]` を返す。空リストの場合もエラーにしない。

#### 1. `collect_github_repos() -> list[dict]`

- API: GitHub Search API (`/search/repositories`)
- 検索クエリ: `claude code in:name,description pushed:>{YESTERDAY の日付}`
- ソート: `sort=updated`、最大 10 件
- 返却する dict のキー: `source`, `title`(full_name), `url`(html_url), `desc`(description を truncate), `stars`(stargazers_count), `updated`(updated_at の先頭10文字)

#### 2. `collect_github_issues() -> list[dict]`

- API: GitHub Search API (`/search/issues`)
- 検索クエリ: `repo:anthropics/claude-code is:issue created:>{YESTERDAY の日付}`
- ソート: `sort=created`、最大 10 件
- 返却する dict のキー: `source`, `title`, `url`(html_url), `desc`(body を truncate), `labels`(カンマ区切り文字列), `reactions`(reactions.total_count), `created`(created_at の先頭10文字)

#### 3. `collect_hackernews() -> list[dict]`

- API: Hacker News Algolia API (`hn.algolia.com/api/v1/search`)
- 検索キーワード: `["claude code", "claude-code", "anthropic claude"]` の3つをループ
- フィルタ: `tags=story`, `numericFilters=created_at_i>{YESTERDAY の UNIX タイムスタンプ}`, `hitsPerPage=5`
- 重複排除: `title` が既に取得済みの場合はスキップ（`seen_titles` セットを使用）
- 返却する dict のキー: `source`, `title`, `url`, `hn_url`(HN の議論ページ URL), `points`, `comments`(num_comments)
- 各キーワード間に `time.sleep(0.5)` を入れる

#### 4. `collect_reddit() -> list[dict]`

- API: Reddit JSON API (`/r/{subreddit}/search.json`)
- 対象サブレディット: `["ClaudeAI", "LocalLLaMA"]`
- パラメータ: `q=claude+code&sort=new&t=day&restrict_sr=on&limit=5`
- 返却する dict のキー: `source`("Reddit r/{sub}"), `title`, `url`(permalink から構築), `desc`(selftext を truncate), `score`, `comments`(num_comments)
- 各サブレディット間に `time.sleep(2)` を入れる（Reddit はレート制限が厳しい）

#### 5. `collect_devto() -> list[dict]`

- API: DEV.to API (`/api/articles`)
- パラメータ: `tag=claude&per_page=10&top=1`（過去1日のトップ記事）
- 返却する dict のキー: `source`, `title`, `url`, `desc`(description を truncate), `reactions`(public_reactions_count)

#### 6. `collect_anthropic_commits() -> list[dict]`

- API: GitHub Commits API (`/repos/anthropics/claude-code/commits`)
- パラメータ: `since={YESTERDAY}T00:00:00Z&per_page=10`
- 返却する dict のキー: `source`, `title`(コミットメッセージ1行目を truncate(120)), `url`(html_url), `date`(committer.date の先頭10文字)
- レスポンスが list でない場合（API エラー等）は空リストを返す

#### 7. `collect_qiita() -> list[dict]`

- API: Qiita API v2 (`/api/v2/items`)
- 検索キーワード: `["claude code", "claude-code"]` の2つをループ
- パラメータ: `query={keyword}&per_page=10`
- 日付フィルタ: `created_at` が YESTERDAY 以降のもののみ
- 重複排除: URL ベースで重複を除去
- 返却する dict のキー: `source`, `title`, `url`, `desc`(body を truncate(200)), `tags`(カンマ区切り文字列), `likes`(likes_count), `created`(created_at の先頭10文字)
- 各キーワード間に `time.sleep(1)` を入れる

#### 8. `collect_zenn() -> list[dict]`

- API: Zenn API (`/api/articles`)
- パラメータ: `q=claude+code&order=latest`
- 日付フィルタ: `published_at` が YESTERDAY 以降のもののみ
- 最大 10 件
- 返却する dict のキー: `source`, `title`, `url`(username と slug から構築), `emoji`, `likes`(liked_count), `published`(published_at の先頭10文字)

### Markdown 生成関数

#### `build_markdown(repos, issues, hn, reddit, devto, commits, qiita, zenn) -> str`

NotebookLM の Audio Overview で読み上げた際に、ポッドキャストとして自然に聴けることを意識したフォーマットにする。

出力する Markdown の構造:

```
# Claude Code 活用情報レポート — {YYYY年MM月DD日}

{導入文}
{NotebookLM への指示文}

## Anthropic 公式アップデート        ← commits
## 注目の GitHub リポジトリ           ← repos（stars 降順）
## 公式リポジトリの最新 Issue          ← issues
## Hacker News での議論              ← hn（points 降順）
## Reddit コミュニティの声            ← reddit（score 降順）
## DEV.to の技術記事                 ← devto
## Qiita の技術記事                  ← qiita（likes 降順）
## Zenn の技術記事                   ← zenn（likes 降順）

---
{フッター: 合計件数、収集日時、ツール名}
```

ルール:
- 各セクションは、そのセクションに該当するデータが 0 件の場合は丸ごと省略する
- 全セクション合計が 0 件の場合は「今日は新情報なし。明日をお楽しみに！」とブロック引用で出力する
- 各セクションの冒頭には、そのセクションの情報がどう役立つかの説明文を1〜2行入れる
- 導入文には以下の2つを含める:
  - このドキュメントが NotebookLM の Audio Overview 用であること
  - 「ポッドキャストでは、開発者が朝の通勤中に聴けるよう、各トピックの『なぜこれが重要か』『すぐ試せるアクション』を交えて紹介してください。」という NotebookLM への指示

### main 関数

```python
def main():
    # 1. 各収集関数を順番に実行（間に time.sleep(1)）
    # 2. build_markdown() で Markdown 生成
    # 3. OUTPUT_DIR/{YYYY-MM-DD}.md にファイル出力（os.makedirs で出力先を自動作成）
    # 4. 標準出力に進捗サマリーを表示
```

- 進行状況を `print()` で標準出力に表示する（Actions のログで確認できるように）
- `if __name__ == "__main__": main()` で実行
- 常に exit code 0 で終了する

---

## 3. README.md

以下のセクションを含む README を作成してください。

1. **プロジェクトタイトルと概要**: 「Claude Code Tips Collector」、1行説明
2. **仕組み**: ASCII アートでデータフローを示す
3. **セットアップ手順**: Fork → コミット → Actions 自動有効化 → 手動テスト方法
4. **毎朝の使い方（所要2分）**: tips/ からファイル取得 → NotebookLM にソース追加 → Audio Overview 生成 → 通勤中に聴く
5. **NotebookLM 活用 Tips**: 週次サマリーの作り方、カスタム指示の書き方、オフライン再生
6. **カスタマイズ方法**: キーワード変更、ソース追加の例
7. **コスト表**: GitHub Actions 無料、API 無料、NotebookLM 無料、合計 ¥0

---

## 4. その他のファイル

### `.gitignore`

```
__pycache__/
*.pyc
.env
.DS_Store
```

### `tips/.gitkeep`

空ファイル（ディレクトリを git で保持するため）。

---

## 5. 実装上の注意事項

### エラーハンドリング

- 各収集関数は独立しており、1つの API が失敗しても他の収集は続行すること
- `fetch_json` でリトライしても失敗した場合は空リストを返し、スクリプト全体は正常終了する
- GitHub Actions がエラーで止まらないよう、`collect_tips.py` は常に exit code 0 で終了する

### レート制限対策

| API | 制限 | 対策 |
|-----|------|------|
| GitHub Search API | トークン無し: 10 req/min, トークン有り: 30 req/min | `GITHUB_TOKEN` 環境変数で緩和 |
| Reddit JSON API | 厳しめ | 各サブレディット間に 2 秒間隔 |
| Hacker News Algolia | 緩め | 各キーワード間に 0.5 秒間隔 |
| DEV.to API | 緩め | 1 秒間隔 |
| Qiita API v2 | 認証無し: 60 req/h | 各キーワード間に 1 秒間隔 |
| Zenn API | 緩め | 1 秒間隔 |

### NotebookLM 最適化

- Markdown のヘッダー部分に NotebookLM の Audio Overview 生成時の指示テキストを含めること。これにより NotebookLM が自動的にポッドキャスト形式で解説してくれる
- 各セクションの冒頭説明文は、音声で聴いた時に文脈がわかるよう自然な日本語にする
- URL は各アイテムに必ず含める（NotebookLM が参照情報として認識する）

### テスト方法

- ローカルで `python scripts/collect_tips.py` を実行して動作確認できる
- `OUTPUT_DIR` 環境変数で出力先を変更可能
- `GITHUB_TOKEN` が無くても動作する（レート制限が厳しくなるだけ）

---

## 6. 期待する出力ファイルのサンプル

ファイルパス: `tips/2026-03-04.md`

```markdown
# Claude Code 活用情報レポート — 2026年03月04日

このドキュメントは、Claude Code の最新活用事例・Tips・ニュースを各種無料ソースから自動収集してまとめたものです。NotebookLM の Audio Overview でポッドキャストとして聴くことを想定しています。

ポッドキャストでは、開発者が朝の通勤中に聴けるよう、各トピックの「なぜこれが重要か」「すぐ試せるアクション」を交えて紹介してください。

## Anthropic 公式アップデート

Claude Code 開発元の最新コミット。新機能やバグ修正の手がかりになります。

### fix: resolve OAuth token refresh in headless mode
- 日付: 2026-03-03
- URL: https://github.com/anthropics/claude-code/commit/abc123

## 注目の GitHub リポジトリ

Claude Code を活用した新プロジェクトやツールです。

### user/claude-code-recipes
- 概要: A collection of useful Claude Code custom commands and workflows
- スター: 234 / 更新: 2026-03-03
- URL: https://github.com/user/claude-code-recipes

## 公式リポジトリの最新 Issue

他の開発者の使い方や課題がわかります。

### Feature: Add MCP server auto-discovery
- ラベル: enhancement, feature-request / リアクション: 15
- 内容: It would be great if Claude Code could automatically discover...
- URL: https://github.com/anthropics/claude-code/issues/30000

## Hacker News での議論

技術者コミュニティの注目トピック。

### Claude Code just replaced my entire CI/CD pipeline
- ポイント: 342 / コメント: 189
- 記事: https://example.com/article
- HN議論: https://news.ycombinator.com/item?id=12345

## Reddit コミュニティの声

ユーザー体験談や実践的 Tips が豊富です。

### My Claude Code workflow that saves 2 hours daily
- Reddit r/ClaudeAI / スコア: 156 / コメント: 43
- 抜粋: I've been using Claude Code for 3 months now and...
- URL: https://www.reddit.com/r/ClaudeAI/comments/xxx

---
合計 **12 件** 収集。
収集日時: 2026-03-04 05:02 JST
by claude-tips-collector (GitHub Actions)
```

---

## 7. 完了条件チェックリスト

以下がすべて満たされていること:

- [ ] `scripts/collect_tips.py` が `python scripts/collect_tips.py` でローカル実行できる
- [ ] 外部パッケージ不要（import は標準ライブラリのみ）
- [ ] `tips/` ディレクトリに `{YYYY-MM-DD}.md` 形式のファイルが出力される
- [ ] `.github/workflows/daily-collect.yml` が正しい YAML 構文である
- [ ] README.md にセットアップ手順と使い方が記載されている
- [ ] `.gitignore` が存在する
- [ ] `tips/.gitkeep` が存在する
- [ ] 1つの API が失敗しても他の収集が続行される
- [ ] 全 API が失敗しても exit code 0 で終了する
