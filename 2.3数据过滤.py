# =====================导入依赖库=====================
import pandas as pd
from pathlib import Path

# =====================配置参数区=====================
OUTPUT_DIR = Path("./output")
# 输入文件
INPUT_BASE_MERGE = OUTPUT_DIR / "park_base_merge_lonlat.csv"   # 任务2.2输出：融合API经纬度的停车场基础总表
INPUT_DYNAMIC = OUTPUT_DIR / "park_dynamic_total.csv"          # 任务2.1输出：融合后的全量泊车记录表

# 输出文件
OUT_VALID_PARK_BASE = OUTPUT_DIR / "valid_park_base.csv"    # 过滤后【有效停车场基础信息表】
OUT_VALID_DYNAMIC = OUTPUT_DIR / "valid_park_dynamic.csv"   # 过滤后【有效泊车记录表】

CSV_ENCODING = "utf-8-sig"
JOIN_KEY = "TCCBH"       # 停车场编号，两张表关联主键

# =====================主程序入口=====================
def main():
    print("====================任务2.3 数据过滤 开始====================")
    print("=====4条清洗规则=====")
    print("规则1：泊车记录表中停车场编码不存在于停车场基础信息表的数据为无效数据；")
    print("规则2：停车场基础信息表中对应无泊车记录的数据为无效数据；")
    print("规则3：停车场经纬度信息为空的记录为无效数据；")
    print("规则4：剩余泊车位无更新的停车场为无效数据；\n")

    # --------步骤1：读取输入数据--------
    if not INPUT_BASE_MERGE.exists():
        print(f"\n文件不存在：{INPUT_BASE_MERGE}，请先运行任务2.2！")
        return
    df_base = pd.read_csv(INPUT_BASE_MERGE, encoding=CSV_ENCODING)
    print(f"\n读取【融合经纬度停车场基础表】原始总记录数：{df_base.shape[0]}")

    if not INPUT_DYNAMIC.exists():
        print(f"\n文件不存在：{INPUT_DYNAMIC}，请先运行任务2.1！")
        return
    df_dynamic = pd.read_csv(INPUT_DYNAMIC, encoding=CSV_ENCODING)
    print(f"\n读取【全量泊车记录表】原始总记录数：{df_dynamic.shape[0]}")

    # =====================规则1 处理：泊车记录表中停车场编码不存在于停车场基础信息表的数据为无效数据 =====================
    print("\n----------【执行规则1】过滤泊车记录：剔除TCCBH不在基础表中的泊车记录----------")
    # 获取基础表里所有合法停车场编号集合
    valid_park_id_set = set(df_base[JOIN_KEY].dropna())
    # 保留泊车表中TCCBH存在于基础表编号集合里的记录，其余直接剔除
    df_dynamic_rule1 = df_dynamic[df_dynamic[JOIN_KEY].isin(valid_park_id_set)].copy()
    print(f"\n规则1执行前泊车记录：{df_dynamic.shape[0]}，规则1执行后泊车记录：{df_dynamic_rule1.shape[0]}")
    print(f"\n规则1剔除无效泊车记录数量：{df_dynamic.shape[0] - df_dynamic_rule1.shape[0]}")


    # =====================规则3 处理：停车场经纬度信息为空的记录为无效数据 =====================
    # 说明：优先使用任务2.2融合进来的api采集经纬度(api_lon_gcj02,api_lat_gcj02)作为校验经纬度
    # 只要api_lon_gcj02或者api_lat_gcj02任意一个为空，则判定该停车场经纬度为空，直接剔除
    print("\n----------【执行规则3】过滤停车场基础表：剔除经纬度为空的停车场----------")
    df_base_rule3 = df_base[
        (df_base["api_lon_gcj02"].notna()) &
        (df_base["api_lat_gcj02"].notna())
    ].copy()
    print(f"\n规则3执行前停车场总数：{df_base.shape[0]}，规则3执行后停车场数量：{df_base_rule3.shape[0]}")
    print(f"\n规则3剔除经纬度为空停车场数量：{df_base.shape[0] - df_base_rule3.shape[0]}")


    # =====================规则4 处理：剩余泊车位无更新的停车场为无效数据 =====================
    # 说明：剩余泊位更新字段：SYBW（剩余泊车位）；FBSJ（发布时间）。
    # 剩余泊车位无更新：理解为SYBW为空，代表没有实时泊位更新数据，该停车场无效
    print("\n----------【执行规则4】过滤停车场基础表：剔除剩余泊车位无更新的停车场----------")
    # 第一步：从【经过规则1过滤后的泊车表】，提取有泊位更新记录的停车场编号
    park_has_update = df_dynamic_rule1[df_dynamic_rule1["SYBW"].notna()][JOIN_KEY].unique()
    # 第二步：在经过规则3过滤后的停车场表里，只保留存在泊位更新记录的停车场
    df_base_rule3_4 = df_base_rule3[df_base_rule3[JOIN_KEY].isin(park_has_update)].copy()
    print(f"规则4执行前停车场数量：{df_base_rule3.shape[0]}，规则4执行后停车场数量：{df_base_rule3_4.shape[0]}")
    print(f"规则4剔除无泊位更新停车场数量：{df_base_rule3.shape[0] - df_base_rule3_4.shape[0]}")


    # =====================规则2 处理：停车场基础信息表中对应无泊车记录的数据为无效数据 =====================
    print("\n----------【执行规则2】过滤停车场：剔除没有任何泊车记录的停车场----------")
    # 从规则1过滤后的泊车表，提取所有存在泊车记录的停车场编号
    park_id_with_dynamic = df_dynamic_rule1[JOIN_KEY].unique()
    # 在经过规则3、4过滤后的停车场表，只保留存在泊车记录的停车场
    df_base_final = df_base_rule3_4[df_base_rule3_4[JOIN_KEY].isin(park_id_with_dynamic)].copy()
    print(f"规则2执行前停车场数量：{df_base_rule3_4.shape[0]}，规则2执行后【最终有效停车场】：{df_base_final.shape[0]}")
    print(f"规则2剔除无泊车记录停车场数量：{df_base_rule3_4.shape[0] - df_base_final.shape[0]}")

    # 同步过滤泊车表：只保留最终有效停车场对应的泊车记录
    final_valid_park_ids = set(df_base_final[JOIN_KEY])
    df_dynamic_final = df_dynamic_rule1[df_dynamic_rule1[JOIN_KEY].isin(final_valid_park_ids)].copy()


    # --------输出结果--------
    df_base_final.to_csv(OUT_VALID_PARK_BASE, encoding=CSV_ENCODING, index=False)
    df_dynamic_final.to_csv(OUT_VALID_DYNAMIC, encoding=CSV_ENCODING, index=False)

    print("\n====================任务2.3 过滤完成，汇总统计====================")
    print(f"\n最终有效停车场记录数量：{df_base_final.shape[0]}")
    print(f"\n最终有效泊车记录数量：{df_dynamic_final.shape[0]}")
    print(f"\n有效停车场表输出：{OUT_VALID_PARK_BASE}")
    print(f"\n有效泊车记录表输出：{OUT_VALID_DYNAMIC}")


    # 执行顺序说明
    # 执行顺序：规则1 → 规则3 → 规则4 → 规则2


    # 规则1 先清洗泊车表，把泊车表里非法停车场编号直接删掉，减少后续数据量
    # 规则3 清洗停车场，剔除经纬度为空停车场
    # 规则4 剔除没有泊位更新（SYBW为空）的停车场
    # 规则2 最后剔除剩下里面没有任何泊车记录的停车场
    #
    # 最后用筛选完的停车场编号，反向过滤泊车表，得到最终泊车记录




if __name__ == "__main__":
    main()