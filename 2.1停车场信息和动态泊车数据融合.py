# =====================导入依赖库=====================
import pandas as pd   # pandas表格处理库，用于读取csv、表格拼接
from pathlib import Path  # Path更优雅处理文件路径，兼容Windows/macOS/Linux

# =====================配置参数区=====================
# data文件夹路径，存放全部原始csv数据
DATA_FOLDER = Path("./data")

# --------停车场基础信息表文件名列表（5个区县）--------
base_file_list = [
    "上虞区智慧停车综合系统-上虞区停车场基础信息.csv",
    "诸暨市停车场基础信息.csv",
    "越城区停车诱导系统-停车场基础信息.csv",
    "新昌县停车场基础信息.csv",
    "浙里畅行-I出行-停车场基础信息.csv"
]

# --------动态停泊（泊车记录表）文件名列表（5个区县）--------
dynamic_file_list = [
    "上虞区智慧停车综合系统-上虞区停车场动态停泊信息.csv",
    "诸暨市停车场动态停泊信息.csv",
    "越城区停车诱导系统-停车场动态停泊信息.csv",
    "新昌县停车场动态停泊信息.csv",
    "浙里畅行-I出行-停车场动态停泊信息.csv"
]

# --------输出融合之后的文件路径--------
OUTPUT_DIR = Path("./output")
OUT_PARK_BASE = OUTPUT_DIR / "park_base_total.csv"    # 融合后【停车场基础信息总表】
OUT_PARK_DYNAMIC = OUTPUT_DIR / "park_dynamic_total.csv" # 融合后【泊车记录总表】

# csv读取编码，处理中文乱码，utf‑8‑sig兼容带BOM的导出csv
CSV_ENCODING = "utf-8-sig"

# =====================函数定义=====================
def concat_csv(file_name_list: list, data_dir: Path, desc: str):
    """
    读取一组csv文件列表，纵向拼接（上下堆叠）所有表格
    :param file_name_list: 需要读取的csv文件名列表
    :param data_dir: csv文件所在文件夹路径
    :param desc: 当前处理的表描述，打印日志使用
    :return: DataFrame，拼接完成后的大表格
    """
    df_list = []  # 空列表，用来存放每一张读取成功的DataFrame

    # 循环遍历每一个文件名
    for filename in file_name_list:
        # 拼接完整文件路径
        full_path = data_dir / filename
        print(f"\n========正在读取{desc}：{filename}========")

        # 判断文件是否存在，防止文件缺失程序直接崩溃
        if not full_path.exists():
            print(f"警告：文件 {filename} 不存在，跳过该文件！")
            continue

        try:
            # 读取csv文件
            df_temp = pd.read_csv(full_path, encoding=CSV_ENCODING)
            print(f"读取成功，记录行数：{df_temp.shape[0]}，字段数：{df_temp.shape[1]}")

            # 将读取成功的表格加入列表，后续统一concat拼接
            df_list.append(df_temp)

        except Exception as e:
            # 捕获读取异常：编码错误、文件损坏等
            print(f"读取文件 {filename} 失败，错误信息：{str(e)}")
            continue

    # 判断列表是否为空，没有任何文件读取成功直接返回空表格
    if len(df_list) == 0:
        print(f"\n没有读取到任何{desc}数据！")
        return pd.DataFrame()

    # pd.concat：纵向拼接
    # axis=0：表示表格的纵向拼接
    # ignore_index=True：拼接完成后重置 0,1,2,3... 行号，否则保留各个原始 csv 自己的行索引，会出现重复索引，后续查询报错
    df_concat = pd.concat(df_list, axis=0, ignore_index=True)
    print(f"\n{desc}全部文件融合完成！")
    print(f"融合后总记录行数：{df_concat.shape[0]} 行，总字段：{df_concat.shape[1]} 列")

    return df_concat

# =====================主程序入口=====================
def main():
    print("====================任务2.1 数据融合开始====================")

    # --------步骤1：融合5张停车场基础信息表--------
    df_park_base_total = concat_csv(base_file_list, DATA_FOLDER, desc="停车场基础信息表")

    # 保存融合后的停车场基础总表到csv文件
    df_park_base_total.to_csv(OUT_PARK_BASE, encoding=CSV_ENCODING, index=False)
    print(f"已输出融合后停车场基础总表：{OUT_PARK_BASE}")

    # --------步骤2：融合5张动态停泊（泊车记录表）--------
    df_park_dynamic_total = concat_csv(dynamic_file_list, DATA_FOLDER, desc="动态停泊泊车记录表")

    # 保存融合后的泊车记录总表
    df_park_dynamic_total.to_csv(OUT_PARK_DYNAMIC, encoding=CSV_ENCODING, index=False)
    print(f"已输出融合后泊车记录总表：{OUT_PARK_DYNAMIC}")

    # --------打印关键统计信息，方便调试查看--------
    print("\n====================任务2.1融合结果汇总====================")
    print(f"【停车场基础信息总表】总记录：{df_park_base_total.shape[0]} 条")
    print(f"【泊车记录总表】总泊车记录：{df_park_dynamic_total.shape[0]} 条")

    # 打印关键字段，确认停车场编号TCCBH存在（后续任务2.2、2.3关联核心主键）
    print("\n停车场基础表字段列表：")
    print(df_park_base_total.columns.tolist())
    print("\n泊车记录表字段列表：")
    print(df_park_dynamic_total.columns.tolist())

    # 简单查看前3行数据，确认数据正常
    print("\n---停车场基础总表预览前3行---")
    print(df_park_base_total.head(3))
    print("\n---泊车记录表预览前3行---")
    print(df_park_dynamic_total.head(3))



if __name__ == "__main__":
    main()