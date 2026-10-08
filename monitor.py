"""
Monitor de posições OKX -> alerta no Telegram quando um par chega no zero a zero.
Somente leitura: não abre nem fecha nada.
"""

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from okx_client import OKXClient, OKXError, carregar_env

BRT = timezone(timedelta(hours=-3))


def agora():
    return datetime.now(BRT).strftime("%d/%m %H:%M:%S")


def telegram(texto):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": texto,
                         "parse_mode": "HTML"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
    except Exception as e:
        print(f"[{agora()}] falha ao enviar Telegram: {e}", flush=True)


def resumo_pares(client, cache, taker):
    """Agrupa as posições por par e calcula resultado e preço de zero a zero."""
    pares = {}
    for p in client.posicoes():
        qtd = float(p["pos"] or 0)
        if qtd == 0:
            continue
        inst = p["instId"]
        if inst not in cache:
            cache[inst] = client.instrumento(p["instType"], inst)
        info = cache[inst]

        mark = float(p["markPx"])
        ct = float(info["ctVal"]) * float(info.get("ctMult") or 1)
        moedas = abs(qtd) * ct
        if info.get("ctType") == "inverse":
            moedas /= mark

        if p["posSide"] == "net":
            sinal = 1 if qtd > 0 else -1
        else:
            sinal = 1 if p["posSide"] == "long" else -1

        d = pares.setdefault(inst, {"mark": mark, "liquido": 0.0,
                                    "bruto": 0.0, "pnl": 0.0})
        d["liquido"] += sinal * moedas
        d["bruto"] += moedas
        d["pnl"] += float(p["upl"] or 0)

    for d in pares.values():
        d["taxa"] = d["bruto"] * d["mark"] * taker      # fechar tudo a mercado
        d["resultado"] = d["pnl"] - d["taxa"]
        if abs(d["liquido"]) > 1e-12:
            d["alvo"] = d["mark"] - d["resultado"] / d["liquido"]
            d["dist"] = (d["alvo"] / d["mark"] - 1) * 100
        else:
            d["alvo"] = d["dist"] = None                 # hedge total
    return pares


def texto_status(pares):
    linhas = [f"📊 <b>Status</b> ({agora()})"]
    for inst, d in sorted(pares.items(), key=lambda x: x[1]["resultado"]):
        nome = inst.replace("-USDT-SWAP", "")
        if d["alvo"] is None:
            alvo = "hedge total"
        elif d["alvo"] <= 0:
            alvo = "sem preço possível"
        else:
            alvo = f"zero a zero em {d['alvo']:.6g} ({d['dist']:+.1f}%)"
        linhas.append(f"<b>{nome}</b> {d['mark']:.6g} | "
                      f"{d['resultado']:+.2f} USDT | {alvo}")
    return "\n".join(linhas)


def main():
    carregar_env()
    client = OKXClient(
        api_key=os.environ["OKX_API_KEY"],
        api_secret=os.environ["OKX_API_SECRET"],
        passphrase=os.environ["OKX_PASSPHRASE"],
        demo=os.getenv("OKX_DEMO", "0") == "1",
    )
    intervalo = int(os.getenv("INTERVALO", "60"))          # segundos
    lucro_min = float(os.getenv("LUCRO_MINIMO", "0.5"))    # USDT acima de zero
    status_horas = float(os.getenv("STATUS_HORAS", "6"))   # resumo periódico

    try:
        t = client.taxas("SWAP")[0]
        taker = abs(float(t.get("takerU") or t.get("taker")))
    except Exception:
        taker = 0.0005

    cache, alertados = {}, set()
    ultimo_status, falhas = 0.0, 0
    telegram(f"🤖 Monitor iniciado. Checando a cada {intervalo}s, "
             f"alerta a partir de {lucro_min:+.2f} USDT por par.")

    while True:
        try:
            pares = resumo_pares(client, cache, taker)
            falhas = 0

            for inst, d in pares.items():
                nome = inst.replace("-USDT-SWAP", "")
                if d["resultado"] >= lucro_min and inst not in alertados:
                    telegram(f"✅ <b>{nome} chegou no zero a zero!</b>\n"
                             f"Preço: {d['mark']:.6g}\n"
                             f"Resultado se fechar tudo agora: "
                             f"{d['resultado']:+.2f} USDT (já com taxa)\n"
                             f"Feche pela Talos as duas pontas.")
                    alertados.add(inst)
                elif d["resultado"] < lucro_min - 2 and inst in alertados:
                    telegram(f"↩️ {nome} saiu da zona de zero a zero "
                             f"({d['resultado']:+.2f} USDT).")
                    alertados.discard(inst)

            alertados &= set(pares)   # esquece pares que foram fechados

            if time.time() - ultimo_status >= status_horas * 3600:
                telegram(texto_status(pares))
                ultimo_status = time.time()

            resumo = " | ".join(f"{i.split('-')[0]} {d['resultado']:+.2f}"
                                for i, d in pares.items())
            print(f"[{agora()}] {resumo}", flush=True)

        except Exception as e:
            falhas += 1
            print(f"[{agora()}] erro ({falhas}): {e}", flush=True)
            if falhas == 5:
                telegram(f"⚠️ Monitor com erro há 5 tentativas seguidas:\n{e}")

        time.sleep(intervalo)


if __name__ == "__main__":
    main()