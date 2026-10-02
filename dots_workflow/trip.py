"""Offline consistency checks for supplied itinerary records, never a booking verdict.

Times must carry UTC offsets. Station/city names are compared literally, without
geocoding or alias inference. Required lodging nights and connection order must
be explicit. Source contents, including notes, are untrusted data only.
"""
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import math
import re


_SCOPE = (
    "仅比较输入记录和明确给定的门槛；未核验真实班次、路线、换乘耗时、来源内容或预订状态。"
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _text(value):
    return value if isinstance(value, str) and value.strip() else None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return value >= 0 and math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class _Check:
    def __init__(self):
        self.issues = []
        self.unknowns = set()

    def add(self, severity, code, message, *refs, unknown=False):
        self.issues.append({"severity": severity, "code": code,
                            "message": message, "refs": sorted(set(refs))})
        if unknown:
            self.unknowns.add(message)

    def records(self, data, field, required=False):
        value = data.get(field, [])
        if not isinstance(value, list):
            self.add("error", "invalid_collection", f"{field} 必须为数组。", field,
                     unknown=True)
            return []
        if required and not value:
            self.add("warning", "missing_segments", "未提供交通分段，无法完成行程核对。", field,
                     unknown=True)
        records = []
        for raw in sorted(value, key=_canonical):
            fallback = f"missing-{field}-{sha256(_canonical(raw).encode()).hexdigest()[:12]}"
            if not isinstance(raw, dict):
                self.add("error", "invalid_record", f"{field} 中每条记录必须为对象。",
                         fallback, unknown=True)
                continue
            ident = _text(raw.get("id"))
            if not ident:
                ident = fallback
                self.add("error", "missing_id", f"{field} 记录缺少非空字符串 ID。",
                         ident, unknown=True)
            records.append((ident, raw))
        counts = Counter(ident for ident, _ in records)
        for ident, count in sorted(counts.items()):
            if count > 1:
                self.add("error", f"duplicate_{field.rstrip('s')}_id",
                         f"{field} 的 ID {ident!r} 出现 {count} 次，引用无法唯一确定，不会任选或覆盖。",
                         ident, unknown=True)
        return records

    def time(self, raw, field, ident):
        value = raw.get(field)
        if not _text(value):
            self.add("warning", "missing_time", f"{ident}：缺少 {field}。", ident,
                     unknown=True)
            return None
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}", value):
                raise ValueError
            parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                self.add("warning", "missing_timezone",
                         f"{ident}：{field} 缺少 UTC 偏移量；不会假定时区。",
                         ident, unknown=True)
                return None
            # Also catches UTC conversion overflow at datetime's boundary years.
            parsed.astimezone(timezone.utc)
            return parsed
        except (ValueError, OverflowError):
            self.add("error", "invalid_time", f"{ident}：{field} 不是受支持的 ISO 8601 时间戳。",
                     ident, unknown=True)
            return None

    def day(self, value, field, ident):
        try:
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError
            return date.fromisoformat(value)
        except ValueError:
            self.add("error", "invalid_date", f"{ident}：{field} 必须为有效的 YYYY-MM-DD 日期。",
                     ident, unknown=True)
            return None

    def location(self, value, field, ident, flight=False):
        value = value if isinstance(value, dict) else {}
        result = {key: _text(value.get(key)) for key in ("city", "station", "terminal")}
        for key in ("city", "station"):
            if result[key] is None:
                self.add("warning", "missing_location", f"{ident}：{field}.{key} 未知。",
                         ident, unknown=True)
        if flight and result["terminal"] is None:
            self.add("warning", "missing_terminal", f"{ident}：{field}.terminal 航站楼未知。",
                     ident, unknown=True)
        return result

    def sources(self, raw, ident, counts):
        refs = raw.get("source_ids")
        if not isinstance(refs, list) or not refs:
            self.add("warning", "missing_source_reference", f"{ident}：未提供 source_ids，来源待确认。",
                     ident, unknown=True)
            return []
        if any(_text(ref) is None for ref in refs):
            self.add("error", "invalid_source_reference", f"{ident}：source_ids 只能包含非空字符串。",
                     ident, unknown=True)
        result = sorted(set(ref for ref in refs if _text(ref)))
        for ref in result:
            if not counts.get(ref):
                self.add("error", "unknown_source_reference", f"{ident}：引用来源 {ref!r} 不存在。",
                         ident, ref, unknown=True)
            elif counts[ref] > 1:
                self.add("error", "ambiguous_source_reference", f"{ident}：来源 {ref!r} 重复，引用无法唯一确定。",
                         ident, ref, unknown=True)
        return result


def run(data: dict) -> dict:
    """Return deterministic JSON-compatible findings without modifying input.

    Extensions to the core segments/connections/lodgings schema:
    - from/to.terminal (required to assess airport terminal continuity)
    - trip_id, required_nights and stays (alias for lodgings) for date-only coverage
    - local_time/timezone are explicitly unsupported named-zone/DST inputs
    - notes are returned under untrusted_source_data and are never acted upon
    """
    check = _Check()
    if not isinstance(data, dict):
        check.add("error", "invalid_input", "输入必须为对象。", unknown=True)
        data = {}
    sources = check.records(data, "sources")
    source_counts = Counter(ident for ident, _ in sources)
    for ident, raw in sources:
        for field in ("title", "kind"):
            if not _text(raw.get(field)):
                check.add("warning", "incomplete_source", f"来源 {ident}：缺少 {field}。",
                          ident, unknown=True)
    if "local_time" in data or _text(data.get("default_timezone")) or _text(data.get("timezone")):
        check.add("warning", "explicitly_unsupported_timezone_case",
                  "暂不支持命名时区或夏令时消歧，请提供含明确 UTC 偏移量的时间戳。"
                  "不会据此把本地时间、时区名称或 fold 自动解析成唯一时刻。", "timezone", unknown=True)

    parsed = []
    for ident, raw in check.records(data, "segments", required=True):
        mode = _text(raw.get("mode"))
        if not mode:
            check.add("warning", "missing_mode", f"{ident}：交通方式 mode 未知。", ident, unknown=True)
        departure = check.time(raw, "departure", ident)
        arrival = check.time(raw, "arrival", ident)
        start = departure.astimezone(timezone.utc) if departure else None
        end = arrival.astimezone(timezone.utc) if arrival else None
        duration = (end - start).total_seconds() / 60 if start and end else None
        if duration is not None and duration < 0:
            check.add("error", "negative_duration", f"{ident}：按 UTC 比较，到达早于出发 {-duration:g} 分钟。", ident)
        status = raw.get("booking_status", "unknown")
        if status not in ("confirmed", "unconfirmed", "unknown"):
            check.add("error", "invalid_booking_status", f"{ident}：booking_status 无效。", ident, unknown=True)
            status = "unknown"
        if status != "confirmed":
            check.add("warning", "booking_not_confirmed", f"{ident}：输入的 booking_status 为 {status}，预订仍待确认；程序未核验订单。",
                      ident, unknown=True)
        flight = mode in ("flight", "air", "airplane")
        result = {"id": ident, "mode": mode,
                  "from": check.location(raw.get("from"), "from", ident, flight),
                  "to": check.location(raw.get("to"), "to", ident, flight),
                  "departure": _text(raw.get("departure")), "arrival": _text(raw.get("arrival")),
                  "departure_utc": _iso(departure) if departure else None,
                  "arrival_utc": _iso(arrival) if arrival else None,
                  "duration_minutes": duration, "booking_status": status,
                  "booking_status_basis": "supplied_only",
                  "source_ids": check.sources(raw, ident, source_counts),
                  "temporal_status": "unknown" if duration is None else ("invalid" if duration < 0 else "checked")}
        parsed.append((result, start, end))
    parsed.sort(key=lambda item: (item[1] is None, item[1] or datetime.max.replace(tzinfo=timezone.utc),
                                  item[0]["id"], _canonical(item[0])))
    segments = [item[0] for item in parsed]
    segment_counts = Counter(item["id"] for item in segments)
    unique = {item[0]["id"]: item for item in parsed if segment_counts[item[0]["id"]] == 1}
    valid = [item for item in parsed if item[1] is not None and item[2] is not None and item[2] >= item[1]]
    for index, (left, lstart, lend) in enumerate(valid):
        for right, rstart, rend in valid[index + 1:]:
            overlap = (min(lend, rend) - max(lstart, rstart)).total_seconds() / 60
            if overlap > 0:
                check.add("error", "segment_overlap",
                          f"{left['id']} 与 {right['id']}：输入时间区间重叠 {overlap:g} 分钟。",
                          left["id"], right["id"])

    connections = []
    raw_connections = data.get("connections", [])
    if not isinstance(raw_connections, list):
        check.add("error", "invalid_collection", "connections 必须为数组。", "connections", unknown=True)
        raw_connections = []
    for raw in sorted(raw_connections, key=_canonical):
        if not isinstance(raw, dict):
            check.add("error", "invalid_connection", "衔接记录必须为对象。", "connections", unknown=True)
            continue
        before, after = _text(raw.get("from_segment")), _text(raw.get("to_segment"))
        refs = [ref for ref in (before, after) if ref]
        label = f"衔接 {before!r} → {after!r}"
        minimum = raw.get("min_buffer_minutes")
        transfer = raw.get("transfer_minutes")
        minimum_valid = _number(minimum)
        transfer_valid = _number(transfer)
        if not minimum_valid:
            check.add("error", "invalid_buffer", f"{label}：min_buffer_minutes 必须为有限非负数。",
                      *refs, unknown=True)
        if transfer is not None and not transfer_valid:
            check.add("error", "invalid_transfer_duration", f"{label}：transfer_minutes 必须为有限非负数。",
                      *refs, unknown=True)
        result = {"from_segment": before, "to_segment": after,
                  "min_buffer_minutes": minimum if minimum_valid else None,
                  "transfer_minutes": transfer if transfer_valid else None,
                  "available_minutes": None, "required_minutes": None,
                  "shortfall_minutes": None, "margin_minutes": None, "check_status": "unknown"}
        connections.append(result)
        if before not in unique or after not in unique:
            check.add("error", "unknown_or_ambiguous_segment_reference", f"{label}：前后分段必须均能通过 ID 唯一定位。",
                      *refs, unknown=True)
            continue
        if before == after:
            check.add("error", "self_connection", f"{label}：分段不能衔接自身。", *refs)
            continue
        left, _, arrival = unique[before]
        right, departure, _ = unique[after]
        a, b = left["to"], right["from"]
        different_station = bool(a["station"] and b["station"] and a["station"] != b["station"])
        different_city = bool(a["city"] and b["city"] and a["city"] != b["city"])
        different_terminal = bool(a["terminal"] and b["terminal"] and a["terminal"] != b["terminal"])
        for different, code, description in ((different_station, "different_station", "车站名称"),
                                               (different_city, "different_city", "城市名称"),
                                               (different_terminal, "different_terminal", "航站楼名称")):
            if different:
                check.add("warning", code, f"{label}：输入的{description}不同；不会假定为同一地点或推断路线。", *refs)
        unknown_location = any(a[key] is None or b[key] is None for key in ("city", "station"))
        airport = left["mode"] in ("flight", "air", "airplane") or right["mode"] in ("flight", "air", "airplane")
        unknown_terminal = airport and (a["terminal"] is None or b["terminal"] is None)
        if unknown_terminal:
            check.add("warning", "missing_terminal", f"{label}：缺少航站楼信息，无法判断是否同航站楼。", *refs, unknown=True)
        same_place = not (different_city or different_station or different_terminal or unknown_location or unknown_terminal)
        if transfer is None and same_place:
            transfer, transfer_valid = 0, True
            result["transfer_minutes"] = 0
        elif not transfer_valid:
            check.add("warning", "unknown_transfer_duration", f"{label}：换乘耗时未知；不同或未知地点之间需要明确提供 transfer_minutes。",
                      *refs, unknown=True)
        if arrival is None or departure is None:
            check.add("warning", "connection_time_unknown", f"{label}：到达时间或后续出发时间未知。", *refs, unknown=True)
            continue
        delta = departure - arrival
        available_exact = Decimal((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds) / Decimal(60000000)
        available = float(available_exact)
        result["available_minutes"] = available
        if available < 0:
            check.add("error", "connection_order_conflict", f"{label}：后续出发比前段到达早 {-available:g} 分钟，明确衔接顺序冲突。", *refs)
        # Even without transfer data, an explicit minimum gives a useful lower bound.
        required_exact = Decimal(str(minimum)) + Decimal(str(transfer)) if minimum_valid and transfer_valid else None
        required = float(required_exact) if required_exact is not None else None
        if required is not None and not _number(required):
            check.add("error", "invalid_buffer", f"{label}：给定缓冲总额超出受支持的数值范围。", *refs, unknown=True)
            required = required_exact = None
        result["required_minutes"] = required
        bound = required if required is not None else minimum if minimum_valid else None
        bound_exact = required_exact if required_exact is not None else Decimal(str(minimum)) if minimum_valid else None
        if bound_exact is not None and available_exact < bound_exact:
            result["check_status"] = "below_requested_minimum"
            result["shortfall_minutes"] = float(bound_exact - available_exact)
            result["margin_minutes"] = float(available_exact - required_exact) if required_exact is not None else None
            check.add("warning", "buffer_below_requested_minimum",
                      f"{label}：可用 {available:g} 分钟，比输入的{'合计' if required is not None else '仅最低缓冲'}门槛 {bound:g} 分钟"
                      f"少 {result['shortfall_minutes']:g} 分钟；这不是实际交通耗时预测。", *refs)
        elif required is not None:
            result["shortfall_minutes"] = 0
            result["margin_minutes"] = float(available_exact - required_exact)
            result["check_status"] = "at_requested_minimum" if available_exact == required_exact else "above_requested_minimum"
            if available_exact == required_exact:
                check.add("warning", "buffer_no_margin", f"{label}：恰好达到输入门槛 {required:g} 分钟，没有额外余量。", *refs)
        if left["temporal_status"] == "invalid" or right["temporal_status"] == "invalid":
            result["check_status"] = "invalid_segment_times"

    lodging_data = data
    if "stays" in data and "lodgings" not in data:
        lodging_data = dict(data, lodgings=data["stays"])
    elif "stays" in data and "lodgings" in data:
        check.add("error", "ambiguous_lodging_collection", "lodgings 和 stays 只能提供其中一组；同时提供时，两组均不用于住宿覆盖判断。",
                  "lodgings", "stays", unknown=True)
        lodging_data = dict(data, lodgings=[])
    lodgings = []
    stay_times = []
    trip_id = _text(data.get("trip_id"))
    for ident, raw in check.records(lodging_data, "lodgings"):
        start = check.day(raw.get("check_in"), "check_in", ident)
        end = check.day(raw.get("check_out"), "check_out", ident)
        if start is not None and end is not None and end <= start:
            check.add("error", "invalid_lodging_interval", f"{ident}：退房 check_out 必须晚于入住 check_in。", ident)
        city = _text(raw.get("city"))
        if not city:
            check.add("warning", "missing_location", f"{ident}：住宿城市未知。", ident, unknown=True)
        stay_trip = _text(raw.get("trip_id"))
        lodging = {"id": ident, "trip_id": stay_trip, "city": city,
                   "check_in": start.isoformat() if start else None,
                   "check_out": end.isoformat() if end else None,
                   "source_ids": check.sources(raw, ident, source_counts)}
        lodgings.append(lodging)
        stay_times.append((lodging, start, end))
    lodging_counts = Counter(item["id"] for item in lodgings)
    required_nights = []
    if "required_nights" in data:
        nights = data["required_nights"]
        if not isinstance(nights, list):
            check.add("error", "invalid_collection", "required_nights 必须为 YYYY-MM-DD 日期数组。", "required_nights", unknown=True)
            nights = []
        for value in sorted(nights, key=_canonical):
            day = check.day(value, "required_nights", "required_nights")
            if day:
                required_nights.append(day)
        if not trip_id:
            check.add("warning", "missing_trip_id", "住宿覆盖判断需要 trip_id；不会假定住宿属于本次旅行。",
                      "trip_id", unknown=True)
    required_nights = sorted(set(required_nights))
    eligible = []
    for lodging, start, end in stay_times:
        if required_nights and (not trip_id or not lodging["trip_id"]):
            check.add("warning", "unknown_stay_trip", f"{lodging['id']}：所属旅行未知，不用于住宿覆盖判断。",
                      lodging["id"], unknown=True)
        elif trip_id and lodging["trip_id"] and lodging["trip_id"] != trip_id:
            check.add("info", "different_trip_stay", f"{lodging['id']}：属于另一趟旅行，不用于本次住宿覆盖判断。", lodging["id"])
        elif trip_id and lodging["trip_id"] == trip_id and start and end and end > start and lodging_counts[lodging["id"]] == 1:
            eligible.append((lodging, start, end))
            if required_nights and not any(start <= night < end for night in required_nights):
                check.add("warning", "stay_outside_trip_window", f"{lodging['id']}：输入住宿日期未覆盖本次旅行任何一个所需夜晚，请核对日期。", lodging["id"])
    uncovered = [night.isoformat() for night in required_nights
                 if not any(start <= night < end for _, start, end in eligible)]
    for night in uncovered:
        check.add("warning", "uncovered_night", f"本次旅行缺少可唯一定位且覆盖 {night} 这一晚的住宿记录，住宿仍待确认。", trip_id or "trip_id", unknown=True)
    for index, (left, start, end) in enumerate(eligible):
        for right, rstart, rend in eligible[index + 1:]:
            if max(start, rstart) < min(end, rend):
                check.add("warning", "lodging_overlap", f"{left['id']} 与 {right['id']}：同次旅行的住宿日期重叠，请核对是否有意安排。", left["id"], right["id"])
    if lodgings:
        check.unknowns.add("住宿仅提供日期；未核验具体入住和退房时刻、时区及预订状态。")
    unknowns = sorted(check.unknowns)
    # Dedup identical findings, then use stable severity/code/reference order.
    issues = list({_canonical(issue): issue for issue in check.issues}.values())
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda issue: (order[issue["severity"]], issue["code"], issue["refs"], issue["message"]))
    summary = {"segment_count": len(segments), "connection_count": len(connections),
               "lodging_count": len(lodgings), "timed_segment_count": len(valid),
               "error_count": sum(issue["severity"] == "error" for issue in issues),
               "warning_count": sum(issue["severity"] == "warning" for issue in issues),
               "info_count": sum(issue["severity"] == "info" for issue in issues),
               "unknown_count": len(unknowns), "scope": _SCOPE}
    result = {"engine": "trip", "summary": summary, "issues": issues, "segments": segments,
              "sources": [{"id": ident, "title": raw.get("title"), "kind": raw.get("kind"),
                           "url": raw.get("url"), "text": raw.get("text"),
                           "verification_status": "not_verified", "untrusted_source_data": dict(raw)}
                          for ident, raw in sources],
              "connections": sorted(connections, key=_canonical),
              "lodgings": sorted(lodgings, key=lambda item: (item["check_in"] is None, item["check_in"] or "", item["id"], _canonical(item))),
              "required_nights": [night.isoformat() for night in required_nights],
              "uncovered_nights": uncovered, "unknowns": unknowns}
    if "notes" in data:
        # Pure data preservation, not instruction processing or permission.
        result["untrusted_source_data"] = {"notes": data["notes"]}
    return result
