"""Evidence ledger validation, not factual certification."""
from .common import finish, issue, unique_rows, source_index, references, canonical

LEVELS = {"author_report", "official", "locally_reproduced", "inference", "opinion", "unknown"}


def run(data):
    issues = []
    sources, source_rows = source_index(data, issues)
    claims, claim_rows = unique_rows(data, "claims", "claim", issues)
    tests, test_rows = unique_rows(data, "tests", "test", issues)
    if not claim_rows:
        issue(issues, "warning", "no_claims", "没有可检查的主张；不能据空输入视为完成证据检查")
    ledger = []
    used = set()
    for identifier, (i, row) in claims.items():
        level = row.get("evidence_level", "unknown")
        if not isinstance(level, str) or level not in LEVELS:
            issue(issues, "error", "invalid_evidence_level", "证据级别不受支持，按 unknown 保留", [identifier], f"claims[{i}].evidence_level")
            level = "unknown"
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            issue(issues, "error", "missing_claim_text", "主张缺少正文", [identifier], f"claims[{i}].text")
        refs = references(row, "source_ids", sources, issues, f"claims[{i}].source_ids", identifier)
        used.update(refs)
        if not refs and level not in ("opinion", "unknown", "locally_reproduced"):
            issue(issues, "warning", "unsupported_claim", "主张没有来源引用；需要补充证据或降级表达", [identifier])
        if level in ("unknown", "inference"):
            issue(issues, "warning", "claim_requires_review", "未知/推断应保留限定语并人工审查", [identifier])
        reproduction = None
        if level == "locally_reproduced":
            test_id = row.get("test_id")
            test = tests.get(test_id) if isinstance(test_id, str) else None
            if not test or test[1].get("status") != "passed" or not isinstance(test[1].get("command"), str) or not test[1]["command"].strip() or not isinstance(test[1].get("observed"), str) or not test[1]["observed"].strip():
                issue(issues, "error", "missing_reproduction_evidence", "本地复现主张需关联 passed 测试记录，含命令和观察结果；检查器不会执行命令", [identifier], f"claims[{i}].test_id")
            else:
                reproduction = {"test_id": test_id, "evidence_origin": "user_supplied_test_record", "executed_by_checker": False}
        if level == "author_report":
            issue(issues, "info", "author_report_only", "作者自述应归因于作者，不等于独立复现", [identifier])
        ledger.append({"id": identifier, "text": text, "evidence_level": level, "source_ids": refs, "test_id": row.get("test_id"), "reproduction": reproduction, "fact_certified": False})
    for identifier in sorted(set(sources) - used):
        issue(issues, "warning", "orphan_source", "来源未关联任何主张", [identifier])
    result = {"engine": "evidence", "summary": {"source_count": len(source_rows), "claim_count": len(claim_rows)}, "issues": issues,
              "claims": ledger, "sources": sorted([r for _, r in source_rows], key=canonical),
              "tests": sorted([r for _, r in test_rows], key=canonical),
              "untrusted_source_data": True, "external_actions": []}
    return finish(result)
