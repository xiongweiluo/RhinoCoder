"""
data_pipeline/discourse_scraper.py

McNeel 论坛（discourse.mcneel.com）异步采集器。

技术选型：
  - httpx.AsyncClient   异步 HTTP 客户端，统一管理连接池与超时
  - BeautifulSoup4      解析 Discourse 返回的 cooked HTML，提取代码块
  - asyncio.Semaphore   控制最大并发请求数，配合 sleep 实现礼貌限速

限速策略（三层防护，防止 IP 被封禁）：
  ① 请求间隔：每次请求前 sleep BASE_DELAY + 随机抖动（0~JITTER_RANGE 秒）
  ② 并发上限：Semaphore(MAX_CONCURRENT)，同时在途请求不超过 3 个
  ③ 指数退避：遇到 429 时优先读取 Retry-After 响应头；若无，则
              等待 BACKOFF_BASE^attempt 秒（2, 4, 8, 16, 32…），
              并叠加随机抖动防止多 worker 同步重试（"惊群效应"）

输出格式（data/raw_samples.jsonl，每行一个 JSON）：
  {
    "topic_id":    int,    # 主题 ID（唯一标识）
    "title":       str,    # 主题标题（供后续 SFT 指令生成使用）
    "topic_url":   str,    # 主题 URL（溯源链接）
    "post_id":     int,    # 帖子 ID
    "post_number": int,    # 帖子在主题中的楼层序号
    "raw_text":    str,    # 帖子原始 Markdown 文本（供后续生成"指令"时使用）
    "code_blocks": [str]   # 从该帖提取的 Python 代码块列表
  }
"""

import asyncio
import json
import logging
import random
import re
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

# ── 目录配置 ─────────────────────────────────────────────────────────────────
# 输出到项目根目录的 data/ 文件夹，与 .gitignore 中的数据目录规则对应
DATA_DIR = Path(__file__).parent.parent / "data"
RAW_SAMPLES_PATH = DATA_DIR / "raw_samples.jsonl"

# ── Discourse API 配置 ────────────────────────────────────────────────────────
FORUM_BASE = "https://discourse.mcneel.com"
SCRIPTING_CATEGORY_SLUG = "scripting"
SCRIPTING_CATEGORY_ID = 9       # McNeel 论坛 Scripting 分类 ID

# 测试阶段仅抓取 5 页（每页约 30 个主题），验证流水线通路后再扩大到 50+
DEFAULT_MAX_PAGES = 5

# ── 限速参数 ──────────────────────────────────────────────────────────────────
MAX_CONCURRENT = 3              # 最大并发 HTTP 请求数（保守值，防止触发论坛限速）
BASE_DELAY = 0.8                # 每次请求前的基础等待时间（秒）
JITTER_RANGE = 0.5              # 随机抖动范围（秒），均匀分布在 [0, JITTER_RANGE]
MAX_RETRIES = 5                 # 单次请求的最大重试次数
BACKOFF_BASE = 2.0              # 指数退避基数：等待时间 = BACKOFF_BASE^attempt 秒

# ── 过滤条件 ──────────────────────────────────────────────────────────────────
# 只保留帖子中引用了 Rhino 脚本相关命名空间的代码块，过滤掉无关 Python 代码
RHINO_API_KEYWORDS = re.compile(
    r"\b(rhinoscriptsyntax|RhinoCommon|Rhino\.Geometry|Rhino\.DocObjects"
    r"|scriptcontext|ghpythonlib|rs\.\w+|rg\.\w+)\b",
    re.IGNORECASE,
)

# ── 日志配置 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("discourse_scraper")


# ═════════════════════════════════════════════════════════════════════════════
# 网络层：带指数退避的请求封装
# ═════════════════════════════════════════════════════════════════════════════

async def _fetch_json(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
    *,
    max_retries: int = MAX_RETRIES,
) -> Optional[dict]:
    """
    对单个 URL 发起 GET 请求，返回解析后的 JSON dict。

    异常处理策略：
      - HTTP 200：正常返回
      - HTTP 429：读取 Retry-After 头（若有）决定等待时长；否则指数退避
      - HTTP 404/410：资源不存在，直接返回 None，不重试（避免浪费配额）
      - HTTP 5xx / 网络异常：指数退避后重试
      - 超过 max_retries 次后返回 None，由调用方决定如何处理

    Args:
        client:      共享的 httpx.AsyncClient 实例（连接池复用）
        url:         目标 URL
        semaphore:   并发限制信号量
        max_retries: 最大重试次数（默认 MAX_RETRIES=5）

    Returns:
        解析后的响应 JSON dict，或 None（请求最终失败时）
    """
    # Semaphore 在整个请求周期（含重试）内持有，使并发槽位与实际 HTTP 活动对齐
    async with semaphore:
        for attempt in range(max_retries):
            # ── 三层限速的第①层：每次尝试前的礼貌等待 + 随机抖动 ──────────────
            # 抖动设计：即使多个 coroutine 同时解锁 semaphore，抖动也能将它们
            # 的实际请求时刻错开，避免瞬时并发冲击论坛服务器
            jitter = random.uniform(0, JITTER_RANGE)
            await asyncio.sleep(BASE_DELAY + jitter)

            try:
                resp = await client.get(url)

                if resp.status_code == 200:
                    return resp.json()

                elif resp.status_code == 429:
                    # ── 三层限速的第③层：服务器明确拒绝，指数退避 ────────────
                    retry_after_header = resp.headers.get("Retry-After")
                    if retry_after_header:
                        # 优先尊重服务器声明的等待时间
                        wait_s = float(retry_after_header)
                        logger.warning(
                            f"[429] 服务器限速，遵循 Retry-After={wait_s:.0f}s "
                            f"(attempt {attempt + 1}/{max_retries}): {url}"
                        )
                    else:
                        # 无 Retry-After 头时自行计算：2^attempt + 抖动
                        wait_s = (BACKOFF_BASE ** (attempt + 1)) + random.uniform(0, 1)
                        logger.warning(
                            f"[429] 服务器限速，指数退避 {wait_s:.1f}s "
                            f"(attempt {attempt + 1}/{max_retries}): {url}"
                        )
                    await asyncio.sleep(wait_s)
                    # 继续下一次 attempt（不 return）

                elif resp.status_code in (404, 410):
                    # 资源永久不存在，无需重试
                    logger.debug(f"[{resp.status_code}] 资源不存在，跳过: {url}")
                    return None

                else:
                    # 其他错误（5xx 等）：简单指数退避
                    wait_s = BACKOFF_BASE ** attempt
                    logger.warning(
                        f"[{resp.status_code}] 意外状态码，等待 {wait_s:.1f}s 后重试 "
                        f"(attempt {attempt + 1}/{max_retries}): {url}"
                    )
                    await asyncio.sleep(wait_s)

            except httpx.TimeoutException:
                wait_s = BACKOFF_BASE ** attempt + random.uniform(0, 1)
                logger.warning(
                    f"[Timeout] 请求超时，等待 {wait_s:.1f}s 后重试 "
                    f"(attempt {attempt + 1}/{max_retries}): {url}"
                )
                await asyncio.sleep(wait_s)

            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
                wait_s = BACKOFF_BASE ** attempt + random.uniform(0, 1)
                logger.warning(
                    f"[{type(exc).__name__}] 网络错误，等待 {wait_s:.1f}s 后重试 "
                    f"(attempt {attempt + 1}/{max_retries}): {url}"
                )
                await asyncio.sleep(wait_s)

        # 所有重试均已耗尽
        logger.error(f"放弃请求（{max_retries} 次重试后仍失败）: {url}")
        return None


# ═════════════════════════════════════════════════════════════════════════════
# 代码块提取层
# ═════════════════════════════════════════════════════════════════════════════

def _extract_from_cooked_html(cooked_html: str) -> list[str]:
    """
    从 Discourse 返回的 cooked（已渲染）HTML 中提取 Python 代码块。

    Discourse 将 Markdown 围栏代码块渲染为：
      <pre><code class="lang-python">...</code></pre>
    或旧版主题中的：
      <code class="lang-python">...</code>

    使用 BeautifulSoup4 进行稳健解析，避免手写正则误伤嵌套 HTML。
    """
    if not cooked_html:
        return []

    soup = BeautifulSoup(cooked_html, "html.parser")
    blocks: list[str] = []

    # 匹配 class 含 lang-python 或 lang-py 的 <code> 标签（class 可能含多个值）
    for code_tag in soup.find_all("code", class_=re.compile(r"lang-(python|py)$", re.I)):
        text = code_tag.get_text()
        if text.strip():
            blocks.append(text.strip())

    return blocks


def _extract_from_raw_markdown(raw_md: str) -> list[str]:
    """
    从帖子原始 Markdown 中提取 Python 围栏代码块（作为 HTML 解析的补充）。

    Discourse 有时不返回 cooked 字段，或旧帖的 cooked 格式与 class 约定不符，
    此时直接解析原始 Markdown 作为兜底策略。

    匹配模式：
      ```python\n...\n```
      ```py\n...\n```
      （不区分大小写，支持代码块内含三个反引号的边缘情况）
    """
    if not raw_md:
        return []

    # re.DOTALL 使 . 匹配换行符；使用非贪婪 .*? 避免跨代码块匹配
    pattern = re.compile(
        r"```(?:python|py)\s*\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )
    return [m.group(1).strip() for m in pattern.finditer(raw_md) if m.group(1).strip()]


def _is_rhino_related(code: str) -> bool:
    """
    判断代码块是否与 Rhino API 相关（rhinoscriptsyntax / RhinoCommon / GH Python 等）。
    过滤掉纯 Python 通用代码（如字符串处理、数学计算），提高数据集信噪比。
    """
    return bool(RHINO_API_KEYWORDS.search(code))


def _extract_code_blocks(cooked_html: str, raw_md: str) -> list[str]:
    """
    综合 HTML 和 Markdown 两种来源提取 Python 代码块，并过滤非 Rhino 相关代码。

    优先级：cooked HTML（格式最规范）> 原始 Markdown（兜底）
    若 HTML 已提取到代码，不再尝试 Markdown，避免重复。
    """
    blocks = _extract_from_cooked_html(cooked_html)
    if not blocks:
        blocks = _extract_from_raw_markdown(raw_md)

    # 保留与 Rhino API 相关的代码块；纯通用 Python 代码对微调无直接价值
    return [b for b in blocks if _is_rhino_related(b)]


# ═════════════════════════════════════════════════════════════════════════════
# 采集逻辑层
# ═════════════════════════════════════════════════════════════════════════════

async def _fetch_topic_list(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    page: int,
) -> list[dict]:
    """
    获取 Scripting 分类第 page 页的主题列表。

    Discourse 分类 JSON API 端点：
      GET /c/{slug}/{id}.json?page={page}
    返回结构中的 topic_list.topics 数组，每个元素包含 id / title / slug 等字段。

    若该页无主题（API 返回空列表），调用方应停止翻页。
    """
    url = (
        f"{FORUM_BASE}/c/{SCRIPTING_CATEGORY_SLUG}"
        f"/{SCRIPTING_CATEGORY_ID}.json?page={page}"
    )
    logger.info(f"▶ 获取第 {page} 页主题列表 ...")
    data = await _fetch_json(client, url, semaphore)
    if data is None:
        return []

    topics: list[dict] = data.get("topic_list", {}).get("topics", [])
    logger.info(f"  第 {page} 页：{len(topics)} 个主题")
    return topics


async def _fetch_posts_from_topic(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    topic: dict,
) -> list[dict]:
    """
    获取单个主题下的所有帖子，提取 Python 代码块，返回结构化样本列表。

    Discourse 主题帖子 JSON API 端点：
      GET /t/{topic_id}.json
    返回 post_stream.posts 数组，每个帖子包含 cooked（HTML）和 raw（Markdown）字段。

    返回的每个样本格式见模块头部文档。
    若主题内无任何 Rhino 相关 Python 代码，返回空列表。
    """
    topic_id: int = topic["id"]
    title: str = topic.get("title", "")
    slug: str = topic.get("slug", str(topic_id))
    topic_url = f"{FORUM_BASE}/t/{slug}/{topic_id}"

    url = f"{FORUM_BASE}/t/{topic_id}.json"
    data = await _fetch_json(client, url, semaphore)
    if data is None:
        return []

    posts: list[dict] = data.get("post_stream", {}).get("posts", [])
    samples: list[dict] = []

    for post in posts:
        cooked: str = post.get("cooked", "") or ""
        raw_md: str = post.get("raw", "") or ""

        code_blocks = _extract_code_blocks(cooked, raw_md)
        if not code_blocks:
            # 此帖无 Rhino Python 代码，跳过（不写入输出）
            continue

        samples.append({
            "topic_id":    topic_id,
            "title":       title,
            "topic_url":   topic_url,
            "post_id":     post.get("id"),
            "post_number": post.get("post_number"),
            # raw_text 保留完整 Markdown 原文，供后续 SFT 指令生成步骤使用
            # （利用 DeepSeek-V4-Pro 从上下文推断设计师的"原始意图"）
            "raw_text":    raw_md,
            "code_blocks": code_blocks,
        })

    return samples


# ═════════════════════════════════════════════════════════════════════════════
# 输出层
# ═════════════════════════════════════════════════════════════════════════════

def _write_jsonl(path: Path, records: list[dict]) -> int:
    """
    以追加模式将 records 写入 JSONL 文件（每条记录占一行）。
    ensure_ascii=False 保留中文字符，避免 Unicode 转义膨胀文件体积。
    返回实际写入的行数。
    """
    written = 0
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
    return written


# ═════════════════════════════════════════════════════════════════════════════
# 公开入口
# ═════════════════════════════════════════════════════════════════════════════

async def scrape_all(
    max_pages: int = DEFAULT_MAX_PAGES,
    output_path: Path = RAW_SAMPLES_PATH,
) -> None:
    """
    完整采集入口：遍历前 max_pages 页，并发抓取每页的帖子详情。

    设计决策：
    - 每页主题列表串行获取（页与页之间有依赖：上一页空则停止）
    - 同页内各主题的帖子详情并发获取（asyncio.gather + Semaphore 限速）
    - 结果逐页实时追加写入输出文件，支持后续断点续跑（直接改 page 起始值）

    Args:
        max_pages:   最大抓取页数（测试阶段建议 5，全量建议 50+）
        output_path: 输出 JSONL 文件路径（默认 data/raw_samples.jsonl）
    """
    # 确保输出目录存在，并清空旧文件保证输出幂等
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("", encoding="utf-8")
    logger.info(f"输出文件已初始化: {output_path}")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    total_topics_processed = 0
    total_samples_written = 0

    # 共享连接池：httpx.AsyncClient 在整个采集周期内复用 TCP 连接
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
        headers={
            # 向论坛服务器表明爬虫身份，是负责任的爬虫实践
            "User-Agent": (
                "RhinoCoder-DataPipeline/0.1 "
                "(academic research scraper; contact: xiongweiluo1@gmail.com)"
            ),
            "Accept": "application/json",
        },
        follow_redirects=True,
    ) as client:

        for page in range(max_pages):
            # ── 串行获取每页的主题列表 ──────────────────────────────────────
            topics = await _fetch_topic_list(client, semaphore, page)
            if not topics:
                logger.info(f"第 {page} 页无主题，采集提前终止（共处理 {page} 页）")
                break

            total_topics_processed += len(topics)

            # ── 并发获取同页所有主题的帖子详情 ─────────────────────────────
            # return_exceptions=True：单个主题失败不影响其他主题
            tasks = [
                _fetch_posts_from_topic(client, semaphore, topic)
                for topic in topics
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 收集本页所有有效样本
            page_samples: list[dict] = []
            failed_count = 0
            for result in results:
                if isinstance(result, list):
                    page_samples.extend(result)
                else:
                    # result 是 Exception 实例（由 return_exceptions=True 捕获）
                    logger.warning(f"帖子获取异常（已忽略）: {result!r}")
                    failed_count += 1

            # 实时写入，避免内存累积
            written = _write_jsonl(output_path, page_samples)
            total_samples_written += written

            logger.info(
                f"  第 {page} 页完成：{len(topics)} 个主题，"
                f"{failed_count} 个请求失败，"
                f"写入 {written} 条含 Rhino Python 代码的样本"
            )

    # ── 最终统计摘要 ──────────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 65)
    logger.info("采集完成")
    logger.info(f"  处理主题数：{total_topics_processed}")
    logger.info(f"  写入样本数：{total_samples_written}（含 Rhino Python 代码块的帖子）")
    logger.info(f"  输出文件：  {output_path}")
    logger.info("=" * 65)


if __name__ == "__main__":
    # 直接运行本脚本时，使用默认参数（max_pages=5）进行测试采集
    asyncio.run(scrape_all())
