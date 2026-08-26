# API

## Health

GET /health

---

## Clientes

GET /clients

GET /clients/{codigo}

POST /clients

PUT /clients/{codigo}

DELETE /clients/{codigo}

---

## Pedidos

GET /orders

POST /orders

PUT /orders/{id}

---

## Produtos

GET /products

POST /products

---

## Entregadores

GET /delivery-drivers

POST /delivery-drivers

---

## WhatsApp

### Status da Sessão

GET /whatsapp/status

GET /whatsapp/health

### QR Code

GET /whatsapp/qr

### Controle da Sessão

POST /whatsapp/start

POST /whatsapp/logout

### Contatos

GET /whatsapp/contacts?limit=50&offset=0

GET /whatsapp/contacts/{id}

POST /whatsapp/contacts/sync

### Clientes (CRM)

GET /whatsapp/customers?limit=50&offset=0

GET /whatsapp/customers/{id}

POST /whatsapp/customers/{contact_id}/promote

POST /whatsapp/customers/{id}/opt-in

POST /whatsapp/customers/{id}/opt-out

### Listas

GET /whatsapp/lists

POST /whatsapp/lists

POST /whatsapp/lists/seed

GET /whatsapp/lists/{id}/customers

### Campanhas

GET /whatsapp/campaigns

POST /whatsapp/campaigns

GET /whatsapp/campaigns/{id}

POST /whatsapp/campaigns/{id}/preview

POST /whatsapp/campaigns/{id}/start

POST /whatsapp/campaigns/{id}/pause

POST /whatsapp/campaigns/{id}/cancel

GET /whatsapp/campaigns/{id}/results

---

## WhatsApp Service (Node.js)

Acesse diretamente o serviço WhatsApp em http://localhost:3001

GET /api/health

GET /api/whatsapp/status

GET /api/whatsapp/qr

POST /api/whatsapp/start

POST /api/whatsapp/logout

GET /api/contacts

GET /api/customers

GET /api/lists

GET /api/campaigns

Página de conexão QR Code: http://localhost:3001/connect
