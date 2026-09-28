# ===================== 导入需要的库 =====================
# pandas：表格读取、合并、分组统计
import pandas as pd
# glob：批量匹配文件夹里所有csv、xlsx文件
import glob
# os：文件路径处理
import os

# ===================== 【配置区，按需修改】 =====================
# data文件夹路径，存放原始csv和训练集xlsx
DATA_FOLDER = "./data"
# 复用任务2.1输出的停车场基础信息总表
BASIC_FROM_TASK21 = "./park_base_total.csv"
# 任务3.3输出结果文件
OUTPUT_FILE = "./Hourly_Parking_Utilization_Results.csv"
# CSV中文编码
CSV_ENCODING = "utf-8-sig"
# 利用率标签阈值（可根据题目要求修改）
HIGH_THRESHOLD = 0.7   # >=0.7 → 高利用率
LOW_THRESHOLD = 0.3    # 0.3<=x<0.7 → 中利用率；<0.3 → 低利用率

# ===================== 工具函数：根据平均利用率生成标签 =====================
def get_util_tag(util_rate):
    """
    根据车位利用率返回标签
    :param util_rate: 停车场某一小时的平均车位利用率
    :return: 标签文本：高利用率/中利用率/低利用率/未知
    """
    # 判断空值，空值标记为未知
    if pd.isna(util_rate):
        return "未知"
    if util_rate >= HIGH_THRESHOLD:
        return "高利用率"
    elif util_rate >= LOW_THRESHOLD:
        return "中利用率"
    else:
        return "低利用率"

# ===================== 工具函数：读取单个动态停泊文件（支持csv/xlsx） =====================
def read_one_dynamic(file_path):
    """
    读取单个动态停泊文件，自动区分csv / xlsx
    xlsx特殊规则：第1行中文表头，第2行是英文别名行，真实数据从第3行开始
    :param file_path: 文件完整路径
    :return: 处理完成后的动态停泊DataFrame
    """
    file_name = os.path.basename(file_path)
    print(f"\n正在读取动态停泊文件：{file_name}")

    # 判断文件后缀
    if file_path.lower().endswith(".csv"):
        # 读取csv文件，字符串格式读取，防止编号丢失前导0
        df = pd.read_csv(file_path, encoding=CSV_ENCODING, dtype=str)
    elif file_path.lower().endswith(".xlsx"):
        # xlsx：header=0，取第1行作为列名；跳过第2行（英文别名行），真实数据第3行开始
        df = pd.read_excel(file_path, header=0, dtype=str)
        # 过滤第2行（该行内容是英文字段别名如TCCBH，不是真实数据）
        df = df[df["停车场编号"] != "TCCBH"]
    else:
        print(f"\n跳过不支持的文件类型：{file_name}")
        return pd.DataFrame()

    # 列名字典：中文列名映射为英文，和csv保持统一
    col_map = {
        "停车场编号": "TCCBH",
        "发布时间": "FBSJ",
        "泊位总数": "BWZS",
        "剩余泊位": "SYBW"
    }
    # 只重命名存在的列，不存在的不处理，避免报错
    rename_dict = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=rename_dict)

    return df

# ===================== 工具函数：批量读取全部动态停泊信息（csv + xlsx） =====================
def load_all_dynamic(folder):
    """读取data下所有动态停泊相关csv、xlsx，纵向拼接"""
    # 匹配两类文件：动态停泊csv、训练集xlsx（越城、诸暨）
    file_list = []
    file_list.extend(glob.glob(os.path.join(folder, "*动态停泊信息.csv")))
    file_list.extend(glob.glob(os.path.join(folder, "训练集*.xlsx")))

    df_list = []
    for f in file_list:
        df_one = read_one_dynamic(f)
        if not df_one.empty:
            df_list.append(df_one)
    if len(df_list) == 0:
        print("\n没有找到任何动态停泊信息文件！")
        return pd.DataFrame()
    # 纵向合并所有动态停泊数据
    df_all = pd.concat(df_list, ignore_index=True)
    return df_all

# ===================== 主程序入口 =====================
def main():
    print("==================== 任务3.3【兼容csv+xlsx，复用任务2.1基础总表】版本 开始 ====================")

    # 1、读取全部动态停泊信息（csv+训练集xlsx）
    print("正在读取所有动态停泊信息文件...")
    df_dynamic = load_all_dynamic(DATA_FOLDER)
    if df_dynamic.empty:
        return
    print(f"✅ 全部动态停泊表合并完成，总原始记录行数：{df_dynamic.shape[0]}")

    # 2、读取【任务2.1输出的停车场基础总表】，复用2.1成果
    print(f"\n正在读取任务2.1输出基础总表：{BASIC_FROM_TASK21}")
    if not os.path.exists(BASIC_FROM_TASK21):
        print(f"\n文件不存在！请先运行任务2.1生成 {BASIC_FROM_TASK21}！")
        return
    df_base = pd.read_csv(BASIC_FROM_TASK21, encoding=CSV_ENCODING)
    print(f"\n任务2.1基础总表读取成功，停车场记录数：{df_base.shape[0]}")

    # 3、动态停泊表字段标准化处理
    print("\n===== 动态停泊表字段标准化 =====")
    # 统一重命名字段
    df_dynamic = df_dynamic.rename(columns={
        "TCCBH": "停车场ID",
        "FBSJ": "记录时间",
        "BWZS": "泊位总数",
        "SYBW": "剩余泊位"
    })
    # 将泊位数量由字符串转为数值，无法转换的变成NaN
    df_dynamic["泊位总数"] = pd.to_numeric(df_dynamic["泊位总数"], errors="coerce")
    df_dynamic["剩余泊位"] = pd.to_numeric(df_dynamic["剩余泊位"], errors="coerce")
    # 核心公式：当前泊车数量 = 泊位总数 - 剩余泊位
    df_dynamic["当前泊车数量"] = df_dynamic["泊位总数"] - df_dynamic["剩余泊位"]

    # 4、基础信息表筛选：只保留停车场ID、总泊车位，去重
    print("\n===== 基础信息表字段筛选 =====")
    df_base = df_base.rename(columns={"TCCBH": "停车场ID", "BWZS": "总泊车位"})
    df_base["总泊车位"] = pd.to_numeric(df_base["总泊车位"], errors="coerce")
    # 同一个停车场只保留第一条记录，去除重复停车场
    df_base = df_base[["停车场ID", "总泊车位"]].drop_duplicates(subset="停车场ID", keep="first")
    print(f"\n基础表提取完成，唯一停车场数量：{df_base.shape[0]}")

    # 5、时间转换，提取【日期+小时】用于分组
    print("\n===== 时间解析，提取小时信息 =====")
    # format="mixed"：自动识别混合时间格式，兼容带毫秒的时间字符串
    df_dynamic["记录时间"] = pd.to_datetime(df_dynamic["记录时间"], errors="coerce", format="mixed")
    # 删除时间为空、当前泊车数量为空的无效行
    df_dynamic = df_dynamic.dropna(subset=["记录时间", "当前泊车数量"])
    # 将时间向下取整到小时，例如 08:15 → 08:00，用于按小时分组
    df_dynamic["日期小时"] = df_dynamic["记录时间"].dt.floor("h")
    print(f"\n时间清洗完成，剩余有效动态停泊记录：{df_dynamic.shape[0]}")

    # 6、两张表合并：根据停车场ID关联总泊车位
    print("\n===== 关联停车场基础信息（总泊车位） =====")
    df_merge = pd.merge(left=df_dynamic, right=df_base, on="停车场ID", how="left")
    # 清洗：剔除总泊车位为空、总泊车位=0的行，防止除以0报错
    df_merge = df_merge.dropna(subset=["总泊车位"])
    df_merge = df_merge[df_merge["总泊车位"] > 0]
    print(f"\n表合并完成，有效记录行数：{df_merge.shape[0]}")

    # 7、计算每一条采样时刻的【瞬时车位利用率】
    print("\n===== 计算每一时刻瞬时车位利用率 =====")
    # 公式：瞬时车位利用率 = 当前泊车数量 / 总泊车位
    df_merge["瞬时车位利用率"] = df_merge["当前泊车数量"] / df_merge["总泊车位"]
    # 限制利用率范围0~1，过滤脏数据（泊车数量大于总车位导致利用率>1）
    df_merge["瞬时车位利用率"] = df_merge["瞬时车位利用率"].clip(lower=0, upper=1)

    # 8、分组：按【停车场ID + 日期小时】求平均，得到每小时车位利用率
    print("\n===== 分组计算每个停车场每小时平均车位利用率 =====")
    df_hour_result = df_merge.groupby(["停车场ID", "日期小时"], as_index=False).agg(
        每小时平均车位利用率=("瞬时车位利用率", "mean"),
        该小时采样记录条数=("瞬时车位利用率", "count")
    )

    # 9、根据每小时平均利用率打标签
    print("\n===== 根据车位利用率打标签 =====")
    df_hour_result["利用率标签"] = df_hour_result["每小时平均车位利用率"].apply(get_util_tag)

    # 10、输出预览，保存结果csv
    print("\n===== 结果预览（前10行） =====")
    print(df_hour_result.head(10))
    df_hour_result.to_csv(OUTPUT_FILE, encoding=CSV_ENCODING, index=False)
    print(f"\n任务3.3结果保存成功 → {OUTPUT_FILE}")
    print("输出字段：停车场ID / 日期小时 / 每小时平均车位利用率 / 该小时采样记录条数 / 利用率标签")

    print("\n==================== 任务3.3执行完毕 ====================")

if __name__ == "__main__":
    main()