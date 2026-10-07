"""Spike Fase 3 - Faces de Logradouro 2022 (IBGE) x CNEFE, Belem.

Uso:
  python spike_cnefe_faces.py <faces.json> <cnefe.csv>

Responde, com numeros:
  A. quantas faces, quantos logradouros, quantas faces sem nome
  B. topologia: nos compartilhados entre faces de ruas DIFERENTES = cruzamentos
  C. juncao CNEFE<->face por (CD_SETOR, CD_QUADRA, CD_FACE): % de cobertura
  D. faixa de numeros por face (do CNEFE) e o caso de aceite Ivan Leao 45
"""

import csv
import json
import sys
import unicodedata
from collections import defaultdict


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def nome_face(p):
    return norm(
        " ".join(
            [
                p.get("NM_TIP_LOG") or "",
                p.get("NM_TIT_LOG") or "",
                p.get("NM_LOG") or "",
            ]
        )
    )


def key(coord):
    return (round(coord[0], 6), round(coord[1], 6))


def main(faces_path, cnefe_path):
    with open(faces_path, encoding="utf-8") as fh:
        gj = json.load(fh)
    feats = gj["features"]

    faces = []
    sem_prop = 0
    for f in feats:
        p = f.get("properties") or {}
        geo = f.get("geometry") or {}
        coords = geo.get("coordinates")
        if not p or not coords:
            sem_prop += 1
            continue
        faces.append(
            {
                "nome": nome_face(p),
                "setor": p.get("CD_SETOR") or "",
                "quadra": p.get("CD_QUADRA") or "",
                "face": p.get("CD_FACE") or "",
                "tot_res": p.get("TOT_RES"),
                "tot_geral": p.get("TOT_GERAL"),
                "coords": coords,
            }
        )
    if sem_prop:
        print(f"(features sem propriedades/geometria ignoradas: {sem_prop})")

    print("=== A. Faces de Logradouro 2022 - Belem ===")
    print(f"faces (segmentos)          : {len(faces)}")
    nomes = {f["nome"] for f in faces if f["nome"]}
    sem_nome = sum(1 for f in faces if not f["nome"])
    print(f"logradouros distintos      : {len(nomes)}")
    print(
        f"faces sem nome             : {sem_nome} ({100.0 * sem_nome / max(len(faces), 1):.1f}%)"
    )

    # B. topologia
    nodo = defaultdict(set)  # no -> set de nomes
    for f in faces:
        for c in f["coords"]:
            nodo[key(c)].add(f["nome"])
    cruz_nos = {k: v for k, v in nodo.items() if len([n for n in v if n]) >= 2}
    print()
    print("=== B. Topologia (nos compartilhados) ===")
    print(f"nos distintos              : {len(nodo)}")
    print(f"nos de >=2 ruas diferentes : {len(cruz_nos)}  <- cruzamentos derivados")
    # faces conectadas: quantas faces tem os DOIS extremos em nos de cruzamento
    conectadas = 0
    for f in faces:
        ends = [key(f["coords"][0]), key(f["coords"][-1])]
        if all(len([n for n in nodo[e] if n]) >= 2 for e in ends):
            conectadas += 1
    print(
        f"faces com 2 extremos cruzados: {conectadas} ({100.0 * conectadas / max(len(faces), 1):.1f}%)"
    )

    # C. juncao CNEFE <-> face
    face_por_key = {(f["setor"], f["quadra"], f["face"]): f for f in faces}
    por_face_num = defaultdict(list)
    total = 0
    casados = 0
    with open(cnefe_path, encoding="latin-1", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            total += 1
            k = (
                row["COD_SETOR"].strip(),
                (
                    row["NUM_QUADRA"].strip().zfill(3)
                    if row["NUM_QUADRA"].strip()
                    else ""
                ),
                (row["NUM_FACE"].strip().zfill(3) if row["NUM_FACE"].strip() else ""),
            )
            f = face_por_key.get(k)
            if f is None:
                continue
            casados += 1
            num = row["NUM_ENDERECO"].strip()
            if num.isdigit():
                por_face_num[k].append(int(num))

    print()
    print("=== C. Juncao CNEFE <-> Face (setor+quadra+face) ===")
    print(f"enderecos CNEFE            : {total}")
    print(
        f"casados com uma face       : {casados} ({100.0 * casados / max(total, 1):.1f}%)"
    )
    faixa = sum(1 for k in por_face_num if len(por_face_num[k]) >= 2)
    print(
        f"faces com >=2 numeros      : {faixa} ({100.0 * faixa / max(len(faces), 1):.1f}%)"
    )

    # D. caso de aceite
    print()
    print("=== D. Caso de aceite: Passagem Ivan Leao, 45 ===")
    alvo = {
        "passagem ivan leao": [],
        "travessa dos berredos": [],
        "travessa dos andradas": [],
    }
    for f in faces:
        if f["nome"] in alvo:
            k = (f["setor"], f["quadra"], f["face"])
            nums = sorted(set(por_face_num.get(k, [])))
            alvo[f["nome"]].append((f, nums))

    for rua, lst in alvo.items():
        print(f"  {rua}: {len(lst)} faces")
        for f, nums in lst:
            ends = [key(f["coords"][0]), key(f["coords"][-1])]
            cruzas = set()
            for e in ends:
                for n in nodo[e]:
                    if n and n != rua:
                        cruzas.add(n)
            rng = f"{min(nums)}..{max(nums)}" if nums else "sem numeros"
            print(
                f"      face {f['quadra']}/{f['face']} nums={rng:>12}  cruza: {sorted(cruzas)}"
            )

    # O numero 45 cai na face de Ivan Leao cujo range contem 45?
    print()
    print("  --- resolucao do numero 45 ---")
    achou = False
    for f, nums in alvo["passagem ivan leao"]:
        if nums and min(nums) <= 45 <= max(nums):
            achou = True
            ends = [key(f["coords"][0]), key(f["coords"][-1])]
            cruzas = sorted(
                {n for e in ends for n in nodo[e] if n and n != "passagem ivan leao"}
            )
            print(
                f"  numero 45 -> face {f['quadra']}/{f['face']} range {min(nums)}..{max(nums)}"
            )
            print(f"  ruas que cruzam os extremos: {cruzas}")
    if not achou:
        print("  numero 45 nao caiu em nenhuma face de Ivan Leao com >=2 numeros")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
