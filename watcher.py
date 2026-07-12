"""
甲子園予選 敗退通知ウォッチャー (hsbflash.jp版)

data/target_schools.csv に載っている学校（甲子園出場経験校）が
都道府県予選で負けたら、Discord Webhook に通知を送る。

データ元: https://{都道府県}.hsbflash.jp/ の「今日の試合」一覧
  例: https://tokyo.hsbflash.jp/ (東京都)

使い方:
  python watcher.py --once
  python watcher.py --interval 300

環境変数:
  DISCORD_WEBHOOK_URL   Discordの Webhook URL (必須)

注意:
  - 非公式サイトのスクレイピングです。頻度は最低でも数分間隔を空けてください。
  - hsbflash_prefectures.py のスラッグは一部推測です。合わない都道府県があれば
    そこだけ [警告] としてログに出ます（他の都道府県には影響しません）。
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

from hsbflash_prefectures import HSBFLASH_SLUG

JST = timezone(timedelta(hours=9))

DATA_DIR = Path(__file__).parent / "data"
SCHOOLS_CSV = DATA_DIR / "target_schools.csv"
STATE_JSON = DATA_DIR / "state.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KoshienWatcher/1.0; personal use)"}

FINISHED_KEYWORDS = ["試合終了", "コールド", "サヨナラ", "打切り", "没収"]


def load_target_schools() -> dict:
    """prefecture -> {school名: {"spring": n, "summer": n}} を読み込む

    data/aliases.csv (prefecture,alias,canonical) があれば、
    現在の速報サイトで使われている表記(alias)を、対象校リスト上の
    正式な表記(canonical)に対応づける。学校の統合・改称で表記が
    ずれている場合に、ここへ1行足すだけで直せる。
    """
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

    aliases_path = DATA_DIR / "aliases.csv"
    if aliases_path.exists():
        with open(aliases_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pref, alias, canonical = row["prefecture"], row["alias"], row["canonical"]
                canonical_counts = schools.get(pref, {}).get(canonical)
                if canonical_counts is None:
                    print(f"  [警告] aliases.csv: {pref}の'{canonical}'が対象校リストに見つかりません")
                    continue
                schools.setdefault(pref, {})[alias] = canonical_counts

    return schools


def load_state() -> set:
    if STATE_JSON.exists():
        return set(json.loads(STATE_JSON.read_text(encoding="utf-8")))
    return set()


def save_state(notified: set):
    STATE_JSON.write_text(json.dumps(sorted(notified), ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_today_games(slug: str):
    """{slug}.hsbflash.jp のトップページから、今日の試合一覧を取得する"""
    url = f"https://{slug}.hsbflash.jp/"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    games = []
    for li in soup.find_all("li"):
        game = parse_game_li(li)
        if game:
            games.append(game)
    return games


def parse_game_li(li):
    """1試合分の <li> から情報を取り出す。試合情報でなければ None を返す。"""
    strings = list(li.stripped_strings)

    # 「〔試合終了〕」のようなステータス表示を探す
    status_idx = None
    status = None
    for i, s in enumerate(strings):
        if s.startswith("〔") and s.endswith("〕"):
            status_idx = i
            status = s.strip("〔〕")
            break
    if status_idx is None or status_idx == 0:
        return None

    team1 = strings[status_idx - 1].strip()

    # ステータスの後から、数字を2つ（スコア）拾う
    nums = []
    j = status_idx + 1
    while j < len(strings) and len(nums) < 2:
        if strings[j].strip().isdigit():
            nums.append(int(strings[j].strip()))
        j += 1
    if len(nums) < 2:
        return None
    score1, score2 = nums

    # 「◯ 08:30」のような球場略称+時刻の文字列を探し、その次を team2 とする
    team2 = None
    while j < len(strings):
        if ":" in strings[j] and any(c.isdigit() for c in strings[j]):
            k = j + 1
            while k < len(strings):
                if strings[k].strip() and strings[k].strip() != "詳細":
                    team2 = strings[k].strip()
                    break
                k += 1
            break
        j += 1

    if not team1 or not team2:
        return None

    # 試合を一意に識別するため、詳細リンクのURLを拾う（なければteam名とスコアで代用）
    href = None
    a = li.find("a")
    if a and a.get("href"):
        href = a["href"]

    return {
        "team1": team1, "score1": score1,
        "team2": team2, "score2": score2,
        "status": status, "href": href,
    }


def is_finished(status):
    return any(k in status for k in FINISHED_KEYWORDS)


def send_discord_notification(webhook_url, pref, loser, winner,
                               score_loser, score_winner,
                               spring_count, summer_count, status, detail_url=None):
    now_str = datetime.now(JST).strftime("%m/%d %H:%M")
    content = (
        f"@everyone 🔔 **{pref}大会**\n"
        f"**{loser}**（春{spring_count}回、夏{summer_count}回）が "
        f"**{winner}** に {score_loser}-{score_winner}（{status}） で敗退\n"
        f"検知時刻: {now_str}"
    )
    if detail_url:
        content += f"\n📋 [試合詳細はこちら](<{detail_url}>)"
    resp = requests.post(webhook_url, json={"content": content}, timeout=15)
    resp.raise_for_status()


def check_prefecture(pref, slug, target_schools, notified, webhook_url, dry_run=False):
    try:
        games = fetch_today_games(slug)
    except requests.RequestException as e:
        print(f"  [エラー] {pref}: 取得失敗 ({e})")
        return

    for g in games:
        if not is_finished(g["status"]):
            continue  # 進行中の試合はまだ判定しない

        if g["score1"] > g["score2"]:
            winner, loser = g["team1"], g["team2"]
            score_w, score_l = g["score1"], g["score2"]
        elif g["score2"] > g["score1"]:
            winner, loser = g["team2"], g["team1"]
            score_w, score_l = g["score2"], g["score1"]
        else:
            continue  # 引き分け・延長中など

        if loser not in target_schools:
            continue

        # 「詳細」リンクのURLは毎回トークンが変わり不安定なため使わない。
        # 学校名とスコアの組み合わせだけで、同じ試合かどうかを判定する。
        game_key = f"{pref}|{g['team1']}|{g['team2']}|{g['score1']}-{g['score2']}"
        if game_key in notified:
            continue

        counts = target_schools[loser]
        detail_url = None
        if g.get("href"):
            from urllib.parse import urljoin
            detail_url = urljoin(f"https://{slug}.hsbflash.jp/", g["href"])
        print(f"  [敗退検知] {pref}: {loser}（春{counts['spring']}回、夏{counts['summer']}回）"
              f"が {winner} に {score_l}-{score_w}（{g['status']}） で敗退")
        if not dry_run:
            send_discord_notification(webhook_url, pref, loser, winner, score_l, score_w,
                                       counts["spring"], counts["summer"], g["status"], detail_url)
        notified.add(game_key)


def run_once(prefectures, target_schools_by_pref, notified, webhook_url, dry_run):
    for pref in prefectures:
        slug = HSBFLASH_SLUG.get(pref)
        if slug is None:
            print(f"  [警告] 未知の都道府県: {pref}")
            continue
        target_schools = target_schools_by_pref.get(pref, {})
        if not target_schools:
            continue
        print(f"チェック中: {pref}")
        check_prefecture(pref, slug, target_schools, notified, webhook_url, dry_run)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="1回だけチェックして終了")
    parser.add_argument("--interval", type=int, default=300, help="ループ間隔（秒）。デフォルト300秒=5分")
    parser.add_argument("--prefectures", type=str, default="",
                         help="カンマ区切りで対象都道府県を限定（例: 東京,大阪）。省略時は全都道府県")
    parser.add_argument("--dry-run", action="store_true", help="Discordに送らずログ表示のみ")
    args = parser.parse_args()

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url and not args.dry_run:
        print("[エラー] 環境変数 DISCORD_WEBHOOK_URL を設定してください（--dry-run で確認だけも可能）")
        sys.exit(1)

    target_schools_by_pref = load_target_schools()
    notified = load_state()

    prefectures = [p.strip() for p in args.prefectures.split(",") if p.strip()] or list(HSBFLASH_SLUG.keys())

    if args.once:
        run_once(prefectures, target_schools_by_pref, notified, webhook_url, args.dry_run)
        save_state(notified)
    else:
        try:
            while True:
                run_once(prefectures, target_schools_by_pref, notified, webhook_url, args.dry_run)
                save_state(notified)
                print(f"{args.interval}秒待機します...")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            save_state(notified)
            print("終了します")


if __name__ == "__main__":
    main()
