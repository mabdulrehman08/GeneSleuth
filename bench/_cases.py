"""Case source for the benchmark: which option ids belong to a split, and how a case is (re)built or restored.

Feature: the only place bench/ touches Agent A3's case data. Everything goes through genesleuth.data.api
(list_demo_options, build_case, holdout_for), so it behaves the same on every computer. The split membership comes from
A3's splits (assets/splits.json or DATA_DIR/work/splits.json, or a function in genesleuth.data.splits). In a dry run
(FAKE_MODE=1) the fake options are partitioned instead.

Built cases are saved next to the results (bench/results/<split>/cases/<option_id>.json) so a resumed run reuses the exact
same case (suspects, letter path, truth) even if the builder is not deterministic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from genesleuth import config
from genesleuth.schemas import Case, CaseTruth

DEV_N_FAKE = 5


def _find(name: str) -> Optional[Path]:
    for p in (config.ROOT / "assets" / name, config.DATA_DIR / "work" / name):
        if p.exists():
            return p
    return None


def _ids(items) -> list[str]:
    out = []
    for x in items:
        if isinstance(x, dict):
            x = x.get("option_id") or x.get("clinvar_id") or x.get("variation_id") or x.get("id")
        if x is not None:
            out.append(str(x))
    return out


def stratified_subsample(items: list[dict], n: int) -> list[str]:
    """Pick n option ids keeping each stratum's share (largest-remainder), taking the first ones of each stratum in list order.

    Deterministic: the split lists are already seeded (seed 42), so 'first k per stratum' is a fixed, documented selection.
    """
    if n >= len(items):
        return _ids(items)
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(str(it.get("stratum") or it.get("region") or "all"), []).append(it)
    total = len(items)
    quota = {k: n * len(v) / total for k, v in groups.items()}
    take = {k: int(q) for k, q in quota.items()}
    for k in sorted(quota, key=lambda k: (-(quota[k] - take[k]), k))[: n - sum(take.values())]:
        take[k] += 1
    out: list[dict] = []
    for k in sorted(groups):
        out += groups[k][: take[k]]
    return _ids(out)


def list_split_options(split: str, max_cases: Optional[int] = None) -> list[str]:
    """Option ids (ClinVar variation ids) of a split, in a stable order; max_cases subsamples stratified by region stratum."""
    if max_cases and not config.FAKE_MODE:
        try:
            from genesleuth.data import splits as S
            items = S.load_splits().get(split)
            if isinstance(items, list) and items and isinstance(items[0], dict):
                return stratified_subsample(items, max_cases)
        except ImportError:
            pass
    if config.FAKE_MODE:
        from genesleuth.data import api
        ids = [o.option_id for o in api.list_demo_options()]
        return ids[:DEV_N_FAKE] if split == "dev" else ids[DEV_N_FAKE:]
    try:  # a function in A3's splits module, if it exposes one
        from genesleuth.data import splits as S
        for fn in ("split_option_ids", "option_ids", "get_split", "load_split", "split_options"):
            if hasattr(S, fn):
                got = getattr(S, fn)(split)
                if got:
                    return _ids(got)
    except ImportError:
        pass
    p = _find("splits.json")
    if p is not None:
        data = json.loads(p.read_text(encoding="utf-8"))
        if split == "named" and isinstance(data, dict):  # items tagged "named" in any list (DNM1 anchor, MFSD8, PLA2G6)
            return _ids(x for k, v in data.items() if isinstance(v, list) for x in v if isinstance(x, dict) and x.get("named"))
        if isinstance(data, dict) and split in data:
            return _ids(data[split])
    raise SystemExit(f"no split '{split}' found: A3's splits.json / genesleuth.data.splits is not available yet")


def load_or_build(split: str, option_id: str, seed: int, case_dir: Path) -> tuple[Case, CaseTruth, set[str]]:
    """Restore the saved case for this option or build it through genesleuth.data.api and save it."""
    from genesleuth.data import api
    f = case_dir / f"{option_id}.json"
    if f.exists():
        raw = json.loads(f.read_text(encoding="utf-8"))
        case, truth = Case.model_validate(raw["case"]), CaseTruth.model_validate(raw["truth"])
    else:
        case, truth = api.build_case(option_id, None, split, seed)
        case_dir.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"option_id": option_id, "case": case.model_dump(), "truth": truth.model_dump()}), encoding="utf-8")
        tmp.replace(f)
    return case, truth, api.holdout_for(truth)


def detect_letter_type(pdf_path: str) -> str:
    """'scanned' when the PDF has no extractable text (image-only) or its file name says so, 'clean' when it has text."""
    p = Path(pdf_path)
    if "scanned" in p.name.lower():
        return "scanned"
    if not p.exists():
        for alt in (config.ROOT / "assets" / "letters" / p.name,):
            if alt.exists():
                p = alt
                break
        else:
            return "unknown"
    try:
        from pypdf import PdfReader
        text = "".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
        return "clean" if len(text.strip()) > 40 else "scanned"
    except Exception:  # noqa: BLE001
        return "unknown"
