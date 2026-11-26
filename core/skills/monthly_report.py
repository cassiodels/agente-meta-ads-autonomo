"""
Skill: MonthlyReport (Relatório Mensal Simplificado).
Coleta dados reais do mês em Python puro (0 tokens) e gera um resumo executivo
em linguagem simples para qualquer pessoa entender, salvando em reports/ e enviando no Telegram.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv

from core.meta_client import MetaClient
from core.memory_manager import MemoryManager
from core.model_manager import ModelManager, AIUnavailableError
from core.telegram_notifier import TelegramNotifier

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ACCOUNTS_DIR = BASE_DIR / "accounts"


def _extract_conversions(insights: Dict[str, Any]) -> int:
    total = 0
    for act in insights.get("actions", []):
        if act.get("action_type") in ("purchase", "lead", "contact"):
            total += int(act.get("value", 0))
    return total


def generate_monthly_report(account_folder: str, send_telegram: bool = True) -> Path:
    account_dir = ACCOUNTS_DIR / account_folder
    with open(account_dir / "config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    state = {}
    if (account_dir / "state.json").exists():
        with open(account_dir / "state.json", "r", encoding="utf-8") as f:
            state = json.load(f)

    account_name = cfg.get("account_name", account_folder)
    ad_account_id = cfg.get("meta_ad_account_id")
    monthly_max = float(cfg.get("budget", {}).get("monthly_max_brl", 0.0))

    meta = MetaClient(os.getenv("META_ACCESS_TOKEN", ""), ad_account_id)
    insights_list = meta.get_insights(date_preset="this_month")
    data = insights_list[0] if insights_list else {}

    spend = float(data.get("spend", 0.0))
    clicks = int(data.get("clicks", 0))
    impressions = int(data.get("impressions", 0))
    ctr = float(data.get("ctr", 0.0))
    conversions = _extract_conversions(data)
    cpa = (spend / conversions) if conversions > 0 else 0.0

    approved_count = len(state.get("approved_actions", []))
    rejected_count = len(state.get("rejected_actions", []))
    top_learnings = MemoryManager(account_dir / "memory.json").get_top_insights(limit=5)

    # Resumo executivo em linguagem simples (1 chamada leve opcional; fallback em Python)
    summary_text = ""
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        prompt = f"""
Escreva um resumo mensal curto (3 parágrafos simples, sem jargões técnicos difíceis) para o dono da empresa "{account_name}".
Dados do mês:
- Investido: R$ {spend:.2f} (teto combinado: R$ {monthly_max:.2f})
- Pessoas alcançadas/impressões: {impressions} | Cliques: {clicks} (CTR {ctr:.2f}%)
- Resultados (cadastros/leads): {conversions} (custo por resultado: R$ {cpa:.2f})
- Ações aprovadas pelo gestor: {approved_count} | Rejeitadas: {rejected_count}
- Principais aprendizados do agente: {top_learnings}

Responda em JSON: {{"resumo_simples": "...", "proximo_passo": "..."}}
"""
        try:
            ai_res = ModelManager(gemini_key).generate_json(prompt)
            summary_text = (
                f"{ai_res.get('resumo_simples', '')}\n\n"
                f"**Próximo passo recomendado:** {ai_res.get('proximo_passo', '')}"
            )
        except AIUnavailableError:
            summary_text = ""

    if not summary_text:
        summary_text = (
            f"Neste mês, investimos R$ {spend:.2f} dentro do limite de R$ {monthly_max:.2f}, "
            f"gerando {clicks} cliques e {conversions} cadastros (média de R$ {cpa:.2f} por cadastro). "
            f"Foram aprovadas {approved_count} ações e rejeitadas {rejected_count}."
        )

    month_tag = datetime.now().strftime("%Y_%m")
    reports_dir = account_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"relatorio_mensal_{month_tag}.md"

    learnings_md = "\n".join(f"- {item}" for item in top_learnings) or "- Nenhum aprendizado registrado ainda."
    report_md = (
        f"# Relatório Mensal — {account_name} ({month_tag})\n\n"
        f"## Resumo Executivo\n{summary_text}\n\n"
        f"## Números do Mês\n"
        f"- **Investimento:** R$ {spend:.2f} / R$ {monthly_max:.2f}\n"
        f"- **Impressões:** {impressions}\n"
        f"- **Cliques:** {clicks} (CTR: {ctr:.2f}%)\n"
        f"- **Resultados / Leads:** {conversions} (CPA médio: R$ {cpa:.2f})\n"
        f"- **Ações Aprovadas / Rejeitadas:** {approved_count} / {rejected_count}\n\n"
        f"## O que o Agente Aprendeu (Top Memória)\n{learnings_md}\n"
    )
    report_path.write_text(report_md, encoding="utf-8")

    if send_telegram:
        tg = TelegramNotifier(os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", ""))
        tg.send_message(
            f"📅 *Relatório Mensal — {account_name}*\n"
            f"• Investido: R$ {spend:.2f} / R$ {monthly_max:.2f}\n"
            f"• Cliques: {clicks} | Resultados: {conversions} (CPA: R$ {cpa:.2f})\n\n"
            f"{summary_text}"
        )
    return report_path


def run_all_monthly_reports():
    for folder in ACCOUNTS_DIR.iterdir():
        if folder.is_dir() and folder.name != "cliente_modelo" and (folder / "config.json").exists():
            generate_monthly_report(folder.name)


if __name__ == "__main__":
    run_all_monthly_reports()
