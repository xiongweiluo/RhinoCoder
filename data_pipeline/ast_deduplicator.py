"""
data_pipeline/ast_deduplicator.py

AST 结构去重模块：从 raw_samples.jsonl 读取原始代码块，
经两阶段清洗后输出高纯度训练数据 train.jsonl。

两阶段清洗设计：
  阶段一：语法校验（快速失败）
    使用 compile(code, '<string>', 'exec') 而非 ast.parse()。
    compile() 更接近 CPython 解释器的真实执行路径，能捕获 ast.parse()
    可能放过的极少数边缘语法问题（如某些编码声明错误）。
    引发 SyntaxError 的片段直接丢弃，不进入后续流程。

  阶段二：AST 结构规范化 + SHA-256 哈希去重
    使用 ASTNormalizer（NodeTransformer 子类）抹去所有标识符和字面量，
    仅保留语法结构骨架（控制流、调用链、属性访问模式），然后对规范化
    AST 的 dump 字符串计算 SHA-256 哈希。哈希相同的代码块视为同构重复，
    只保留第一条（通常是 McNeel 官方文档示例，质量最高）。

    关键设计：保留 Attribute.attr（属性名，如 AddSphere）
    ─────────────────────────────────────────────────────────
    Rhino API 调用的核心语义在属性名，而非对象名：
      rs.AddSphere([0,0,0], 5)  ─┐ 结构不同（属性名不同）→ 不同哈希 ✓
      rs.AddLine([0,0,0], [1,1,1]) ─┘
      rs.AddSphere([0,0,0], 5)  ─┐ 结构相同（仅坐标不同）→ 相同哈希 ✓
      rs.AddSphere([1,2,3], 10) ─┘
    若连属性名也抹去，AddSphere 和 AddLine 会被误判为同构，丢失 API 多样性。

输出格式（data/train.jsonl，每行一个 JSON）：
  {
    "code":        str,   # 原始代码（保留真实变量名，供模型学习 API 用法）
    "struct_hash": str,   # 结构哈希（用于调试和增量去重）
    "topic_id":    int,
    "title":       str,   # 主题标题（供后续 SFT 指令生成使用）
    "topic_url":   str,
    "post_id":     int,
    "post_number": int,
    "raw_text":    str    # 帖子原始 Markdown（供后续指令生成使用）
  }

Q4 升级路径：替换为 tree-sitter 以支持 C# RhinoCommon 代码样本。
重要提醒：Q2 流水线跑通后立即人工抽检 200 条样本验证去重逻辑，
          不要等到全量数据爬取完成——发现大量同构样本混入训练集代价极高。
"""

import ast
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── 目录配置 ─────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data"
RAW_SAMPLES_PATH = DATA_DIR / "raw_samples.jsonl"
TRAIN_PATH = DATA_DIR / "train.jsonl"

# ── 过滤参数 ──────────────────────────────────────────────────────────────────
# 行数过少的代码片段（如单行 import 或单行函数调用）信息量极低，
# 且往往是帖子内嵌的行内代码而非完整示例，提前过滤避免污染数据集
MIN_CODE_LINES = 3

# ── 日志配置 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ast_deduplicator")


# ═════════════════════════════════════════════════════════════════════════════
# 阶段一：语法校验
# ═════════════════════════════════════════════════════════════════════════════

def check_syntax(code: str) -> bool:
    """
    使用 compile() 对代码片段进行语法校验，返回 True 表示语法合法。

    选用 compile() 而非 ast.parse() 的原因：
      compile() 触发完整的编译前端管道（词法 → 语法 → 语义检查），
      能捕获 ast.parse() 可能忽略的极少数异常（如非法编码声明），
      且与 CPython 解释器在 exec() 前的检查行为完全一致。

    Args:
        code: 待校验的 Python 源代码字符串

    Returns:
        True — 语法合法，可继续后续处理
        False — 存在 SyntaxError，应直接丢弃此代码片段
    """
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError:
        return False
    except Exception:
        # compile() 在极少数情况下（如空字节、BOM 问题）可能抛出其他异常
        return False


# ═════════════════════════════════════════════════════════════════════════════
# 阶段二：AST 规范化 + 结构哈希
# ═════════════════════════════════════════════════════════════════════════════

class ASTNormalizer(ast.NodeTransformer):
    """
    AST 节点变换器：将代码规范化为语法结构骨架，抹去所有与具体业务无关的标识符和字面量。

    继承 ast.NodeTransformer 而非 ast.NodeVisitor，因为需要原地修改（返回新节点）。
    NodeTransformer 会自动递归调用 generic_visit() 处理未显式重写的节点类型，
    确保整棵 AST 都被遍历到。

    设计决策说明：
      ✗ 抹去 Name.id（变量名）    → 'VAR'
        理由：变量名是业务标识符，与代码结构无关
      ✗ 抹去 arg.arg（参数名）    → 'ARG'
        理由：同上
      ✗ 抹去 FunctionDef.name    → 'FUNC'
        理由：自定义函数名是业务命名，不代表算法结构
      ✗ 抹去 ClassDef.name       → 'CLASS'
        理由：同上
      ✗ 抹去 str/int/float 常量  → 'STR' / 0
        理由：具体坐标值、字符串参数是业务数据，不是结构特征
      ✓ 保留 Attribute.attr（属性名，如 AddSphere）
        理由：Rhino API 方法名是代码结构的核心语义特征（见模块文档）
      ✓ 保留 Import / ImportFrom 语句
        理由：导入的模块名（rhinoscriptsyntax、RhinoCommon）是 API 使用模式的结构特征
    """

    def visit_Name(self, node: ast.Name) -> ast.Name:
        """将所有变量引用标识符（变量名）统一替换为占位符 'VAR'"""
        node.id = "VAR"
        return node  # 不调用 generic_visit：Name 节点无子节点需要递归

    def visit_arg(self, node: ast.arg) -> ast.arg:
        """将函数/Lambda 参数名统一替换为 'ARG'；递归处理参数的类型注解"""
        node.arg = "ARG"
        self.generic_visit(node)  # 类型注解（annotation）是子节点，需递归规范化
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """将 def 函数名替换为 'FUNC'；递归处理函数体、参数列表、装饰器"""
        node.name = "FUNC"
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        """将 async def 函数名替换为 'FUNC'；处理方式同 visit_FunctionDef"""
        node.name = "FUNC"
        self.generic_visit(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        """将类名替换为 'CLASS'；递归处理类体、基类、装饰器"""
        node.name = "CLASS"
        self.generic_visit(node)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        """
        将所有字面量常量规范化为类型占位符。

        注意：bool 是 int 的子类，isinstance(True, int) == True，
        因此必须先检查 bool，否则 True/False 会被误当 int 处理为 0。
        NoneType 和 Ellipsis 保持原样：它们本身就是语法结构信息，
        None 通常表示"无返回值"语义，Ellipsis 用于类型注解占位。
        """
        if isinstance(node.value, bool):
            node.value = False          # bool 占位符（True/False 统一为 False）
        elif isinstance(node.value, str):
            node.value = "STR"
        elif isinstance(node.value, (int, float, complex)):
            node.value = 0
        # NoneType / Ellipsis 不处理，保留原值
        return node

    # ── 以下方法为空实现，用于文档说明设计决策 ──────────────────────────────

    # visit_Attribute 不重写：NodeTransformer 默认调用 generic_visit，
    # 会递归处理 node.value（Name 节点 → 变为 'VAR'），
    # 而 node.attr（字符串字段，非 AST 节点）不会被 generic_visit 触及，
    # 自然保留属性名（如 AddSphere）。这正是我们想要的行为。

    # visit_Import / visit_ImportFrom 不重写：默认 generic_visit 对 alias
    # 节点的 name/asname 字段不做处理（它们是 str，不是 AST 节点），
    # 因此模块名自然保留。


def normalize_ast(code: str) -> Optional[str]:
    """
    将 Python 代码规范化为结构骨架字符串，用于后续哈希去重。

    流程：
      1. compile() 快速语法校验（已在上游调用，此处作为防御性二次检查）
      2. ast.parse() 解析为完整 AST
      3. ASTNormalizer().visit() 原地规范化所有节点
      4. ast.fix_missing_locations() 修复被替换节点可能缺失的位置信息
      5. ast.dump(indent=None) 将规范化后的 AST 序列化为紧凑字符串

    Args:
        code: 已通过语法校验的 Python 源代码

    Returns:
        规范化 AST 字符串（用于哈希），或 None（极端情况下 parse 失败）
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # check_syntax() 已过滤大部分语法错误，此处仅作防御
        return None
    except Exception as exc:
        # ast.parse() 在极少数非 UTF-8 编码或编译器内部错误时可能抛出
        logger.debug(f"ast.parse() 抛出意外异常（已忽略）: {exc!r}")
        return None

    try:
        normalizer = ASTNormalizer()
        normalized_tree = normalizer.visit(tree)
        # fix_missing_locations 填充被变换节点可能缺失的 lineno/col_offset，
        # 防止 ast.dump() 在某些 Python 版本下报错
        ast.fix_missing_locations(normalized_tree)
        # indent=None 生成紧凑单行字符串，减少哈希输入体积
        return ast.dump(normalized_tree, indent=None)
    except Exception as exc:
        logger.debug(f"AST 规范化异常（已忽略）: {exc!r}")
        return None


def structural_hash(normalized_ast_str: str) -> str:
    """
    对规范化 AST 字符串计算 SHA-256 哈希，作为结构去重的唯一键。

    选用 SHA-256 而非内置 hash() 的原因：
      - hash() 受 Python 哈希随机化（PYTHONHASHSEED）影响，跨进程/跨运行不确定
      - SHA-256 是确定性的，支持多次运行产生相同结果（可复现性）
      - 碰撞概率可忽略不计（2^-256）

    Returns:
        64 字符的十六进制哈希字符串
    """
    return hashlib.sha256(normalized_ast_str.encode("utf-8")).hexdigest()


# ═════════════════════════════════════════════════════════════════════════════
# 统计收集
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class DeduplicationStats:
    """去重流水线统计数据，用于最终报告和质量监控"""
    total_posts: int = 0           # 输入的原始帖子记录数
    total_blocks: int = 0          # 展开后的总代码块数
    discarded_too_short: int = 0   # 因行数过短丢弃
    discarded_syntax_error: int = 0  # 因语法错误丢弃
    discarded_ast_failure: int = 0   # 因 AST 规范化失败丢弃（极少数边缘情况）
    discarded_duplicate: int = 0   # 因结构重复丢弃
    kept: int = 0                  # 最终保留的高纯度样本数

    @property
    def retain_rate(self) -> float:
        """保留率（%）"""
        if self.total_blocks == 0:
            return 0.0
        return self.kept / self.total_blocks * 100

    def log_summary(self) -> None:
        """将统计摘要输出到日志"""
        logger.info("")
        logger.info("=" * 65)
        logger.info("去重流水线完成")
        logger.info(f"  输入原始帖子记录数：{self.total_posts}")
        logger.info(f"  输入代码块总数：    {self.total_blocks}")
        logger.info(f"  丢弃（行数过短）：  {self.discarded_too_short}")
        logger.info(f"  丢弃（语法错误）：  {self.discarded_syntax_error}")
        logger.info(f"  丢弃（AST 失败）：  {self.discarded_ast_failure}")
        logger.info(f"  丢弃（结构重复）：  {self.discarded_duplicate}")
        logger.info(f"  保留（高纯度）：    {self.kept}")
        logger.info(f"  保留率：           {self.retain_rate:.1f}%")
        logger.info("=" * 65)


# ═════════════════════════════════════════════════════════════════════════════
# I/O 层
# ═════════════════════════════════════════════════════════════════════════════

def _load_raw_samples(input_path: Path) -> list[dict]:
    """
    读取 discourse_scraper.py 输出的 raw_samples.jsonl。

    健壮性设计：
      - 文件不存在时返回空列表并记录错误（不抛异常，保证流水线可继续）
      - 格式错误的行跳过并记录警告（部分损坏不影响整体）
    """
    if not input_path.exists():
        logger.error(f"输入文件不存在: {input_path}")
        return []

    samples: list[dict] = []
    malformed_lines = 0

    with open(input_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError as exc:
                malformed_lines += 1
                logger.warning(f"第 {lineno} 行 JSON 解析失败（已跳过）: {exc}")

    if malformed_lines:
        logger.warning(f"共跳过 {malformed_lines} 行格式错误的记录")

    logger.info(f"读取原始样本：{len(samples)} 条帖子记录，来自 {input_path}")
    return samples


# ═════════════════════════════════════════════════════════════════════════════
# 公开入口
# ═════════════════════════════════════════════════════════════════════════════

def run_deduplication(
    input_path: Path = RAW_SAMPLES_PATH,
    output_path: Path = TRAIN_PATH,
    min_lines: int = MIN_CODE_LINES,
) -> DeduplicationStats:
    """
    完整去重流水线：读取 → 过滤 → 去重 → 写入。

    处理步骤（与 tech-stack.md §4.4 流水线步骤 ③④ 对应）：
      ① 加载 raw_samples.jsonl，展开每个帖子的 code_blocks 列表
      ② 行数过滤：< min_lines 行的片段直接丢弃（快速过滤，减少后续开销）
      ③ compile() 语法校验：引发 SyntaxError 的片段丢弃
      ④ AST 规范化：normalize_ast() 生成结构骨架字符串
      ⑤ SHA-256 哈希：structural_hash() 计算唯一键
      ⑥ 去重：哈希已见过的代码块丢弃，保留第一条
      ⑦ 写入 train.jsonl（保留原始代码 + 完整元数据供后续步骤使用）

    Args:
        input_path:  raw_samples.jsonl 路径（discourse_scraper.py 的输出）
        output_path: train.jsonl 输出路径
        min_lines:   行数过滤阈值（默认 3 行）

    Returns:
        DeduplicationStats 对象，包含各阶段丢弃/保留计数
    """
    stats = DeduplicationStats()

    raw_samples = _load_raw_samples(input_path)
    if not raw_samples:
        logger.error("未读取到任何样本，流水线终止")
        return stats

    stats.total_posts = len(raw_samples)

    # 用于结构去重的哈希集合（内存中维护，单机运行足够）
    seen_hashes: set[str] = set()

    # 确保输出目录存在，覆盖写入（保证输出幂等）
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as out_f:

        for sample in raw_samples:
            code_blocks: list[str] = sample.get("code_blocks", [])

            for block_idx, code in enumerate(code_blocks):
                stats.total_blocks += 1

                # ── 步骤 ②：行数过滤（极短代码噪声多，优先快速过滤）──────────
                stripped_lines = [ln for ln in code.splitlines() if ln.strip()]
                if len(stripped_lines) < min_lines:
                    stats.discarded_too_short += 1
                    continue

                # ── 步骤 ③：compile() 语法校验 ──────────────────────────────
                if not check_syntax(code):
                    stats.discarded_syntax_error += 1
                    logger.debug(
                        f"语法错误丢弃 topic_id={sample.get('topic_id')} "
                        f"block[{block_idx}] 前60字符: {code[:60]!r}"
                    )
                    continue

                # ── 步骤 ④：AST 规范化 ──────────────────────────────────────
                normalized = normalize_ast(code)
                if normalized is None:
                    # normalize_ast 内部已记录 debug 日志
                    stats.discarded_ast_failure += 1
                    continue

                # ── 步骤 ⑤：计算结构哈希 ────────────────────────────────────
                h = structural_hash(normalized)

                # ── 步骤 ⑥：去重判断 ────────────────────────────────────────
                if h in seen_hashes:
                    stats.discarded_duplicate += 1
                    continue
                seen_hashes.add(h)

                # ── 步骤 ⑦：写入高纯度训练样本 ─────────────────────────────
                record = {
                    "code":        code,
                    # struct_hash 保留在输出中，便于后续增量去重和调试
                    "struct_hash": h,
                    "topic_id":    sample.get("topic_id"),
                    "title":       sample.get("title"),
                    "topic_url":   sample.get("topic_url"),
                    "post_id":     sample.get("post_id"),
                    "post_number": sample.get("post_number"),
                    # raw_text：供后续 sft_formatter.py 用 LLM 生成"指令"字段
                    "raw_text":    sample.get("raw_text", ""),
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                stats.kept += 1

    logger.info(f"高纯度样本已写入: {output_path}")
    stats.log_summary()
    return stats


if __name__ == "__main__":
    # 直接运行本脚本时，从默认路径读取 raw_samples.jsonl 并输出 train.jsonl
    run_deduplication()
