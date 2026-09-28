# ===================== 导入库 =====================
import pandas as pd
import folium
from folium.plugins import HeatMap
from pathlib import Path

# =====================【配置区，务必核对修改】 =====================
OUTPUT_DIR = Path("./output")
# 在任务2.3输出停车场基础表上 任务3.1已完成经纬度的编码格式转换GCJ‑02 → WGS84转换
PARK_BASE = OUTPUT_DIR / "valid_park_base_wgs84.csv"
# 任务3.3输出：每小时车位利用率
UTIL_33 = OUTPUT_DIR / "Hourly_Parking_Utilization_Results.csv"
# 输出交互式热力地图
OUT_HTML = OUTPUT_DIR / "Folium_绍兴停车场供需热力地图.html"
CSV_ENCODING = "utf-8-sig"




# ---------- 这里修改为你表格里面真实WGS84字段名 ----------
# 任务3.1输出的WGS84经度、纬度
WGS84_LON_COL = "lon_wgs84_cgcs2000"
WGS84_LAT_COL = "lat_wgs84_cgcs2000"

# 热力图样式参数
HEAT_RADIUS = 26
HEAT_BLUR = 18
MAP_ZOOM_START = 11

# 颜色梯度：蓝色(利用率低，供给充足) →绿色→黄色→橙色→红色(利用率高，供需紧张)
HEAT_GRADIENT = {
    0.0: "#0044ff",
    0.3: "#00cc44",
    0.5: "#ffdd00",
    0.7: "#ff7700",
    1.0: "#dd0000"
}


def main():
    print("==================== 任务4.1 Folium停车场泊车供需热力地图 开始 ====================")

    # --------------------------
    # 步骤1：读取停车场基础信息（WGS84坐标来自任务3.1处理结果）
    # --------------------------
    print("\n1.读取停车场基础信息表")
    df_park = pd.read_csv(PARK_BASE, encoding=CSV_ENCODING)
    print(f"\n停车场总记录数：{df_park.shape[0]}")
    print(f"表格全部字段：{df_park.columns.tolist()}")

    # 过滤：WGS84经纬度、停车场编号、总泊位不为空，总泊位>0
    df_park = df_park.dropna(subset=["TCCBH", WGS84_LON_COL, WGS84_LAT_COL, "BWZS"])
    df_park = df_park[df_park["BWZS"] > 0].copy()

    # 转为数值
    df_park[WGS84_LON_COL] = pd.to_numeric(df_park[WGS84_LON_COL], errors="coerce")
    df_park[WGS84_LAT_COL] = pd.to_numeric(df_park[WGS84_LAT_COL], errors="coerce")
    df_park["BWZS"] = pd.to_numeric(df_park["BWZS"], errors="coerce")

    # 过滤绍兴合理经纬度范围
    df_park = df_park[(df_park[WGS84_LON_COL] > 119.0) & (df_park[WGS84_LON_COL] < 121.0)]
    df_park = df_park[(df_park[WGS84_LAT_COL] > 29.0) & (df_park[WGS84_LAT_COL] < 31.0)]
    print(f"\n过滤后有效WGS84坐标停车场数量：{df_park.shape[0]}")


    # --------------------------
    # 步骤2：读取任务3.3小时利用率，聚合得到每个停车场平均车位利用率
    # --------------------------
    print("\n2.读取任务3.3车位利用率数据，聚合至停车场维度")
    df_hour_util = pd.read_csv(UTIL_33, encoding=CSV_ENCODING)
    df_park_util = df_hour_util.groupby("停车场ID").agg(
        avg_usage_rate=("每小时平均车位利用率", "mean")
    ).reset_index()
    df_park_util.rename(columns={"停车场ID": "TCCBH"}, inplace=True)
    print(f"\n存在利用率统计的停车场数量：{df_park_util.shape[0]}")


    # --------------------------
    # 步骤3：合并基础信息 + 利用率
    # --------------------------
    print("\n3.合并停车场基础信息与平均车位利用率")
    df_merge = pd.merge(
        df_park,
        df_park_util,
        on="TCCBH",
        how="inner"
    )
    print(f"\n同时具备WGS84坐标+利用率的停车场样本数：{df_merge.shape[0]}")


    # --------------------------
    # 步骤4：组装热力数据 格式 [纬度，经度，权重(平均利用率)]
    # --------------------------
    print("\n4.组装热力图层数据，直接使用任务3.1输出WGS84坐标，不做坐标转换")
    heat_data = []
    for _, row in df_merge.iterrows():
        lat = row[WGS84_LAT_COL]
        lon = row[WGS84_LON_COL]
        weight = row["avg_usage_rate"]
        heat_data.append([lat, lon, weight])

    # 地图中心点：全部停车场经纬度均值
    center_lat = df_merge[WGS84_LAT_COL].mean()
    center_lon = df_merge[WGS84_LON_COL].mean()

    print("\n5.使用稳定底图初始化地图")
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=MAP_ZOOM_START,
        tiles="OpenStreetMap",  # 或者 "OpenStreetMap"
        attr="CartoDB"
    )

    # 添加热力图层
    HeatMap(
        heat_data,
        radius=HEAT_RADIUS,
        blur=HEAT_BLUR,
        gradient=HEAT_GRADIENT,
        min_opacity=0.2,
        max_zoom=16,
        name="停车场供需热力(平均车位利用率)"
    ).add_to(m)


    # --------------------------
    # 步骤5：添加停车场点位，点击弹窗查看详情
    # --------------------------
    print("\n5.添加停车场点位弹窗标记")
    for _, row in df_merge.iterrows():
        pop_html = (
            f"<b>停车场编号:</b> {row['TCCBH']}<br>"
            f"<b>停车场名称:</b> {row['TCCMC']}<br>"
            f"<b>总泊位数:</b> {row['BWZS']}<br>"
            f"<b>平均车位利用率:</b> {round(row['avg_usage_rate'],3)}"
        )
        folium.CircleMarker(
            location=[row[WGS84_LAT_COL], row[WGS84_LON_COL]],
            radius=3,
            popup=folium.Popup(pop_html, max_width=380),
            color="#222222",
            fill=True,
            fill_color="#444444",
            fill_opacity=0.6
        ).add_to(m)

    folium.LayerControl().add_to(m)

    # 保存输出HTML
    m.save(str(OUT_HTML))
    print(f"\n热力地图文件已保存：{OUT_HTML}")
    print("\n使用说明：浏览器打开html，需要联网加载地图底图。")
    print("颜色释义：🟦蓝色：利用率低、泊位充足；🔴红色：利用率高，停车供需矛盾突出。")
    print("\n本代码直接读取任务3.1输出WGS84坐标，不再执行GCJ‑02坐标转换，避免二次转换坐标错乱。")
    print("\n==================== 任务4.1执行完毕 ====================")


if __name__ == "__main__":
    main()
