"""PnL do dia como a OKX calcula: variação de patrimônio (marcação a mercado) desde a virada do dia."""
import os, sys
sys.path.insert(0, "/app"); sys.path.insert(0, os.getcwd())
from okx_client import OKXClient, carregar_env
from datetime import datetime, timezone, timedelta
from collections import defaultdict
carregar_env()
c = OKXClient(os.getenv("OKX_API_KEY"), os.getenv("OKX_API_SECRET"), os.getenv("OKX_PASSPHRASE"), demo=os.getenv("OKX_DEMO", "1") == "1")


def paginar(endpoint, params, chave):
    out, after = [], None
    while True:
        d = c._request("GET", endpoint, {**params, "limit": 100, "after": after}, privado=True)
        out += d
        if len(d) < 100:
            return out
        after = d[-1][chave]


ctval = {}
def moedas(inst, ctr):
    if inst not in ctval:
        i = c.instrumento("SWAP", inst)
        ctval[inst] = float(i["ctVal"]) * float(i.get("ctMult") or 1)
    return ctr * ctval[inst]


def mark_em(inst, ms):
    k = c._request("GET", "/api/v5/market/mark-price-candles", {"instId": inst, "bar": "1m", "after": ms + 60000, "limit": 1})
    return float(k[0][1])


posicoes = c.posicoes()
mark_agora, pos_agora = {}, defaultdict(float)  # quantidade líquida em moedas (+long / -short)
for p in posicoes:
    q = float(p["pos"])
    sinal = (1 if q > 0 else -1) if p["posSide"] == "net" else (1 if p["posSide"] == "long" else -1)
    pos_agora[p["instId"]] += sinal * moedas(p["instId"], abs(q))
    mark_agora[p["instId"]] = float(p["markPx"])

now = datetime.now(timezone.utc)
for fuso in (-3, 0, 8):
    ini = now.astimezone(timezone(timedelta(hours=fuso))).replace(hour=0, minute=0, second=0, microsecond=0)
    ms = int(ini.timestamp() * 1000)
    fills = paginar("/api/v5/trade/fills", {"instType": "SWAP", "begin": ms}, "billId")
    bills = paginar("/api/v5/account/bills", {"begin": ms, "type": 8}, "billId")  # funding

    caixa, taxa, funding, delta = (defaultdict(float) for _ in range(4))
    for f in fills:
        inst, s = f["instId"], (1 if f["side"] == "buy" else -1)
        q = moedas(inst, float(f["fillSz"]))
        delta[inst] += s * q
        caixa[inst] -= s * q * float(f["fillPx"])
        taxa[inst] += float(f["fee"] or 0)
    for b in bills:
        funding[b["instId"]] += float(b["balChg"] or 0)

    print(f"\n=== Dia começando {ini:%d/%m %H:%M} UTC{fuso:+d}  ({len(fills)} execuções) ===")
    total = 0.0
    for inst in sorted(set(pos_agora) | set(delta) | set(funding)):
        p1 = pos_agora.get(inst, 0.0)
        p0 = p1 - delta[inst]
        m1 = mark_agora.get(inst) or (mark_em(inst, int(now.timestamp() * 1000) - 60000) if p1 else 0.0)
        m0 = mark_em(inst, ms) if abs(p0) > 1e-12 else 0.0
        mtm = caixa[inst] + p1 * m1 - p0 * m0
        pnl = mtm + taxa[inst] + funding[inst]
        total += pnl
        print(f"  {inst:<16} pos {p0:+g} -> {p1:+g}  marca {m0:g} -> {m1:g}  "
              f"preço {mtm:+8.2f}  taxa {taxa[inst]:+6.2f}  funding {funding[inst]:+6.2f}  = {pnl:+8.2f}")
    print(f"  PNL DO DIA: {total:+.2f} USDT")
