"""Importação idempotente e agendada dos dados pessoais do MeuPluggy.

Lê exclusivamente contas explicitamente vinculadas ao item pessoal
configurado. Uma transação importada nunca cria Registro nem quita Provisão.
"""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from axora_v2 import db, meu_pluggy

log = logging.getLogger("axora.meu_pluggy")


def _personal_workspace():
    owner = meu_pluggy.owner_id()
    if owner is None:
        raise HTTPException(503, "Proprietário da conexão não configurado.")
    return db.call("POST", "rpc/axora_user_workspace", data={"p_user_id": owner})


def _account(workspace, account_id):
    rows = db.call("GET", "finance_bank_accounts", params={
        "workspace_id": "eq." + str(workspace),
        "id": "eq." + str(account_id), "limit": 1
    })
    if not rows:
        raise HTTPException(404, "Conta não localizada no espaço pessoal.")
    account = rows[0]
    if str(account.get("pluggy_item_id") or "") != meu_pluggy.personal_item():
        raise HTTPException(403, "Conta não pertence à conexão pessoal autorizada.")
    if not account.get("pluggy_account_id"):
        raise HTTPException(409, "Conta ainda não vinculada ao extrato.")
    return account


def sync_account(workspace, account_id):
    account = _account(workspace, account_id)
    options = {a["id"]: a for a in meu_pluggy.bank_accounts()}
    source_id = meu_pluggy.uuid_text(account["pluggy_account_id"])
    remote = options.get(source_id)
    if not remote:
        raise HTTPException(409, "Conta vinculada não retornada pelo MeuPluggy.")
    incoming = meu_pluggy.recent_transactions(source_id)
    # Se alguma página falhar, nada é importado, evitando extratos incompletos.
    for offset in range(0, len(incoming), 200):
        rows = [
            {"workspace_id": str(workspace), "account_id": int(account_id), **entry}
            for entry in incoming[offset:offset + 200]
        ]
        db.call("POST", "finance_bank_transactions",
                params={"on_conflict": "account_id,source,external_ref"},
                data=rows, prefer="resolution=ignore-duplicates,return=minimal")
    db.call("PATCH", "finance_bank_accounts", params={
        "workspace_id": "eq." + str(workspace), "id": "eq." + str(account_id),
        "pluggy_item_id": "eq." + meu_pluggy.personal_item(),
    }, data={
        "pluggy_balance": remote.get("balance"),
        "pluggy_last_synced": datetime.now(timezone.utc).isoformat()
    }, prefer="return=minimal")
    return {"account_id": int(account_id), "checked": len(incoming),
            "read_only": True, "reconciled": 0,
            "message": "Extrato consultado. Novas transações aguardam validação manual."}


def sync_personal_accounts():
    if not meu_pluggy.configured():
        return 0
    workspace = _personal_workspace()
    accounts = db.call("GET", "finance_bank_accounts", params={
        "workspace_id": "eq." + str(workspace),
        "pluggy_item_id": "eq." + meu_pluggy.personal_item(),
        "select": "id", "limit": 20,
    })
    completed = 0
    for account in accounts:
        try:
            sync_account(workspace, account["id"])
            completed += 1
        except Exception:
            # O worker não interrompe o aplicativo; a próxima tentativa será automática.
            # Não registrar identificadores bancários, credenciais nem respostas do provedor.
            log.warning("Falha na atualização programada de uma conta pessoal.")
    return completed


async def periodic_sync():
    """Consulta a cada 1 hora; a atualização real do MeuPluggy é aproximadamente diária."""
    while True:
        try:
            if meu_pluggy.configured():
                await asyncio.to_thread(sync_personal_accounts)
        except Exception:
            log.warning("Atualização pessoal Pluggy temporariamente indisponível.")
        await asyncio.sleep(3600)
