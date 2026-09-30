import os
import time
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

# ============ 【配置区】 ============
# 高德开放平台 Web 服务 Key。两种来源都可以，同时配置时环境变量优先：
# 1. 环境变量 AMAP_API_KEY
# 2. 项目根目录 .env 中写一行：AMAP_API_KEY=你的key
ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env", override=False)
API_KEY = os.getenv("AMAP_API_KEY", "").strip()

# data文件夹，csv全部放在这个文件夹
DATA_FOLDER = Path("./data")

# 输出目录与坐标结果文件（字段需与下游任务对齐，勿改列名）
OUTPUT_DIR = Path("./output")
OUTPUT_CSV = OUTPUT_DIR / "绍兴全部停车场坐标.csv"
FAIL_CSV = OUTPUT_DIR / "停车场地理编码失败清单_坐标采集.csv"
OUTPUT_COLS = [
    "park_TCCBH",
    "park_TCCMC",
    "park_TCCDZ",
    "park_lon_gcj02",
    "park_lat_gcj02",
]

# 限定查询城市：绍兴，防止匹配到外省同名地点
CITY = "绍兴"

# 每次http请求延时，高德免费QPS限制，不要低于0.3秒
DELAY = 0.5

# 调试模式：设置数字5只跑前5个停车场；None=全部跑
MAX_PARKING = None

# 数据表内的列名
NAME_COL = "TCCMC"    # 停车场名称
ADDR_COL = "TCCDZ"    # 停车场地址
ID_COL = "TCCBH"      # 停车场编号

# 高德 POI 类型：停车场（含地下/地面等子类）
PARKING_TYPES = "150900"

# 5张停车场基础信息表
base_csv_list = [
    "上虞区智慧停车综合系统-上虞区停车场基础信息.csv",
    "诸暨市停车场基础信息.csv",
    "越城区停车诱导系统-停车场基础信息.csv",
    "新昌县停车场基础信息.csv",
    "浙里畅行-I出行-停车场基础信息.csv",
]
# =============================================


def _normalize(text: str) -> str:
    return str(text).strip().replace(" ", "").replace("　", "").lower()


def _parse_location(loc_str):
    if not loc_str or "," not in str(loc_str):
        return None
    lon, lat = str(loc_str).split(",", 1)
    return float(lon), float(lat)


def search_place(keywords: str, types: str = None, city: str = None):
    """
    高德关键字搜索：按名称匹配 POI（与坐标拾取器搜地点更接近）
    :return: pois 列表；失败返回空列表
    """
    url = "https://restapi.amap.com/v3/place/text"
    params = {
        "key": API_KEY,
        "keywords": keywords,
        "city": city or CITY,
        "citylimit": "true",
        "offset": 20,
        "page": 1,
        "extensions": "base",
        "output": "json",
    }
    if types:
        params["types"] = types

    try:
        resp = requests.get(url, params=params, timeout=10)
        res_json = resp.json()
    except Exception as e:
        print(f"\n[网络/解析异常] keywords:{keywords} 错误:{str(e)}")
        return []
    finally:
        time.sleep(DELAY)

    if res_json.get("status") != "1":
        print(f"\n[POI搜索失败] keywords:{keywords} types:{types} info:{res_json.get('info')}")
        return []

    pois = res_json.get("pois") or []
    if isinstance(pois, dict):
        pois = [pois]
    return pois


def pick_best_poi(pois, name: str, address: str = ""):
    """从候选 POI 中选与停车场名称/地址最匹配的一条。"""
    if not pois:
        return None

    name_n = _normalize(name)
    addr_n = _normalize(address) if address else ""
    scored = []

    for poi in pois:
        poi_name = str(poi.get("name") or "")
        poi_addr = str(poi.get("address") or "")
        typecode = str(poi.get("typecode") or "")
        pn = _normalize(poi_name)
        pa = _normalize(poi_addr)
        score = 0

        if name_n and pn == name_n:
            score += 100
        elif name_n and name_n in pn:
            score += 60
        elif name_n and pn in name_n:
            score += 40

        if typecode.startswith("1509"):
            score += 30

        if addr_n and addr_n in pa:
            score += 20
        elif addr_n and len(addr_n) >= 4 and any(
            addr_n[i:i + 4] in pa for i in range(0, len(addr_n) - 3)
        ):
            score += 10

        scored.append((score, poi))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_poi = scored[0]
    # 名称完全对不上时，宁可失败也不硬取第一条无关 POI
    if best_score < 40 and name_n and name_n not in _normalize(best_poi.get("name") or ""):
        return None
    return best_poi


def geocode(address: str, name: str, city: str = None):
    """
    地理编码兜底：POI 搜不到时再用地址解析
    :return: (经度,纬度) 成功；返回None 失败
    """
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {
        "key": API_KEY,
        "output": "json",
        "city": city,
    }
    if pd.notna(address) and str(address).strip() != "":
        query_text = f"{name} {address}" if _normalize(name) != _normalize(address) else name
    else:
        query_text = name
    params["address"] = query_text

    try:
        resp = requests.get(url, params=params, timeout=10)
        res_json = resp.json()
    except Exception as e:
        print(f"\n[网络/解析异常] 查询文本:{query_text} 错误:{str(e)}")
        return None
    finally:
        time.sleep(DELAY)

    if res_json.get("status") == "1" and res_json.get("geocodes"):
        return _parse_location(res_json["geocodes"][0].get("location"))

    print(f"\n[地理编码失败] query:{query_text}  info:{res_json.get('info')}")
    return None


def resolve_parking_coord(name: str, address: str = "", city: str = None):
    """
    优先 POI 关键字搜索匹配停车场；搜不到再地理编码兜底。
    :return: (lon, lat, source)  source=poi|geocode；失败 (None, None, None)
    """
    city = city or CITY
    attempts = [
        (name, PARKING_TYPES),
        (name, None),
    ]
    if address and _normalize(address) != _normalize(name):
        attempts.append((address, PARKING_TYPES))
        attempts.append((f"{name}{address}", PARKING_TYPES))

    for keywords, types in attempts:
        if not keywords or not str(keywords).strip():
            continue
        pois = search_place(keywords=keywords, types=types, city=city)
        best = pick_best_poi(pois, name=name, address=address)
        if best:
            coord = _parse_location(best.get("location"))
            if coord:
                print(
                    f"\n[POI匹配] keywords:{keywords} "
                    f"命中:{best.get('name')} type:{best.get('type')} "
                    f"addr:{best.get('address')}"
                )
                return coord[0], coord[1], "poi"

    print(f"\n[POI未命中] name:{name} addr:{address}，尝试地理编码兜底")
    coord = geocode(address=address, name=name, city=city)
    if coord:
        return coord[0], coord[1], "geocode"
    return None, None, None


def main():
    if not API_KEY:
        print("\n未找到 AMAP_API_KEY，任选一种方式配置后重新运行：")
        print("1. 设置环境变量 AMAP_API_KEY")
        print("2. 在项目根目录 .env 中写入：AMAP_API_KEY=你的key")
        print("两种都配置时，使用环境变量里的值。")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_park_df_list = []
    for csv_name in base_csv_list:
        csv_path = DATA_FOLDER / csv_name
        if not csv_path.exists():
            print(f"\n文件不存在跳过：{csv_name}")
            continue
        df_temp = pd.read_csv(csv_path, encoding="utf-8-sig")
        all_park_df_list.append(df_temp)
        print(f"\n读取文件 {csv_name} 行数：{len(df_temp)}")

    if not all_park_df_list:
        print("\n未读到任何停车场基础表，结束。")
        return

    df_all_park = pd.concat(all_park_df_list, ignore_index=True)
    print(f"\n合并后总停车场数量：{len(df_all_park)}")

    must_cols = [NAME_COL, ADDR_COL, ID_COL]
    for col in must_cols:
        if col not in df_all_park.columns:
            print(f"\n缺失字段：{col}，现有列名 {list(df_all_park.columns)}")
            return

    if MAX_PARKING is not None and isinstance(MAX_PARKING, int):
        df_all_park = df_all_park.head(MAX_PARKING)
        print(f"\n调试模式，仅处理前 {MAX_PARKING} 个停车场")

    coord_rows = []
    fail_park_list = []
    total_count = len(df_all_park)
    poi_ok = 0
    geocode_ok = 0

    for idx, row in df_all_park.iterrows():
        park_id = str(row[ID_COL]).strip()
        park_name = str(row[NAME_COL]).strip()
        park_addr = str(row[ADDR_COL]) if pd.notna(row[ADDR_COL]) else ""
        park_addr = park_addr.strip()

        print(f"\n==== [{idx + 1}/{total_count}] 停车场编号:{park_id} 名称:{park_name} ====")

        park_lon, park_lat, source = resolve_parking_coord(
            name=park_name, address=park_addr, city=CITY
        )

        if park_lon is None:
            print("\n无法匹配坐标，跳过该停车场")
            fail_park_list.append({
                "停车场编号": park_id,
                "停车场名称": park_name,
                "停车场地址": park_addr,
            })
            continue

        if source == "poi":
            poi_ok += 1
        else:
            geocode_ok += 1

        print(f"\n获取坐标成功({source}) GCJ-02 lon={park_lon}, lat={park_lat}")

        # 输出字段与下游一致，不增加额外列
        coord_rows.append({
            "park_TCCBH": park_id,
            "park_TCCMC": park_name,
            "park_TCCDZ": park_addr,
            "park_lon_gcj02": park_lon,
            "park_lat_gcj02": park_lat,
        })

    df_coord = pd.DataFrame(coord_rows, columns=OUTPUT_COLS)
    df_coord.to_csv(OUTPUT_CSV, encoding="utf-8-sig", index=False)
    print(f"\n坐标采集完成！成功停车场数：{len(df_coord)}（POI:{poi_ok} 地理编码兜底:{geocode_ok}）")
    print(f"\ncsv输出文件：{OUTPUT_CSV}")

    if len(fail_park_list) > 0:
        df_fail = pd.DataFrame(fail_park_list)
        df_fail.to_csv(FAIL_CSV, encoding="utf-8-sig", index=False)
        print(f"\n{len(fail_park_list)}个停车场坐标采集失败，清单输出:{FAIL_CSV}")


if __name__ == "__main__":
    main()
