# OKX Monitor

Monitora suas posições abertas na OKX e manda um alerta no Telegram quando um par chega no **zero a zero** (resultado ≥ `LUCRO_MINIMO`, já descontando a taxa para fechar tudo a mercado).

**Só faz leitura:** não abre nem fecha nenhuma posição.

Usa apenas a biblioteca padrão do Python, então não precisa de `pip install`.

---

## 1. Pré-requisitos

- Python 3.10 ou mais novo (`python3 --version`)
- Conta na OKX
- Conta no Telegram

## 2. Criar a chave de API na OKX

1. Na OKX, vá em **Perfil → API → Criar chave de API V5**.
2. Permissão: marque **somente Leitura** (o monitor não precisa de Trade nem de Saque).
3. Defina uma **passphrase** e anote.
4. Guarde a **API Key**, a **Secret Key** e a **Passphrase**.

> Se você criar a chave na conta **demo** (Trading simulado), use `OKX_DEMO=1`. Para a conta real, use `OKX_DEMO=0`.

## 3. Criar o bot do Telegram

1. No Telegram, abra o [@BotFather](https://t.me/BotFather) e mande `/newbot`.
2. Escolha um nome e um usuário (precisa terminar com `bot`).
3. Copie o **token** que ele devolve (algo como `123456789:AAH...`). Esse é o `TELEGRAM_TOKEN`.
4. Abra uma conversa com o seu bot novo e mande qualquer mensagem (ex.: `oi`). **Sem isso o bot não consegue falar com você.**
5. Descubra o seu `chat_id` abrindo no navegador:

   ```
   https://api.telegram.org/bot<SEU_TOKEN>/getUpdates
   ```

   Procure por `"chat":{"id":123456789,...}`. Esse número é o `TELEGRAM_CHAT_ID`.

   > Para mandar para um grupo: adicione o bot ao grupo, mande uma mensagem no grupo e repita o passo acima. O id de grupo começa com `-`.

## 4. Configurar o `.env`

```bash
cp .env.example .env
```

Edite o `.env`:

| Variável | O que é | Padrão |
|---|---|---|
| `OKX_API_KEY` | API Key da OKX | — |
| `OKX_API_SECRET` | Secret Key da OKX | — |
| `OKX_PASSPHRASE` | Passphrase da chave | — |
| `OKX_DEMO` | `1` = conta demo, `0` = conta real | `0` |
| `TELEGRAM_TOKEN` | Token do bot (BotFather) | — |
| `TELEGRAM_CHAT_ID` | Seu chat id | — |
| `LUCRO_MINIMO` | Resultado mínimo (USDT) por par para disparar o alerta | `0.5` |
| `STATUS_HORAS` | De quantas em quantas horas mandar um resumo geral | `6` |
| `INTERVALO` | Segundos entre cada checagem | `60` |

O `.env` está no `.gitignore` — **nunca suba ele para o Git**.

---

## 5. Rodar localmente

### Testar a conexão com a OKX (opcional)

```bash
python3 okx_client.py
```

Mostra saldo, ordens abertas, posições e uma análise de exposição. Se aparecer erro de credencial aqui, corrija antes de seguir.

### Iniciar o monitor

```bash
python3 monitor.py
```

Você deve receber no Telegram:

```
🤖 Monitor iniciado. Checando a cada 60s, alerta a partir de +10.00 USDT por par.
```

No terminal aparece uma linha a cada checagem com o resultado de cada par. Para parar: `Ctrl+C`.

### Mensagens que o bot manda

- ✅ **chegou no zero a zero** — o par atingiu `LUCRO_MINIMO`.
- ↩️ **saiu da zona de zero a zero** — o resultado caiu 2 USDT abaixo do mínimo (o alerta é rearmado).
- 📊 **Status** — resumo de todos os pares a cada `STATUS_HORAS`.
- ⚠️ **Monitor com erro** — 5 falhas seguidas (API fora, chave inválida etc.).

> Rodando localmente, o monitor só funciona enquanto o computador estiver ligado e o terminal aberto. Para rodar 24h, faça o deploy na nuvem (abaixo).

### Rodar localmente com Docker (opcional)

```bash
docker build -t okx-monitor .
docker run --rm --env-file .env okx-monitor
```

---

## 6. Deploy na nuvem (Fly.io)

O projeto já tem `Dockerfile` e `fly.toml`. A região configurada é `gru` (São Paulo).

### 6.1 Instalar o `flyctl` e fazer login

```bash
curl -L https://fly.io/install.sh | sh
fly auth login
```

### 6.2 Criar o app

O nome do app precisa ser único no Fly. Se `okx-monitor-paulo` já estiver em uso, troque o `app = "..."` no `fly.toml`.

```bash
fly launch --no-deploy --copy-config
```

(Se perguntar se quer sobrescrever o `fly.toml`, responda **não**.)

### 6.3 Cadastrar as variáveis como secrets

O `.env` **não** vai para a imagem Docker. As credenciais são passadas como secrets do Fly:

```bash
fly secrets set \
  OKX_API_KEY="..." \
  OKX_API_SECRET="..." \
  OKX_PASSPHRASE="..." \
  OKX_DEMO="0" \
  TELEGRAM_TOKEN="..." \
  TELEGRAM_CHAT_ID="..." \
  LUCRO_MINIMO="10" \
  STATUS_HORAS="6"
```

Ou, mais rápido, importando direto do seu `.env`:

```bash
fly secrets import < .env
```

### 6.4 Subir

```bash
fly deploy
```

Garanta que só existe **uma** máquina rodando (senão você recebe alertas em dobro):

```bash
fly scale count 1
```

A mensagem "🤖 Monitor iniciado" deve chegar no Telegram.

### 6.5 Comandos úteis

```bash
fly logs                # acompanhar os logs em tempo real
fly status              # ver se a máquina está rodando
fly secrets list        # listar os secrets (sem mostrar valores)
fly machine restart     # reiniciar
fly scale count 0       # pausar o monitor
fly scale count 1       # religar
```

Mudou o código? Rode `fly deploy` de novo. Mudou só um secret? O `fly secrets set` já reinicia a máquina sozinho.

---

## 7. Problemas comuns

| Sintoma | Causa provável |
|---|---|
| Nenhuma mensagem no Telegram | Você não mandou mensagem para o bot antes, ou o `TELEGRAM_CHAT_ID` está errado. Veja os logs: aparece `falha ao enviar Telegram`. |
| `Erro OKX 50113` / `50111` / `50105` | API Key, secret ou passphrase errados. |
| `Erro OKX 50101` | Chave da conta demo usada com `OKX_DEMO=0` (ou o contrário). |
| `Erro OKX 50110` | A chave tem restrição de IP. No Fly o IP de saída muda; remova a restrição ou libere o IP. |
| Alertas duplicados | Mais de uma máquina no Fly. Rode `fly scale count 1`. |
