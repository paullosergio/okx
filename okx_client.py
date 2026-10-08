"""
Cliente simples para a API v5 da OKX, usando apenas a biblioteca padrão.

Configuração (variáveis de ambiente ou arquivo .env na mesma pasta):
    OKX_API_KEY=...
    OKX_API_SECRET=...
    OKX_PASSPHRASE=...
    OKX_DEMO=1          # 1 = conta demo (simulated trading), 0 = conta real
"""

import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def carregar_env(caminho=".env"):
    """Carrega um arquivo .env simples (CHAVE=valor) sem libs externas."""
    if not os.path.exists(caminho):
        return
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


class OKXError(Exception):
    pass


class OKXClient:
    def __init__(self, api_key="", api_secret="", passphrase="",
                 demo=False, base_url="https://www.okx.com", timeout=15):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.demo = demo
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ---------- infraestrutura ----------

    @staticmethod
    def _timestamp():
        # Formato exigido: 2024-01-01T12:00:00.123Z
        return (datetime.now(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"))

    def _assinar(self, timestamp, metodo, caminho, corpo):
        mensagem = f"{timestamp}{metodo}{caminho}{corpo}"
        digest = hmac.new(self.api_secret.encode(), mensagem.encode(),
                          hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def _request(self, metodo, endpoint, params=None, body=None, privado=False):
        metodo = metodo.upper()
        caminho = endpoint
        if params:
            # Remove parâmetros None
            params = {k: v for k, v in params.items() if v is not None}
            if params:
                caminho += "?" + urllib.parse.urlencode(params)

        corpo = json.dumps(body) if body is not None else ""

        headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
        if self.demo:
            headers["x-simulated-trading"] = "1"

        if privado:
            if not (self.api_key and self.api_secret and self.passphrase):
                raise OKXError("Credenciais não configuradas.")
            ts = self._timestamp()
            headers.update({
                "OK-ACCESS-KEY": self.api_key,
                "OK-ACCESS-SIGN": self._assinar(ts, metodo, caminho, corpo),
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": self.passphrase,
            })

        req = urllib.request.Request(
            self.base_url + caminho,
            data=corpo.encode() if corpo else None,
            headers=headers,
            method=metodo,
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                dados = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            detalhe = e.read().decode(errors="replace")
            raise OKXError(f"HTTP {e.code}: {detalhe}") from None
        except urllib.error.URLError as e:
            raise OKXError(f"Erro de conexão: {e.reason}") from None

        if dados.get("code") != "0":
            raise OKXError(f"Erro OKX {dados.get('code')}: {dados.get('msg')} "
                           f"| data={dados.get('data')}")
        return dados["data"]

    # ---------- dados de mercado (públicos) ----------

    def ticker(self, inst_id):
        return self._request("GET", "/api/v5/market/ticker",
                             {"instId": inst_id})[0]

    def candles(self, inst_id, bar="1H", limit=100):
        """Retorna listas: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]"""
        return self._request("GET", "/api/v5/market/candles",
                             {"instId": inst_id, "bar": bar, "limit": limit})

    def orderbook(self, inst_id, sz=20):
        return self._request("GET", "/api/v5/market/books",
                             {"instId": inst_id, "sz": sz})[0]

    # ---------- conta (privado) ----------

    def saldo(self, ccy=None):
        return self._request("GET", "/api/v5/account/balance",
                             {"ccy": ccy}, privado=True)

    def posicoes(self, inst_type=None):
        return self._request("GET", "/api/v5/account/positions",
                             {"instType": inst_type}, privado=True)

    # ---------- trading (privado) ----------

    def criar_ordem(self, inst_id, side, sz, ord_type="limit", px=None,
                    td_mode="cash", **extras):
        """
        side: 'buy' ou 'sell'
        ord_type: 'limit', 'market', 'post_only', 'ioc', 'fok'
        td_mode: 'cash' (spot), 'cross' ou 'isolated' (margem/derivativos)
        """
        body = {"instId": inst_id, "tdMode": td_mode, "side": side,
                "ordType": ord_type, "sz": str(sz)}
        if px is not None:
            body["px"] = str(px)
        body.update(extras)
        return self._request("POST", "/api/v5/trade/order",
                             body=body, privado=True)[0]

    def cancelar_ordem(self, inst_id, ord_id):
        return self._request("POST", "/api/v5/trade/cancel-order",
                             body={"instId": inst_id, "ordId": ord_id},
                             privado=True)[0]

    def ordens_abertas(self, inst_type=None, inst_id=None):
        """inst_type: 'SPOT', 'SWAP', 'FUTURES', 'MARGIN', 'OPTION'"""
        return self._request("GET", "/api/v5/trade/orders-pending",
                             {"instType": inst_type, "instId": inst_id},
                             privado=True)

    def consultar_ordem(self, inst_id, ord_id):
        return self._request("GET", "/api/v5/trade/order",
                             {"instId": inst_id, "ordId": ord_id},
                             privado=True)[0]

    def instrumento(self, inst_type, inst_id):
        """Informações do contrato, incluindo o tamanho (ctVal)."""
        return self._request("GET", "/api/v5/public/instruments",
                             {"instType": inst_type, "instId": inst_id})[0]

    def taxas(self, inst_type="SWAP"):
        """Suas taxas de maker/taker para o tipo de instrumento."""
        return self._request("GET", "/api/v5/account/trade-fee",
                             {"instType": inst_type}, privado=True)

# ---------- exemplo de uso ----------

def analisar_posicoes(client, cenarios=(-20, -10, -5, 5, 10, 20)):
    posicoes = client.posicoes()
    if not posicoes:
        print("\nNenhuma posição aberta.")
        return

    # Taxa taker real da sua conta (com valor padrão se falhar)
    try:
        t = client.taxas("SWAP")[0]
        taker = abs(float(t.get("takerU") or t.get("taker")))
    except (OKXError, ValueError, TypeError, IndexError):
        taker = 0.0005

    patrimonio = float(client.saldo()[0]["totalEq"])

    # Agrupa as posições por par
    pares, cache = {}, {}
    for p in posicoes:
        inst = p["instId"]
        qtd = float(p["pos"])
        if qtd == 0:
            continue
        if inst not in cache:
            cache[inst] = client.instrumento(p["instType"], inst)
        info = cache[inst]

        mark = float(p["markPx"])
        ct = float(info["ctVal"]) * float(info.get("ctMult") or 1)
        contratos = abs(qtd)
        if info.get("ctType") == "inverse":
            moedas = contratos * ct / mark
        else:
            moedas = contratos * ct

        if p["posSide"] == "net":
            lado = "long" if qtd > 0 else "short"
        else:
            lado = p["posSide"]

        d = pares.setdefault(inst, {
            "mark": mark, "long": 0.0, "short": 0.0,
            "long_ctr": 0.0, "short_ctr": 0.0,
            "m_long": 0.0, "m_short": 0.0, "pnl": 0.0,
        })
        d[lado] += moedas
        d[lado + "_ctr"] += contratos
        d["m_" + lado] += float(p["imr"] or p["margin"] or 0)
        d["pnl"] += float(p["upl"] or 0)

    # Calcula métricas por par
    linhas = []
    for inst, d in pares.items():
        liquido = d["long"] - d["short"]          # >0 = long, <0 = short
        exposicao = liquido * d["mark"]
        casado = min(d["long"], d["short"])        # parte que se anula
        margem_lib = 0.0
        if d["long"]:
            margem_lib += d["m_long"] * casado / d["long"]
        if d["short"]:
            margem_lib += d["m_short"] * casado / d["short"]
        taxa_fech = casado * d["mark"] * 2 * taker
        linhas.append((inst, d, liquido, exposicao, casado, margem_lib, taxa_fech))

    linhas.sort(key=lambda x: abs(x[3]), reverse=True)

    print("\n" + "=" * 70)
    print(f"ANÁLISE DE POSIÇÕES   (patrimônio: {patrimonio:.2f} USDT, "
          f"taxa taker: {taker * 100:.3f}%)")
    print("=" * 70)

    tot = {"pnl": 0.0, "expo": 0.0, "bruta": 0.0, "lib": 0.0, "taxa": 0.0}
    for inst, d, liquido, expo, casado, lib, taxa in linhas:
        moeda = inst.split("-")[0]
        if abs(liquido) < 1e-12:
            direcao = "NEUTRO (hedge total)"
        else:
            direcao = f"{'LONG' if liquido > 0 else 'SHORT'} {abs(liquido):g} {moeda}"

        print(f"\n{inst}  (marca: {d['mark']})")
        print(f"  long: {d['long']:g} {moeda} ({d['long_ctr']:g} ctr)   "
              f"short: {d['short']:g} {moeda} ({d['short_ctr']:g} ctr)")
        print(f"  líquido: {direcao}   exposição: {abs(expo):.2f} USDT "
              f"({abs(expo) / patrimonio * 100:.1f}% do patrimônio)")
        print(f"  PnL somado: {d['pnl']:+.2f} USDT   impacto de ±10%: "
              f"±{abs(expo) * 0.10:.2f} USDT")
        if casado > 0:
            ctr_casados = min(d["long_ctr"], d["short_ctr"])
            print(f"  parte travada: {ctr_casados:g} ctr de cada lado -> "
                  f"libera {lib:.2f} USDT de margem, taxa aprox. {taxa:.2f} USDT")

        tot["pnl"] += d["pnl"]
        tot["expo"] += expo
        tot["bruta"] += abs(expo)
        tot["lib"] += lib
        tot["taxa"] += taxa

    print("\n" + "-" * 70)
    print(f"PnL total não realizado:      {tot['pnl']:+.2f} USDT")
    lado_total = "LONG" if tot["expo"] > 0 else "SHORT"
    print(f"Exposição líquida total:      {lado_total} {abs(tot['expo']):.2f} USDT "
          f"({abs(tot['expo']) / patrimonio:.2f}x o patrimônio)")
    print(f"Fechando todos os hedges:     libera {tot['lib']:.2f} USDT, "
          f"custo aprox. {tot['taxa']:.2f} USDT em taxas")

    # Cenários: todos os pares se movendo juntos na mesma porcentagem
    print("\nCenário (todos os pares movendo juntos):")
    for pct in cenarios:
        impacto = tot["expo"] * pct / 100
        print(f"  mercado {pct:+d}%  ->  {impacto:+9.2f} USDT   "
              f"patrimônio: {patrimonio + impacto:.2f}")
    print("=" * 70)

if __name__ == "__main__":
    carregar_env()

    client = OKXClient(
        api_key=os.getenv("OKX_API_KEY", ""),
        api_secret=os.getenv("OKX_API_SECRET", ""),
        passphrase=os.getenv("OKX_PASSPHRASE", ""),
        demo=os.getenv("OKX_DEMO", "1") == "1",
    )

    # Privado (precisa de chave)
    if client.api_key:
        conta = client.saldo()[0]
        print(f"\nPatrimônio total (USD): {conta['totalEq']}")
        for d in conta["details"]:
            if float(d["eq"] or 0) > 0:
                print(f"  {d['ccy']}: {d['eq']} (disponível: {d['availBal']})")

        for tipo in ("SWAP", "FUTURES"):
            ordens = client.ordens_abertas(inst_type=tipo)
            print(f"\nOrdens abertas ({tipo}): {len(ordens)}")
            for o in ordens:
                data = datetime.fromtimestamp(int(o["cTime"]) / 1000)
                print(f"  {o['instId']:<22} {o['side']:<4} {o['posSide']:<5} "
                      f"{o['ordType']:<10} preço: {o['px'] or 'mercado':<10} "
                      f"qtd: {o['sz']} (exec: {o['accFillSz']})  "
                      f"alav: {o['lever']}x  {data:%d/%m %H:%M}")

        posicoes = client.posicoes()
        print(f"\nPosições abertas: {len(posicoes)}")
        for p in posicoes:
            qtd = float(p["pos"])
            # Em modo "net" a direção vem do sinal da quantidade
            if p["posSide"] == "net":
                lado = "LONG" if qtd > 0 else "SHORT"
            else:
                lado = p["posSide"].upper()
            pnl = float(p["upl"] or 0)
            pnl_pct = float(p["uplRatio"] or 0) * 100
            print(f"  {p['instId']:<22} {lado:<5} {abs(qtd)} contratos  "
                  f"{p['lever']}x {p['mgnMode']}")
            print(f"    entrada: {p['avgPx']}  marca: {p['markPx']}  "
                  f"liquidação: {p['liqPx'] or '-'}")
            print(f"    margem: {float(p['imr'] or p['margin'] or 0):.2f} USDT  "
                  f"PnL: {pnl:+.2f} USDT ({pnl_pct:+.2f}%)")
    
    analisar_posicoes(client)