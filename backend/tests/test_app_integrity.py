"""Guard de integridade do app — falha o CI quando algo fica órfão ou quebrado.

Cruza frontend ↔ backend ↔ desktop ↔ WhatsApp ↔ mobile ↔ banco para que nenhuma
tela fique sem endpoint, nenhuma rota fique sem link, nenhuma ponte IPC fique
sem handler e nenhum dado fique invisível. Roda no job `backend` do CI, junto do
pytest, em pull_request e push.

Exceções legítimas ficam em `tests/integrity_allowlist.json`, cada uma com
motivo — adicionar algo novo sem justificar faz o teste falhar.

Para ver o relatório completo (com os itens já previstos na allowlist):

    python -m tests.integrity_audit --report
"""

from tests import integrity_audit as audit


def test_app_integrity() -> None:
    findings = audit.collect_findings()
    pending = audit.unallowed(findings)

    detalhe = "; ".join(f"[{f.check}] {f.target} — {f.detail}" for f in pending)
    assert not pending, (
        f"{len(pending)} problema(s) de integridade fora da allowlist "
        f"(rode `python -m tests.integrity_audit --report`): {detalhe}"
    )
