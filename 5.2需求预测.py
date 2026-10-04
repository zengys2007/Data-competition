# ===================== 导入需要的库 =====================
# pandas：表格读写、特征拼接
import pandas as pd
# numpy：对数、数值裁剪
import numpy as np
# pathlib：跨平台路径
from pathlib import Path

# ===================== 【配置区 / 接口，改这里即可】 =====================
# 本文件是主模型：LightGBM 学习「真实利用率 - 画像基线」的残差。
# 依赖任务 5.1 的中间表与画像预测网格，请先跑 5.1。
# 不用 data 里未过滤的区县 csv。

# -------- 路径（5.1 / 清洗 / POI） --------
OUTPUT_DIR = Path("./output")
# 5.1 小时利用率（清洗动态 + 训练集，已筛有效场库）
HOUR_UTIL_FILE = OUTPUT_DIR / "Hourly_Parking_Utilization_Clean_Train.csv"
# 5.1 全覆盖预测网格（已带画像基线利用率，含回退）
BASELINE_FORECAST_FILE = OUTPUT_DIR / "预测_越城诸暨_20250414-0418_画像基线.csv"
# 2.3 有效停车场基础表
VALID_PARK_BASE = OUTPUT_DIR / "valid_park_base.csv"
# 3.4 POI-停车场关联（1 km 内）
POI_REL_FILE = OUTPUT_DIR / "POI_ParkingLot_Association_Table.csv"
# 3.2 大模型收费标签（没有该文件就跳过，不报错退出）
GLM_TAG_FILE = OUTPUT_DIR / "valid_park_base_wgs84_glm_tag.csv"

OUT_FORECAST = OUTPUT_DIR / "预测_越城诸暨_20250414-0418_主模型.csv"
OUT_VAL_METRIC = OUTPUT_DIR / "主模型_验证指标.csv"

CSV_ENCODING = "utf-8-sig"

# -------- 预测窗口（须与 5.1 一致） --------
TARGET_DISTRICTS = ["越城区", "诸暨市"]
PREDICT_START = "2025-04-14"
PREDICT_END = "2025-04-18"

# -------- 时间验证（按日期切，禁止随机打乱） --------
# 该日期及之后的小时样本只用于看 MAE，不参与第一次训练
VALID_START_DATE = "2025-04-11"
# 验证时是否只统计工作日（预测窗口全是工作日，建议 True）
VAL_WEEKDAY_ONLY = True
# 验证上主模型若不如画像，最终预测仍以画像为主（残差只作对照）
PREFER_BASELINE_IF_VAL_WORSE = True

# -------- 高峰标志（可按赛题改） --------
MORNING_PEAK_HOURS = [7, 8, 9]
EVENING_PEAK_HOURS = [17, 18, 19]
# POI 诱导需求：各类型在不同小时的相对权重（0～1），可按常识微调
POI_HOUR_WEIGHT = {
    "学校": {7: 1.0, 8: 1.0, 9: 0.6, 15: 0.7, 16: 1.0, 17: 1.0, 18: 0.5},
    "医院": {h: 0.8 for h in range(8, 18)},
    "大型超市": {h: 0.9 for h in list(range(10, 22))},
    "小区": {h: 0.9 for h in list(range(0, 8)) + list(range(18, 24))},
}

# -------- LightGBM 超参 --------
LGB_PARAMS = {
    "n_estimators": 400,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "max_depth": 6,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
    "verbosity": -1,
}
EARLY_STOPPING_ROUNDS = 40

# 利用率 / 占用数裁剪
CLIP_UTIL = True
# ===================== 配置区结束 =====================

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
def group_loo_mean(df, keys, value_col):
    """
    留一法均值：该行的画像 = 同组其他行的平均，不含自己。
    若组内只有 1 条，返回 NaN，交给下一层回退。
    这样残差才不是 0，验证也不会把「当天自己」漏进基线。
    """
    cnt = df.groupby(keys)[value_col].transform("count")
    sm = df.groupby(keys)[value_col].transform("sum")
    return np.where(cnt > 1, (sm - df[value_col]) / (cnt - 1), np.nan)


def attach_loo_profile(df_hour, df_base):
    """历史样本用留一法画像，作为主模型的基线特征与残差目标。"""
    val = "每小时平均车位利用率"
    grid = df_hour.copy()
    if "SZQX" not in grid.columns:
        grid = grid.merge(df_base[["TCCBH", "SZQX"]].drop_duplicates("TCCBH"), on="TCCBH", how="left")

    layers = [
        (["TCCBH", "星期几序号", "小时"], "停车场_星期_小时"),
        (["TCCBH", "是否工作日", "小时"], "停车场_工作日_小时"),
        (["TCCBH", "小时"], "停车场_小时"),
        (["SZQX", "星期几序号", "小时"], "区县_星期_小时"),
        (["SZQX", "小时"], "区县_小时"),
        (["小时"], "全市_小时"),
    ]
    grid["画像基线利用率"] = np.nan
    grid["画像来源"] = pd.NA
    for keys, src in layers:
        cand = pd.Series(group_loo_mean(grid, keys, val), index=grid.index)
        miss = grid["画像基线利用率"].isna() & cand.notna()
        grid.loc[miss, "画像基线利用率"] = cand.loc[miss]
        grid.loc[miss, "画像来源"] = src

    still = grid["画像基线利用率"].isna()
    if still.any():
        grid.loc[still, "画像基线利用率"] = grid.loc[still, val].mean() if grid[val].notna().any() else 0.0
        grid.loc[still, "画像来源"] = "缺省均值"
    return grid


def build_poi_features(poi_path, park_ids):
    """
    每个停车场：各类型 POI 个数、距离倒数加权、以及后续按小时算诱导指数用的计数。
    关联键优先 park_TCCBH（1.2 采集编号），与 2.3 有效编号对齐。
    """
    empty_cols = [
        "poi_学校", "poi_医院", "poi_大型超市", "poi_小区",
        "poi_学校_w", "poi_医院_w", "poi_大型超市_w", "poi_小区_w", "poi_总数",
    ]
    if not poi_path.exists():
        print(f"未找到 POI 关联表 {poi_path}，POI 特征全填 0")
        return pd.DataFrame({"TCCBH": list(park_ids), **{c: 0.0 for c in empty_cols}})

    rel = pd.read_csv(poi_path, encoding=CSV_ENCODING, dtype=str)
    id_col = "park_TCCBH" if "park_TCCBH" in rel.columns else "TCCBH"
    rel[id_col] = rel[id_col].astype(str)
    rel = rel[rel[id_col].isin(park_ids)].copy()
    rel["poi_distance_m"] = pd.to_numeric(rel["poi_distance_m"], errors="coerce")

    # 同一停车场同一 POI 只计一次（3.4 表里可能因编号写法重复）
    if "poi_id" in rel.columns:
        rel = rel.drop_duplicates(subset=[id_col, "poi_id"], keep="first")
    else:
        rel = rel.drop_duplicates(subset=[id_col, "poi_name", "poi_type_label"], keep="first")

    rel["w"] = 1.0 / (1.0 + rel["poi_distance_m"].fillna(1000) / 100.0)
    types = ["学校", "医院", "大型超市", "小区"]
    rows = []
    for pid, g in rel.groupby(id_col):
        rec = {"TCCBH": pid}
        for t in types:
            sub = g[g["poi_type_label"] == t]
            rec[f"poi_{t}"] = float(len(sub))
            rec[f"poi_{t}_w"] = float(sub["w"].sum()) if len(sub) else 0.0
        rec["poi_总数"] = float(len(g))
        rows.append(rec)
    poi_df = pd.DataFrame(rows)
    all_ids = pd.DataFrame({"TCCBH": list(park_ids)})
    poi_df = all_ids.merge(poi_df, on="TCCBH", how="left")
    for c in empty_cols:
        if c not in poi_df.columns:
            poi_df[c] = 0.0
        poi_df[c] = poi_df[c].fillna(0.0)
    print(f"POI 特征覆盖停车场：{(poi_df['poi_总数'] > 0).sum()} / {len(poi_df)}")
    return poi_df


def poi_demand_by_hour(row):
    """用 POI 个数 × 该小时业态权重，合成一列诱导需求。"""
    h = int(row["小时"])
    s = 0.0
    for t, wmap in POI_HOUR_WEIGHT.items():
        s += float(row.get(f"poi_{t}", 0) or 0) * float(wmap.get(h, 0.15))
    return s


def add_calendar_flags(df):
    """高峰、正弦小时（让 23 点靠近 0 点）。"""
    out = df.copy()
    out["是否早高峰"] = out["小时"].isin(MORNING_PEAK_HOURS).astype(int)
    out["是否晚高峰"] = out["小时"].isin(EVENING_PEAK_HOURS).astype(int)
    out["小时_sin"] = np.sin(2 * np.pi * out["小时"] / 24.0)
    out["小时_cos"] = np.cos(2 * np.pi * out["小时"] / 24.0)
    return out


def add_lag_features(hist_df, fut_df):
    """
    滞后只用「过去时刻」的真实利用率，不看未来。
    预测日没有真实值，因此 14-18 日的滞后来自 13 日及更早的同场同时段。
    """
    hist = hist_df[["TCCBH", "日期", "小时", "每小时平均车位利用率"]].copy()
    fut = fut_df[["TCCBH", "日期", "小时"]].copy()
    fut["每小时平均车位利用率"] = np.nan
    all_df = pd.concat([hist, fut], ignore_index=True)
    all_df["日期"] = pd.to_datetime(all_df["日期"])
    all_df = all_df.sort_values(["TCCBH", "小时", "日期"], kind="mergesort")

    g = all_df.groupby(["TCCBH", "小时"], sort=False)
    all_df["滞后_同时段上次"] = g["每小时平均车位利用率"].shift(1)
    all_df["滞后_同时段上上次"] = g["每小时平均车位利用率"].shift(2)

    all_df["星期几序号"] = all_df["日期"].dt.dayofweek
    g2 = all_df.groupby(["TCCBH", "星期几序号", "小时"], sort=False)
    all_df["滞后_同星期同时段"] = g2["每小时平均车位利用率"].shift(1)

    lag_cols = ["TCCBH", "日期", "小时", "滞后_同时段上次", "滞后_同时段上上次", "滞后_同星期同时段"]
    return all_df[lag_cols]


def load_glm_tag(path, park_ids):
    """读取 3.2 的高价/平价标签；文件不存在则填「未知」。"""
    if not path.exists():
        print(f"未找到 {path.name}，价格标签填「未知」（可先跑 3.2 再跑本脚本）")
        return pd.DataFrame({"TCCBH": list(park_ids), "price_tag": "未知"})
    tag = pd.read_csv(path, encoding=CSV_ENCODING, dtype=str)
    if "TCCBH" not in tag.columns or "price_tag" not in tag.columns:
        print("收费标签表缺少 TCCBH / price_tag，填「未知」")
        return pd.DataFrame({"TCCBH": list(park_ids), "price_tag": "未知"})
    tag["TCCBH"] = tag["TCCBH"].astype(str)
    tag = tag[["TCCBH", "price_tag"]].drop_duplicates("TCCBH", keep="first")
    tag = pd.DataFrame({"TCCBH": list(park_ids)}).merge(tag, on="TCCBH", how="left")
    tag["price_tag"] = tag["price_tag"].fillna("未知")
    return tag


def make_lgb_or_hist():
    """优先 LightGBM；没装则退回 sklearn 的直方图梯度提升。"""
    try:
        from lightgbm import LGBMRegressor
        return "lightgbm", LGBMRegressor(**LGB_PARAMS)
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingRegressor
        print("未安装 lightgbm，改用 sklearn.HistGradientBoostingRegressor")
        return "sklearn_hist", HistGradientBoostingRegressor(
            max_depth=LGB_PARAMS.get("max_depth", 6),
            learning_rate=LGB_PARAMS.get("learning_rate", 0.05),
            max_iter=LGB_PARAMS.get("n_estimators", 400),
            random_state=LGB_PARAMS.get("random_state", 42),
        )


def encode_cats(train_df, other_df, cat_cols):
    """
    LightGBM 可以直接吃 category；sklearn 版本把类别变成整数编码。
    编码规则只在训练集上定，避免验证/预测泄漏。
    """
    maps = {}
    train_out = train_df.copy()
    other_out = other_df.copy()
    for c in cat_cols:
        uniq = list(train_out[c].astype(str).fillna("未知").unique())
        maps[c] = {v: i for i, v in enumerate(uniq)}
        train_out[c] = train_out[c].astype(str).map(maps[c]).fillna(-1).astype(int)
        other_out[c] = other_out[c].astype(str).map(maps[c]).fillna(-1).astype(int)
    return train_out, other_out, maps


# ===================== 主程序 =====================
def main():
    print("==================== 任务5.2 需求预测（LightGBM 残差主模型）开始 ====================")
    print("请确认已运行 5.1。本脚本读清洗表 + 5.1 输出 + POI 关联，不读脏 csv。\n")

    for p in [HOUR_UTIL_FILE, BASELINE_FORECAST_FILE, VALID_PARK_BASE]:
        if not p.exists():
            print(f"缺少文件：{p}")
            if p == HOUR_UTIL_FILE or p == BASELINE_FORECAST_FILE:
                print("请先运行：python 5.1需求预测.py")
            return

    # ---------- 1. 读 5.1 小时样本、有效场库、5.1 画像网格 ----------
    print("1. 读取 5.1 小时利用率、有效停车场、画像预测网格")
    df_hour = pd.read_csv(HOUR_UTIL_FILE, encoding=CSV_ENCODING, dtype={"TCCBH": str})
    df_hour["日期小时"] = pd.to_datetime(df_hour["日期小时"])
    df_hour["日期"] = df_hour["日期小时"].dt.normalize()
    df_hour["小时"] = df_hour["小时"].astype(int)
    df_hour["星期几序号"] = df_hour["星期几序号"].astype(int)
    df_hour["是否工作日"] = df_hour["是否工作日"].astype(int)

    df_base = pd.read_csv(VALID_PARK_BASE, encoding=CSV_ENCODING, dtype={"TCCBH": str})
    df_base = df_base[df_base["SZQX"].isin(TARGET_DISTRICTS)].copy()
    df_base = df_base.drop_duplicates("TCCBH", keep="first")
    df_base["BWZS"] = pd.to_numeric(df_base["BWZS"], errors="coerce")
    park_ids = set(df_base["TCCBH"].astype(str))
    df_hour = df_hour[df_hour["TCCBH"].isin(park_ids)].copy()

    df_base_fc = pd.read_csv(BASELINE_FORECAST_FILE, encoding=CSV_ENCODING, dtype={"停车场ID": str})
    print(f"历史小时样本：{df_hour.shape[0]}，画像网格：{df_base_fc.shape[0]}")

    # ---------- 2. 静态特征：类型、容量、POI、收费标签 ----------
    print("\n2. 构造停车场静态特征与 POI 特征")
    static = df_base[["TCCBH", "TCCMC", "SZQX", "TCCLX", "BWZS"]].copy()
    static["log总泊位"] = np.log1p(static["BWZS"].clip(lower=0))
    poi_df = build_poi_features(POI_REL_FILE, park_ids)
    tag_df = load_glm_tag(GLM_TAG_FILE, park_ids)
    static = static.merge(poi_df, on="TCCBH", how="left").merge(tag_df, on="TCCBH", how="left")
    static["price_tag"] = static["price_tag"].fillna("未知")
    static["TCCLX"] = static["TCCLX"].fillna("未知").astype(str)

    # ---------- 3. 历史样本贴画像，算残差 ----------
    print("\n3. 给历史样本贴画像基线，目标 = 真实利用率 - 画像")
    df_hour = attach_loo_profile(df_hour, df_base)
    df_hour = df_hour.drop(columns=["SZQX", "BWZS", "TCCMC"], errors="ignore")
    df_hour = df_hour.merge(static, on="TCCBH", how="left")
    df_hour = add_calendar_flags(df_hour)
    df_hour["poi诱导"] = df_hour.apply(poi_demand_by_hour, axis=1)
    df_hour["残差"] = df_hour["每小时平均车位利用率"] - df_hour["画像基线利用率"]

    # ---------- 4. 预测网格（沿用 5.1 已回退的画像） ----------
    print("\n4. 整理 14-18 日预测网格特征")
    fut = df_base_fc.rename(columns={"停车场ID": "TCCBH", "区县": "SZQX", "总泊位": "BWZS"})
    fut["日期"] = pd.to_datetime(fut["日期"])
    fut["小时"] = fut["小时"].astype(int)
    fut["星期几序号"] = fut["日期"].dt.dayofweek.astype(int)
    fut["是否工作日"] = (fut["星期几序号"] <= 4).astype(int)
    # 静态列以基础表为准，避免和网格重复列冲突
    fut = fut.drop(columns=["SZQX", "BWZS", "停车场名称"], errors="ignore")
    fut = fut.merge(static, on="TCCBH", how="left")
    fut = add_calendar_flags(fut)
    fut["poi诱导"] = fut.apply(poi_demand_by_hour, axis=1)

    # ---------- 5. 滞后特征 ----------
    print("\n5. 构造滞后特征（只用历史真实利用率）")
    lags = add_lag_features(df_hour, fut)
    df_hour["日期"] = pd.to_datetime(df_hour["日期"])
    df_hour = df_hour.merge(lags, on=["TCCBH", "日期", "小时"], how="left")
    fut = fut.merge(lags, on=["TCCBH", "日期", "小时"], how="left")
    for c in ["滞后_同时段上次", "滞后_同时段上上次", "滞后_同星期同时段"]:
        df_hour[c] = df_hour[c].fillna(df_hour["画像基线利用率"])
        fut[c] = fut[c].fillna(fut["画像基线利用率"])

    feat_num = [
        "画像基线利用率", "小时", "星期几序号", "是否工作日",
        "是否早高峰", "是否晚高峰", "小时_sin", "小时_cos",
        "BWZS", "log总泊位", "poi诱导",
        "poi_学校", "poi_医院", "poi_大型超市", "poi_小区",
        "poi_学校_w", "poi_医院_w", "poi_大型超市_w", "poi_小区_w", "poi_总数",
        "滞后_同时段上次", "滞后_同时段上上次", "滞后_同星期同时段",
    ]
    feat_cat = ["SZQX", "TCCLX", "price_tag"]
    feat_cols = feat_num + feat_cat

    # ---------- 6. 按日期验证 ----------
    print("\n6. 按日期切分训练 / 验证")
    valid_start = pd.Timestamp(VALID_START_DATE)
    is_val = df_hour["日期"] >= valid_start
    if VAL_WEEKDAY_ONLY:
        val_mask = is_val & (df_hour["是否工作日"] == 1)
    else:
        val_mask = is_val
    train_mask = ~is_val
    df_tr = df_hour.loc[train_mask].copy()
    df_va = df_hour.loc[val_mask].copy()
    print(f"训练样本：{len(df_tr)}，验证样本：{len(df_va)}（验证起点 {VALID_START_DATE}）")

    backend, model = make_lgb_or_hist()
    y_tr = df_tr["残差"].astype(float).values

    def to_lgb_cats(frame, cat_ref=None):
        """类别列转 category；预测集必须沿用训练集的类别清单，否则编码错位。"""
        out = frame.copy()
        for c in feat_cat:
            if cat_ref is None:
                out[c] = out[c].astype("category")
            else:
                out[c] = pd.Categorical(out[c].astype(str), categories=cat_ref[c].cat.categories)
        return out

    if backend == "lightgbm":
        X_tr = to_lgb_cats(df_tr[feat_cols])
        fit_kw = {}
        if len(df_va) > 0:
            X_va = to_lgb_cats(df_va[feat_cols], X_tr)
            y_va = df_va["残差"].astype(float).values
            try:
                from lightgbm import early_stopping, log_evaluation
                callbacks = [early_stopping(EARLY_STOPPING_ROUNDS), log_evaluation(0)]
                fit_kw = {"eval_X": X_va, "eval_y": y_va, "callbacks": callbacks}
            except TypeError:
                fit_kw = {"eval_set": [(X_va, y_va)]}
        model.fit(X_tr, y_tr, **fit_kw)
        if len(df_va) > 0:
            pred_res = model.predict(X_va)
            pred_util = np.clip(
                df_va["画像基线利用率"].values + pred_res, 0, 1
            ) if CLIP_UTIL else df_va["画像基线利用率"].values + pred_res
            mae_model = float(np.mean(np.abs(pred_util - df_va["每小时平均车位利用率"].values)))
            mae_base = float(np.mean(np.abs(
                df_va["画像基线利用率"].values - df_va["每小时平均车位利用率"].values
            )))
        else:
            mae_model = mae_base = np.nan
            print("验证集为空，跳过验证指标")
    else:
        X_tr, X_va_enc, _ = encode_cats(df_tr[feat_cols], df_va[feat_cols] if len(df_va) else df_tr[feat_cols], feat_cat)
        model.fit(X_tr[feat_cols].values, y_tr)
        if len(df_va) > 0:
            pred_res = model.predict(X_va_enc[feat_cols].values)
            pred_util = np.clip(df_va["画像基线利用率"].values + pred_res, 0, 1)
            mae_model = float(np.mean(np.abs(pred_util - df_va["每小时平均车位利用率"].values)))
            mae_base = float(np.mean(np.abs(
                df_va["画像基线利用率"].values - df_va["每小时平均车位利用率"].values
            )))
        else:
            mae_model = mae_base = np.nan

    print(f"\n验证 MAE 利用率 | 画像基线：{mae_base:.6f} | 主模型：{mae_model:.6f}")
    metric_df = pd.DataFrame([{
        "验证起点": VALID_START_DATE,
        "验证只含工作日": VAL_WEEKDAY_ONLY,
        "训练样本数": len(df_tr),
        "验证样本数": len(df_va),
        "MAE_画像基线": mae_base,
        "MAE_主模型": mae_model,
        "后端": backend,
    }])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    metric_df.to_csv(OUT_VAL_METRIC, index=False, encoding=CSV_ENCODING)
    print(f"验证指标已保存：{OUT_VAL_METRIC}")

    # ---------- 7. 预测 14-18 日 ----------
    print("\n7. 预测 2025-04-14～18")
    use_baseline_only = False
    if PREFER_BASELINE_IF_VAL_WORSE and pd.notna(mae_model) and pd.notna(mae_base):
        if mae_model >= mae_base:
            use_baseline_only = True
            print("验证上主模型未超过画像，最终主模型列与画像基线相同（避免过拟合乱调）。")

    if use_baseline_only:
        fut_res = np.zeros(len(fut), dtype=float)
    elif backend == "lightgbm":
        X_fut = to_lgb_cats(fut[feat_cols], X_tr)
        fut_res = model.predict(X_fut)
    else:
        _, X_fut, _ = encode_cats(df_tr[feat_cols], fut[feat_cols], feat_cat)
        fut_res = model.predict(X_fut[feat_cols].values)

    fut["主模型利用率"] = fut["画像基线利用率"].astype(float) + fut_res
    if CLIP_UTIL:
        fut["主模型利用率"] = fut["主模型利用率"].clip(0, 1)
    fut["主模型占用数"] = (fut["主模型利用率"] * fut["BWZS"]).round(0).clip(lower=0)
    fut["主模型占用数"] = fut[["主模型占用数", "BWZS"]].min(axis=1).astype(int)

    out = pd.DataFrame({
        "停车场ID": fut["TCCBH"],
        "停车场名称": fut["TCCMC"],
        "区县": fut["SZQX"],
        "日期": pd.to_datetime(fut["日期"]).dt.strftime("%Y-%m-%d"),
        "小时": fut["小时"],
        "星期几": fut["星期几序号"].map(WEEKDAY_CN),
        "画像基线利用率": fut["画像基线利用率"].astype(float).round(6),
        "主模型利用率": fut["主模型利用率"].astype(float).round(6),
        "总泊位": fut["BWZS"].astype(int),
        "画像基线占用数": np.minimum(
            (fut["画像基线利用率"].astype(float) * fut["BWZS"]).round(0).clip(lower=0),
            fut["BWZS"],
        ).astype(int),
        "主模型占用数": fut["主模型占用数"],
        "画像来源": fut["画像来源"] if "画像来源" in fut.columns else "",
    })
    out = out.sort_values(["区县", "停车场ID", "日期", "小时"], kind="mergesort")
    out.to_csv(OUT_FORECAST, index=False, encoding=CSV_ENCODING)

    print(f"主模型预测已保存：{OUT_FORECAST}")
    print(f"总行数：{out.shape[0]}")
    print("\n预览前 8 行：")
    print(out.head(8).to_string(index=False))
    print("\n==================== 任务5.2 执行完毕 ====================")


if __name__ == "__main__":
    main()
