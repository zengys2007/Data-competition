# ====================== 导入需要使用的库 ======================
# pandas：python数据分析库，专门用来读取csv/xlsx表格文件、处理表格数据
import pandas as pd
# os库用来操作电脑文件、文件夹路径，获取文件夹里面所有文件名
import os

# ====================== 配置参数 ======================
# data文件夹路径，代表存放所有csv和xlsx数据的文件夹
data_folder = "./data"

# 定义csv文件名列表，和赛题10张csv数据表一一对应
csv_file_list = [
    "上虞区智慧停车综合系统-上虞区停车场动态停泊信息.csv",
    "上虞区智慧停车综合系统-上虞区停车场基础信息.csv",
    "诸暨市停车场动态停泊信息.csv",
    "诸暨市停车场基础信息.csv",
    "越城区停车诱导系统-停车场基础信息.csv",
    "越城区停车诱导系统-停车场动态停泊信息.csv",
    "新昌县停车场动态停泊信息.csv",
    "新昌县停车场基础信息.csv",
    "浙里畅行-I出行-停车场动态停泊信息.csv",
    "浙里畅行-I出行-停车场基础信息.csv"
]

# 定义xlsx训练集文件名列表（data文件夹里额外存在的2个xlsx文件）
xlsx_file_list = [
    "训练集-越城-停车场-20250413.xlsx",
    "训练集-诸暨-停车场-20250413.xlsx"
]

# 创建字典，用来存储【文件名：读取到的DataFrame表格对象】
data_dict = {}

# ====================== 工具函数1：读取csv文件 ======================
def read_csv_file(file_path):
    """
    读取csv文件，处理中文乱码
    :param file_path: csv完整路径
    :return: DataFrame表格对象；读取失败返回None
    """
    try:
        # pd.read_csv()读取csv，encoding='utf-8-sig'解决中文BOM乱码
        df = pd.read_csv(file_path, encoding="utf-8-sig")
        return df
    except Exception as e:
        print(f"【读取失败】{os.path.basename(file_path)}，错误信息：{str(e)}")
        return None

# ====================== 工具函数2：读取xlsx训练集文件 ======================
def read_xlsx_train_file(file_path):
    """
    读取xlsx训练集文件（每个xlsx有2个sheet：动态泊车记录sheet + 停车场信息sheet）
    特殊处理：
      1. 第2行是英文列名别名行（estarID,TCCBH,TCCMC...），属于脏数据，需要剔除
      2. 分别读取2个sheet，分别存储，sheet名加入字典key方便区分
    :param file_path: xlsx完整路径
    :return: 无，直接写入全局data_dict
    """
    file_name = os.path.basename(file_path)
    try:
        # pd.ExcelFile：打开xlsx文件，读取所有sheet名
        excel = pd.ExcelFile(file_path)

        print(f"\n 读取xlsx文件：{file_name}，共 {len(excel.sheet_names)} 个sheet")

        # 遍历这个xlsx里每一个sheet
        for sheet_name in excel.sheet_names:
            # 读取当前sheet，dtype=str全部当字符串读，避免编号被转成科学计数法
            df = pd.read_excel(file_path, sheet_name=sheet_name, dtype=str, header=0)

            # 关键：剔除第2行的英文列名别名行
            # 当"停车场编号"这一列的值恰好等于"TCCBH"时，说明这一行是别名行，删除
            if "停车场编号" in df.columns:
                df = df[df["停车场编号"] != "TCCBH"]

            # 字典key用「xlsx文件名_sheet名」区分，例如：
            # 训练集-越城_动态停泊历史信息 / 训练集-越城_停车场基本信息
            dict_key = f"{file_name} @ {sheet_name}"
            data_dict[dict_key] = df

            print(f"  —— sheet [{sheet_name}]：读取记录数 {df.shape[0]} 条，字段数 {df.shape[1]} 列")

    except Exception as e:
        print(f"【读取失败】{file_name}，错误信息：{str(e)}")

# ====================== 主程序入口 ======================
def main():
    print("=" * 80)
    print("任务1.1 数据采集：读取data文件夹下全部csv + xlsx训练集")
    print("=" * 80)

    # --------第1步：循环读取全部csv文件--------
    print("\n--------------- 第一部分：读取10张csv数据表 ---------------")
    for filename in csv_file_list:
        # os.path.join：拼接文件夹路径+文件名，得到完整文件路径
        file_full_path = os.path.join(data_folder, filename)

        # 判断文件是否存在，防止文件名写错、文件缺失报错
        if not os.path.exists(file_full_path):
            print(f"【警告】文件不存在：{filename}")
            continue  # 跳过本次循环，处理下一个文件

        # 调用工具函数读取csv
        df = read_csv_file(file_full_path)
        if df is None:
            continue  # 读取失败跳过

        # 把读取到的表格存入字典
        data_dict[filename] = df

        # df.shape返回元组(行数,列数)；df.shape[0]=记录行数(不含表头)
        row_count = df.shape[0]
        col_count = df.shape[1]

        print("-" * 80)
        print(f"数据表名称：{filename}")
        print(f"读取记录行数(有效数据)：{row_count} 条")
        print(f"数据表字段列数：{col_count} 列")

    # --------第2步：循环读取2个xlsx训练集文件--------
    print("\n--------------- 第二部分：读取2个xlsx训练集文件 ---------------")
    for filename in xlsx_file_list:
        file_full_path = os.path.join(data_folder, filename)

        if not os.path.exists(file_full_path):
            print(f"【警告】文件不存在：{filename}")
            continue

        # 调用工具函数读取xlsx（内部处理2个sheet + 剔除别名行）
        read_xlsx_train_file(file_full_path)

    # --------第3步：全部读取完成后汇总输出--------
    print("\n" + "=" * 80)
    print("全部文件读取完成汇总（任务1.1输出）：")
    print("=" * 80)
    total_row = 0  # 统计总记录数
    for fname, table_df in data_dict.items():
        print(f"  {fname} ：{table_df.shape[0]} 条记录")
        total_row += table_df.shape[0]
    print("-" * 80)
    print(f"累计读取记录总数：{total_row} 条")
    print(f"共读取文件/表数量：{len(data_dict)} 个")

# ====================== 程序入口调用 ======================
if __name__ == "__main__":
    main()