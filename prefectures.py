# 都道府県名 -> koshien89.com の blog-category ID
# https://koshien89.com/blog-category-<ID>.html に各都道府県の予選速報記事がある
# ※北海道は夏の予選が「北北海道」「南北海道」に分かれるため、実際の記事タイトルで判定する

PREF_CATEGORY = {
    "北海道": 6,
    "青森": 7, "岩手": 9, "宮城": 11, "秋田": 8, "山形": 10, "福島": 12,
    "茨城": 13, "栃木": 14, "群馬": 15, "埼玉": 16, "千葉": 17, "神奈川": 18, "山梨": 19,
    "東京": 20,
    "新潟": 21, "富山": 23, "石川": 24, "福井": 25, "長野": 22,
    "岐阜": 28, "静岡": 26, "愛知": 27, "三重": 29,
    "滋賀": 30, "京都": 31, "大阪": 32, "兵庫": 33, "奈良": 34, "和歌山": 35,
    "鳥取": 38, "島根": 39, "岡山": 36, "広島": 37, "山口": 40,
    "徳島": 42, "香川": 41, "愛媛": 43, "高知": 44,
    "福岡": 45, "佐賀": 46, "長崎": 47, "熊本": 48, "大分": 49, "宮崎": 50,
    "鹿児島": 51, "沖縄": 52,
}

# 高校野球Ref（対象校リスト取得元）の都道府県 -> URLスラッグ
PREF_SLUG = {
    "北海道": "hokkaido", "青森": "aomori", "岩手": "iwate", "宮城": "miyagi",
    "秋田": "akita", "山形": "yamagata", "福島": "fukushima",
    "茨城": "ibaraki", "栃木": "tochigi", "群馬": "gunma", "埼玉": "saitama",
    "千葉": "chiba", "東京": "tokyo", "神奈川": "kanagawa",
    "新潟": "niigata", "富山": "toyama", "石川": "ishikawa", "福井": "fukui",
    "山梨": "yamanashi", "長野": "nagano", "岐阜": "gifu", "静岡": "shizuoka",
    "愛知": "aichi", "三重": "mie",
    "滋賀": "shiga", "京都": "kyoto", "大阪": "ohsaka", "兵庫": "hyogo",
    "奈良": "nara", "和歌山": "wakayama",
    "鳥取": "tottori", "島根": "shimane", "岡山": "okayama", "広島": "hiroshima", "山口": "yamaguchi",
    "徳島": "tokushima", "香川": "kagawa", "愛媛": "ehime", "高知": "kochi",
    "福岡": "fukuoka", "佐賀": "saga", "長崎": "nagasaki", "熊本": "kumamoto",
    "大分": "ohita", "宮崎": "miyazaki", "鹿児島": "kagoshima", "沖縄": "okinawa",
}
