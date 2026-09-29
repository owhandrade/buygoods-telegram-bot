"""
Bot Telegram - Notificador de Vendas BuyGoods
Versão Railway (24/7) - usa variáveis de ambiente
"""

from flask import Flask, request, jsonify
import requests
import os
import hmac
from html import escape
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# ========== CONFIGURAÇÕES VIA VARIÁVEIS DE AMBIENTE ==========
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "minha_chave_secreta_123")
HW_WEBHOOK_TOKEN = os.environ.get("HW_WEBHOOK_TOKEN", "")
# ==============================================================

BRT = timezone(timedelta(hours=-3))  # horário de Brasília (sem horário de verão)


def send_telegram_message(text: str):
    """Envia mensagem para o Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao enviar mensagem Telegram: {e}")
        return False


@app.route("/webhook/buygoods", methods=["GET", "POST"])
def buygoods_webhook():
    """
    Endpoint que recebe o postback da BuyGoods.
    Funciona tanto com GET (query params) quanto POST (form/json).
    """

    # Pega os parâmetros (GET ou POST)
    if request.method == "POST":
        data = request.form.to_dict() or request.get_json(silent=True) or {}
    else:
        data = request.args.to_dict()

    # Log no terminal
    print(f"\n[{datetime.now()}] Postback recebido:")
    for k, v in data.items():
        print(f"  {k} = {v}")

    # Validação opcional da chave secreta
    if data.get("secret") != SECRET_KEY:
        print("[AVISO] Chave secreta inválida ou ausente. Ignorando.")
        return jsonify({"status": "unauthorized"}), 401

    # Extrai os dados do postback
    order_id = data.get("order_id", "N/A")
    amount = data.get("amount", "N/A")
    conv_type = data.get("conv_type", "purchase")
    email_hash = data.get("email_hash", "N/A")
    subid = data.get("subid", "N/A")
    product = data.get("product", "N/A")

    # Define emoji e tipo baseado no evento
    if conv_type.lower() in ("refund", "chargeback"):
        emoji = "🔴"
        tipo = "REEMBOLSO"
    elif conv_type.lower() == "upsell":
        emoji = "💎"
        tipo = "UPSELL"
    else:
        emoji = "💰"
        tipo = "VENDA"

    # Monta a mensagem
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    message = (
        f"{emoji} <b>NOVA {tipo}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>Order:</b> {order_id}\n"
        f"💵 <b>Valor:</b> ${amount}\n"
        f"📦 <b>Produto:</b> {product}\n"
        f"🔄 <b>Tipo:</b> {conv_type}\n"
        f"🔗 <b>SubID:</b> {subid}\n"
        f"🕐 <b>Data:</b> {now}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    # Envia pro Telegram
    sent = send_telegram_message(message)

    if sent:
        print("[OK] Mensagem enviada com sucesso!")
        return jsonify({"status": "ok"}), 200
    else:
        return jsonify({"status": "error", "msg": "falha ao enviar"}), 500


# ================== H&W HUB (hwaffiliate.com) ==================

HW_EVENTS = {
    "ORDER_PAID": ("💰", "VENDA APROVADA"),
    "ORDER_UPSELL": ("💎", "UPSELL"),
    "ORDER_PENDING": ("⏳", "PEDIDO PENDENTE"),
    "ORDER_FAILED": ("❌", "PAGAMENTO RECUSADO"),
}


def _find(data, *keys):
    """Procura as chaves na ordem dada (em qualquer nível do JSON) e
    devolve o primeiro valor simples (texto/número) encontrado."""
    for key in keys:
        key = key.lower()
        queue = [data]
        while queue:
            cur = queue.pop(0)
            if isinstance(cur, dict):
                for k, v in cur.items():
                    if k.lower() == key and isinstance(v, (str, int, float)) and v != "":
                        return v
                queue.extend(v for v in cur.values() if isinstance(v, (dict, list)))
            elif isinstance(cur, list):
                queue.extend(cur)
    return None


def _hw_token_ok(data):
    """Aceita o token pela URL (?token=), cabeçalho ou corpo do webhook."""
    if not HW_WEBHOOK_TOKEN:
        return True
    auth = request.headers.get("Authorization", "")
    candidates = [
        request.args.get("token"),
        request.headers.get("X-Webhook-Token"),
        request.headers.get("X-Hub-Token"),
        request.headers.get("Token"),
        auth[7:] if auth.lower().startswith("bearer ") else auth,
        _find(data, "token", "webhook_token", "webhookToken"),
    ]
    return any(
        isinstance(c, str) and hmac.compare_digest(c, HW_WEBHOOK_TOKEN)
        for c in candidates
    )


def _get(d, *path):
    """Lê um caminho no JSON (ex.: _get(data, "order", "utm", "utm_campaign"))."""
    for p in path:
        if isinstance(d, dict):
            d = d.get(p)
        elif isinstance(d, list) and isinstance(p, int) and -len(d) <= p < len(d):
            d = d[p]
        else:
            return None
    return d


def _money(value, currency=""):
    if not isinstance(value, (int, float)):
        return None
    prefix = {"USD": "US$ ", "BRL": "R$ ", "EUR": "€ "}.get(str(currency).upper(), "")
    suffix = "" if prefix or not currency else f" {currency}"
    return f"{prefix}{value:,.2f}{suffix}"


@app.route("/webhook/hw", methods=["POST"])
def hw_webhook():
    """Endpoint que recebe os webhooks do H&W Hub."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}

    if not _hw_token_ok(data):
        print(f"[{datetime.now(BRT)}] [AVISO] Webhook H&W com token inválido ou ausente. Ignorando.")
        return jsonify({"status": "unauthorized"}), 401

    body = data.get("data") if isinstance(data.get("data"), dict) else data
    order = body.get("order") if isinstance(body.get("order"), dict) else body
    event = str(data.get("event") or _find(data, "event", "eventType", "event_type") or "")
    products = [p for p in (order.get("products") or []) if isinstance(p, dict)]
    commissions = [c for c in (body.get("commissions") or order.get("commissions") or []) if isinstance(c, dict)]
    currency = order.get("currency") or ""
    is_upsell = event.upper() == "ORDER_UPSELL" or any(p.get("isUpsell") for p in products)
    is_test = bool(order.get("isTest") or data.get("isTest"))

    # Log resumido (sem dados do cliente)
    order_ref = order.get("orderNumber") or order.get("id") or "N/A"
    print(f"[{datetime.now(BRT)}] Webhook H&W: event={event} pedido={order_ref} teste={is_test}")

    emoji, tipo = HW_EVENTS.get(event.upper(), ("🔔", event.upper() or "EVENTO H&W"))
    if is_upsell and event.upper() == "ORDER_PAID":
        emoji, tipo = HW_EVENTS["ORDER_UPSELL"]

    # Oferta: nome da oferta (se vier) ou nome dos produtos
    offer_names = [o.get("name") for o in (body.get("offers") or order.get("offers") or []) if isinstance(o, dict) and o.get("name")]
    product_names = [f"{p.get('name')}{' (upsell)' if p.get('isUpsell') else ''}" for p in products if p.get("name")]
    oferta = ", ".join(offer_names or product_names) or "N/A"

    # Valor da venda e sua comissão
    valor = _money(order.get("totalAmount") or order.get("total"), currency) or "N/A"
    if commissions:
        net = sum(c.get("netValue") or 0 for c in commissions)
        gross = sum(c.get("grossValue") or 0 for c in commissions)
        comissao = f"{_money(net, currency)} (bruto {_money(gross, currency)})"
        c0 = commissions[0]
        if c0.get("status") == "PENDING" and c0.get("daysToRelease") is not None:
            comissao += f"\n⏳ <b>Liberação:</b> em {c0['daysToRelease']} dias"
    else:
        ac = _get(products, 0, "affiliateCommission") or {}
        net = ac.get("valueNet") if isinstance(ac, dict) else None
        comissao = _money(net, currency) or _money(_get(body, "values", "totalNet"), currency) or "N/A"

    utm = order.get("utm") if isinstance(order.get("utm"), dict) else {}
    campanha = utm.get("utm_campaign") or "N/A"
    origem = " / ".join(x for x in (utm.get("utm_source"), utm.get("utm_medium")) if x) or "N/A"
    subid4 = _find(data, "subid4", "subId4") or "N/A"
    pais = (_get(order, "customer", "shippingAddress", "country")
            or _get(order, "customer", "billingAddress", "country") or "N/A")

    def h(val):
        return escape(str(val))

    now = datetime.now(BRT).strftime("%d/%m/%Y %H:%M:%S")
    message = (
        f"{'🧪 <b>[TESTE]</b> ' if is_test else ''}{emoji} <b>H&amp;W: {h(tipo)}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Oferta:</b> {h(oferta)}\n"
        f"🆔 <b>Pedido:</b> {h(order_ref)}\n"
        f"💵 <b>Valor:</b> {h(valor)}\n"
        f"🤑 <b>Comissão:</b> {comissao if commissions else h(comissao)}\n"
        f"📣 <b>Campanha:</b> {h(campanha)}\n"
        f"🎯 <b>Origem:</b> {h(origem)}\n"
        f"🔗 <b>SubID4:</b> {h(subid4)}\n"
        f"🌎 <b>País:</b> {h(pais)}\n"
        f"🕐 <b>Data:</b> {now}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    if send_telegram_message(message):
        print("[OK] Mensagem H&W enviada com sucesso!")
        return jsonify({"status": "ok"}), 200
    return jsonify({"status": "error", "msg": "falha ao enviar"}), 500


@app.route("/health", methods=["GET"])
def health():
    """Endpoint pra verificar se o servidor está rodando."""
    return jsonify({"status": "online", "time": datetime.now().isoformat()}), 200


@app.route("/", methods=["GET"])
def home():
    """Página inicial."""
    return jsonify({"app": "BuyGoods Telegram Bot", "status": "running"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("🤖 Bot BuyGoods → Telegram rodando!")
    print(f"   Porta: {port}")
    print("=" * 50)
    app.run(host="0.0.0.0", port=port)
