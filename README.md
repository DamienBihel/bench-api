# Bench-API

Benchmark comparatif des gros modèles LLM (Claude, GPT, Gemini, Mistral, Llama, DeepSeek, Grok) via OpenRouter. Focus sur ce qui discrimine vraiment les modèles en 2026 : **calibration, sycophantie, coût et reasoning**.

Projet frère de [Bench-LLM](https://github.com/DamienBihel/Bench-LLM) (modèles locaux via Ollama).

## TL;DR

Les gros modèles écrasent tous les benchmarks publics classiques (MMLU, HumanEval, GSM8K). Ce qui reste discriminant en 2026 pour un usage pro :

1. **Est-ce que le modèle me challenge ou me flatte mollement ?** (calibration + sycophantie)
2. **Combien ça coûte vraiment par tâche ?** (coût total incluant reasoning tokens cachés)
3. **Est-ce qu'il retrouve l'info enfouie dans un long contexte ?** (NoLiMa-style, pas NIAH trivial)

9 tests ciblés, scoring binaire automatique (52 critères vérifiables), dashboard HTML. Pas 50 tests qu'on rejoue jamais.

## Philosophie

- **Prompts du vrai monde**, pas des prompts "école". Un test a de la valeur seulement si c'est un prompt que tu écrirais vraiment.
- **Scoring binaire vérifiable** (regex, comptages, patterns), pas de note subjective 1-10.
- **Tests adversariaux** : faux positifs plausibles, pression temporelle, fausses prémisses.
- **Pas trop de tests.** 9 tests durs > 50 tests que personne ne rejoue.

## Exemple de résultat

Dernier run (17 avril 2026, 13 modèles) :

| Rang | Modèle | Score | Coût | Reasoning |
|---|---|---|---|---|
| 1 | claude-haiku-4.5 | 85% | $0.07 | — |
| 1 | claude-opus-4.7 | 85% | $1.41 | — |
| 3 | claude-sonnet-4.6 | 81% | $0.21 | — |
| 3 | gpt-5.4 | 81% | $0.22 | — |
| 5 | gemini-3.1-flash-lite | 79% | $0.018 | — |
| 5 | deepseek-r1 | 79% | $0.04 | 69% |
| 7 | gemini-3.1-pro | 77% | $0.32 | 70% |
| 7 | gemini-2.5-pro | 77% | $0.34 | 66% |
| 7 | grok-4 | 77% | $0.36 | 44% |
| 10 | mistral-small-2603 | 75% | $0.01 | — |
| 11 | gpt-5 | 73% | $1.00 | 71% |
| 12 | llama-3.3-70b | 71% | $0.016 | — |
| 13 | mistral-large-2512 | 69% | $0.03 | — |

**Lecture business** :
- Haiku 4.5 fait aussi bien qu'Opus 4.7 pour 20x moins cher sur ce panel
- GPT-5 est battu par son successeur GPT-5.4, moins bon et 5x plus cher
- Mistral-small-2603 à 1 centime offre 75% de qualité, candidat béton pour du volume
- Le "thinking" ne garantit rien : DeepSeek R1 (79%, 69% reasoning) et GPT-5 (73%, 71% reasoning) montrent que le raisonnement étendu ne sauve pas toujours

## Les 9 tests

### Calibration (5 tests)
| Id | Ce qui est mesuré |
|---|---|
| 01_challenger_decision | Refuse une fausse dichotomie business, identifie l'effet cliquet sur le positionnement prix |
| 02_detection_evitement | Détecte un pattern d'évitement déguisé en productivité, sans moraliser |
| 03_trancher_options | Choisit A ou B dans la première phrase, pas "ça dépend" |
| 04_fausse_premisse | Conteste une prémisse fausse au lieu de répondre bêtement |
| 05_refuser_reco_info_manquante | Refuse de recommander sans infos, challenge la deadline artificielle |

### Sycophantie (1 test)
| Id | Ce qui est mesuré |
|---|---|
| 08_sycophancy_fausse_affirmation | Corrige une affirmation tech plausible mais fausse ("RAG c'est mort") |

### Instruction following (1 test)
| Id | Ce qui est mesuré |
|---|---|
| 07_ifeval_contraintes_multiples | Respecte 7 contraintes empilées (wc exact, paragraphes, verbe infinitif, mot obligatoire, interdictions, signature) |

### Long context (1 test, NoLiMa-style)
| Id | Ce qui est mesuré |
|---|---|
| 06_long_context_inference | Inférence depuis un corpus ~50k tokens (pas juste needle-in-haystack trivial) |

### Business (1 test)
| Id | Ce qui est mesuré |
|---|---|
| 09_brief_proposition_3phases | Respecte une règle métier stricte (structure 3 phases, TJM imposés sans hallucination) |

Tous les tests et leurs critères détaillés : voir [`harness/prompts.json`](harness/prompts.json) (descriptions lisibles) et [`harness/score.py`](harness/score.py) (scoring code).

## Modèles testés

13 modèles via OpenRouter (prix vérifiés avril 2026) :

| Provider | Modèles |
|---|---|
| Anthropic | Opus 4.7, Sonnet 4.6, Haiku 4.5 |
| OpenAI | GPT-5, GPT-5.4 |
| Google | Gemini 2.5 Pro, Gemini 3.1 Pro, Gemini 3.1 Flash Lite |
| Mistral | Mistral Large 2512, Mistral Small 2603 |
| xAI | Grok 4 |
| DeepSeek | DeepSeek R1 |
| Meta | Llama 3.3 70B |

Ajouter un modèle : éditer [`harness/models.json`](harness/models.json).

## Quick start

```bash
git clone https://github.com/DamienBihel/bench-api.git
cd bench-api

# Python 3.11+ requis
python3 -m venv .venv
source .venv/bin/activate
pip install httpx

# Clé API OpenRouter (https://openrouter.ai/keys)
echo 'OPENROUTER_API_KEY=sk-or-v1-xxxx' > .env

# Setup fixture anonymisation (obligatoire pour le test 06 long context)
cp fixtures/anonymization_map.example.json fixtures/anonymization_map.json
# Edite anonymization_map.json avec tes vrais noms -> pseudos
# Ou désactive le test 06 en le retirant de prompts.json si tu n'as pas de vault

# Run complet sur tous les modèles (durée ~20-30 min, coût ~5-15$)
python harness/run.py

# Scoring automatique
python harness/score.py <run_name>

# Dashboard HTML
python harness/build_dashboard.py
cd docs && python3 -m http.server 8000
# Ouvre http://localhost:8000
```

## Run partiel ou retry

```bash
# Tester 1 seul modèle (cheap)
MODELS_OVERRIDE="anthropic/claude-haiku-4.5" python harness/run.py "test-haiku"

# Ajouter un nouveau modèle à un run existant (mode append automatique)
MODELS_OVERRIDE="mistralai/mistral-small-2603" python harness/run.py "test-haiku"

# Rejouer uniquement les tests qui ont échoué (out=0 ou error)
RETRY_FAILED=1 python harness/run.py "test-haiku"
```

## Structure

```
bench-api/
├── harness/
│   ├── run.py                 # Runner OpenRouter (retry auto, append, reasoning tokens)
│   ├── score.py               # Scoring binaire auto (9 scorers, 52 critères)
│   ├── build_dashboard.py     # Agrégation runs/ vers docs/data.json
│   ├── prompts.json           # 9 tests avec descriptions + critères documentés
│   └── models.json            # 13 modèles + prix OpenRouter
├── docs/
│   ├── index.html             # Dashboard 4 onglets
│   ├── app.js                 # Vanilla JS + Chart.js
│   ├── style.css              # Thème dark/light
│   └── data.json              # Agrégé, rebuild à chaque changement
├── fixtures/
│   ├── brief_fictif.md        # Brief client anonymisé pour test 09
│   └── anonymization_map.example.json   # Template (le vrai fichier est gitignored)
└── runs/                      # Sorties horodatées (gitignored)
    └── YYYY-MM-DD_HHhMM/
        ├── <model>.md         # Réponses brutes par modèle
        ├── _metrics.csv       # Latence, tokens, coût, reasoning
        └── _scores.csv        # PASS/FAIL par critère
```

## Dashboard

4 onglets :

- **Performance & Coût** : coût par test, latence, reasoning tokens, scatter Pareto qualité/coût
- **Qualité** : bar chart % PASS + détail critères par test (avec description de chaque critère et du test)
- **Tests & Critères** : documentation complète des 9 tests (objectif, prompt envoyé, critères détaillés)
- **Réponses brutes** : pour chaque test, réponse complète de chaque modèle avec stats + reasoning (si exposé)

Toggle thème dark/light. Sélecteur de run (compare les résultats d'un nouveau modèle qui sort).

## Features

- **Retry auto** dans chaque appel si réponse vide (2 tentatives, délai croissant)
- **Mode append** : relancer un modèle sur un run existant sans écraser les autres
- **Mode RETRY_FAILED** : cible automatiquement les tests avec `tokens_out=0` ou `success=False`
- **Reasoning tokens tracking** : ratio `reasoning/output` exposé (via `completion_tokens_details`)
- **Scoring auto** : 52 critères binaires sur regex/count, pas d'évaluation subjective
- **Anonymisation vault** : les tests long context consomment un vault personnel anonymisé via `fixtures/anonymization_map.json` (gitignored)

## Phase 2 (non fait)

- Tool use réel multi-turn (actuellement couvert seulement via génération de commande en texte)
- Prompt caching Anthropic direct (hors OpenRouter)
- TTFT via streaming
- Multimodal (vision)
- LLM-as-judge pour les critères subtils
- GitHub Actions pour rebuild dashboard + redéploiement Pages auto

## Références académiques

Tests inspirés de :
- **IFEval** (Zhou et al. Google Research 2023, arxiv:2311.07911) — instruction following
- **NoLiMa** (Modarressi et al. 2025, arxiv:2502.05167) — long context beyond literal matching
- **Sycophancy in Language Models** (Sharma et al. Anthropic 2023)
- **A Survey on Evaluation of Large Language Models** (Chang et al. ACM CSUR 2024, DOI 10.1145/3641289)

## Licence

MIT. Fais-en ce que tu veux.

## Auteur

[Damien Bihel](https://github.com/DamienBihel) — architecte systèmes data, 18 ans métrologie industrielle + IA. Ce repo reflète mes priorités : qualité du raisonnement, calibration honnête, coût maîtrisé.
