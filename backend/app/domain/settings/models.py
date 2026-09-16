"""Settings domain — defaults do quadro de configurações (seed inicial)."""

DEFAULT_SETTINGS = [
    # (key, category, value, description)
    ("site_name", "general", "GasFlow", "Nome da plataforma"),
    ("timezone", "general", "America/Sao_Paulo", "Fuso horário padrão"),
    ("currency", "general", "BRL", "Moeda principal"),
    ("whatsapp_auto_reply", "whatsapp", True, "Resposta automática no WhatsApp"),
    ("whatsapp_agent_enabled", "whatsapp", True, "IA do WhatsApp ativa"),
    ("whatsapp_reactivate_enabled", "whatsapp", False, "Reativação de clientes inativos (WhatsApp)"),
    ("whatsapp_reactivate_days", "whatsapp", 90, "Dias de inatividade para reativar"),
    (
        "whatsapp_reactivate_template",
        "whatsapp",
        "Olá {{nome}}! Faz tempo que não falamos. Para manter seus dados atualizados, confirme seu endereço:\nRua: {{rua}} Nº{{numero}}\nComplemento: {{complemento}}\nBairro: {{bairro}}\nSe algum dado estiver errado, responda com a correção. \U0001f60a",
        "Template da mensagem de reativação",
    ),
    ("notify_order_created", "notifications", True, "Notificar admin quando pedido chega"),
    (
        "notify_driver_webhook",
        "notifications",
        "",
        "Webhook para notificar motoristas",
    ),
    ("pix_enabled", "integrations", True, "Habilitar PIX"),
    (
        "payment_methods",
        "integrations",
        ["PIX", "DINHEIRO", "CARTAO"],
        "Métodos de pagamento disponíveis",
    ),
    ("delivery_estimation_mode", "operations", "heuristic", "heuristic ou osrm"),
    # ── IA (Item 3) ─────────────────────────────────────────
    # Toggle admin da IA. O provider_factory lê esta chave em runtime;
    # desligar aqui derruba TODA a IA (Copilot, WhatsApp agent) de imediato,
    # sem restart. Fallback externo não existe (Fase 4.2, cenário B).
    ("ai.enabled", "ai", True, "Ativar Inteligência (IA)"),
    # ── App do Entregador (LGPD) ────────────────────────────
    # Janela de trabalho do motorista: localização só é aceita dentro dela
    # (driver_location_service). "HH:MM"; suporta travessia de meia-noite.
    ("driver.work_hours.start", "operations", "06:00", "Início do horário de trabalho (rastreamento)"),
    ("driver.work_hours.end", "operations", "22:00", "Fim do horário de trabalho (rastreamento)"),
    (
        "driver.tracking.interval_seconds",
        "operations",
        120,
        "Intervalo de envio de posição pelo app do entregador (segundos)",
    ),
    ("dark_mode", "appearance", False, "Tema escuro no frontend"),
    ("brand_color", "appearance", "#E30613", "Cor primária do GasFlow"),
    # ── Impressão em tempo real (F3) ────────────────────────
    # Auto-print só dispara para pedidos nestes status (lista separada
    # por vírgula). Default "PAID,CONFIRMED": pedido novo sem filtro
    # imprimiria lixo (itens em draft, cancelados, etc.).
    (
        "printer.auto_print.min_status",
        "operations",
        "PAID,CONFIRMED",
        "Status que disparam auto-print (lista separada por vírgula)",
    ),
]

SETTING_CATEGORIES = ("general", "whatsapp", "notifications", "integrations", "operations", "appearance", "ai")
