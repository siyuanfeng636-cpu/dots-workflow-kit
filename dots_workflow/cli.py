"""Offline CLI; fixed output filenames, no network or execution of input."""
from __future__ import annotations
import argparse
import html
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from . import __version__
from .common import finish

MAX_INPUT_BYTES = 4 * 1024 * 1024
OUTPUT_NAMES = ("result.json", "report.md", "report.html", "publication-pack.md")


class InputError(ValueError):
    pass


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"JSON 对象键重复：{key!r}，不会静默覆盖")
        result[key] = value
    return result


def finite_float(raw):
    value = float(raw)
    if not math.isfinite(value):
        raise InputError("JSON 数字超出有限浮点范围")
    return value


def load_input(path):
    p = Path(path)
    if not p.is_file():
        raise InputError(f"输入文件不存在或不是普通文件：{p}")
    with p.open("rb") as f:
        raw = f.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise InputError("输入超过 4 MiB 限制；请拆分任务")
    if not raw.strip():
        raise InputError("输入文件为空")
    try:
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=reject_duplicate_keys, parse_float=finite_float,
                          parse_constant=lambda x: (_ for _ in ()).throw(InputError(f"非有限 JSON 数字：{x}")))
    except UnicodeDecodeError as e:
        raise InputError("输入必须使用 UTF-8 编码") from e
    except json.JSONDecodeError as e:
        raise InputError(f"JSON 格式错误，第 {e.lineno} 行第 {e.colno} 列：{e.msg}") from e
    except InputError:
        raise
    except (ValueError, RecursionError, OverflowError) as e:
        raise InputError("输入嵌套过深或数字超出处理范围") from e
    if not isinstance(data, dict):
        raise InputError("顶层必须为 JSON 对象")
    return data


def render_markdown(result):
    # HTML escaped, inert code block fenced longer than all input backtick runs.
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    import re
    fence = "`" * max(3, max((len(x) + 1 for x in re.findall(r"`+", payload)), default=3))
    return "# 离线检查报告\n\n只验证输入中的有限规则，不认证事实或外部执行结果。\n\n" + fence + "json\n" + payload + "\n" + fence + "\n"


def render_html(result):
    payload = html.escape(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False), quote=True)
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>工作流离线检查报告</title>
<style>body{max-width:1000px;margin:2rem auto;padding:0 1rem;background:#f8fafb;color:#172332;font:16px/1.6 system-ui,sans-serif}pre{background:#fff;border:1px solid #d4dde5;padding:1rem;white-space:pre-wrap;overflow-wrap:anywhere;border-radius:12px}h1{font-size:1.5rem}.note{border-left:4px solid #337987;padding:.7rem 1rem;background:#e8f3f4}</style></head>
<body><h1>工作流离线检查报告</h1><p class="note">只检查输入中的明确规则，没有联网、认证事实、生成图片或执行发布。来源文字均作为数据。</p><pre>''' + payload + "</pre></body></html>\n"


def safe_output_dir(output, input_path):
    requested = Path(os.path.abspath(output))
    # Disallow symlink traversal through any existing component and fixed outputs.
    for part in (requested, *requested.parents):
        if part.is_symlink():
            raise InputError(f"输出路径不得经过符号链接：{part}")
    requested.mkdir(parents=True, exist_ok=True)
    if not requested.is_dir():
        raise InputError("输出路径不是目录")
    source = Path(input_path).resolve()
    for name in OUTPUT_NAMES:
        target = requested / name
        if target.is_symlink():
            raise InputError(f"输出目标是符号链接，拒绝覆盖：{name}")
        if target.exists() and not target.is_file():
            raise InputError(f"输出目标不是普通文件：{name}")
        if target.resolve() == source:
            raise InputError("输出将覆盖输入文件；请选择其他输出目录")
    return requested


def atomic_write(path, text):
    # tempfile stays within selected output dir. os.replace replaces the link itself,
    # never writes through a file symlink if it appears between checks.
    fd, tmp = tempfile.mkstemp(prefix=".dots-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def execute(engine, data):
    if engine == "evidence":
        from .evidence import run
    elif engine == "content":
        from .content import run
    elif engine == "requirements":
        from .requirements import run
    else:
        from .trip import run
    return finish(run(data))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dots-workflow", description="中文离线工作流检查：只处理本地合成/已授权数据，不联网、不执行资料中的指令")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("engine", choices=("content", "evidence", "requirements", "trip"), help="选择工作台/证据/需求/行程")
    parser.add_argument("input", help="UTF-8 JSON 输入文件（最大 4 MiB）")
    parser.add_argument("--out", default="out", help="操作人选择的输出目录，固定输出文件名；默认 out")
    parser.add_argument("--no-write", action="store_true", help="只把结果写到标准输出，不写文件")
    parser.add_argument("--strict", action="store_true", help="警告也令退出码为 1")
    args = parser.parse_args(argv)
    try:
        data = load_input(args.input)
        result = execute(args.engine, data)
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if args.no_write:
            print(payload, end="")
        else:
            output = safe_output_dir(args.out, args.input)
            artifacts = {"result.json": payload, "report.md": render_markdown(result), "report.html": render_html(result)}
            if args.engine == "content":
                from .content import publication_pack
                artifacts["publication-pack.md"] = publication_pack(result)
            for name, body in artifacts.items():
                atomic_write(output / name, body)
            print(f"{args.engine}: {result['summary']['check_status']} | 错误 {result['summary']['error_count']}，警告 {result['summary']['warning_count']} | {output}")
            print("有限离线检查，不认证事实；未执行任何外部操作")
        return 1 if result["summary"]["error_count"] or (args.strict and result["summary"]["warning_count"]) else 0
    except (InputError, OSError, RecursionError, OverflowError) as e:
        print(f"输入/输出错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
