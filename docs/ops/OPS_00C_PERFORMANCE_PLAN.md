# OPS-00C — Plano de desempenho e redução de gargalos de disco

**Coleta:** 27/10/2026
**Escopo:** diagnóstico observacional e plano futuro. Nenhuma otimização persistente foi aplicada.

## 1. Resumo executivo

- **Principal gargalo medido nesta sessão:** CPU em processos da janela VS Code. Em duas janelas de 6 segundos, contadores por processo reportaram 64%/38% no renderer (PID 1472) e 86%/54% no processo GPU (PID 3368). O contador global de CPU oscilou de 59% a 23%. Essas amostras são breves e variáveis; não comprovam que o VS Code explica toda a lentidão percebida.
- **Disco:** o Toshiba MQ04ABF100 é HDD. Houve uma amostra anterior, registrada na OPS-00B, com aproximadamente 9,66 MB/s de leitura e fila física/lógica de 4/11. Nesta coleta houve três janelas separadas praticamente ociosas; duas amostras posteriores tiveram 0,8–1,0 MB/s, filas 1/1 e leitura de páginas de memória. Isso demonstra atividade episódica, não um disco ocupado continuamente. Os contadores de I/O por processo do VS Code ficaram em aproximadamente 2,6–2,8 MB/s mesmo quando o contador de leitura física marcou zero; portanto, esses contadores não foram usados como prova de I/O físico no HDD.
- **HDD:** SMART confiável não foi obtido. O estado físico completo é **NÃO VERIFICADO**; `Healthy`/`OK` não é uma certificação de saúde.
- **OneDrive:** CPU e bytes/s observados para `OneDrive.Sync.Service.exe` foram zero nas leituras pontuais. O impacto atual da sincronização não foi demonstrado. A árvore contém, porém, muitas pastas candidatas à sincronização: só `node_modules` tem cerca de 131.691 arquivos e 1,93 GiB estimados entre os worktrees `GasFlow` e `GasFlow-integration`. São tamanhos lógicos obtidos por metadados; status real de sync e impacto em tempo não foram medidos.
- **VS Code:** versão 1.143.1; 122 extensões listadas, 124 diretórios de pacotes (incluem versões antigas). Uma janela, um Extension Host de cerca de 689 MB e um agent-host/Copilot Runtime com cerca de 476 MB combinados foram observados. O perfil atual não atribui CPU/RAM individual a cada extensão.
- **Transferência:** não mover diretamente a pasta principal `GasFlow` nem o diretório comum `.git`: a árvore principal precisa permanecer intacta para não arriscar GasFlow Desktop. Proponho criar uma cópia local de desenvolvimento separada, reconstruindo os worktrees a partir de um bundle Git validado e copiando de forma controlada as alterações, relatórios e configurações aprovadas. A origem ficará intacta como rollback.
- **LAB-01:** atualmente não executável, pois o Docker permanece parado. Após inicialização manual pelo operador, validações de isolamento e autorização explícita, PostgreSQL + Redis podem ser avaliados com restrições; o total configurado dos containers é 768 MiB, mas Docker Desktop/WSL também consomem recursos.

## 2. Git e preservação

- Worktree de integração: branch `release/home-server-candidate`, HEAD `e989f70d029385fd974d3d7e5cb0426cbce670a5`; status contém somente documentos não rastreados em `docs/ops/` (OPS-00B e este plano).
- Worktree principal `GasFlow`: branch `sec-02-whatsapp-gateway`, HEAD `213c1873...`; permanece com o arquivo não rastreado preexistente `docs/OPS_00_HOME_SERVER_READINESS.md`.
- Worktrees de desenvolvimento: `GasFlow-freebuff` em `parallel/freebuff-mobile-p0`, HEAD `92e3d500...`; `GasFlow-opencode` em `parallel/opencode-data`, HEAD `d256ac6...`.
- A branch local `main` está **2 commits à frente** da referência local `origin/main`. Essa informação veio das refs já disponíveis; não houve `fetch` nem acesso remoto. Os commits devem ser preservados mesmo que não estejam publicados.
- As três worktrees secundárias são vinculadas ao repositório comum `GasFlow\.git`. Não executar `Move-Item`, `robocopy` final, `git clean`, `reset`, `gc`, `prune`, clone por cima, nem mover o repositório principal sem um plano aprovado.
- O worktree e a origem permaneceram intactos. Nenhum commit, branch, referência ou configuração Git foi modificado nesta tarefa.

## 3. Amostras de HDD e memória

Contadores de desempenho do Windows são fotografias em instantes diferentes. Latência retornou zero quando a fila e a atividade também estavam zeradas; esse valor não representa uma medição válida de latência sob carga.

| Momento / origem | Leitura / escrita do disco | Fila física / lógica | Latência WMI | Memória / paginação |
|---|---:|---:|---:|---|
| OPS-00B, amostra de 8 s | 9,66 MB/s / 0 | 4 / 11 | Contador ocupado inconsistente; latência formatada 0 | Não medida em paralelo |
| 12:21:17, janela de 8 s | 0 / 0,02 MB/s | 0 / 0 | 0/0 ms (ocioso; não interpretável como latência) | 4.497 MB disponíveis; pages input/output 0/0 |
| 12:21:39, janela de 8 s | 0 / 0 | 0 / 0 | 0/0 ms (ocioso) | 4.549 MB disponíveis; pages input/output 0/0 |
| 12:22:07, janela de 8 s | 0 / 0,15 MB/s | 0 / 0 | 0/0 ms (ocioso) | 4.429 MB disponíveis; pages input/output 0/0 |
| 12:24:03 | 0,815 / 0,446 MB/s | 1 / 1 | WMI 0/0 ms | 4.340 MB disponíveis; page reads/input 321/s; page writes/output 0 |
| 12:24:14 | 1,018 / 0 MB/s | 1 / 1 | WMI 0/0 ms | 4.340 MB disponíveis; page reads/input 196/s; page writes/output 0 |
| 12:27:21 | 0 / 0 | 0 / 0 | 0/0 ms (ocioso) | 4.241 MB disponíveis; page reads/input/output 0/0; pagefile atual 103 MB |
| 12:27:30 | 0 / 0 | 0 / 0 | 0/0 ms (ocioso) | 4.259 MB disponíveis; page reads/input/output 0/0; pagefile atual 103 MB |

`PagesInputPersec`/`PageReadsPersec` não significam necessariamente leitura do arquivo de paginação; incluem leituras de páginas mapeadas. Não houve `PagesOutputPersec`/`PageWritesPersec` nem crescimento do pagefile nas amostras finais. Portanto, a amostra não prova pressão persistente de paginação.

O inventário recursivo por metadados de quatro árvores levou aproximadamente 9 segundos. A varredura posterior de metadados de pacotes de extensões levou mais de 120 segundos para concluir; esse trabalho de auditoria produz seu próprio churn de leitura e não serve como baseline do uso normal. Leituras obtidas enquanto a enumeração estava ativa devem ser tratadas como potencialmente contaminadas por essa medição.

### Estado verificável do HDD

- Modelo: Toshiba MQ04ABF100; tipo reportado HDD; barramento SATA por `Get-PhysicalDisk`, interface IDE por `Win32_DiskDrive`.
- Estado genérico: `Healthy`/`OK`; sem eventos de aviso/erro encontrados nas consultas recentes do log System feitas na OPS-00B/OPS-00C.
- `Get-StorageReliabilityCounter` e a consulta de predição SMART não forneceram dados; ferramenta `smartctl` não está instalada. Temperatura e `fsutil dirty query C:` também não foram verificáveis com a permissão atual.
- **Conclusão:** sem confirmação de falha, mas saúde mecânica/SMART **NÃO VERIFICADA**. Não foi executado benchmark, teste SMART ativo, chkdsk, desfragmentação ou reparo.

## 4. VS Code, extensões e agentes

### Processos observados por `code --status`

Uma janela VS Code (`[1]`) foi reportada. Snapshot do process explorer interno:

| Processo/serviço | RAM aprox. | CPU no snapshot | Evidência / interpretação |
|---|---:|---:|---|
| Window/renderer (PID 1472) | 613 MB | 9% | Atividade alta também nas amostras de 6 s; maior evidência de consumo de CPU na janela |
| GPU process (PID 3368) | 160 MB | 7% | CPU elevada nas amostras subsequentes; verificar efeito gráfico se lentidão ocorrer ao rolar/renderizar |
| Extension Host (PID 11976) | 689 MB | 2% | Maior processo VS Code no snapshot; consumo agregado, não atribuído a uma extensão |
| Agent-host (PID 16244) | 191 MB | 0% | Hospeda subprocessos de ferramentas/agentes |
| Copilot Runtime (PID 12968) | 285 MB | 0% | Processo de runtime iniciado pelo agent-host; sem CPU relevante naquele snapshot |
| JSON language server | 99 MB | 0% | Processo filho do Extension Host |
| MongoDB extension language server | 97 MB | 0% | Confirmado pelo caminho do executável; consumo moderado naquele momento |
| PostgreSQL extension server | 96 MB | 0% | Processo filho do Extension Host |
| SQLTools language server | 96 MB | 0% | Processo filho do Extension Host |
| ESLint server | 99 MB | 0% | Processo filho do Extension Host |
| File watchers | 93–101 MB cada no snapshot | 0% | Watcher do VS Code e watcher do agent-host; não foram comprovados órfãos |

O total do Extension Host e servidores filhos pode ser material para a RAM, mas os valores são snapshots por processo e podem mudar rapidamente. O processo de `Code --status` lista servidores Node hospedados pelo próprio `Code.exe`; não apareceu `node.exe` independente no inventário. Um `python.exe` transitório apareceu em consulta anterior com pai não identificado e desapareceu antes da inspeção posterior; isso não comprova órfão. Não foi encontrado `Pylance`/`pyright` executando nesta amostra, apesar de a extensão estar instalada.

Um PowerShell filho do Extension Host estava fazendo `Get-Content -Tail 200 -Wait` em um log do Ollama, com cerca de 56 MB e CPU/I/O nulos no snapshot. Ele pode ser um terminal/monitor aberto deliberadamente; não foi encerrado nem classificado como órfão. Um processo `azmcp.exe` e servidores GitLens também aparecem no conjunto de processos; nenhum foi alterado.

O contador `code --status` mostrou I/O por processo de cerca de 2,6–2,8 MB/s em alguns processos `Code.exe` enquanto o contador do disco físico registrava 0. Essa divergência pode refletir I/O lógico/cache ou diferença de janela de amostragem. **Não atribuir esses bytes diretamente a leitura física do HDD.**

### Extensões

- `code --list-extensions --show-versions`: 122 extensões listadas; 124 diretórios de pacote existentes, incluindo mais de uma versão de algumas extensões.
- Os maiores pacotes por tamanho em disco foram: MSSQL 370,5 MiB; Oracle Java 301,1 MiB; PowerShell 300,9 MiB; Claude Code versões 2.1.310 e 2.1.311 (295–297 MiB cada); Windows AI Studio 272,6 MiB; C/C++ 269,2 MiB; Gemini Code Assist 238,6 MiB; Java 177,8 MiB; Roo/Cline 143,3 MiB; Pylance 141,7 MiB; extensão n8n 131,1 MiB.
- Tamanho do pacote instalado **não é** consumo de CPU/RAM em execução. A telemetria disponível não fornece ranking confiável de consumo individual por extensão. Não desativei, removi ou atualizei extensões.

### Recomendações específicas

1. Reproduzir a lentidão com `code --status` aberto e comparar o mesmo processo em 2–3 janelas curtas; se renderer/GPU continuam altos enquanto o disco está ocioso, priorizar a carga da janela/abas e não culpar OneDrive.
2. Quando o VS Code estiver ocioso e com aprovação do usuário, usar **Developer: Show Running Extensions** para conferir quais extensões estão realmente ativas e seus tempos de ativação. Se for preciso perfil, iniciar **Developer: Start Extension Host Profile** apenas numa sessão dedicada e salvar a evidência; não assumir que pacote grande seja extensão lenta.
3. Rever, por workspace/perfil, a necessidade de vários clientes de banco e servidores SQL/MongoDB se não estiverem sendo usados. Não desativar extensão globalmente sem aprovação e sem verificar a necessidade do GasFlow.
4. Manter apenas um workspace GasFlow aberto durante builds/indexação; não abrir simultaneamente os quatro worktrees sem necessidade. Ainda assim, o snapshot revelou só uma janela, portanto concorrência de worktrees não foi demonstrada como causa atual.
5. Se o problema for renderização, comparar com aceleração gráfica em investigação controlada, sem mudar a configuração nesta fase. O GPU process apresentou CPU relevante, mas a relação causal não foi testada.

## 5. OneDrive e tamanho dos worktrees

Inventário por `stat`/metadados, sem ler conteúdo de arquivos SQLite, sessões ou logs pessoais. Os tamanhos são lógicos e podem incluir arquivos gerados. Categorias podem estar aninhadas e **não devem ser somadas** entre si.

| Árvore no diretório sincronizado | `.git`/artefato Git | `node_modules` | `dist` | `build` | Cache Python (`__pycache__`) | Dados e candidatos SQLite |
|---|---:|---:|---:|---:|---:|---|
| `GasFlow` | 6.915 arquivos; 736,39 MiB no diretório comum `.git` | 80.841; 1.377,14 MiB | 16.930; 644,30 MiB | 15.308; 525,40 MiB | 6.784; 109,81 MiB | `data`: 1.269 arquivos/22,13 MiB; candidatos SQLite: 26/32,67 MiB |
| `GasFlow-freebuff` | `.git` é ponteiro de worktree, não outro object store | Não encontrado | 47; 0,31 MiB | 2; 0,05 MiB | 305; 3,80 MiB | `data`: 73/16,56 MiB; SQLite: 1/2,09 MiB |
| `GasFlow-integration` | `.git` é ponteiro de worktree | 50.850; 599,54 MiB | 14.338; 182,00 MiB | 2.676; 11,33 MiB | 508; 9,62 MiB | `data`: 976/19,55 MiB; SQLite: 2/2,20 MiB |
| `GasFlow-opencode` | `.git` é ponteiro de worktree | Não encontrado | 47; 0,31 MiB | 2; 0,05 MiB | 491; 9,17 MiB | `data`: 93/16,83 MiB; SQLite: 1/2,09 MiB |

Outros dados agregados: `.ruff_cache` soma aproximadamente 0,14 MiB; `.pytest_cache`, 0,45 MiB; diretórios `coverage`, aproximadamente 35,21 MiB; `logs`/`log`, aproximadamente 0,73 MiB (arquivos com extensão de log: cerca de 0,96 MiB). Parte desses valores pode estar dentro de outra categoria.

Foram encontrados 30 candidatos de arquivos `.db`/`.sqlite`/`.sqlite3`, com cerca de 39 MiB lógicos em conjunto. **Nenhum nome, registro ou conteúdo foi lido.** Tratar todos como dados potencialmente operacionais até que o responsável os classifique; não copiar ou excluir automaticamente. Os diretórios `data` também podem conter bancos, mídia ou dados de execução.

O serviço `OneDrive.Sync.Service.exe` reportou CPU 0 e 0 bytes/s de leitura/escrita nas leituras pontuais de 12:24 e 12:27. Isso não prova que a sincronização estava pausada, nem que OneDrive não tenha causado I/O antes/depois. Não foi possível relacionar arquivos individuais com eventos de upload/download. Os mais de 131 mil arquivos em `node_modules` e mais de 31 mil em `dist` são **candidatos de alto churn potencial**, mas o número de arquivos realmente sincronizados e o tempo economizável são **NÃO VERIFICADOS**. Só `node_modules` nos dois worktrees mencionados representa aproximadamente 1,93 GiB lógico; o armazenamento pode ser menor por compressão/arquivos sob demanda.

## 6. Plano seguro de transferência para disco local (não executado)

### Arquitetura recomendada

1. Manter a árvore principal `GasFlow` e o `.git` comum original intocados, protegendo a operação do GasFlow Desktop e todas as quatro worktrees atuais como rollback.
2. Confirmar um destino local fora de `%OneDrive%` e sem colisão, por exemplo `C:\GasFlow-Dev`; não criar ou preencher esse destino nesta fase.
3. Em uma futura janela aprovada, criar backup local verificado do repositório comum e manifesto de todos os quatro worktrees: branch/HEAD, `git worktree list --porcelain`, refs locais, `git status --porcelain=v2 --untracked-files=all`, arquivos ignorados de configuração, relatórios não rastreados e hashes dos arquivos que serão copiados.
4. Confirmar commits locais não publicados sem `fetch` automático. Preservar todas as refs locais, inclusive `main` (2 commits à frente da `origin/main` local).
5. Criar e validar um `git bundle --all` do repositório comum para transportar o histórico/ref locais para uma cópia de desenvolvimento independente. Verificar o bundle com `git bundle verify` e comparar a lista de refs/HEADs antes de criar branches/worktrees locais.
6. Recriar na cópia local as quatro associações de branch/worktree registradas no manifesto, sem editar os metadados absolutos em `.git/worktrees` manualmente. Validar `git worktree list --porcelain`, HEAD e branch por diretório.
7. Transferir alterações não commitadas, arquivos não rastreados (incluindo os relatórios `OPS_00B`, este `OPS_00C` e `OPS_00_HOME_SERVER_READINESS.md`) e configurações locais explicitamente aprovadas, como `.env.lab`. Não exibir valores de configuração nos logs.
8. Não copiar `.git` a mão para dentro de um worktree nem copiar bases de sessão/SQLite, bancos operacionais, caches gerados ou dependências sem classificação e aprovação. Primeiro comparar nomes/tamanhos/estado Git apenas; qualquer candidato de banco permanece na origem até decisão do responsável. Confirmar que os demais dados são regeneráveis antes de excluir algo do escopo de cópia.
9. Preferir cópia em duas fases: staging e validação no destino; manter origens intocadas. Verificar hashes dos arquivos elegíveis, estado Git, configuração local e ausência de bancos/sessões no destino; executar apenas validações sem escrita operacional.
10. Usar um meio de backup independente para recuperação de falha física se estiver disponível. Uma cópia no mesmo HDD dá rollback lógico de migração, mas não protege contra falha do disco; SMART continua indisponível.
11. Só após validação e aprovação decidir se as árvores antigas serão removidas/retiradas do escopo OneDrive. Até lá, manter origens, relatórios e configurações no lugar. Plano de rollback: fechar a cópia local sem mexer na origem, voltar a abrir as worktrees originais com o Git já registrado e confirmar branch/status/HEAD.

Esse desenho não move o repositório de que o Desktop depende, mantém uma cópia verificável dos commits e recria as referências das worktrees com ferramentas Git. Requer atenção especial a `.git` compartilhado, configurações por worktree, arquivos ignorados e credenciais locais; nenhuma transferência foi realizada.

## 7. Plano de otimização priorizado

| Ganho potencial | Proposta | Evidência medida | Risco operacional | Reversibilidade | Recurso necessário | Impacto no GasFlow | Aprovação |
|---|---|---|---|---|---|---|---|
| Alto, potencial e não quantificado | Criar cópia local de desenvolvimento fora do OneDrive conforme seção 6; não tocar no `GasFlow` operacional | 50.850 `node_modules`/600 MiB na integração; 80.841/1,35 GiB no `GasFlow`; `.git` comum de 736 MiB; OneDrive não mostrou I/O nas amostras | Alto se refs, relatórios, configs ou bancos forem copiados/removidos incorretamente | Alta se copiar, validar e manter origem intacta | Espaço livre local; tempo; manifesto/hash; backup independente recomendado | Sem impacto previsto se a árvore principal, Desktop e dados operacionais ficarem intactos | **Sim**, para transferência, exclusões e eventual retirada do OneDrive |
| Médio-alto, imediato mas dependente do uso | Reduzir trabalho simultâneo do VS Code: manter uma janela/worktree e abas de projetos necessárias | Uma janela; renderer/GPU com uso alto; CPU global variável; extensão/servidores agregam memória | Pode atrasar tarefas paralelas se fechar janelas/abas | Alta, reabrindo a janela | Organização de sessões | Nenhuma alteração nos arquivos/dados; afeta apenas fluxo do desenvolvedor | **Sim**, antes de fechar ou alterar sessão existente |
| Médio | Avaliar extensões ativas no `Show Running Extensions` e perfilar Extension Host numa sessão dedicada; desabilitar apenas extensões comprovadamente desnecessárias por workspace | 122 extensões listadas; Extension Host 689 MB; servidores de DB/ESLint/JSON; sem atribuição de CPU por extensão | Pode retirar funcionalidade de linguagem, banco, IA ou tooling do GasFlow | Alta; reativar a extensão/perfil | Tempo de diagnóstico; VS Code | Evitar desativar extensões usadas pelo projeto | Perfil é observacional; **aprovação necessária para desativar** |
| Médio | Investigar renderer/GPU e aceleração gráfica somente se travamento visual se reproduzir | GPU process com 7% no `code --status`, até 86% numa amostra de 6 s; não há teste causal | Alteração pode piorar renderização/estabilidade | Alta por configuração local reversível | Reprodução controlada | Sem alteração no código; impacto apenas na IDE | **Sim** antes de alterar configuração |
| Pequeno a médio | Medir OneDrive durante sintoma real antes de pausar ou mudar pastas sincronizadas | CPU e I/O 0 nos snapshots; árvore tem muitos arquivos gerados; status de sync não verificado | Pausar/mudar sync pode atrasar backup de documentos | Alta para pausa curta, mas dependente do conteúdo pendente | Observação do status do cliente e timestamps | Pode atrasar sincronização de relatórios/código | **Sim** para pausar sync ou mudar escopo |
| Pequeno imediato | Não iniciar Docker/WSL enquanto não estiverem em uso; executar LAB-01 somente com preflight/autorização | Docker service parado; WSL distros paradas; 4.14–4.55 GiB livres nos snapshots | Baixo; iniciar stack reduz RAM livre e adiciona I/O ao HDD | Alta: stop dos serviços do laboratório, sem remover volumes | Cerca de 768 MiB de limites de containers, mais overhead não medido do Desktop/WSL | Não usar dados operacionais nem iniciar Home Server completo | Inicialização requer aprovação explícita |
| Pequeno | Evitar executar scans recursivos, builds paralelos e diagnósticos repetidos durante o atendimento | Enumeração de extensões de metadados levou >120 s; disk samples variaram | Pode atrasar diagnóstico/testes | Alta | Planejar tarefas fora do horário de atendimento | Preserva responsividade do Desktop | Sim para tarefas que consomem I/O em horário de operação |
| Sem benefício comprovado | Desabilitar SysMain, Windows Search, Defender, Firewall, Update, OneDrive ou extensões em massa | Nenhuma relação causal demonstrada; proteções estão ativas | Alto/segurança e perda de função | Variável | Não recomendado | Risco para empresa e desenvolvimento | **Não recomendar** nesta evidência |

## 8. Memória e prontidão LAB-01

- RAM total observada: 11,82 GiB. Memória disponível durante a sessão: aproximadamente 4,14–4,55 GiB.
- Pagefile: uso atual observado 103 MB e pico reportado desde boot 807 MB. As amostras finais de `PagesInputPersec`/`PagesOutputPersec` estavam em zero; em outra janela houve 196–321 page reads/input por segundo, sem escrita/saída.
- O orçamento de PostgreSQL + Redis já configurado para o laboratório é 768 MiB, mas o Docker Desktop, WSL2, backend de armazenamento e tarefas simultâneas consomem memória além do teto dos containers. Não é seguro afirmar que todos esses 4,14 GiB estejam “livres para Docker”; são memória disponível do Windows antes de iniciar o daemon.
- **Parecer:** computador **não está pronto agora** para LAB-01, porque Docker/WSL estão parados e o daemon não foi validado. Após partida manual pelo operador, conflito/isolamento e caminhos de ambiente devem ser revalidados, então LAB-01 com apenas PostgreSQL/Redis pode ser **APTO COM RESTRIÇÕES**, desde que o usuário autorize explicitamente. Não iniciar migrations, backend, frontend, WhatsApp ou observabilidade.

## 9. Estado final e ações

- Nenhum arquivo operacional, banco, sessão, cache, dependência ou extensão foi excluído.
- Nenhum processo foi encerrado; nenhuma extensão, serviço, agendamento, configuração de OneDrive/Windows/WSL/Docker foi alterada. O autostart OpenClaw não foi consultado nem modificado nesta tarefa.
- Não houve inicialização de Docker, reboot, push, merge, deploy, commit ou alteração em outros worktrees.
- O único arquivo novo nesta tarefa é este plano não commitado em `docs/ops/`.
- Próximo passo recomendado: se o usuário aprovar, fazer uma captura dedicada de `code --status` quando a lentidão estiver acontecendo, sem enumerar diretórios; depois decidir se e quando preparar a cópia local de desenvolvimento.
