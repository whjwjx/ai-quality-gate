"""抽取器：统一接口 + 回放实现 + 真实调用实现。

关键设计：上层判定逻辑只依赖 Extractor 接口，不关心输出是来自文件还是 API。
换数据来源不改判定逻辑，换判定逻辑不改数据来源。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from eval.loader import load_snapshot
from eval.schema import expected_fields


class Extractor(Protocol):
    """返回模型的原始输出字符串，不做任何解析。"""

    def extract(self, case: dict) -> str: ...


def load_prompt(prompt_version: str, prompt_dir: str = "prompts") -> str:
    path = Path(prompt_dir) / f"extract_{prompt_version}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"找不到 prompt 文件 {path}。切换 prompt 版本时必须从 prompts/ 里显式指定。"
        )
    return path.read_text(encoding="utf-8")


def build_prompt(case: dict, prompt_version: str) -> str:
    template = load_prompt(prompt_version)
    fields = expected_fields(case["doc_type"])
    return template.format(
        doc_type=case["doc_type"],
        fields=", ".join(fields),
        document=case["document"],
    )


class ReplayExtractor:
    """从冻结快照里读历史响应。不发任何网络请求，结果完全确定。"""

    def __init__(self, snapshot_path: str | Path):
        self.snapshot_path = Path(snapshot_path)
        self._snapshot, self.model = load_snapshot(self.snapshot_path)

    def extract(self, case: dict) -> str:
        cid = case["case_id"]
        if cid not in self._snapshot:
            raise KeyError(
                f"快照 {self.snapshot_path} 中缺少 case '{cid}'。"
                f"新增用例或换了 prompt 版本后，必须重新录制快照。"
            )
        return self._snapshot[cid]["raw_response"]


class LLMExtractor:
    """真实调用 DeepSeek，只用于本地录制快照。CI 中不启用。"""

    def __init__(self, prompt_version: str, model: str | None = None):
        self.prompt_version = prompt_version
        self.model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError(
                "缺少 DEEPSEEK_API_KEY。录制快照需要真实 key；"
                "只想跑回放请设 EXTRACTOR_BACKEND=replay。"
            )
        self.api_key = api_key
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")

    def extract(self, case: dict) -> str:
        import httpx

        prompt = build_prompt(case, self.prompt_version)
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def make_extractor(prompt_version: str, snapshot: str | None = None) -> Extractor:
    """按 EXTRACTOR_BACKEND 选择实现。默认回放，保证 CI 零成本可重复。"""
    backend = os.environ.get("EXTRACTOR_BACKEND", "replay").lower()
    if backend == "replay":
        name = snapshot or os.environ.get("SNAPSHOT", "deepseek")
        path = Path("snapshots") / name / f"prompt_{prompt_version}.jsonl"
        return ReplayExtractor(path)
    if backend == "deepseek":
        return LLMExtractor(prompt_version)
    raise ValueError(f"未知的 EXTRACTOR_BACKEND: {backend}（可选 replay / deepseek）")
