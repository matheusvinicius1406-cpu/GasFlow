# OPS-00B — Auditoria de saúde do PC e preparação do Home Server

**Coleta:** 27/10/2026

**Escopo:** diagnóstico de leitura, preparação do computador e desativação autorizada somente do autostart do OpenClaw.
**Resultado geral:** o HDD e a atividade do sistema precisam de acompanhamento; a causa única da lentidão não foi comprovada. O Home Server completo não é recomendado neste hardware para operação contínua. Um LAB-01 limitado pode ser avaliado depois que o Docker estiver disponível e houver autorização explícita.

## A — Resumo executivo

- O computador tem um HDD mecânico Toshiba de 1 TB, CPU i3 de 2 núcleos/4 threads e 12 GB de RAM. Há espaço livre abundante em C:, então capacidade do volume não explica a lentidão observada.
- As amostras variaram: uma leitura de CPU chegou a 99%, outras ficaram em 37–38%. Em amostras de 8–10 segundos, processos filhos do VS Code tiveram atividade elevada de CPU e I/O. Uma amostra de disco ficou ociosa; outra registrou cerca de 9,7 MB/s de leitura e filas de 4 (disco físico) e 11 (volume lógico). Não houve amostragem longa ou rastreamento por arquivo suficiente para atribuir uma causa exclusiva.
- Não houve paginação ativa nas leituras de `PagesInputPersec`/`PagesOutputPersec`; havia aproximadamente 4,4–4,8 GB de memória física disponível. O processo de compressão de memória e vários processos de navegador/VS Code consomem recursos, mas não há evidência de pressão sustentada de RAM.
- O estado reportado do HDD é `Healthy`/`OK` e não foram encontrados eventos de aviso/erro de armazenamento nos últimos 30 dias. SMART, contadores de confiabilidade, temperatura e estado dirty não puderam ser verificados por falta de acesso/disponibilidade. Portanto, **saúde física completa do HDD: NÃO VERIFICADA**.
- Foi desativada exclusivamente a tarefa agendada de logon `OpenClaw Gateway`. O launcher e o comando manual continuam presentes. Nenhum processo foi encerrado.
- Docker Desktop/engine está parado, assim como as distribuições WSL2 observadas. Docker e containers não foram iniciados.
- **Prioridade de hardware, se houver orçamento futuro:** migrar de HDD para SSD SATA compatível tende a ser a melhoria de maior impacto percebido. Isso não é pré-requisito imposto nesta auditoria; orçamento atual informado é R$ 0,00.

## B — Hardware e Windows

| Item | Estado observado |
|---|---|
| Windows | Windows 11 Home Single Language, versão 10.0, build 26200, 64 bits |
| Computador | Samsung 550XCJ/550XCR |
| CPU | Intel Core i3-10110U, 2 núcleos/4 processadores lógicos, 2,10 GHz; máximo reportado pelo CIM: 2.592 MHz |
| RAM física | 12.691.425.792 bytes (aprox. 11,82 GiB): módulo de 8 GiB e módulo de 4 GiB; velocidades reportadas pelos módulos: 3200 e 2667 MT/s. A frequência efetivamente aplicada não foi medida |
| Memória disponível durante a coleta | Aproximadamente 4,4–4,8 GiB |
| Disco físico | 1 × Toshiba MQ04ABF100, HDD mecânico, aproximadamente 1 TB. O provedor Storage reporta SATA; `Win32_DiskDrive` reporta interface legada IDE |
| Volume C: | NTFS, aproximadamente 998,9 GB; aproximadamente 758,7 GB livres |
| Outro volume | Volume NTFS sem letra, aproximadamente 1,22 GB; cerca de 85 MB livres. Não foi alterado |
| Arquivo de paginação | `C:\pagefile.sys`, alocação 2.904 MB; uso observado 101 MB; pico desde o boot 807 MB |
| Uptime | Último boot informado em 14/10/2026 às 16:34:47; aproximadamente 12 dias e 19 horas até a coleta |
| Virtualização | Hipervisor detectado |
| Plano de energia | Equilibrado |
| WSL2 | `Ubuntu-24.04` e `docker-desktop` instaladas, ambas paradas |
| Docker | Serviço `com.docker.service` parado, tipo Manual; engine indisponível. Docker Desktop não foi iniciado |

## C — CPU e memória

As medições são fotografias curtas, não médias de uma jornada de trabalho:

- A leitura pontual de `Win32_Processor.LoadPercentage` variou entre 37%, 38% e 99%.
- Em uma amostra de 10 segundos, contadores por processo apontaram os filhos do VS Code PID 1472 e PID 3368 com aproximadamente 71% e 25% de `PercentProcessorTime`, respectivamente. Em uma amostra posterior de 8 segundos, esses processos tiveram aproximadamente 52% e 46%; `System` chegou a 17%. Os PIDs 1472 e 3368 eram `Code.exe` (renderer e processo gráfico).
- Os contadores de I/O por processo mostraram atividade de leitura/escrita nos mesmos processos `Code.exe`. Isso comprova correlação temporal com o VS Code, não qual arquivo, extensão ou operação é a causa.
- Foram observados 213–219 processos. Processos com maiores working sets em uma amostra: VS Code aproximadamente 684 MB; Brave aproximadamente 656 MB; Memory Compression aproximadamente 624–658 MB; outro VS Code aproximadamente 617–658 MB; Copilot Runtime aproximadamente 274–291 MB; Defender aproximadamente 232–247 MB. Os valores variam entre amostras.
- A soma de working sets de processos não equivale a RAM física ocupada, pois há memória compartilhada. A leitura do Windows mostrou 4,4–4,8 GB disponíveis.
- `PagesInputPersec`, `PagesOutputPersec`, `PageReadsPersec` e `PageWritesPersec` estavam em zero na leitura obtida. Uso atual do pagefile era 101 MB. Não há evidência nesta coleta de paginação contínua.

**Interpretação:** VS Code e o conjunto de processos de desenvolvimento/navegador são os maiores candidatos observados para picos de CPU e consumo individual de RAM. A amostra de CPU muito alta não persistiu em todas as leituras e parte da atividade pode ter sido causada pelas próprias consultas de diagnóstico. Confiança moderada para associação ao VS Code; insuficiente para afirmar causa única da lentidão.

## D — Disco

- O armazenamento é um HDD mecânico, não SSD. C: tem cerca de 76% de espaço livre, portanto não há pressão por falta de capacidade.
- `Get-PhysicalDisk` informou `HealthStatus: Healthy` e `OperationalStatus: OK`; `Win32_DiskDrive` informou `Status: OK`.
- Em uma amostra de oito segundos, os contadores WMI mostraram cerca de 9,66 MB/s de leitura no disco físico, fila física 4 e fila lógica 11. Uma amostra anterior indicou disco ocioso. O contador `PercentDiskTime` retornou 558 nessa amostra e não deve ser interpretado isoladamente como uma porcentagem literal de tempo; os valores de latência formatados retornaram zero e não serviram para calcular latência real.
- Os contadores de I/O por processo colocaram processos `Code.exe` entre os principais durante a coleta. O OneDrive não apareceu entre os principais processos de I/O nas amostras disponíveis; não foi possível medir taxa de sincronização por arquivo.
- Não foram encontrados avisos/erros relacionados a disco, NTFS, armazenamento, volume ou WHEA no log System dos últimos 30 dias consultados.
- `Get-StorageReliabilityCounter` não forneceu acesso ao recurso CIM. O provedor SMART `MSStorageDriver_FailurePredictStatus` também retornou acesso negado. A consulta de temperatura ACPI foi negada/não disponível. `fsutil dirty query C:` retornou acesso negado.
- Fragmentação, latência com resolução adequada e setores defeituosos não foram testados. Não foram executados `chkdsk`, benchmarks, otimização/desfragmentação ou reparos.

**Conclusão do HDD:** não há evidência observada de falha iminente, mas o estado genérico `Healthy` não substitui SMART. O risco físico permanece **NÃO VERIFICADO**. Se surgirem ruídos, erros de leitura, travamentos repetidos ou novos eventos de disco, preservar dados prioritários e não executar cargas pesadas, desfragmentação ou reparo automático.

## E — Inicialização

Itens reportados por `Win32_StartupCommand`:

| Item | Classificação | Ação nesta auditoria |
|---|---|---|
| Ollama (`Ollama.lnk` na Startup do usuário) | Desenvolvimento/opcional; impacto real não medido | Mantido; candidato a desativação manual somente após aprovação |
| OneDrive (`OneDrive.exe /background`) | Sincronização; potencialmente necessário aos arquivos atuais | Mantido |
| Docker Desktop | Desenvolvimento/Home Server; não estava em execução | Mantido; iniciar manualmente apenas quando necessário |
| Microsoft Lists / `OneDrive.Sync.Service.exe` | Sincronização/aplicativo Microsoft; finalidade operacional não validada | Mantido |
| Microsoft Edge AutoLaunch | Opcional | Mantido; candidato a desativação após aprovação |
| SecurityHealth | Notificações de segurança | Mantido |
| OneDrive Startup Task | Tarefa de inicialização do sincronizador | Mantida |
| RtkAudUService64_BG | Driver/serviço de áudio Realtek | Mantido |

As entradas padrão da Microsoft e tarefas do Windows não foram alteradas. Não foi feita alteração de inicialização além da tarefa OpenClaw detalhada na seção F.

## F — OpenClaw

**Identificação do mecanismo:** tarefa agendada `\OpenClaw Gateway`, habilitada originalmente, com gatilho de logon e ação única `C:\Users\mathe\.openclaw\gateway.cmd`. A descrição identificava OpenClaw Gateway v2026.6.10. Não foi encontrado serviço Windows, entrada de registro `Run` ou atalho de Startup adicional associado a OpenClaw.

**Alteração autorizada realizada:** `Disable-ScheduledTask` foi aplicado somente à tarefa `OpenClaw Gateway`. A tarefa segue registrada, mas com `Settings.Enabled = False`. A verificação posterior confirmou que o launcher ainda existe e que o comando `openclaw` continua disponível em `C:\Users\mathe\AppData\Roaming\npm\openclaw.ps1`. Nenhum processo OpenClaw foi encerrado; nenhum arquivo, dado, configuração ou plugin foi removido.

**Estado anterior registrado:** tarefa habilitada; ação `C:\Users\mathe\.openclaw\gateway.cmd`; gatilho de logon. O último resultado registrado antes da mudança era `3221225786` (`0xC000013A`); a causa desse resultado não foi investigada. O XML da tarefa foi consultado em memória, não exportado para arquivo.

**Reversão:** em PowerShell, executar `Enable-ScheduledTask -TaskName 'OpenClaw Gateway' -TaskPath '\'`. Não foi feito reboot para teste.

## G — OneDrive e repositórios

- O diretório dos projetos está sob `C:\Users\mathe\OneDrive\Desktop\automação zap\`; a variável OneDrive aponta para `C:\Users\mathe\OneDrive`.
- O processo `OneDrive.Sync.Service.exe` foi observado com cerca de 95 MB de working set. Não ficou entre os principais processos de I/O nas amostras disponíveis; atividade de sincronização em nível de arquivo não foi verificada.
- `GasFlow-integration` está em worktree Git e tem branch `release/home-server-candidate`, HEAD `e989f70d029385fd974d3d7e5cb0426cbce670a5`; seu status estava limpo antes da criação deste relatório.
- Worktrees verificadas: `GasFlow` em `sec-02-whatsapp-gateway` (HEAD `213c1873...`, com o arquivo não rastreado preexistente `docs/OPS_00_HOME_SERVER_READINESS.md`), `GasFlow-freebuff` em `parallel/freebuff-mobile-p0` (HEAD `92e3d500...`), `GasFlow-integration` em `release/home-server-candidate` e `GasFlow-opencode` em `parallel/opencode-data` (HEAD `d256ac63...`). Nenhuma foi movida ou alterada por esta auditoria.
- `frontend\node_modules` existe. `backend\node_modules`, `backend\.venv`, `node_modules`, `.venv`, diretórios `backend\data`, `backend\logs`, `logs`, `dist` e `build` não foram encontrados nos caminhos diretos consultados. `.ruff_cache` existe.
- Não foi feita varredura recursiva de todos os arquivos nem leitura de bancos SQLite. Assim, tamanhos de `node_modules`, caches, builds, logs, SQLite e dados sincronizados são **NÃO VERIFICADOS**.
- `git count-objects -vH` reportou um caminho classificado como `garbage` (0 bytes) sob `GasFlow\.git\worktrees\GasFlow-integration\refs`, além de 6.771 objetos soltos e 4 packs. O status Git da worktree de integração permaneceu limpo. Nada foi removido nem executado `git gc`/`prune`; confirmar o significado do aviso em uma investigação Git separada antes de qualquer limpeza ou migração.

**Plano futuro, não executado:** antes de qualquer migração para fora do OneDrive, inventariar todas as worktrees e arquivos não rastreados, confirmar commits locais sem push, criar backup verificável, copiar para diretório local fora da sincronização, validar branches/arquivos e só então preparar rollback. Não mover ou interromper a sincronização nesta fase.

## H — Serviços e virtualização

- `SysMain` e `WSearch` estavam em execução com inicialização Automática. Não há evidência medida de que sejam a causa; foram mantidos.
- `wuauserv` estava em execução com inicialização Manual; BITS estava em execução Automática.
- Defender, Firewall e serviços de áudio permaneceram ativos.
- `com.docker.service` estava parado/Manual; WSL2 e `docker-desktop` também estavam parados. Nenhum serviço foi iniciado ou parado pela auditoria.
- Não foi observada escuta na porta local 8000 nem processo identificável como backend GasFlow, WhatsApp Gateway, Python, Node ou Docker na consulta final. Isso descreve apenas o instante da coleta e não autoriza encerramento de processos.
- Nenhum serviço de Windows foi desabilitado. Nenhum backend, Desktop, SQLite ou sessão WhatsApp foi alterado.

## I — Segurança e saúde do Windows

- Microsoft Defender: serviço e antivírus ativos; proteção em tempo real ativa. Assinaturas reportadas atualizadas em 27/10/2026 às 02:12.
- Firewall: perfis Domain, Private e Public habilitados.
- Não foram encontrados os indicadores de reboot pendente consultados no Component Based Servicing e Windows Update.
- Os hotfixes consultados incluíam atualizações de segurança instaladas em 14/10/2026. A existência de atualizações ainda pendentes **não foi verificada online**.
- Não foram executados SFC, DISM, reparos, alterações de política ou mudanças de segurança.
- Acesso insuficiente impediu algumas consultas privilegiadas descritas na seção D; não se presume integridade total do Windows/disco a partir disso.

## J — Plano de limpeza (aguarda aprovação)

Nenhum arquivo foi apagado e nenhum cache foi limpo. Há candidatos a medir em uma etapa posterior:

| Candidato | Evidência | Espaço recuperável | Risco |
|---|---|---:|---|
| `frontend\node_modules` | Diretório existe dentro do repositório sincronizado | NÃO VERIFICADO; não medido | Pode exigir reinstalação e gerar I/O/sincronização ao recriar |
| `.ruff_cache` | Diretório existe | NÃO VERIFICADO | Baixo para o código, mas não há justificativa para apagar agora |
| TEMP, cache npm/pip, logs e builds | Não houve varredura recursiva | NÃO VERIFICADO | Pode remover arquivos em uso ou evidências |
| Objetos Git e worktrees | Há múltiplas worktrees e aviso de `garbage` | Não candidato a limpeza nesta fase | Alto risco de perda de histórico/refs se usar `gc`/`prune` sem investigar |

O volume C: dispõe de aproximadamente 758,7 GB livres; portanto, não há necessidade urgente de apagar arquivos por falta de espaço. Quantificação de espaço recuperável fica pendente de uma medição controlada, após avaliar o HDD.

## K — Capacidade para o Home Server

- Para um LAB-01 limitado a PostgreSQL e Redis, os limites configurados são aproximadamente 640 MiB + 128 MiB (768 MiB total) e 1,0 + 0,5 CPU. Isso pode ser avaliável em teste controlado, mas não foi executado e o daemon está indisponível.
- O conjunto principal configurado (PostgreSQL, Redis, backend, frontend e WhatsApp Gateway) tem limites aproximados de 2.688 MiB e até 4,5 CPUs somadas; a observabilidade adicionaria aproximadamente 672 MiB e não deve ser ativada antes de o núcleo funcionar bem.
- Esses limites não são medições de consumo real e não incluem todos os custos de Windows, Docker Desktop/WSL, GasFlow Desktop e ferramentas de desenvolvimento.
- Com 2 núcleos físicos, HDD mecânico, 12 GB de RAM e uso simultâneo para empresa/desenvolvimento, o computador **NÃO É RECOMENDADO para hospedar o Home Server completo como serviço de produção contínuo**.
- Para o laboratório inicial de PostgreSQL + Redis, a classificação é **APTO COM RESTRIÇÕES**, somente depois de o usuário iniciar o Docker Desktop manualmente, confirmar o daemon/isolamento e autorizar explicitamente a execução. No momento, o LAB-01 está bloqueado pelo daemon indisponível.
- O gargalo provável de armazenamento é o HDD; CPU de 2 núcleos também limita concorrência. Um SSD SATA compatível é a melhoria futura de maior impacto provável, mas não foi comprado nem instalado, e não é requisito para continuar diagnósticos de baixo risco.
- Nenhuma observabilidade completa foi iniciada ou recomendada antes da validação do núcleo.

## L — Priorização

| Prioridade | Item | Evidência e ação segura |
|---|---|---|
| P0 | Sinais de falha física do HDD, se surgirem | Nenhum sinal conclusivo nesta coleta; SMART não verificado. Se houver erro/ruído, preservar dados e suspender cargas pesadas; não reparar ou desfragmentar automaticamente |
| P1 | Lentidão/intermitência de CPU e I/O em HDD | Picos de CPU em processos VS Code e filas/leitura de disco em uma amostra curta; causa por arquivo ainda não identificada. Coletar amostra em período de uso real com ferramenta aprovada, sem stress test |
| P1 | Home Server completo neste host | CPU com 2 núcleos e HDD mecânico tornam a hospedagem contínua não recomendada; manter teste limitado até validação e orçamento |
| P1 | Docker parado para LAB-01 | Engine indisponível e recursos preexistentes ainda não podem ser inspecionados. Operador deve iniciar manualmente e autorizar antes de qualquer `up` |
| P2 | Projetos no OneDrive e `frontend\node_modules` | Aumentam potencial de I/O e churn de sincronização; atividade e tamanho não medidos. Planejar avaliação/migração futura com backup e validação |
| P2 | Inicialização de Ollama, Docker Desktop e Edge | Candidatos opcionais; não foram desativados. Avaliar uso e aprovação individual |
| P2 | SMART/temperatura/dirty flag sem leitura | Limitação de permissões/disponibilidade; repetir por administrador somente em etapa aprovada, sem reparos |
| P3 | Relatório Git de `garbage` em `refs` | Aviso de 0 bytes sem alteração de status. Investigar separadamente; não limpar |

## M — Plano de otimização

### Correção autorizada realizada

- Desabilitada somente a tarefa de logon `OpenClaw Gateway`; launcher, instalação e comando manual preservados. Reversão descrita na seção F.

### Sugestões que exigem aprovação adicional

1. Medir por período maior a utilização de CPU e I/O no momento em que a lentidão for percebida, identificando processos/arquivos sem interromper o GasFlow.
2. Avaliar, individualmente, se Ollama, Docker Desktop e Edge precisam iniciar automaticamente; não desativar sem aprovação.
3. Medir tamanhos de caches e `frontend\node_modules` depois de confirmar saúde do HDD; aprovar cada limpeza antes de apagar.
4. Repetir SMART/eventos com permissões apropriadas. Se houver indício de falha, priorizar cópia de dados antes de qualquer manutenção.

### Mudanças estruturais para outro momento

- Planejar mudança dos repositórios para fora do OneDrive, mantendo os quatro worktrees, branches, commits locais, arquivos não rastreados e rollback.
- Avaliar SSD SATA compatível e, em momento futuro, hardware com mais núcleos para hospedagem contínua.
- Não mudar BIOS, serviços do Windows, Defender, Firewall, Update, WSL ou Docker automaticamente.

## N — Estado final

- Worktree de integração: branch `release/home-server-candidate`, HEAD `e989f70d029385fd974d3d7e5cb0426cbce670a5`. O relatório é o único arquivo novo não commitado nesta worktree.
- Worktree `GasFlow` continua com o arquivo não rastreado preexistente `docs/OPS_00_HOME_SERVER_READINESS.md`; não foi alterado. Worktrees Freebuff e OpenCode também não foram alteradas.
- Alteração no sistema: tarefa agendada `OpenClaw Gateway` desabilitada, reversível; nenhum outro autostart modificado.
- Nenhum processo foi finalizado. Serviços Windows não foram modificados. Defender e Firewall permaneceram ativos.
- Nenhum Docker, container, migration, limpeza, reparo, reboot, push, merge ou deploy foi executado.
- **Próxima ação:** quando o usuário decidir, iniciar Docker Desktop manualmente; repetir preflight do engine e verificar containers/volumes/redes/portas do projeto LAB-01. Só depois de aprovação explícita executar comandos de homologação limitados a PostgreSQL e Redis.

## Respostas diretas

1. **Por que o PC está lento?** Não foi isolada uma causa única. Há CPU de 2 núcleos e HDD; amostras curtas mostraram picos em processos VS Code e filas/leituras no disco, mas não identificam arquivo ou causa persistente.
2. **O HDD está saudável?** O Windows reportou `Healthy`/`OK` e não houve eventos de armazenamento nos últimos 30 dias consultados. SMART e dirty flag não puderam ser verificados; saúde física completa: **NÃO VERIFICADO**.
3. **O que mais consome disco?** Nas amostras de processo, processos filhos do VS Code tiveram os maiores contadores de I/O; OneDrive não foi o maior observado. A origem por arquivo não foi identificada.
4. **O que mais consome RAM?** Instâncias do VS Code e Brave, seguidas por Memory Compression, Copilot Runtime e Defender. Havia aproximadamente 4,4–4,8 GB disponíveis e não foi observada paginação ativa.
5. **O que inicia desnecessariamente?** Não é possível determinar necessidade apenas pelo nome. Ollama, Docker Desktop e Edge são candidatos opcionais; nenhuma dessas entradas foi alterada. OneDrive e componentes de segurança/driver foram mantidos.
6. **O OpenClaw deixou de iniciar automaticamente?** Sim. A tarefa `OpenClaw Gateway` está desabilitada; o launcher e o comando manual permanecem.
7. **Quanto espaço pode ser recuperado?** **NÃO VERIFICADO**; nenhuma varredura recursiva ou limpeza foi executada. C: já tem cerca de 758,7 GB livres.
8. **Quais otimizações realmente farão diferença?** Diagnosticar a origem de I/O durante a lentidão; reduzir concorrência de processos de desenvolvimento/navegador quando não necessários; avaliar SSD no futuro. Desativar serviços Windows sem evidência não é recomendado.
9. **O PC aguenta o Home Server?** Não é recomendado para o conjunto completo em produção contínua; pode ser avaliado com restrições para laboratório PostgreSQL + Redis.
10. **O que fazer antes do LAB-01?** Iniciar Docker Desktop manualmente, confirmar daemon e isolamento, verificar que não existem recursos com o projeto do laboratório e obter autorização expressa antes de `docker compose up`. Não executar migrations nesta fase.
