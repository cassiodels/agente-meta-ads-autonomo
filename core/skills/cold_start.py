"""
Skill: ColdStart (Autodetecção de Ativos e Setup Inicial da Conta).
Consulta a Meta API (zero tokens de IA) para extrair automaticamente
page_id, instagram_user_id, lead_gen_form_id, campanha e conjunto padrão.
"""
import json
import requests
from pathlib import Path
from typing import Any, Dict, List


class ColdStart:
    def __init__(self, access_token: str, ad_account_id: str, api_version: str = "v19.0"):
        self.access_token = access_token
        self.ad_account_id = ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"
        self.base_url = f"https://graph.facebook.com/{api_version}"

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        params["access_token"] = self.access_token
        resp = requests.get(f"{self.base_url}/{endpoint}", params=params, timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(f"Erro Meta API ({resp.status_code}): {resp.text[:300]}")
        return resp.json()

    def discover_assets(self) -> Dict[str, Any]:
        """Inspeciona campanhas, conjuntos e anúncios existentes para preencher ativos."""
        discovered = {
            "page_id": "",
            "instagram_user_id": "",
            "lead_gen_form_id": "",
            "default_campaign_id": "",
            "default_adset_id": "",
        }
        missing: List[str] = []

        # 1. Buscar campanhas e conjuntos (preferindo ACTIVE)
        campaigns = self._get(f"{self.ad_account_id}/campaigns", {
            "fields": "id,name,objective,effective_status", "limit": 25
        }).get("data", [])
        adsets = self._get(f"{self.ad_account_id}/adsets", {
            "fields": "id,name,effective_status,campaign_id,promoted_object", "limit": 25
        }).get("data", [])

        active_adsets = [a for a in adsets if a.get("effective_status") == "ACTIVE"] or adsets
        if active_adsets:
            chosen_adset = active_adsets[0]
            discovered["default_adset_id"] = chosen_adset.get("id", "")
            discovered["default_campaign_id"] = chosen_adset.get("campaign_id", "")
            promoted = chosen_adset.get("promoted_object") or {}
            if promoted.get("page_id"):
                discovered["page_id"] = str(promoted["page_id"])
        elif campaigns:
            discovered["default_campaign_id"] = campaigns[0].get("id", "")

        # 2. Inspecionar criativos de anúncios existentes para achar IG e lead_gen_form_id
        ads = self._get(f"{self.ad_account_id}/ads", {
            "fields": "id,effective_status,creative{object_story_spec}", "limit": 25
        }).get("data", [])
        active_ads = [ad for ad in ads if ad.get("effective_status") == "ACTIVE"] or ads

        for ad in active_ads:
            spec = (ad.get("creative") or {}).get("object_story_spec") or {}
            if not discovered["page_id"] and spec.get("page_id"):
                discovered["page_id"] = str(spec["page_id"])
            if not discovered["instagram_user_id"] and spec.get("instagram_user_id"):
                discovered["instagram_user_id"] = str(spec["instagram_user_id"])

            for media_key in ("video_data", "link_data"):
                cta_val = (spec.get(media_key) or {}).get("call_to_action", {}).get("value", {})
                if not discovered["lead_gen_form_id"] and cta_val.get("lead_gen_form_id"):
                    discovered["lead_gen_form_id"] = str(cta_val["lead_gen_form_id"])

            if all(discovered.values()):
                break

        labels = {
            "page_id": "ID da Página do Facebook",
            "instagram_user_id": "ID da Conta do Instagram",
            "lead_gen_form_id": "ID do Formulário de Cadastro",
            "default_adset_id": "ID do Conjunto de Anúncios Padrão",
        }
        for key, label in labels.items():
            if not discovered[key]:
                missing.append(label)

        return {
            "is_virgin_account": len(campaigns) == 0 and len(ads) == 0,
            "discovered": discovered,
            "missing": missing,
        }

    def apply_to_config(self, config_path: Path) -> Dict[str, Any]:
        """Preenche apenas campos vazios no config.json sem sobrescrever edições manuais."""
        result = self.discover_assets()
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        assets = cfg.setdefault("meta_assets", {})
        updated_fields = []
        for k, v in result["discovered"].items():
            if v and not assets.get(k):
                assets[k] = v
                updated_fields.append(k)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

        result["updated_fields"] = updated_fields
        return result
