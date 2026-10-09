"""Histórico de execuções e funding de um par nos últimos 7 dias. Uso: python pnl_simbolo.py HBAR"""
import os, sys
sys.path.insert(0, "/app"); sys.path.insert(0, os.getcwd())
from okx_client import OKXClient, carregar_env
from datetime import datetime, timezone, timedelta
from collections import defaultdict
carregar_env()
c = OKXClient(os.getenv("OKX_API_KEY"), os.getenv("OKX_API_SECRET"), os.getenv("OKX_PASSPHRASE"), demo=os.getenv("OKX_DEMO", "1") == "1")

inst = f"{(sys.argv[1] if len(sys.argv) > 1 else 'HBAR').upper()}-USDT-SWAP"
TZ = timezone(timedelta(hours=8))  # dia da OKX
begin = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)


def paginar(endpoint, params):
    out, after = [], None
    while True:
        d = c._request("GET", endpoint, {**params, "limit": 100, "after": after}, privado=True)
        out += d
        if len(d) < 100:
            return out
        after = d[-1]["billId"]


fills = paginar("/api/v5/trade/fills-history", {"instType": "SWAP", "instId": inst, "begin": begin})
funding = paginar("/api/v5/account/bills", {"instType": "SWAP", "type": 8, "begin": begin})
ct = float(c.instrumento("SWAP", inst)["ctVal"])

dia = defaultdict(lambda: defaultdict(float))
print(f"{inst}: {len(fills)} execuções nos últimos 7 dias\n")
for f in reversed(fills):
    t = datetime.fromtimestamp(int(f["ts"]) / 1000, TZ)
    q = float(f["fillSz"]) * ct
    d = dia[t.date()]
    d["n"] += 1; d["vol"] += q * float(f["fillPx"])
    d["pnl"] += float(f["fillPnl"] or 0); d["taxa"] += float(f["fee"] or 0)
    d["maker"] += f["execType"] == "M"
    print(f"  {t:%d/%m %H:%M:%S}  {f['side']:<4} {f['posSide']:<5} {q:>8g} @ {f['fillPx']:<9} "
          f"{'maker' if f['execType'] == 'M' else 'taker'}  pnl {float(f['fillPnl'] or 0):+8.2f}  taxa {float(f['fee'] or 0):+.4f}")
for b in funding:
    if b["instId"] == inst:
        dia[datetime.fromtimestamp(int(b["ts"]) / 1000, TZ).date()]["funding"] += float(b["balChg"] or 0)

print("\nPor dia (UTC+8):")
tot = defaultdict(float)
for k in sorted(dia):
    d = dia[k]
    for x in d: tot[x] += d[x]
    print(f"  {k:%d/%m}  {int(d['n']):>3} exec ({int(d['maker'])} maker)  volume {d['vol']:>9.2f}  "
          f"pnl {d['pnl']:+8.2f}  taxa {d['taxa']:+7.2f}  funding {d['funding']:+6.2f}")
print(f"  TOTAL  {int(tot['n']):>3} exec ({int(tot['maker'])} maker)  volume {tot['vol']:>9.2f}  "
      f"pnl {tot['pnl']:+8.2f}  taxa {tot['taxa']:+7.2f}  funding {tot['funding']:+6.2f}  "
      f"= {tot['pnl'] + tot['taxa'] + tot['funding']:+.2f}")

# Posições fechadas: a OKX lança o realizedPnl da vida inteira da posição no dia em que ela fecha
hist = c._request("GET", "/api/v5/account/positions-history", {"instType": "SWAP", "instId": inst, "limit": 100}, privado=True)
print(f"\nHistórico de posições ({len(hist)}):")
for h in hist:
    abre = datetime.fromtimestamp(int(h["cTime"]) / 1000, TZ)
    fecha = datetime.fromtimestamp(int(h["uTime"]) / 1000, TZ)
    print(f"  {h['posSide']:<5} aberta {abre:%d/%m/%y %H:%M}  fechada {fecha:%d/%m/%y %H:%M}  "
          f"entrada {h['openAvgPx']}  saída {h['closeAvgPx']}  máx {float(h['openMaxPos']) * ct:g}  "
          f"pnl {float(h['pnl']):+8.2f}  taxa {float(h['fee']):+7.2f}  funding {float(h['fundingFee']):+6.2f}  "
          f"realizado {float(h['realizedPnl']):+8.2f}")
