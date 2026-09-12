"""
RBAC Seed — catálogo de permissões, roles de sistema e matriz.

Fonte compartilhada usada em DOIS pontos:
1. Migration e4f7a9b1c3d5 (bancos novos versionados);
2. Boot do Desktop (desktop_entry), DEPOIS do init_db — cobre bancos
   legados `create_all` que receberam `stamp head` (a migration não roda
   neles, mas o boot sim).

Idempotente: INSERT OR IGNORE / upsert — rodar N vezes não duplica.
Banco = fonte de verdade; ROLE_PERMISSIONS (código) = fallback.
"""

import json
import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

# ── Permissões do catálogo (resource.action) ─────────────────────────
PERMISSIONS: list[tuple[str, str, str]] = [
    # (code, module, description)
    ("customer.read", "customer", "Visualizar clientes"),
    ("customer.write", "customer", "Editar clientes"),
    ("customer.create", "customer", "Criar clientes"),
    ("order.read", "order", "Visualizar pedidos"),
    ("order.create", "order", "Criar pedidos"),
    ("order.update", "order", "Atualizar pedidos"),
    ("order.cancel", "order", "Cancelar pedidos"),
    ("product.read", "product", "Visualizar produtos"),
    ("product.write", "product", "Editar produtos"),
    ("product.create", "product", "Criar produtos"),
    ("inventory.read", "inventory", "Visualizar estoque"),
    ("inventory.adjust", "inventory", "Ajustar estoque"),
    ("inventory.snapshot", "inventory", "Gerar snapshot diário de estoque"),
    ("finance.read", "finance", "Visualizar financeiro"),
    ("finance.receive", "finance", "Registrar recebimentos"),
    ("finance.refund", "finance", "Estornar pagamentos"),
    ("finance.export_pdf", "finance", "Exportar relatórios em PDF"),
    ("finance.export_docx", "finance", "Exportar relatórios em Word"),
    ("whatsapp.read", "whatsapp", "Visualizar WhatsApp"),
    ("whatsapp.send", "whatsapp", "Enviar mensagens WhatsApp"),
    ("whatsapp.takeover", "whatsapp", "Assumir conversas"),
    ("conversation.read", "conversation", "Visualizar conversas"),
    ("conversation.takeover", "conversation", "Assumir conversas (agente)"),
    ("workflow.read", "workflow", "Visualizar workflows"),
    ("workflow.execute", "workflow", "Executar workflows"),
    ("agent.read", "agent", "Visualizar agente"),
    ("agent.execute", "agent", "Executar agente"),
    ("automation.read", "automation", "Visualizar automações"),
    ("automation.pause", "automation", "Pausar automações"),
    ("user.read", "user", "Visualizar usuários"),
    ("user.create", "user", "Criar usuários"),
    ("user.update", "user", "Editar usuários"),
    ("user.reset_password", "user", "Resetar senhas"),
    ("user.deactivate", "user", "Desativar usuários"),
    ("role.manage", "user", "Gerenciar papéis"),
    ("permission.assign", "user", "Atribuir permissões"),
    ("delivery.read", "delivery", "Visualizar entregas"),
    ("delivery.manage", "delivery", "Gerenciar entregas"),
    ("delivery.assign", "delivery", "Atribuir entregas a motoristas"),
    ("driver.view_location", "driver", "Ver localização de motoristas em tempo real"),
    ("driver.view_history", "driver", "Ver histórico de localização de motoristas"),
    ("fiscal.issue_nfce", "fiscal", "Emitir NFC-e (modelo 65)"),
    ("fiscal.issue_nfe", "fiscal", "Emitir NF-e (modelo 55)"),
    ("fiscal.cancel", "fiscal", "Cancelar notas fiscais"),
    ("ai.use", "ai", "Usar módulo de Inteligência"),
    ("settings.read", "settings", "Visualizar configurações"),
    ("settings.write", "settings", "Alterar configurações"),
    ("audit.view", "audit", "Visualizar trilha de auditoria"),
    # Curingas por módulo (usados pela matriz ROLE_MATRIX): o catálogo precisa
    # conter TODOS os códigos atribuíveis para que a matriz role_permissions
    # possa referenciá-los e o loader expandi-los.
    ("customer.*", "customer", "Todos os direitos de clientes (wildcard)"),
    ("order.*", "order", "Todos os direitos de pedidos (wildcard)"),
    ("product.*", "product", "Todos os direitos de produtos (wildcard)"),
    ("inventory.*", "inventory", "Todos os direitos de estoque (wildcard)"),
    ("finance.*", "finance", "Todos os direitos do financeiro (wildcard)"),
    ("whatsapp.*", "whatsapp", "Todos os direitos de WhatsApp (wildcard)"),
    ("conversation.*", "conversation", "Todos os direitos de conversas (wildcard)"),
    ("workflow.*", "workflow", "Todos os direitos de workflows (wildcard)"),
    ("agent.*", "agent", "Todos os direitos do agente (wildcard)"),
    ("automation.*", "automation", "Todos os direitos de automações (wildcard)"),
    ("coupon.*", "coupon", "Todos os direitos de cupons (wildcard)"),
    ("integration.*", "integration", "Todos os direitos de integrações (wildcard)"),
    # Permissões específicas do fluxo do motorista (role DRIVER).
    ("delivery.read.assigned", "delivery", "Visualizar entregas atribuídas a si"),
    ("delivery.accept", "delivery", "Aceitar entrega atribuída"),
    ("delivery.start", "delivery", "Iniciar rota de entrega"),
    ("delivery.arrive", "delivery", "Registrar chegada no destino"),
    ("delivery.complete", "delivery", "Concluir entrega"),
    ("delivery.fail", "delivery", "Registrar falha de entrega"),
    ("route.read.assigned", "driver", "Visualizar rota atribuída a si"),
    ("location.write.self", "driver", "Enviar a própria localização"),
    ("proof.write.assigned", "driver", "Anexar prova de entrega atribuída"),
    ("admin.*", "admin", "Acesso total (wildcard)"),
]

# Matriz role → permissões (espelha ROLE_PERMISSIONS + novas do roadmap).
ROLE_MATRIX: dict[str, list[str]] = {
    "ADMIN": ["admin.*"],
    "MANAGER": [
        "customer.*",
        "order.*",
        "product.*",
        "inventory.*",
        "finance.*",
        "whatsapp.*",
        "conversation.*",
        "workflow.*",
        "agent.*",
        "automation.*",
        "user.read",
        "user.update",
        "user.reset_password",
        "delivery.read",
        "delivery.manage",
        "delivery.assign",
        "driver.view_location",
        "driver.view_history",
        "ai.use",
        "settings.read",
        "audit.view",
        "coupon.*",
        "integration.*",
    ],
    "OPERATOR": [
        "customer.read",
        "customer.write",
        "order.read",
        "order.create",
        "order.update",
        "product.read",
        "inventory.read",
        "finance.read",
        "whatsapp.read",
        "whatsapp.send",
        "whatsapp.takeover",
        "conversation.read",
        "conversation.takeover",
        "coupon.read",
        "settings.read",
        "delivery.read",
    ],
    "DRIVER": [
        "customer.read",
        "order.read",
        "delivery.read.assigned",
        "delivery.accept",
        "delivery.start",
        "delivery.arrive",
        "delivery.complete",
        "delivery.fail",
        "route.read.assigned",
        "location.write.self",
        "proof.write.assigned",
    ],
    "VIEWER": [
        "customer.read",
        "order.read",
        "product.read",
        "inventory.read",
        "finance.read",
        "delivery.read",
        "settings.read",
    ],
    "CUSTOMER": ["order.read", "product.read"],
    "SYSTEM": ["admin.*"],
}


def seed_rbac(conn: Connection) -> dict[str, int]:
    """Popula permissions + role_permissions + auth_roles de sistema.

    Retorna contadores para logging/testes. Idempotente.
    """
    from app.domain.security.models import SystemRole

    inserted_permissions = 0
    now = datetime.utcnow().isoformat()
    for code, module, description in PERMISSIONS:
        # created_at explícito: a coluna é NOT NULL sem server default e o
        # INSERT OR IGNORE engoliria a violação silenciosamente (0 linhas).
        result = conn.execute(
            text(
                "INSERT OR IGNORE INTO permissions (code, description, module, created_at) "
                "VALUES (:code, :description, :module, :created_at)"
            ),
            {"code": code, "description": description, "module": module, "created_at": now},
        )
        inserted_permissions += result.rowcount

    id_by_code: dict[str, int] = {
        row.code: row.id for row in conn.execute(text("SELECT id, code FROM permissions")).fetchall()
    }

    matrix_rows = 0
    for role_name, perms in ROLE_MATRIX.items():
        system_role = SystemRole[role_name].value  # todos os 7 roles estão no enum
        row = conn.execute(
            text("SELECT id FROM auth_roles WHERE name = :name"),
            {"name": role_name},
        ).fetchone()
        if row is None:
            role_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO auth_roles (id, name, system_role, permissions, created_at) "
                    "VALUES (:id, :name, :system_role, :permissions, :created_at)"
                ),
                {
                    "id": role_id,
                    "name": role_name,
                    "system_role": system_role,
                    "permissions": json.dumps(perms),
                    "created_at": now,
                },
            )
        else:
            role_id = row.id
            conn.execute(
                text("UPDATE auth_roles SET permissions = :permissions WHERE id = :id"),
                {"id": role_id, "permissions": json.dumps(perms)},
            )
        for code in perms:
            pid = id_by_code.get(code)
            if pid is None:
                continue  # curinga específico (ex.: delivery.*) não catalogado
            result = conn.execute(
                text(
                    "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id)"
                ),
                {"role_id": role_id, "permission_id": pid},
            )
            matrix_rows += result.rowcount

    return {
        "permissions_inserted": inserted_permissions,
        "matrix_rows_inserted": matrix_rows,
        "roles": len(ROLE_MATRIX),
    }
