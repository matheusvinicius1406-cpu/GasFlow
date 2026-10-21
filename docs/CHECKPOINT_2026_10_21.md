# Checkpoint — 21/10/2026 (identidade visual + app do entregador)

Retomada de `docs/CHECKPOINT_2026_10_20.md`. O teste no celular (passos 1–6
de ontem) **segue pendente** — o aparelho continua fora do `adb devices` — e
entrou um lote novo fechado hoje: a identidade visual.

## Fechado hoje (21/10)

- **Símbolo unificado do projeto** — `scripts/generate_brand_icons.py` (novo):
  uma chama com miolo gerada por Bézier, desenhada em 4× e reduzida com LANCZOS.
  A mesma arte sai para todos os destinos:
  - launcher Android legado (`mipmap-{mdpi..xxxhdpi}/ic_launcher{,_round}.png`);
  - adaptive icon do Android 8+ (`mipmap-anydpi-v26/ic_launcher{,_round}.xml`,
    `ic_launcher_foreground.png` 432 px, cor de fundo em `values/colors.xml`);
  - `mobile/assets/logo-mark.png` + `logo-badge.png` (UI: splash/login);
  - `desktop/build/icon.png` (512) e `icon.ico` (16→256, electron-builder);
  - `frontend/public/favicon.svg` (vetorial, escrito pelo mesmo script —
    nunca diverge da arte).
  O robô verde do template do RN saiu; o cilindro "GF" antigo do desktop saiu
  também.
- **Design system mobile** (`mobile/src/theme/index.ts`): tokens copiados do
  `frontend/src/index.css` (tema dark) + `src/components/ui/`: `Button`,
  `Input`, `Card`, `StatusChip`, `Banner`, `EmptyState`, `Logo`.
- **Telas refizidas no tema escuro**: `LoginScreen`, `ChangePasswordScreen`
  (checklist de requisitos ao vivo), `ConsentScreen`, `RouteTodayScreen`
  (hero de progresso com %, km do dia, chips de status, estado vazio),
  `DeliveryDetailScreen` (Navegar/Ligar, ações por status, nota da fila
  offline), `UpdateScreen`, `AnimatedSplash`.
- **Navegação**: `RootNavigator` com tema dark do React Navigation, headers
  `#0f0f12`, status bar clara permanente; `windowBackground` nativo trocado
  de branco para `#09090B` (o ícone no splash nativo agora é o novo).
- **Contêiner** (`wired.tsx`): banner "sem conexão" quando o modo é offline,
  erro de atualização em banner de perigo, loading do detalhe via
  `DeliveryLoading`.
- **Web**: `BrandLogo` (sidebar, login, UpdateScreen) e o boot do
  `index.html` usam `/favicon.svg`; `frontend/dist` regerado.
- **Gates**: mobile `typecheck` limpo + **64/64** testes · frontend lint limpo
  + **528/528** testes + `npm run build` · ruff 0 no script novo · APK
  **release buildado em 14m03s** (`C:\gflow`, receita do `android/BUILD.md`),
  copiado para `mobile\android\app\build\outputs\apk\release\app-release.apk`
  (52,8 MB, bundle embutido, foreground 432 px conferido byte a byte dentro
  do pacote).

## Ainda na fila (igual a ontem, com o APK novo)

1. Reconectar o celular e `adb devices` (aceitar depuração USB no aparelho).
2. `adb install -r mobile\android\app\build\outputs\apk\release\app-release.apk`
3. `adb reverse tcp:8000 tcp:8000` com o desktop aberto.
4. Login `edson` / senha temporária → troca de senha (agora com checklist
   visual) → "Rota do Dia" (hero de progresso + chips).
5. Conferir linhas novas em `driver_locations` (driver 000001) e o ponto no
   mapa de rastreio do desktop.
6. Registrar o resultado em `release-v1.2.0-spec.md` (D4/D5) e no CHANGELOG.

## Decisões levantadas hoje

- **Versão do app ficou 1.2.0** (sem bump): o CHANGELOG ganhou a seção
  `1.3.1` para o lote visual, mas `versionName`/`versionCode` do Android e o
  `mobile_version.json` só devem subir quando uma release for publicada — o
  `download_url` aponta para `releases/latest`, que ainda serve o 1.2.0.
- A árvore de trabalho está **suja e não commitada** (ícones, tema, telas,
  favicon, script, docs). Precisa de commit quando você quiser fechar o lote.
- `desktop/build/icon.{png,ico}` mudou: o próximo build do empacotado do
  desktop já sai com a nova marca (não precisa de ação agora).
