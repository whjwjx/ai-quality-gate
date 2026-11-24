"""评测相关的共享定义：字段 schema、归一化规则、判定口径。

所有判定逻辑集中在这里，避免脚本各处硬编码。
"""

from __future__ import annotations

import re

# 每类文档要抽取的字段。新增文档类型时在这里加一行，评测集与判定自动生效。
FIELD_SCHEMA: dict[str, list[str]] = {
    "invoice": ["invoice_no", "seller", "total_amount", "issue_date"],
    "contract": ["contract_no", "party_a", "party_b", "amount", "sign_date"],
    "resume": ["name", "years_experience", "highest_degree", "current_city"],
    "expense": ["expense_no", "applicant", "category", "amount"],
    "purchase_order": ["po_no", "supplier", "total_amount", "order_date"],
}

# 需要做数值归一化的字段（金额、年限）
NUMERIC_FIELDS = {"total_amount", "amount", "years_experience"}

# 需要做日期归一化的字段
DATE_FIELDS = {"issue_date", "sign_date", "order_date"}

_AMOUNT_CLEAN = re.compile(r"[¥￥$,\s]|人民币|元")
_DATE_PATTERNS = [
    re.compile(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?$"),
]


def normalize(field: str, value: object) -> str | None:
    """把模型输出和真值都过一遍同一套归一化，再比较。

    这是判定的前提：如果一边是 "¥13,568.00"、另一边是 "13568.00"，
    直接字符串比较会误判为错误。
    """
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"null", "none", "n/a"}:
        return None

    if field in NUMERIC_FIELDS:
        cleaned = _AMOUNT_CLEAN.sub("", text)
        try:
            return f"{float(cleaned):.2f}"
        except ValueError:
            return cleaned

    if field in DATE_FIELDS:
        for pat in _DATE_PATTERNS:
            m = pat.match(text)
            if m:
                y, mo, d = m.groups()
                return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        return text

    # 文本字段：去掉所有空白（含全角空格）
    return re.sub(r"\s+", "", text)


def expected_fields(doc_type: str) -> list[str]:
    return FIELD_SCHEMA.get(doc_type, [])
