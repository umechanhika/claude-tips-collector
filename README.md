# Claude Code Tips Collector

Claude Code の活用事例・Tips・ニュースを毎朝自動収集し、NotebookLM のポッドキャストとして通勤中に聴くための GitHub Actions プロジェクトです。

## 仕組み

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  GitHub      │     │  collect_tips.py │     │   tips/         │
│  Actions     │────>│                  │────>│   2026-03-04.md │
│  (毎朝5時)   │     │  8つの無料APIから  │     │   2026-03-05.md │
└─────────────┘     │  情報を自動収集    │     │   ...           │
                    └──────────────────┘     └────────┬────────┘
                                                      │
                    ┌──────────────────┐              │
                    │  NotebookLM      │<─────────────┘
                    │  Audio Overview  │    Markdownをソースに追加
                    │  → ポッドキャスト  │
                    └──────────────────┘
```

### 収集ソース

| ソース | 内容 |
|--------|------|
| GitHub Repos | Claude Code 関連の新規・更新リポジトリ |
| GitHub Issues | anthropics/claude-code の最新 Issue |
| Hacker News | Claude Code に関する議論 |
| Reddit | r/ClaudeAI, r/LocalLLaMA の投稿 |
| DEV.to | Claude タグの技術記事 |
| Qiita | 日本語の Claude Code 関連技術記事 |
| Zenn | 日本語の Claude Code 関連技術記事 |
| Anthropic Commits | claude-code リポジトリの最新コミット |

## セットアップ手順

### 1. リポジトリを Fork

このリポジトリを自分のアカウントに Fork してください。

### 2. GitHub Actions を有効化

Fork したリポジトリの **Actions** タブを開き、ワークフローを有効化します。

### 3. 手動テスト

1. **Actions** タブ → **Daily Claude Code Tips Collection** を選択
2. **Run workflow** ボタンをクリック
3. 実行完了後、`tips/` ディレクトリに Markdown ファイルが生成されていることを確認

以降は毎朝 JST 5:00 に自動実行されます。

## 毎朝の使い方（所要2分）

1. リポジトリの `tips/` フォルダから最新の日付の `.md` ファイルを取得
2. [NotebookLM](https://notebooklm.google.com/) を開き、新しいノートブックを作成
3. 「ソースを追加」から Markdown ファイルの内容を貼り付け
4. **Audio Overview** をクリックしてポッドキャストを生成
5. 通勤中にイヤホンで聴く

## NotebookLM 活用 Tips

### 週次サマリーの作り方

1週間分の Markdown ファイル（月〜金の5ファイル）をまとめて NotebookLM のソースに追加すると、週次ダイジェストとしてポッドキャストを生成できます。

### カスタム指示の書き方

NotebookLM のノートブック設定で以下のような指示を追加すると、より実用的な内容になります:

> 各トピックについて「なぜ重要か」「明日から使える具体的アクション」を必ず含めてください。
> 技術用語は簡潔に説明し、初中級者にもわかりやすくしてください。

### オフライン再生

Audio Overview で生成されたポッドキャストはダウンロードできます。通勤前にダウンロードしておけば、オフライン環境でも聴けます。

## カスタマイズ方法

### キーワード変更

`scripts/collect_tips.py` の各収集関数内の検索クエリを変更できます。

例: GitHub リポジトリ検索のキーワードを変更する場合

```python
# 変更前
query = urllib.parse.quote(f"claude code in:name,description pushed:>{YESTERDAY_STR}")

# 変更後（例: Cursor も対象に含める）
query = urllib.parse.quote(f"claude code OR cursor in:name,description pushed:>{YESTERDAY_STR}")
```

### ソース追加の例

新しい API ソースを追加するには:

1. `scripts/collect_tips.py` に新しい `collect_xxx()` 関数を追加
2. `main()` 内で呼び出しを追加
3. `build_markdown()` に新しいセクションを追加

## コスト

| 項目 | コスト |
|------|--------|
| GitHub Actions (パブリックリポジトリ) | 無料 |
| GitHub API | 無料 |
| Hacker News API | 無料 |
| Reddit JSON API | 無料 |
| DEV.to API | 無料 |
| Qiita API | 無料 |
| Zenn API | 無料 |
| NotebookLM | 無料 |
| **合計** | **¥0** |

## ライセンス

MIT
