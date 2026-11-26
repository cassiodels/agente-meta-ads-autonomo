import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")
meta_token = os.getenv("META_ACCESS_TOKEN")
ad_account_id = sys.argv[1] if len(sys.argv) > 1 else os.getenv("META_AD_ACCOUNT_ID", "act_000000000000")

print("=" * 50)
print("1. TESTANDO DISPARO NO TELEGRAM...")
tg_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
tg_payload = {
    "chat_id": chat_id,
    "text": "🚀 *Agente Meta Ads Conectado com Sucesso!*\n\nBot integrado e pronto para operar.",
    "parse_mode": "Markdown",
}
try:
    tg_resp = requests.post(tg_url, json=tg_payload, timeout=10)
    if tg_resp.status_code == 200:
        print("✅ Telegram OK: Mensagem de teste enviada com sucesso!")
    else:
        print(f"❌ Erro Telegram ({tg_resp.status_code}): {tg_resp.text}")
except Exception as e:
    print(f"❌ Erro de conexão com Telegram: {e}")

print("\n" + "=" * 50)
print(f"2. TESTANDO LEITURA DA CONTA NA META ({ad_account_id})...")
meta_url = f"https://graph.facebook.com/v19.0/{ad_account_id}"
params = {
    "access_token": meta_token,
    "fields": "id,name,account_status,currency,amount_spent,balance",
}
try:
    meta_resp = requests.get(meta_url, params=params, timeout=10)
    meta_data = meta_resp.json()
    if meta_resp.status_code == 200:
        print("✅ Meta API OK: Conexão efetuada com sucesso!")
        print(f"   Nome da Conta: {meta_data.get('name')}")
        print(f"   ID: {meta_data.get('id')}")
        print(f"   Status da Conta: {meta_data.get('account_status')} (1 = Ativa)")
        print(f"   Moeda: {meta_data.get('currency')}")
    else:
        print(f"❌ Erro Meta API: {meta_data}")
except Exception as e:
    print(f"❌ Erro de conexão com Meta: {e}")
print("=" * 50)
