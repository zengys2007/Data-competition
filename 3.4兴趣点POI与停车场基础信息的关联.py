# ===================== 导入需要的库 =====================
# pandas：表格读写、数据清洗、表关联
import pandas as pd
# pathlib：文件路径管理，适配Windows/Linux，避免路径斜杠报错
from pathlib import Path

# ===================== 【配置区，按需修改文件名称】 =====================
OUTPUT_DIR = Path("./output")
# 任务1.2输出：绍兴全市合并后的停车场周边POI总表（csv文件，本次修改后的路径）
POI_FILE = OUTPUT_DIR / "绍兴全部停车场周边POI信息表.csv"
# 任务2.1输出：停车场基础信息总表（包含停车场编号、名称、经纬度）
PARK_BASE_FILE = OUTPUT_DIR / "park_base_total.csv"
# 任务3.4输出：POI与停车场多对多关联明细结果
OUTPUT_34 = OUTPUT_DIR / "POI_ParkingLot_Association_Table.csv"
# CSV文件编码，设置utf-8-sig，防止中文打开乱码
CSV_ENCODING = "utf-8-sig"
# 距离阈值：小于1000米判定存在关联（题目规定）
DISTANCE_THRESHOLD = 1000

# ===================== 主程序入口 =====================
def main():
    print("==================== 任务3.4 POI与停车场多对多空间关联 开始 ====================")

    # ========== 步骤1：读取任务1.2采集生成的POI兴趣点数据表 ==========
    print("1. 读取任务1.2采集的绍兴全部停车场周边POI信息表")
    df_poi_raw = pd.read_csv(POI_FILE, encoding=CSV_ENCODING)
    print(f"\nPOI原始采集记录总数：{df_poi_raw.shape[0]} 条")
    # 打印POI表全部字段，排查列名
    print(f"\nPOI表真实字段列表：{list(df_poi_raw.columns)}")

    # ========== 步骤2：读取任务2.1合并后的停车场基础信息总表 ==========
    print("\n2. 读取任务2.1合并的停车场基础信息总表")
    df_park_all = pd.read_csv(PARK_BASE_FILE, encoding=CSV_ENCODING)
    print(f"\n停车场基础信息，停车场总数量：{df_park_all.shape[0]} 个")
    print(f"df_park_all字段列表: {list(df_park_all.columns)}")

    # 选取需要的4个字段，使用原始编码字段名，不再转中文
    # TCCBH:停车场编号，TCCMC:停车场名称，JDZB:经度，WDZB:纬度
    df_park_simple = df_park_all[["TCCBH", "TCCMC", "JDZB", "WDZB"]].copy()
    print(f"df_park_simple字段列表: {list(df_park_simple.columns)}")

    # ========== 步骤3：POI实体去重，生成唯一POI标识 ==========
    print("\n3. 对POI进行去重，生成唯一POI实体")
    # 构造poi_id：poi_name + 保留6位小数的经纬度
    # 保留6位小数是为了规避浮点数精度误差，坐标微小差异判定为同一个POI
    df_poi_raw["poi_id"] = (
        df_poi_raw["poi_name"].astype(str)
        + "_"
        + df_poi_raw["poi_lon_gcj02"].astype(float).round(6).astype(str)
        + "_"
        + df_poi_raw["poi_lat_gcj02"].astype(float).round(6).astype(str)
    )
    # 按唯一键去重，保留第一条POI基础信息，得到不重复的独立POI实体集合
    df_poi_unique = df_poi_raw.drop_duplicates(subset="poi_id", keep="first").copy()
    print(f"\n去重后，独立唯一POI数量：{df_poi_unique.shape[0]}")

    # ========== 步骤4：按题目规则校验距离，筛选直线距离小于1000米的POI-停车场配对 ==========
    print("\n4. 距离校验，筛选直线距离小于1000米的POI-停车场配对")
    # 将距离字段转为数值类型，无法转换的脏数据自动置为空
    df_poi_raw["poi_distance_m"] = pd.to_numeric(df_poi_raw["poi_distance_m"], errors="coerce")
    # 核心筛选规则：距离 <1000米，满足条件才判定二者存在关联
    df_poi_qualified = df_poi_raw[df_poi_raw["poi_distance_m"] < DISTANCE_THRESHOLD].copy()
    print(f"\n满足距离条件的POI-停车场配对数量：{df_poi_qualified.shape[0]}")

    # ========== 步骤5：关联停车场基础信息，完善明细表字段 ==========
    print("\n5. 将合格的POI配对关联停车场基础信息（补充停车场编号TCCBH）")
    # left_on：POI表中存放停车场名字的列（1.2输出为park_name）
    # right_on：停车场基础表中存放停车场名称的列 TCCMC
    df_link_detail = pd.merge(
        left=df_poi_qualified,
        right=df_park_simple[["TCCBH", "TCCMC"]],
        left_on="park_TCCMC",
        right_on="TCCMC",
        how="left"
    )
    # 剔除停车场编号为空的无效行（名称匹配失败、无对应停车场的脏数据）
    df_link_detail = df_link_detail.dropna(subset=["TCCBH"])
    print(f"\n成功匹配到停车场编号的有效关联记录：{df_link_detail.shape[0]}")

    # ========== 步骤6：统计指标（用于分析多对多特征，可选） ==========
    print("\n6. 统计每个POI关联到的停车场数量")
    # 按poi_id分组，统计每个POI关联了多少个不同停车场
    poi_link_count = df_link_detail.groupby("poi_id").agg(
        关联停车场数量=("TCCBH", "nunique")
    ).reset_index()
    # 将统计结果合并回POI实体总表
    df_poi_unique = pd.merge(
        df_poi_unique,
        poi_link_count,
        on="poi_id",
        how="left"
    )
    # 空值填充为0：没有关联任何停车场的POI，关联数量记为0
    df_poi_unique["关联停车场数量"] = df_poi_unique["关联停车场数量"].fillna(0)

    # ========== 步骤7：输出保存多对多关联明细表 ==========
    print("\n7. 保存任务3.4结果：POI-停车场多对多关联明细")
    df_link_detail.to_csv(OUTPUT_34, encoding=CSV_ENCODING, index=False)
    print(f"\n结果文件已保存：{OUTPUT_34}")

    # 打印前10行预览，方便快速检查数据
    print("\n===== 关联表预览（前10行） =====")
    print(df_link_detail.head(10))

    print("\n==================== 任务3.4执行完毕 ====================")

# 程序入口，运行主函数
if __name__ == "__main__":
    main()