#!/usr/bin/env bash
# Workflow de publication Bench-API :
# 1. Score le run specifie (ou le dernier si non fourni)
# 2. Rebuild docs/data.json
# 3. Commit + push -> declenche rebuild GitHub Pages automatique
#
# Usage :
#   ./publish.sh                        # dernier run (auto)
#   ./publish.sh 2026-04-17_11h52       # run precis
#   ./publish.sh --skip-score           # juste rebuild + push (si deja score)

set -e

cd "$(dirname "$0")"

# Activation venv si present
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

SKIP_SCORE=0
RUN_NAME=""
for arg in "$@"; do
  case "$arg" in
    --skip-score) SKIP_SCORE=1 ;;
    *) RUN_NAME="$arg" ;;
  esac
done

# Si pas de run fourni, prendre le plus recent
if [ -z "$RUN_NAME" ] && [ "$SKIP_SCORE" -eq 0 ]; then
  RUN_NAME=$(ls -1t runs/ 2>/dev/null | head -1)
  if [ -z "$RUN_NAME" ]; then
    echo "ERREUR : aucun run dans runs/. Lance d'abord python harness/run.py."
    exit 1
  fi
  echo "[publish] Dernier run detecte : $RUN_NAME"
fi

# 1. Score (sauf si --skip-score)
if [ "$SKIP_SCORE" -eq 0 ]; then
  echo "[publish] Scoring $RUN_NAME..."
  python harness/score.py "$RUN_NAME"
fi

# 2. Rebuild dashboard
echo "[publish] Rebuild docs/data.json..."
python harness/build_dashboard.py

# 3. Commit + push si changement
if git diff --quiet docs/data.json; then
  echo "[publish] docs/data.json inchange. Rien a push."
  exit 0
fi

echo "[publish] Commit..."
git add docs/data.json

# Message commit base sur le run name
if [ -n "$RUN_NAME" ]; then
  MSG="chore(bench-api): publish run $RUN_NAME"
else
  MSG="chore(bench-api): rebuild dashboard"
fi

git commit -m "$MSG"

# 4. Pull rebase + push (regle : jamais push sans rebase)
echo "[publish] Pull rebase..."
git pull --rebase

echo "[publish] Push..."
git push

echo ""
echo "[publish] OK. Dashboard accessible sous 1-2 min :"
echo "  https://damienbihel.github.io/bench-api/"
