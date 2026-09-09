/** Fixtures de HTML para os testes do agente. */

export const ORDERS_TABLE_HTML = `<!DOCTYPE html>
<html><head><title>Painel de Pedidos — Revenda X</title></head>
<body>
<h1>Últimos pedidos</h1>
<table class="orders" id="grid">
  <tr><th>Pedido</th><th>Cliente</th><th>Telefone</th><th>Produto</th><th>Qtd</th><th>Valor</th><th>Status</th></tr>
  <tr><td>1001</td><td>Maria Souza</td><td>(91) 98168-9969</td><td>Botijão P13</td><td>2</td><td>R$ 220,00</td><td>pendente</td></tr>
  <tr><td>1002</td><td>João Lima</td><td>91 99123-4567</td><td>Água 20L</td><td>1</td><td>R$ 15,90</td><td>pago</td></tr>
  <tr><td>1003</td><td>Ana Costa</td><td></td><td>P45</td><td>3</td><td>R$ 300,00</td><td>pendente</td></tr>
  <tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
</table>
</body></html>`;

export const MULTI_ITEM_HTML = `<!DOCTYPE html>
<html><head><title>Vendas</title></head><body>
<table>
  <tr><th>Nº</th><th>Cliente</th><th>Endereço</th><th>Itens</th><th>Total</th></tr>
  <tr><td>2001</td><td>Carlos Prado</td><td>Rua das Flores, 12, Centro</td><td>2x Botijão P13; 1x Água 20L</td><td>235,90</td></tr>
</table>
</body></html>`;

export const NO_TABLE_HTML = `<html><head><title>Login</title></head><body>
<form><input name="user"><input name="pass" type="password"></form>
</body></html>`;

export const HEADED_ROW_HTML = `<html><body>
<table>
  <tr><td>relatório mensal</td></tr>
  <tr><th>Pedido</th><th>Cliente</th><th>Valor</th></tr>
  <tr><td>3001</td><td>Beatriz Alves</td><td>R$ 99,00</td></tr>
</table>
</body></html>`;

/** Tabela marcada com id — alvo do seletor `table` configurável. A tabela
 * de histórico não tem cabeçalho reconhecível (score 0), então sem seletor
 * ela não é detectada; com o seletor, só a #pedidos é considerada. */
export const SELECTOR_TABLE_HTML = `<!DOCTYPE html>
<html><body>
<table class="histórico"><tr><th>Protocolo</th><th>Referência</th><th>Observação</th></tr>
<tr><td>900</td><td>Histórico Antigo</td><td>R$ 1,00</td></tr></table>
<table id="pedidos"><tr><th>Pedido</th><th>Cliente</th><th>Valor</th></tr>
<tr><td>4001</td><td>Davi Rocha</td><td>R$ 55,00</td></tr></table>
</body></html>`;

/** Layout em divs (sem <table>) — caso dos seletores row/cell. */
export const DIV_LAYOUT_HTML = `<!DOCTYPE html>
<html><body>
<div class="orders">
  <div class="order-row head"><span class="c">Pedido</span><span class="c">Cliente</span><span class="c">Valor</span></div>
  <div class="order-row"><span class="c">5001</span><span class="c">Elisa Nunes</span><span class="c">R$ 42,00</span></div>
  <div class="order-row"><span class="c">5002</span><span class="c">Fábio Pires</span><span class="c">R$ 77,00</span></div>
</div>
</body></html>`;
