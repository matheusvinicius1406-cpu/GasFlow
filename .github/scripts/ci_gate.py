"""CI gate do release — GasFlow.

Aguarda a run de CI do commit da tag terminar e confere que os 4 jobs de
teste (backend, frontend, whatsapp, agent) passaram. E2E/Trivy NÃO fazem
parte do gate (problemas pré-existentes — ver docs/entregas-cupons-spec.md §4).

Variáveis de ambiente (injetadas pelo release.yml):
  GH_TOKEN  — token com leitura de Actions
  REPO      — "owner/repo"
  SHA       — commit apontado pela tag

Notas de projeto:
- A conclusão GERAL do CI pode ser "failure" por E2E/Trivy; o gate olha
  apenas os jobs de teste, individualmente.
- A tag deve apontar para um commit já na main (CI roda em push p/ main);
  enquanto a run não existir, o gate aguarda com timeout de 75 min —
  calendário calibrado para caber o job de teste mais lento (~10 min de
  suíte backend em runner hosted) MAIS um re-run completo em caso de flaky.
- Run concluída com job vermelho NÃO encerra o gate na primeira leitura:
  o gate segue consultando até o deadline, dando janela para um re-run
  manual no Actions (a run volta a in_progress e é reavaliada). Só o
  prazo esgotado com o vermelho persistente reprova o release.
- "Não transformar falha real em sucesso": o gate só espera mais; um job
  vermelho após o deadline continua falhando o release.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

API = "https://api.github.com"

REQUIRED_JOBS = (
    "Backend (ruff + pytest)",
    "Frontend (typecheck + build + tests)",
    "WhatsApp service (typecheck + build + tests)",
    "Agent (typecheck + build + tests)",
)

TIMEOUT_S = 75 * 60
POLL_INTERVAL_S = 60


def api_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "gasflow-ci-gate",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def find_run(repo: str, sha: str, token: str) -> int | None:
    data = api_get(
        f"/repos/{repo}/actions/workflows/ci.yml/runs?head_sha={sha}&per_page=10", token
    )
    runs = [r for r in data.get("workflow_runs", []) if r.get("head_sha") == sha]
    return runs[0]["id"] if runs else None


def check_jobs(repo: str, run_id: int, token: str) -> str | None:
    """None se os 4 jobs de teste passaram; senão, o resumo do problema."""
    data = api_get(f"/repos/{repo}/actions/runs/{run_id}/jobs?per_page=30", token)
    jobs = {j["name"]: j.get("conclusion") for j in data.get("jobs", [])}

    missing = [r for r in REQUIRED_JOBS if not any(n.startswith(r) for n in jobs)]
    failed = [
        n
        for n, c in jobs.items()
        if any(n.startswith(r) for r in REQUIRED_JOBS) and c != "success"
    ]
    if missing:
        return f"jobs de teste ausentes na run: {', '.join(missing)}"
    if failed:
        return f"jobs de teste reprovados: {', '.join(failed)}"
    return None


def dry_run() -> int:
    """Validação local sem esperar conclusão de CI (--dry-run).

    Confere: credenciais/variáveis presentes, conectividade com a API
    (query barata do repositório) e formato do SHA. Não bloqueia nem
    espera runs — serve para validar o setup antes de criar a tag.
    """
    token = os.environ.get("GH_TOKEN")
    repo = os.environ.get("REPO")
    sha = os.environ.get("SHA", "")

    if not token:
        print("dry-run: GH_TOKEN não definido.")
        return 1
    if not repo or "/" not in repo:
        print("dry-run: REPO deve ser 'owner/repo'.")
        return 1
    if len(sha) != 40 or not all(c in "0123456789abcdef" for c in sha.lower()):
        print("dry-run: SHA deve ser um commit SHA de 40 hex chars.")
        return 1

    try:
        data = api_get(f"/repos/{repo}", token)
        print(f"dry-run OK: API acessível para '{data.get('full_name', repo)}'.")
        print("dry-run OK: GH_TOKEN, REPO e SHA válidos.")
        return 0
    except Exception as exc:  # urllib.HTTPError, timeout etc.
        print(f"dry-run FALHOU: API inacessível: {exc}")
        return 1


def main() -> None:
    if "--dry-run" in sys.argv:
        sys.exit(dry_run())

    token = os.environ["GH_TOKEN"]
    repo = os.environ["REPO"]
    sha = os.environ["SHA"]
    deadline = time.monotonic() + TIMEOUT_S

    print(f"Aguardando CI para o commit {sha[:12]} (timeout {TIMEOUT_S // 60} min)...")
    attempt = 0
    red: str | None = None
    while True:
        attempt += 1
        run_id = find_run(repo, sha, token)
        if run_id is not None:
            run = api_get(f"/repos/{repo}/actions/runs/{run_id}", token)
            status, conclusion = run["status"], run.get("conclusion")
            print(
                f"tentativa {attempt}: run {run_id} status={status} conclusão={conclusion}"
            )
            if status == "completed":
                red = check_jobs(repo, run_id, token)
                if red is None:
                    print(
                        "Gate OK: backend/frontend/whatsapp/agent verdes "
                        "no commit da tag."
                    )
                    return
                remaining = max(0, int(deadline - time.monotonic()))
                print(
                    f"  ::warning::{red} — CI vermelho; o gate espera mais "
                    f"{remaining // 60} min para caber um re-run manual "
                    "antes de reprovar."
                )
            else:
                print(f"  status={status} — aguardando {POLL_INTERVAL_S}s…")
        else:
            print(
                f"tentativa {attempt}: run de CI ainda não registrada para {sha[:12]} — "
                f"aguardando {POLL_INTERVAL_S}s…"
            )

        if time.monotonic() >= deadline:
            if red:
                print(
                    f"::error::Timeout ({TIMEOUT_S // 60} min) com o CI ainda "
                    f"vermelho: {red}. Re-run manual no Actions se foi flaky — "
                    "o release não segue com job reprovado."
                )
            else:
                print(
                    "::error::Timeout aguardando CI (75 min). A tag deve apontar "
                    "para um commit já na main, e o CI precisa terminar dentro "
                    "do prazo — re-run manual se foi flaky."
                )
            sys.exit(1)
        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
