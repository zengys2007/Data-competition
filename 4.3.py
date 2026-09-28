# ===================== 导入库 =====================
import pandas as pd
import folium
from folium.plugins import HeatMap
import math
from pathlib import Path

# =====================【配置区，务必核对修改】 =====================
OUTPUT_DIR = Path("./output")
# ---------- 输入文件 ----------
# 任务1.2采集的兴趣点POI表
POI_FILE = OUTPUT_DIR / "绍兴全部停车场周边POI信息表.csv"
# 任务3.4输出的停车场-兴趣点关联表
REL_FILE = OUTPUT_DIR / "POI_ParkingLot_Association_Table.csv"
# 任务2.3停车场基础表（任务3.1已完成GCJ‑02 → WGS84）
PARK_BASE = OUTPUT_DIR / "valid_park_base_wgs84.csv"
# 任务3.3停车场每小时车位利用率结果
UTIL_33 = OUTPUT_DIR / "Hourly_Parking_Utilization_Results.csv"
# 输出热力地图
OUT_HTML = OUTPUT_DIR / "POI泊车供需热力图.html"
CSV_ENCODING = "utf-8-sig"

# ---------- 字段名称配置（根据你csv实际列名修改）----------
# POI表字段（任务1.2输出）
POI_NAME_COL = "poi_name"    # POI名称列名
POI_LON_COL = "poi_lon_gcj02"# POI原始GCJ02经度
POI_LAT_COL = "poi_lat_gcj02"# POI原始GCJ02纬度

# 关联表字段（任务3.4输出）
REL_PARK_COL = "park_TCCBH"    # 关联表：停车场id
REL_POI_COL = "poi_id"      # 关联表：poi_id（和本代码生成规则一致）

# 停车场基础表字段
PARK_ID_COL = "TCCBH"
PARK_NAME_COL = "TCCMC"
WGS84_LON_COL = "lon_wgs84_cgcs2000"
WGS84_LAT_COL = "lat_wgs84_cgcs2000"
PARK_CAPACITY_COL = "BWZS"

# ---------- 热力图样式参数 ----------
HEAT_RADIUS = 22
HEAT_BLUR = 15
MAP_ZOOM_START = 12

# 颜色梯度：蓝(利用率低，车位充足)→绿→黄→橙→红(利用率高，车位紧张)
HEAT_GRADIENT = {
    0.0: "#0044ff",
    0.3: "#00cc44",
    0.5: "#ffdd00",
    0.7: "#ff7700",
    1.0: "#dd0000"
}

# ===================== GCJ‑02 转 WGS84 坐标转换函数 =====================
def gcj02_to_wgs84(gcj_lon, gcj_lat):
    """
    将高德GCJ02火星坐标转换为WGS84坐标，用于folium地图可视化
    注意：poi_id的生成不使用此转换后的坐标，poi_id永远基于原始GCJ02
    :param gcj_lon: GCJ02经度
    :param gcj_lat: GCJ02纬度
    :return: wgs84经度, wgs84纬度
    """
    PI = 3.14159265358979324
    a = 6378245.0
    ee = 0.00669342162296594323

    def transform_lat(x, y):
        ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
        ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
        ret += (160.0 * math.sin(y / 12.0 * PI) + 320 * math.sin(y / 30.0 * PI)) * 2.0 / 3.0
        return ret

    def transform_lon(x, y):
        ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
        ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
        ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
        return ret

    d_lat = transform_lat(gcj_lon - 105.0, gcj_lat - 35.0)
    d_lon = transform_lon(gcj_lon - 105.0, gcj_lat - 35.0)
    rad_lat = gcj_lat / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - ee * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((a * (1 - ee)) / (magic * sqrt_magic) * PI)
    d_lon = (d_lon * 180.0) / (a / sqrt_magic * math.cos(rad_lat) * PI)
    wgs_lat = gcj_lat - d_lat
    wgs_lon = gcj_lon - d_lon
    return wgs_lon, wgs_lat

def main():
    print("==================== 任务4.3 POI泊车供需热力图（poi_id与任务3.4规则统一）开始 ====================")

    # ---------- 1. 读取任务1.2兴趣点POI原始数据 ----------
    print("\n1.读取任务1.2兴趣点POI原始数据")
    df_poi = pd.read_csv(POI_FILE, encoding=CSV_ENCODING)
    print(f"\nPOI原始总记录数：{df_poi.shape[0]}")
    print(f"\nPOI原始表全部字段：{df_poi.columns.tolist()}")

    # 清洗POI：删除经纬度为空的行，转为数值类型
    df_poi = df_poi.dropna(subset=[POI_LON_COL, POI_LAT_COL]).copy()
    df_poi[POI_LON_COL] = pd.to_numeric(df_poi[POI_LON_COL], errors="coerce")
    df_poi[POI_LAT_COL] = pd.to_numeric(df_poi[POI_LAT_COL], errors="coerce")
    df_poi = df_poi.dropna(subset=[POI_LON_COL, POI_LAT_COL])
    print(f"清洗空值后POI数量：{df_poi.shape[0]}")

    # =====================【生成poi_id，与任务3.4代码逻辑完全一致】=====================
    # 规则：poi名称_保留6位小数GCJ02经度_保留6位小数GCJ02纬度
    # round(6)：消除浮点数微小精度误差，相近坐标判定为同一个POI
    print("\n2. 生成poi_id，规则：poi名称_6位小数GCJ02经度_6位小数GCJ02纬度")
    df_poi["poi_id"] = (
        df_poi[POI_NAME_COL].astype(str)
        + "_"
        + df_poi[POI_LON_COL].astype(float).round(6).astype(str)
        + "_"
        + df_poi[POI_LAT_COL].astype(float).round(6).astype(str)
    )
    # 按poi_id去重，保留第一条记录（和任务3.4去重逻辑保持一致）
    df_poi = df_poi.drop_duplicates(subset=["poi_id"], keep="first")
    print(f"\n生成poi_id并去重后，唯一POI实体数量：{df_poi.shape[0]}")
    # =================================================================================

    # =====================【批量GCJ-02转WGS84，仅用于地图可视化】=====================
    print("\n3. GCJ02火星坐标批量转换为WGS84坐标（仅地图绘图使用）")
    # 对每一行POI执行坐标转换
    transform_result = df_poi.apply(lambda row: gcj02_to_wgs84(row[POI_LON_COL], row[POI_LAT_COL]), axis=1)
    df_poi["wgs84_lon"] = [item[0] for item in transform_result]
    df_poi["wgs84_lat"] = [item[1] for item in transform_result]
    print("\n坐标转换完成，新增字段 wgs84_lon、wgs84_lat")
    # ===============================================================================

    # ---------- 4. 读取任务3.4停车场-POI关联表 ----------
    print("\n4.读取任务3.4停车场-POI关联表")
    df_rel = pd.read_csv(REL_FILE, encoding=CSV_ENCODING)
    print(f"关联表记录数量：{df_rel.shape[0]}")
    print(f"关联表字段列表：{df_rel.columns.tolist()}")

    # ---------- 5. 读取停车场基础信息 + 车位利用率数据 ----------
    print("\n5.读取停车场基础信息与利用率数据")
    df_park = pd.read_csv(PARK_BASE, encoding=CSV_ENCODING)
    df_park = df_park.dropna(subset=[PARK_ID_COL])
    df_park = df_park[df_park[PARK_CAPACITY_COL] > 0].copy()
    df_park[PARK_CAPACITY_COL] = pd.to_numeric(df_park[PARK_CAPACITY_COL], errors="coerce")
    print(f"有效停车场数量：{df_park.shape[0]}")

    # 读取利用率，求停车场平均利用率
    df_hour_util = pd.read_csv(UTIL_33, encoding=CSV_ENCODING)
    df_park_util = df_hour_util.groupby("停车场ID").agg(
        avg_usage_rate=("每小时平均车位利用率", "mean")
    ).reset_index()
    df_park_util.rename(columns={"停车场ID": PARK_ID_COL}, inplace=True)

    # 停车场基础信息 和 利用率合并
    df_park_full = pd.merge(df_park, df_park_util, on=PARK_ID_COL, how="inner")
    print(f"带有利用率数据的停车场数量：{df_park_full.shape[0]}")

    # ---------- 6. 关联表 + 停车场利用率，聚合得到每个POI的供需权重 ----------
    print("\n6. 将停车场利用率关联到POI，计算每个POI周边停车场平均利用率")
    # 关联表和停车场利用率合并，拿到每个关联关系的利用率
    df_rel_util = pd.merge(
        df_rel[[REL_PARK_COL, REL_POI_COL]],
        df_park_full[[PARK_ID_COL, "avg_usage_rate"]],
        left_on=REL_PARK_COL,
        right_on=PARK_ID_COL,
        how="inner"
    )
    # 按poi_id分组聚合：平均利用率作为热力权重，统计关联停车场数量
    df_poi_weight = df_rel_util.groupby(REL_POI_COL).agg(
        weight=("avg_usage_rate", "mean"),
        park_count=("avg_usage_rate", "count")
    ).reset_index()
    print(f"\n匹配到停车场的POI数量：{df_poi_weight.shape[0]}")

    # ---------- 7. POI基础信息 和 POI权重合并 ----------
    print("\n7. 合并POI坐标信息与供需权重")
    df_final = pd.merge(
        df_poi,
        df_poi_weight,
        left_on="poi_id",
        right_on=REL_POI_COL,
        how="inner"
    )
    print(f"最终可绘制热力图的POI点位数量：{df_final.shape[0]}")
    if df_final.shape[0] == 0:
        print("\n警告：没有匹配到任何数据！请检查poi_id生成规则、关联表字段是否一致！")
        return
    print(f"\n供需权重范围：{df_final['weight'].min():.3f} ~ {df_final['weight'].max():.3f}")

    # ---------- 8. 构造热力图数据，创建folium地图 ----------
    print("\n8. 生成热力地图")
    # HeatMap要求格式：[纬度,经度,权重]
    heat_data = [[r["wgs84_lat"], r["wgs84_lon"], r["weight"]] for _, r in df_final.iterrows()]
    # 地图中心点：所有POI坐标均值
    center_lat = df_final["wgs84_lat"].mean()
    center_lon = df_final["wgs84_lon"].mean()

    # ========== 替换为高德电子底图（中文，带区县/街道地名） ==========
    gaode_tile_url = "https://wprd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&style=7&x={x}&y={y}&z={z}"
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=MAP_ZOOM_START,
        tiles=gaode_tile_url,
        attr="© 高德地图"
    )

    # 添加热力图层
    HeatMap(
        heat_data,
        radius=HEAT_RADIUS,
        blur=HEAT_BLUR,
        gradient=HEAT_GRADIENT,
        min_opacity=0.2,
        max_zoom=16,
        name="POI泊车供需热力图层"
    ).add_to(m)

    # 为每个POI添加点击弹窗
    print("添加POI点位弹窗标记")
    for _, row in df_final.iterrows():
        popup_html = (
            f"<b>POI名称：</b>{row[POI_NAME_COL]}<br>"
            f"<b>poi_id：</b>{row['poi_id']}<br>"
            f"<b>周边关联停车场数量：</b>{int(row['park_count'])}<br>"
            f"<b>平均车位利用率(供需权重)：</b>{round(row['weight'],3)}"
        )
        folium.CircleMarker(
            location=[row["wgs84_lat"], row["wgs84_lon"]],
            radius=3,
            popup=folium.Popup(popup_html, max_width=400),
            color="#222222",
            fill=True,
            fill_color="#444444",
            fill_opacity=0.7
        ).add_to(m)

    # 添加图层切换控件
    folium.LayerControl().add_to(m)

    # 保存html文件
    m.save(str(OUT_HTML))
    print(f"\n任务4.3执行完成！热力图已保存至：{OUT_HTML}")
    print("\n提示：使用浏览器打开html文件查看热力图。")

if __name__ == "__main__":
    main()