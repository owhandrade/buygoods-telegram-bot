"""
Bot Telegram - Notificador de Vendas BuyGoods
Versão Railway (24/7) - usa variáveis de ambiente
"""

from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime

app = Flask(__name__)

# ========== CONFIGURAÇÕES VIA VARIÁVEIS DE AMBIENTE ==========
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "minha_chave_secreta_123")
# ==============================================================


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
