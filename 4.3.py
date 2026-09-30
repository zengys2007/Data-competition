# ===================== 导入库 =====================
import pandas as pd
import folium
from folium.plugins import HeatMap
from pathlib import Path

# =====================【配置区，务必核对修改】 =====================
OUTPUT_DIR = Path("./output")
# ---------- 输入文件 ----------
# 任务1.2采集的兴趣点POI表
POI_FILE = OUTPUT_DIR / "绍兴全部停车场周边POI信息表.csv"
# 任务3.4输出的停车场-兴趣点关联表
REL_FILE = OUTPUT_DIR / "POI_ParkingLot_Association_Table.csv"
# 任务2.3/3.1停车场基础表
PARK_BASE = OUTPUT_DIR / "valid_park_base_wgs84.csv"
# 任务3.3停车场每小时车位利用率结果
UTIL_33 = OUTPUT_DIR / "Hourly_Parking_Utilization_Results.csv"
# 输出热力地图
OUT_HTML = OUTPUT_DIR / "POI泊车供需热力图.html"
CSV_ENCODING = "utf-8-sig"

# ---------- 字段名称配置（根据你csv实际列名修改）----------
# POI表字段（任务1.2输出）：直接用 GCJ-02，配合高德底图（与4.1一致）
POI_NAME_COL = "poi_name"
POI_LON_COL = "poi_lon_gcj02"
POI_LAT_COL = "poi_lat_gcj02"

# 关联表字段（任务3.4输出）
REL_PARK_COL = "park_TCCBH"
REL_POI_COL = "poi_id"

# 停车场基础表字段
PARK_ID_COL = "TCCBH"
PARK_CAPACITY_COL = "BWZS"

# 高德矢量路网瓦片（国内可访问，坐标系为 GCJ-02）——与4.1一致
GAODE_TILES = (
    "https://webrd02.is.autonavi.com/appmaptile?"
    "lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}"
)
GAODE_ATTR = "高德地图"

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
    print("\n2. 生成poi_id，规则：poi名称_6位小数GCJ02经度_6位小数GCJ02纬度")
    df_poi["poi_id"] = (
        df_poi[POI_NAME_COL].astype(str)
        + "_"
        + df_poi[POI_LON_COL].astype(float).round(6).astype(str)
        + "_"
        + df_poi[POI_LAT_COL].astype(float).round(6).astype(str)
    )
    df_poi = df_poi.drop_duplicates(subset=["poi_id"], keep="first")
    print(f"\n生成poi_id并去重后，唯一POI实体数量：{df_poi.shape[0]}")

    # ---------- 3. 读取任务3.4停车场-POI关联表 ----------
    print("\n3.读取任务3.4停车场-POI关联表")
    df_rel = pd.read_csv(REL_FILE, encoding=CSV_ENCODING)
    print(f"关联表记录数量：{df_rel.shape[0]}")
    print(f"关联表字段列表：{df_rel.columns.tolist()}")

    # ---------- 4. 读取停车场基础信息 + 车位利用率数据 ----------
    print("\n4.读取停车场基础信息与利用率数据")
    df_park = pd.read_csv(PARK_BASE, encoding=CSV_ENCODING)
    df_park = df_park.dropna(subset=[PARK_ID_COL])
    df_park = df_park[df_park[PARK_CAPACITY_COL] > 0].copy()
    df_park[PARK_CAPACITY_COL] = pd.to_numeric(df_park[PARK_CAPACITY_COL], errors="coerce")
    print(f"有效停车场数量：{df_park.shape[0]}")

    df_hour_util = pd.read_csv(UTIL_33, encoding=CSV_ENCODING)
    df_park_util = df_hour_util.groupby("停车场ID").agg(
        avg_usage_rate=("每小时平均车位利用率", "mean")
    ).reset_index()
    df_park_util.rename(columns={"停车场ID": PARK_ID_COL}, inplace=True)

    df_park_full = pd.merge(df_park, df_park_util, on=PARK_ID_COL, how="inner")
    print(f"带有利用率数据的停车场数量：{df_park_full.shape[0]}")

    # ---------- 5. 关联表 + 停车场利用率，聚合得到每个POI的供需权重 ----------
    print("\n5. 将停车场利用率关联到POI，计算每个POI周边停车场平均利用率")
    df_rel_util = pd.merge(
        df_rel[[REL_PARK_COL, REL_POI_COL]],
        df_park_full[[PARK_ID_COL, "avg_usage_rate"]],
        left_on=REL_PARK_COL,
        right_on=PARK_ID_COL,
        how="inner"
    )
    df_poi_weight = df_rel_util.groupby(REL_POI_COL).agg(
        weight=("avg_usage_rate", "mean"),
        park_count=("avg_usage_rate", "count")
    ).reset_index()
    print(f"\n匹配到停车场的POI数量：{df_poi_weight.shape[0]}")

    # ---------- 6. POI基础信息 和 POI权重合并 ----------
    print("\n6. 合并POI坐标信息与供需权重")
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

    # ---------- 7. 构造热力图数据，创建folium地图（GCJ-02 + 高德底图，与4.1一致） ----------
    print("\n7. 生成热力地图（使用原始GCJ-02坐标，匹配高德底图）")
    heat_data = [
        [r[POI_LAT_COL], r[POI_LON_COL], r["weight"]]
        for _, r in df_final.iterrows()
    ]
    center_lat = df_final[POI_LAT_COL].mean()
    center_lon = df_final[POI_LON_COL].mean()

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=MAP_ZOOM_START,
        tiles=GAODE_TILES,
        attr=GAODE_ATTR,
    )

    HeatMap(
        heat_data,
        radius=HEAT_RADIUS,
        blur=HEAT_BLUR,
        gradient=HEAT_GRADIENT,
        min_opacity=0.2,
        max_zoom=16,
        name="POI泊车供需热力图层"
    ).add_to(m)

    print("添加POI点位弹窗标记")
    for _, row in df_final.iterrows():
        popup_html = (
            f"<b>POI名称：</b>{row[POI_NAME_COL]}<br>"
            f"<b>poi_id：</b>{row['poi_id']}<br>"
            f"<b>周边关联停车场数量：</b>{int(row['park_count'])}<br>"
            f"<b>平均车位利用率(供需权重)：</b>{round(row['weight'], 3)}"
        )
        folium.CircleMarker(
            location=[row[POI_LAT_COL], row[POI_LON_COL]],
            radius=3,
            popup=folium.Popup(popup_html, max_width=400),
            color="#222222",
            fill=True,
            fill_color="#444444",
            fill_opacity=0.7
        ).add_to(m)

    folium.LayerControl().add_to(m)

    m.save(str(OUT_HTML))
    print(f"\n任务4.3执行完成！热力图已保存至：{OUT_HTML}")
    print("\n提示：使用浏览器打开html文件查看热力图。")


if __name__ == "__main__":
    main()
