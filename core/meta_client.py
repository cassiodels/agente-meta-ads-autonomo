"""
Cliente para interação com a Meta Marketing API (Graph API v19.0).
Extrai campanhas, conjuntos, anúncios e métricas reais (incluindo frequency, reach e nível de anúncio).
Detecta expiração do token (código 190) com exceção dedicada.
"""
import requests
from typing import Dict, Any, List, Optional


class MetaTokenExpiredError(RuntimeError):
    """Token de acesso da Meta expirado ou inválido (erro OAuth 190)."""


class MetaClient:
    def __init__(self, access_token: str, ad_account_id: str, api_version: str = "v19.0"):
        self.access_token = access_token
        self.ad_account_id = ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"
        self.base_url = f"https://graph.facebook.com/{api_version}"

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        req_params = dict(params or {})
        req_params["access_token"] = self.access_token
        url = f"{self.base_url}/{endpoint}"
        resp = requests.get(url, params=req_params, timeout=20)
        data = resp.json()
        if resp.status_code != 200 or "error" in data:
            err = data.get("error", {})
            if isinstance(err, dict) and err.get("code") == 190:
                raise MetaTokenExpiredError(err.get("message", "Token da Meta expirado."))
            raise RuntimeError(f"Erro Meta API ({resp.status_code}): {data}")
        return data

    def get_account_overview(self) -> Dict[str, Any]:
        """Retorna visão geral da conta: saldo, status, moeda e gasto total."""
        fields = "id,name,account_status,currency,amount_spent,balance"
        return self._get(self.ad_account_id, {"fields": fields})

    def get_campaigns(self, status_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Lista as campanhas da conta com status e orçamento."""
        fields = "id,name,status,effective_status,objective,daily_budget,lifetime_budget,created_time,updated_time"
        params: Dict[str, Any] = {"fields": fields, "limit": 50}
        if status_filter:
            params["filtering"] = [{"field": "effective_status", "operator": "IN", "value": status_filter}]
        return self._get(f"{self.ad_account_id}/campaigns", params).get("data", [])

    def get_adsets(self, campaign_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lista conjuntos de anúncios com informações de aprendizado e orçamento."""
        fields = "id,name,status,effective_status,daily_budget,lifetime_budget,learning_stage_info,created_time,updated_time"
        endpoint = f"{campaign_id}/adsets" if campaign_id else f"{self.ad_account_id}/adsets"
        return self._get(endpoint, {"fields": fields, "limit": 50}).get("data", [])

    def get_ads(self, adset_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lista anúncios individuais."""
        fields = "id,name,status,effective_status,adset_id,creative{id,name,title,body,image_url},created_time"
        endpoint = f"{adset_id}/ads" if adset_id else f"{self.ad_account_id}/ads"
        return self._get(endpoint, {"fields": fields, "limit": 50}).get("data", [])

    def get_insights(self, date_preset: str = "last_7d") -> List[Dict[str, Any]]:
        """Extrai métricas consolidadas da conta (com reach e frequency reais)."""
        fields = "spend,impressions,reach,frequency,clicks,cpc,ctr,actions,cost_per_action_type"
        params = {"fields": fields, "date_preset": date_preset, "level": "account"}
        return self._get(f"{self.ad_account_id}/insights", params).get("data", [])

    def get_campaign_insights(self, date_preset: str = "last_7d") -> List[Dict[str, Any]]:
        """Extrai métricas detalhadas a nível de campanha."""
        fields = "campaign_id,campaign_name,spend,impressions,reach,frequency,clicks,cpc,ctr,actions,cost_per_action_type"
        params = {"fields": fields, "date_preset": date_preset, "level": "campaign", "limit": 50}
        return self._get(f"{self.ad_account_id}/insights", params).get("data", [])

    def get_ad_insights(self, date_preset: str = "last_7d") -> List[Dict[str, Any]]:
        """Extrai métricas individuais por anúncio (permite identificar anúncios caros para Stop-Loss)."""
        fields = "ad_id,ad_name,adset_id,campaign_id,spend,impressions,reach,frequency,clicks,cpc,ctr,actions,cost_per_action_type"
        params = {"fields": fields, "date_preset": date_preset, "level": "ad", "limit": 50}
        return self._get(f"{self.ad_account_id}/insights", params).get("data", [])
