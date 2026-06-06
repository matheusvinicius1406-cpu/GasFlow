# Banco de Dados

## clientes

id
codigo
nome
telefone
telefone_secundario
rua
numero
complemento
referencia
bairro
ativo
created_at
updated_at

---

## pedidos

id
cliente_id
status
valor_total
forma_pagamento
created_at
updated_at

---

## produtos

id
nome
preco
ativo

---

## entregadores

id
nome
telefone
ativo

---

## empresas

id
nome
telefone
responsavel
