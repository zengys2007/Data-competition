# =====================导入依赖库=====================
import pandas as pd
from pathlib import Path

# =====================配置参数区=====================
OUTPUT_DIR = Path("./output")
# 任务2.1输出：融合后的停车场基础总表
INPUT_BASE = OUTPUT_DIR / "park_base_total.csv"
# 任务1.2输出：停车场周边兴趣点信息表
INPUT_POI = OUTPUT_DIR / "绍兴全部停车场周边POI信息表.csv"
# 任务2.2输出：融合互联网采集经纬度后的停车场基础表
OUT_MERGE_BASE = OUTPUT_DIR / "park_base_merge_lonlat.csv"

CSV_ENCODING = "utf-8-sig"

# 关联主键：停车场编号，两张表关联的核心字段
JOIN_KEY = "TCCBH"
# POI表里面停车场编号字段名（来自任务1.2输出）
POI_JOIN_KEY = "park_TCCBH"

# =====================函数定义=====================
def get_park_unique_coord(poi_df: pd.DataFrame, park_id_col: str, lon_col: str, lat_col: str):
    """
    从多对多POI结果表提取【每个停车场唯一一组采集的经纬度】
    说明：POI表一个停车场有多条POI，但是停车场自身坐标是重复的，去重，每个停车场只保留一行坐标
    :param poi_df: 任务1.2输出的POI完整表
    :param park_id_col: POI表停车场编号列名
    :param lon_col: POI表停车场经度列
    :param lat_col: POI表停车场纬度列
    :return: DataFrame，两列：park_TCCBH, api_lon_gcj02, api_lat_gcj02
    """
    # 选取停车场编号、API采集的停车场经纬度，丢弃POI相关字段
    park_coord_df = poi_df[[park_id_col, lon_col, lat_col]].copy()

    # 重命名列，方便merge的时候区分原始坐标和API采集坐标
    park_coord_df.rename(columns={
        park_id_col: JOIN_KEY,
        lon_col: "api_lon_gcj02",
        lat_col: "api_lat_gcj02"
    }, inplace=True)

    # 去重：同一个停车场保留1条API坐标，去除重复行
    park_coord_df = park_coord_df.drop_duplicates(subset=[JOIN_KEY], keep="first")
    print(f"\n从POI表提取去重后的停车场API坐标记录数：{park_coord_df.shape[0]}")
    return park_coord_df


# =====================主程序入口=====================
def main():
    print("====================任务2.2 互联网采集经纬度融合 开始====================")

    # --------步骤1：读取输入文件--------
    # 读取任务2.1输出的停车场基础总表
    if not INPUT_BASE.exists():
        print(f"文件不存在：{INPUT_BASE}，请先运行任务2.1生成该文件！")
        return
    df_base = pd.read_csv(INPUT_BASE, encoding=CSV_ENCODING)
    print(f"\n读取停车场基础总表，记录数：{df_base.shape[0]}")
    print(f"\n基础表字段：{df_base.columns.tolist()}")

    # 读取任务1.2输出POI表
    if not INPUT_POI.exists():
        print(f"文件不存在：{INPUT_POI}，请先运行任务1.2采集POI！")
        return
    df_poi_raw = pd.read_csv(INPUT_POI, encoding=CSV_ENCODING)
    print(f"\n读取POI兴趣点原始表，POI关联总记录数：{df_poi_raw.shape[0]}")
    print(f"\nPOI表字段：{df_poi_raw.columns.tolist()}")

    # --------步骤2：从POI多对多表提取每个停车场唯一API采集坐标--------
    # park_lon_gcj02、park_lat_gcj02：任务1.2输出，停车场自身GCJ‑02经纬度
    df_park_api_coord = get_park_unique_coord(
        poi_df=df_poi_raw,
        park_id_col=POI_JOIN_KEY,
        lon_col="park_lon_gcj02",
        lat_col="park_lat_gcj02"
    )

    # --------步骤3：左连接融合：基础表 left join API采集坐标表 --------
    """
    how="left"：左连接，保留停车场基础表全部停车场；
    匹配上的停车场，填充api_lon_gcj02、api_lat_gcj02；
    没有采集到API坐标的停车场，api_xxx字段填充NaN空值。
    """
    df_merge = pd.merge(
        left=df_base,
        right=df_park_api_coord,
        on=JOIN_KEY,
        how="left"
    )

    print(f"\nmerge融合完成，融合后总记录行数：{df_merge.shape[0]}")

    # --------统计：API采集坐标获取成功/失败数量--------
    api_has_coord = df_merge["api_lon_gcj02"].notna().sum()
    api_no_coord = df_merge["api_lon_gcj02"].isna().sum()
    print(f"\n统计：成功获取API采集经纬度停车场数量：{api_has_coord}")
    print(f"\n统计：未获取API采集经纬度停车场数量：{api_no_coord}")

    # --------输出融合之后的csv文件--------
    df_merge.to_csv(OUT_MERGE_BASE, encoding=CSV_ENCODING, index=False)
    print(f"\n任务2.2输出文件：{OUT_MERGE_BASE}")

    print("\n====字段说明（输出表新增2列）====")
    print("api_lon_gcj02 ：高德API互联网采集得到停车场经度 GCJ‑02坐标系")
    print("api_lat_gcj02 ：高德API互联网采集得到停车场纬度 GCJ‑02坐标系")
    print("JDZB / WDZB ：原始csv自带的经纬度（数据质量参差不齐，部分坐标错误）")




if __name__ == "__main__":
    main()