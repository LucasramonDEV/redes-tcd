#!/usr/bin/env bash
# Uso:  bash publicar.sh [private|public]     (padrão: private)
# Roda os testes; só se passarem, versiona e cria/sobe o repositório no GitHub.
set -euo pipefail
cd "$(dirname "$0")"

VIS="${1:-private}"
NOME="redes-tcd"

echo "==> 1/4 Testes"
python3 testes/test_handshake.py

echo "==> 2/4 GitHub CLI"
command -v gh >/dev/null || { echo "Instale o gh: brew install gh"; exit 1; }
gh auth status >/dev/null 2>&1 || gh auth login

echo "==> 3/4 Commit"
[ -d .git ] || git init -b main
git add .
git commit -m "Handshake de 3 vias, testes e secao de processo com IA" || echo "(nada novo para commitar)"

echo "==> 4/4 Repositório ($VIS)"
if git remote get-url origin >/dev/null 2>&1; then
  git push -u origin main
else
  gh repo create "$NOME" "--$VIS" --source=. --push
fi
gh repo view --web || true
echo "Pronto."
