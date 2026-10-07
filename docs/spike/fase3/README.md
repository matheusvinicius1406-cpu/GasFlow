# Spike Fase 3 — "entre ruas" por dados oficiais do IBGE

Medição que sustenta o `docs/adr/ADR-0008-entre-ruas-por-dados-ibge.md` e a
`docs/prompts/renomeador-contatos-fase3.md`. Reproduzível com **Python puro**
(stdlib), sem dependência nova.

## Dados (Baixar)

```bash
# CNEFE 2022 - Belem (rua, numero, CEP, lat/lng) : 13 MB zip -> 97,9 MB csv
curl -sSL -o belem_addr.zip \
  "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/15_PA/1501402_BELEM.zip"

# Faces de Logradouro 2022 - PA inteiro (json por municipio) : 15,4 MB zip
curl -sSL -o faces_pa.zip \
  "https://geoftp.ibge.gov.br/recortes_para_fins_estatisticos/malha_de_setores_censitarios/censo_2022/base_de_faces_de_logradouros_versao_2022_censo_demografico/json/PA_faces_de_logradouros_2022_json.zip"

unzip -o belem_addr.zip 1501402_BELEM.csv
unzip -o faces_pa.zip "PA/1501402_faces_de_logradouros_2022.json"
```

## Rodar

```bash
python docs/spike/fase3/cnefe_cobertura.py 1501402_BELEM.csv
python docs/spike/fase3/faces_caso_aceite.py \
  PA/1501402_faces_de_logradouros_2022.json 1501402_BELEM.csv
```

## Resultado medido (2026-09-30, Belém)

CNEFE: **618.075** endereços, **100%** com lat/lng, **100%** com número numérico,
**98,8%** dos 5.962 logradouros com **≥2 âncoras**. A rua que reprovava a Fase 2
(Rodovia Augusto Montenegro, **0** âncoras no OSM) tem **8.668** no CNEFE.

Faces: **48.159** segmentos, **30.217** nós de ≥2 ruas (cruzamentos derivados),
junção CNEFE↔face cobre **85,6%** dos endereços. Limites: 19,6% das faces sem
nome; só 52,3% com **dois** cruzamentos.

Caso de aceite (Passagem Ivan Leão, 45): **5** faces de Ivan Leão contêm o 45;
as duas faixas mais apertadas (`002/018` = `33..62`, `004/011` = `35..65`)
concordam no par **"Passagem Pedro Álvares Cabral e Travessa dos Berredos"** —
o par imaginado ("Berredos e Andradas") **não** se reproduz.

O ADR-0008 tem a tabela completa; este README só garante que o número é
re-executável.
