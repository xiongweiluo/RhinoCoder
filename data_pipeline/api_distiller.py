"""
data_pipeline/api_distiller.py

LLM 蒸馏模块：从 rhinoscriptsyntax 官方 API 源文件中按函数为单位提取定义，
异步并发调用 DeepSeek（OpenAI 兼容格式）合成多样化【用户指令-代码回答】训练对，
结果以 JSONL 格式追加写入 data/train.jsonl。

处理流程：
  ① 扫描 raw_api_source/Scripts/rhinoscript/*.py，提取所有公开顶层函数
  ② 以函数为粒度构造 Prompt，asyncio.gather() 并发调用 LLM（Semaphore=3）
  ③ 解析 JSON 响应，校验 qa_pairs 字段
  ④ 追加写入 data/train.jsonl（instruction + output 两字段）

并发与健壮性：
  - asyncio.Semaphore(3) 限制同时活跃的 API 请求数
  - 指数退避重试（最多 3 次），限速/服务端错误/超时均触发重试
  - 单个 chunk 失败记录日志后跳过，不影响整体流水线
"""

import ast
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

# ── 环境变量 ──────────────────────────────────────────────────────────────────
# .env 文件放置于项目根目录，包含 DEEPSEEK_API_KEY（必填）和可选覆盖项
load_dotenv()

DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
MODEL_NAME: str = os.getenv("DEEPSEEK_MODEL", "deepseek-coder")

# ── 目录配置 ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
RAW_API_DIR  = PROJECT_ROOT / "raw_api_source" / "Scripts" / "rhinoscript"
DATA_DIR     = PROJECT_ROOT / "data"
TRAIN_PATH   = DATA_DIR / "train.jsonl"

# ── 并发与重试参数 ─────────────────────────────────────────────────────────────
SEMAPHORE_LIMIT  = 3      # 同时活跃的 API 请求上限
MAX_RETRIES      = 3      # 单次请求最大重试次数（不含首次）
RETRY_BASE_SECS  = 2.0    # 指数退避基数（秒），第 n 次等待 RETRY_BASE_SECS^n 秒

# ── 日志配置 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("api_distiller")


# ═════════════════════════════════════════════════════════════════════════════
# Prompt 常量
# ═════════════════════════════════════════════════════════════════════════════

DISTILLATION_PROMPT = """\
你是一位专业的数据合成专家，深度熟悉 Rhino 3D 建模软件的 Python 脚本编程（rhinoscriptsyntax API）。

你的任务是：根据下面提供的一个 rhinoscriptsyntax API 函数源码，生成 5 个高质量的\
【用户指令 - 代码回答】训练对，用于训练代码生成模型。

生成要求：
1. 5 个训练对必须覆盖不同使用场景与复杂度，分别对应以下风格：
   a) 初学者口语化提问（场景具体，表达不精确）
   b) 进阶开发者的精确技术需求（含参数说明）
   c) 复合任务（将该函数与 1-2 个其他 rhinoscriptsyntax 函数组合使用）
   d) 边界情况或错误处理（如参数为 None 时的防御性写法）
   e) 中文自然语言描述，模拟真实用户提问习惯

2. instruction 字段：
   - 使用自然语言描述用户需求，禁止直接出现 API 函数名
   - 从用户目标角度出发，而非从函数签名角度出发

3. output 字段：
   - 完整可运行的 Python 代码（含 import rhinoscriptsyntax as rs 等必要导入）
   - 代码风格参考官方文档示例（简洁、有注释、遵循 rhinoscriptsyntax 惯用法）
   - 代码必须真实调用该 API，不得臆造不存在的函数

输出格式：严格输出合法 JSON 对象，禁止包含 markdown 代码块、注释或任何额外文字：
{
  "qa_pairs": [
    {"instruction": "...", "output": "..."},
    {"instruction": "...", "output": "..."},
    {"instruction": "...", "output": "..."},
    {"instruction": "...", "output": "..."},
    {"instruction": "...", "output": "..."}
  ]
}

以下是待处理的 API 函数源码：
"""


# ═════════════════════════════════════════════════════════════════════════════
# 函数 Chunk 提取
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class FunctionChunk:
    """从源文件中提取的单个公开顶层函数定义"""
    source_file: str   # 来源文件名（不含路径），用于日志和溯源
    func_name:   str   # 函数名
    source_code: str   # 完整函数源码（含 docstring、示例代码）


def extract_function_chunks(py_file: Path) -> list[FunctionChunk]:
    """
    从单个 .py 文件中提取所有公开顶层函数定义的源码。

    只取顶层函数（tree.body 直接子节点），跳过嵌套函数和类方法，
    也跳过以 _ 开头的私有函数——它们是内部实现，不适合生成用户侧训练数据。

    保留原始源文本切片（含 docstring 和行内示例），让 LLM 理解完整 API 语义。
    """
    try:
        source_text = py_file.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(f"无法读取文件 {py_file.name}: {exc}")
        return []

    try:
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        logger.warning(f"AST 解析失败 {py_file.name}: {exc}")
        return []

    source_lines = source_text.splitlines(keepends=True)
    chunks: list[FunctionChunk] = []

    for node in tree.body:  # 只遍历顶层节点，避免 ast.walk 递归进嵌套函数
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        # end_lineno 在 Python 3.8+ 可用；ast.parse 默认填充此字段
        func_source = "".join(source_lines[node.lineno - 1 : node.end_lineno])
        chunks.append(FunctionChunk(
            source_file=py_file.name,
            func_name=node.name,
            source_code=func_source.strip(),
        ))

    return chunks


def collect_all_chunks(api_dir: Path) -> list[FunctionChunk]:
    """扫描目录下全部 .py 文件，返回所有公开顶层函数的 chunk 列表"""
    py_files = sorted(api_dir.glob("*.py"))
    if not py_files:
        logger.error(f"未找到任何 .py 文件，目录: {api_dir}")
        return []

    all_chunks: list[FunctionChunk] = []
    for py_file in py_files:
        if py_file.stem.startswith("_"):  # 跳过 __init__.py 等内部文件
            continue
        chunks = extract_function_chunks(py_file)
        logger.info(f"  {py_file.name}: 提取 {len(chunks)} 个函数")
        all_chunks.extend(chunks)

    logger.info(f"共提取 {len(all_chunks)} 个函数 chunk，来自 {len(py_files)} 个文件")
    return all_chunks


# ═════════════════════════════════════════════════════════════════════════════
# 异步 API 调用
# ═════════════════════════════════════════════════════════════════════════════

async def call_llm_with_retry(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    chunk: FunctionChunk,
) -> Optional[list[dict]]:
    """
    对单个 FunctionChunk 调用 LLM，含并发限制和指数退避重试。

    Returns:
        成功时返回 QA 对列表（list[dict]），失败（含重试耗尽）返回 None。
    """
    user_message = DISTILLATION_PROMPT + chunk.source_code

    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": user_message}],
        # response_format=json_object 强制模型输出合法 JSON，DeepSeek/OpenAI 均支持
        "response_format": {"type": "json_object"},
        "temperature": 0.8,  # 适度多样性，防止 5 条训练对雷同
        "max_tokens": 4096,
    }

    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(
                    f"{BASE_URL}/chat/completions",
                    json=payload,
                    timeout=120.0,  # 较长超时，函数体大时响应慢
                )
                resp.raise_for_status()

                content = resp.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                qa_pairs = parsed.get("qa_pairs", [])

                if not isinstance(qa_pairs, list) or not qa_pairs:
                    logger.warning(
                        f"[{chunk.func_name}] 响应 qa_pairs 字段为空或非列表，已跳过"
                    )
                    return None

                return qa_pairs

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (429, 500, 502, 503, 504):
                    wait = RETRY_BASE_SECS ** (attempt + 1)
                    logger.warning(
                        f"[{chunk.func_name}] HTTP {status}，"
                        f"{wait:.0f}s 后重试（{attempt + 1}/{MAX_RETRIES}）"
                    )
                    await asyncio.sleep(wait)
                else:
                    # 4xx（非 429）通常是请求本身的问题，不重试
                    logger.error(
                        f"[{chunk.func_name}] HTTP {status} 不可重试: "
                        f"{exc.response.text[:200]}"
                    )
                    return None

            except httpx.TimeoutException:
                wait = RETRY_BASE_SECS ** (attempt + 1)
                logger.warning(
                    f"[{chunk.func_name}] 请求超时，"
                    f"{wait:.0f}s 后重试（{attempt + 1}/{MAX_RETRIES}）"
                )
                await asyncio.sleep(wait)

            except json.JSONDecodeError as exc:
                logger.error(
                    f"[{chunk.func_name}] JSON 解析失败（第 {attempt + 1} 次）: {exc}"
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BASE_SECS)
                else:
                    return None

            except Exception as exc:
                logger.error(f"[{chunk.func_name}] 意外异常（已跳过）: {exc!r}")
                return None

    return None  # 所有重试均失败


# ═════════════════════════════════════════════════════════════════════════════
# JSONL 写入
# ═════════════════════════════════════════════════════════════════════════════

def append_qa_pairs(output_path: Path, qa_pairs: list[dict]) -> int:
    """
    将 QA 对追加写入 JSONL，每对一行，只保留 instruction 和 output 字段。
    过滤掉任一字段为空的残缺记录。
    返回实际写入的条数。
    """
    written = 0
    with open(output_path, "a", encoding="utf-8") as f:
        for pair in qa_pairs:
            instruction = str(pair.get("instruction", "")).strip()
            output      = str(pair.get("output", "")).strip()
            if not instruction or not output:
                continue
            f.write(json.dumps(
                {"instruction": instruction, "output": output},
                ensure_ascii=False,
            ) + "\n")
            written += 1
    return written


# ═════════════════════════════════════════════════════════════════════════════
# 统计
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class DistillationStats:
    total_chunks: int = 0   # 输入函数 chunk 总数
    api_success:  int = 0   # API 调用成功（返回有效 QA 列表）
    api_failed:   int = 0   # API 调用失败（含重试耗尽）
    qa_written:   int = 0   # 最终写入 JSONL 的 QA 对总数

    def log_summary(self) -> None:
        avg = self.qa_written / max(self.api_success, 1)
        logger.info("")
        logger.info("=" * 65)
        logger.info("蒸馏流水线完成")
        logger.info(f"  输入函数 chunk 总数：{self.total_chunks}")
        logger.info(f"  API 调用成功：      {self.api_success}")
        logger.info(f"  API 调用失败：      {self.api_failed}")
        logger.info(f"  写入 QA 对总数：    {self.qa_written}")
        logger.info(f"  平均每次成功产出：  {avg:.1f} 对")
        logger.info("=" * 65)


# ═════════════════════════════════════════════════════════════════════════════
# 主协程
# ═════════════════════════════════════════════════════════════════════════════

async def distill_all(
    api_dir:         Path = RAW_API_DIR,
    output_path:     Path = TRAIN_PATH,
    semaphore_limit: int  = SEMAPHORE_LIMIT,
) -> DistillationStats:
    """
    主蒸馏协程：扫描 API 源文件 → 并发 LLM 调用 → 写入 JSONL。

    所有 chunk 的任务以 asyncio.gather() 同时提交，
    Semaphore 在内部将并发活跃请求数限制为 semaphore_limit，
    兼顾吞吐量与 API 限速保护。
    """
    if not DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY 未设置，请在项目根目录 .env 文件中配置")
        raise RuntimeError("缺少 DEEPSEEK_API_KEY")

    stats = DistillationStats()

    logger.info(f"扫描 API 源文件目录: {api_dir}")
    chunks = collect_all_chunks(api_dir)

    # 👇 修改这里：强行截取前 2 个 chunk
    logger.info("🧪 触发小批量测试模式：强行截断，仅处理前 2 个 API 函数")
    # 👆 修改结束
    
    if not chunks:
        logger.error("未提取到任何函数 chunk，流水线终止")
        return stats

    stats.total_chunks = len(chunks)
    logger.info(f"共 {stats.total_chunks} 个 chunk 待处理，并发上限={semaphore_limit}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(semaphore_limit)

    # 复用单个 httpx.AsyncClient，连接池在所有请求间共享
    async with httpx.AsyncClient(
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
    ) as client:
        tasks = [
            call_llm_with_retry(client, semaphore, chunk)
            for chunk in chunks
        ]
        results: list[Optional[list[dict]]] = await asyncio.gather(*tasks)

    # 顺序写入，避免多协程并发 append 产生文件竞争（gather 已完成，此处为串行）
    for chunk, qa_pairs in zip(chunks, results):
        if qa_pairs is None:
            stats.api_failed += 1
            logger.warning(f"跳过失败 chunk: {chunk.source_file}:{chunk.func_name}")
            continue

        stats.api_success += 1
        written = append_qa_pairs(output_path, qa_pairs)
        stats.qa_written += written
        logger.info(
            f"  ✓ {chunk.source_file}:{chunk.func_name} → {written} 对写入"
        )

    logger.info(f"JSONL 已追加写入: {output_path}")
    stats.log_summary()
    return stats


# ═════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """
    命令行入口。

    用法：
      python -m data_pipeline.api_distiller
      python data_pipeline/api_distiller.py
      python data_pipeline/api_distiller.py --concurrency 5 --output data/my_train.jsonl
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="rhinoscriptsyntax API LLM 蒸馏工具",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--api-dir",
        type=Path,
        default=RAW_API_DIR,
        help="API 源文件目录",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=TRAIN_PATH,
        help="输出 JSONL 路径（追加写入）",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=SEMAPHORE_LIMIT,
        help="并发 API 请求上限",
    )
    args = parser.parse_args()

    asyncio.run(distill_all(
        api_dir=args.api_dir,
        output_path=args.output,
        semaphore_limit=args.concurrency,
    ))


if __name__ == "__main__":
    main()
