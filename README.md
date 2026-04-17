# Bench-API

Benchmark cible sur 2 points durs : **calibration** (est-ce que le modele te pousse ou te flatte) et **cout** (quel modele vaut vraiment son prix).

Projet frere de [Bench-LLM](../Bench-LLM) (modeles locaux via Ollama). Ici on teste les gros modeles via OpenRouter (Opus, Sonnet, GPT-5, Gemini, DeepSeek, Grok, Llama).

## Philosophie

Les gros modeles ecrasent tous les tests generiques (francais, JSON, code, raisonnement basique). Inutile de les rejouer. Ce qui discrimine vraiment :

1. **Calibration** : est-ce que le modele valide mollement ou il challenge ?
2. **Cout par tache** : combien ca coute pour un usage reel Damien ?
3. **Long context** : est-ce qu.il retrouve une info precise noyee dans ~50k tokens ?

5 tests calibration + 1 test long context = 6 prompts. Pas 50. Pas 15.

## Tests (9 au total, ~46 criteres binaires)

### Calibration (5 tests)
| Id | Label | Discriminant |
|---|---|---|
| 01 | Challenger TJM (fausse dichotomie 500/800) | Effet cliquet + alternatives chiffrees |
| 02 | Detection evitement (CRM vs relances post-cafe rate) | Nomme pattern + challenge rationalisation |
| 03 | Trancher 2 options equivalentes (cafe vs post) | Choix explicite premiere phrase, pas "ca depend" |
| 04 | Fausse premisse (site web pour churn client) | Conteste premisse + pose question |
| 05 | Refuser reco info manquante (5000 EUR/mois, 2h) | 3+ questions + challenge deadline |

### Sycophantie (1 test)
| Id | Label | Discriminant |
|---|---|---|
| 08 | Fausse affirmation tech ("RAG c'est mort") | Corrige avec contre-args + nuance |

### Instruction following (1 test)
| Id | Label | Discriminant |
|---|---|---|
| 07 | Contraintes empilees email relance (7 contraintes) | wc exact, paragraphes, verbe infinitif, mots obligatoires/interdits, signature |

### Long context (1 test, NoLiMa-style)
| Id | Label | Discriminant |
|---|---|---|
| 06 | Inference pivot strategique dans 50k tokens vault | Trouve "Methode > Produit mars 2026" par inference |

### Business (1 test)
| Id | Label | Discriminant |
|---|---|---|
| 09 | Brief client vers proposition 3 phases (regle Diagnostic Visible) | Structure phases + TJM 1000/800/1000 sans hallucination |

Prompts dans `harness/prompts.json`. Rubriques binaires dans `harness/score.py` (fonctions `score_XX_*`).

Fixtures (generees/lues au 1er run) :
- `fixtures/vault_dump.md` : concat vault DamIA (~50k tokens) pour test 06
- `fixtures/brief_fictif.md` : brief client anonymise pour test 09

## Modeles testes (v1)

Tous via OpenRouter (`https://openrouter.ai/api/v1/chat/completions`).

| Alias | Prix in ($/M) | Prix out ($/M) | Context | Thinking |
|---|---|---|---|---|
| opus-4.7 | 15.00 | 75.00 | 200k | oui |
| sonnet-4.6 | 3.00 | 15.00 | 200k | oui |
| haiku-4.5 | 1.00 | 5.00 | 200k | non |
| gpt-5 | 10.00 | 30.00 | 1M | oui |
| gemini-2.5-pro | 2.50 | 10.00 | 2M | oui |
| llama-3.3-70b | 0.35 | 0.40 | 128k | non |
| deepseek-r1 | 0.55 | 2.19 | 128k | oui |
| grok-4 | 5.00 | 15.00 | 256k | oui |

Prix a verifier avant chaque run (OpenRouter change les prix sans prevenir). Mise a jour dans `harness/models.json`.

## Setup

```bash
cd /Users/damien/Forge/Projets/Bench-API

# Python 3.11+ requis
python3 -m venv .venv
source .venv/bin/activate
pip install httpx

# API key
echo 'OPENROUTER_API_KEY=sk-or-v1-xxxx' > .env
```

Recuperer la cle : https://openrouter.ai/keys

## Lancer un run

```bash
python harness/run.py                          # run auto (timestamp)
python harness/run.py "mon-run-custom"         # nom explicite

# Run partiel (un ou deux modeles seulement)
MODELS_OVERRIDE="anthropic/claude-haiku-4.5 openai/gpt-5" python harness/run.py
```

Sortie dans `runs/<run_name>/` :
- `<model>.md` : reponses brutes + stats par test
- `_metrics.csv` : latence, tokens in/out, cout par test

Cout estime par run complet : **$5-15** (le long context pese, reste negligeable).

## Scorer un run

```bash
python harness/score.py <run_name>
```

Applique les rubriques binaires. Genere `_scores.csv` et affiche :
- Score par modele (X / Y criteres passes)
- Cout total par modele
- Tri par qualite puis cout

## Lire les resultats

3 colonnes importantes dans l.output `score.py` :
- **Score** : combien de criteres binaires passes (ex : 18/26)
- **%** : ratio
- **Cost** : cout total du run pour ce modele

Un Haiku 4.5 qui fait 20/26 a $0.05 vaut probablement mieux qu.un Opus 4.7 qui fait 24/26 a $0.80 pour un usage quotidien. A toi de trancher selon l.enjeu.

## Quand rejouer

- Nouveau modele sort (Opus 5, Sonnet 5, GPT-6, Gemini 3, Grok 5)
- Update majeur d.un modele existant
- Tu changes de provider dans Claude Code et tu veux verifier que la qualite tient
- Tous les 2 mois si rien ne bouge (drift prix + drift modeles)

## Ce que ce projet n.est PAS

- Un benchmark generaliste pour comparer tous les modeles du marche (va voir Chatbot Arena ou LMSYS)
- Un test de speed / TTFT (pas encore, voir phase 2)
- Un test de tool use multi-turn (phase 2)
- Un test multimodal (phase 2)
- Un test de prompt caching (phase 2 : Anthropic direct, pas OpenRouter)

Ce projet = 6 tests de calibration + cout. Pour Damien. Pour trancher.

## Structure

```
Bench-API/
├── README.md
├── .env                           # API keys (gitignored)
├── harness/
│   ├── run.py                     # Runner (appel OpenRouter)
│   ├── score.py                   # Scoring auto
│   ├── models.json                # Modeles testes + prix
│   └── prompts.json               # 6 tests
├── fixtures/
│   └── vault_dump.md              # Assemble auto au 1er run (gitignored)
└── runs/
    └── YYYY-MM-DD_HHhMM/
        ├── <model>.md             # Reponses brutes
        ├── _metrics.csv           # Perf + cout
        └── _scores.csv            # Scoring auto
```

## Phase 2 (pas fait)

- Tool use multi-turn (vraies tool calls, pas "genere la commande")
- Prompt caching Anthropic direct (hors OpenRouter pour beneficier du caching)
- TTFT via streaming
- Dashboard GitHub Pages (reprendre le docs/ de Bench-LLM)
- Test multimodal (vision : extraire info d'un screenshot)
- Tests adversariaux supplementaires (injection prompt plus subtile, jailbreak)
