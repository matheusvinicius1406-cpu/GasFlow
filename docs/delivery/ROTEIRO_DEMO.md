# GasFlow — Roteiro de Demonstração (empresa)

| | |
|---|---|
| **Duração alvo** | 20–30 min (12 passos) |
| **Ambiente recomendado** | **GasFlow Desktop** operacional hoje (`http://127.0.0.1:8000`), banco SQLite do desktop |
| **Dados** | **somente fictícios** (prefixo `DEMO`), nenhum cliente/telefone real |
| **WhatsApp** | somente modo seguro (leitura/tela) — **não** parear número real durante a demo |
| **O que NÃO fazer** | subir Docker, migrar o SQLite, rodar backup, alterar `.env`, apagar dados reais |

> **Por que no Desktop e não na stack nova?** O Desktop é o que está em
> produção hoje. O perfil Home Server (OPS-01B) está configurado, mas a
> migração de dados/backup é de outra frente e não foi validada. Demonstrar na
> stack não exercitada trocaria risco técnico por risco de plateia.

---

## 0. Preparação (30 min antes)

1. Conferir que o Desktop está no ar: abrir o app ou `http://127.0.0.1:8000`
   → tela de login. (Sintoma de problema: `GET /health` ≠ 200.)
2. Fazer uma **cópia** do SQLite do desktop antes de criar dados de demo
   (`%APPDATA%\gasflow-desktop\gasflow.db` + `gasflow.db.backups\`). Não mover
   nem restaurar durante a demo.
3. Criar os dados fictícios **antes** da apresentação (passos 3–7), para a demo
   ser navegação, não digitação sob pressão.
4. Fechar abas/notificações que possam expor dados reais; usar tenant/ambiente
   de demonstração se já existir.
5. Ter à mão: `docs/delivery/ROTEIRO_DEMO.md` (este), janela do navegador com
   o sistema, e o app do entregador **apenas se** houver aparelho preparado.
6. **WhatsApp:** se a sessão real estiver conectada, mostrar somente telas de
   leitura (contatos/histórico). Não disparar campanha nem mensagem.

---

## 1. Login

- **Pré-requisito:** app Desktop aberto; usuário admin da demo.
- **Fazer:** abrir o sistema → informar usuário e senha → entrar.
- **Esperado:** dashboard carrega; menu respeita as permissões do perfil.
- **Comprovar:** tela inicial + cabeçalho com usuário; `/health` → 200.
- **Plano B:** se a senha falhar, entrar com outro usuário de demo; nunca
  resetar a senha do admin real durante a demo.

## 2. Dashboard

- **Pré-requisito:** sessão ativa.
- **Fazer:** percorrer os cartões de indicadores e o atalho de pedidos.
- **Esperado:** números coerentes com os dados fictícios criados; sem erro de
  carregamento.
- **Comprovar:** cartões preenchidos; console do navegador sem erro 5xx.
- **Plano B:** se um cartão depender de janela de período, ajustar o filtro
  para “hoje/7 dias”.

## 3. Criar cliente fictício

- **Pré-requisito:** perfil com permissão de clientes.
- **Fazer:** Clientes → Novo → nome `DEMO Cliente`, telefone de teste
  (ex.: `9100000000`), e-mail opcional → salvar.
- **Esperado:** cliente aparece na lista e abre no detalhe.
- **Comprovar:** busca por `DEMO` retorna o registro; “Customer 360” abre.
- **Plano B:** usar um cliente `DEMO` já criado na preparação.

## 4. Endereço do cliente

- **Pré-requisito:** cliente aberto em edição.
- **Fazer:** preencher rua/número/complemento/referência/bairro → salvar.
- **Esperado:** endereço aparece no detalhe do cliente.
- **Comprovar:** reabrir o cliente e ver os campos persistidos.
- **Plano B / transparência:** o sistema hoje guarda **um endereço por
  cliente** (não existe múltiplos endereços). Se a empresa perguntar, dizer que
  está no backlog — não improvisar dois cadastros para “simular”.

## 5. Criar produto

- **Pré-requisito:** permissão de produtos.
- **Fazer:** Produtos → Novo → `DEMO Gás P13`, preço fictício, estoque inicial
  10 → salvar.
- **Esperado:** produto na lista, com preço e estoque.
- **Comprovar:** abrir o produto; estoque exibido.
- **Plano B:** usar produto `DEMO` pré-criado.

## 6. Criar pedido

- **Pré-requisito:** cliente e produto de demo prontos.
- **Fazer:** Pedidos → Novo → escolher `DEMO Cliente` → adicionar
  `DEMO Gás P13` (qtd 1) → salvar.
- **Esperado:** pedido criado com código; status inicial `PENDING`.
- **Comprovar:** abrir o pedido; itens e total corretos.
- **Plano B:** se o formulário exigir campos extras, usar o pedido `DEMO`
  pré-criado e explicar o fluxo.

## 7. Atribuir entregador

- **Pré-requisito:** entregador `DEMO Entregador` cadastrado (Drivers → Novo) e
  pedido em `PENDING`.
- **Fazer:** Pedido → atribuir entregador (ou tela Entregas → atribuir).
- **Esperado:** status vai para `ASSIGNED`; entrega vinculada ao entregador.
- **Comprovar:** lista de entregas do entregador na tela Entregas.
- **Plano B:** atribuir por `PATCH /orders/{codigo}/assign-driver` na tela de
  entregas, se o botão estiver oculto por permissão.

## 8. Alterar status até “chegou”

- **Pré-requisito:** entrega atribuída.
- **Fazer:** Entregas → iniciar rota (`EN_ROUTE`) → marcar chegada
  (`ARRIVED`).
- **Esperado:** status muda e o histórico/timeline registra cada passo.
- **Comprovar:** timeline da entrega com os eventos.
- **Plano B:** se o botão “chegou” não estiver disponível no perfil, usar a
  tela de entregas do operador (é o mesmo `arrive` do backend).

## 9. Acompanhar o pedido (rastreio)

- **Pré-requisito:** entregador com posição enviada OU link público emitido.
- **Fazer:** na tela de entregadores, gerar link público e abrir
  `/track/{token}` em outra aba.
- **Esperado:** mapa com a posição mais recente; sem dados pessoais do cliente.
- **Comprovar:** página pública abre **sem login** e mostra só posição/horário.
- **Plano B:** se não houver posição (sem GPS no aparelho), mostrar o mapa do
  dashboard e explicar que o link depende de uma posição recente. **Não** usar
  GPS falso e chamar de validação.

## 10. Registrar a entrega

- **Pré-requisito:** entrega em `ARRIVED`.
- **Fazer:** Entregas → Concluir (prova `MANUAL_CONFIRMATION`).
- **Esperado:** status `DELIVERED`, data/hora e prova registradas; estoque
  debitado (regra do projeto: débito só em `DELIVERED`).
- **Comprovar:** pedido/entrega com status final e histórico; produto com
  estoque reduzido.
- **Plano B:** se a conclusão falhar, **não** insistir: usar uma entrega `DEMO`
  já concluída na preparação e registrar o defeito.

## 11. Financeiro / histórico

- **Pré-requisito:** pedido `DELIVERED`.
- **Fazer:** Financeiro → visão geral do período de hoje; abrir o lançamento do
  pedido.
- **Esperado:** recebível/lançamento coerente com o pedido; relatório do dia
  consistente.
- **Comprovar:** valor do pedido = valor no financeiro.
- **Plano B:** mostrar o relatório de período com filtro “hoje”.

## 12. WhatsApp (modo seguro)

- **Pré-requisito:** sessão já conectada (leitura) **ou** nenhuma sessão.
- **Fazer:** abrir o módulo WhatsApp e mostrar contatos/histórico e a tela de
  campanhas **sem disparar**.
- **Esperado:** telas carregam; nada é enviado.
- **Comprovar:** nenhuma mensagem nova no aparelho da empresa.
- **Plano B:** se a sessão não estiver conectada, mostrar a tela explicando o
  pareamento por QR e usar capturas da preparação. **Nunca** parear o número da
  empresa no meio da demo.

---

## 13. Se a empresa pedir para ver o app do entregador

- **Só com aparelho preparado e autorizado.** APK da v1.2.1 instalado, servidor
  digitado como `http://<ip>` (porta 80 do servidor web) — **sem `:8000`**,
  que não é publicado no Home Server.
- Mostrar: login, lista de entregas, iniciar, GPS em movimento.
- **Limitação a declarar:** concluir exige que o operador marque “chegou”; o app
  ainda não tem essa ação. Fila offline e GPS em segundo plano ainda não são
  persistentes/validados.
- **Plano B:** demonstrar pelo desktop e explicar que a validação de campo do
  app está na pendência de homologação.

---

## 14. Encerramento e limpeza

1. Não apagar dados reais. Os registros `DEMO` podem ficar (identificados pelo
   prefixo) ou ser desativados depois, com o backup feito no passo 0.
2. Conferir que nenhuma campanha foi disparada e nenhuma sessão de WhatsApp foi
   alterada.
3. Registrar no final: passos que funcionaram, passos com plano B e horário —
   isso vira evidência para `CHECKLIST_ACEITE.md` (nível A).
4. **Não** rodar migração, Docker, restore ou deploy depois da demo sem janela
   combinada.
