"""
Módulo de Notificação e Interação via Telegram.
Envia relatórios diários executivos e botões de ação para aprovação humana.
"""
import requests
from typing import Dict, Any, List, Optional

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"

    def send_message(self, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> bool:
        """Envia mensagem de texto com suporte a Markdown e botões inline opcionais."""
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        resp = requests.post(url, json=payload, timeout=15)
        return resp.status_code == 200

    def send_photo(self, photo_path: str, caption: str) -> bool:
        """Envia foto com legenda direta."""
        url = f"{self.api_url}/sendPhoto"
        with open(photo_path, "rb") as photo_file:
            resp = requests.post(
                url,
                data={"chat_id": self.chat_id, "caption": caption, "parse_mode": "Markdown"},
                files={"photo": photo_file},
                timeout=25
            )
        if resp.status_code != 200:
            # Fallback sem markdown na legenda
            with open(photo_path, "rb") as photo_file:
                resp = requests.post(
                    url,
                    data={"chat_id": self.chat_id, "caption": caption},
                    files={"photo": photo_file},
                    timeout=25
                )
        return resp.status_code == 200

    def send_ad_proposal(
        self,
        photo_path: str,
        account_name: str,
        ad_proposal: Dict[str, Any],
        asset_name: str
    ) -> bool:
        """
        Envia a proposta de anúncio de forma robusta e à prova de falhas:
        1. Envia a foto com uma legenda limpa (respeitando o limite estrito de 1024 chars do Telegram).
        2. Envia o texto completo da copy com os botões inline de aprovação.
        """
        import json

        # 1. Foto com resumo
        photo_caption = (
            f"💡 *NOVA SUGESTÃO DE CRIATIVO DETECTADA*\n"
            f"Conta: *{account_name}*\n"
            f"Arquivo: `{asset_name}`\n"
            f"Visão do Criativo: _{ad_proposal.get('visual_analysis', 'Imagem Gamer')[:200]}_\n"
            f"Compliance Meta: *✅ {ad_proposal.get('compliance_status', 'OK')}*"
        )
        self.send_photo(photo_path=photo_path, caption=photo_caption)

        # 2. Mensagem detalhada com a Copy e botões
        inline_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Aprovar e Publicar", "callback_data": f"approve_{asset_name}"},
                    {"text": "❌ Rejeitar", "callback_data": f"reject_{asset_name}"}
                ]
            ]
        }

        full_copy_text = (
            f"📝 *PROPOSTA DE COPY GERADA (GEMINI 3.8 FLASH)*\n"
            f"🎯 *Ângulo:* _{ad_proposal.get('angle', 'Oferta')}_\n\n"
            f"📌 *Título:* {ad_proposal.get('headline')}\n\n"
            f"📄 *Texto Principal:*\n{ad_proposal.get('primary_text')}\n\n"
            f"🔘 *Botão de Ação (CTA):* `{ad_proposal.get('call_to_action', 'CADASTRAR_SE')}`\n\n"
            f"⚠️ _Deseja aprovar e colocar este anúncio no ar?_"
        )

        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": full_copy_text,
            "parse_mode": "Markdown",
            "reply_markup": inline_keyboard
        }
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            # Fallback sem markdown caso haja caracteres especiais não escapados
            payload.pop("parse_mode", None)
            resp = requests.post(url, json=payload, timeout=15)

        return resp.status_code == 200

    def format_daily_report(
        self,
        account_name: str,
        budget_health: Dict[str, Any],
        insights_7d: Dict[str, Any],
        campaigns: List[Dict[str, Any]],
        recommendations: List[str]
    ) -> str:
        """Formata um relatório diário executivo e elegante para o Telegram."""
        spend_7d = float(insights_7d.get("spend", 0.0))
        impressions = int(insights_7d.get("impressions", 0))
        clicks = int(insights_7d.get("clicks", 0))
        ctr = float(insights_7d.get("ctr", 0.0))
        cpc = float(insights_7d.get("cpc", 0.0))

        # Conversões
        actions = insights_7d.get("actions", [])
        conversions = 0
        for act in actions:
            if act.get("action_type") in ["purchase", "lead", "contact"]:
                conversions += int(act.get("value", 0))

        cpa_text = f"R$ {spend_7d/conversions:.2f}" if conversions > 0 else "N/A"

        msg = []
        msg.append(f"📊 *Relatório Diário — {account_name}*")
        msg.append("━" * 28)

        # Saúde do Orçamento
        msg.append("💰 *Controle de Orçamento Mensal:*")
        msg.append(f"• Teto Mensal: *R$ {budget_health['monthly_max']:.2f}*")
        msg.append(f"• Gasto no Mês: *R$ {budget_health['current_month_spend']:.2f}*")
        msg.append(f"• Saldo Restante: *R$ {budget_health['remaining_budget']:.2f}*")
        msg.append(f"• Ritmo Diário Seguro: *R$ {budget_health['safe_daily_pace']:.2f}/dia*")

        if budget_health.get("alert"):
            msg.append(f"\n{budget_health['alert']}")

        msg.append("\n📈 *Performance (Últimos 7 dias):*")
        msg.append(f"• Investimento 7d: R$ {spend_7d:.2f}")
        msg.append(f"• Cliques no link: {clicks} (CTR: {ctr:.2f}%)")
        msg.append(f"• Custo por Clique (CPC): R$ {cpc:.2f}")
        msg.append(f"• Resultados/Conversões: {conversions} (CPA: {cpa_text})")

        msg.append("\n📌 *Status das Campanhas:*")
        if not campaigns:
            msg.append("• _Nenhuma campanha ativa no momento._")
        else:
            for camp in campaigns[:5]:
                status_icon = "🟢" if camp.get("status") == "ACTIVE" else "⏸️"
                msg.append(f"• {status_icon} *{camp.get('name')}* — Status: {camp.get('status')}")

        msg.append("\n🤖 *Ações Recomendadas pelo Agente:*")
        if not recommendations:
            msg.append("• ✅ Todas as campanhas operando dentro dos parâmetros de segurança. Nenhuma intervenção necessária hoje.")
        else:
            for idx, rec in enumerate(recommendations, 1):
                msg.append(f"{idx}. {rec}")

        msg.append("\n_Agente em modo Supervisionado (Human-in-the-Loop)_")
        return "\n".join(msg)
