# =====================导入依赖库=====================
import pandas as pd
import math
from pathlib import Path

# =====================配置参数区=====================
OUTPUT_DIR = Path("./output")
# 输入文件
INPUT_VALID_PARK = OUTPUT_DIR / "valid_park_base.csv"          # 任务2.3输出：有效停车场基础表
INPUT_POI = OUTPUT_DIR / "绍兴全部停车场周边POI信息表.csv"       # 任务1.2输出POI表

# 输出文件：统一转换到WGS84（CGCS2000，竞赛民用等价）
OUT_PARK_WGS84 = OUTPUT_DIR / "valid_park_base_wgs84.csv"
OUT_POI_WGS84 = OUTPUT_DIR / "poi_info_wgs84.csv"

CSV_ENCODING = "utf-8-sig"

# ===================== 公开坐标系转换工具函数 =====================
# 常量定义，火星坐标转换参数
PI = 3.141592653589793
A = 6378245.0
EE = 0.00669342162296594323

def transform_lat(x: float, y: float) -> float:
    """GCJ‑02纬度转换中间计算函数"""
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret

def transform_lon(x: float, y: float) -> float:
    """GCJ‑02经度转换中间计算函数"""
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret

def gcj02_to_wgs84(gcj_lon: float, gcj_lat: float):
    """
    GCJ‑02(火星坐标) 转 WGS84 (CGCS2000民用等价)
    :param gcj_lon: GCJ02经度
    :param gcj_lat: GCJ02纬度
    :return: wgs_lon, wgs_lat；输入空值返回None,None
    """
    if pd.isna(gcj_lon) or pd.isna(gcj_lat):
        return None, None
    # 判断是否在中国境外，境外不做偏移直接返回原值
    if abs(gcj_lon) < 0.001 or abs(gcj_lat) < 0.001:
        return gcj_lon, gcj_lat

    dlat = transform_lat(gcj_lon - 105.0, gcj_lat - 35.0)
    dlon = transform_lon(gcj_lon - 105.0, gcj_lat - 35.0)
    radlat = gcj_lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * PI)
    dlon = (dlon * 180.0) / (A / sqrtmagic * math.cos(radlat) * PI)

    wgs_lat = gcj_lat - dlat
    wgs_lon = gcj_lon - dlon
    return wgs_lon, wgs_lat


# =====================主程序入口=====================
def main():
    print("====================任务3.1 坐标系统一转换 GCJ‑02 → WGS84(CGCS2000) 开始====================")

    # --------步骤1：读取输入文件 有效停车场基础表--------
    if not INPUT_VALID_PARK.exists():
        print(f"\n文件不存在 {INPUT_VALID_PARK}，请先运行任务2.3！")
        return
    df_park = pd.read_csv(INPUT_VALID_PARK, encoding=CSV_ENCODING)
    print(f"\n读取有效停车场表，记录数：{df_park.shape[0]}")

    # --------步骤2：停车场表：GCJ‑02转为WGS84(CGCS2000)--------
    """
    api_lon_gcj02 / api_lat_gcj02 ：高德采集原始GCJ‑02火星坐标
    新增两列输出WGS84，后续空间计算、地图可视化全部使用wgs84坐标
    """
    # apply逐行调用转换函数
    def park_convert(row):
        gcj_lon = row["api_lon_gcj02"]
        gcj_lat = row["api_lat_gcj02"]
        wgs_lon, wgs_lat = gcj02_to_wgs84(gcj_lon, gcj_lat)
        return pd.Series([wgs_lon, wgs_lat])

    # 新增两列：wgs84等价CGCS2000
    df_park[["lon_wgs84_cgcs2000", "lat_wgs84_cgcs2000"]] = df_park.apply(park_convert, axis=1)

    print("\n停车场坐标转换完成，新增字段 lon_wgs84_cgcs2000，lat_wgs84_cgcs2000")

    # --------步骤3：读取POI兴趣点表，转换POI的GCJ‑02坐标到WGS84--------
    if not INPUT_POI.exists():
        print(f"\n文件不存在 {INPUT_POI}，请先运行任务1.2！")
        return
    df_poi = pd.read_csv(INPUT_POI, encoding=CSV_ENCODING)
    print(f"\n读取POI兴趣点表，POI总记录数：{df_poi.shape[0]}")

    """
    POI表有两套GCJ02坐标：
    park_lon_gcj02 / park_lat_gcj02 ：停车场自身坐标
    poi_lon_gcj02 / poi_lat_gcj02   ：周边兴趣点POI坐标
    两套全部转换，新增对应WGS84字段
    """
    def poi_convert(row):
        # 停车场坐标转换
        p_gcj_lon = row["park_lon_gcj02"]
        p_gcj_lat = row["park_lat_gcj02"]
        p_wgs_lon, p_wgs_lat = gcj02_to_wgs84(p_gcj_lon, p_gcj_lat)
        # POI兴趣点坐标转换
        poi_gcj_lon = row["poi_lon_gcj02"]
        poi_gcj_lat = row["poi_lat_gcj02"]
        poi_wgs_lon, poi_wgs_lat = gcj02_to_wgs84(poi_gcj_lon, poi_gcj_lat)
        return pd.Series([p_wgs_lon, p_wgs_lat, poi_wgs_lon, poi_wgs_lat])

    df_poi[
        [
            "park_lon_wgs84_cgcs2000",
            "park_lat_wgs84_cgcs2000",
            "poi_lon_wgs84_cgcs2000",
            "poi_lat_wgs84_cgcs2000"
        ]
    ] = df_poi.apply(poi_convert, axis=1)

    print("\nPOI兴趣点坐标转换完成，新增4组WGS84(CGCS2000)坐标字段")

    # --------步骤4：输出csv文件--------
    df_park.to_csv(OUT_PARK_WGS84, encoding=CSV_ENCODING, index=False)
    df_poi.to_csv(OUT_POI_WGS84, encoding=CSV_ENCODING, index=False)

    print(f"\n停车场输出文件：{OUT_PARK_WGS84}")
    print(f"\nPOI兴趣点输出文件：{OUT_POI_WGS84}")

    print("\n====字段说明 ====")
    print("api_lon_gcj02 / api_lat_gcj02：原始高德GCJ‑02火星坐标（保留用于溯源）")
    print("lon_wgs84_cgcs2000 / lat_wgs84_cgcs2000：转换后WGS84，竞赛等价CGCS2000，后续全部任务3/4使用这套坐标！")
    print("park/poi_xxx_gcj02：POI表原始火星坐标；park/poi_xxx_wgs84_cgcs2000转换后坐标")



if __name__ == "__main__":
    main()