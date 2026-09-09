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
    ("dark_mode", "appearance", False, "Tema escuro no frontend"),
    ("brand_color", "appearance", "#E30613", "Cor primária do GasFlow"),
]

SETTING_CATEGORIES = ("general", "whatsapp", "notifications", "integrations", "operations", "appearance")
