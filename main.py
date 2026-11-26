"""
Orquestrador Diário Unificado do Agente de IA Meta Ads.
Executa a auditoria consolidada via AgencyHub e envia:
1. Alerta imediato caso o token da Meta tenha expirado (erro 190).
2. Central Consolidada de Operações no Telegram (sem disparar imagens sem necessidade).
3. Briefings ou alertas críticos apenas quando o AdAuditor identificar necessidade real.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

from core.agency_hub import AgencyHub
from core.telegram_notifier import TelegramNotifier

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
ACCOUNTS_DIR = BASE_DIR / "accounts"


def run_daily_routine(send_telegram: bool = True):
    meta_token = os.getenv("META_ACCESS_TOKEN", "")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not meta_token or not tg_token or not tg_chat_id:
        print("❌ Variáveis de ambiente incompletas no .env")
        return

    hub = AgencyHub(accounts_dir=ACCOUNTS_DIR, meta_token=meta_token)
    notifier = TelegramNotifier(bot_token=tg_token, chat_id=tg_chat_id)

    print("📡 Auditando todas as contas configuradas...")
    overview = hub.scan_all_accounts_overview()
    if not overview:
        print("ℹ️ Nenhuma conta configurada em accounts/. Cadastre um cliente pelo Painel Web.")
        return

    menu = hub.format_central_menu(overview)
    print(menu["text"])

    if not send_telegram:
        return

    # 1. Alerta imediato de token expirado
    if any(item.get("token_expired") for item in overview):
        notifier.send_message(
            "🔑 *ALERTA CRÍTICO: Token da Meta expirado (erro 190)!*\n"
            "Abra o Painel Web (`app.py`) e atualize o `META_ACCESS_TOKEN` para retomar a gestão."
        )

    # 2. Central Consolidada
    notifier.send_message(menu["text"], reply_markup=menu["reply_markup"])

    # 3. Alertas proativos apenas quando o AdAuditor pedir ação urgente (Briefing ou Stop-Loss)
    for item in overview:
        pending = item.get("pending_action") or {}
        action = pending.get("action")
        if action == "BRIEFING_NOVO_CRIATIVO" and pending.get("briefing"):
            notifier.send_message(pending["briefing"])
        elif action == "PAUSAR_ANUNCIO":
            notifier.send_message(
                f"⚠️ *Stop-Loss — {item['account_name']}*\n"
                f"{pending.get('reason')}\n"
                f"👉 Acesse *{item['account_name']}* na Central acima para pausar com 1 clique."
            )
        elif action == "SUGERIR_ORCAMENTO":
            notifier.send_message(f"📈 *{item['account_name']}*\n{pending.get('reason')}")


if __name__ == "__main__":
    run_daily_routine()
