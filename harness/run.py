#!/usr/bin/env python3
"""Bench-API : runner pour benchmarker des gros modeles via OpenRouter.

Usage :
    python run.py                       # run avec nom auto (timestamp)
    python run.py "mon-run-custom"      # run avec nom custom
    MODELS_OVERRIDE="anthropic/claude-haiku-4.5 openai/gpt-5" python run.py

Lit OPENROUTER_API_KEY dans .env ou env.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

HARNESS_DIR = Path(__file__).parent.resolve()
BENCH_ROOT = HARNESS_DIR.parent
RUNS_DIR = BENCH_ROOT / "runs"
FIXTURES_DIR = BENCH_ROOT / "fixtures"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT_S = 300
TEMPERATURE = 0.2
MAX_OUTPUT_TOKENS = 4096


def load_env():
    """Charge .env si present."""
    env_path = BENCH_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def anonymize(text, mapping):
    """Applique un dict de remplacements (par longueur decroissante pour eviter
    les collisions : 'Sandra Labrunie' doit etre remplace avant 'Sandra')."""
    # Filtre les cles meta (commencent par _)
    pairs = [(k, v) for k, v in mapping.items() if not k.startswith("_")]
    pairs.sort(key=lambda kv: len(kv[0]), reverse=True)
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def load_anonymization_map():
    path = FIXTURES_DIR / "anonymization_map.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def load_vault_fixture():
    """Assemble le fixture pour le test long_context depuis le vault DamIA.

    Concatene les fichiers vault cles puis applique l'anonymisation definie
    dans fixtures/anonymization_map.json. Le contenu contient naturellement
    les elements cherches par le test (ex : pivot 'methode > produit' en mars 2026).
    """
    fixture_path = FIXTURES_DIR / "vault_dump.md"
    if fixture_path.exists():
        return fixture_path.read_text()

    vault_root = Path("/Users/damien/DamIA")
    files = [
        "CLAUDE.md",
        "Actions/ROADMAP.md",
        "Actions/areas/Argent/Profil Argent.md",
        "Actions/areas/Argent/ROADMAP_MONEY.md",
        "Actions/areas/Commercial/ROADMAP_COMMERCIAL.md",
        "Actions/areas/Communication/ROADMAP_COMMUNICATION.md",
        "Actions/areas/Reseau/ROADMAP_RESEAU.md",
        "Calendar/Objectifs/focus_semaine.md",
        "Calendar/Objectifs/Plan_90_Jours_Q1_2026.md",
    ]
    parts = []
    for rel in files:
        p = vault_root / rel
        if p.exists():
            parts.append(f"=== FILE: {rel} ===\n\n{p.read_text()}\n\n")
    dump = "".join(parts)

    # Anonymisation avant ecriture
    anonymization_map = load_anonymization_map()
    if anonymization_map:
        dump = anonymize(dump, anonymization_map)

    FIXTURES_DIR.mkdir(exist_ok=True)
    fixture_path.write_text(dump)
    return dump


def load_models():
    with open(HARNESS_DIR / "models.json") as f:
        return json.load(f)


def load_prompts():
    with open(HARNESS_DIR / "prompts.json") as f:
        return json.load(f)["tests"]


def call_openrouter(api_key, model, prompt, reasoning_effort=None, max_retries=1):
    """Appel synchrone a OpenRouter. Renvoie dict avec reponse et metriques.

    reasoning_effort : "low" | "medium" | "high" pour forcer le niveau de
    thinking (quand le modele supporte). None = defaut provider.

    max_retries : si l'appel retourne success=False OU tokens_out=0, on
    retente N fois avec delai croissant. Utile pour les echecs transitoires
    des providers OpenRouter.
    """
    attempt = 0
    while True:
        result = _call_openrouter_once(api_key, model, prompt, reasoning_effort)
        is_empty = result["success"] and result["tokens_out"] == 0 and not result["response"]
        if result["success"] and not is_empty:
            result["retries"] = attempt
            return result
        if attempt >= max_retries:
            result["retries"] = attempt
            return result
        attempt += 1
        time.sleep(2 * attempt)


def _call_openrouter_once(api_key, model, prompt, reasoning_effort=None):
    """Un seul appel a OpenRouter (sans retry)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/damienbihel/Bench-API",
        "X-Title": "Bench-API Damien",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}

    start = time.time()
    try:
        with httpx.Client(timeout=TIMEOUT_S) as client:
            r = client.post(OPENROUTER_URL, headers=headers, json=payload)
        latency = time.time() - start

        if r.status_code != 200:
            return {
                "success": False,
                "error": f"HTTP {r.status_code}: {r.text[:500]}",
                "latency_s": latency,
                "response": "",
                "tokens_in": 0,
                "tokens_out": 0,
                "reasoning": "",
            }

        data = r.json()
        msg = data.get("choices", [{}])[0].get("message", {})
        response = msg.get("content", "") or ""
        reasoning = msg.get("reasoning", "") or msg.get("reasoning_content", "") or ""
        usage = data.get("usage", {})

        # reasoning_tokens : expose par certains providers
        # OpenAI o-series : usage.completion_tokens_details.reasoning_tokens
        # OpenRouter direct : usage.reasoning_tokens
        # Anthropic thinking : usage.completion_tokens_details.reasoning_tokens (via OpenRouter)
        reasoning_tokens = 0
        details = usage.get("completion_tokens_details") or {}
        if isinstance(details, dict):
            reasoning_tokens = details.get("reasoning_tokens", 0) or 0
        if not reasoning_tokens:
            reasoning_tokens = usage.get("reasoning_tokens", 0) or 0

        return {
            "success": True,
            "error": "",
            "latency_s": latency,
            "response": response,
            "reasoning": reasoning,
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "reasoning_tokens": reasoning_tokens,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception: {type(e).__name__}: {e}",
            "latency_s": time.time() - start,
            "response": "",
            "reasoning": "",
            "tokens_in": 0,
            "tokens_out": 0,
            "reasoning_tokens": 0,
        }


def compute_cost(tokens_in, tokens_out, model_info):
    """Cout en dollars."""
    cost_in = tokens_in * model_info["price_input_per_1m"] / 1_000_000
    cost_out = tokens_out * model_info["price_output_per_1m"] / 1_000_000
    return cost_in + cost_out


def safe_model_filename(model):
    return model.replace("/", "__").replace(":", "_")


def remove_section_from_md(md_path, label):
    """Supprime une section '## <label>...' jusqu'au prochain header section."""
    import re as _re
    if not md_path.exists():
        return
    text = md_path.read_text()
    # Pattern : "## <label>\n" jusqu'au prochain "\n## X\n\n- **Id** :" (ou EOF)
    pattern = (
        rf"## {_re.escape(label)}\n.*?"
        rf"(?=\n## [^\n]+\n\n- \*\*Id\*\* :|\Z)"
    )
    new_text = _re.sub(pattern, "", text, flags=_re.DOTALL)
    # Nettoie lignes vides multiples resultantes
    new_text = _re.sub(r"\n{3,}", "\n\n", new_text)
    md_path.write_text(new_text)


def main():
    load_env()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERREUR: OPENROUTER_API_KEY absente (variable d'env ou .env)")
        sys.exit(1)

    run_name = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d_%Hh%M")
    run_dir = RUNS_DIR / run_name
    metrics_csv = run_dir / "_metrics.csv"
    # Mode append si le run existe deja avec un CSV (on fusionne les nouveaux modeles)
    append_mode = run_dir.exists() and metrics_csv.exists()
    # Mode retry_failed : on ne relance QUE les tests qui ont echoue (out=0 ou error)
    retry_failed = os.environ.get("RETRY_FAILED", "").lower() in ("1", "true", "yes")
    run_dir.mkdir(parents=True, exist_ok=True)

    models_all = load_models()
    override = os.environ.get("MODELS_OVERRIDE")
    if override:
        models = {k: models_all[k] for k in override.split() if k in models_all}
    else:
        models = models_all

    prompts = load_prompts()

    print(f"{'=' * 60}")
    print(f"  BENCH-API {'[APPEND]' if append_mode else '[NEW RUN]'}")
    print(f"  Run  : {run_name}")
    print(f"  Out  : {run_dir}")
    print(f"  Models : {len(models)}")
    print(f"  Tests  : {len(prompts)}")
    print(f"{'=' * 60}")

    # Prepare fixtures
    fixtures = {}
    has_long = any(t["axe"] == "long_context" for t in prompts)
    if has_long:
        print("\n  Preparation fixture long context...")
        fixtures["vault_dump"] = load_vault_fixture()
        approx_tokens = len(fixtures["vault_dump"]) // 4
        print(f"  vault_dump : {len(fixtures['vault_dump']):,} chars (~{approx_tokens:,} tokens)")

    brief_path = FIXTURES_DIR / "brief_fictif.md"
    if brief_path.exists():
        fixtures["brief"] = brief_path.read_text()
        print(f"  brief : {len(fixtures['brief']):,} chars")

    # Calcul des tests a relancer par modele
    # - retry_failed : on identifie les tests avec out=0 OR success=False dans le CSV existant
    # - sinon : on relance tous les tests du modele
    failed_per_model = {}  # {model: set of test_ids a relancer}
    if append_mode:
        with open(metrics_csv) as f:
            reader = csv.DictReader(f)
            header = list(reader.fieldnames or [])
            all_rows = list(reader)

        # Migration schema : ajoute 'retries' si absent (ancien format)
        if "retries" not in header:
            header.append("retries")
            for r in all_rows:
                r["retries"] = "0"

        if retry_failed:
            for row in all_rows:
                if row["model"] not in models:
                    continue
                success = row.get("success", "True").lower() in ("true", "1")
                try:
                    tout = int(row.get("tokens_out", 0) or 0)
                except ValueError:
                    tout = 0
                if not success or tout == 0:
                    failed_per_model.setdefault(row["model"], set()).add(row["test_id"])
            # Conserver toutes les lignes sauf les failed qu'on va relancer
            existing_rows = [
                r for r in all_rows
                if not (r["model"] in failed_per_model and r["test_id"] in failed_per_model[r["model"]])
            ]
            if not failed_per_model:
                print("  [RETRY_FAILED] Aucun test failed trouve pour les modeles selectionnes. Exit.")
                return
            print(f"  [RETRY_FAILED] Tests a relancer :")
            for m, tests in failed_per_model.items():
                print(f"    {m} : {sorted(tests)}")
        else:
            # Mode append normal : on supprime toutes les lignes des modeles cibles
            existing_rows = [r for r in all_rows if r.get("model") not in models]

        with open(metrics_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(existing_rows)
    else:
        with open(metrics_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "model", "alias", "test_id", "test_label",
                "success", "latency_s", "tokens_in", "tokens_out",
                "reasoning_tokens", "ratio_reasoning",
                "cost_usd", "reasoning_chars", "response_chars",
                "error", "retries",
            ])

    for model, info in models.items():
        alias = info.get("alias", model)
        md_path = run_dir / f"{safe_model_filename(model)}.md"
        total_cost = 0.0

        # En mode retry_failed, skip les modeles sans fails
        if retry_failed and model not in failed_per_model:
            print(f"\n  [SKIP] {alias} (aucun test failed)")
            continue

        if retry_failed and md_path.exists():
            # Supprime les sections failed du MD existant (on va les regenerer)
            for tid in failed_per_model.get(model, set()):
                test_label = next((p["label"] for p in prompts if p["id"] == tid), None)
                if test_label:
                    remove_section_from_md(md_path, test_label)
            # Marque le retry
            with open(md_path, "a") as f:
                f.write(f"\n<!-- RETRY_FAILED {datetime.now().isoformat()} -->\n\n")
        elif not append_mode or not md_path.exists():
            # Mode normal (nouveau run ou modele nouveau) : ecrit header
            with open(md_path, "w") as f:
                f.write(f"# {model}\n\n")
                f.write(f"Alias : {alias}\n")
                f.write(f"Run : {run_name}\n\n")
        else:
            # append mode (relance complete d'un modele) : reecrit header
            with open(md_path, "w") as f:
                f.write(f"# {model}\n\n")
                f.write(f"Alias : {alias}\n")
                f.write(f"Run : {run_name}\n\n")

        print(f"\n{'-' * 60}")
        print(f"  MODELE : {alias}  ({model})")
        if retry_failed:
            print(f"  [RETRY] {len(failed_per_model.get(model, set()))} tests a relancer")
        print(f"{'-' * 60}")

        for i, test in enumerate(prompts):
            tid = test["id"]
            label = test["label"]
            axe = test["axe"]

            # Mode retry_failed : skip les tests qui n'ont pas echoue
            if retry_failed and tid not in failed_per_model.get(model, set()):
                continue

            if "prompt_template" in test:
                prompt = test["prompt_template"]
                for key, val in fixtures.items():
                    prompt = prompt.replace("{" + key + "}", val)
            else:
                prompt = test["prompt"]

            print(f"\n  [{i+1}/{len(prompts)}] {label}...")

            # max_retries=2 : retente jusqu'a 2 fois les appels vides/failed
            result = call_openrouter(api_key, model, prompt, max_retries=2)
            cost = compute_cost(result["tokens_in"], result["tokens_out"], info)
            total_cost += cost

            # ratio reasoning : quelle fraction de completion_tokens etait du thinking
            rt = result["reasoning_tokens"]
            tout = result["tokens_out"]
            ratio = (rt / tout) if (rt and tout) else 0.0

            status = "OK" if result["success"] else "FAIL"
            if result["success"] and tout == 0:
                status = "EMPTY"
            think_str = f"  think={rt} ({ratio:.0%})" if rt else ""
            retry_str = f"  retries={result['retries']}" if result.get("retries", 0) else ""
            print(
                f"       {status}  latence={result['latency_s']:.1f}s  "
                f"in={result['tokens_in']}  out={tout}{think_str}  "
                f"cost=${cost:.4f}{retry_str}"
            )
            if not result["success"]:
                print(f"       ERROR: {result['error'][:200]}")

            with open(md_path, "a") as f:
                f.write(f"## {label}\n\n")
                f.write(f"- **Id** : {tid}\n")
                f.write(f"- **Axe** : {axe}\n")
                think_md = (
                    f" | reasoning_tokens={rt} ({ratio:.0%})" if rt else ""
                )
                f.write(
                    f"- **Stats** : latence={result['latency_s']:.1f}s | "
                    f"tokens_in={result['tokens_in']} | "
                    f"tokens_out={tout}{think_md} | "
                    f"cost=${cost:.4f}\n\n"
                )
                if result["reasoning"]:
                    f.write("**Reasoning :**\n\n```\n")
                    f.write(result["reasoning"])
                    f.write("\n```\n\n")
                f.write("**Reponse :**\n\n```\n")
                f.write(result["response"] if result["success"] else f"[ERROR] {result['error']}")
                f.write("\n```\n\n---\n\n")

            with open(metrics_csv, "a", newline="") as f:
                w = csv.writer(f)
                w.writerow([
                    model, alias, tid, label,
                    result["success"], f"{result['latency_s']:.2f}",
                    result["tokens_in"], result["tokens_out"],
                    rt, f"{ratio:.3f}",
                    f"{cost:.6f}",
                    len(result["reasoning"]),
                    len(result["response"]),
                    result["error"][:200],
                    result.get("retries", 0),
                ])

        with open(md_path, "a") as f:
            f.write(f"\n## Total run\n\nCout total pour ce modele : **${total_cost:.4f}**\n")
        print(f"\n  Cout total {alias} : ${total_cost:.4f}")

    print(f"\n{'=' * 60}")
    print(f"  Resultats : {run_dir}")
    print(f"  Metriques : {metrics_csv}")
    print(f"  Prochaine etape : python score.py {run_name}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
