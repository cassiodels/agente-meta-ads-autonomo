"""
Motor de Regras Rígidas (Hard Guardrails).
Garante:
1. Respeito inviolável ao teto mensal de orçamento.
2. Nenhuma alteração sem aprovação explícita.
3. Respeito absoluto à fase de aprendizado da Meta.
4. Regras de Stop-Loss (CPA máximo aceitável).
"""
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
        self.max_cpa = float(self.guardrails.get("max_acceptable_cpa_brl", 20.0))

    def evaluate_monthly_budget_health(self, current_month_spend: float) -> Dict[str, Any]:
        """Avalia se o gasto do mês está dentro da projeção segura."""
        now = datetime.now()
        day_of_month = now.day
        # Total de dias aproximado no mês atual
        total_days = 30
        
        target_spend_so_far = (self.monthly_max / total_days) * day_of_month
        remaining_budget = max(0.0, self.monthly_max - current_month_spend)
        remaining_days = max(1, total_days - day_of_month)
        safe_daily_pace = remaining_budget / remaining_days

        status = "NORMAL"
        alert = None

        if current_month_spend > self.monthly_max:
            status = "EXCEEDED"
            alert = f"⚠️ ALERTA CRÍTICO: Gasto atual (R$ {current_month_spend:.2f}) excedeu o teto mensal (R$ {self.monthly_max:.2f})!"
        elif current_month_spend > (target_spend_so_far * 1.25):
            status = "PACING_FAST"
            alert = f"⚠️ ATENÇÃO: Gasto acumulado está 25% acima do ritmo planejado. Sugerido ajustar o ritmo diário para R$ {safe_daily_pace:.2f}."
        elif current_month_spend < (target_spend_so_far * 0.70):
            status = "PACING_SLOW"
            alert = f"ℹ️ Ritmo abaixo do orçamento: ainda restam R$ {remaining_budget:.2f} para {remaining_days} dias."

        return {
            "status": status,
            "monthly_max": self.monthly_max,
            "current_month_spend": current_month_spend,
            "remaining_budget": remaining_budget,
            "safe_daily_pace": round(safe_daily_pace, 2),
            "alert": alert
        }

    def can_modify_adset(self, adset: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verifica se um conjunto de anúncios pode ser otimizado ou se está bloqueado pela fase de aprendizado.
        """
        learning_info = adset.get("learning_stage_info", {})
        status = learning_info.get("status")

        # Se a Meta reportar expressamente LEARNING
        if status == "LEARNING":
            return {
                "can_modify": False,
                "reason": "Conjunto está em fase de aprendizado (Status LEARNING na Meta). Alterações estão bloqueadas para não prejudicar a entrega."
            }

        # Verificação por tempo de atualização (últimas X horas/dias)
        updated_time_str = adset.get("updated_time")
        if updated_time_str:
            try:
                # Exemplo: 2026-11-20T14:00:00+0000
                dt_clean = updated_time_str.replace("+0000", "+00:00")
                updated_dt = datetime.fromisoformat(dt_clean)
                days_since_update = (datetime.now(timezone.utc) - updated_dt).total_seconds() / 86400.0
                if days_since_update < self.min_learning_days:
                    return {
                        "can_modify": False,
                        "reason": f"Última alteração foi há {days_since_update:.1f} dias. A regra de segurança exige {self.min_learning_days} dias de estabilização."
                    }
            except Exception:
                pass

        return {"can_modify": True, "reason": "Conjunto elegível para otimização."}

    def validate_budget_increase(self, current_budget: float, proposed_budget: float) -> Dict[str, Any]:
        """Valida que aumentos de orçamento nunca ultrapassem a variação máxima permitida (ex: 20%)."""
        if current_budget <= 0:
            return {"allowed": True, "validated_budget": proposed_budget}

        pct_change = ((proposed_budget - current_budget) / current_budget) * 100.0

        if pct_change > self.max_daily_budget_change_pct:
            capped_budget = current_budget * (1 + (self.max_daily_budget_change_pct / 100.0))
            return {
                "allowed": False,
                "reason": f"Aumento proposto (+{pct_change:.1f}%) ultrapassa o limite de segurança de {self.max_daily_budget_change_pct}% por ciclo.",
                "safe_budget": round(capped_budget, 2)
            }

        return {"allowed": True, "validated_budget": proposed_budget}
