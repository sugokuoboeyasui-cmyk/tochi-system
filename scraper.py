# -*- coding: utf-8 -*-
"""
scraper.py
・物件概要テーブルから「土地面積」「坪数」をピンポイント正確取得
・周辺広告等の床面積誤爆を完全根絶
・SUUMO公式記載の坪数を直接取得して坪単価を正確計算
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import time
import urllib.parse
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("tochi-scraper")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
REQUEST_TIMEOUT = 25

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "物件データ")
PRESET_FILE = "presets.json"
TSUBO_SQM = 3.305785

SHEET_HEADERS = [
    "物件ID", "情報ソース", "物件タイトル", "所在地", "価格(万円)",
    "土地面積(㎡)", "土地面積(坪)", "坪単価(万円/坪)", "駅徒歩(分)",
    "バス利用", "総区画数", "接道状況", "現況", "建築条件", "注意タグ",
    "備考", "詳細URL", "初回取得日時"
]

CAUTION_KEYWORDS = [
    "私道持分", "古家あり", "傾斜地", "崖", "がけ", "擁壁",
    "高低差", "再建築不可", "旗竿地", "路地状敷地", "路地上敷地"
]

def polite_sleep(min_sec=1.2, max_sec=2.0):
    time.sleep(random.uniform(min_sec, max_sec))

def fetch_html(url: str) -> str | None:
    try:
        res = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        res.encoding = "utf-8"
        return res.text
    except Exception as e:
        logger.warning("HTTP取得エラー: %s (%s)", url, e)
        return None
    finally:
        polite_sleep()

def parse_price(text: str | None) -> float | None:
    if not text:
        return None
    t = text.replace(",", "").replace(" ", "").replace("　", "")
    oku = 0.0
    m_oku = re.search(r"(\d+(?:\.\d+)?)\s*億", t)
    if m_oku:
        oku = float(m_oku.group(1)) * 10000
    man = 0.0
    m_man = re.search(r"(\d+(?:\.\d+)?)\s*万", t)
    if m_man:
        man = float(m_man.group(1))
    total = oku + man
    if total == 0:
        m_num = re.search(r"(\d+(?:\.\d+)?)", t)
        if m_num:
            total = float(m_num.group(1))
    return round(total, 1) if total else None

def extract_area_and_tsubo(area_text: str) -> tuple[float | None, float | None]:
    """SUUMOの『土地面積』欄のテキストから㎡と坪数を直接ピンポイント抽出"""
    if not area_text:
        return None, None

    # 表記ゆれ統一（上付き文字やスペースの除去）
    cleaned = area_text.replace(" ", "").replace("　", "").replace("m2", "㎡").replace("m²", "㎡")

    # 1. 坪数の直接抽出（例: 『（59.63坪）』や『約130坪』）
    tsubo_val = None
    m_tsubo = re.search(r"(\d+(?:\.\d+)?)\s*坪", cleaned)
    if m_tsubo:
        tsubo_val = round(float(m_tsubo.group(1)), 2)

    # 2. ㎡数の抽出（例: 『197.13㎡』や『197.13m2』）
    sqm_val = None
    m_sqm = re.search(r"(\d+(?:\.\d+)?)\s*㎡", cleaned)
    if not m_sqm:
        m_sqm = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if m_sqm:
        sqm_val = round(float(m_sqm.group(1)), 2)

    # 相互補完
    if sqm_val and not tsubo_val:
        tsubo_val = round(sqm_val / TSUBO_SQM, 2)
    elif tsubo_val and not sqm_val:
        sqm_val = round(tsubo_val * TSUBO_SQM, 2)

    return sqm_val, tsubo_val

def extract_caution_tags(road_text: str, full_text: str) -> list[str]:
    tags = []
    m_w = re.search(r"(?:幅員|幅)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*m", road_text or full_text)
    if m_w:
        w = float(m_w.group(1))
        if w < 4.0:
            tags.append(f"⚠️道幅狭小({w:.1f}m)")
    if "セットバック" in full_text:
        tags.append("⚠️要セットバック")
    for kw in CAUTION_KEYWORDS:
        if kw in full_text:
            tags.append(f"⚠️{kw}")
    return list(dict.fromkeys(tags))

def make_property_id(source: str, url: str | None, title: str | None, address: str | None) -> str:
    base = f"{source}|{url or ''}|{title or ''}|{address or ''}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]

# --------------------------------------------------------------------------
# 詳細ページの物件概要テーブルから全項目を精密ピンポイント取得
# --------------------------------------------------------------------------
def fetch_detail_info(detail_url: str) -> dict:
    info = {
        "road": "", "status": "", "remarks": "", "extra_text": "",
        "scale": 1, "area_sqm": None, "tsubo": None
    }
    html = fetch_html(detail_url)
    if not html:
        return info

    soup = BeautifulSoup(html, "lxml")
    full_text = soup.get_text(" ", strip=True)
    info["extra_text"] = full_text

    # 区画数
    m_scale = re.search(r"(?:総区画数|販売区画数)[^\d]*(\d+)\s*区画", full_text)
    if m_scale:
        info["scale"] = int(m_scale.group(1))

    # 物件概要テーブルを1行ずつ解析
    for th in soup.find_all(["th", "dt"]):
        title = th.get_text(strip=True)
        td = th.find_next_sibling(["td", "dd"])
        if not td:
            continue
        val = td.get_text(" ", strip=True)

        if "土地面積" in title or "敷地面積" in title:
            # ★土地面積のセルから直接抽出（周辺店舗の床面積などの誤爆を完全排除）
            sqm, tsb = extract_area_and_tsubo(val)
            info["area_sqm"] = sqm
            info["tsubo"] = tsb
        elif "接道" in title or "道路" in title:
            info["road"] = val
        elif "現況" in title:
            info["status"] = val
        elif "備考" in title or "特記事項" in title:
            info["remarks"] = val

    return info

def get_suumo_official_urls() -> dict[str, str]:
    url_map = {}
    top_url = "https://suumo.jp/tochi/fukuoka/"
    html = fetch_html(top_url)
    if not html:
        return url_map

    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if "/tochi/fukuoka/sc_" in href and text:
            clean_name = re.sub(r"[\(\（].*?[\)\）]|\d+件", "", text).strip()
            url_map[clean_name] = urljoin(top_url, href)
    return url_map

def get_all_presets_mapped() -> dict[str, set[str]]:
    area_to_towns: dict[str, set[str]] = {}
    if os.path.exists(PRESET_FILE):
        try:
            with open(PRESET_FILE, "r", encoding="utf-8") as f:
                presets = json.load(f)
                for p in presets.values():
                    saved_keys = p.get("town_keys", [])
                    for k in saved_keys:
                        if "_" in k:
                            a, t = k.split("_", 1)
                            if a not in area_to_towns:
                                area_to_towns[a] = set()
                            area_to_towns[a].add(t)
        except Exception:
            pass
    return area_to_towns

# --------------------------------------------------------------------------
# メイン処理
# --------------------------------------------------------------------------
def main() -> None:
    logger.info("=== 定期巡回スクレイピングを開始します ===")

    raw_id = SPREADSHEET_ID.strip().strip('"').strip("'")
    m_id = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", raw_id)
    target_sheet_id = m_id.group(1) if m_id else raw_id
    if not target_sheet_id:
        logger.error("SPREADSHEET_ID が未設定です")
        return

    try:
        json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        if json_str:
            creds = Credentials.from_service_account_info(json.loads(json_str), scopes=scopes)
        else:
            creds = Credentials.from_service_account_file(os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json"), scopes=scopes)

        client = gspread.authorize(creds)
        sh = client.open_by_key(target_sheet_id)
        try:
            ws = sh.worksheet(WORKSHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=5000, cols=len(SHEET_HEADERS) + 2)
            ws.append_row(SHEET_HEADERS)

        existing_header = ws.row_values(1)
        if not existing_header or len(existing_header) < len(SHEET_HEADERS):
            ws.delete_rows(1)
            ws.insert_row(SHEET_HEADERS, index=1)

        col = ws.col_values(1)
        existing_ids = set(col[1:]) if len(col) > 1 else set()
        logger.info("既存登録済み件数: %d 件（既知の物件はスキップします）", len(existing_ids))
    except Exception as e:
        logger.error("スプレッドシート接続エラー: %s", e)
        return

    official_urls = get_suumo_official_urls()
    area_to_towns = get_all_presets_mapped()
    if not area_to_towns:
        logger.warning("プリセットが保存されていません。画面でエリアを選んで保存してください。")
        return

    logger.info("🎯 今回巡回する全エリア: %s", list(area_to_towns.keys()))

    new_rows = []
    seen_in_this_run = set()
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for area_name, allowed_towns in area_to_towns.items():
        base_url = None
        short_name = area_name.replace("北九州市", "").replace("遠賀郡", "").strip()
        for k, u in official_urls.items():
            if area_name in k or short_name == k or k in area_name:
                base_url = u
                break

        if not base_url:
            encoded_kwd = urllib.parse.quote(area_name)
            base_url = f"https://suumo.jp/tochi/fukuoka/?kwd={encoded_kwd}"

        logger.info("--- [%s] の巡回を開始 (対象町名: %d件 / URL: %s) ---", area_name, len(allowed_towns), base_url)
        page = 1

        while True:
            separator = "&" if "?" in base_url else "?"
            page_url = f"{base_url}{separator}pn={page}" if page > 1 else base_url
            html = fetch_html(page_url)
            if not html:
                break

            soup = BeautifulSoup(html, "lxml")
            items = soup.select("div.property_unit, div.cassetteitems, div.unit") or soup.select("div[class*='property']")
            if not items:
                break

            for item in items:
                try:
                    link_node = item.select_one("a[href*='/tochi/']")
                    if not link_node or not link_node.get("href"):
                        continue
                    url = urljoin(base_url, link_node.get("href"))
                    title_node = item.select_one("h2, h3, a[href*='/tochi/']")
                    title = title_node.get_text(strip=True) if title_node else f"{area_name}売地"
                    text_all = item.get_text(" ", strip=True)

                    m_addr = re.search(r"(福岡県[^\s　]+|[^\s　]+[市区町村][^\s　]+)", text_all)
                    address = m_addr.group(1) if m_addr else area_name

                    # 町名の厳密照合
                    is_match = False
                    for t in allowed_towns:
                        if t in address:
                            idx = address.find(t)
                            if idx == 0 or address[idx-1] in ["区", "市", "町", "村", "県", "大字"]:
                                is_match = True
                                break
                        elif t in title:
                            is_match = True
                            break

                    if not is_match:
                        continue

                    pid = make_property_id("SUUMO", url, title, address)
                    if pid in existing_ids or pid in seen_in_this_run:
                        continue
                    seen_in_this_run.add(pid)

                    # 詳細ページ解析
                    logger.info("✨【新着解析中】%s (%s)", title[:20], address)
                    detail = fetch_detail_info(url)

                    # 価格
                    m_price = re.search(r"(\d+(?:億\d+)?(?:,\d+)?万円|\d+万円)", text_all)
                    price_man = parse_price(m_price.group(1)) if m_price else None

                    # ★土地面積と坪数を詳細テーブルからダイレクト取得
                    area_sqm = detail.get("area_sqm")
                    tsubo = detail.get("tsubo")

                    # もし詳細テーブルで取れなかった場合は一覧カードのテキストから補完
                    if not area_sqm or not tsubo:
                        # タイトル内の「約130坪」などを救済
                        m_title_tsubo = re.search(r"(\d+(?:\.\d+)?)\s*坪", title)
                        if m_title_tsubo:
                            tsubo = float(m_title_tsubo.group(1))
                            area_sqm = round(tsubo * TSUBO_SQM, 2)
                        else:
                            # 一覧カード内の面積テキストから抽出
                            m_card_sqm = re.search(r"(\d+(?:\.\d+)?)\s*(?:㎡|m2|m²)", text_all)
                            if m_card_sqm:
                                area_sqm = float(m_card_sqm.group(1))
                                tsubo = round(area_sqm / TSUBO_SQM, 2)

                    # 坪単価の計算
                    tsubo_price = round(price_man / tsubo, 1) if (price_man and tsubo) else None

                    # 駅徒歩
                    m_walk = re.search(r"(?:徒歩|歩)\s*(\d+)\s*分", f"{text_all} {detail.get('extra_text', '')}")
                    walk_min = int(m_walk.group(1)) if m_walk else ""
                    has_bus = "あり" if "バス" in f"{text_all} {detail.get('extra_text', '')}" else "なし"
                    scale_val = detail.get("scale", 1)

                    # 建築条件
                    combined = f"{text_all} {detail.get('extra_text', '')}"
                    if "建築条件なし" in combined or "条件なし" in combined:
                        condition = "なし"
                    elif "建築条件付" in combined:
                        condition = "あり"
                    else:
                        condition = "情報なし"

                    status_text = detail.get("status") or ""
                    if not status_text:
                        m_stat = re.search(r"(更地|古家あり|上物あり|宅地)", combined)
                        status_text = m_stat.group(1) if m_stat else ""

                    road_text = detail.get("road") or ""
                    tags = extract_caution_tags(road_text, combined)

                    new_rows.append([
                        pid, "SUUMO", title, address,
                        price_man if price_man is not None else "",
                        area_sqm if area_sqm is not None else "",
                        tsubo if tsubo is not None else "",
                        tsubo_price if tsubo_price is not None else "",
                        walk_min, has_bus, scale_val,
                        road_text, status_text, condition,
                        ", ".join(tags), detail.get("remarks", ""), url, fetched_at
                    ])
                except Exception:
                    continue

            has_next = any("次へ" in a.get_text() for a in soup.find_all("a"))
            if len(items) < 15 and not has_next:
                break
            page += 1
            if page > 12:
                break

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        logger.info("🎉 新着 %d 件を正しい面積・坪数で追記保存しました！", len(new_rows))
    else:
        logger.info("該当する新着物件はありませんでした（最新状態です）")

    logger.info("=== 巡回処理を完了しました ===")

if __name__ == "__main__":
    main()
