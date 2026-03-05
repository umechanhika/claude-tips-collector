#!/usr/bin/env python3
"""Claude Code Tips Collector — 各種無料 API から Claude Code 関連情報を自動収集する."""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# 定数・設定
# ---------------------------------------------------------------------------

JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST)
YESTERDAY = TODAY - timedelta(days=1)
YESTERDAY_STR = YESTERDAY.strftime("%Y-%m-%d")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "tips")

# ---------------------------------------------------------------------------
# ユーティリティ関数
# ---------------------------------------------------------------------------


def fetch_json(url, headers=None, retries=2):
    """URL から JSON を取得する。失敗時はリトライし、全失敗で None を返す。"""
    if headers is None:
        headers = {}
    headers.setdefault("User-Agent", "ClaudeTipsCollector/1.0")

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            print(f"  [WARN] fetch_json attempt {attempt + 1} failed: {url} — {exc}", file=sys.stderr)
            if attempt < retries:
                time.sleep(2 ** attempt)
    return None


def truncate(text, max_len=300):
    """文字列を max_len で切り詰める。改行はスペースに置換する。"""
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", " ")
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def gh_headers():
    """GitHub API 用ヘッダーを返す。"""
    if GITHUB_TOKEN:
        return {"Authorization": f"token {GITHUB_TOKEN}"}
    return {}


# ---------------------------------------------------------------------------
# 収集関数 (8 つ)
# ---------------------------------------------------------------------------


def collect_github_repos():
    """GitHub Search API でリポジトリを収集する。"""
    print("[1/8] Collecting GitHub repos...")
    query = urllib.parse.quote(f"claude code in:name,description pushed:>{YESTERDAY_STR}")
    url = f"https://api.github.com/search/repositories?q={query}&sort=updated&per_page=10"
    data = fetch_json(url, headers=gh_headers())
    if not data or "items" not in data:
        return []
    results = []
    for item in data["items"][:10]:
        results.append({
            "source": "GitHub Repos",
            "title": item.get("full_name", ""),
            "url": item.get("html_url", ""),
            "desc": truncate(item.get("description", "") or ""),
            "stars": item.get("stargazers_count", 0),
            "updated": (item.get("updated_at", "") or "")[:10],
        })
    print(f"  -> {len(results)} repos found")
    return results


def collect_github_issues():
    """GitHub Search API で anthropics/claude-code の Issue を収集する。"""
    print("[2/8] Collecting GitHub issues...")
    query = urllib.parse.quote(f"repo:anthropics/claude-code is:issue created:>{YESTERDAY_STR}")
    url = f"https://api.github.com/search/issues?q={query}&sort=created&per_page=10"
    data = fetch_json(url, headers=gh_headers())
    if not data or "items" not in data:
        return []
    results = []
    for item in data["items"][:10]:
        labels = ", ".join(lbl.get("name", "") for lbl in item.get("labels", []))
        reactions = item.get("reactions", {}).get("total_count", 0) if isinstance(item.get("reactions"), dict) else 0
        results.append({
            "source": "GitHub Issues",
            "title": item.get("title", ""),
            "url": item.get("html_url", ""),
            "desc": truncate(item.get("body", "") or ""),
            "labels": labels,
            "reactions": reactions,
            "created": (item.get("created_at", "") or "")[:10],
        })
    print(f"  -> {len(results)} issues found")
    return results


def collect_hackernews():
    """Hacker News Algolia API で関連ストーリーを収集する。"""
    print("[3/8] Collecting Hacker News stories...")
    keywords = ["claude code", "claude-code", "anthropic claude"]
    ts = int(YESTERDAY.timestamp())
    seen_titles = set()
    results = []
    for i, kw in enumerate(keywords):
        if i > 0:
            time.sleep(0.5)
        query = urllib.parse.quote(kw)
        url = (
            f"https://hn.algolia.com/api/v1/search?query={query}"
            f"&tags=story&numericFilters=created_at_i>{ts}&hitsPerPage=5"
        )
        data = fetch_json(url)
        if not data or "hits" not in data:
            continue
        for hit in data["hits"]:
            title = hit.get("title", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
            results.append({
                "source": "Hacker News",
                "title": title,
                "url": hit.get("url", "") or hn_url,
                "hn_url": hn_url,
                "points": hit.get("points", 0),
                "comments": hit.get("num_comments", 0),
            })
    print(f"  -> {len(results)} stories found")
    return results


def collect_reddit():
    """Reddit JSON API で関連投稿を収集する。"""
    print("[4/8] Collecting Reddit posts...")
    subreddits = ["ClaudeAI", "LocalLLaMA"]
    results = []
    for i, sub in enumerate(subreddits):
        if i > 0:
            time.sleep(2)
        url = (
            f"https://www.reddit.com/r/{sub}/search.json"
            f"?q=claude+code&sort=new&t=day&restrict_sr=on&limit=5"
        )
        data = fetch_json(url)
        if not data or "data" not in data:
            continue
        children = data.get("data", {}).get("children", [])
        for child in children:
            d = child.get("data", {})
            permalink = d.get("permalink", "")
            results.append({
                "source": f"Reddit r/{sub}",
                "title": d.get("title", ""),
                "url": f"https://www.reddit.com{permalink}" if permalink else "",
                "desc": truncate(d.get("selftext", "") or ""),
                "score": d.get("score", 0),
                "comments": d.get("num_comments", 0),
            })
    print(f"  -> {len(results)} posts found")
    return results


def collect_devto():
    """DEV.to API で Claude 関連記事を収集する。"""
    print("[5/8] Collecting DEV.to articles...")
    url = "https://dev.to/api/articles?tag=claude&per_page=10&top=1"
    data = fetch_json(url)
    if not data or not isinstance(data, list):
        return []
    results = []
    for item in data:
        results.append({
            "source": "DEV.to",
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "desc": truncate(item.get("description", "") or ""),
            "reactions": item.get("public_reactions_count", 0),
        })
    print(f"  -> {len(results)} articles found")
    return results


def collect_anthropic_commits():
    """GitHub Commits API で anthropics/claude-code の最新コミットを収集する。"""
    print("[6/8] Collecting Anthropic commits...")
    url = (
        f"https://api.github.com/repos/anthropics/claude-code/commits"
        f"?since={YESTERDAY_STR}T00:00:00Z&per_page=10"
    )
    data = fetch_json(url, headers=gh_headers())
    if not data or not isinstance(data, list):
        return []
    results = []
    for item in data:
        commit = item.get("commit", {})
        message = commit.get("message", "")
        first_line = message.split("\n")[0] if message else ""
        committer = commit.get("committer", {})
        results.append({
            "source": "Anthropic Commits",
            "title": truncate(first_line, 120),
            "url": item.get("html_url", ""),
            "date": (committer.get("date", "") or "")[:10],
        })
    print(f"  -> {len(results)} commits found")
    return results


def collect_qiita():
    """Qiita API で Claude Code 関連記事を収集する。"""
    print("[7/8] Collecting Qiita articles...")
    keywords = ["claude code", "claude-code"]
    seen_urls = set()
    results = []
    for i, kw in enumerate(keywords):
        if i > 0:
            time.sleep(1)
        query = urllib.parse.quote(kw)
        url = (
            f"https://qiita.com/api/v2/items?query={query}"
            f"&per_page=10"
        )
        data = fetch_json(url)
        if not data or not isinstance(data, list):
            continue
        for item in data:
            item_url = item.get("url", "")
            if item_url in seen_urls:
                continue
            # 日付フィルタ: created_at が YESTERDAY 以降のみ
            created = (item.get("created_at", "") or "")[:10]
            if created < YESTERDAY_STR:
                continue
            seen_urls.add(item_url)
            tags = ", ".join(t.get("name", "") for t in item.get("tags", []))
            results.append({
                "source": "Qiita",
                "title": item.get("title", ""),
                "url": item_url,
                "desc": truncate(item.get("body", "") or "", 200),
                "tags": tags,
                "likes": item.get("likes_count", 0),
                "created": created,
            })
    print(f"  -> {len(results)} articles found")
    return results


def collect_zenn():
    """Zenn API で Claude Code 関連記事を収集する。"""
    print("[8/8] Collecting Zenn articles...")
    url = "https://zenn.dev/api/articles?q=claude+code&order=latest"
    data = fetch_json(url)
    if not data or not isinstance(data, dict):
        return []
    articles = data.get("articles", [])
    results = []
    for item in articles[:10]:
        slug = item.get("slug", "")
        user_name = item.get("user", {}).get("username", "")
        article_url = f"https://zenn.dev/{user_name}/articles/{slug}" if user_name and slug else ""
        # 日付フィルタ: published_at が YESTERDAY 以降のみ
        published = (item.get("published_at", "") or "")[:10]
        if published < YESTERDAY_STR:
            continue
        results.append({
            "source": "Zenn",
            "title": item.get("title", ""),
            "url": article_url,
            "emoji": item.get("emoji", ""),
            "likes": item.get("liked_count", 0),
            "published": published,
        })
    print(f"  -> {len(results)} articles found")
    return results


# ---------------------------------------------------------------------------
# Markdown 生成
# ---------------------------------------------------------------------------


def build_markdown(repos, issues, hn, reddit, devto, commits, qiita, zenn):
    """収集結果を NotebookLM 用 Markdown に変換する。"""
    date_str = TODAY.strftime("%Y年%m月%d日")
    lines = []

    # ヘッダー・導入文
    lines.append(f"# Claude Code 活用情報レポート — {date_str}")
    lines.append("")
    lines.append(
        "このドキュメントは、Claude Code の最新活用事例・Tips・ニュースを"
        "各種無料ソースから自動収集してまとめたものです。"
        "NotebookLM の Audio Overview でポッドキャストとして聴くことを想定しています。"
    )
    lines.append("")
    lines.append(
        "ポッドキャストでは、開発者が朝の通勤中に聴けるよう、"
        "各トピックの「なぜこれが重要か」「すぐ試せるアクション」を交えて紹介してください。"
    )
    lines.append("")

    total = 0

    # --- Anthropic 公式アップデート ---
    if commits:
        lines.append("## Anthropic 公式アップデート")
        lines.append("")
        lines.append("Claude Code 開発元の最新コミット。新機能やバグ修正の手がかりになります。")
        lines.append("")
        for c in commits:
            lines.append(f"### {c['title']}")
            lines.append(f"- 日付: {c['date']}")
            lines.append(f"- URL: {c['url']}")
            lines.append("")
        total += len(commits)

    # --- 注目の GitHub リポジトリ ---
    if repos:
        sorted_repos = sorted(repos, key=lambda x: x.get("stars", 0), reverse=True)
        lines.append("## 注目の GitHub リポジトリ")
        lines.append("")
        lines.append("Claude Code を活用した新プロジェクトやツールです。")
        lines.append("")
        for r in sorted_repos:
            lines.append(f"### {r['title']}")
            lines.append(f"- 概要: {r['desc']}")
            lines.append(f"- スター: {r['stars']} / 更新: {r['updated']}")
            lines.append(f"- URL: {r['url']}")
            lines.append("")
        total += len(repos)

    # --- 公式リポジトリの最新 Issue ---
    if issues:
        lines.append("## 公式リポジトリの最新 Issue")
        lines.append("")
        lines.append("他の開発者の使い方や課題がわかります。")
        lines.append("")
        for iss in issues:
            lines.append(f"### {iss['title']}")
            label_str = iss['labels'] if iss['labels'] else "なし"
            lines.append(f"- ラベル: {label_str} / リアクション: {iss['reactions']}")
            lines.append(f"- 内容: {iss['desc']}")
            lines.append(f"- URL: {iss['url']}")
            lines.append("")
        total += len(issues)

    # --- Hacker News での議論 ---
    if hn:
        sorted_hn = sorted(hn, key=lambda x: x.get("points", 0), reverse=True)
        lines.append("## Hacker News での議論")
        lines.append("")
        lines.append("技術者コミュニティの注目トピック。")
        lines.append("")
        for h in sorted_hn:
            lines.append(f"### {h['title']}")
            lines.append(f"- ポイント: {h['points']} / コメント: {h['comments']}")
            lines.append(f"- 記事: {h['url']}")
            lines.append(f"- HN議論: {h['hn_url']}")
            lines.append("")
        total += len(hn)

    # --- Reddit コミュニティの声 ---
    if reddit:
        sorted_reddit = sorted(reddit, key=lambda x: x.get("score", 0), reverse=True)
        lines.append("## Reddit コミュニティの声")
        lines.append("")
        lines.append("ユーザー体験談や実践的 Tips が豊富です。")
        lines.append("")
        for rd in sorted_reddit:
            lines.append(f"### {rd['title']}")
            lines.append(f"- {rd['source']} / スコア: {rd['score']} / コメント: {rd['comments']}")
            lines.append(f"- 抜粋: {rd['desc']}")
            lines.append(f"- URL: {rd['url']}")
            lines.append("")
        total += len(reddit)

    # --- DEV.to の技術記事 ---
    if devto:
        lines.append("## DEV.to の技術記事")
        lines.append("")
        lines.append("実践的なチュートリアルや活用事例が見つかります。")
        lines.append("")
        for d in devto:
            lines.append(f"### {d['title']}")
            lines.append(f"- リアクション: {d['reactions']}")
            lines.append(f"- 概要: {d['desc']}")
            lines.append(f"- URL: {d['url']}")
            lines.append("")
        total += len(devto)

    # --- Qiita の技術記事 ---
    if qiita:
        sorted_qiita = sorted(qiita, key=lambda x: x.get("likes", 0), reverse=True)
        lines.append("## Qiita の技術記事")
        lines.append("")
        lines.append("日本語の実践的な技術記事やノウハウが豊富です。")
        lines.append("")
        for q in sorted_qiita:
            lines.append(f"### {q['title']}")
            lines.append(f"- タグ: {q['tags']} / いいね: {q['likes']}")
            lines.append(f"- 概要: {q['desc']}")
            lines.append(f"- URL: {q['url']}")
            lines.append("")
        total += len(qiita)

    # --- Zenn の技術記事 ---
    if zenn:
        sorted_zenn = sorted(zenn, key=lambda x: x.get("likes", 0), reverse=True)
        lines.append("## Zenn の技術記事")
        lines.append("")
        lines.append("日本の開発者による深い技術解説や活用事例が見つかります。")
        lines.append("")
        for z in sorted_zenn:
            emoji = z['emoji'] + " " if z.get('emoji') else ""
            lines.append(f"### {emoji}{z['title']}")
            lines.append(f"- いいね: {z['likes']} / 公開日: {z['published']}")
            lines.append(f"- URL: {z['url']}")
            lines.append("")
        total += len(zenn)

    # --- 0 件の場合 ---
    if total == 0:
        lines.append("> 今日は新情報なし。明日をお楽しみに！")
        lines.append("")

    # --- フッター ---
    lines.append("---")
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    lines.append(f"合計 **{total} 件** 収集。")
    lines.append(f"収集日時: {now_str} JST")
    lines.append("by claude-tips-collector (GitHub Actions)")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("Claude Code Tips Collector")
    print(f"Date: {TODAY.strftime('%Y-%m-%d %H:%M JST')}")
    print("=" * 60)

    # 各収集関数を順番に実行
    repos = collect_github_repos()
    time.sleep(1)

    issues = collect_github_issues()
    time.sleep(1)

    hn = collect_hackernews()
    time.sleep(1)

    reddit = collect_reddit()
    time.sleep(1)

    devto = collect_devto()
    time.sleep(1)

    commits = collect_anthropic_commits()
    time.sleep(1)

    qiita = collect_qiita()
    time.sleep(1)

    zenn = collect_zenn()

    # Markdown 生成
    print("\nBuilding Markdown...")
    md = build_markdown(repos, issues, hn, reddit, devto, commits, qiita, zenn)

    # ファイル出力
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = TODAY.strftime("%Y-%m-%d") + ".md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\nOutput: {filepath}")
    total = len(repos) + len(issues) + len(hn) + len(reddit) + len(devto) + len(commits) + len(qiita) + len(zenn)
    print(f"Total items: {total}")
    print("Done!")


if __name__ == "__main__":
    main()
