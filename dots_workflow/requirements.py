"""Conservative reconciliation of explicit, user-supplied requirement records.

This is a structural consistency check, not a source or fact certification system.
Time alone never replaces a decision. Only valid explicit links change state.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
import math

_STATUSES = {"decision", "proposal", "retracted"}
_KINDS = {"primary", "secondary", "author_reported", "synthetic"}


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _json(value):
    """Require real JSON values, including string-only object keys."""
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json(item) for key, item in value.items())
    return False


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _cycles(graph):
    """Iterative SCC detection, including malformed records' declared links."""
    seen, order = set(), []
    for start in sorted(graph):
        if start in seen:
            continue
        stack = [(start, False)]
        while stack:
            node, done = stack.pop()
            if done:
                order.append(node)
            elif node not in seen:
                seen.add(node)
                stack.append((node, True))
                stack.extend((other, False) for other in reversed(sorted(graph[node])) if other not in seen)
    reverse = {node: set() for node in graph}
    for node, others in graph.items():
        for other in others:
            reverse[other].add(node)
    seen, components = set(), []
    for start in reversed(order):
        if start in seen:
            continue
        component, stack = set(), [start]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            component.add(node)
            stack.extend(reverse[node] - seen)
        if len(component) > 1 or start in graph[start]:
            components.append(sorted(component))
    return sorted(components)


def run(data: dict) -> dict:
    """Return deterministic issues, normalized records, and effective decision IDs.

    ``effective`` excludes a whole subject/scope when its active choices conflict
    or its explicit changes remain unresolved. Matching active decisions may all
    be effective. Source kind never confers authority; missing provenance is kept
    visible. A withdrawn replacement never automatically revives its predecessor.
    """
    issues, unknowns = [], set()

    def issue(severity, code, message, refs=()):
        issues.append({"severity": severity, "code": code, "message": message, "refs": sorted(set(refs))})

    if not isinstance(data, dict):
        issue("error", "invalid_input", "输入必须为 JSON 对象。")
        data = {}
    raw_records, raw_sources = data.get("records", []), data.get("sources", [])
    if not isinstance(raw_records, list):
        issue("error", "invalid_records", "records 必须为数组。")
        raw_records = []
    if not isinstance(raw_sources, list):
        issue("error", "invalid_sources", "sources 必须为数组。")
        raw_sources = []
    if not raw_records:
        issue("warning", "no_records", "尚未提供需求记录；无法完成需求对账。")

    def indexed(items, label):
        counts = Counter(item.get("id") for item in items if isinstance(item, dict) and _string(item.get("id")))
        for ident in sorted(key for key, count in counts.items() if count > 1):
            issue("error", "duplicate_" + label + "_id", f"{label} 的 ID {ident!r} 重复；拒绝该 ID 的全部记录，不任选一项。", [ident])
        result = {}
        for item in items:
            if not isinstance(item, dict) or not _string(item.get("id")):
                issue("error", "invalid_" + label + "_id", f"每条 {label} 必须为对象，并包含非空字符串 ID。")
            elif counts[item["id"]] == 1:
                result[item["id"]] = item
        return result

    source_inputs = indexed(raw_sources, "source")
    sources = {}
    for ident, source in sorted(source_inputs.items()):
        valid = True
        if not _string(source.get("title")):
            issue("error", "invalid_source_title", f"来源 {ident!r} 缺少非空标题。", [ident])
            valid = False
        if not isinstance(source.get("kind"), str) or source.get("kind") not in _KINDS:
            issue("error", "invalid_source_kind", f"来源 {ident!r} 的 kind 缺失或不受支持。", [ident])
            valid = False
        if "url" in source and not _string(source["url"]):
            issue("error", "invalid_source_url", f"来源 {ident!r} 如提供 URL，必须为非空字符串。", [ident])
            valid = False
        if valid:
            sources[ident] = {key: source[key] for key in ("id", "title", "kind", "url") if key in source}

    inputs = indexed(raw_records, "record")
    declared = {ident: set() for ident in inputs}
    for ident, raw in inputs.items():
        if isinstance(raw.get("supersedes"), list):
            declared[ident] = {target for target in raw["supersedes"] if _string(target) and target in inputs}
    cycle_components = _cycles(declared)
    cyclic = set()
    for component in cycle_components:
        cyclic.update(component)
        issue("error", "supersedes_cycle", "声明的替代关系存在循环；不应用循环成员发起的替代关系。", component)

    records, times, valid_ids, blocked = {}, {}, set(), set()
    for ident, raw in sorted(inputs.items()):
        valid = True
        record = {"id": ident}
        for field in ("subject", "scope", "status"):
            record[field] = raw.get(field) if isinstance(raw.get(field), str) else None
            if not _string(raw.get(field)):
                issue("error", "invalid_" + field, f"记录 {ident!r} 的 {field} 必须为非空字符串。", [ident])
                valid = False
        if record["status"] is not None and record["status"] not in _STATUSES:
            issue("error", "invalid_status", f"记录 {ident!r} 的状态不受支持；引用或转述文本不会升级为正式决定。", [ident])
            valid = False
        if "value" not in raw and record["status"] != "retracted":
            issue("error", "missing_value", f"记录 {ident!r} 缺少 value。", [ident])
            valid = False
        if not _json(raw.get("value")):
            issue("error", "invalid_value", f"记录 {ident!r} 的 value 必须为 JSON 数据，且数字必须有限。", [ident])
            valid = False
            record["value"] = None
        else:
            record["value"] = json.loads(_canonical(raw.get("value")))
        if isinstance(raw.get("text"), str):
            record["text"] = raw["text"]
        for field in ("source_ids", "supersedes", "retracts"):
            value = raw.get(field, [])
            if not isinstance(value, list) or any(not _string(item) for item in value):
                issue("error", "invalid_" + field, f"记录 {ident!r} 的 {field} 必须为非空字符串 ID 数组。", [ident])
                valid = False
                record[field] = []
            else:
                record[field] = sorted(set(value))
        timestamp = raw.get("decided_at")
        record["decided_at"] = timestamp if isinstance(timestamp, str) else None
        record["timestamp_state"] = "unknown"
        times[ident] = None
        if timestamp is None:
            unknowns.add(f"记录 {ident!r} 的时间未知。")
        else:
            try:
                if not isinstance(timestamp, str):
                    raise ValueError("not a string")
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    record["timestamp_state"] = "naive"
                    issue("warning", "naive_timestamp", f"记录 {ident!r} 的时间缺少时区，不能用于确定变更顺序。", [ident])
                    unknowns.add(f"记录 {ident!r} 的时区未知。")
                else:
                    record["timestamp_state"] = "known"
                    times[ident] = parsed
            except (ValueError, TypeError, OverflowError):
                record["timestamp_state"] = "invalid"
                issue("error", "invalid_timestamp", f"记录 {ident!r} 的时间不是有效的带时区 ISO 8601 时间。", [ident])
                unknowns.add(f"记录 {ident!r} 的时间无效。")
        record["source_provenance"] = [sources[source_id].copy() for source_id in record["source_ids"] if source_id in sources]
        if not record["source_ids"]:
            issue("warning", "missing_provenance", f"记录 {ident!r} 没有来源引用；检查器不认证来源。", [ident])
            unknowns.add(f"记录 {ident!r} 的来源依据未知。")
        for source_id in record["source_ids"]:
            if source_id not in sources:
                issue("error", "unknown_source_reference", f"记录 {ident!r} 引用的来源 {source_id!r} 不存在、ID 重复或内容无效。", [ident, source_id])
                unknowns.add(f"记录 {ident!r} 的来源 {source_id!r} 待确认。")
        record["state"] = "invalid" if not valid else record["status"]
        record["effective"] = False
        records[ident] = record
        if valid:
            valid_ids.add(ident)
        elif record["status"] == "decision" and record["subject"] and record["scope"]:
            blocked.add((record["subject"], record["scope"]))
        if ident in cyclic and record["status"] == "decision" and record["subject"] and record["scope"]:
            blocked.add((record["subject"], record["scope"]))

    def key(ident):
        return records[ident]["subject"], records[ident]["scope"]

    def block(ident):
        if records[ident]["subject"] and records[ident]["scope"]:
            blocked.add(key(ident))

    def check_link(actor, target, relation):
        """Return true only when identity, scope, kind and ordering are established."""
        record = records[actor]
        if target not in records:
            issue("error", "unknown_" + relation + "_reference", f"记录 {actor!r} 的 {relation} 引用了不存在或 ID 重复的记录 {target!r}。", [actor, target])
            block(actor)
            return False
        if actor not in valid_ids or target not in valid_ids:
            issue("error", "invalid_" + relation + "_record", f"{relation} 关系引用了无效记录。", [actor, target])
            block(actor)
            return False
        if records[target]["status"] != "decision":
            issue("error", "invalid_" + relation + "_target", f"{relation} 的目标必须为正式决定，不能是建议或撤回记录。", [actor, target])
            block(actor)
            return False
        if key(actor) != key(target):
            issue("error", "cross_scope_" + relation, f"{relation} 两端必须属于相同主题和范围。", [actor, target])
            block(actor)
            return False
        if times[actor] is None or times[target] is None:
            issue("warning", "unresolved_" + relation, f"{relation} 两端缺少有效的带时区时间，无法确定顺序。", [actor, target])
            unknowns.add(f"{relation} 关系 {actor!r} -> {target!r} 的先后顺序未知。")
            block(actor)
            return False
        if times[actor] <= times[target]:
            issue("error", "nonforward_" + relation, f"发起 {relation} 的记录必须严格晚于目标记录。", [actor, target])
            block(actor)
            return False
        return True

    # Establish withdrawal times before checking whether a replacement targeted
    # a decision that had already been withdrawn at the replacement's timestamp.
    retractions = defaultdict(list)
    for ident, record in records.items():
        if record["status"] == "retracted" and not record["retracts"]:
            issue("error", "missing_retraction_target", f"撤回记录 {ident!r} 必须在 retracts 中明确指定至少一条正式决定。", [ident])
            block(ident)
        if record["retracts"] and record["status"] != "retracted":
            issue("error", "invalid_retraction_actor", "只有明确标记为 retracted 的记录才能撤回正式决定。", [ident])
            if record["status"] == "decision":
                block(ident)
        else:
            for target in record["retracts"]:
                if check_link(ident, target, "retracts"):
                    retractions[target].append(ident)

    supersessions = defaultdict(set)
    for ident, record in records.items():
        if record["supersedes"] and record["status"] != "decision":
            issue("error", "invalid_supersedes_actor", "只有正式决定才能替代另一条决定；建议不能覆盖决定。", [ident])
            continue
        for target in record["supersedes"]:
            if ident in cyclic:
                continue
            if not check_link(ident, target, "supersedes"):
                continue
            if any(times[retraction] <= times[ident] for retraction in retractions[target]):
                issue("error", "supersedes_retracted_decision", "不能替代在替代记录生效时间之前已经撤回的决定。", [ident, target])
                block(ident)
                continue
            supersessions[ident].add(target)

    displaced = set().union(*supersessions.values()) if supersessions else set()
    active = set()
    for ident, record in records.items():
        record["superseded_by"] = sorted(actor for actor, targets in supersessions.items() if ident in targets)
        record["retracted_by"] = sorted(retractions[ident])
        if ident not in valid_ids:
            continue
        if record["status"] == "decision":
            if ident in retractions and retractions[ident]:
                record["state"] = "retracted"
            elif ident in displaced:
                record["state"] = "superseded"
            else:
                record["state"] = "active"
                active.add(ident)
        elif record["status"] == "retracted":
            record["state"] = "retraction"

    # Keep the historical displacement even when a replacing decision is later
    # withdrawn. An independently explicit active replacement can resolve it.
    covered = set()
    for ident in active:
        stack = list(supersessions[ident])
        while stack:
            target = stack.pop()
            if target not in covered:
                covered.add(target)
                stack.extend(supersessions[target])
    for ident in sorted(supersessions):
        abandoned = supersessions[ident] - covered
        if retractions[ident] and abandoned:
            issue("warning", "retracted_replacement_unresolved", "替代决定已撤回；此前被替代的决定不会自动恢复，需要明确的新决定。", [ident, *abandoned, *retractions[ident]])
            unknowns.add(f"替代决定 {ident!r} 撤回后，当前选择仍待确认。")
            block(ident)

    groups = defaultdict(list)
    for ident in sorted(active):
        groups[key(ident)].append(ident)
    conflicts = 0
    for group, members in sorted(groups.items()):
        choices = {_canonical(records[ident]["value"]) for ident in members}
        if any(records[ident]["value"] is None for ident in members):
            blocked.add(group)
            issue("warning", "unknown_decision_value", "仍有效候选决定的值为未知的 null，无法确定最终选择。", members)
            unknowns.add(f"范围 {group[1]!r} 中主题 {group[0]!r} 的决定值未知。")
        if len(choices) > 1:
            conflicts += 1
            blocked.add(group)
            issue("error", "conflicting_decisions", "相同主题和范围内的候选决定互相矛盾；不能仅凭时间较新自动选择。", members)
            for ident in members:
                records[ident]["state"] = "conflicted"
        for ident in members:
            records[ident]["effective"] = group not in blocked
    effective = sorted(ident for ident, record in records.items() if record["effective"])
    # Repeated malformed items do not produce duplicate messages. Sorting does
    # not depend on record/source order, graph traversal, or source list order.
    issues = sorted({_canonical(item): item for item in issues}.values(), key=lambda item: ({"error": 0, "warning": 1, "info": 2}[item["severity"]], item["code"], item["refs"], item["message"]))
    return {
        "engine": "requirements",
        "summary": {
            "input_records": len(raw_records), "accepted_records": len(valid_ids),
            "active_decisions": len(active), "effective_decisions": len(effective),
            "proposals": sum(records[ident]["status"] == "proposal" for ident in valid_ids),
            "superseded_decisions": sum(record["state"] == "superseded" for record in records.values()),
            "retracted_decisions": sum(record["status"] == "decision" and record["state"] == "retracted" for record in records.values()),
            "conflicting_scopes": conflicts, "unresolved_scopes": len(blocked),
            "errors": sum(item["severity"] == "error" for item in issues),
            "warnings": sum(item["severity"] == "warning" for item in issues),
            "certification": "仅对账结构和显式关系，不认证来源权威性或事实真实性。",
        },
        "issues": issues,
        "records": [records[ident] for ident in sorted(records)],
        "effective": effective,
        "unknowns": sorted(unknowns),
    }
