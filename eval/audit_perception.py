#!/usr/bin/env python3
"""审计 golden_dataset：统计每条轨迹是否含 get_scene_summary 自检调用，挑出「零感知」轨迹。

用法：
    python eval/audit_perception.py                      # 审计默认 data/golden_traces_v2.jsonl
    python eval/audit_perception.py path/to/data.jsonl   # 审计指定文件
    python eval/audit_perception.py --dump-zero          # 把零感知轨迹导出到 *_zero_perception.jsonl
"""
import json
import sys
from collections import Counter
from pathlib import Path

PERCEPTION_TOOLS = {"get_scene_summary", "get_bounding_box", "get_object_info",
                    "get_objects_by_name", "get_selected_objects"}
SELF_CHECK_TOOL = "get_scene_summary"  # 我们最关心的强制自检工具


def tool_call_names(msg):
    """从一条 assistant 消息里取出它调用的工具名列表。"""
    names = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function", {}).get("name")
        if fn:
            names.append(fn)
    return names


def first_user_instruction(messages):
    for m in messages:
        if m.get("role") == "user":
            return (m.get("content") or "").strip().replace("\n", " ")
    return "(无 user 指令)"


def audit(path, dump_zero=False):
    path = Path(path)
    if not path.exists():
        print(f"[ERR] 文件不存在: {path}")
        sys.exit(1)

    rows = []          # (idx, instr, all_tools, has_self_check)
    zero_lines = []    # 原始 json 行，供导出

    with path.open(encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            msgs = obj.get("messages", [])
            tools = []
            for m in msgs:
                if m.get("role") == "assistant":
                    tools.extend(tool_call_names(m))
            has_check = SELF_CHECK_TOOL in tools
            rows.append((idx, first_user_instruction(msgs), tools, has_check))
            if not has_check:
                zero_lines.append(line)

    total = len(rows)
    with_check = sum(1 for r in rows if r[3])
    zero = total - with_check

    print(f"\n{'='*72}")
    print(f"审计文件: {path}   共 {total} 条轨迹")
    print(f"{'='*72}")
    print(f"✅ 含 get_scene_summary 自检 : {with_check:3d} 条 ({with_check/total*100:.0f}%)")
    print(f"⚠️  零感知（须重采/复核）     : {zero:3d} 条 ({zero/total*100:.0f}%)")

    # 工具使用频次概览
    counter = Counter()
    for _, _, tools, _ in rows:
        counter.update(tools)
    print(f"\n工具调用频次（全库）:")
    for name, n in counter.most_common():
        flag = " ⟵ 感知" if name in PERCEPTION_TOOLS else ""
        print(f"  {name:<24} {n:4d}{flag}")

    if zero:
        print(f"\n{'─'*72}\n⚠️  以下轨迹未调用 get_scene_summary（可能是零感知，建议复核/重采）:")
        for idx, instr, tools, has in rows:
            if not has:
                preview = instr[:48] + ("…" if len(instr) > 48 else "")
                print(f"  行 {idx:>3}: {preview}")
    else:
        print(f"\n🎉 全部轨迹均含 get_scene_summary 自检，无零感知污染。")

    if dump_zero and zero_lines:
        out = path.with_name(path.stem + "_zero_perception.jsonl")
        out.write_text("\n".join(zero_lines) + "\n", encoding="utf-8")
        print(f"\n[DUMP] 已将 {len(zero_lines)} 条零感知轨迹导出 → {out}")

    return zero


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dump = "--dump-zero" in sys.argv
    target = args[0] if args else "data/golden_traces_v2.jsonl"
    audit(target, dump_zero=dump)
