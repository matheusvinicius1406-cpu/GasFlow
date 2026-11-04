# Acesso à LAN, nome local e certificado

Objetivo: abrir `https://192.168.0.211` (ou `https://gasflow.home`) no celular
e no PC da casa **sem aviso de certificado** e **sem expor nada na internet**.

## 1. IP do servidor

O Caddy publica apenas no IPv4 privado definido em `GASFLOW_LAN_IP`
(`deploy/home-server/.env.lab`). Hoje: **192.168.0.211**.

```powershell
# confirmar o bind (não deve existir 0.0.0.0:443)
docker port gasflow-hs-lab-caddy
```

Se o roteador trocar o IP do servidor por DHCP, o certificado e o bind
continuam válidos para o IP **antigo** até você atualizar `GASFLOW_LAN_IP` e
recriar o container do Caddy. Prefira **reserva de DHCP** (ou IP fixo) para
`192.168.0.211`.

## 2. Nome `gasflow.home`

`gasflow.home` não é um domínio público: é um nome local que precisa ser
resolvido dentro de casa. Duas opções, ambas sem custo:

**A. Entrada estática por aparelho (mais simples, mais confiável)**

- Android: não tem `/etc/hosts` sem root. Use a opção **B** ou acesse pelo IP.
- Windows (servidor e clientes): `C:\Windows\System32\drivers\etc\hosts`
  ```
  192.168.0.211  gasflow.home
  ```

**B. DNS local no roteador**

Crie um *host override* (`gasflow.home` → `192.168.0.211`) no DNS do
roteador. Todos os aparelhos passam a resolver o nome sem configuração.

> Sem DNS/hosts o nome não resolve — o acesso por IP continua funcionando
> normalmente. O verificador reporta isso como **AVISO**, não como falha.

## 3. O certificado

O Caddy usa `local_certs`: emite para `gasflow.home` (SAN DNS) e para
`192.168.0.211` (SAN IP) a partir de uma CA raiz própria.

| Item | Valor |
|---|---|
| CA raiz | `Caddy Local Authority - 2026 ECC Root` |
| Validade | até 2036 |
| Arquivo exportado | `deploy/home-server/certs/gasflow-home-ca.crt` |
| Onde vive no container | `/data/caddy/pki/authorities/local/root.crt` (volume `caddy_data`) |

O arquivo em `deploy/home-server/certs/` é **ignorado pelo Git** — é material
de instalação, não código.

Exportar de novo (se perder o arquivo):

```powershell
docker exec gasflow-hs-lab-caddy cat /data/caddy/pki/authorities/local/root.crt `
  > deploy/home-server/certs/gasflow-home-ca.crt
```

> Perder o volume `caddy_data` significa emitir uma CA nova e **reinstalar o
> certificado em todos os aparelhos**. Não remova esse volume por limpeza.

### Instalar no Android

1. Copie `gasflow-home-ca.crt` para o aparelho (USB, e-mail ou
   `https://192.168.0.211` não serve — o certificado precisa vir por fora).
2. *Configurações → Segurança → Criptografia e credenciais → Instalar um
   certificado → Certificado de CA*.
3. Confirme o aviso de "sua conexão pode ser monitorada" (é esperado para
   qualquer CA instalada manualmente).
4. Abra `https://192.168.0.211` — cadeado válido, sem tela de aviso.

### Instalar no Windows (clientes)

```powershell
Import-Certificate -FilePath deploy/home-server/certs/gasflow-home-ca.crt `
  -CertStoreLocation Cert:\LocalMachine\Root
```

(Requer PowerShell como administrador.)

## 4. Por que existe `default_sni`

Navegador e Android **não enviam SNI em conexão por IP** (RFC 6066 proíbe IP
no SNI). Com dois sites no mesmo Caddy, sem SNI ele não sabe qual
certificado entregar e **aborta o handshake** com
`TLSV1_ALERT_INTERNAL_ERROR`.

O `Caddyfile` resolve com:

```caddyfile
{
    default_sni {$GASFLOW_LAN_IP}
}
```

Resultado: quem abre `https://192.168.0.211` recebe o certificado do IP.
Quem abre `https://gasflow.home` envia SNI e recebe o do nome.

Verificação sem SNI (deve completar o handshake):

```powershell
docker run --rm --network gasflow-hs-lab_internal curlimages/curl:latest `
  -sS -o NUL -w "%{http_code}`n" https://192.168.0.211/ --insecure
```

## 5. Firewall

A porta 443 está publicada, mas o Windows Firewall ainda precisa permitir a
entrada **somente no perfil privado / sub-rede local**:

```powershell
New-NetFirewallRule -DisplayName "GasFlow Home Server 443 (LAN)" `
  -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow `
  -Profile Private -RemoteAddress 192.168.0.0/24
```

Não crie regra para o perfil Público. Não faça *port forwarding* no roteador:
o servidor não deve ser alcançável de fora.

## 6. Ferramentas de verificação

- **Use** `python scripts/home-server/verify_lan_https.py` para validar a
  cadeia: ele respeita a CA (`ssl` + `cafile`).
- **Evite** o `curl` do Git Bash nesta máquina: ele usa o backend
  *schannel* do Windows e **ignora `--cacert`**, produzindo
  `SEC_E_INTERNAL_ERROR` mesmo com o certificado certo. Para inspeção rápida,
  `curl -k` serve; para prova de confiança, use o verificador Python.
