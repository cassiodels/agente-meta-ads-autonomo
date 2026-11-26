"""
Skill 4: AudienceManager (Gestor de Públicos da Meta API).
Permite listar e criar Públicos Personalizados (Custom Audiences)
e Públicos Semelhantes (Lookalikes) para renovação de audiência.
"""
import requests
from typing import Dict, Any, List

class AudienceManager:
    def __init__(self, access_token: str, ad_account_id: str, api_version: str = "v19.0"):
        self.access_token = access_token
        self.ad_account_id = ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"
        self.base_url = f"https://graph.facebook.com/{api_version}"

    def get_custom_audiences(self) -> List[Dict[str, Any]]:
        """Lista os públicos já existentes na conta."""
        url = f"{self.base_url}/{self.ad_account_id}/customaudiences"
        params = {
            "access_token": self.access_token,
            "fields": "id,name,subtype,approximate_count_lower_bound,approximate_count_upper_bound"
        }
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        return data.get("data", [])

    def create_custom_audience(self, name: str, description: str = "") -> Dict[str, Any]:
        """Cria um novo público personalizado."""
        url = f"{self.base_url}/{self.ad_account_id}/customaudiences"
        payload = {
            "access_token": self.access_token,
            "name": name,
            "subtype": "CUSTOM",
            "description": description,
            "customer_file_source": "USER_PROVIDED_ONLY"
        }
        resp = requests.post(url, json=payload, timeout=15)
        return resp.json()
