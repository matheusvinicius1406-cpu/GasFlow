# OPS-00D — Otimização reversível do VS Code e ambiente de desenvolvimento

**Coleta:** 27/10/2026
**Branch/HEAD:** `release/home-server-candidate` / `e989f70d029385fd974d3d7e5cb0426cbce670a5`
**Escopo:** diagnóstico observacional e arquivos de configuração propostos para um perfil novo. Nada foi aplicado.

## 1. Diagnóstico

- VS Code 1.143.1 (x64) no Windows 11 build 26200; CPU Intel i3-10110U, 4 processadores lógicos.
- O `code --status` nativo reportou **uma janela** e um Extension Host. Snapshot às 12:35:37: 11,82 GiB de RAM total, 4.484 MiB disponíveis, páginas input/output 0/0, leitura física 0 B/s, escrita 16.341 B/s e fila de disco zero.
- No snapshot interno `code --status`, a janela/renderer estava em 9% CPU e 582 MB; o GPU process, 7% e 175 MB; Extension Host, 0% e 572 MB; agent-host, 1% e 191 MB; Copilot Runtime, 1% e 291 MB; file watcher principal, 0% e 91 MB. São amostras pontuais e não um perfil médio.
- Em janelas curtas anteriores, o renderer e o GPU process chegaram a valores muito maiores (renderer 38–64%, GPU 54–86%). Não houve medição de duração suficiente para diagnosticar um consumo contínuo. A atividade observada em processos Electron do VS Code é um sinal para comparar perfis, não uma atribuição causal a uma extensão.
- A contagem do Windows na coleta foi 17 processos `Code.exe`, nenhum `node.exe` independente e nenhum `python.exe`/`pythonw.exe` no instante do baseline. `code --status` mostrou processos Node hospedados pelo próprio VS Code e 1 runtime Copilot nativo; isso é diferente de processos órfãos. Um Python transitório fora desta amostra não foi comprovado como órfão.
- Não houve evidência de múltiplas janelas VS Code. O snapshot indicou uma janela associada ao workspace `automação zap`; não expôs os caminhos dos demais worktrees. Logo, atividade simultânea dos quatro worktrees **não foi comprovada**.
- O disco físico estava ocioso no baseline curto. Em amostras anteriores OPS-00C, houve atividade episódica e filas pequenas; latência formatada zero não constitui uma medição sob carga. O HDD permanece sem SMART verificável.
- O OneDrive reportou CPU e bytes/s nulos nas amostras pontuais OPS-00C. A presença de arquivos gerados em worktrees sincronizados mantém risco de churn, mas nenhuma contribuição atual do OneDrive ao gargalo foi medida.

## 2. Extensões instaladas versus ativação observada

### Instaladas

- `code --list-extensions --show-versions` retornou 122 IDs de extensão; o diretório de extensões continha 126 diretórios no momento da coleta, incluindo pacotes/versões antigos.
- Instalação não significa ativação. O tamanho em disco de uma extensão não estima seu consumo em execução.
- O OpenCode CLI existe em `C:\Users\mathe\AppData\Roaming\npm\opencode.ps1`. Não foi identificado ID de extensão OpenCode na lista atual; o fluxo OpenCode pode continuar pelo terminal integrado.

### Processos/servidores observados em `code --status`

| Evidência | Interpretação segura |
|---|---|
| Um `extension-host` (PID observado 11976), ~572 MB no snapshot | Host de extensões agregado. O CLI não atribuiu essa RAM/CPU por extensão |
| Servidor JSON, ~99 MB | Servidor de linguagem integrado ao VS Code |
| Processos `languageServer.js`, `languageserver.js`, `eslintServer.js`, cada um ~96–99 MB | Servidores hospedados pelo VS Code. Caminhos identificavam MongoDB, PostgreSQL, SQLTools e ESLint; são evidências de processos ativos dessas ferramentas |
| Servidor GitHub Actions, ~100 MB em leitura anterior de `--status` | Processo associado a `github.vscode-github-actions` |
| GitLens `gk.exe`/MCP e Azure MCP `azmcp.exe` em snapshot de processos | Integrações residentes foram vistas; não se mediu custo sustentado |
| agent-host (~191 MB) + Copilot Runtime (~291 MB) | Processos de agente/runtime observados. Não equivalem a todas as extensões de IA instaladas nem indicam indexação contínua |
| file-watcher do workspace (~91 MB) e watcher do agent-host (~101 MB em snapshot OPS-00C) | Dois observadores de escopos distintos; não comprovadamente duplicados ou órfãos |

### Ativação e limites do diagnóstico nativo

`code --status` fornece process explorer, CPU e memória do snapshot, mas **não forneceu a lista completa “Running Extensions” nem o tempo de ativação individual**. O acesso nesta sessão não oferece uma interface segura para executar o comando de paleta `Developer: Show Running Extensions` no VS Code existente, sem simular interação destrutiva ou alterar a sessão do usuário. Por isso:

- não declaro uma lista completa de extensões ativas;
- os servidores mencionados acima são extensões/processos ativos identificados por caminhos, mas o Extension Host agrega o restante;
- não atribuo o custo do Extension Host individualmente a uma extensão;
- tempo de ativação por extensão fica **NÃO VERIFICADO**;
- não houve prova de processos Node/Python órfãos, servidores duplicados ou indexação simultânea dos worktrees.

Para completar essa atribuição depois, usar no VS Code atual **Developer: Show Running Extensions** e registrar tempos/estado sem alterar nada. Para perfil por CPU, **Developer: Start Extension Host Profile** em sessão de diagnóstico aprovada; não usar o tamanho dos pacotes como substituto.

## 3. Proposta de perfil `GasFlow-Leve`

Criar um perfil VS Code separado a partir de uma **cópia** do perfil atual usando `Profiles: Create Profile` e o nome `GasFlow-Leve`. Não criar um perfil vazio que perca as integrações atualmente úteis; copiar o atual preserva preferências, autenticação e disponibilidade de ferramentas. Aplicar as candidatas abaixo **somente ao perfil novo**, uma por vez, e medir antes/depois.

### Manter disponíveis

- **Python/FastAPI:** `ms-python.python`, `ms-python.vscode-pylance`, `ms-python.debugpy`, `ms-python.vscode-python-envs`.
- **React/TypeScript:** TypeScript/JavaScript integrados ao VS Code; manter ESLint (`dbaeumer.vscode-eslint`).
- **Git:** Git integrado. GitLens pode ser mantido se seus recursos extras/MCP forem usados.
- **Docker/YAML quando necessário:** `ms-azuretools.vscode-containers`, `redhat.vscode-yaml`; `ms-vscode-remote.remote-containers` somente para tarefas Dev Containers.
- **Depuração:** Python Debugger, depuração JS/TS integrada e ferramentas específicas apenas quando o projeto pedir.
- **OpenCode:** CLI já instalado, preservar `opencode` no terminal; não depende de extensão identificada.

O arquivo [extensions.json](./proposals/GasFlow-Leve/extensions.json) registra recomendações para este conjunto essencial. Ele está fora de `.vscode`, portanto não ativa nem instala extensões.

### Candidatas a desativação apenas no perfil novo

O arquivo [extensions-disable-candidates.json](./proposals/GasFlow-Leve/extensions-disable-candidates.json) detalha os IDs e motivos. Principais grupos:

1. **Assistentes alternativos redundantes** se não forem usados nesse perfil: Claude Code, Gemini Code Assist/CLI companion, Roo/Cline, DeepSeek, gateway/OAI-compatible Copilot, Windows AI Studio. Escolher as ferramentas de IA necessárias e manter OpenCode CLI; não desligar os recursos de IA do perfil atual.
2. **Banco de dados redundante:** MSSQL/SQL projects, MongoDB e múltiplos clientes PostgreSQL/SQLTools. Se for necessária conexão interativa, manter no novo perfil apenas um cliente que o usuário escolha. Não desativar nem remover configurações de conexão, bancos ou dados.
3. **Toolchains de outros domínios:** Oracle/Java/Maven/Gradle/Spring, C/C++/CMake, Rust e Kubernetes se não houver tarefas desses ecossistemas no perfil.
4. **Azure MCP/Resource Groups/Azure Copilot** se não forem necessários para a tarefa local. Preservar todas essas ferramentas no perfil atual e reativar no `GasFlow-Leve` quando o trabalho exigir.
5. **GitLens** é opcional; Git integrado e CLI permanecem. Desativá-lo no perfil novo pode remover painéis e a integração MCP GitLens.

Desativar no perfil é reversível e mantém extensões instaladas. A aplicação de cada candidato ainda exige confirmação do usuário e verificação funcional no novo perfil.

## 4. Proposta de exclusões de arquivos gerados

O arquivo [settings.json](./proposals/GasFlow-Leve/settings.json) propõe exclusões apenas no escopo do perfil `GasFlow-Leve`. Não está em `.vscode` nem na pasta de configurações ativa.

| Configuração | Efeito | Proposta |
|---|---|---|
| `files.watcherExclude` | Impede o watcher do VS Code de observar paths correspondentes; não oculta do Explorer, não remove do Git e não é uma regra geral para análise estática | Excluir dependências, virtualenvs, caches, artefatos `dist`/`build`/`coverage` e logs gerados |
| `search.exclude` | Exclui esses paths dos resultados da busca textual integrada; não altera watchers, Git ou ferramentas de análise independentes | Usar os mesmos diretórios/arquivos gerados para reduzir resultados e varredura |
| `files.exclude` | Oculta itens no Explorer; não deixa de rastrear no Git e pode esconder artefatos necessários à investigação | **Nenhuma alteração proposta.** Manter arquivos visíveis, inclusive `dist`, logs e caches quando forem inspecionados deliberadamente |

Os padrões propostos cobrem `node_modules`, `.venv`, `venv`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `dist`, `build`, `coverage`, `logs`, `log`, `*.log` e `*.log.*`.

Não excluir `data`, arquivos SQLite, código-fonte, testes, migrações, `pyproject.toml`, `package.json`, arquivos de configuração, `docs` ou `.github`. Não modificar `.gitignore` ou a descoberta do Git. O VS Code já pode aplicar exclusões padrão para dependências; a configuração explícita proposta deve ser validada no perfil novo para confirmar que não oculta cenários úteis.

## 5. Recursos e configurações de desempenho

Leitura da configuração global `C:\Users\mathe\AppData\Roaming\Code\User\settings.json` e ausência de `.vscode/settings.json` nos quatro worktrees:

| Área | Estado observado | Recomendação |
|---|---|---|
| Auto-save | Não configurado explicitamente | Não habilitar automaticamente; evita churn e escrita inesperada durante atendimento |
| Format on save / code actions on save | Não configurados explicitamente | Manter padrão até validar linguagens e ações; não desligar lint |
| TypeScript server | Sem limites/opções customizados localizados | Manter defaults; não aumentar memória no host de 12 GB |
| Python analysis/indexing | Sem opções customizadas localizadas | Manter análise estática; reduzir somente caminhos gerados via exclusões testadas |
| ESLint | Sem política customizada localizada | Manter lint e comportamento padrão; não desligar verificações |
| File watchers | Sem `files.watcherExclude` workspace/user localizado | Aplicar exclusões seletivas no perfil novo e comparar watcher/I/O |
| Git auto-refresh | Não configurado explicitamente | Manter default, para não tornar o estado Git desatualizado |
| Indexação contínua de IA | Não foi possível confirmar frequência/paths pelos diagnósticos nativos | Não afirmar que ocorre; evitar manter vários assistentes concorrentes no perfil novo |
| GPU do terminal | Configuração global existente `terminal.integrated.gpuAcceleration: "off"` | Não alterar. Afeta o terminal integrado, não prova que aceleração gráfica da janela esteja desativada; fazer A/B somente se o sintoma reproduzir |

Não foram encontrados ajustes excessivos de auto-save, análise Python/TypeScript, ESLint ou Git no escopo consultado. Não recomendar desativação permanente de lint, testes, análise de segurança, serviços Windows, Defender, Firewall ou Update.

## 6. Diff proposto (não aplicado)

Os arquivos de proposta ficam em `docs/ops/proposals/GasFlow-Leve/`, fora das configurações efetivas do VS Code.

```diff
--- perfil atual / settings.json efetivo
+++ GasFlow-Leve/settings.json proposto
@@
+ "files.watcherExclude": {
+   "**/node_modules/**": true,
+   "**/.venv/**": true,
+   "**/venv/**": true,
+   "**/__pycache__/**": true,
+   "**/.pytest_cache/**": true,
+   "**/.mypy_cache/**": true,
+   "**/.ruff_cache/**": true,
+   "**/dist/**": true,
+   "**/build/**": true,
+   "**/coverage/**": true,
+   "**/logs/**": true,
+   "**/log/**": true,
+   "**/*.log": true,
+   "**/*.log.*": true
+ },
+ "search.exclude": {
+   "...": "mesmos padrões de diretórios/arquivos gerados"
+ }
```

Nenhuma chave será adicionada ao `settings.json` global nem a qualquer `.vscode` de worktree. `files.exclude` foi deliberadamente omitido.

## 7. Riscos, compatibilidade e reversão

- **Risco principal do watcher:** uma extensão pode depender de eventos dentro de artefatos excluídos. Validar build/teste de frontend e Python no novo perfil. Fonte e testes ficam observados.
- **Risco de busca:** pesquisas de logs/artefatos deixam de retornar resultados por padrão. O usuário pode mudar a exclusão de busca no perfil temporariamente para investigar.
- **Análise estática:** os padrões não desligam a análise Python/TypeScript/ESLint. Algumas extensões reutilizam exclusões de watcher; observar diagnósticos e importações no perfil.
- **Extensões:** desativar um cliente de banco, Azure, Java ou assistente no perfil novo pode retirar comandos/painéis daquela tarefa. As extensões permanecem instaladas e disponíveis no perfil original.
- **OneDrive:** estas exclusões são comportamentos internos do VS Code; **não impedem nem reduzem a sincronização do OneDrive**. Não mover, apagar, excluir da sincronização ou pausar nesta etapa.
- **Reversão das settings:** remover do `GasFlow-Leve` as chaves `files.watcherExclude` e `search.exclude` ou restaurar o conteúdo anterior do perfil. Não mexer em configurações globais.
- **Reversão das extensões:** no perfil `GasFlow-Leve`, reativar as extensões selecionadas em `Extensions: Enable`/perfil. O perfil atual não deve ser alterado. Se necessário, excluir somente o perfil proposto via UI depois de voltar ao perfil atual; não apagar diretórios de extensão.
- **Reversão completa:** voltar ao perfil atual na UI. Por ser criado como cópia e as extensões não serem removidas, isso restaura a experiência original sem tocar em branches, arquivos ou processos do GasFlow.

## 8. Métricas de referência curta

Baseline capturada em 27/10/2026 às 12:35:37, sem iniciar carga:

| Métrica | Valor de referência | Método/limite |
|---|---:|---|
| Memória total/disponível | 11,82 GiB / 4.484 MiB livres | `code --status` e contador de memória Windows |
| CPU do renderer / GPU | 9% / 7% | Snapshot único `code --status`; outras janelas OPS-00C chegaram a 38–64% / 54–86% |
| CPU do Extension Host | 0% no snapshot | Não representa média |
| Memória renderer / GPU | 582 / 175 MB | Snapshot `code --status` |
| Memória Extension Host | 572 MB | Agregado, não atribuído a extensões |
| Agent-host / Copilot Runtime | 191 / 291 MB | Snapshot; runtime ativo |
| File watcher principal | 91 MB | Snapshot |
| Processos `Code.exe` / `node.exe` / Python | 17 / 0 / 0 | Contagem no instante da coleta |
| Janela / Extension Hosts | 1 / 1 | `code --status` |
| Extensões instaladas / diretórios de pacotes | 122 / 126 | CLI e diretório; não equivale a extensão ativa |
| Disco físico read/write / fila | 0 B/s / 16.341 B/s / 0 | Snapshot; não representa latência sob carga |
| Page input/output | 0 / 0 páginas/s | Snapshot |
| OneDrive | Sem medição nesta leitura de referência | OPS-00C observou CPU/read/write 0 em amostras pontuais, não prova ausência de sync |

## 9. Roteiro de validação antes/depois

1. Escolher um período sem atendimento/uso do GasFlow Desktop; não iniciar containers. Anotar hora, janela e worktree, e evitar scans/builds durante ambas as medições.
2. Antes de criar o perfil, coletar duas leituras de `code --status` separadas por 30 segundos, mais `Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory` e `PerfDisk_PhysicalDisk`. Registrar memória disponível, CPU/RAM do renderer/GPU/Extension Host/agent-host, processos Code/Node/Python, bytes/s e fila.
3. No VS Code, abrir `Developer: Show Running Extensions`; registrar IDs que realmente aparecem ativos e tempos de ativação. Não presumir que todos os instalados foram ativados.
4. Criar pela UI um perfil **cópia** chamado `GasFlow-Leve`, ainda sem desativar nada. Importar/colar as configurações propostas somente no perfil novo. O material desta pasta é apenas proposta e não é carregado automaticamente.
5. Desativar, uma por vez, apenas as candidatas aprovadas no perfil novo. Manter um cliente PostgreSQL se necessário, Python/Pylance/debugpy, ESLint, TypeScript integrado, YAML/Containers e OpenCode CLI acessíveis.
6. Repetir mesmas leituras após 2 minutos de idle e após abrir o mesmo workspace/arquivos. Não rodar build/teste de carga. Comparar mediana/valores dos snapshots, extensão ativa, tempo de ativação, erros de linguagem, Git status e observações do OneDrive.
7. Critérios: fontes/testes ainda pesquisáveis; Python diagnostics/debugger, React/TypeScript, ESLint, Git, YAML/Containers quando solicitados e `opencode` no terminal disponíveis; nenhuma regressão operacional; ganho repetível em uso de memória/CPU ou estabilidade, não só uma leitura isolada.
8. Se houver regressão, reativar a última extensão no novo perfil ou remover suas exclusões e repetir; manter o perfil original intacto.

## 10. OneDrive, Git e impacto operacional

- Não há configuração de VS Code que impeça o cliente OneDrive de sincronizar `node_modules`, `dist`, caches ou worktrees. `watcherExclude` e `search.exclude` reduzem trabalho do VS Code, não sincronização de nuvem.
- A OPS-00C contou milhares de arquivos gerados e >1,9 GiB lógicos de `node_modules` nas árvores `GasFlow` e `GasFlow-integration`, mas a atividade OneDrive observada era zero nos snapshots e a quantidade realmente transferida não foi verificada.
- Migrar worktrees pode reduzir churn futuro, porém deve manter a árvore principal `GasFlow` que sustenta o GasFlow Desktop e o `.git` comum original intocados. Usar cópia local de desenvolvimento separada, backup verificável, manifesto de refs/HEAD/status/untracked/ignored, `git bundle --all` verificado e recriação de worktrees com Git, como detalhado na OPS-00C. Copiar relatórios/configurações não rastreadas de forma explícita; classificar bancos/sessões antes de copiá-los.
- **Nenhuma** movimentação, dessicronização, pausa de OneDrive, limpeza, alteração em banco, sessão WhatsApp ou processo operacional ocorreu nesta tarefa.

## 11. Parecer sobre LAB-01

**Não pronto neste momento.** O Docker service/engine continua parado, e esta tarefa não o iniciou. O perfil proposto não substitui os gates do laboratório: depois da criação do novo perfil e quando o operador decidir, é necessário iniciar o Docker Desktop manualmente, revalidar contexto, daemon, ambiente e ausência de containers/volumes/redes/portas conflitantes, confirmar alvo somente PostgreSQL + Redis e obter autorização expressa antes de `up`. A memória livre vista no baseline é 4.484 MiB antes de overhead de Docker/WSL; não deve ser tratada como capacidade reservada. Se os gates forem aprovados, LAB-01 poderá ser testado **com restrições**; sem daemon verificado, segue bloqueado.

## 12. Estado final

- Branch preservada: `release/home-server-candidate`; HEAD `e989f70d029385fd974d3d7e5cb0426cbce670a5`.
- OPS-00B e OPS-00C permanecem não commitados; os quatro worktrees foram preservados.
- Os arquivos neste diretório de proposta não pertencem a `.vscode` e não modificam o perfil atual:
  - [settings.json](./proposals/GasFlow-Leve/settings.json)
  - [extensions.json](./proposals/GasFlow-Leve/extensions.json)
  - [extensions-disable-candidates.json](./proposals/GasFlow-Leve/extensions-disable-candidates.json)
- Não foram desativadas extensões, alteradas settings globais, movidos worktrees, interrompidos processos, iniciados containers ou reiniciado o Windows. Não houve commit, push ou merge.
