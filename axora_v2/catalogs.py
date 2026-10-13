"""Catálogos padronizados por espaço financeiro do AXORA.

Preserva descrições históricas; a lista determina apenas novos lançamentos.
"""
import csv
import io
import re
from fastapi import HTTPException

KIND_NAMES = {"category": "Categoria", "responsible": "Responsável"}


def clean_option(payload):
    if not isinstance(payload, dict) or set(payload) != {"kind", "name"}:
        raise HTTPException(422, "Informe tipo e nome da opção.")
    kind = payload["kind"]
    name = payload["name"]
    if kind not in KIND_NAMES or not isinstance(name, str):
        raise HTTPException(422, "Categoria ou responsável inválido.")
    name = " ".join(name.strip().split())
    if not (1 <= len(name) <= 120) or re.search(r"[\\x00-\\x1f\\x7f]", name):
        raise HTTPException(422, "O nome precisa ter de 1 a 120 caracteres válidos.")
    return {"kind": kind, "name": name}


def canonicalize_provision(values, options):
    """Substitui nomes digitados pela grafia de um catálogo ativo do workspace."""
    for field, kind in (("p_category", "category"), ("p_responsible", "responsible")):
        selected = str(values.get(field, "")).strip().casefold()
        allowed = [entry["name"] for entry in options
                   if entry.get("kind") == kind and entry.get("active")
                   and str(entry.get("name", "")).casefold() == selected]
        if not allowed:
            raise HTTPException(422, f"{KIND_NAMES[kind]} fora do catálogo. Atualize as listas em Configurações.")
        values[field] = allowed[0]
    return values


def export_csv(items):
    """CSV com BOM e separador ; para Excel, sem fórmula executável."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["AXORA — PADRONIZAÇÃO DE LANÇAMENTOS"])
    writer.writerow(["Tipo", "Nome padronizado", "Situação", "Orientação"])
    for kind in ("category", "responsible"):
        for item in sorted((x for x in items if x["kind"] == kind),
                           key=lambda i: (not i["active"], i["name"].casefold())):
            name = str(item["name"])
            if name.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                name = "'" + name
            label = KIND_NAMES[kind]
            guide = ("Classifica a finalidade da despesa."
                     if kind == "category" else "Identifica quem responde pelo compromisso.")
            writer.writerow([label, name, "Ativo" if item["active"] else "Inativo", guide])
    return "\ufeff" + output.getvalue()
