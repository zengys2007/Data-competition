# ===================== 导入需要的库 =====================
# pandas：读取 5.2 预测表、按区县/小时聚合
import pandas as pd
# pathlib：跨平台路径
from pathlib import Path
# pyecharts：交互折线图（与任务 4.2 同一套）
from pyecharts import options as opts
from pyecharts.charts import Line, Scatter, Page
from pyecharts.globals import ThemeType, CurrentConfig

# 国内 CDN，避免默认 js 地址加载失败
CurrentConfig.ONLINE_HOST = "https://cdn.bootcdn.net/ajax/libs/echarts/5.4.3/"

# ===================== 【配置区 / 接口，改这里即可】 =====================
# 本文件只画图，不训练。数据来自 5.2 对 2025-04-14～18 的预测。

OUTPUT_DIR = Path("./output")
# 5.2 主模型预测（含画像列；窗口必须是 14-18 日）
INPUT_FORECAST = OUTPUT_DIR / "预测_越城诸暨_20250414-0418_主模型.csv"
# 5.1 小时真实利用率（清洗动态 + 训练集），用于拟合对照散点
HOUR_UTIL_FILE = OUTPUT_DIR / "Hourly_Parking_Utilization_Clean_Train.csv"
VALID_PARK_BASE = OUTPUT_DIR / "valid_park_base.csv"
OUT_HTML = OUTPUT_DIR / "预测_越城诸暨_20250414-0418_折线图.html"

CSV_ENCODING = "utf-8-sig"

# 预测窗口：只画这 5 天（与 5.2 一致）；14-18 日没有真值，拟合图上只画预测线
PREDICT_START = "2025-04-14"
PREDICT_END = "2025-04-18"
TARGET_DISTRICTS = ["越城区", "诸暨市"]
# 拟合对照用的历史窗口（有真实点）；默认训练集工作日那一周，不含 3 月碎快照以免横轴过稀
FIT_HIST_START = "2025-04-07"
FIT_HIST_END = "2025-04-13"

# True：同一张图上再画一条画像基线（当前若与主模型相同会重叠，方便以后对照）
SHOW_BASELINE_SERIES = True
# ===================== 配置区结束 =====================


def make_line(title, subtitle, x_data, series_list, y_name, y_min=None, y_max=None,
              x_name="时间", x_rotate=30, x_interval=5):
    """
    生成一张折线图。
    series_list：[(系列名, y值列表, 是否虚线), ...]
    """
    line = Line(init_opts=opts.InitOpts(width="1400px", height="520px", theme=ThemeType.LIGHT))
    line.add_xaxis(xaxis_data=x_data)
    for name, y_vals, dashed in series_list:
        line.add_yaxis(
            series_name=name,
            y_axis=y_vals,
            symbol="circle",
            symbol_size=5,
            is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(type_="dashed" if dashed else "solid", width=2),
            label_opts=opts.LabelOpts(is_show=False),
        )
    yaxis_kw = dict(
        name=y_name,
        name_location="middle",
        name_gap=50,
    )
    if y_min is not None:
        yaxis_kw["min_"] = y_min
    if y_max is not None:
        yaxis_kw["max_"] = y_max
    line.set_global_opts(
        title_opts=opts.TitleOpts(title=title, subtitle=subtitle),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        legend_opts=opts.LegendOpts(pos_top="8%"),
        xaxis_opts=opts.AxisOpts(
            name=x_name,
            name_location="middle",
            name_gap=30,
            boundary_gap=False,
            axislabel_opts=opts.LabelOpts(rotate=x_rotate, interval=x_interval),
        ),
        yaxis_opts=opts.AxisOpts(**yaxis_kw),
        toolbox_opts=opts.ToolboxOpts(is_show=True),
        datazoom_opts=[opts.DataZoomOpts(type_="slider", orient="horizontal")],
    )
    return line


def mean_profile(df, keys, value_col, out_col):
    """与 5.1 相同：按键求平均，得到画像查找表。"""
    g = df.groupby(keys, as_index=False)[value_col].mean()
    return g.rename(columns={value_col: out_col})


def fill_with_profile(grid, profile, keys, src_name):
    """只填充仍为空的画像利用率。"""
    tmp = profile.copy()
    util_col = [c for c in tmp.columns if c not in keys][0]
    tmp = tmp.rename(columns={util_col: "_fill_util"})
    merged = grid.merge(tmp, on=keys, how="left")
    miss = merged["拟合利用率"].isna() & merged["_fill_util"].notna()
    merged.loc[miss, "拟合利用率"] = merged.loc[miss, "_fill_util"]
    merged.loc[miss, "画像来源"] = src_name
    return merged.drop(columns=["_fill_util"])


def attach_insample_profile(df_hour, df_base):
    """
    历史样本上的「预测函数」：5.1 同款回退画像（含自己，即样本内拟合曲线）。
    用来和真实点对比拟合效果；不是 14-18 的外推值。
    """
    val = "每小时平均车位利用率"
    p1 = mean_profile(df_hour, ["TCCBH", "星期几序号", "小时"], val, "util")
    p2 = mean_profile(df_hour, ["TCCBH", "是否工作日", "小时"], val, "util")
    p3 = mean_profile(df_hour, ["TCCBH", "小时"], val, "util")
    df_d = df_hour.merge(df_base[["TCCBH", "SZQX"]].drop_duplicates("TCCBH"), on="TCCBH", how="left")
    p4 = mean_profile(df_d, ["SZQX", "星期几序号", "小时"], val, "util")
    p5 = mean_profile(df_d, ["SZQX", "小时"], val, "util")
    p6 = mean_profile(df_d, ["小时"], val, "util")

    grid = df_hour.copy()
    if "SZQX" not in grid.columns:
        grid = grid.merge(df_base[["TCCBH", "SZQX"]].drop_duplicates("TCCBH"), on="TCCBH", how="left")
    grid["拟合利用率"] = pd.NA
    grid["画像来源"] = pd.NA
    grid = fill_with_profile(grid, p1, ["TCCBH", "星期几序号", "小时"], "停车场_星期_小时")
    grid = fill_with_profile(grid, p2, ["TCCBH", "是否工作日", "小时"], "停车场_工作日_小时")
    grid = fill_with_profile(grid, p3, ["TCCBH", "小时"], "停车场_小时")
    grid = fill_with_profile(grid, p4, ["SZQX", "星期几序号", "小时"], "区县_星期_小时")
    grid = fill_with_profile(grid, p5, ["SZQX", "小时"], "区县_小时")
    grid = fill_with_profile(grid, p6, ["小时"], "全市_小时")
    grid["拟合利用率"] = pd.to_numeric(grid["拟合利用率"], errors="coerce").fillna(0)
    return grid


def make_fit_overlay(x_data, y_line, y_points, title, subtitle):
    """
    同一坐标系：折线 = 预测函数（场均拟合/外推），散点 = 真实场均利用率。
    没有真值的时刻（14-18 日）散点为 None，echarts 会跳过。
    """
    line = Line(init_opts=opts.InitOpts(width="1400px", height="560px", theme=ThemeType.LIGHT))
    line.add_xaxis(xaxis_data=x_data)
    line.add_yaxis(
        series_name="预测函数（拟合/外推）",
        y_axis=y_line,
        symbol="none",
        is_smooth=True,
        linestyle_opts=opts.LineStyleOpts(width=2.5, type_="solid"),
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color="#1f77b4"),
    )
    line.set_global_opts(
        title_opts=opts.TitleOpts(title=title, subtitle=subtitle),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        legend_opts=opts.LegendOpts(pos_top="8%"),
        xaxis_opts=opts.AxisOpts(
            name="时间",
            name_location="middle",
            name_gap=32,
            boundary_gap=False,
            axislabel_opts=opts.LabelOpts(rotate=30, interval=3),
        ),
        yaxis_opts=opts.AxisOpts(
            name="平均利用率",
            name_location="middle",
            name_gap=50,
            min_=0,
            max_=1,
        ),
        toolbox_opts=opts.ToolboxOpts(is_show=True),
        datazoom_opts=[opts.DataZoomOpts(type_="slider", orient="horizontal")],
    )
    scatter = Scatter()
    scatter.add_xaxis(x_data)
    scatter.add_yaxis(
        series_name="真实利用率（场均）",
        y_axis=y_points,
        symbol_size=9,
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color="#d62728"),
    )
    scatter.set_series_opts(
        tooltip_opts=opts.TooltipOpts(formatter="{b}<br/>真实点：{c}")
    )
    return line.overlap(scatter)


def main():
    print("==================== 任务5.3 预测需求折线图（14-18日）开始 ====================")
    print("说明：只可视化 5.2 的 2025-04-14～18 预测，不读脏 csv。\n")

    if not INPUT_FORECAST.exists():
        print(f"缺少文件：{INPUT_FORECAST}")
        print("请先运行：python 5.1需求预测.py  以及  python 5.2需求预测.py")
        return

    # ---------- 1. 读取并严格筛 14-18 日 ----------
    print("1. 读取 5.2 预测表，只保留 2025-04-14～18")
    df = pd.read_csv(INPUT_FORECAST, encoding=CSV_ENCODING, dtype={"停车场ID": str})
    print(f"原始行数：{df.shape[0]}，字段：{df.columns.tolist()}")

    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    start = pd.Timestamp(PREDICT_START)
    end = pd.Timestamp(PREDICT_END)
    df = df[(df["日期"] >= start) & (df["日期"] <= end)].copy()
    if "区县" in df.columns:
        df = df[df["区县"].isin(TARGET_DISTRICTS)].copy()
    df["小时"] = pd.to_numeric(df["小时"], errors="coerce").astype(int)
    df["主模型利用率"] = pd.to_numeric(df["主模型利用率"], errors="coerce")
    df["主模型占用数"] = pd.to_numeric(df["主模型占用数"], errors="coerce")
    if "画像基线利用率" in df.columns:
        df["画像基线利用率"] = pd.to_numeric(df["画像基线利用率"], errors="coerce")
    if "画像基线占用数" in df.columns:
        df["画像基线占用数"] = pd.to_numeric(df["画像基线占用数"], errors="coerce")

    df = df.dropna(subset=["日期", "小时", "主模型利用率"])
    df["时刻"] = df["日期"] + pd.to_timedelta(df["小时"], unit="h")
    print(f"窗口内记录：{df.shape[0]}")
    print(f"日期：{sorted(df['日期'].dt.strftime('%Y-%m-%d').unique().tolist())}")
    print(df["区县"].value_counts().to_string() if "区县" in df.columns else "")

    if df.empty:
        print("筛选后没有数据，请检查 5.2 是否已生成 14-18 日预测。")
        return

    # ---------- 2. 全市 + 分县：连续 5 天 × 24 小时 ----------
    print("\n2. 聚合全市与分县时段均值 / 占用合计")
    x_time = (
        df[["时刻"]].drop_duplicates().sort_values("时刻")["时刻"]
        .dt.strftime("%m-%d %H时").tolist()
    )

    def series_by_time(sub, util_col, occ_col):
        g = sub.groupby("时刻", as_index=False).agg(
            利用率=(util_col, "mean"),
            占用合计=(occ_col, "sum"),
        ).sort_values("时刻")
        # 与全市时间轴对齐，缺时刻填 None
        g = pd.DataFrame({"时刻标签": x_time}).merge(
            pd.DataFrame({
                "时刻标签": g["时刻"].dt.strftime("%m-%d %H时"),
                "利用率": g["利用率"].round(4),
                "占用合计": g["占用合计"].round(0),
            }),
            on="时刻标签",
            how="left",
        )
        return g["利用率"].tolist(), g["占用合计"].tolist()

    util_all, occ_all = series_by_time(df, "主模型利用率", "主模型占用数")
    util_series = [("两区平均利用率（主模型）", util_all, False)]
    occ_series = [("两区占用合计（主模型）", occ_all, False)]

    if SHOW_BASELINE_SERIES and "画像基线利用率" in df.columns:
        util_b, occ_b = series_by_time(df, "画像基线利用率", "画像基线占用数")
        util_series.append(("两区平均利用率（画像）", util_b, True))
        occ_series.append(("两区占用合计（画像）", occ_b, True))

    for dist in TARGET_DISTRICTS:
        sub = df[df["区县"] == dist]
        if sub.empty:
            continue
        u, o = series_by_time(sub, "主模型利用率", "主模型占用数")
        util_series.append((f"{dist}平均利用率", u, False))
        occ_series.append((f"{dist}占用合计", o, False))

    chart_util = make_line(
        title="越城·诸暨 停车需求预测（利用率）",
        subtitle="预测窗口：2025-04-14（一）至 2025-04-18（五），0–23 点全覆盖；Y 轴为各场平均利用率",
        x_data=x_time,
        series_list=util_series,
        y_name="平均利用率",
        y_min=0,
        y_max=1,
    )
    chart_occ = make_line(
        title="越城·诸暨 停车需求预测（占用车位数）",
        subtitle="预测窗口：2025-04-14 至 2025-04-18；Y 轴为各场预测占用数之和（需求量）",
        x_data=x_time,
        series_list=occ_series,
        y_name="占用车位合计",
        y_min=0,
        y_max=None,
    )

    # ---------- 3. 按天对比：X=0-23，五天各一条线 ----------
    print("\n3. 按自然日拆成 5 条线，对比每天 24 小时形态")
    hours = list(range(0, 24))
    x_hour = [f"{h:02d}时" for h in hours]
    day_series = []
    dates = sorted(df["日期"].unique())
    for d in dates:
        day = pd.Timestamp(d)
        label = day.strftime("%m-%d") + " " + {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}[day.dayofweek]
        sub = df[df["日期"] == day]
        g = sub.groupby("小时")["主模型利用率"].mean().reindex(hours)
        day_series.append((label, g.round(4).tolist(), False))

    chart_day = make_line(
        title="预测窗口内各日 24 小时利用率对比",
        subtitle="2025-04-14～18 每天一条线，便于看工作日高峰是否一致",
        x_data=x_hour,
        series_list=day_series,
        y_name="平均利用率",
        y_min=0,
        y_max=1,
        x_name="小时",
        x_rotate=0,
        x_interval=0,
    )

    # ---------- 4. 拟合效果：预测函数折线 + 历史真实散点 ----------
    print("\n4. 拟合对照：历史真实点叠在预测函数上（14-18 日无真值，只有折线）")
    chart_fit = None
    if not HOUR_UTIL_FILE.exists() or not VALID_PARK_BASE.exists():
        print("缺少小时利用率或有效场库表，跳过拟合对照图。请先跑 5.1。")
    else:
        df_base = pd.read_csv(VALID_PARK_BASE, encoding=CSV_ENCODING, dtype={"TCCBH": str})
        df_base = df_base[df_base["SZQX"].isin(TARGET_DISTRICTS)].drop_duplicates("TCCBH")
        park_ids = set(df_base["TCCBH"].astype(str))

        hist = pd.read_csv(HOUR_UTIL_FILE, encoding=CSV_ENCODING, dtype={"TCCBH": str})
        hist = hist[hist["TCCBH"].isin(park_ids)].copy()
        hist["日期小时"] = pd.to_datetime(hist["日期小时"])
        hist["日期"] = hist["日期小时"].dt.normalize()
        hist["小时"] = hist["小时"].astype(int)
        hist["星期几序号"] = hist["星期几序号"].astype(int)
        hist["是否工作日"] = hist["是否工作日"].astype(int)
        hist_start = pd.Timestamp(FIT_HIST_START)
        hist_end = pd.Timestamp(FIT_HIST_END)
        hist = hist[(hist["日期"] >= hist_start) & (hist["日期"] <= hist_end)].copy()
        hist = attach_insample_profile(hist, df_base)

        hist_agg = hist.groupby("日期小时", as_index=False).agg(
            真实=("每小时平均车位利用率", "mean"),
            拟合=("拟合利用率", "mean"),
        )
        fut_agg = df.groupby("时刻", as_index=False).agg(拟合=("主模型利用率", "mean"))
        fut_agg = fut_agg.rename(columns={"时刻": "日期小时"})
        fut_agg["真实"] = pd.NA

        both = pd.concat(
            [
                hist_agg[["日期小时", "拟合", "真实"]],
                fut_agg[["日期小时", "拟合", "真实"]],
            ],
            ignore_index=True,
        )
        both["日期小时"] = pd.to_datetime(both["日期小时"])
        both = both.sort_values("日期小时").drop_duplicates("日期小时", keep="first")
        x_fit = both["日期小时"].dt.strftime("%m-%d %H时").tolist()
        y_fit_line = both["拟合"].astype(float).round(4).tolist()
        y_fit_pts = [
            None if pd.isna(v) else round(float(v), 4) for v in both["真实"].tolist()
        ]
        n_pts = sum(v is not None for v in y_fit_pts)
        print(f"拟合横轴时刻数：{len(x_fit)}，其中带真实点：{n_pts}")

        chart_fit = make_fit_overlay(
            x_data=x_fit,
            y_line=y_fit_line,
            y_points=y_fit_pts,
            title="拟合效果：预测函数 vs 真实利用率",
            subtitle=(
                f"红点：{FIT_HIST_START}～{FIT_HIST_END} 两区场均真实值；"
                "蓝线：同期样本内画像拟合，以及 2025-04-14～18 主模型外推（无红点）"
            ),
        )

    # ---------- 5. 合成一页 HTML ----------
    print("\n5. 写入 HTML")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    page = Page(page_title="越城诸暨停车需求预测折线图 2025-04-14至18")
    charts = [chart_util, chart_occ, chart_day]
    if chart_fit is not None:
        charts.append(chart_fit)
    page.add(*charts)
    page.render(str(OUT_HTML))
    print(f"折线图已保存：{OUT_HTML}")
    print("浏览器打开：预测利用率 / 占用 / 分日对比 / 拟合对照（线+真实点）。")
    print("\n==================== 任务5.3 执行完毕 ====================")


if __name__ == "__main__":
    main()
