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


def _as_int(v, default=0):
    try: return int(v or default)
    except (ValueError, TypeError): return default


def _as_float(v, default=0.0):
    try: return float(v or default)
    except (ValueError, TypeError): return default


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

    section_starts = [
        (m.start(), m.group(1).strip())
        for m in re.finditer(r"^## ([^\n]+)\n\n- \*\*Id\*\* :", text, re.MULTILINE)
    ]

    responses = []
    for i, (start, label) in enumerate(section_starts):
        end = section_starts[i + 1][0] if i + 1 < len(section_starts) else len(text)
        sec = text[start:end]
        test_id = label_map.get(label, "")
        reasoning_match = re.search(
            r"\*\*Reasoning\s*:\*\*\s*\n+```\n(.*?)\n```",
            sec, flags=re.DOTALL,
        )
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
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
    return {
        "model": row.get("model", ""),
        "alias": row.get("alias", row.get("model", "")),
        "test_id": row.get("test_id", ""),
        "test_label": row.get("test_label", ""),
        "success": row.get("success", "True") in ("True", "true", "1"),
        "latency_s": _as_float(row.get("latency_s")),
        "tokens_in": _as_int(row.get("tokens_in")),
        "tokens_out": _as_int(row.get("tokens_out")),
        "reasoning_tokens": _as_int(row.get("reasoning_tokens", 0)),
        "ratio_reasoning": _as_float(row.get("ratio_reasoning", 0)),
        "cost_usd": _as_float(row.get("cost_usd")),
        "reasoning_chars": _as_int(row.get("reasoning_chars", 0)),
        "response_chars": _as_int(row.get("response_chars", 0)),
        "error": row.get("error", ""),
    }


def build_synthesis(run_dirs, label_map):
    """Construit le run synthetique 'latest' en prenant pour chaque
    (model, test_id) l'entree du run le plus recent (tri par mtime desc).

    run_dirs est deja trie par mtime decroissant.
    """
    metrics_seen = {}   # (model, test_id) -> entry
    scores_seen = {}    # (model, test_id, critere) -> entry
    responses_seen = {} # (model, test_id) -> entry

    for run_dir in run_dirs:
        run_name = run_dir.name

        metrics_raw = read_csv(run_dir / "_metrics.csv")
        for row in metrics_raw:
            m = normalize_metrics(row)
            key = (m["model"], m["test_id"])
            if key not in metrics_seen:
                m["source_run"] = run_name
                metrics_seen[key] = m

        scores_raw = read_csv(run_dir / "_scores.csv")
        for row in scores_raw:
            key = (row.get("model", ""), row.get("test_id", ""), row.get("critere", ""))
            if key not in scores_seen:
                entry = dict(row)
                entry["source_run"] = run_name
                scores_seen[key] = entry

        for md in sorted(run_dir.glob("*.md")):
            if md.name in ("SYNTHESE.md", "INSIGHTS.md"):
                continue
            model, resp_list = parse_response_md(md, label_map)
            for r in resp_list:
                r["model"] = model
                key = (model, r["test_id"])
                if key not in responses_seen:
                    r["source_run"] = run_name
                    responses_seen[key] = r

    return {
        "name": "latest",
        "is_synthesis": True,
        "metrics": list(metrics_seen.values()),
        "scores": list(scores_seen.values()),
        "responses": list(responses_seen.values()),
    }


def collect_orphans(run_dirs, known_models):
    """Retourne un dict des modeles vus dans les runs mais absents de models.json."""
    orphans = {}
    for run_dir in run_dirs:
        for row in read_csv(run_dir / "_metrics.csv"):
            model = row.get("model", "")
            if model and model not in known_models and model not in orphans:
                alias = row.get("alias", "") or model
                orphans[model] = {"alias": alias, "_orphan": True}
    return orphans


def main():
    prompts = load_prompts()
    models = load_models_meta()
    label_map = label_to_id(prompts)

    run_dirs = []
    if RUNS_DIR.exists():
        for d in RUNS_DIR.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            if (d / "_metrics.csv").exists():
                run_dirs.append(d)

    # Tri par mtime decroissant : le run modifie le plus recemment a la priorite.
    # Si Damien rejoue un vieux run, il prend le pas — comportement attendu.
    run_dirs_sorted = sorted(run_dirs, key=lambda d: d.stat().st_mtime, reverse=True)

    orphans = collect_orphans(run_dirs_sorted, models)
    extended_models = {**models, **orphans}

    synthesis = build_synthesis(run_dirs_sorted, label_map)

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompts": prompts,
        "models": extended_models,
        "runs": [synthesis],
    }

    DOCS_DIR.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2))

    print(f"Wrote {OUT}")
    print(f"  Run order (mtime desc): {[d.name for d in run_dirs_sorted]}")
    print(f"  Metrics: {len(synthesis['metrics'])} | Scores: {len(synthesis['scores'])} | Responses: {len(synthesis['responses'])}")
    print(f"  Models total: {len(extended_models)} (orphans: {list(orphans.keys()) or 'none'})")


if __name__ == "__main__":
    main()
