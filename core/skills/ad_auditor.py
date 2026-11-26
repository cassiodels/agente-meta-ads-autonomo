"""
Skill 1: AdAuditor (O Estrategista Crítico de Tráfego).
Analisa métricas reais da conta e de anúncios individuais e determina com precisão:
- COLD_START: conta sem campanhas cadastradas.
- PAUSAR_ANUNCIO: anúncio ativo gastando acima do aceitável (Stop-Loss).
- SOLICITAR_NOVO_CRIATIVO / BRIEFING_NOVO_CRIATIVO: saturação real (frequency).
- AJUSTAR_COPY: CTR baixo sem saturação severa.
- SUGERIR_ORCAMENTO: oportunidade de escala.
- MANTER: campanha saudável, sem intervenção necessária.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional


def _extract_conversions(insight_row: Dict[str, Any]) -> int:
    total = 0
    for act in insight_row.get("actions", []):
        if act.get("action_type") in ("purchase", "lead", "contact", "onsite_conversion.lead_grouped"):
            total += int(float(act.get("value", 0)))
    return total


class AdAuditor:
    def __init__(self, config: Dict[str, Any], memory: Dict[str, Any], folder_name: str = ""):
        self.config = config
        self.memory = memory
        self.folder_name = folder_name
        self.account_name = config.get("account_name", folder_name or "Cliente")
        self.guardrails = config.get("guardrails", {})
        self.max_cpa = float(self.guardrails.get("max_acceptable_cpa_brl", 10.0))

    def evaluate_account_strategy(
        self,
        insights_7d: Dict[str, Any],
        campaigns: List[Dict[str, Any]],
        available_assets: List[Path],
        ad_insights: Optional[List[Dict[str, Any]]] = None,
        active_ads: Optional[List[Dict[str, Any]]] = None,
        folder_name: str = "",
    ) -> Dict[str, Any]:
        folder = folder_name or self.folder_name

        # Regra 0: Cold Start (conta sem campanhas)
        if not campaigns:
            return {
                "action": "COLD_START",
                "reason": "Conta sem campanhas cadastradas. Podemos criar uma campanha e conjunto iniciais PAUSADOS para teste.",
                "briefing": None,
            }

        # Regra 1: Stop-Loss por anúncio individual ativo
        if ad_insights:
            active_ids = None
            if active_ads is not None:
                active_ids = {
                    ad.get("id") for ad in active_ads
                    if ad.get("effective_status") == "ACTIVE" or ad.get("status") == "ACTIVE"
                }

            for ad_row in ad_insights:
                ad_id = ad_row.get("ad_id", "")
                if active_ids is not None and ad_id not in active_ids:
                    continue
                ad_name = ad_row.get("ad_name", ad_id)
                ad_spend = float(ad_row.get("spend", 0.0))
                ad_conv = _extract_conversions(ad_row)

                if ad_conv == 0 and ad_spend >= (self.max_cpa * 1.5):
                    return {
                        "action": "PAUSAR_ANUNCIO",
                        "target_ad_id": ad_id,
                        "target_ad_name": ad_name,
                        "reason": (
                            f"Stop-Loss: o anúncio '{ad_name}' gastou R$ {ad_spend:.2f} nos últimos 7 dias "
                            f"sem nenhuma conversão (limite CPA: R$ {self.max_cpa:.2f})."
                        ),
                        "briefing": None,
                    }

                if ad_conv > 0:
                    ad_cpa = ad_spend / ad_conv
                    if ad_cpa > (self.max_cpa * 1.5) and ad_spend >= self.max_cpa:
                        return {
                            "action": "PAUSAR_ANUNCIO",
                            "target_ad_id": ad_id,
                            "target_ad_name": ad_name,
                            "reason": (
                                f"Stop-Loss: o anúncio '{ad_name}' está com CPA de R$ {ad_cpa:.2f} "
                                f"(acima do limite de R$ {self.max_cpa:.2f}) após gastar R$ {ad_spend:.2f}."
                            ),
                            "briefing": None,
                        }

        spend_7d = float(insights_7d.get("spend", 0.0))
        ctr = float(insights_7d.get("ctr", 0.0))
        frequency = float(insights_7d.get("frequency", 1.0))
        conversions = _extract_conversions(insights_7d)
        current_cpa = (spend_7d / conversions) if conversions > 0 else 0.0

        # Regra 2: Saturação Severa (frequência real da Meta API)
        if frequency > 2.8 and (current_cpa > self.max_cpa or (conversions == 0 and spend_7d >= self.max_cpa)):
            if available_assets:
                return {
                    "action": "SOLICITAR_NOVO_CRIATIVO",
                    "reason": (
                        f"Frequência real em {frequency:.2f} e CPA em R$ {current_cpa:.2f}. "
                        f"Recomendamos subir o novo criativo detectado para {self.account_name}."
                    ),
                    "briefing": None,
                }
            upload_hint = f"`accounts/{folder}/assets/`" if folder else "o painel"
            return {
                "action": "BRIEFING_NOVO_CRIATIVO",
                "reason": f"Saturação detectada em {self.account_name} (Frequência {frequency:.2f}), mas não há novos criativos na pasta.",
                "briefing": (
                    f"💡 *BRIEFING DE PRODUÇÃO DE NOVO CRIATIVO — {self.account_name}*\n"
                    f"• *Motivo:* Frequência atingiu {frequency:.2f} (público repetido) e performance caiu.\n"
                    f"• *Sugestão de formato:* Vídeo curto vertical (9:16, 15-20s) com gancho forte nos primeiros 3s, "
                    f"ou imagem estática com contraste diferente do anúncio atual.\n"
                    f"• *Alinhamento:* Siga o diferencial e público definidos na persona de {self.account_name}.\n"
                    f"👉 Envie o novo arquivo pelo Painel Web (aba Visão Geral & Criativos) ou salve em {upload_hint}."
                ),
            }

        # Regra 3: CTR baixo sem saturação severa (ajustar apenas copy)
        if 0 < ctr < 1.2 and conversions > 0 and current_cpa > (self.max_cpa * 0.8):
            return {
                "action": "AJUSTAR_COPY",
                "reason": f"CTR baixo ({ctr:.2f}%). Recomendamos renovar o título e texto do anúncio ativo para melhorar o gancho.",
                "briefing": None,
            }

        # Regra 4: Oportunidade de Escala de Orçamento
        monthly_max = float(self.config.get("budget", {}).get("monthly_max_brl", 200.0))
        if current_cpa > 0 and current_cpa < (self.max_cpa * 0.3) and conversions >= 15:
            suggested_increase = monthly_max + 100.0
            return {
                "action": "SUGERIR_ORCAMENTO",
                "reason": (
                    f"🚀 *Oportunidade de Escala Identificada!*\n"
                    f"O CPA atual está excelente (R$ {current_cpa:.2f}) com {conversions} conversões.\n"
                    f"Sugerimos aumentar o teto mensal de R$ {monthly_max:.2f} para R$ {suggested_increase:.2f}.\n"
                    f"👉 Para aplicar, abra o painel web e atualize o Teto Máximo Mensal."
                ),
                "briefing": None,
            }

        # Regra 5: Campanha saudável
        return {
            "action": "MANTER",
            "reason": f"Campanhas operando com métricas saudáveis (CPA: R$ {current_cpa:.2f} | CTR: {ctr:.2f}% | Freq: {frequency:.2f}).",
            "briefing": None,
        }
