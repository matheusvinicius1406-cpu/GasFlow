# Laboratório USB para o app do entregador (MOBILE USB LAB 01)

Ambiente **descartável e isolado** para testar o app Android num celular físico,
sem tocar em nada operacional (sem banco de produção, sem porta 8000, sem
WhatsApp real, sem internet).

Regras deste laboratório:

| Regra | Como está garantido |
| --- | --- |
| Nunca usa o banco operacional | `DATABASE_URL` aponta para `gasflow_lab.db` (SQLite) em `%LOCALAPPDATA%\Temp\opencode\gasflow-lab` |
| Nunca usa a porta 8000 | porta **8010**, publicada somente em `127.0.0.1` |
| Sem envio de WhatsApp | `WHATSAPP_SERVICE_URL=http://127.0.0.1:39999` (porta sem serviço) + `WHATSAPP_SERVICE_KEY=""` |
| Sem IA/ViaCEP/Redis | `AI_PROVIDER=mock`, `VIACEP_ENABLED=false`, `RATE_LIMIT_MODE=memory` |
| Segredos fora do repositório | gerados em `secrets.env` no diretório do lab (nunca commitados) |

## Arquivos

| Arquivo | Função |
| --- | --- |
| `start_lab_backend.ps1` | Sobe o backend de lab (idempotente; aborta se a porta estiver ocupada por outro processo) |
| `stop_lab_backend.ps1` | Encerra **somente** o uvicorn do lab (valida a linha de comando antes de matar; nunca mexe em outro serviço) |
| `seed_lab_data.py` | Cria tenant, admin, entregador, produtos, estoque, clientes e entregas fictícias (idempotente) |
| `verify_lab_api.py` | Smoke test / evidência de comunicação API (11 checagens, saída sem segredos) |

## Uso

```powershell
# 1. subir o backend de laboratório (gera secrets.env na 1ª execução)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\mobile-lab\start_lab_backend.ps1 -Port 8010

# 2. túnel USB: o celular acessa http://127.0.0.1:8010 como se fosse o host
adb reverse tcp:8010 tcp:8010
adb reverse --list          # deve listar: UsbFfs tcp:8010 tcp:8010

# 3. dados fictícios (tenant GasFlow Laboratorio + LAB-001..005)
python scripts\mobile-lab\seed_lab_data.py --api http://127.0.0.1:8010

# 4. evidência de comunicação
python scripts\mobile-lab\verify_lab_api.py --api http://127.0.0.1:8010

# 5. encerrar (só o lab)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\mobile-lab\stop_lab_backend.ps1 -Port 8010
```

## Credenciais do laboratório

Nunca ficam no repositório. A primeira execução de `start_lab_backend.ps1`
gera `%LOCALAPPDATA%\Temp\opencode\gasflow-lab\secrets.env` (senha aleatória
por execução, política 8+ / maiúscula / minúscula / dígito). O
`seed_lab_data.py` grava a credencial de uso do motorista em
`...\gasflow-lab\driver-credentials.txt`.

> `secrets.env` e `driver-credentials.txt` ficam **fora** da árvore do Git.
> Não copie conteúdo deles para logs, commits, prints ou tickets.

Usuários do lab:

- `admin` — administrador de plataforma (cria o tenant de lab)
- `admin_lab` — administrador do tenant `gasflow_lab`
- `motorista-lab-001` — entregador fictício (`MOTORISTA-LAB-001`, tenant `gasflow_lab`)

## Dados fictícios

- Tenant: `gasflow_lab` / "GasFlow Laboratorio"
- Produtos: `Gas P13` e `Agua 20 L` (estoque via API real `/inventory/{codigo}/entries`)
- Clientes: `Cliente Teste Lab 1..5`, telefones sintéticos (`919000000xx`)
- Endereços: rotulados como teste, **não representam entrega real**
- Coordenadas: lote sintético (`-1.4558, -48.5039` e vizinhos), gravadas
  direto no SQLite de lab porque a API HTTP não expõe `lat/lng`

## Desligar tudo sem afetar serviços operacionais

1. `stop_lab_backend.ps1 -Port 8010` → mata só o uvicorn do lab e remove o
   `adb reverse tcp:8010`.
2. Para apagar o laboratório inteiro, delete a pasta
   `%LOCALAPPDATA%\Temp\opencode\gasflow-lab` (banco, logs, segredos, PID).
3. Nenhum container, volume, banco Postgres ou serviço operacional é tocado
   por estes scripts — eles só leem o código de `backend/` e gravam no
   diretório temporário do lab.
