import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -------------------------- 配置项（按需修改）--------------------------
CSV_FILE_PATH = r"D:\recipe\code\traindata\cleaned_data\data - 副本.csv"
REQUEST_DELAY = 2               # 基础请求间隔（秒）
TIMEOUT = 10                    # 超时时间（秒）
MAX_RETRIES = 3                 # 单次URL最大重试次数
RETRY_BACKOFF = 2               # 重试间隔倍数（秒）
# ---------------------------------------------------------------------

# 配置请求重试机制（针对连接层错误）
retry_strategy = Retry(
    total=MAX_RETRIES,
    backoff_factor=RETRY_BACKOFF,
    status_forcelist=[429, 500, 502, 503, 504]
)
adapter = HTTPAdapter(max_retries=retry_strategy)

# 模拟浏览器请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Connection": "keep-alive",
}


def clean_url(url: str) -> str:
    """清理并规范化URL"""
    if pd.isna(url) or str(url).strip() == "":
        return ""
    url = str(url).strip()
    # 移除可能混入的中文标点或乱码（如%EF%BC%8C等）
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def get_web_name(url: str) -> str:
    """
    从网页解析菜名（带内部重试）
    """
    url = clean_url(url)
    if not url:
        return ""

    # 内部重试循环（尝试MAX_RETRIES次）
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with requests.Session() as session:
                session.mount("http://", adapter)
                session.mount("https://", adapter)
                response = session.get(
                    url,
                    headers=HEADERS,
                    timeout=TIMEOUT,
                    allow_redirects=True
                )
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "utf-8"

                soup = BeautifulSoup(response.text, "html.parser")

                # 优先从<title>获取
                title_tag = soup.select_one("title")
                if title_tag:
                    raw_title = title_tag.get_text(strip=True)
                else:
                    # 备选：从h1或og:title获取
                    h1 = soup.select_one("h1")
                    if h1:
                        raw_title = h1.get_text(strip=True)
                    else:
                        og_title = soup.find("meta", property="og:title")
                        if og_title and og_title.get("content"):
                            raw_title = og_title["content"].strip()
                        else:
                            raw_title = ""

                if not raw_title:
                    return "解析失败（无标题）"

                # 截取"的做法"之前部分
                idx = raw_title.find("的做法")
                if idx != -1:
                    dish_name = raw_title[:idx].strip()
                else:
                    dish_name = raw_title.strip()
                return dish_name

        except Exception as e:
            print(f"⚠️  第{attempt}次尝试失败（{url}）：{str(e)}")
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt  # 2,4,6秒
                print(f"   {wait}秒后重试...")
                time.sleep(wait)
            else:
                print(f"❌ 最终处理URL失败 {url}，错误：{str(e)}")
                return "解析失败（网络异常）"
    return "解析失败"


def save_progress(df, csv_path):
    """立即将当前DataFrame写入CSV（覆盖保存）"""
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"💾 已保存进度至 {csv_path}")


def batch_crawl_csv(csv_path: str):
    # 读取CSV（尝试自动检测编码）
    try:
        df = pd.read_csv(csv_path, encoding="gbk")
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding="utf-8")
    print(f"✅ 成功读取CSV，共 {len(df)} 行数据")

    # 检查列数
    if len(df.columns) < 3:
        print("❌ 错误：CSV文件至少需要3列（A列ID，B列URL，C列名称）")
        return

    url_col = df.columns[1]   # B列
    name_col = df.columns[2]  # C列

    for idx, row in df.iterrows():
        # 跳过已有名称的行（断点续跑）
        if not pd.isna(row[name_col]) and str(row[name_col]).strip() not in ("", "解析失败", "解析失败（网络异常）", "解析失败（无标题）"):
            print(f"⏭️  第{idx+2}行已有名称，跳过")
            continue

        url = row[url_col]
        print(f"🔄 正在处理第 {idx+2} 行，URL：{url}")
        name = get_web_name(url)
        df.at[idx, name_col] = name
        print(f"✅ 第{idx+2}行完成，获取到名称：{name}")

        # ★ 立即保存到文件 ★
        save_progress(df, csv_path)

        # 随机延时，防止被封
        delay = REQUEST_DELAY + random.uniform(0, 1)
        time.sleep(delay)

    print(f"\n🎉 全部处理完成！结果已保存到：{csv_path}")


if __name__ == "__main__":
    batch_crawl_csv(CSV_FILE_PATH)