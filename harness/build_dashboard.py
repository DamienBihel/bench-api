#!/usr/bin/env python3
"""Agrege runs/*/{_metrics.csv, _scores.csv, *.md} + prompts.json + models.json
en docs/data.json au format attendu par le dashboard (structure Bench-LLM).

Usage : python harness/build_dashboard.py
"""

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

HARNESS_DIR = Path(__file__).parent.resolve()
BENCH_ROOT = HARNESS_DIR.parent
RUNS_DIR = BENCH_ROOT / "runs"
DOCS_DIR = BENCH_ROOT / "docs"
OUT = DOCS_DIR / "data.json"


def load_prompts():
    return json.loads((HARNESS_DIR / "prompts.json").read_text())["tests"]


def load_models_meta():
    return json.loads((HARNESS_DIR / "models.json").read_text())


def read_csv(path):
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def label_to_id(prompts):
    return {p["label"]: p["id"] for p in prompts}


def parse_response_md(path, label_map):
    """Parse <model>.md -> (model_name, [{test_id, test_label, response, reasoning}]).

    Utilise un decoupage par marker unique '\\n## X\\n\\n- **Id** :' pour eviter
    les faux positifs sur '## Titre' utilise par les modeles dans leurs reponses
    markdown. Le fence de reponse est matche en greedy pour capturer les fences
    internes (ex: blocs code dans la reponse).
    """
    text = path.read_text()
    model = ""
    for line in text.splitlines():
        if line.startswith("# "):
            model = line[2:].strip()
            break

    # Decoupage : chaque section commence par "## <label>\n\n- **Id** :"
    # Pattern matche le debut de chaque section.
    section_starts = [
        (m.start(), m.group(1).strip())
        for m in re.finditer(r"^## ([^\n]+)\n\n- \*\*Id\*\* :", text, re.MULTILINE)
    ]

    responses = []
    for i, (start, label) in enumerate(section_starts):
        end = section_starts[i + 1][0] if i + 1 < len(section_starts) else len(text)
        sec = text[start:end]
        test_id = label_map.get(label, "")
        # Reasoning (optionnel)
        reasoning_match = re.search(
            r"\*\*Reasoning\s*:\*\*\s*\n+```\n(.*?)\n```",
            sec, flags=re.DOTALL,
        )
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
        # Response : greedy pour capturer les fences internes eventuels
        resp_match = re.search(
            r"\*\*Reponse\s*:\*\*\s*\n+```\n(.*)\n```",
            sec, flags=re.DOTALL,
        )
        response = resp_match.group(1).strip() if resp_match else ""
        responses.append({
            "test_id": test_id,
            "test_label": label,
            "response": response,
            "reasoning": reasoning,
        })
    return model, responses


def normalize_metrics(row):
    """Normalise une ligne metrics.csv (gere l'ancien format sans reasoning_tokens)."""

    def as_int(v, d=0):
        try: return int(v or d)
        except (ValueError, TypeError): return d

    def as_float(v, d=0.0):
        try: return float(v or d)
        except (ValueError, TypeError): return d

    return {
        "model": row.get("model", ""),
        "alias": row.get("alias", row.get("model", "")),
        "test_id": row.get("test_id", ""),
        "test_label": row.get("test_label", ""),
        "success": row.get("success", "True") in ("True", "true", "1"),
        "latency_s": as_float(row.get("latency_s")),
        "tokens_in": as_int(row.get("tokens_in")),
        "tokens_out": as_int(row.get("tokens_out")),
        "reasoning_tokens": as_int(row.get("reasoning_tokens", 0)),
        "ratio_reasoning": as_float(row.get("ratio_reasoning", 0)),
        "cost_usd": as_float(row.get("cost_usd")),
        "reasoning_chars": as_int(row.get("reasoning_chars", 0)),
        "response_chars": as_int(row.get("response_chars", 0)),
        "error": row.get("error", ""),
    }


def build_run(run_dir, label_map):
    metrics_raw = read_csv(run_dir / "_metrics.csv")
    metrics = [normalize_metrics(r) for r in metrics_raw]
    scores = read_csv(run_dir / "_scores.csv")

    # Parse responses from markdown files
    responses = []
    for md in sorted(run_dir.glob("*.md")):
        if md.name in ("SYNTHESE.md", "INSIGHTS.md"):
            continue
        model, resp = parse_response_md(md, label_map)
        for r in resp:
            r["model"] = model
        responses.extend(resp)

    return {
        "name": run_dir.name,
        "is_synthesis": False,
        "metrics": metrics,
        "scores": scores,
        "responses": responses,
    }


def main():
    prompts = load_prompts()
    models = load_models_meta()
    label_map = label_to_id(prompts)

    runs = []
    if RUNS_DIR.exists():
        for d in sorted(RUNS_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            if (d / "_metrics.csv").exists():
                runs.append(build_run(d, label_map))

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompts": prompts,
        "models": models,
        "runs": runs,
    }

    DOCS_DIR.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2))
    total_metrics = sum(len(r["metrics"]) for r in runs)
    total_scores = sum(len(r["scores"]) for r in runs)
    total_resp = sum(len(r["responses"]) for r in runs)
    print(f"Wrote {OUT}")
    print(f"  {len(runs)} runs | {total_metrics} metrics | {total_scores} scores | {total_resp} responses")


if __name__ == "__main__":
    main()
