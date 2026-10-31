# OPS-00E — Otimizacao reversivel do VS Code

**Atualizado:** 27/10/2026, 13:00 (-03:00)
**Branch/HEAD:** `release/home-server-candidate` / `e989f70d029385fd974d3d7e5cb0426cbce670a5`
**Resultado atual:** configuracoes de watcher e busca mescladas no perfil atual; sem criacao de perfil novo.

## Atualizacao OPS-00E — aplicacao no perfil atual

Esta atualizacao substitui as recomendacoes anteriores de criar um perfil separado. A pedido do usuario, foi mantido o perfil atual do VS Code; nenhum perfil adicional foi criado.

### Backup e integridade

- Arquivo antes/depois: `%APPDATA%\Code\User\settings.json`.
- Backup criado antes da alteracao, sem sobrescrever outro arquivo:
  `C:\Users\mathe\AppData\Roaming\Code\User\settings.json.backup-OPS-00E-20261027-125856`
- SHA-256 antes da alteracao e do backup: `3753332D04274E8BED5F913F116A4A39DB5B86B7828D43A43ECCB2FAEAF2058A`.
- SHA-256 apos a alteracao: `16E727D55381514255D4530560CA96D23B1D6ABA16DA8B8CD55B249F8168007A`.
- O backup foi comparado por hash com o arquivo original antes de editar. O JSON foi parseado apos a escrita e todos os valores fora dos dois objetos de exclusao foram comparados com o original; nenhum valor preexistente foi alterado.

### Configuracoes alteradas

Antes da mesclagem, `files.watcherExclude` e `search.exclude` nao existiam no settings global. Foram adicionadas somente estas entradas, com valor `true`, em ambos os objetos:

```json
{
    "**/node_modules/**": true,
    "**/.venv/**": true,
    "**/__pycache__/**": true,
    "**/.pytest_cache/**": true,
    "**/.mypy_cache/**": true,
    "**/.ruff_cache/**": true,
    "**/dist/**": true,
    "**/build/**": true,
    "**/coverage/**": true
}
```

Nenhuma entrada existente foi substituida. `files.exclude` nao foi criado nem alterado. As exclusoes afetam o perfil atual em todos os workspaces que usam este settings global: watcher deixa de observar esses paths e a busca integrada os omite; isso nao altera Git, OneDrive, codigo-fonte ou analise estatica em geral.

### Disponibilidade e verificacoes funcionais

| Componente | Evidencia observada apos a alteracao |
|---|---|
| Git | `git status` no worktree GasFlow-integration respondeu; Git `2.54.0.windows.1` |
| GitHub | `gh auth status` retornou conta conectada e ativa, sem expor credencial no relatorio; extensao `github.vscode-pull-request-github@0.172.0` instalada. Nenhuma autenticacao, conta ou token foi alterado. A sessao de conta no painel visual do VS Code nao foi inspecionada diretamente |
| Copilot | Runtime `copilot-runtime.exe` e `agent-host` presentes no `code --status`. A CLI nao lista Copilot como extensao externa nesta instalacao; nenhum prompt foi enviado e nao foi feito teste de geracao |
| OpenCode | `opencode --version` retornou `1.19.3`; nenhum agente/sessao foi iniciado |
| Python | Python `3.14.6`; extensoes Python/Pylance/debugpy/envs estao instaladas |
| TypeScript | Suporte embutido presente em `...\resources\app\extensions\typescript-language-features\package.json`; nao foi executado build/tsc |
| ESLint | Extensao `dbaeumer.vscode-eslint@3.0.34` instalada e `eslintServer.js` ativo no Extension Host |

O `code --status` apos a alteracao continuou mostrando a janela e Extension Host existentes, runtime Copilot e servidor ESLint. Nenhuma janela foi encerrada. A disponibilidade de GitHub CLI e a presenca do runtime Copilot foram verificadas; nao houve teste interativo de login/geracao no VS Code.

### Baseline e amostra posterior

Medicoes curtas de aproximadamente 10,6 s; quatro processadores logicos. O CPU agregado de `Code.exe` e a soma de delta do tempo de CPU dividida pelo intervalo e pelos processadores logicos. RAM e disco sao leituras de contadores no fim da janela.

| Metrica | Antes (12:46:09–12:46:20) | Depois (13:00:30–13:00:41) | Variacao observada |
|---|---:|---:|---:|
| Processos `Code.exe` | 17 | 17 | 0 |
| Working set agregado | 2.726 MiB | 2.758 MiB | +32 MiB |
| CPU agregado | 57,41% | 28,82% | -28,59 pontos percentuais |
| Memoria disponivel | 4.515 MiB | 4.547 MiB | +32 MiB |
| Leitura fisica | 0 B/s | 0 B/s | Igual |
| Escrita fisica | 31.380 B/s | 0 B/s | Menor no snapshot |
| Fila de disco | 0 | 0 | Igual |
| Page reads / pages input | 0 / 0 por segundo | 0 / 0 por segundo | Igual |

As coletas foram feitas em horarios distintos, sem workload controlado e com outros processos/transitorios do VS Code variando. O CPU caiu nessa amostra, mas o working set aumentou e a atividade de escrita do disco tambem variou. **Nao e possivel atribuir a diferenca as exclusoes nem afirmar ganho de desempenho**; sao snapshots nao perfeitamente comparaveis. Tempo de abertura e busca/watcher nao foram cronometrados antes/depois.

### Reversao exata

Para restaurar integralmente o arquivo anterior usando o backup criado nesta execucao, executar em PowerShell:

```powershell
Copy-Item -LiteralPath 'C:\Users\mathe\AppData\Roaming\Code\User\settings.json.backup-OPS-00E-20261027-125856' -Destination 'C:\Users\mathe\AppData\Roaming\Code\User\settings.json' -Force
Get-FileHash -LiteralPath 'C:\Users\mathe\AppData\Roaming\Code\User\settings.json' -Algorithm SHA256
```

O hash esperado apos a reversao e `3753332D04274E8BED5F913F116A4A39DB5B86B7828D43A43ECCB2FAEAF2058A`. Essa restauracao repoe todo o arquivo de configuracoes anterior ao OPS-00E, nao apenas as duas chaves. Alternativamente, remover somente os nove padroes adicionados de cada objeto `files.watcherExclude` e `search.exclude`, preservando quaisquer entradas futuras, e salvar JSON valido.

### Conclusao atual

Manter as exclusoes por ora: sao adicoes seletivas e reversiveis, o backup foi verificado, e nao foram observadas regressoes no status/processos do VS Code nem alteracoes de autenticacao. Nao ha evidencia de ganho de desempenho mensuravel; se algum watcher ou busca necessaria deixar de funcionar, reverter apenas o padrao afetado ou usar o backup.

## Registro anterior do bloqueio de perfil separado

O texto abaixo registra a investigacao inicial das 12:43–12:46. Suas afirmacoes de que nenhuma configuracao foi aplicada e as recomendacoes de criar perfil separado eram verdadeiras naquele momento, mas foram superadas pela atualizacao acima.

## 1. Perfil criado ou impedimento

**O perfil `GasFlow-Leve` nao foi criado.** A verificacao inicial encontrou somente a pasta de perfil interno `builtin` em `%APPDATA%\Code\User\profiles`; nao havia perfil visivel com nome `GasFlow-Leve`.

A CLI instalada e VS Code 1.143.1. O texto de `code --help` diz que `--profile <profileName>` abre a pasta/workspace com esse perfil e que, se nao existir, cria um **novo perfil vazio**. A CLI nao oferece opcao para copiar o perfil existente. Um perfil vazio nao garante as configuracoes e a ativacao de extensoes necessarias, entao nao seria uma criacao segura para esta solicitacao.

Nao foi usado `code --profile GasFlow-Leve`, nao foi associada a pasta a um perfil novo, e nenhum banco interno ou arquivo de perfil foi editado manualmente. A UI do VS Code nao esta exposta a esta sessao para selecionar com seguranca **Create Profile > Copy from existing profile**. Segui o fallback expresso pelo usuario: registrar o bloqueio e fornecer os passos manuais em vez de criar um perfil inadequado.

## 2. Configuracoes aplicadas

**Nenhuma.** As entradas propostas de `files.watcherExclude` e `search.exclude` nao foram aplicadas porque nao existe um perfil novo confirmado em que aplica-las com seguranca.

O arquivo de proposta [settings.json](./proposals/GasFlow-Leve/settings.json) continua sem alteracao. Nenhum `files.exclude` foi adicionado. Nenhum arquivo `.vscode`, `.gitignore` ou de codigo foi modificado.

## 3. Configuracoes preservadas

- Perfil atual permaneceu aberto e inalterado; nao houve troca de perfil.
- O SHA-256 de `%APPDATA%\Code\User\settings.json` foi registrado antes da tentativa de qualquer alteracao:
  `3753332D04274E8BED5F913F116A4A39DB5B86B7828D43A43ECCB2FAEAF2058A`.
- Nenhuma configuracao global foi escrita nem mesclada.
- As propostas foram lidas integralmente e mantidas como documentacao:
  [OPS_00D_VSCODE_OPTIMIZATION.md](./OPS_00D_VSCODE_OPTIMIZATION.md),
  [settings.json](./proposals/GasFlow-Leve/settings.json),
  [extensions.json](./proposals/GasFlow-Leve/extensions.json),
  [extensions-disable-candidates.json](./proposals/GasFlow-Leve/extensions-disable-candidates.json).
- OPS-00B e OPS-00C permanecem preservados em `docs/ops/`; nenhum outro worktree foi alterado.

## 4. Extensoes preservadas e disponibilidade

As seguintes extensoes estao instaladas globalmente e disponiveis para associar a um perfil pela UI. Seus IDs/versoes foram obtidos com `code --list-extensions --show-versions`:

| Extensao | Versao |
|---|---:|
| `ms-python.python` | 2026.10.0 |
| `ms-python.vscode-pylance` | 2026.4.1 |
| `ms-python.debugpy` | 2026.6.0 |
| `ms-python.vscode-python-envs` | 1.40.0 |
| `dbaeumer.vscode-eslint` | 3.0.34 |
| `redhat.vscode-yaml` | 2.0.0 |
| `ms-azuretools.vscode-containers` | 2.5.3 |
| `ms-vscode-remote.remote-containers` | 0.469.0 |

O OpenCode CLI resolve para `%APPDATA%\npm\opencode.ps1`. Git 2.54.0.windows.1 esta presente. TypeScript/JavaScript e Git tambem possuem funcionalidades integradas ao VS Code.

**Limite:** como o perfil leve nao foi criado, nao e possivel confirmar que essas extensoes estejam habilitadas *nesse perfil*. Nenhuma extensao das 35 candidatas foi desativada, instalada ou removida; nao foi desligado Pylance, ESLint, TypeScript, OpenCode, nem outra ferramenta de IA.

## 5. Testes funcionais

| Funcionalidade | Resultado nesta etapa |
|---|---|
| CLI VS Code / extensoes instaladas | Verificadas por CLI |
| Git no worktree atual | CLI respondeu; branch e status conferidos |
| OpenCode | Executavel resolvido por `Get-Command`; nao foi invocado para evitar iniciar um agente/sessao |
| Terminal integrado | Nao testado em novo perfil, pois o perfil nao foi aberto |
| Python/Pylance/analisador FastAPI | Nao testados em novo perfil |
| TypeScript/React e ESLint | Nao testados em novo perfil |
| Docker/YAML | IDs presentes globalmente; nao ativados/testados em novo perfil; Docker nao foi iniciado |
| Busca/watcher apos exclusoes | Nao testados: exclusoes nao aplicadas |
| GasFlow Desktop / WhatsApp | Nenhuma interacao ou alteracao |

Estes resultados nao afirmam que o novo perfil funciona; ele nao existe ainda.

## 6. Metricas comparaveis

### Baseline do perfil original

Coleta de 27/10/2026, 12:46:09–12:46:20, janela curta de aproximadamente 10,6 s. Amostragem via contadores Windows e soma dos processos `Code.exe`; CPU percentual normalizada pelos quatro processadores logicos.

| Metrica | Baseline original | Observacao |
|---|---:|---|
| Processos `Code.exe` | 17 | Contagem durante a amostra |
| Working set agregado de Code | 2.726 MiB | Soma aproximada dos processos Code |
| CPU agregada de Code | 57,41% | Janela curta; sensivel a atividade transitoria, nao e media de sessao |
| Memoria disponivel | 4.515 MiB | Snapshot no fim da amostra |
| Page reads / pages input | 0 / 0 por segundo | Nenhuma pagina lida observada nesse intervalo |
| Disco fisico leitura/escrita | 0 / 31.380 B/s | Snapshot ao final |
| Fila de disco | 0 | Snapshot ao final |
| Latencia media formatada leitura/escrita | 0 / 0 s | Contador formatado zerado; nao prova latencia zero sob carga |
| Abertura da pasta | Nao cronometrada | Nao houve par comparavel |

O `code --status` tambem mostrou uma janela/workspace com **mais de 20.000 arquivos**; tipos destacados incluíam 7.082 `.py`, 6.789 `.pyc` e 1.179 `.pyi`. Mostrou Extension Host (~669 MiB naquele snapshot), renderer (~641 MiB) e varios language servers, mas uma unica leitura nao equivale a amostra pareada.

### Comparacao

**Nao ha medicao depois**, porque o perfil nao foi criado. Portanto, nao afirmo reducao de CPU/RAM, atividade de disco ou tempo de abertura. A amostra de CPU do perfil original e pontual e deve ser repetida antes de qualquer comparacao.

## 7. Melhorias observadas

**Nenhuma melhoria de desempenho foi observada ou reivindicada.** Esta etapa confirmou a disponibilidade global de ferramentas essenciais e identificou que a CLI nao consegue copiar o perfil atual. A oportunidade potencial permanece: reduzir eventos do watcher e resultados de busca em dependencias/artefatos gerados apos aplicar as exclusoes em um perfil copiado.

## 8. Limitacoes

- `code --profile` nao cria uma copia; cria um perfil vazio quando o nome nao existe.
- A CLI nao disponibiliza comando para copiar settings/extensoes de um perfil existente.
- Nao houve UI de escritorio acessivel para operar o editor Profiles e confirmar quais caixas de conteudo copiar.
- Nao foi seguro editar bancos internos para simular uma criacao por UI.
- Sem perfil novo, nao ha baseline pareada ou validacao funcional do perfil GasFlow-Leve.
- A amostra curta de CPU e contadores de disco pode variar com a atividade do sistema. Nenhuma carga pesada foi executada.

## 9. Como criar e reverter pela UI oficial

### Criacao segura (proxima acao manual)

1. No VS Code que esta no perfil original, abrir a UI de Profiles pelo menu **Manage (engrenagem) > Profiles** ou executar **Profiles: Create Profile...** na Command Palette.
2. Dar o nome exato **GasFlow-Leve**.
3. Escolher **Copy from** e selecionar o perfil original atual (nao escolher Empty Profile). Copiar configuracoes, extensoes, snippets, atalhos, tarefas e MCP servers necessarios; revisar o preview antes de concluir.
4. Se a opcao de copiar MCP servers/integracoes for apresentada, preservar o que for necessario para OpenCode e ferramentas de desenvolvimento, sem alterar autenticacao global. OpenCode CLI permanece fora do VS Code.
5. Ao terminar, confirmar no Profile indicator que `GasFlow-Leve` esta ativo e que o perfil original ainda aparece na lista.
6. Abrir **Preferences: Open User Settings (JSON)** somente enquanto `GasFlow-Leve` estiver ativo. Mesclar, sem substituir objetos existentes, as entradas de `files.watcherExclude` e `search.exclude` da proposta. Preservar todas as chaves ja presentes. Nao adicionar `files.exclude`.
7. Conferir que as oito extensoes essenciais da secao 4 aparecem instaladas/habilitadas neste perfil. Nao desativar as 35 candidatas nesta primeira etapa.
8. Reabrir a mesma pasta do worktree de desenvolvimento no perfil leve, sem abrir/alterar o worktree operacional. Validar terminal, OpenCode, Python, TypeScript/ESLint e Git manualmente.

### Retornar ao perfil original

- Usar o indicador de perfil no canto inferior esquerdo/Manage Profiles e selecionar o perfil original. Isto nao altera o perfil GasFlow-Leve.
- Para retirar apenas as exclusoes, voltar a `Preferences: Open User Settings (JSON)` com `GasFlow-Leve` ativo e remover somente as chaves `files.watcherExclude` e `search.exclude` adicionadas nesta etapa; manter quaisquer entradas preexistentes.
- Para remover GasFlow-Leve, primeiro selecionar o perfil original; depois, na UI Profiles, excluir somente o perfil chamado GasFlow-Leve e confirmar o nome antes de concluir.
- Confirmar que o perfil original e suas extensoes continuam disponiveis. Nao apagar pastas de extensoes nem editar `state.vscdb`.

### Detectar efeitos colaterais

- Repetir a busca por um arquivo gerado deliberadamente: `search.exclude` deve omiti-lo, enquanto a busca por codigo/testes deve continuar retornando resultados.
- Confirmar que `node_modules`, `.venv`, caches, `dist`, `build`, `coverage` e logs continuam visiveis no Explorer (nenhum `files.exclude` foi aplicado).
- Confirmar diagnosticos Python/TypeScript/ESLint, Git status e funcionamento do terminal. Se ferramenta depender de watcher em artefato excluido, remover o padrao especifico do perfil leve.

## 10. Proxima otimizacao recomendada

Criar manualmente um perfil copiado pela UI oficial e aplicar somente as exclusoes propostas de `files.watcherExclude` e `search.exclude` nesse perfil. Repetir a baseline original e coletar a mesma janela de 10–30 s no perfil novo com a mesma pasta, ferramentas e nivel de atividade. Comparar CPU total de Code, working set, Extension Host, memoria disponivel, leituras/escritas/fila de disco e tempo de abertura; anotar variacao e nao inferir causalidade a partir de uma unica amostra.

Depois de validacao funcional e comparacao, considerar desativar uma candidata por vez *somente no perfil novo*, com aprovacao; nenhuma desativacao esta autorizada nesta etapa.

## Estado final

- Branch e HEAD preservados; OPS-00B, OPS-00C e OPS-00D continuam presentes e nao commitados.
- Os quatro worktrees nao foram alterados.
- `settings.json` global permaneceu sem escrita; hash registrado acima.
- Nenhum perfil foi criado, nenhuma extensao alterada e nenhuma configuracao proposta aplicada.
- Nao foram executados Docker, migrations, comandos de OpenCode, testes/builds pesados, reinicio ou alteracoes em servicos/dados operacionais.
- Sem commit, push ou merge.
