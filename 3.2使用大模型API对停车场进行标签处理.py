# ===================== 导入需要的库 =====================
# pandas：表格数据读写处理
import pandas as pd
# time：用于请求之间延时，防止API限流
import time
# pathlib：用于处理文件路径，跨平台兼容
from pathlib import Path
# os：读取环境变量
import os
# requests：http请求库
import requests
# dotenv：从项目根目录 .env 加载密钥；已有环境变量不会被覆盖
from dotenv import load_dotenv

# ===================== 【配置区，需要你修改】 =====================
# 密钥两种来源都可以，同时配置时环境变量优先：
# 1. 环境变量 ZHIPU_API_KEY
#    当前终端临时生效，关掉终端就失效。
#    PowerShell：
#        $env:ZHIPU_API_KEY = "你的key"
#    CMD：
#        set ZHIPU_API_KEY=你的key
#    写入当前 Windows 用户，之后新开的终端都会带上。设完需要重新打开终端。
#    PowerShell：
#        [System.Environment]::SetEnvironmentVariable("ZHIPU_API_KEY", "你的key", "User")
# 2. 项目根目录 .env 中写一行：ZHIPU_API_KEY=你的key
ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env", override=False)
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "").strip()

# 输入文件：任务2.2融合清洗完成后的停车场总表
INPUT_FILE = Path("./valid_park_base_wgs84.csv")
# 输出文件：新增price_tag价格标签的结果文件
OUTPUT_FILE = Path("./valid_park_base_wgs84_glm_tag.csv")

# 文本编码，中文csv固定用utf-8-sig，避免中文乱码
CSV_ENCODING = "utf-8-sig"
# API请求间隔，单位秒，防止请求过快触发限流
REQUEST_DELAY = 1.2

# ===================== 系统提示词（给GLM模型的规则） =====================
SYSTEM_PROMPT = """
你是停车场收费标签标注助手，严格遵守下面全部规则：
1. 收费标准中同时存在小车、大车价格时，**只提取小型车辆（小车）的收费规则，大车数据直接忽略**。
2. 如果是按次收费：小时单价 = 单次费用 ÷ 单次包含的时长（小时）。
示例：小车5元/次，4小时为一次，小时单价=5/4=1.25元/小时。
3. 判断规则：
   小时单价≥8元  OR  单日封顶费用≥50元 → 输出：高价
   小时单价＜8元  AND  单日封顶费用＜50元 → 输出：平价
4. 如果文本为空、乱码、完全提取不到小车价格信息 → 输出：无法判定

硬性输出约束：
只输出标签文字，**禁止任何解释、标点符号、换行**。
只能输出三个值其中一个：高价 / 平价 / 无法判定
"""

# ===================== 定义函数：调用GLM获取价格标签 =====================
def get_price_tag(sfbz_text: str):
    """
    使用requests调用智谱GLM-4-Flash，解析停车场收费标准文本，返回价格标签
    :param sfbz_text: 表格里【收费标准】字段的原始文本
    :return: str，三选一：高价 / 平价 / 无法判定
    """
    # 判断空值：收费标准为空，直接返回无法判定，跳过API调用节省token
    if pd.isna(sfbz_text):
        return "无法判定"
    text = str(sfbz_text).strip()
    if len(text) == 0:
        return "无法判定"

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "glm-4-flash",
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"停车场收费文本：{text}"}
        ]
    }
    try:
        # post请求调用接口
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        resp_json = resp.json()
        # 取出模型返回的内容，去除前后空格
        res_text = resp_json["choices"][0]["message"]["content"].strip()
        # 控制台打印模型原始返回，方便调试
        print(f"【GLM原始返回】->{res_text}")

        # 合法标签集合，过滤模型乱输出的内容
        allow_tags = {"高价", "平价", "无法判定"}
        if res_text in allow_tags:
            return res_text
        else:
            # 模型输出不在允许列表，标记无法判定
            return "无法判定"

    except Exception as e:
        # 捕获所有异常：网络错误、接口报错、超时等，不中断循环
        print(f"\nAPI调用异常：{str(e)}")
        return "无法判定"

# ===================== 主程序入口 =====================
def main():
    print("====================任务2.3 智谱GLM停车场收费打标签（requests版本，无需zhipuai库） 开始====================")

    if not ZHIPU_API_KEY:
        print("\n未找到 ZHIPU_API_KEY，任选一种方式配置后重新运行：")
        print("1. 设置环境变量 ZHIPU_API_KEY")
        print("2. 在项目根目录 .env 中写入：ZHIPU_API_KEY=你的key")
        print("两种都配置时，使用环境变量里的值。")
        return

    # 判断输入文件是否存在
    if not INPUT_FILE.exists():
        print(f"\n输入文件不存在：{INPUT_FILE}，请先执行任务2.1、2.2完成数据融合！")
        return

    # 读取csv总表
    df = pd.read_csv(INPUT_FILE, encoding=CSV_ENCODING)
    print(f"\n成功读取数据表，总记录数：{df.shape[0]}")

    # 检查收费标准字段SFBZ是否存在
    if "SFBZ" not in df.columns:
        print("\n数据表缺少【收费标准】字段 SFBZ！")
        return

    # 列表用来存放每一行生成的标签
    price_tag_result_list = []
    total_rows = len(df)

    # 遍历表格每一行，逐个调用API
    for idx, row in df.iterrows():
        sfbz_content = row["SFBZ"]
        # 打印当前处理进度，只展示前60个字符，避免控制台刷屏
        print(f"[{idx+1}/{total_rows}] 正在处理收费标准：{str(sfbz_content)[:60]}...")
        # 调用函数获取标签
        tag = get_price_tag(sfbz_content)
        price_tag_result_list.append(tag)
        print(f"    → 标签结果：{tag}")
        # 延时，控制请求频率
        time.sleep(REQUEST_DELAY)

    # 将标签列表新增为表格一列
    df["price_tag"] = price_tag_result_list

    # 统计各类标签数量，输出统计结果，方便写报告
    print("\n----------标签统计结果----------")
    tag_stat = df["price_tag"].value_counts()
    print(tag_stat)

    # 保存输出文件
    df.to_csv(OUTPUT_FILE, encoding=CSV_ENCODING, index=False)
    print(f"\n结果已保存至：{OUTPUT_FILE}")
    print("新增字段 price_tag：停车场价格标签（高价 / 平价 / 无法判定）")



# 程序启动入口
if __name__ == "__main__":
    main()