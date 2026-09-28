import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Line
from pyecharts.globals import ThemeType, CurrentConfig

# 更换国内CDN，解决js加载报错
CurrentConfig.ONLINE_HOST = "https://cdn.bootcdn.net/ajax/libs/echarts/5.4.3/"

# =====================配置区=====================
INPUT_CSV = "./output/Hourly_Parking_Utilization_Results.csv"
OUT_HTML = "./output/不同时段车位利用率折线图.html"
CSV_ENCODING = "utf-8-sig"


def main():
    print("====================任务4.2 不同时段车位利用率折线图====================")
    # 1.读取任务3.3输出数据
    df = pd.read_csv(INPUT_CSV, encoding=CSV_ENCODING)
    print(f"原始数据行数：{df.shape[0]}")
    print(f"表格字段：{df.columns.tolist()}")

    # 2.按【小时】分组，计算该时段所有停车场的平均车位利用率
    df_hour_stat = df.groupby("日期小时").agg({
        "每小时平均车位利用率": "mean"
    }).reset_index()

    df_hour_stat.sort_values(by="日期小时", ascending=True, inplace=True)
    print("\n各小时统计结果：")
    print(df_hour_stat)

    # 构造绘图数据
    x_data = df_hour_stat["日期小时"].astype(str).tolist()       # X轴：小时字符串 ["0","1",..."23"]
    y_data = round(df_hour_stat["每小时平均车位利用率"], 3).tolist()

    # 3.构建折线图
    line = (
        Line(init_opts=opts.InitOpts(width="1200px", height="700px", theme=ThemeType.LIGHT))
        .add_xaxis(xaxis_data=x_data)
        .add_yaxis(
            series_name="时段平均车位利用率",
            y_axis=y_data,
            symbol="circle",
            symbol_size=6,
            is_smooth=True,   # 平滑折线
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="绍兴市停车场不同时段车位利用率变化",
                subtitle="X轴：一天24小时，Y轴：平均车位利用率"
            ),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            xaxis_opts=opts.AxisOpts(
                name="小时",
                name_location="middle",
                name_gap=30,
                boundary_gap=False,
                axislabel_opts=opts.LabelOpts(rotate=0)
            ),
            yaxis_opts=opts.AxisOpts(
                name="车位利用率",
                name_location="middle",
                name_gap=45,
                min_=0,
                max_=1.0
            ),
            toolbox_opts=opts.ToolboxOpts(is_show=True),
            datazoom_opts=[opts.DataZoomOpts(type_="slider", orient="horizontal")]
        )
        .set_series_opts(
            label_opts=opts.LabelOpts(is_show=False)
        )
    )

    # 渲染输出
    line.render(OUT_HTML)
    print(f"\n任务4.2执行完成，输出文件：{OUT_HTML}")
    print("\n打开html，可查看24小时车位利用率变化折线；支持缩放、保存图片。")


if __name__ == "__main__":
    main()
