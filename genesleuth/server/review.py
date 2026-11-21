"""Persist reviewer actions atomically and export cited, supported evidence."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from genesleuth.config import DATA_DIR
from genesleuth.schemas import InvestigationResult, RankedSuspect


def read_actions(case_id: str) -> list[dict]:
    """Read a case's ordered review history."""
    path = DATA_DIR / "reviews" / f"{case_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def record_action(case_id: str, action: dict) -> list[dict]:
    """Commit one complete history update before acknowledging it."""
    path = DATA_DIR / "reviews" / f"{case_id}.json"
    history = read_actions(case_id)
    history.append({"at": datetime.now(timezone.utc).isoformat(), **action})
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(history, temporary, indent=2, ensure_ascii=False)
            temporary.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return history


def current_decisions(actions: list[dict]) -> dict[str, str]:
    """Return each candidate's latest explicit accept or reject decision."""
    return {
        item["variant_id"]: item["action"]
        for item in actions
        if item["action"] in {"accept", "reject"}
    }


def markdown_text(value: str) -> str:
    """Keep model and reviewer text as literal inline Markdown content."""
    value = " ".join(value.split())
    for character in "\\`*_{}[]<>#!|":
        value = value.replace(character, "\\" + character)
    return value


def evidence_report(result: InvestigationResult, actions: list[dict]) -> str:
    """Build a Markdown export of accepted candidates, claims, and decisions."""
    decisions = current_decisions(actions)
    ledger = {call.call_id: call for call in result.tool_calls}
    lines = ["# GeneSleuth evidence report", "", f"Case {result.case_id}", "", "## Accepted candidates", ""]
    candidates = {item.variant.variant_id: item for item in result.ranked}
    for action in actions:
        if action["action"] == "accept" and "candidate" in action:
            candidates[action["variant_id"]] = RankedSuspect.model_validate(action["candidate"])
    accepted = [item for variant_id, item in candidates.items() if decisions.get(variant_id) == "accept"]
    if not accepted:
        lines.extend(["No candidates accepted for this shortlist.", ""])
    for item in accepted:
        variant = item.variant
        title = markdown_text(f"{variant.gene or 'Unassigned gene'} · {variant.variant_id}")
        lines.extend([f"### {title}", "", f"Shortlist rank {item.rank}", ""])
        verdicts = {verdict.claim_id: verdict.verdict for verdict in item.verdicts}
        supported = [claim for claim in item.claims if verdicts.get(claim.claim_id) == "supported"]
        if not supported:
            lines.append("No supported claims in the current result.")
        for claim in supported:
            references = ", ".join(markdown_text(call_id) for call_id in claim.cited_call_ids)
            lines.append(f"- {markdown_text(claim.text)} — evidence {references}")
            for call_id in claim.cited_call_ids:
                if call := ledger.get(call_id):
                    detail = markdown_text(f"{call_id} · {call.tool} · {call.result_summary}")
                    lines.append(f"  - {detail}")
        lines.append("")
    lines.extend(["## Review history", ""])
    for action in actions:
        parts = [action["at"], action["action"], action["variant_id"]]
        parts.extend(action[key] for key in ("tissue", "question") if action.get(key))
        lines.append("- " + markdown_text(" · ".join(parts)))
    if not actions:
        lines.append("No review actions recorded.")
    return "\n".join(lines) + "\n"
