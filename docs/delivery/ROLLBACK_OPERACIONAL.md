# GasFlow — Rollback Operacional

> **Documento, não execução.** Nenhum passo deste arquivo foi rodado nesta
> frente. Nada foi migrado, nenhum serviço foi parado e o SQLite operacional não
> foi tocado.

## 0. Situação de partida (por que o rollback é barato hoje)

| Item | Estado |
|---|---|
| Produção real | **GasFlow Desktop** + backend local `127.0.0.1:8000` |
| Banco real | SQLite `%APPDATA%\gasflow-desktop\gasflow.db` (+ `gasflow.db.backups\`) |
| Portal | servido pelo próprio backend do Desktop (`FRONTEND_DIST`) |
| WhatsApp | sessão no userData do Desktop (`whatsapp-data\`, `Partitions\wa-web-primary`) |
| Stack nova (Home Server) | **configurada, nunca operada**; `docker-compose.homeserver*.yml` + `deploy/home-server/` |
| Migração de dados | **não executada** (frente OpenCode em paralelo) |

Consequência: **o rollback hoje é “não implantar”**. O custo real aparece no
minuto em que a stack nova começar a receber pedidos. Por isso o corte precisa
de janela, backup e critério de abortar.

---

## 1. Sinais para abortar a implantação

Abortar (ou nem iniciar) se **qualquer** item for verdadeiro:

- [ ] Não existe backup **testado** (restore em ambiente limpo) do Postgres novo
      **e** cópia do SQLite.
- [ ] A migração SQLite→Postgres não foi ensaiada em cópia com contagem de
      registros conferida.
- [ ] O smoke (`scripts/smoke-test.sh`) falha em qualquer rota de borda
      (`/health`, `/ready`, `/api/v1/health`, `/auth/me` → 401,
      `/metrics` → 404).
- [ ] `docker compose ps` tem serviço `unhealthy` ou reiniciando em loop.
- [ ] Login de operador ou de entregador não completa pela borda.
- [ ] `/driver/*` ou `/ws` respondem diferente do esperado para o app.
- [ ] A sessão de WhatsApp não reconecta (exigiria novo QR em horário de pico).
- [ ] Contagem de pedidos/clientes/entregas no Postgres ≠ SQLite (tolerância
      zero para pedidos do dia).
- [ ] Latência/uso de RAM do servidor degrada a operação (HDD saturado,
      swap constante).
- [ ] Não há responsável técnico disponível durante a janela.
- [ ] É horário de pico de entregas ou há campanha de WhatsApp agendada.

**Regra:** na dúvida, aborta. Reagendar custa menos que perder pedido.

---

## 2. Como voltar ao Desktop

Pré-requisitos: o aplicativo **GasFlow Desktop não é alterado** pela stack nova
(arquivos e `%APPDATA%` intactos), então “voltar” é parar o que foi adicionado e
garantir que o Desktop segue dono da porta 8000 e do SQLite.

1. **Parar a stack nova** (somente se ela foi iniciada), sem remover volumes:
   `docker compose -f docker-compose.prod.yml -f docker-compose.homeserver.yml down`
   (no laboratório: acrescentar `-f docker-compose.homeserver.lab.yml` e usar o
   projeto `gasflow-hs-lab`). **Não** usar `-v` em ambiente com dados que possam
   ser necessários para diagnóstico.
2. **Não** apagar volumes, imagens ou logs antes de coletar evidência.
3. Confirmar que o serviço/atalho do Desktop continua íntegro e que o processo
   do backend voltou a responder em `127.0.0.1:8000` (`GET /health` → 200).
4. Se o Desktop estava fechado, abrir pelo atalho normal do Windows (não
   reinstalar, não “reparar”, não atualizar durante o incidente).
5. Se algum cliente apontou para a stack nova (app/portal), avisar para voltar
   ao endereço antigo (`http://<ip>:8000` na LAN ou `127.0.0.1:8000` no host).
6. Registrar horário do aborto, motivo e evidências (logs, `ps`, prints).

---

## 3. Como preservar o SQLite

- **Nunca** abrir o SQLite com a stack nova, nem apontar `DATABASE_URL` para
  ele: a stack usa Postgres e qualquer escrita concorrente corrompe o arquivo.
- Antes de qualquer janela: copiar `gasflow.db`, `-wal` e `-shm` **e** a pasta
  `gasflow.db.backups\` para um destino separado (HD externo/nuvem) **com o app
  fechado**, para garantir consistência.
- Manter o padrão de backup automático do Desktop ativo até o corte definitivo.
- Não “limpar” nem compactar o arquivo durante a janela.
- Se for necessário restaurar: fechar o app, guardar o arquivo atual como
  `gasflow.db.pre-rollback-<data>`, copiar o backup escolhido e abrir o app.
- **Nunca** restaurar por cima do arquivo em uso com o app aberto.

---

## 4. Como evitar perda de pedidos

1. **Congelar entrada** de pedidos novos no início da janela (operador avisado).
2. **Snapshot antes do corte:** backup do SQLite + dump do Postgres (quando
   houver) + exportação da lista de pedidos abertos (código, status, valor).
3. Durante a janela, **uma única fonte de escrita**: ou Desktop, ou stack nova —
   nunca as duas recebendo pedidos.
4. Se um pedido for criado na stack nova e houver rollback, ele **não existe** no
   SQLite: exportar/reimportar manualmente (ou cancelar com o cliente) antes de
   voltar. Registrar cada caso.
5. Só reabrir a entrada de pedidos depois de validar o §6 e avisar os
   operadores.
6. Mensagens de WhatsApp programadas devem ser pausadas durante a janela.

---

## 5. Como comparar o estado antigo × novo

Comparações mínimas (executar em cópia, nunca no banco em produção):

| Dado | Antigo (SQLite) | Novo (Postgres) | Critério |
|---|---|---|---|
| Clientes | `COUNT(clientes)` | `COUNT(clients)` | igual |
| Pedidos | `COUNT(pedidos)` | `COUNT(orders)` | igual |
| Pedidos por status | agrupado | agrupado | igual |
| Entregas | `COUNT(entregas)` | `COUNT(delivery_records)` | igual |
| Pagamentos/recebíveis | soma por período | soma por período | igual (centavos) |
| Amostra de 5 pedidos | código + total + status | idem | idêntico |
| Último pedido criado | código/hora | presente | presente |

Ferramentas: consultas SQL somente-leitura; exportação CSV do Desktop para
conferência manual. Divergência **não** é ajustada “na mão” no banco novo sem
registro; é motivo de aborto.

---

## 6. Como validar que o atendimento voltou ao normal

1. `GET http://127.0.0.1:8000/health` → 200 (liveness) e `/ready` → 200.
2. Login de operador no Desktop e no portal embutido.
3. Criar **um pedido de teste** identificado (`ROLLBACK-TEST`) e concluir o
   ciclo até `DELIVERED`; conferir financeiro.
4. Abrir a tela de entregas e o rastreio público (`/track/{token}`).
5. App do entregador (se aplicável): login + lista de entregas.
6. WhatsApp: enviar **uma** mensagem para número interno de teste e confirmar
   recebimento.
7. Confirmar com o operador que os pedidos do dia estão visíveis e com status
   correto.
8. Monitorar 30–60 min: erros no log do backend do Desktop, reclamações de
   entregadores, fila de mensagens.
9. Registrar o resultado e remover o pedido de teste (`ROLLBACK-TEST`) após a
   validação.

Tempo-alvo proposto: **RTO ≤ 2 h** para voltar ao Desktop; **RPO = último backup
do SQLite** (o backup automático do Desktop é a rede de segurança até o corte).

---

## 7. Quando **não** seguir com a migração

- Restore nunca testado, ou teste falhou.
- Migração sem contagem conferida / sem rollback escrito.
- Sessão de WhatsApp não reconectável em janela curta.
- Disco do servidor com sinal de falha (SMART) ou sem espaço para backup local.
- Sem domínio/URL fixa para o app e o rastreio (link efêmero quebra o campo).
- Equipe de campo sem treinamento ou sem aparelho homologado.
- Véspera de fim de semana/feriado, pico de pedidos ou campanha agendada.
- Falta de aprovação formal da empresa.

Nesses casos, a decisão correta é **manter o Desktop** e registrar a pendência.

---

## 8. Responsabilidades e comunicação

| Papel | Responsabilidade |
|---|---|
| Integrador técnico | decidir aborto, executar o rollback, validar §6 |
| Frente OpenCode | backup, restore e migração (DEPENDÊNCIA OPENCODE) |
| Operação | congelar pedidos, comunicar clientes, confirmar normalidade |
| Empresa | aprovar janela e critério de aceite (nível C) |

Comunicação mínima: aviso 24 h antes, mensagem no início da janela, aviso de
conclusão ou aborto com motivo, e registro em
`docs/delivery/STATUS_DE_ENTREGA.md` (§6/§7) na próxima revisão.

---

## 9. O que já está pronto para o rollback

- O Desktop **não foi alterado** por nenhuma frente OPS (o OPS-01B é aditivo:
  novos arquivos de compose + documentação).
- Não existe dependência da stack nova para o atendimento atual.
- Backup do SQLite é automático (Desktop) e continua ativo.
- O laboratório é isolado (`gasflow-hs-lab`): subir/derrubar não toca em
  volumes, rede ou segredos do ambiente real.

O que **falta** para o rollback de nível C: restore testado do Postgres,
migração ensaiada e responsável designado — itens da frente OpenCode.
