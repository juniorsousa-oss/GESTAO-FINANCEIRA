"""Pix BR Code offline: valida entrada e gera QR sem serviços externos.

A chave Pix exige nome e cidade do recebedor para montar BR Code estático.
Um Pix Copia e Cola existente é preservado integralmente, com CRC verificado.
Não processa nem confirma pagamentos.
"""
import io
import base64
import re
import unicodedata
from uuid import UUID

import qrcode
from fastapi import HTTPException


def bad(message="Chave Pix ou código Pix inválido."):
    raise HTTPException(422, message)


def _crc16(data: str) -> str:
    crc = 0xFFFF
    for byte in data.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _tlv(tag: str, value: str) -> str:
    if len(value.encode("ascii")) > 99:
        bad("Campo do Pix excede o tamanho permitido.")
    return f"{tag}{len(value):02d}{value}"


def _fields(payload: str):
    """Parser de TLV numérico, sem interpretar/consultar URLs de cobranças dinâmicas."""
    i, found = 0, {}
    while i < len(payload):
        if i + 4 > len(payload) or not payload[i:i+4].isdigit():
            bad("Pix Copia e Cola contém campos inválidos.")
        tag, count = payload[i:i+2], int(payload[i+2:i+4])
        i += 4
        if count > len(payload) - i or tag in found:
            bad("Pix Copia e Cola contém campos duplicados ou incompletos.")
        found[tag] = payload[i:i+count]
        i += count
    return found


def validate_brcode(text: str) -> str:
    if not isinstance(text, str) or len(text) < 40 or len(text) > 1200:
        bad("Pix Copia e Cola deve conter um código completo.")
    if any(ord(c) < 32 or ord(c) > 126 for c in text):
        bad("Pix Copia e Cola deve conter somente caracteres ASCII válidos.")
    values = _fields(text)
    if (values.get("00") != "01" or values.get("53") != "986"
        or values.get("58") != "BR" or "59" not in values or "60" not in values
        or not re.fullmatch(r"6304[0-9A-Fa-f]{4}", text[-8:])):
        bad("Pix Copia e Cola não segue o padrão BR Code.")
    if _crc16(text[:-4]) != text[-4:].upper():
        bad("CRC inválido no Pix Copia e Cola. Confira o código original.")
    merchants = [v for k, v in values.items() if k.isdigit() and 26 <= int(k) <= 51]
    if not any(_fields(m).get("00", "").lower() == "br.gov.bcb.pix" for m in merchants):
        bad("Código não identificado como Pix.")
    return text


def _verified_digits(digits: str) -> bool:
    # Recebe somente dígitos: CPF de 11 ou CNPJ de 14 algarismos.
    if len(set(digits)) == 1:
        return False
    if len(digits) == 11:
        for size in (9, 10):
            check=(sum(int(v)*(size+1-i) for i,v in enumerate(digits[:size]))*10)%11
            if check == 10: check = 0
            if check != int(digits[size]): return False
        return True
    if len(digits) == 14:
        for size,weights in ((12,[5,4,3,2,9,8,7,6,5,4,3,2]),
                             (13,[6,5,4,3,2,9,8,7,6,5,4,3,2])):
            remainder=sum(int(v)*w for v,w in zip(digits[:size],weights))%11
            check=0 if remainder<2 else 11-remainder
            if check!=int(digits[size]): return False
        return True
    return False


def normalize_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 130:
        bad("Informe uma chave Pix válida.")
    value = value.strip()
    if any(ord(c)<33 or ord(c)>126 for c in value):
        bad("A chave Pix contém espaços ou caracteres inválidos.")
    try:
        return str(UUID(value))
    except ValueError:
        pass
    if re.fullmatch(r"[\d.\-/]+",value):
        digits=re.sub(r"\D","",value)
        if len(digits) in (11,14) and _verified_digits(digits):
            return digits
    if re.fullmatch(r"\+55[1-9]\d{9,10}",value):
        return value
    if re.fullmatch(r"[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", value):
        return value
    bad("Chave Pix inválida. Use CPF, CNPJ, e-mail, telefone +55 ou chave aleatória.")


def _receiver(value: str, max_len: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        bad(f"Informe {label} do recebedor para gerar o QR Code.")
    raw=unicodedata.normalize("NFKD", value)
    text="".join(c for c in raw if not unicodedata.combining(c)).upper().strip()
    text=re.sub(r"[^A-Z0-9 .\-/]", " ", text)
    text=re.sub(r"\s+", " ",text).strip()[:max_len]
    if len(text)<2:
        bad(f"{label} do recebedor inválido.")
    return text


def clean_pix(kind, value, receiver_name=None, receiver_city=None):
    if kind not in ("key","brcode"):
        bad("Escolha Chave Pix ou Pix Copia e Cola.")
    if kind=="brcode":
        code=validate_brcode(value)
        return {"kind":"brcode","value":code,"receiver_name":None,"receiver_city":None}
    return {"kind":"key","value":normalize_key(value),
            "receiver_name":_receiver(receiver_name,25,"o nome"),
            "receiver_city":_receiver(receiver_city,15,"a cidade")}


def brcode_from_key(value: str, name: str, city: str) -> str:
    key=normalize_key(value)
    name=_receiver(name,25,"o nome")
    city=_receiver(city,15,"a cidade")
    merchant=_tlv("00","br.gov.bcb.pix")+_tlv("01",key)
    code=("000201"+
         _tlv("26",merchant)+_tlv("52","0000")+_tlv("53","986")+
         _tlv("58","BR")+_tlv("59",name)+_tlv("60",city)+
         _tlv("62",_tlv("05","***"))+"6304")
    return code+_crc16(code)


def pix_qr(kind: str, value: str, receiver_name: str = None, receiver_city: str = None):
    payload=validate_brcode(value) if kind=="brcode" else brcode_from_key(value,receiver_name,receiver_city)
    qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                     box_size=9,border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    png=io.BytesIO()
    qr.make_image(fill_color="black",back_color="white").save(png,format="PNG")
    return {"copy_paste":payload,"image_data":"data:image/png;base64,"+
            base64.b64encode(png.getvalue()).decode("ascii"),
            "amount_fixed":False if kind=="key" else None,
            "kind":kind}
