#!/usr/bin/env python3
"""Export only allowlisted historical tasks, never discover a new holdout.

No imported history scripts, eval/exec, remote calls, GPU, Rhino or new-run
claims. Output stays outside every registered worktree with private modes.
Visible source literals and prepared R cases are conservatively excluded too;
the export is not a claim that every task was actually executed or recovered.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from tools.c5_rhino_formal20_owner_exclusion import _worktrees

TEXT_KEYS = {'task', 'task_text', 'user_step', 'instruction', 'prompt', 'step_text', 'request_text', 'text'}
IDS = ('family_id', 'task_id', 'case_id', 'id')
R_PATTERNS = ('eval/r4*.json', 'eval/r4*.jsonl', 'eval/r_research/*.json',
    'docs/r4-evidence/**/*.json', 'docs/r4*.json', 'docs/r4*.md', 'docs/r-research*.md',
    'tools/r4*.py', 'tools/r_research*.py', 'training/*candidate*.py', 'eval/test_r4*.py')
C5_FILES = ('eval/c5/modelbridge-development-spec-20261003.json',
    'eval/c5/modelbridge-development-spec-20261003-b.json',
    'eval/c5/native12-development-spec-20261003.json', 'tools/c5_native12_common.py',
    'tools/c5_rhino_native12_batch.py', 'eval/test_c5_formal20_preparation.py',
    'eval/test_c5_formal20_field_adapters.py')
ACTION = re.compile(r'创建|生成|移动|平移|旋转|缩放|查看|查询|删除|选中|请|麻烦|取消|拒绝')
LIMIT = 8 * 1024 * 1024


def static_expression(node, bindings):
    """Tiny non-executing arithmetic/string interpreter, no calls/attributes."""
    if isinstance(node, ast.Constant) and type(node.value) in (str, int, float): return node.value
    if isinstance(node, ast.Name) and node.id in bindings: return bindings[node.id]
    if isinstance(node, (ast.Tuple, ast.List)): return [static_expression(v, bindings) for v in node.elts]
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
        a, b = static_expression(node.left, bindings), static_expression(node.right, bindings)
        if type(a) not in (int, float) or type(b) not in (int, float): raise ValueError('non_numeric_static_expression')
        return a+b if isinstance(node.op, ast.Add) else a-b if isinstance(node.op, ast.Sub) else a*b
    if isinstance(node, ast.JoinedStr):
        pieces = []
        for p in node.values:
            if isinstance(p, ast.Constant) and isinstance(p.value, str): pieces.append(p.value)
            elif isinstance(p, ast.FormattedValue) and p.conversion == -1 and p.format_spec is None:
                pieces.append(str(static_expression(p.value, bindings)))
            else: raise ValueError('unsupported_static_format')
        return ''.join(pieces)
    raise ValueError('dynamic_expression_not_executed')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def read_bytes(path):
    if path.resolve() != path or not path.is_file() or not 0 < path.stat().st_size <= LIMIT:
        raise ValueError('unsafe_or_unbounded_historical_source')
    with path.open('rb') as stream: raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT: raise ValueError('historical_source_grew')
    return raw


def json_value(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: raise ValueError('duplicate_historical_json_key')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_historical_json')))


class Collector:
    def __init__(self): self.rows, self.sources, self.unresolved = {}, {}, []

    def add(self, text, source, locator, kind, context=None):
        if not isinstance(text, str) or not text.strip(): return
        text = text.strip()
        if len(text.encode()) > 4096:
            self.unresolved.append({'source': source, 'locator': locator, 'reason': 'text_exceeds_task_bound'})
            return
        context = context or {}
        identities = {k: str(context[k]) for k in (*IDS, 'template_family')
            if isinstance(context.get(k), str) and context[k]}
        # Preserve all historical identities even when the text is duplicated.
        key = hashlib.sha256(canonical({'task_text': text, 'identities': identities})).hexdigest()
        row = self.rows.setdefault(key, {'task_text': text, 'task_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'representation_kinds': [], 'sources': [], **identities})
        if 'family_id' not in row:
            for k in IDS[1:]:
                if k in row: row['family_id'] = row[k]; break
        if kind not in row['representation_kinds']: row['representation_kinds'].append(kind)
        provenance = {'source': source, 'locator': locator}
        if provenance not in row['sources']: row['sources'].append(provenance)

    def walk(self, value, source, locator='$', context=None):
        if isinstance(value, dict):
            ctx = {**(context or {}), **{k: value[k] for k in (*IDS, 'template_family') if k in value}}
            for key, item in value.items():
                where = locator + '.' + str(key)
                if key in TEXT_KEYS and isinstance(item, str): self.add(item, source, where, 'historical_text_field', ctx)
                if key == 'steps' and isinstance(item, list):
                    for index, step in enumerate(item):
                        if isinstance(step, str): self.add(step, source, where + '[%d]' % index, 'planned_user_step', ctx)
                self.walk(item, source, where, ctx)
            # The R two-write probe used these JSON bytes as its actual task.
            if isinstance(value.get('op'), str) and all(isinstance(k, str) for k in value):
                self.add(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True),
                    source, locator, 'explicit_operation_json', ctx)
            # Native12 was not an LLM task. Keep a marked operation proxy for
            # manual equivalence review; never fabricate a historical prompt.
            if set(value) == {'name', 'arguments'} and isinstance(value['arguments'], dict):
                self.add(canonical(value).decode(), source, locator, 'native_operation_proxy_not_original_prompt', ctx)
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value): self.walk(item, source, locator + '[%d]' % i, context)

    def ingest(self, path, source):
        raw = read_bytes(path)
        before = len(self.rows)
        if path.suffix in {'.json', '.jsonl'}:
            if path.suffix == '.jsonl':
                for i, line in enumerate(raw.splitlines(), 1):
                    if line.strip(): self.walk(json_value(line), source, 'line:%d' % i)
            else: self.walk(json_value(raw), source)
        elif path.suffix == '.py':
            tree = ast.parse(raw, filename=source)
            parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
            materialized = set()
            for node in ast.walk(tree):
                if not isinstance(node, ast.GeneratorExp) or len(node.generators) != 1: continue
                g = node.generators[0]
                if (not isinstance(g.target, ast.Name) or g.ifs or g.is_async or not isinstance(g.iter, ast.Call)
                        or not isinstance(g.iter.func, ast.Name) or g.iter.func.id != 'range' or g.iter.keywords): continue
                try:
                    args = [ast.literal_eval(v) for v in g.iter.args]
                    if not 1 <= len(args) <= 3 or any(type(v) is not int for v in args): continue
                    numbers = range(*args)
                    if len(numbers) > 256: continue
                    values = [static_expression(node.elt, {g.target.id: i}) for i in numbers]
                except (ValueError, TypeError, SyntaxError): continue
                for i, value in enumerate(values):
                    def strings(v):
                        if isinstance(v, str) and ACTION.search(v):
                            self.add(v, source, 'AST:%d:variant:%d' % (node.lineno, i), 'materialized_static_generator')
                        elif isinstance(v, list):
                            for child in v: strings(child)
                    strings(value)
                materialized.update(n for n in ast.walk(node) if isinstance(n, ast.JoinedStr))
            # AST-only literal inspection, NEVER execute/import a history file.
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if any(isinstance(t, ast.Name) and re.search(r'(^|_)(task|prompt|user_step)$', t.id, re.I) for t in targets):
                        try: value = ast.literal_eval(node.value)
                        except (ValueError, TypeError, SyntaxError): value = None
                        if isinstance(value, str): self.add(value, source, 'AST:%d' % node.lineno, 'literal_task_assignment')
                if isinstance(node, (ast.Dict, ast.List, ast.Tuple)):
                    try: literal = ast.literal_eval(node)
                    except (ValueError, TypeError, SyntaxError, RecursionError): continue
                    self.walk(literal, source, 'AST:%d' % node.lineno)
                if (isinstance(node, ast.Constant) and isinstance(node.value, str) and ACTION.search(node.value)
                        and not isinstance(parents.get(node), ast.JoinedStr)):
                    # Conservative: visible literals may include unexecuted
                    # development cases. A partial f-string is NOT a task.
                    self.add(node.value, source, 'AST:%d' % node.lineno, 'visible_source_literal_not_execution_proof')
                if (isinstance(node, ast.JoinedStr) and node not in materialized
                    and not any(isinstance(x, ast.Constant) and isinstance(x.value, str) and '<form' in x.value for x in node.values)
                    and any(isinstance(x, ast.Constant) and isinstance(x.value, str) and ACTION.search(x.value) for x in node.values)):
                    self.unresolved.append({'source': source, 'locator': 'AST:%d' % node.lineno,
                        'reason': 'dynamic_task_template_check_materialized_history_and_semantics'})
        elif path.suffix == '.md':
            for i, line in enumerate(raw.decode().splitlines(), 1):
                for text in re.findall(r'`([^`\n]+)`|[“「]([^”」\n]+)[”」]', line):
                    candidate = next((s for s in text if s), '')
                    if ACTION.search(candidate): self.add(candidate, source, 'line:%d' % i, 'quoted_history_documentation')
        self.sources[source] = {'sha256': hashlib.sha256(raw).hexdigest(),
            'new_unique_rows': len(self.rows) - before, 'bytes': len(raw)}


def collect(c5_root, r_roots, development_root):
    worktrees = _worktrees()
    c5_root, development_root = c5_root.resolve(), development_root.resolve()
    if c5_root not in worktrees or any(p.resolve() not in worktrees for p in r_roots):
        raise ValueError('history_inputs_must_be_registered_worktrees')
    result = Collector()
    for name in C5_FILES:
        result.ingest(c5_root / name, 'c5:' + name)
    freeze = json_value(read_bytes(c5_root / 'eval/c5/dataset-v2-freeze-manifest.json'))
    for artifact in freeze['artifacts']:
        if artifact['path'] not in {'train.jsonl', 'validation.jsonl', 'development.jsonl'}:
            raise ValueError('unexpected_development_artifact')
        path = development_root / artifact['path']; raw = read_bytes(path)
        if hashlib.sha256(raw).hexdigest() != artifact['sha256']: raise ValueError('development_freeze_drift')
        result.ingest(path, 'frozen-development:' + artifact['path'])
    for index, root in enumerate(r_roots):
        root = root.resolve(); files = sorted({p for pattern in R_PATTERNS for p in root.glob(pattern) if p.is_file()})
        if not files: raise ValueError('missing_r_history_sources')
        for path in files: result.ingest(path, 'r-history-%d:' % index + path.relative_to(root).as_posix())
    # Deterministically materialized CPU-only examples already exposed by the
    # checked-in fixture generator, not real formal20 or its private loader.
    fixture = c5_root / 'eval/test_c5_formal20_preparation.py'
    tree = ast.parse(read_bytes(fixture))
    templates = [node for node in ast.walk(tree) if isinstance(node, ast.JoinedStr)
        and any(isinstance(p, ast.Constant) and p.value == 'Synthetic only, case ' for p in node.values)]
    if len(templates) != 1: raise ValueError('synthetic_fixture_template_changed_review_required')
    # Exact template shape is verified rather than executing test code.
    expected = ast.parse("f'Synthetic only, case {index} with a distinct purpose token {chr(65+index)}.'", mode='eval').body
    if ast.dump(templates[0]) != ast.dump(expected): raise ValueError('synthetic_fixture_template_changed_review_required')
    for i in range(20):
        result.add('Synthetic only, case %d with a distinct purpose token %s.' % (i, chr(65+i)),
            'c5:eval/test_c5_formal20_preparation.py', 'synthetic-case:%d' % i,
            'materialized_checked_cpu_fixture', {'family_id': 'synthetic-family-%02d' % i,
                'template_family': 'synthetic-template-%02d' % i})
    return result


def export(result, output, worktrees):
    output = output.absolute()
    if output.resolve() != output or any(output.is_relative_to(root) for root in worktrees):
        raise ValueError('output_must_be_canonical_outside_all_worktrees')
    if output.exists(): raise ValueError('history_export_must_not_overwrite')
    rows = [result.rows[k] for k in sorted(result.rows)]
    raw = b''.join(canonical(row) + b'\n' for row in rows)
    if not 0 < len(rows) <= 5000 or len(raw) > LIMIT: raise ValueError('export_exceeds_preflight_budget')
    output.mkdir(mode=0o700)
    def write(name, data):
        fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
    write('extra-exclusion.jsonl', raw)
    report = {'status': 'local_historical_exclusion_superset_not_complete_consumption_attestation',
        'rows': len(rows), 'unique_task_texts': len({r['task_text'] for r in rows}),
        'extra_exclusion_sha256': hashlib.sha256(raw).hexdigest(), 'extra_exclusion_bytes': len(raw),
        'source_count': len(result.sources), 'source_files': result.sources,
        'source_inventory_sha256': hashlib.sha256(canonical(result.sources)).hexdigest(),
        'representation_counts': dict(Counter(k for r in rows for k in r['representation_kinds'])),
        'unresolved_dynamic_or_oversized_contexts': result.unresolved,
        'manual_complete_r_inventory_review_required': True, 'all_history_proven_complete': False,
        'new20_body_rows_read': 0, 'original80_body_rows_read': 0,
        'gpu_calls': 0, 'rhino_calls': 0, 'formal_claims_created': 0, 'formal_run_authorized': False,
        'limits': ['Visible/prepared cases are excluded even without execution proof',
            'Operation JSON proxies need manual natural-language/geometric equivalence review',
            'Numeric normalization and 0.92 text similarity do not prove semantic separation',
            'Unrecorded terminal/remote tasks and dynamic templates require owner review']}
    write('coverage-report.json', canonical(report) + b'\n')
    return {k: report[k] for k in ('status', 'rows', 'unique_task_texts', 'source_count',
        'extra_exclusion_sha256', 'new20_body_rows_read', 'original80_body_rows_read', 'formal_run_authorized')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--c5-root', type=Path, default=ROOT)
    parser.add_argument('--r-history-root', type=Path, action='append', required=True)
    parser.add_argument('--development-root', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    args = parser.parse_args()
    try: summary = export(collect(args.c5_root, args.r_history_root, args.development_root), args.output_directory, _worktrees())
    except (ValueError, OSError, SyntaxError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'historical_export_failed_no_private_candidate_read', 'error_type': type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True)); return 0


if __name__ == '__main__': raise SystemExit(main())
