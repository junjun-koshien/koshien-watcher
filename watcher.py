"""
甲子園予選 敗退通知ウォッチャー

data/target_schools.csv に載っている学校（甲子園出場経験校）が
都道府県予選で負けたら、Discord Webhook に通知を送る。

データ元: https://koshien89.com/ の都道府県別カテゴリページ
  例: https://koshien89.com/blog-category-20.html (東京都)

使い方:
  # 1回だけチェックして終了 (GitHub Actions のcronで使う想定)
  python watcher.py --once

  # ローカルでずっと動かす場合 (5分おきにチェック)
  python watcher.py --interval 300

環境変数:
  DISCORD_WEBHOOK_URL   Discordの Webhook URL (必須)

注意:
  - 非公式サイトのスクレイピングです。頻度は最低でも数分間隔を空けてください。
  - サイトのHTML構造が変わると parse_games() の調整が必要になります。
  - 学校名は完全一致でマッチングしています。旧字体・別表記等は
    data/target_schools.csv 側で調整してください。
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from prefectures import PREF_CATEGORY

JST = timezone(timedelta(hours=9))
STANDARD_INNINGS = 9  # 高校野球の規定回数（これより少なければコールド、多ければ延長とみなす）

DATA_DIR = Path(__file__).parent / "data"
SCHOOLS_CSV = DATA_DIR / "target_schools.csv"
STATE_JSON = DATA_DIR / "state.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KoshienWatcher/1.0; personal use)"}

ROUND_HEADER_RE = re.compile(r"※(?P<round>[^\(]+)\((?P<date>[\d/]+)\)")
GAME_RE = re.compile(r"(?P<t1>[^\s\d※]+?)\s+(?P<s1>\d+)-(?P<s2>\d+)\s+(?P<t2>[^\s\(]+)(?:\((?P<innings>\d+)\))?")


def game_note(innings: int | None, score_diff: int) -> str:
    """簡単な試合内容（コールドゲーム／延長）の注記を作る。
    ※元データに「サヨナラ」等の明示的な表記がないため、それらは判定していない。
    """
    if innings is None:
        return ""
    if innings > STANDARD_INNINGS:
        return f"延長{innings}回"
    if innings < STANDARD_INNINGS:
        return f"コールドゲーム（{innings}回）"
    return ""


def load_target_schools() -> dict:
    """prefecture -> {school名: {"spring": n, "summer": n}} を読み込む"""
    import csv
    schools = {}
    if not SCHOOLS_CSV.exists():
        print(f"[エラー] {SCHOOLS_CSV} がありません。先に build_school_list.py を実行してください。")
        sys.exit(1)
    with open(SCHOOLS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            schools.setdefault(row["prefecture"], {})[row["school"]] = {
                "spring": int(row.get("spring_count", 0) or 0),
                "summer": int(row.get("summer_count", 0) or 0),
            }
    return schools


def load_state() -> set:
    if STATE_JSON.exists():
        return set(json.loads(STATE_JSON.read_text(encoding="utf-8")))
    return set()


def save_state(notified: set):
    STATE_JSON.write_text(json.dumps(sorted(notified), ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_latest_article_html(pref_category_id: int) -> str | None:
    """都道府県カテゴリページから最新記事のHTML本文を取得する"""
    url = f"https://koshien89.com/blog-category-{pref_category_id}.html"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 記事本文らしき最初のブロックを探す（サイト構造に依存するため要調整）
    article = soup.select_one("div.entry_body, div.article, article")
    if article is None:
        # フォールバック: 一番大きいテキストブロックを本文とみなす
        candidates = soup.find_all("div")
        if not candidates:
            return None
        article = max(candidates, key=lambda d: len(d.get_text()))

    # <br> をテキストの改行に変換してから抽出（行区切りが情報として重要）
    for br in article.find_all("br"):
        br.replace_with("\n")

    return article.get_text()


def parse_games(article_text: str):
    """記事本文から (round, date, team1, score1, team2, score2) のリストを作る"""
    games = []
    current_round, current_date = None, None

    for line in article_text.splitlines():
        line = line.strip()
        if not line:
            continue

        header_match = ROUND_HEADER_RE.match(line)
        if header_match:
            current_round = header_match.group("round")
            current_date = header_match.group("date")
            line = line[header_match.end():]  # 同じ行に試合が続く場合があるので残りを処理

        for m in GAME_RE.finditer(line):
            innings = m.group("innings")
            games.append({
                "round": current_round,
                "date": current_date,
                "team1": m.group("t1"),
                "score1": int(m.group("s1")),
                "team2": m.group("t2"),
                "score2": int(m.group("s2")),
                "innings": int(innings) if innings else None,
            })

    return games


def send_discord_notification(webhook_url: str, pref: str, loser: str, winner: str,
                               score_loser: int, score_winner: int, round_name: str, date: str,
                               spring_count: int, summer_count: int, note: str):
    now_str = datetime.now(JST).strftime("%m/%d %H:%M")
    note_part = f"（{note}）" if note else ""
    content = (
        f"@everyone 🔔 **{pref}大会** {round_name or ''}（{date or '日付不明'}）\n"
        f"**{loser}**（春{spring_count}回、夏{summer_count}回）が "
        f"**{winner}** に {score_loser}-{score_winner}{note_part} で敗退\n"
        f"検知時刻: {now_str}"
    )
    resp = requests.post(webhook_url, json={"content": content}, timeout=15)
    resp.raise_for_status()


def check_prefecture(pref: str, category_id: int, target_schools: dict, notified: set,
                      webhook_url: str, dry_run: bool = False):
    try:
        article_text = fetch_latest_article_html(category_id)
    except requests.RequestException as e:
        print(f"  [エラー] {pref}: 取得失敗 ({e})")
        return

    if not article_text:
        return

    games = parse_games(article_text)
    for g in games:
        winner, loser = None, None
        if g["score1"] > g
