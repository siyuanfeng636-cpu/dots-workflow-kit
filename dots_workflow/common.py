"""Shared data-only validation helpers."""
from __future__ import annotations
import json
from datetime import datetime
from urllib.parse import urlsplit


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def issue(issues, severity, code, message, refs=(), path=None):
    row = {"severity": severity, "code": code, "message": message, "refs": sorted(set(str(x) for x in refs))}
    if path is not None:
        row["path"] = path
    issues.append(row)


def rows(data, name, issues):
    value = data.get(name, [])
    if not isinstance(value, list):
        issue(issues, "error", "invalid_collection", f"{name} 必须为数组", path=name)
        return []
    result = []
    for i, row in enumerate(value):
        if not isinstance(row, dict):
            issue(issues, "error", "invalid_record", f"{name}[{i}] 必须为对象", path=f"{name}[{i}]")
        else:
            result.append((i, row))
    return result


def unique_rows(data, name, noun, issues):
    entries = rows(data, name, issues)
    groups = {}
    for i, row in entries:
        identifier = row.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            issue(issues, "error", f"missing_{noun}_id", f"{name}[{i}] 缺少非空字符串 ID", path=f"{name}[{i}].id")
            continue
        groups.setdefault(identifier, []).append((i, row))
    unique = {}
    for identifier, matches in sorted(groups.items()):
        if len(matches) > 1:
            issue(issues, "error", f"duplicate_{noun}_id", f"ID {identifier} 重复；不会覆盖或任选一项", [identifier])
        else:
            unique[identifier] = matches[0]
    return unique, entries


def source_index(data, issues):
    index, entries = unique_rows(data, "sources", "source", issues)
    for identifier, (i, row) in index.items():
        url = row.get("url")
        if url is not None:
            if not isinstance(url, str):
                issue(issues, "error", "invalid_url", "来源 URL 必须为字符串或 null", [identifier], f"sources[{i}].url")
            else:
                try:
                    p = urlsplit(url)
                    if p.scheme.lower() not in ("http", "https"):
                        issue(issues, "error", "unsupported_url_scheme", "仅记录 http/https URL；不会请求链接", [identifier], f"sources[{i}].url")
                    elif not p.hostname or p.username is not None or p.password is not None:
                        issue(issues, "error", "invalid_url", "URL 缺少主机或包含不允许的认证信息", [identifier], f"sources[{i}].url")
                except ValueError:
                    issue(issues, "error", "invalid_url", "来源 URL 格式错误", [identifier], f"sources[{i}].url")
        # A syntactically valid URL, source status or source kind is not proof.
        if row.get("status") in (None, "not_fetched") or not row.get("text"):
            issue(issues, "warning", "source_not_verified", "来源内容未提供或未读取；链接/标签不构成事实核验", [identifier])
        if row.get("status") == "synthetic":
            issue(issues, "info", "synthetic_source", "这是合成演示资料，不能作为真实事实证据", [identifier])
    return index, entries


def references(row, key, known, issues, path, owner):
    value = row.get(key, [])
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        issue(issues, "error", "invalid_reference_list", f"{key} 必须为非空字符串 ID 数组", [owner], path)
        return []
    for i, identifier in enumerate(value):
        if identifier not in known:
            issue(issues, "error", "unknown_source_reference" if key == "source_ids" else "unknown_claim_reference", f"引用 {identifier} 不存在或 ID 重复而不可用", [owner, identifier], f"{path}[{i}]")
    return sorted(set(value))


def finish(result):
    issues = result.setdefault("issues", [])
    result["issues"] = sorted(issues, key=lambda row: (row.get("severity", ""), row.get("code", ""), canonical(row)))
    summary = result.setdefault("summary", {})
    summary.update({f"{s}_count": sum(x.get("severity") == s for x in issues) for s in ("error", "warning", "info")})
    summary["check_status"] = ("checks_failed" if summary["error_count"] else "needs_review" if summary["warning_count"] else "passed_limited_checks")
    result["verification_boundary"] = "只检查输入中的结构、引用及明确规则；没有访问来源、认证事实、连接 dots/Codex、预订或发布。"
    return result
