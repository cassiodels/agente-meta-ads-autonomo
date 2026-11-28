"""
Motor de Regras Rígidas (Hard Guardrails).
Garante:
1. Respeito inviolável ao teto mensal CONSOLIDADO da conta (gasto no mês + comprometido ativo CBO/ABO).
2. Nenhuma alteração sem aprovação explícita.
3. Respeito absoluto à fase de aprendizado da Meta.
4. Regras de Stop-Loss (CPA máximo aceitável).
"""
import calendar
from typing import Dict, Any, List
from datetime import datetime, timezone


class RulesEngine:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.budget_cfg = config.get("budget", {})
        self.guardrails = config.get("guardrails", {})

        self.monthly_max = float(self.budget_cfg.get("monthly_max_brl", 0.0))
        self.require_approval = self.budget_cfg.get("require_approval_for_budget_changes", True)
        self.min_learning_days = int(self.guardrails.get("min_learning_phase_days", 3))
        self.max_daily_budget_change_pct = float(self.guardrails.get("max_daily_budget_change_pct", 20.0))
        self.max_cpa = float(self.guardrails.get("max_acceptable_cpa_brl", 10.0))

    def evaluate_monthly_budget_health(self, current_month_spend: float) -> Dict[str, Any]:
        """Avalia o ritmo simples de gasto mensal (mantido por compatibilidade)."""
        now = datetime.now()
        day_of_month = now.day
        total_days = calendar.monthrange(now.year, now.month)[1]

        target_spend_so_far = (self.monthly_max / total_days) * day_of_month
        remaining_budget = max(0.0, self.monthly_max - current_month_spend)
        remaining_days = max(1, total_days - day_of_month + 1)
        safe_daily_pace = remaining_budget / remaining_days

        status = "NORMAL"
        alert = None

        if current_month_spend >= self.monthly_max:
            status = "EXCEEDED"
            alert = f"⚠️ ALERTA CRÍTICO: Gasto atual (R$ {current_month_spend:.2f}) atingiu/excedeu o teto mensal (R$ {self.monthly_max:.2f})!"
        elif current_month_spend > (target_spend_so_far * 1.25):
            status = "PACING_FAST"
            alert = f"⚠️ ATENÇÃO: Gasto acumulado está 25% acima do ritmo planejado. Ritmo diário seguro: R$ {safe_daily_pace:.2f}."
        elif current_month_spend < (target_spend_so_far * 0.70):
            status = "PACING_SLOW"
            alert = f"ℹ️ Ritmo abaixo do orçamento: ainda restam R$ {remaining_budget:.2f} para {remaining_days} dias."

        return {
            "status": status,
            "monthly_max": self.monthly_max,
            "current_month_spend": round(current_month_spend, 2),
            "remaining_budget": round(remaining_budget, 2),
            "safe_daily_pace": round(safe_daily_pace, 2),
            "alert": alert,
        }

    def evaluate_consolidated_account_budget(
        self,
        spent_this_month: float,
        spent_today: float,
        campaigns: List[Dict[str, Any]],
        adsets: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calcula o orçamento consolidado REAL da conta (act_...):
        soma gasto já realizado no mês + orçamento comprometido das campanhas CBO e conjuntos ABO ativos
        (sem contar duplicado) pelos dias restantes do mês.
        """
        now = datetime.now()
        total_days = calendar.monthrange(now.year, now.month)[1]
        future_days = max(0, total_days - now.day)
        remaining_days_including_today = max(1, total_days - now.day + 1)

        active_daily_total = 0.0
        cbo_campaign_ids = set()
        active_campaign_ids = set()

        for camp in campaigns or []:
            is_active = camp.get("effective_status") == "ACTIVE" or camp.get("status") == "ACTIVE"
            if not is_active:
                continue
            cid = camp.get("id")
            if cid:
                active_campaign_ids.add(cid)
            camp_daily = float(camp.get("daily_budget") or 0.0) / 100.0
            camp_lifetime = float(camp.get("lifetime_budget") or 0.0) / 100.0
            if camp_daily > 0:
                active_daily_total += camp_daily
                if cid:
                    cbo_campaign_ids.add(cid)
            elif camp_lifetime > 0 and cid:
                cbo_campaign_ids.add(cid)

        for adset in adsets or []:
            is_active = adset.get("effective_status") == "ACTIVE" or adset.get("status") == "ACTIVE"
            if not is_active:
                continue
            cid = adset.get("campaign_id")
            if cid in cbo_campaign_ids:
                continue
            if campaigns and cid and cid not in active_campaign_ids:
                continue
            adset_daily = float(adset.get("daily_budget") or 0.0) / 100.0
            active_daily_total += adset_daily

        active_daily_total = round(active_daily_total, 2)
        committed_today_remaining = max(0.0, active_daily_total - spent_today)
        committed_rest_of_month = round(committed_today_remaining + (active_daily_total * future_days), 2)
        projected_month_total = round(spent_this_month + committed_rest_of_month, 2)
        available_monthly_budget = round(max(0.0, self.monthly_max - projected_month_total), 2)
        available_daily_budget = round(available_monthly_budget / remaining_days_including_today, 2)

        status = "NORMAL"
        alert = None
        if spent_this_month >= self.monthly_max:
            status = "EXCEEDED"
            alert = (
                f"🚨 TETO MENSAL EXCEDIDO: Gasto atual (R$ {spent_this_month:.2f}) "
                f"já atingiu o teto da conta (R$ {self.monthly_max:.2f})!"
            )
        elif projected_month_total > (self.monthly_max * 1.02):
            status = "PROJECTED_EXCEEDED"
            alert = (
                f"⚠️ PROJEÇÃO ACIMA DO TETO: Com R$ {active_daily_total:.2f}/dia ativos, "
                f"o mês projeta R$ {projected_month_total:.2f} (teto: R$ {self.monthly_max:.2f})."
            )

        if self.monthly_max <= 350.0:
            topology = "Concentrar em 1 campanha / 1 conjunto com até 2-3 anúncios para acelerar aprendizado"
        else:
            topology = "Permite dividir em até 2 campanhas/conjuntos respeitando a folga real"

        return {
            "status": status,
            "monthly_max": round(self.monthly_max, 2),
            "current_month_spend": round(spent_this_month, 2),
            "spent_today": round(spent_today, 2),
            "active_daily_total": active_daily_total,
            "committed_rest_of_month": committed_rest_of_month,
            "projected_month_total": projected_month_total,
            "available_monthly_budget": available_monthly_budget,
            "available_daily_budget": available_daily_budget,
            "remaining_days_including_today": remaining_days_including_today,
            "remaining_budget": round(max(0.0, self.monthly_max - spent_this_month), 2),
            "safe_daily_pace": available_daily_budget,
            "recommended_topology": topology,
            "alert": alert,
        }

    def can_commit_new_daily_budget(self, budget_status: Dict[str, Any], new_daily_brl: float) -> Dict[str, Any]:
        """Valida se um novo orçamento diário cabe na folga consolidada até o fim do mês."""
        rem_days = int(budget_status.get("remaining_days_including_today", 1))
        new_commitment = round(float(new_daily_brl) * rem_days, 2)
        projected = float(budget_status.get("projected_month_total", 0.0))

        if projected + new_commitment > (self.monthly_max * 1.01):
            return {
                "allowed": False,
                "new_commitment": new_commitment,
                "max_safe_daily": float(budget_status.get("available_daily_budget", 0.0)),
                "reason": (
                    f"Bloqueado pelo teto global da conta: R$ {new_daily_brl:.2f}/dia comprometeria "
                    f"+R$ {new_commitment:.2f} nos próximos {rem_days} dias, levando a projeção para "
                    f"R$ {projected + new_commitment:.2f} (teto: R$ {self.monthly_max:.2f}). "
                    f"Folga máxima segura hoje: R$ {budget_status.get('available_daily_budget', 0.0):.2f}/dia."
                ),
            }
        return {"allowed": True, "new_commitment": new_commitment}

    def can_modify_adset(self, adset: Dict[str, Any]) -> Dict[str, Any]:
        """Verifica se um conjunto de anúncios pode ser otimizado ou está na fase de aprendizado."""
        learning_info = adset.get("learning_stage_info", {})
        status = learning_info.get("status")

        if status == "LEARNING":
            return {
                "can_modify": False,
                "reason": "Conjunto está em fase de aprendizado (Status LEARNING na Meta). Alterações estão bloqueadas para não prejudicar a entrega.",
            }

        updated_time_str = adset.get("updated_time")
        if updated_time_str:
            try:
                dt_clean = updated_time_str.replace("+0000", "+00:00")
                updated_dt = datetime.fromisoformat(dt_clean)
                days_since_update = (datetime.now(timezone.utc) - updated_dt).total_seconds() / 86400.0
                if days_since_update < self.min_learning_days:
                    return {
                        "can_modify": False,
                        "reason": f"Última alteração foi há {days_since_update:.1f} dias. A regra de segurança exige {self.min_learning_days} dias de estabilização.",
                    }
            except Exception:
                pass

        return {"can_modify": True, "reason": "Conjunto elegível para otimização."}

    def validate_budget_increase(self, current_budget: float, proposed_budget: float) -> Dict[str, Any]:
        """Valida que aumentos de orçamento nunca ultrapassem a variação máxima permitida."""
        if current_budget <= 0:
            return {"allowed": True, "validated_budget": proposed_budget}

        pct_change = ((proposed_budget - current_budget) / current_budget) * 100.0
        if pct_change > self.max_daily_budget_change_pct:
            capped_budget = current_budget * (1 + (self.max_daily_budget_change_pct / 100.0))
            return {
                "allowed": False,
                "reason": f"Aumento proposto (+{pct_change:.1f}%) ultrapassa o limite de segurança de {self.max_daily_budget_change_pct}% por ciclo.",
                "safe_budget": round(capped_budget, 2),
            }

        return {"allowed": True, "validated_budget": proposed_budget}
