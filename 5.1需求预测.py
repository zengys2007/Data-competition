# ===================== 导入需要的库 =====================
# pandas：表格读写、时间解析、分组统计、表关联
import pandas as pd
# pathlib：跨平台路径，避免写死盘符
from pathlib import Path

# ===================== 【配置区 / 接口，改这里即可】 =====================
# 本文件只做「画像基线」：每个停车场「星期几 × 小时」的历史平均利用率。
# 主模型（LightGBM 残差）放到 5.2，不要写进本文件。

# -------- 路径 --------
# 清洗后的停车场名单：任务 2.3 输出（不要用 data 里未过滤的原始 csv）
VALID_PARK_BASE = Path("./output/valid_park_base.csv")
# 清洗后的动态泊车记录：任务 2.3 输出
VALID_PARK_DYNAMIC = Path("./output/valid_park_dynamic.csv")
# 训练集文件夹：只读「训练集-*.xlsx」，不读 data 里各区脏 csv
TRAIN_DIR = Path("./data")
# 训练集文件名通配（越城 / 诸暨各一份）
TRAIN_XLSX_GLOB = "训练集*.xlsx"

# 输出目录
OUTPUT_DIR = Path("./output")
# 画像查找表：5.2 主模型也可以复用
OUT_PROFILE = OUTPUT_DIR / "画像基线_停车场星期小时.csv"
# 预测结果：越城+诸暨，预测窗口内 0-23 点全覆盖
OUT_FORECAST = OUTPUT_DIR / "预测_越城诸暨_20250414-0418_画像基线.csv"
# 小时利用率中间表（仅有效场库 + 训练集动态，便于核对）
OUT_HOUR_UTIL = OUTPUT_DIR / "Hourly_Parking_Utilization_Clean_Train.csv"

CSV_ENCODING = "utf-8-sig"

# -------- 预测范围 --------
# 只预测这两个区县（与 valid_park_base.SZQX 一致）
TARGET_DISTRICTS = ["越城区", "诸暨市"]
# 预测起止日期（含首尾），赛题窗口
PREDICT_START = "2025-04-14"
PREDICT_END = "2025-04-18"
# 小时全覆盖：0～23
HOURS_FULL = list(range(0, 24))

# -------- 历史数据开关（True=使用，False=跳过） --------
# 使用 2.3 洗过的动态表（诸暨/越城这段主要是 3 月初快照）
USE_VALID_DYNAMIC = True
# 使用官方训练集 xlsx 动态 sheet（2025-04-07～04-13，工作日画像的主力）
USE_TRAIN_XLSX = True

# -------- 画像缺失时的回退阶梯（从上到下，谁有数用谁） --------
# 1 停车场×星期几×小时 → 2 停车场×是否工作日×小时 → 3 停车场×小时
# → 4 区县×星期几×小时 → 5 区县×小时 → 6 全市×小时
ENABLE_FALLBACK = True

# 利用率裁剪到 [0, 1]；占用数裁剪到 [0, 总泊位]
CLIP_UTIL = True
# ===================== 配置区结束 =====================

# pandas 星期：0=周一 … 6=周日（与预测窗口周一到周五对齐）
WEEKDAY_CN = {
    0: "星期一",
    1: "星期二",
    2: "星期三",
    3: "星期四",
    4: "星期五",
    5: "星期六",
    6: "星期日",
}


# ===================== 工具函数 =====================
def rename_dynamic_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    把动态表列名统一成英文赛题字段，兼容 csv（已是 TCCBH）和 xlsx 中文表头。
    """
    col_map = {
        "停车场编号": "TCCBH",
        "停车场名称": "TCCMC",
        "所在区县": "SZQX",
        "泊位总数": "BWZS",
        "剩余泊位": "SYBW",
        "发布时间": "FBSJ",
    }
    rename_dict = {k: v for k, v in col_map.items() if k in df.columns}
    return df.rename(columns=rename_dict)


def is_dynamic_sheet(df: pd.DataFrame) -> bool:
    """
    判断当前 sheet 是不是「动态泊车记录」。
    训练集 xlsx 还有一张停车场基础信息，基础信息没有「剩余泊位/发布时间」这一套，要跳过。
    """
    df = rename_dynamic_columns(df)
    need = {"TCCBH", "SYBW", "FBSJ"}
    return need.issubset(set(df.columns))


def read_train_xlsx_dynamic(train_dir: Path, glob_pat: str) -> pd.DataFrame:
    """
    读取 data 下全部训练集 xlsx 的【动态泊车】sheet，剔除第 2 行英文字段别名。
    不用训练集里的停车场基础 sheet 当预测名单（名单只认 2.3 洗过的 valid_park_base）。
    """
    files = sorted(train_dir.glob(glob_pat))
    if len(files) == 0:
        print(f"\n未找到训练集：{train_dir / glob_pat}")
        return pd.DataFrame()

    frames = []
    for fpath in files:
        print(f"\n读取训练集：{fpath.name}")
        try:
            excel = pd.ExcelFile(fpath)
        except Exception as e:
            print(f"  打开失败，跳过。原因：{e}")
            continue

        for sheet_name in excel.sheet_names:
            try:
                df = pd.read_excel(fpath, sheet_name=sheet_name, dtype=str, header=0)
            except Exception as e:
                print(f"  sheet [{sheet_name}] 读取失败，跳过。原因：{e}")
                continue

            # 去掉英文字段别名行（停车场编号列等于 TCCBH）
            if "停车场编号" in df.columns:
                df = df[df["停车场编号"] != "TCCBH"].copy()

            if not is_dynamic_sheet(df):
                print(f"  sheet [{sheet_name}] 不是动态泊车表，跳过")
                continue

            df = rename_dynamic_columns(df)
            print(f"  sheet [{sheet_name}] 动态记录 {df.shape[0]} 条")
            frames.append(df)

    if len(frames) == 0:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_valid_dynamic(path: Path) -> pd.DataFrame:
    """读取任务 2.3 清洗后的动态泊车 csv。"""
    if not path.exists():
        print(f"\n文件不存在：{path}，请先运行任务 2.3")
        return pd.DataFrame()
    df = pd.read_csv(path, encoding=CSV_ENCODING, dtype=str)
    df = rename_dynamic_columns(df)
    print(f"\n读取清洗动态表 {path.name}，记录数：{df.shape[0]}")
    return df


def to_hourly_util(df_dyn: pd.DataFrame, df_base: pd.DataFrame) -> pd.DataFrame:
    """
    把瞬时泊车记录聚合成「停车场 × 小时」利用率。
    占用数 = 总泊位 - 剩余泊位；利用率 = 占用数 / 基础表总泊位（与任务 3.3 公式一致）。
    总泊位一律用 valid_park_base 的 BWZS，不用动态表里可能不一致的 BWZS。
    """
    df = df_dyn.copy()
    df["SYBW"] = pd.to_numeric(df["SYBW"], errors="coerce")
    df["FBSJ"] = pd.to_datetime(df["FBSJ"], errors="coerce", format="mixed")
    df = df.dropna(subset=["TCCBH", "FBSJ", "SYBW"])

    cap = df_base[["TCCBH", "BWZS"]].drop_duplicates(subset="TCCBH", keep="first")
    cap["BWZS"] = pd.to_numeric(cap["BWZS"], errors="coerce")
    cap = cap[(cap["BWZS"].notna()) & (cap["BWZS"] > 0)]

    df = df.merge(cap, on="TCCBH", how="inner")
    df["占用数"] = df["BWZS"] - df["SYBW"]
    df["瞬时利用率"] = df["占用数"] / df["BWZS"]
    if CLIP_UTIL:
        df["瞬时利用率"] = df["瞬时利用率"].clip(lower=0, upper=1)

    df["日期小时"] = df["FBSJ"].dt.floor("h")
    hour_df = df.groupby(["TCCBH", "日期小时"], as_index=False).agg(
        每小时平均车位利用率=("瞬时利用率", "mean"),
        该小时采样记录条数=("瞬时利用率", "count"),
        总泊位=("BWZS", "first"),
    )
    return hour_df


def add_calendar_cols(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    """从时间列拆出小时、星期几序号、是否工作日。"""
    out = df.copy()
    ts = pd.to_datetime(out[time_col], errors="coerce")
    out["小时"] = ts.dt.hour.astype(int)
    out["星期几序号"] = ts.dt.dayofweek.astype(int)
    out["是否工作日"] = (out["星期几序号"] <= 4).astype(int)
    return out


def mean_profile(df: pd.DataFrame, keys: list, value_col: str, out_col: str) -> pd.DataFrame:
    """按 keys 对利用率求平均，得到一张查找表。"""
    g = df.groupby(keys, as_index=False)[value_col].mean()
    return g.rename(columns={value_col: out_col})


def fill_with_profile(grid: pd.DataFrame, profile: pd.DataFrame, keys: list, src_name: str) -> pd.DataFrame:
    """
    把画像利用率 merge 到预测网格。
    只填充「画像基线利用率」仍为空的行，并记下本层来源，方便检查回退用了哪一层。
    """
    tmp = profile.copy()
    util_col = [c for c in tmp.columns if c not in keys][0]
    tmp = tmp.rename(columns={util_col: "_fill_util"})
    merged = grid.merge(tmp, on=keys, how="left")
    miss = merged["画像基线利用率"].isna() & merged["_fill_util"].notna()
    merged.loc[miss, "画像基线利用率"] = merged.loc[miss, "_fill_util"]
    merged.loc[miss, "画像来源"] = src_name
    return merged.drop(columns=["_fill_util"])


# ===================== 主程序 =====================
def main():
    print("==================== 任务5.1 需求预测（画像基线）开始 ====================")
    print("说明：本脚本只用 output 清洗表 + 训练集 xlsx，不用 data 里未过滤的区县 csv。")
    print("主模型请用单独文件 5.2，不要改本文件职责。\n")

    # ---------- 1. 预测名单：2.3 有效停车场 ∩ 目标区县 ----------
    print("1. 读取清洗后的停车场基础表，筛选越城区 / 诸暨市")
    if not VALID_PARK_BASE.exists():
        print(f"文件不存在：{VALID_PARK_BASE}，请先运行任务 2.3")
        return
    df_base_all = pd.read_csv(VALID_PARK_BASE, encoding=CSV_ENCODING, dtype={"TCCBH": str})
    df_base = df_base_all[df_base_all["SZQX"].isin(TARGET_DISTRICTS)].copy()
    df_base["TCCBH"] = df_base["TCCBH"].astype(str)
    df_base["BWZS"] = pd.to_numeric(df_base["BWZS"], errors="coerce")
    df_base = df_base.dropna(subset=["TCCBH", "BWZS"])
    df_base = df_base[df_base["BWZS"] > 0]
    df_base = df_base.drop_duplicates(subset="TCCBH", keep="first")
    print(f"目标区县有效停车场数量：{df_base.shape[0]}")
    print(df_base["SZQX"].value_counts().to_string())
    target_ids = set(df_base["TCCBH"])

    # ---------- 2. 历史动态：清洗表 + 训练集，且只保留上述有效编号 ----------
    print("\n2. 拼接历史泊车记录（清洗动态表 + 训练集动态 sheet）")
    dyn_parts = []
    if USE_VALID_DYNAMIC:
        df_vd = load_valid_dynamic(VALID_PARK_DYNAMIC)
        if not df_vd.empty:
            df_vd["TCCBH"] = df_vd["TCCBH"].astype(str)
            df_vd = df_vd[df_vd["TCCBH"].isin(target_ids)]
            print(f"清洗动态表中属于目标场库的记录：{df_vd.shape[0]}")
            dyn_parts.append(df_vd[["TCCBH", "SYBW", "FBSJ"]])
    if USE_TRAIN_XLSX:
        df_tr = read_train_xlsx_dynamic(TRAIN_DIR, TRAIN_XLSX_GLOB)
        if not df_tr.empty:
            df_tr["TCCBH"] = df_tr["TCCBH"].astype(str)
            df_tr = df_tr[df_tr["TCCBH"].isin(target_ids)]
            print(f"训练集动态中属于目标场库的记录：{df_tr.shape[0]}")
            dyn_parts.append(df_tr[["TCCBH", "SYBW", "FBSJ"]])

    if len(dyn_parts) == 0:
        print("没有可用历史泊车记录，无法做画像。")
        return

    df_dyn = pd.concat(dyn_parts, ignore_index=True)
    # 同一停车场同一发布时间只留一条，避免清洗表与训练集重叠重复计权
    df_dyn = df_dyn.drop_duplicates(subset=["TCCBH", "FBSJ"], keep="last")
    print(f"去重后历史动态记录：{df_dyn.shape[0]}")

    # ---------- 3. 聚合成小时利用率 ----------
    print("\n3. 计算每个停车场每小时平均利用率")
    df_hour = to_hourly_util(df_dyn, df_base)
    df_hour = add_calendar_cols(df_hour, "日期小时")
    print(f"小时样本行数：{df_hour.shape[0]}")
    print(f"覆盖停车场数：{df_hour['TCCBH'].nunique()} / {len(target_ids)}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df_hour.to_csv(OUT_HOUR_UTIL, index=False, encoding=CSV_ENCODING)
    print(f"小时利用率已保存：{OUT_HOUR_UTIL}")

    # ---------- 4. 多层画像表 ----------
    print("\n4. 按「停车场 × 星期几 × 小时」等层级计算画像均值")
    val = "每小时平均车位利用率"
    p1 = mean_profile(df_hour, ["TCCBH", "星期几序号", "小时"], val, "util")
    p2 = mean_profile(df_hour, ["TCCBH", "是否工作日", "小时"], val, "util")
    p3 = mean_profile(df_hour, ["TCCBH", "小时"], val, "util")
    # 区县、全市画像需要带上 SZQX
    df_hour_d = df_hour.merge(df_base[["TCCBH", "SZQX"]], on="TCCBH", how="left")
    p4 = mean_profile(df_hour_d, ["SZQX", "星期几序号", "小时"], val, "util")
    p5 = mean_profile(df_hour_d, ["SZQX", "小时"], val, "util")
    p6 = mean_profile(df_hour_d, ["小时"], val, "util")

    # 主画像表落盘（第 1 层，未回退），给 5.2 当特征
    profile_save = p1.merge(df_base[["TCCBH", "TCCMC", "SZQX", "BWZS"]], on="TCCBH", how="left")
    profile_save["星期几"] = profile_save["星期几序号"].map(WEEKDAY_CN)
    profile_save = profile_save.rename(columns={"util": "画像基线利用率", "TCCBH": "停车场ID"})
    profile_save.to_csv(OUT_PROFILE, index=False, encoding=CSV_ENCODING)
    print(f"主画像表（停车场×星期几×小时）已保存：{OUT_PROFILE}")

    # ---------- 5. 预测网格：场库 × 日期 × 0-23 小时，全覆盖 ----------
    print("\n5. 展开预测网格（全覆盖 0-23 点）")
    dates = pd.date_range(PREDICT_START, PREDICT_END, freq="D")
    park_df = df_base[["TCCBH", "TCCMC", "SZQX", "BWZS"]].copy()
    date_df = pd.DataFrame({"日期": dates})
    hour_df = pd.DataFrame({"小时": HOURS_FULL})
    grid = park_df.merge(date_df, how="cross").merge(hour_df, how="cross")
    grid["星期几序号"] = grid["日期"].dt.dayofweek.astype(int)
    grid["是否工作日"] = (grid["星期几序号"] <= 4).astype(int)
    grid["星期几"] = grid["星期几序号"].map(WEEKDAY_CN)
    grid["画像基线利用率"] = pd.NA
    grid["画像来源"] = pd.NA
    print(f"网格规模：{grid.shape[0]} 行 = {park_df.shape[0]} 场 × {len(dates)} 天 × {len(HOURS_FULL)} 小时")

    # ---------- 6. 按回退阶梯填利用率 ----------
    print("\n6. 用画像填网格（缺测时段按配置回退）")
    grid = fill_with_profile(grid, p1, ["TCCBH", "星期几序号", "小时"], "停车场_星期_小时")
    if ENABLE_FALLBACK:
        grid = fill_with_profile(grid, p2, ["TCCBH", "是否工作日", "小时"], "停车场_工作日_小时")
        grid = fill_with_profile(grid, p3, ["TCCBH", "小时"], "停车场_小时")
        grid = fill_with_profile(grid, p4, ["SZQX", "星期几序号", "小时"], "区县_星期_小时")
        grid = fill_with_profile(grid, p5, ["SZQX", "小时"], "区县_小时")
        grid = fill_with_profile(grid, p6, ["小时"], "全市_小时")

    still_na = int(grid["画像基线利用率"].isna().sum())
    if still_na > 0:
        print(f"警告：仍有 {still_na} 行没有画像，利用率填 0")
        grid["画像基线利用率"] = grid["画像基线利用率"].fillna(0)
        grid["画像来源"] = grid["画像来源"].fillna("缺省0")

    if CLIP_UTIL:
        grid["画像基线利用率"] = pd.to_numeric(grid["画像基线利用率"], errors="coerce").clip(0, 1)

    # 占用数 = 利用率 × 总泊位，裁到整数车位
    grid["画像基线占用数"] = (grid["画像基线利用率"] * grid["BWZS"]).round(0).clip(lower=0)
    grid["画像基线占用数"] = grid[["画像基线占用数", "BWZS"]].min(axis=1).astype(int)

    # ---------- 7. 整理列名并保存 ----------
    print("\n7. 保存预测结果")
    out = pd.DataFrame({
        "停车场ID": grid["TCCBH"],
        "停车场名称": grid["TCCMC"],
        "区县": grid["SZQX"],
        "日期": grid["日期"].dt.strftime("%Y-%m-%d"),
        "小时": grid["小时"],
        "星期几": grid["星期几"],
        "画像基线利用率": grid["画像基线利用率"].astype(float).round(6),
        "总泊位": grid["BWZS"].astype(int),
        "画像基线占用数": grid["画像基线占用数"],
        "画像来源": grid["画像来源"],
    })
    out = out.sort_values(["区县", "停车场ID", "日期", "小时"], kind="mergesort")
    out.to_csv(OUT_FORECAST, index=False, encoding=CSV_ENCODING)

    print(f"预测结果已保存：{OUT_FORECAST}")
    print(f"总行数：{out.shape[0]}")
    print("\n画像来源分布（回退用了哪一层）：")
    print(out["画像来源"].value_counts().to_string())
    print("\n预览前 8 行：")
    print(out.head(8).to_string(index=False))
    print("\n==================== 任务5.1 执行完毕 ====================")
    print("请先核对输出表；确认后再做 5.2 主模型。")


if __name__ == "__main__":
    main()
