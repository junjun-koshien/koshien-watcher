"""
甲子園出場経験校の一覧を作成するスクリプト。

データ元: 高校野球Ref (https://kokobaseball.kumobit.com/bypref/)
各都道府県ページの「代表校」列を集計し、都道府県ごとに
過去に甲子園（春 or 夏）に出場したことのある学校名の一覧を作る。

出力: data/target_schools.csv (columns: prefecture, school, spring_count, summer_count)

注意:
- 「代表校」は年ごとの表記のため、大昔の学校（旧制中学名など）は
  現在の校名と異なる場合がある。必要に応じて data/target_schools.csv を
  手動で編集・補正すること。
- 高校野球Refのページ構造が変わると動かなくなる可能性がある。
"""

import csv
import time
from collections import defaultdict

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from prefectures import PREF_SLUG

BASE_URL = "https://kokobaseball.kumobit.com/bypref/past_{slug}.html"
OUTPUT_PATH = "data/target_schools.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Referer": "https://kokobaseball.kumobit.com/bypref/pastpref_index.html",
}
REQUEST_INTERVAL_SEC = 3  # サイトに負荷をかけないよう間隔を空ける

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504]
)))


def fetch_prefecture_schools(pref: str, slug: str) -> dict:
    """1都道府県ページから 代表校 -> {spring: n, summer: n} を集計して返す"""
    url = BASE_URL.format(slug=slug)
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    # サイト側が申告する文字コードが信用できないため、UTF-8だと決め打ちして読み込む
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    counts = defaultdict(lambda: {"spring": 0, "summer": 0})

    table = soup.find("table")
    if table is None:
        print(f"  [警告] {pref}: テーブルが見つかりません")
        return counts

    rows = table.find_all("tr")
    for row in rows[1:]:  # 先頭はヘッダー
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        season_cell = cols[1]
        school_cell = cols[2]

        school = school_cell.get_text(strip=True)
        if not school or school in ("中止",):
            continue

        # 春夏の判定は画像のファイル名 (sun_summer.png / sakura.png) で行う
        img = season_cell.find("img")
        is_summer = bool(img and "summer" in (img.get("src") or ""))
        is_spring = bool(img and "sakura" in (img.get("src") or ""))

        if is_summer:
            counts[school]["summer"] += 1
        elif is_spring:
            counts[school]["spring"] += 1

    return counts


def main():
    all_rows = []
    for pref, slug in PREF_SLUG.items():
        print(f"取得中: {pref}")
        try:
            counts = fetch_prefecture_schools(pref, slug)
        except requests.RequestException as e:
            print(f"  [エラー] {pref}: {e}")
            continue

        for school, c in counts.items():
            all_rows.append({
                "prefecture": pref,
                "school": school,
                "spring_count": c["spring"],
                "summer_count": c["summer"],
            })
        time.sleep(REQUEST_INTERVAL_SEC)

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["prefecture", "school", "spring_count", "summer_count"])
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n完了: {len(all_rows)}校を {OUTPUT_PATH} に書き出しました")


if __name__ == "__main__":
    main()
