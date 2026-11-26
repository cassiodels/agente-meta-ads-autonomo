"""
Central de Gestão Multi-Cliente (Agency Hub).
Compila métricas reais de todas as contas (incluindo nível de anúncio, frequency e orçamento),
detecta token expirado (190) e gera a mensagem da Central de Operações para o Telegram.
"""
from pathlib import Path
from typing import Dict, Any, List
import json

from core.meta_client import MetaClient, MetaTokenExpiredError
from core.rules_engine import RulesEngine
from core.skills.ad_auditor import AdAuditor
from core.asset_manager import AssetManager


class AgencyHub:
    def __init__(self, accounts_dir: Path, meta_token: str):
        self.accounts_dir = accounts_dir
        self.meta_token = meta_token

    def scan_all_accounts_overview(self) -> List[Dict[str, Any]]:
        """Varre todas as contas ativas e gera diagnóstico crítico com métricas reais."""
        overview_list: List[Dict[str, Any]] = []

        for folder in sorted(self.accounts_dir.iterdir()):
            if not (folder.is_dir() and folder.name != "cliente_modelo"):
                continue
            config_file = folder / "config.json"
            if not config_file.exists():
                continue

            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            memory_file = folder / "memory.json"
            memory_data = json.loads(memory_file.read_text(encoding="utf-8")) if memory_file.exists() else {}

            account_name = cfg.get("account_name", folder.name)
            ad_account_id = cfg.get("meta_ad_account_id")

            auditor = AdAuditor(config=cfg, memory=memory_data, folder_name=folder.name)
            rules = RulesEngine(config=cfg)
            asset_mgr = AssetManager(account_dir=folder)
            new_assets = asset_mgr.scan_new_assets()

            spend_today = 0.0
            month_spend = 0.0
            budget_health = rules.evaluate_monthly_budget_health(0.0)
            pending_action = None
            status_icon = "🟢"
            token_expired = False

            try:
                meta = MetaClient(self.meta_token, ad_account_id)
                insights_today = meta.get_insights(date_preset="today")
                insights_month = meta.get_insights(date_preset="this_month")
                insights_7d = meta.get_insights(date_preset="last_7d")
                campaigns = meta.get_campaigns()
                ad_insights = meta.get_ad_insights(date_preset="last_7d")
                ads = meta.get_ads()

                if insights_today:
                    spend_today = float(insights_today[0].get("spend", 0.0))
                if insights_month:
                    month_spend = float(insights_month[0].get("spend", 0.0))
                budget_health = rules.evaluate_monthly_budget_health(month_spend)

                data_7d = insights_7d[0] if insights_7d else {}
                evaluation = auditor.evaluate_account_strategy(
                    insights_7d=data_7d,
                    campaigns=campaigns,
                    available_assets=new_assets,
                    ad_insights=ad_insights,
                    active_ads=ads,
                    folder_name=folder.name,
                )

                if budget_health["status"] == "EXCEEDED":
                    status_icon = "🚨"
                    pending_action = {
                        "action": "ORCAMENTO_EXCEDIDO",
                        "reason": budget_health["alert"],
                        "briefing": None,
                    }
                elif evaluation["action"] != "MANTER":
                    status_icon = "⚠️"
                    pending_action = evaluation

            except MetaTokenExpiredError as e:
                status_icon = "🔑"
                token_expired = True
                pending_action = {"action": "TOKEN_EXPIRADO", "reason": str(e)}
            except Exception as e:
                status_icon = "❌"
                pending_action = {"action": "ERRO_CONEXAO", "reason": str(e)}

            overview_list.append({
                "folder_name": folder.name,
                "account_name": account_name,
                "status_icon": status_icon,
                "spend_today": spend_today,
                "month_spend": month_spend,
                "monthly_max": budget_health["monthly_max"],
                "budget_health": budget_health,
                "pending_action": pending_action,
                "available_assets_count": len(new_assets),
                "token_expired": token_expired,
            })

        return overview_list

    def format_central_menu(self, overview_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Formata o texto e os botões inline da Central de Operações."""
        lines = [
            "🏢 *CENTRAL DE OPERAÇÕES — AGÊNCIA META ADS*",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Contas Monitoradas: *{len(overview_list)}*",
            "",
        ]

        buttons = []
        for idx, item in enumerate(overview_list, 1):
            action_desc = "OK" if not item["pending_action"] else item["pending_action"]["action"]
            lines.append(
                f"{item['status_icon']} *{idx}. {item['account_name']}*\n"
                f"   • Hoje: R$ {item['spend_today']:.2f} | Mês: R$ {item['month_spend']:.2f}/R$ {item['monthly_max']:.2f}\n"
                f"   • Status: `{action_desc}` | Novos criativos: {item['available_assets_count']}"
            )
            buttons.append([
                {"text": f"Auditar {item['account_name']}", "callback_data": f"audit_{item['folder_name']}"}
            ])

        lines.append("\n👇 _Clique em uma conta abaixo para gerenciar ou aprovar ações:_")
        return {
            "text": "\n".join(lines),
            "reply_markup": {"inline_keyboard": buttons},
        }
