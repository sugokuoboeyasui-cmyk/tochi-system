# -*- coding: utf-8 -*-
"""
app.py (超高速・ブラウザフリーズ完全防止版)
1000町名の描画負荷を極小化し、Chromeが一瞬でサクサク開く軽量設計
"""
from __future__ import annotations

import json
import os
import re
import time

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

st.set_page_config(
    page_title="福岡北部 売地情報 精密検索",
    page_icon="🏗️",
    layout="wide",
)

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

PRESET_FILE = "presets.json"
MAX_PRESETS = 10

def get_config(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val:
        return val
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

SPREADSHEET_ID = get_config("SPREADSHEET_ID", "")
WORKSHEET_NAME = get_config("WORKSHEET_NAME", "物件データ")

NUMERIC_COLUMNS = ["価格(万円)", "土地面積(㎡)", "土地面積(坪)", "坪単価(万円/坪)", "駅徒歩(分)", "総区画数"]

# 全エリアマスタ定義（北九州7区 ＋ 周辺9市町）
MASTER_AREAS = {
    "北九州市小倉北区": {
        "あ行・か行": ["愛宕", "浅野", "朝日ケ丘", "足立", "足原", "大字足原", "赤坂", "赤坂海岸", "大字藍島", "青葉", "泉台", "大字板櫃", "板櫃町", "今町", "井堀", "鋳物師町", "魚町", "宇佐町", "大田町", "大手町", "大畠", "大字馬島", "鍛冶町", "片野", "片野新町", "金田", "上到津", "上富野", "香春口", "神岳", "貴船町", "木町", "京町", "清水", "霧ケ丘", "金鶏町", "熊谷", "熊本", "黒住町", "黒原", "黄金", "江南町", "許斐町", "米町", "小文字", "紺屋町", "大字富野", "大字中井"],
        "さ行・た行": ["菜園場", "堺町", "三郎丸", "皿山町", "山門町", "重住", "篠崎", "下到津", "下富野", "昭和町", "白銀", "白萩町", "神幸町", "新高田", "寿山町", "城内", "城野団地", "末広", "須賀町", "砂津", "船頭町", "船場町", "高尾", "高浜", "高坊", "高見台", "高峰町", "竪林町", "竪町", "田町", "大門", "常盤町", "富野台", "親和町"],
        "な行・は行": ["中井", "中井口", "中井浜", "中島", "中津口", "長浜町", "西港町", "萩崎町", "原町", "馬借", "日明", "東篠崎", "東城野町", "東港", "平松町", "古船場町", "弁天町"],
        "ま行〜わ行": ["真鶴", "緑ケ丘", "南丘", "三萩野", "都", "妙見町", "室町", "明和町", "山田町", "吉野町", "若富士町"]
    },
    "北九州市小倉南区": {
        "あ行・か行": ["安部山", "大字合馬", "市瀬", "大字市丸", "大字井手浦", "石田町", "大字石田", "石田南", "大字石原町", "大字隠蓑", "隠蓑", "空港北町", "葛原", "大字葛原", "葛原高松", "葛原東", "葛原本町", "葛原元町", "企救丘", "北方", "大字木下", "朽網西", "朽網東", "大字朽網", "大字小森", "蒲生", "大字蒲生", "上石田", "上葛原", "上曽根", "上曽根新町", "上貫", "上吉田", "大字志井"],
        "さ行・た行": ["重住", "下石田", "志井", "志井公園", "志井鷹羽台", "志徳", "下城野", "下曽根", "下曽根新町", "下貫", "下南方", "下吉田", "新曽根", "新道寺", "大字新道寺", "城野", "星和台", "曽根", "大字曽根", "曽根北町", "曽根新田", "曽根新田北", "曽根新田南", "田原", "田原新町", "高野", "大字高津尾", "大字田代", "大字辻三", "津田", "大字津田", "津田新町", "津田南町", "大字道原", "徳吉西", "徳吉東", "徳吉南", "大字徳吉", "徳力", "徳力新町", "徳力団地", "大字徳力"],
        "な行・は行": ["長尾", "長行西", "長行東", "大字長行", "中曽根", "中曽根新町", "中曽根東", "中貫", "中貫本町", "中吉田", "長野", "大字長野", "長野東町", "長野本町", "西貫", "西水町", "蜷田若園", "沼", "大字沼", "沼新町", "沼南町", "沼本町", "沼緑町", "貫", "大字貫", "貫弥生が丘", "八幡町", "葉山町", "春ケ丘", "大字春吉", "日の出町", "平尾台", "富士見", "大字堀越"],
        "ま行〜わ行": ["舞ケ丘", "南若園町", "南方", "大字南方", "大字母原", "守恒", "守恒本町", "八重洲町", "山手", "大字山本", "湯川", "湯川新町", "大字湯川", "吉田", "大字吉田", "吉田にれの木坂", "呼野", "大字呼野", "若園", "横代北町", "横代葉山", "横代東町", "横代南町", "大字横代"]
    },
    "北九州市戸畑区": {
        "あ行・か行": ["旭町", "浅生", "一枝", "沖台", "川代", "観音寺町", "北鳥旗町", "銀座", "金比羅町", "小芝", "大字戸畑"],
        "さ行・た行": ["幸町", "境川", "沢見", "三六町", "汐井町", "正津町", "新池", "新川町", "菅原", "仙水町", "千防", "椎ノ木町", "高峰", "土取町", "天神", "天籟寺", "飛幡町"],
        "な行・は行": ["中原新町", "中原西", "中原東", "大字中原", "中本町", "西大谷", "西鞘ケ谷町", "初音町", "東大谷", "東鞘ケ谷町", "福柳木"],
        "ま行〜わ行": ["牧山", "牧山海岸", "牧山新町", "丸町", "南鳥旗町", "明治町", "元宮町", "夜宮"]
    },
    "北九州市門司区": {
        "あ行・か行": ["青葉台", "大字伊川", "泉ケ丘", "稲積", "大字今津", "梅ノ木町", "老松町", "大久保", "大字大積", "大字大里", "大里新町", "大里桜ケ丘", "大里戸ノ上", "大里原町", "大里東", "大里東口", "大里本町", "大里元町", "大里桃山町", "奥田", "花月園", "風師", "春日町", "片上海岸", "片上町", "上二十町", "上藤松", "上本町", "上馬寄", "吉志", "吉志新町", "大字吉志", "大字喜多久", "北川町", "旧門司", "清滝", "清見", "清見佐夜町", "葛葉", "黒川西", "黒川東", "大字黒川", "黄金町", "小松町", "小森江", "大字小森江"],
        "さ行・た行": ["栄町", "大字猿喰", "社ノ木", "庄司町", "白野江", "大字白野江", "城山町", "新開", "新原町", "新門司", "新門司北", "瀬戸町", "下二十町", "下馬寄", "寺内", "高砂町", "高田", "太刀浦海岸", "谷町", "田野浦", "田野浦海岸", "大字田野浦", "恒見町", "大字恒見"],
        "な行・は行": ["中二十町", "中町", "永黒", "長谷", "鳴竹", "西海岸", "錦町", "西新町", "畑田町", "大字畑", "浜町", "羽山", "原町別院", "光町", "東新町", "東本町", "東馬寄", "東港町", "東門司", "柄杓田町", "大字柄杓田", "広石", "藤松", "二タ松町", "不老町", "別院", "法師庵", "本町"],
        "ま行〜わ行": ["松崎町", "松原", "丸山", "丸山町", "丸山吉野町", "緑ケ丘", "港町", "南本町", "大字門司", "元清滝", "桃山台", "柳原町", "柳町", "矢筈町"]
    },
    "北九州市八幡西区": {
        "あ行・か行": ["相生町", "青山", "赤坂", "浅川", "大字浅川", "浅川学園台", "浅川台", "浅川日の峯", "浅川町", "穴生", "大字穴生", "市瀬", "大字市瀬", "池田", "石坂", "泉ケ浦", "医生ケ丘", "岩崎", "上の原", "永犬丸", "大字永犬丸", "永犬丸西町", "永犬丸東町", "永犬丸南町", "大浦", "大平", "大平台", "岡田町", "沖田", "折尾", "大字折尾", "春日台", "香月中央", "香月西", "大字香月", "上香月", "上上津役", "大字上上津役", "岸の浦", "北鷹見町", "吉祥寺町", "貴船台", "京良城町", "楠木", "大字楠橋", "楠橋上方", "楠橋下方", "楠橋西", "楠橋東", "楠橋南", "楠北", "熊手", "大字熊手", "熊西", "黒崎", "黒崎城石", "皇后崎町", "河桃町", "紅梅", "光明", "木屋瀬", "木屋瀬東", "大字木屋瀬", "金剛", "大字金剛", "小鷺田町", "大字小敷", "小嶺", "小嶺台", "大字小嶺", "御開", "洞南町"],
        "さ行・た行": ["幸神", "桜ケ丘町", "さつき台", "里中", "三ケ森", "下上津役", "下上津役元町", "下畑町", "白岩町", "自由ケ丘", "陣原", "大字陣原", "陣山", "菅原町", "清納", "星和町", "瀬板", "鷹の巣", "鷹見台", "高江", "竹末", "田町", "大膳", "茶売町", "茶屋の原", "千代", "千代ケ崎", "築地町", "筒井町", "鉄王", "鉄竜", "東筑", "塔野", "洞北町", "友田"],
        "な行・は行": ["中須", "中の原", "長崎町", "鳴水町", "大字鳴水", "西王子町", "西折尾町", "西川頭町", "西神原町", "西鳴水", "西曲里町", "野面", "大字野面", "萩原", "白山", "畑谷町", "大字畑", "馬場山", "馬場山西", "馬場山原", "馬場山東", "馬場山緑", "大字馬場山", "東石坂町", "東王子町", "東折尾町", "東川頭町", "東神原町", "東鳴水", "東浜町", "東曲里町", "引野", "樋口町", "日吉台", "平尾町", "藤田", "大字藤田", "藤原", "船越", "舟町", "別所町", "別当町", "星ケ丘", "堀川町", "本城", "本城学研台", "本城東", "大字本城"],
        "ま行〜わ行": ["町上津役西", "町上津役東", "的場町", "真名子", "丸尾町", "三ツ頭", "光貞台", "緑ケ丘", "南王子町", "南鷹見町", "南八千代町", "美原町", "美吉野町", "椋枝", "元城町", "森下町", "屋敷", "八枝", "八千代町", "山寺町", "夕原町", "養福寺町", "力丸町", "若葉", "割子川"]
    },
    "北九州市八幡東区": {
        "あ行・か行": ["荒手", "荒生田", "石坪町", "猪倉町", "祝町", "枝光", "枝光本町", "大字枝光", "大蔵", "大字大蔵", "大谷", "大平町", "大宮町", "尾倉", "大字尾倉", "勝山", "上本町", "神山町", "川淵町", "河内", "清田", "祇園", "祇園原町", "景勝町", "大字小熊野"],
        "さ行・た行": ["山路", "山路松尾町", "山王", "昭和", "白川町", "末広町", "諏訪", "高見", "竹下町", "大字田代", "田代町", "茶屋町", "中央", "槻田", "天神町"],
        "な行・は行": ["中尾", "中畑", "西台良町", "西本町", "西丸山町", "羽衣町", "八王寺町", "花尾町", "春の町", "東台良町", "東田", "東鉄町", "東丸山町", "東山", "日の出", "平野", "藤見町", "帆柱"],
        "ま行〜わ行": ["前田", "大字前田", "松尾町", "宮田町", "宮の町", "桃園", "豊町", "大字若松"]
    },
    "北九州市若松区": {
        "あ行・か行": ["青葉台西", "青葉台東", "青葉台南", "赤岩町", "赤崎町", "赤島町", "大字蜑住", "大字有毛", "大字安瀬", "大字安屋", "今光", "栄盛川町", "老松", "大池町", "大井戸町", "大谷町", "大字大鳥居", "大字乙丸", "片山", "上原町", "鴨生田", "北浜", "北湊町", "久岐の浜", "くきのうみ中央", "小石本村町", "大字小石", "小糸町", "向洋町", "大字小敷", "小敷ひびきの", "大字小竹"],
        "さ行・た行": ["桜町", "迫田町", "塩屋", "大字塩屋", "下原町", "修多羅", "大字修多羅", "新大谷町", "高須北", "高須西", "高須東", "高須南", "大字高須", "大字竹並", "棚田町", "童子丸", "童子丸町", "大字頓田"],
        "な行・は行": ["中川町", "中畑町", "波打町", "西小石町", "西園町", "西天神町", "西畑町", "白山", "畠田", "大字畠田", "畑谷町", "花野路", "浜町", "払川", "大字払川", "原町", "響町", "響南町", "ひびきの", "ひびきの北", "ひびきの南", "深町", "藤木", "大字藤木", "藤ノ木", "二島", "大字二島", "古前", "本町"],
        "ま行〜わ行": ["南二島", "宮前町", "宮丸", "山手町", "山ノ堂町", "百合野町", "用勺町", "和田町", "柳崎町"]
    },
    "直方市": {
        "あ行・か行": ["大字赤地", "大字植木", "大字永満寺", "大字金田屋敷", "大字上境", "大字上新入", "大字上頓野", "大字感田", "大字下境", "大字下新入", "大字知古", "大字頓野", "大字中泉", "大字直方", "大字畑", "大字山部"],
        "さ行・た行": ["神正町", "新知町", "新町", "須崎町", "知古", "津田町", "殿町"],
        "な行・は行": ["日吉町", "古町"],
        "ま行〜わ行": ["丸山町", "溝堀", "湯野原"]
    },
    "中間市": {
        "あ行・か行": ["大字岩瀬", "大字上底井野", "上蓮花寺", "大字下大隈", "大字中底井野", "大字垣生", "朝霧", "池田", "扇ヶ浦", "大辻町", "小田ヶ浦", "岩瀬西町", "岩瀬", "大根土"],
        "さ行・た行": ["太賀", "桜台", "通谷", "土手ノ内", "浄花町", "中央", "下蓮花寺"],
        "な行・は行": ["星ヶ丘", "鍋山町", "中尾", "七重町", "深坂", "中間", "長津", "中鶴", "東中間"],
        "ま行〜わ行": ["蓮花寺", "弥生", "松ヶ岡"]
    },
    "宗像市": {
        "あ行・か行": ["朝野", "朝町", "池浦", "稲元", "王丸", "大井", "大井台", "大穂", "大穂町", "河東", "久原", "大谷", "泉ヶ丘", "広陵台", "青葉台", "桜美台", "アスティ", "くりえいと", "赤間", "赤間文教町", "石丸", "池田", "江口", "鐘崎", "公園通り", "上八", "神湊", "大島", "赤間駅前", "大井南"],
        "さ行・た行": ["栄町", "三郎丸", "自由ヶ丘", "自由ヶ丘西町", "城西ヶ丘", "須恵", "田久", "田熊", "武丸", "土穴", "東郷", "自由ヶ丘南", "天平台", "桜", "樟陽台", "徳重", "地島", "田島", "田野", "多禮"],
        "な行・は行": ["名残", "野坂", "葉山", "原町", "ひかりヶ丘", "日の里", "平等寺", "冨地原", "深田", "平井"],
        "ま行〜わ行": ["曲", "光岡", "緑町", "村山田", "用山", "山田", "吉留", "和歌美台", "陵厳寺", "牟田尻", "吉田", "三倉", "宮田"]
    },
    "遠賀郡遠賀町": {
        "あ行・か行": ["大字浅木", "大字今古賀", "大字老良", "大字尾崎", "大字鬼津", "大字上別府", "大字木守", "大字島津", "大字広渡", "大字別府", "大字虫生津", "大字若松", "遠賀川", "旧停", "浅木", "駅みなみ"],
        "さ行・た行": ["島門", "田園"],
        "な行・は行": ["広渡", "芙蓉"],
        "ま行〜わ行": ["松の本", "若葉台", "虫生津南", "蓮角"]
    },
    "遠賀郡岡垣町": {
        "あ行・か行": ["大字内浦", "大字海老津", "大字黒山", "大字上畑", "大字高倉", "大字手野", "大字戸切", "大字糠塚", "大字野間", "大字波津", "大字原", "大字三吉", "大字山田", "大字吉木", "公園通り", "旭台", "旭南", "高陽台", "海老津駅前", "海老津駅南", "海老津"],
        "さ行・た行": ["桜台", "中央台"],
        "な行・は行": ["鍋田", "東高陽", "東松原", "東山田", "野間", "東高倉", "野間南"],
        "ま行〜わ行": ["松ケ台", "南高陽", "山田峠", "百合ケ丘", "吉木西", "吉木東"]
    },
    "遠賀郡芦屋町": {
        "あ行・か行": ["大字芦屋", "祇園町", "大字山鹿", "江川台"],
        "さ行・た行": ["幸町", "白浜町", "正門町", "船頭町", "高浜町"],
        "な行・は行": ["中ノ浜", "西浜町", "浜口町", "花美坂"],
        "ま行〜わ行": ["緑ケ丘", "山鹿"]
    },
    "遠賀郡水巻町": {
        "あ行・か行": ["梅ノ木団地", "大字頃末", "大字二", "大字吉田", "猪熊", "伊左座", "おかの台", "古賀", "杁", "頃末北", "頃末南", "鯉口"],
        "さ行・た行": ["下二東", "下二西", "立屋敷", "高松", "高尾", "中央"],
        "な行・は行": ["二西", "二東", "樋口", "樋口東"],
        "ま行〜わ行": ["緑ケ丘", "宮尾台", "牟田", "美吉野", "吉田西", "吉田東", "吉田団地", "吉田南"]
    },
    "鞍手郡": {
        "あ行・か行": ["大字赤地", "大字勝野", "大字御徳", "大字新山崎", "大字南良津", "大字新多", "大字猪倉", "大字小牧", "大字上木月", "大字木月", "大字中山", "大字永谷", "大字新北", "大字新延", "大字長谷", "大字古門", "大字室木", "大字八尋"],
        "さ行・た行": [], "な行・は行": [], "ま行〜わ行": ["弥生"]
    },
    "京都郡": {
        "あ行・か行": ["大字集", "大字雨窪", "大字新津", "磯浜町", "大字稲光", "大字岡崎", "大字尾倉", "大字上片島", "大字苅田", "京町", "大字葛川", "大字黒添", "大字下新津", "大字下片島", "大字鋤崎", "大字谷", "大字馬場", "大字提", "大字二崎", "大字法正寺", "大字松山", "大字光国", "大字南原", "大字山口", "大字与原", "大字浜町", "空港南町", "新津", "尾倉", "小波瀬", "近衛ヶ丘", "呰見", "綾野", "有久", "勝山池田", "勝山岩熊", "勝山上田", "勝山浦河内", "勝山大久保", "勝山上矢山", "勝山黒田", "勝山長川", "勝山松田", "勝山箕田", "勝山宮原", "勝山矢山", "上坂", "上原", "彦徳", "国作", "国分"],
        "さ行・た行": ["幸町", "神田町", "新浜町", "殿川町", "富久町", "鳥越町", "桜ヶ丘", "新松山", "犀川鐙畑", "犀川犬丸", "犀川内垣", "犀川生立", "犀川扇谷", "犀川大熊", "犀川大坂", "犀川大村", "犀川上伊良原", "犀川上高屋", "犀川木井馬場", "犀川喜多良", "犀川木山", "犀川崎山", "犀川下伊良原", "犀川下高屋", "犀川末江", "犀川続命院", "犀川谷口", "犀川花熊", "犀川久富", "犀川古川", "犀川帆柱", "犀川本庄", "犀川八ツ溝", "犀川柳瀬", "犀川山鹿", "犀川横瀬", "下原", "節丸", "惣社", "田中", "徳政", "徳永", "豊津"],
        "な行・は行": ["長浜町"],
        "ま行〜わ行": ["松原町", "港町", "若久町", "与原", "光冨", "吉岡"]
    }
}

ALL_AREA_TOWNS = []
for a_name, groups in MASTER_AREAS.items():
    for g_towns in groups.values():
        for t in g_towns:
            ALL_AREA_TOWNS.append((a_name, t))

def load_presets() -> dict:
    if os.path.exists(PRESET_FILE):
        try:
            with open(PRESET_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_presets(presets: dict):
    with open(PRESET_FILE, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)

def extract_area_and_town(address: str) -> tuple[str, str]:
    addr = str(address).replace("福岡県", "").strip()
    matched_area = "その他"
    for a in MASTER_AREAS.keys():
        short_a = a.replace("北九州市", "")
        if a in addr or short_a in addr:
            matched_area = a
            break

    matched_town = "その他"
    candidate_towns = [t for a, t in ALL_AREA_TOWNS if (matched_area == "その他" or a == matched_area)]
    for t in sorted(candidate_towns, key=len, reverse=True):
        if t in addr:
            matched_town = t
            break

    return matched_area, matched_town

@st.cache_data(ttl=600, show_spinner="最新データを読み込み中...")
def load_data() -> pd.DataFrame:
    raw_id = SPREADSHEET_ID.strip().strip('"').strip("'")
    m_id = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", raw_id)
    target_id = m_id.group(1) if m_id else raw_id
    if not target_id:
        st.error("❌ スプレッドシートIDが空です。")
        return pd.DataFrame()

    json_str = get_config("GOOGLE_SERVICE_ACCOUNT_JSON")
    try:
        if json_str:
            if isinstance(json_str, dict):
                info = json_str
            else:
                info = json.loads(json_str)

            # PEMキーの改行崩れ（MalformedFraming）を自動修復
            if "private_key" in info and isinstance(info["private_key"], str):
                info["private_key"] = info["private_key"].replace("\\n", "\n")

            creds = Credentials.from_service_account_info(info, scopes=GOOGLE_SCOPES)
        else:
            key_file = get_config("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
            creds = Credentials.from_service_account_file(key_file, scopes=GOOGLE_SCOPES)
    except Exception as e:
        st.error(f"❌ JSONキーの読み込みに失敗しました: {e}")
        return pd.DataFrame()

    try:
        client = gspread.authorize(creds)
        sh = client.open_by_key(target_id)
        ws = sh.worksheet(WORKSHEET_NAME)
        records = ws.get_all_records()
    except Exception as e:
        st.error(f"❌ スプレッドシート接続エラーの正体: {e}")
        return pd.DataFrame()

    df = pd.DataFrame(records)
    if df.empty:
        return df

    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "駅徒歩(分)" not in df.columns or df["駅徒歩(分)"].isna().all():
        df["駅徒歩(分)"] = df.apply(
            lambda r: float(re.search(r"(?:徒歩|歩)\s*(\d+)\s*分", f"{r.get('物件タイトル', '')} {r.get('備考', '')}").group(1))
            if re.search(r"(?:徒歩|歩)\s*(\d+)\s*分", f"{r.get('物件タイトル', '')} {r.get('備考', '')}") else None,
            axis=1
        )

    if "バス利用" not in df.columns:
        df["バス利用"] = df.apply(lambda r: "あり" if "バス" in f"{r.get('物件タイトル', '')} {r.get('備考', '')}" else "なし", axis=1)

    if "総区画数" not in df.columns:
        df["総区画数"] = df.apply(
            lambda r: float(re.search(r"(?:全|総)\s*(\d+)\s*区画", f"{r.get('物件タイトル', '')} {r.get('備考', '')}").group(1))
            if re.search(r"(?:全|総)\s*(\d+)\s*区画", f"{r.get('物件タイトル', '')} {r.get('備考', '')}") else 1.0,
            axis=1
        )

    df[["市区", "町名"]] = df["所在地"].apply(lambda a: pd.Series(extract_area_and_town(a)))
    return df

# --------------------------------------------------------------------------
# メイン画面初期化
# --------------------------------------------------------------------------
st.title("🏗️ 福岡北部 売地情報 精密検索システム")

try:
    df = load_data()
except Exception:
    df = pd.DataFrame()

# ★件数計算を一瞬で終わらせる事前インデックス作成（フリーズ完全根絶）
town_counts = df["町名"].value_counts().to_dict() if not df.empty and "町名" in df.columns else {}
area_counts = df["市区"].value_counts().to_dict() if not df.empty and "市区" in df.columns else {}

if "init_towns_fast" not in st.session_state:
    for a, t in ALL_AREA_TOWNS:
        st.session_state[f"chk_t_{a}_{t}"] = False
    st.session_state["init_towns_fast"] = True

# --------------------------------------------------------------------------
# サイドバー
# --------------------------------------------------------------------------
st.sidebar.header("🔎 条件絞り込み")

if st.sidebar.button("🔄 最新データに更新", width="stretch"):
    load_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📂 検索条件プリセット")

presets = load_presets()
preset_names = list(presets.keys())

col_sel, col_del = st.sidebar.columns([4, 1])
selected_preset = col_sel.selectbox(
    "保存した条件を選ぶ",
    options=["-- 選択してください --"] + preset_names,
    index=0,
    label_visibility="collapsed"
)

if selected_preset != "-- 選択してください --":
    p_data = presets[selected_preset]
    saved_keys = set(p_data.get("town_keys", []))
    for a, t in ALL_AREA_TOWNS:
        st.session_state[f"chk_t_{a}_{t}"] = (f"{a}_{t}" in saved_keys)

if selected_preset != "-- 選択してください --":
    if col_del.button("🗑️"):
        del presets[selected_preset]
        save_presets(presets)
        st.rerun()

with st.sidebar.expander("💾 現在の条件を新しく保存"):
    if len(presets) >= MAX_PRESETS:
        st.warning("上限（10件）です。")
    else:
        new_name = st.text_input("設定名（例：客A 水巻町のみ）")
        if st.button("保存する"):
            if new_name.strip():
                cur_keys = [f"{a}_{t}" for a, t in ALL_AREA_TOWNS if st.session_state.get(f"chk_t_{a}_{t}", False)]
                presets[new_name.strip()] = {"town_keys": cur_keys}
                save_presets(presets)
                st.success(f"『{new_name}』を保存しました！")
                time.sleep(1)
                st.rerun()

st.sidebar.markdown("---")

# 1. 駅徒歩
st.sidebar.subheader("🚶 駅徒歩分数")
walk_steps = [1, 3, 5, 7, 10, 15, 20]
walk_options = []
total_cnt = len(df) if not df.empty else 0
for step in walk_steps:
    cnt = len(df[df["駅徒歩(分)"] <= step]) if not df.empty and "駅徒歩(分)" in df.columns else 0
    walk_options.append(f"{step}分以内 ({cnt})")
walk_options.append(f"指定なし ({total_cnt})")

sel_walk_label = st.sidebar.selectbox("駅徒歩上限", options=walk_options, index=len(walk_options) - 1)
include_bus = st.sidebar.checkbox("バス利用物件を含む", value=True)

# 2. 建築条件
st.sidebar.subheader("🏠 建築条件")
cond_なし_cnt = len(df[df["建築条件"].astype(str).str.contains("なし")]) if not df.empty and "建築条件" in df.columns else 0
cond_あり_cnt = len(df[df["建築条件"].astype(str).str.contains("あり")]) if not df.empty and "建築条件" in df.columns else 0
cond_map = {f"なし ({cond_なし_cnt})": "なし", f"あり ({cond_あり_cnt})": "あり", f"指定なし ({total_cnt})": "指定なし"}
sel_cond_label = st.sidebar.radio("建築条件", options=list(cond_map.keys()), index=0)
selected_condition = cond_map[sel_cond_label]

# 3. 状況
st.sidebar.subheader("🏡 状況（現況）")
stat_更地_cnt = len(df[df["現況"].astype(str).str.contains("更地")]) if not df.empty and "現況" in df.columns else 0
stat_古家_cnt = len(df[df["現況"].astype(str).str.contains("古家|上物")]) if not df.empty and "現況" in df.columns else 0
stat_map = {f"更地 ({stat_更地_cnt})": "更地", f"古家あり ({stat_古家_cnt})": "古家あり", f"指定なし ({total_cnt})": "指定なし"}
sel_stat_label = st.sidebar.radio("現況", options=list(stat_map.keys()), index=2)
selected_status = stat_map[sel_stat_label]

# 4. 規模
st.sidebar.subheader("🏘️ 規模（区画数）")
scale_30_cnt = len(df[df["総区画数"] >= 30]) if not df.empty and "総区画数" in df.columns else 0
scale_50_cnt = len(df[df["総区画数"] >= 50]) if not df.empty and "総区画数" in df.columns else 0
scale_100_cnt = len(df[df["総区画数"] >= 100]) if not df.empty and "総区画数" in df.columns else 0
scale_map = {f"30区画以上 ({scale_30_cnt})": 30, f"50区画以上 ({scale_50_cnt})": 50, f"100区画以上 ({scale_100_cnt})": 100, f"指定なし ({total_cnt})": 0}
sel_scale_label = st.sidebar.radio("区画規模", options=list(scale_map.keys()), index=3)
selected_min_scale = scale_map[sel_scale_label]

st.sidebar.markdown("---")
st.sidebar.subheader("📐 土地面積（坪）")
tsubo_range = st.sidebar.slider("坪数範囲", min_value=0.0, max_value=150.0, value=(0.0, 150.0), step=2.0)

st.sidebar.subheader("💰 価格帯（万円）")
price_range = st.sidebar.slider("価格範囲（万円）", min_value=0, max_value=5000, value=(0, 5000), step=100)

# ==========================================================================
# メイン画面：エリア選択（超高速描画）
# ==========================================================================
st.markdown("### 📍 エリア選択")

b1, b2, b3 = st.columns([1.5, 1.5, 3])
if b1.button("全エリア 全選択"):
    for a, t in ALL_AREA_TOWNS:
        st.session_state[f"chk_t_{a}_{t}"] = True
    st.rerun()
if b2.button("全エリア 全解除"):
    for a, t in ALL_AREA_TOWNS:
        st.session_state[f"chk_t_{a}_{t}"] = False
    st.rerun()
if b3.button("⭐ 町上津役周辺のみ"):
    for a, t in ALL_AREA_TOWNS:
        st.session_state[f"chk_t_{a}_{t}"] = False
    for t in ["町上津役西", "町上津役東", "春日台", "沖田", "塔野", "大平", "下上津役", "上上津役"]:
        st.session_state[f"chk_t_北九州市八幡西区_{t}"] = True
    st.rerun()

# どの自治体を表示するか選ぶタブ
selected_city = st.selectbox(
    "街を選んで町名をチェック（開いた街だけを描画するので爆速で動きます）",
    options=list(MASTER_AREAS.keys()),
    index=list(MASTER_AREAS.keys()).index("遠賀郡水巻町") if "遠賀郡水巻町" in MASTER_AREAS else 0
)

# 選択された街の町名チェックボックスを展開
groups = MASTER_AREAS[selected_city]
city_towns = [t for g in groups.values() for t in g]
city_cnt = area_counts.get(selected_city, 0)
checked_cnt = sum(1 for t in city_towns if st.session_state.get(f"chk_t_{selected_city}_{t}", False))

st.markdown(f"#### 📍 {selected_city} （データ: {city_cnt}件 / 選択中: {checked_cnt}町）")
btn_c1, btn_c2, _ = st.columns([1.5, 1.5, 5])
if btn_c1.button(f"{selected_city}を全選択", key=f"btn_all_{selected_city}"):
    for t in city_towns:
        st.session_state[f"chk_t_{selected_city}_{t}"] = True
    st.rerun()
if btn_c2.button(f"{selected_city}を全解除", key=f"btn_clr_{selected_city}"):
    for t in city_towns:
        st.session_state[f"chk_t_{selected_city}_{t}"] = False
    st.rerun()

valid_groups = {k: v for k, v in groups.items() if v}
if valid_groups:
    tabs = st.tabs(list(valid_groups.keys()))
    for tab_idx, (group_name, towns) in enumerate(valid_groups.items()):
        with tabs[tab_idx]:
            g1, g2, g3 = st.columns(3)
            cols = [g1, g2, g3]
            for idx, town in enumerate(towns):
                cnt = town_counts.get(town, 0)
                cols[idx % 3].checkbox(f"{town} ({cnt})", key=f"chk_t_{selected_city}_{town}")

# --------------------------------------------------------------------------
# フィルタリング判定
# --------------------------------------------------------------------------
current_active_keys = [f"{a}_{t}" for a, t in ALL_AREA_TOWNS if st.session_state.get(f"chk_t_{a}_{t}", False)]

if df.empty:
    st.info("💡 スプレッドシートにデータがありません。条件を選んで保存したら、ターミナルで `py scraper.py` を実行してください。")
    st.stop()

def filter_row(row):
    area = row.get("市区", "")
    town = row.get("町名", "")
    key = f"chk_t_{area}_{town}"
    # 町名が1つも選択されていない場合は全件表示、選択されている場合はその町のみ
    if not current_active_keys:
        return True
    return st.session_state.get(key, False)

filtered = df[df.apply(filter_row, axis=1)].copy()

filtered = filtered[
    filtered["土地面積(坪)"].isna() | filtered["土地面積(坪)"].between(tsubo_range[0], tsubo_range[1])
]

filtered = filtered[
    filtered["価格(万円)"].isna() | filtered["価格(万円)"].between(price_range[0], price_range[1])
]

if "指定なし" not in sel_walk_label:
    m_w = re.search(r"(\d+)分以内", sel_walk_label)
    if m_w:
        max_w = int(m_w.group(1))
        filtered = filtered[filtered["駅徒歩(分)"].notna() & (filtered["駅徒歩(分)"] <= max_w)]

if not include_bus and "バス利用" in filtered.columns:
    filtered = filtered[filtered["バス利用"] != "あり"]

if selected_condition == "なし":
    filtered = filtered[filtered["建築条件"].astype(str).str.contains("なし", na=False)]
elif selected_condition == "あり":
    filtered = filtered[filtered["建築条件"].astype(str).str.contains("あり", na=False)]

if selected_status == "更地":
    filtered = filtered[filtered["現況"].astype(str).str.contains("更地", na=False)]
elif selected_status == "古家あり":
    filtered = filtered[filtered["現況"].astype(str).str.contains("古家|上物", na=False)]

if selected_min_scale > 0 and "総区画数" in filtered.columns:
    filtered = filtered[filtered["総区画数"] >= selected_min_scale]

# --------------------------------------------------------------------------
# 結果表示
# --------------------------------------------------------------------------
selected_total = len(current_active_keys)

st.markdown("---")
col1, col2, col3, col4 = st.columns(4)
col1.metric("該当物件数", f"{len(filtered)} 件")
if filtered["価格(万円)"].notna().any():
    col2.metric("平均価格", f"{filtered['価格(万円)'].mean():.0f} 万円")
if filtered["坪単価(万円/坪)"].notna().any():
    col3.metric("平均坪単価", f"{filtered['坪単価(万円/坪)'].mean():.1f} 万円/坪")
col4.metric("選択中の町名数", f"{selected_total} 町")

st.markdown("---")

display_cols = ["所在地", "価格(万円)", "土地面積(坪)", "坪単価(万円/坪)", "駅徒歩(分)", "現況", "建築条件", "総区画数", "接道状況", "注意タグ", "詳細URL"]
show_cols = [c for c in display_cols if c in filtered.columns]

if filtered.empty:
    st.info("条件に一致する物件がありません。エリアを選択するか条件を広げてください。")
else:
    st.dataframe(
        filtered[show_cols],
        hide_index=True,
        column_config={
            "詳細URL": st.column_config.LinkColumn("元サイト", display_text="🔗 詳細を開く"),
            "駅徒歩(分)": st.column_config.NumberColumn("駅徒歩", format="徒歩 %d 分"),
            "価格(万円)": st.column_config.NumberColumn("価格", format="%d 万円"),
            "坪単価(万円/坪)": st.column_config.NumberColumn("坪単価", format="%.1f 万/坪"),
            "土地面積(坪)": st.column_config.NumberColumn("面積", format="%.1f 坪"),
            "総区画数": st.column_config.NumberColumn("区画規模", format="%d 区画"),
        }
    )
