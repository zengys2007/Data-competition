
import os
import time
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

# ============ 【配置区，一定要修改】 ============
# 高德开放平台 Web 服务 Key。两种来源都可以，同时配置时环境变量优先：
# 1. 环境变量 AMAP_API_KEY
#    当前终端临时生效，关掉终端就失效。
#    PowerShell：
#        $env:AMAP_API_KEY = "你的key"
#    CMD：
#        set AMAP_API_KEY=你的key
#    写入当前 Windows 用户，之后新开的终端都会带上。设完需要重新打开终端。
#    PowerShell：
#        [System.Environment]::SetEnvironmentVariable("AMAP_API_KEY", "你的key", "User")
# 2. 项目根目录 .env 中写一行：AMAP_API_KEY=你的key
ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env", override=False)
API_KEY = os.getenv("AMAP_API_KEY", "").strip()

# data文件夹，csv全部放在这个文件夹，相对路径，不用写死D盘
DATA_FOLDER = Path("./data")

# 输出目录与POI结果文件
OUTPUT_DIR = Path("./output")
OUTPUT_EXCEL = OUTPUT_DIR / "绍兴全部停车场周边POI信息表.xlsx"
OUTPUT_CSV = OUTPUT_DIR / "绍兴全部停车场周边POI信息表.csv"  # 同时输出csv，后续任务读取更稳定

# 限定查询城市：绍兴，防止匹配到外省同名地点
CITY = "绍兴"

# 周边搜索半径，赛题要求1000米
SEARCH_RADIUS = 1000

# 每次http请求延时，高德免费QPS限制，不要低于0.3秒
DELAY = 0.5

# 调试模式：设置数字5只跑前5个停车场；None=全部跑
MAX_PARKING = None

# 数据表内的列名（看赛题csv字段）
NAME_COL = "TCCMC"    # 停车场名称
ADDR_COL = "TCCDZ"    # 停车场地址
ID_COL = "TCCBH"      # 停车场编号，后续任务2.2关联使用

# 高德POI typecode：需要采集的周边兴趣点类型：医院、学校、大型超市、住宅小区
POI_TYPES = {
    "医院": "090100",
    "学校": "141200|141300",
    "大型超市": "060400",
    "小区": "120300",
}

# 高德 POI 类型：停车场（含地下/地面等子类），用于定位停车场自身坐标
PARKING_TYPES = "150900"

# 5张停车场基础信息表（任务1.2需要全部处理）
base_csv_list = [
    "上虞区智慧停车综合系统-上虞区停车场基础信息.csv",
    "诸暨市停车场基础信息.csv",
    "越城区停车诱导系统-停车场基础信息.csv",
    "新昌县停车场基础信息.csv",
    "浙里畅行-I出行-停车场基础信息.csv"
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
    高德关键字搜索：按名称匹配停车场 POI
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


def nearby_pois(lon: float, lat: float, typecode: str, radius: int):
    """
    高德周边搜索API：给定坐标搜索指定类型POI
    :param lon: GCJ‑02经度
    :param lat: GCJ‑02纬度
    :param typecode: POI类型编码
    :param radius: 搜索半径（米）
    :return: list[dict] POI列表，无结果返回空列表
    """
    url = "https://restapi.amap.com/v3/place/around"
    params = {
        "key": API_KEY,
        "location": f"{lon},{lat}",   # 高德格式 经度,纬度
        "radius": radius,
        "types": typecode,
        "offset": 25,
        "page": 1,
        "extensions": "base",
        "output": "json",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        res_json = resp.json()
    except Exception as e:
        print(f"\n[周边搜索网络异常] {str(e)}")
        return []

    if res_json.get("status") == "1":
        return res_json.get("pois", [])
    else:
        print(f"\n[周边搜索失败] info:{res_json.get('info')}")
        return []

def main():
    if not API_KEY:
        print("\n未找到 AMAP_API_KEY，任选一种方式配置后重新运行：")
        print("1. 设置环境变量 AMAP_API_KEY")
        print("2. 在项目根目录 .env 中写入：AMAP_API_KEY=你的key")
        print("两种都配置时，使用环境变量里的值。")
        return

    all_park_df_list = []
    # 循环读取5张基础信息csv
    for csv_name in base_csv_list:
        csv_path = DATA_FOLDER / csv_name
        if not csv_path.exists():
            print(f"\n文件不存在跳过：{csv_name}")
            continue
        df_temp = pd.read_csv(csv_path, encoding="utf-8-sig")
        all_park_df_list.append(df_temp)
        print(f"\n读取文件 {csv_name} 行数：{len(df_temp)}")

    # 拼接5张表，ignore_index重置行索引
    df_all_park = pd.concat(all_park_df_list, ignore_index=True)
    print(f"\n合并后总停车场数量：{len(df_all_park)}")

    # 校验必须的字段是否存在
    must_cols = [NAME_COL, ADDR_COL, ID_COL]
    for col in must_cols:
        if col not in df_all_park.columns:
            print(f"\n缺失字段：{col}，现有列名 {list(df_all_park.columns)}")
            return

    # 调试模式，只取前N条测试
    if MAX_PARKING is not None and isinstance(MAX_PARKING, int):
        df_all_park = df_all_park.head(MAX_PARKING)
        print(f"\n调试模式，仅处理前 {MAX_PARKING} 个停车场")

    # 存储最终POI结果记录
    poi_result_rows = []
    # 存储地理编码失败的停车场，后续输出失败清单
    fail_park_list = []

    total_count = len(df_all_park)
    # 遍历每一行停车场数据
    for idx, row in df_all_park.iterrows():
        park_id = str(row[ID_COL]).strip()       # 停车场编号，后续关联外键
        park_name = str(row[NAME_COL]).strip()   # 停车场名称
        park_addr = str(row[ADDR_COL]) if pd.notna(row[ADDR_COL]) else ""
        park_addr = park_addr.strip()

        print(f"\n==== [{idx+1}/{total_count}] 停车场编号:{park_id} 名称:{park_name} ====")

        # 优先POI匹配停车场坐标，再地理编码兜底
        park_lon, park_lat, source = resolve_parking_coord(
            name=park_name, address=park_addr, city=CITY
        )

        if park_lon is None:
            print("\n无法匹配坐标，跳过该停车场")
            fail_park_list.append({
                "停车场编号": park_id,
                "停车场名称": park_name,
                "停车场地址": park_addr
            })
            continue
        print(f"\n获取坐标成功({source}) GCJ-02 lon={park_lon}, lat={park_lat}")

        # 循环每一类POI（医院/学校/超市/小区）
        for poi_label, typecode in POI_TYPES.items():
            poi_list = nearby_pois(park_lon, park_lat, typecode, SEARCH_RADIUS)
            time.sleep(DELAY)
            print(f"\n{poi_label} 找到 {len(poi_list)} 个")

            # 遍历返回的每一个兴趣点
            for one_poi in poi_list:
                loc_text = one_poi.get("location", "")
                if "," not in loc_text:
                    continue
                poi_lon_str, poi_lat_str = loc_text.split(",")
                # 组装单条记录，保留停车场编号，用于任务2.2融合
                row_record = {
                    "park_TCCBH": park_id,          # 停车场编号【关键外键！任务2.2用来关联】
                    "park_TCCMC": park_name,        # 停车场名称
                    "park_lon_gcj02": park_lon,     # 停车场GCJ‑02经度
                    "park_lat_gcj02": park_lat,     # 停车场GCJ‑02纬度
                    "poi_type_label": poi_label,    # POI中文类型
                    "poi_name": one_poi.get("name", ""),
                    "poi_lon_gcj02": float(poi_lon_str),
                    "poi_lat_gcj02": float(poi_lat_str),
                    "poi_distance_m": one_poi.get("distance", ""), #距离停车场多少米
                    "poi_address": one_poi.get("address", "")
                }
                poi_result_rows.append(row_record)

    # ----------------输出结果文件----------------
    df_poi_result = pd.DataFrame(poi_result_rows)
    # 输出csv（pandas读取csv兼容性最好，竞赛后续任务优先用csv）
    df_poi_result.to_csv(OUTPUT_CSV, encoding="utf-8-sig", index=False)
    print(f"\nPOI采集完成！总POI关联记录数：{len(df_poi_result)}")
    print(f"\ncsv输出文件：{OUTPUT_CSV}")

    # 输出excel，需要openpyxl库，捕获异常，没有库就跳过excel输出
    try:
        df_poi_result.to_excel(OUTPUT_EXCEL, index=False, engine="openpyxl")
        print(f"\nexcel输出文件：{OUTPUT_EXCEL}")
    except Exception:
        print(f"\n未安装openpyxl，跳过excel输出，可执行 pip install openpyxl")

    # 输出坐标匹配失败清单（文件名保持不变，供后续排查）
    if len(fail_park_list) > 0:
        df_fail = pd.DataFrame(fail_park_list)
        fail_file = OUTPUT_DIR / "停车场地理编码失败清单.csv"
        df_fail.to_csv(fail_file, encoding="utf-8-sig", index=False)
        print(f"\n{len(fail_park_list)}个停车场坐标匹配失败，清单输出:{fail_file}")

if __name__ == "__main__":
    main()