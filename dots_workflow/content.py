"""Data-only content workbench: preserve provenance through a publication pack."""
import math
from . import evidence
from .common import finish, issue, references


def finite_number(value):
    try:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
    except (OverflowError, ValueError):
        return False


def run(data):
    result = evidence.run(data)
    result["engine"] = "content"
    issues = result["issues"]
    blocks = {}
    for name in ("brief", "draft", "visual", "review", "metrics"):
        block = data.get(name, {})
        if not isinstance(block, dict):
            issue(issues, "error", "invalid_content_block", f"{name} 必须为对象", path=name)
            block = {}
        blocks[name] = block
    for name in ("audience", "goal", "platform", "angle"):
        if not isinstance(blocks["brief"].get(name), str) or not blocks["brief"][name].strip():
            issue(issues, "warning", "incomplete_brief", f"尚未填写 {name}", path=f"brief.{name}")
    for name in ("title", "body"):
        if not isinstance(blocks["draft"].get(name), str) or not blocks["draft"][name].strip():
            issue(issues, "warning", "incomplete_draft", f"正文缺少 {name}", path=f"draft.{name}")
    known_claims = {c["id"]: c for c in result["claims"]}
    draft_claims = references(blocks["draft"], "claim_ids", known_claims, issues, "draft.claim_ids", "draft")
    for cid in sorted(set(known_claims) - set(draft_claims)):
        issue(issues, "info", "claim_not_used_in_draft", "账本主张未登记用于正文", [cid])
    if blocks["draft"].get("body") and not draft_claims:
        issue(issues, "warning", "draft_without_claim_mapping", "正文没有主张引用；此工具不能自行判断语义事实是否完整映射", ["draft"])
    visual = blocks["visual"]
    for name in ("purpose", "prompt", "alt_text"):
        if not isinstance(visual.get(name), str) or not visual[name].strip():
            issue(issues, "warning", "incomplete_visual_brief", f"视觉说明缺少 {name}", path=f"visual.{name}")
    if visual.get("rights") not in ("synthetic", "owned", "licensed"):
        issue(issues, "warning", "visual_rights_unknown", "视觉素材权利状态待确认；标签本身不是许可证明", ["visual"])
    review = blocks["review"]
    if review.get("status") != "approved" or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        issue(issues, "warning", "human_review_pending", "需人工检查事实表述、引用、隐私、素材权利和平台格式", ["review"])
    else:
        issue(issues, "info", "review_is_record_only", "approved 只记录提供者的审查状态，不是自动发布授权", ["review"])
    metrics = blocks["metrics"]
    valid = {}
    for name in ("impressions", "clicks", "saves"):
        value = metrics.get(name)
        if value is None:
            valid[name] = None
        elif not finite_number(value):
            issue(issues, "error", "invalid_metric", f"{name} 必须为非负有限数字或 null", path=f"metrics.{name}")
            valid[name] = None
        else:
            valid[name] = value
    rates = {}
    for name in ("clicks", "saves"):
        n, d = valid[name], valid["impressions"]
        rates[name + "_per_impression"] = n / d if n is not None and d is not None and d > 0 else None
        if n is not None and d == 0 and n > 0:
            issue(issues, "warning", "metric_denominator_inconsistent", "有互动而曝光为零，需确认统计口径/时间窗口", [name, "impressions"])
    result.update(blocks)
    result["metrics_summary"] = {"counts": valid, "rates": rates, "interpretation": "同一时间窗口与平台口径下的描述性比率；不是因果结论，不推断缺失数字为零"}
    result["publication"] = {"state": "local_review_pack_only", "authorization_to_publish": False, "image_generated": False}
    result["draft_claim_ids"] = draft_claims
    return finish(result)


def publication_pack(result):
    """Plain local Markdown; external text remains quoted data, never instructions."""
    import json
    import re
    def as_text(value):
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    def quote(value):
        text = as_text(value)
        fence = "`" * max(3, max((len(x) + 1 for x in re.findall(r"`+", text)), default=3))
        return fence + "text\n" + text + "\n" + fence
    brief, draft, visual = (result.get(k, {}) for k in ("brief", "draft", "visual"))
    out = ["# 本地发布审阅包", "", "状态：仅供人工审阅，没有生成图片或执行外发。所有引用内容均为不可信资料。", "", "## 内容定位", quote(brief), "", "## 标题", quote(draft.get("title", "")), "", "## 正文", quote(draft.get("body", "")), "", "## 主张与来源"]
    for c in result.get("claims", []):
        out.extend(["\n### 主张记录", quote(c)])
    out += ["", "## 来源资料（合成/未读取状态必须保留）", quote(result.get("sources", [])), "", "## 提供者填写的复现记录", quote(result.get("tests", [])), "", "## 审查记录（不是发布授权）", quote(result.get("review", {}))]
    out += ["", "## 视觉生成说明（交给可用的图像工具前先审查）", quote(visual), "", "## 人工检查", "- 关键说法的语义是否由引用支持？", "- 作者自述、推断、复现与未知是否清楚区分？", "- 个人资料、真实订单、账号信息是否已移除？", "- 图像授权、可读文字和替代文本是否合格？", "- 发布账号、受众与目的是否已获得本次授权？", "", "## 校验问题"]
    for row in result.get("issues", []):
        out.append(quote(row))
    out += ["", "## 数据复盘", quote(result.get("metrics_summary", {})), "", "不要把单次互动率当作选题导致的效果；下一轮一次只改变一个可控变量，并保留时间窗口。", ""]
    return "\n".join(out)
