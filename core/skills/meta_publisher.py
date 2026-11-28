"""
Skill: MetaPublisher (Operador Seguro em 2 Etapas com Hard Stop Orçamentário Global).
- Suporta anúncios de IMAGEM e VÍDEO (1º frame como capa).
- Valida o teto global consolidado da conta (gasto do mês + comprometido ativo CBO/ABO) antes de criar ou ativar.
- Trata subcódigo 1885183 (App em Modo de Desenvolvimento) com mensagem explicativa.
"""
import json
import requests
from pathlib import Path
from typing import Any, Dict

from core.meta_client import MetaClient, MetaTokenExpiredError
from core.rules_engine import RulesEngine
from core.video_utils import is_video_file, extract_video_frames


CTA_MAP = {
    "CADASTRAR_SE": "APPLY_NOW",
    "GARANTIR_VAGA": "APPLY_NOW",
    "SAIR_NA_FRENTE": "APPLY_NOW",
    "APPLY_NOW": "APPLY_NOW",
    "SAIBA_MAIS": "LEARN_MORE",
    "LEARN_MORE": "LEARN_MORE",
    "ENVIAR_MENSAGEM": "SEND_WHATSAPP_MESSAGE",
    "SEND_WHATSAPP_MESSAGE": "SEND_WHATSAPP_MESSAGE",
    "COMPRAR_AGORA": "SHOP_NOW",
    "SHOP_NOW": "SHOP_NOW",
}

OPTIMIZATION_BY_OBJECTIVE = {
    "OUTCOME_LEADS": "LEAD_GENERATION",
    "OUTCOME_TRAFFIC": "LINK_CLICKS",
    "OUTCOME_ENGAGEMENT": "CONVERSATIONS",
    "OUTCOME_SALES": "OFFSITE_CONVERSIONS",
}


class MetaPublisher:
    def __init__(self, access_token: str, config: Dict[str, Any], api_version: str = "v19.0"):
        self.access_token = access_token
        self.config = config
        ad_id = config.get("meta_ad_account_id", "")
        self.ad_account_id = ad_id if ad_id.startswith("act_") else f"act_{ad_id}"
        self.base_url = f"https://graph.facebook.com/{api_version}"
        self.assets = config.get("meta_assets", {})

    def _post(self, endpoint: str, payload: Dict[str, Any] = None, files=None, timeout: int = 30) -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint}"
        data = dict(payload or {})
        data["access_token"] = self.access_token
        if files:
            resp = requests.post(url, data=data, files=files, timeout=timeout)
        else:
            resp = requests.post(url, data=data, timeout=timeout)
        body = resp.json()
        if resp.status_code != 200 or "error" in body:
            err = body.get("error", body)
            if isinstance(err, dict):
                if err.get("code") == 190:
                    raise MetaTokenExpiredError(err.get("message", "Token da Meta expirado."))
                if err.get("error_subcode") == 1885183:
                    raise RuntimeError(
                        "App Meta em Modo de Desenvolvimento (erro 1885183): "
                        "acesse developers.facebook.com -> Configurações -> Básico, preencha a URL de Política de Privacidade "
                        "e alterne o App para Modo Público (Live) para conseguir criar anúncios."
                    )
            raise RuntimeError(f"Erro Meta API ({resp.status_code}): {err}")
        return body

    def get_consolidated_budget_status(self) -> Dict[str, Any]:
        """Consulta a Meta API e calcula o orçamento consolidado global da conta."""
        meta = MetaClient(self.access_token, self.ad_account_id)
        ins_month = meta.get_insights(date_preset="this_month")
        ins_today = meta.get_insights(date_preset="today")
        campaigns = meta.get_campaigns()
        adsets = meta.get_adsets()

        month_spend = float(ins_month[0].get("spend", 0.0)) if ins_month else 0.0
        today_spend = float(ins_today[0].get("spend", 0.0)) if ins_today else 0.0
        return RulesEngine(self.config).evaluate_consolidated_account_budget(
            spent_this_month=month_spend,
            spent_today=today_spend,
            campaigns=campaigns,
            adsets=adsets,
        )

    def upload_image(self, image_path: Path) -> str:
        """Faz upload da imagem original para a biblioteca da conta e retorna o image_hash."""
        with open(image_path, "rb") as img_file:
            res = self._post(f"{self.ad_account_id}/adimages", files={"filename": img_file}, timeout=45)
        images = res.get("images", {})
        if not images:
            raise RuntimeError(f"Upload de imagem não retornou image_hash: {res}")
        first_key = next(iter(images))
        return images[first_key]["hash"]

    def upload_video(self, video_path: Path) -> str:
        """Faz upload de vídeo para a biblioteca da conta e retorna o video_id."""
        with open(video_path, "rb") as video_file:
            res = self._post(
                f"{self.ad_account_id}/advideos",
                payload={"title": video_path.stem},
                files={"source": video_file},
                timeout=120,
            )
        video_id = res.get("id")
        if not video_id:
            raise RuntimeError(f"Upload de vídeo não retornou id: {res}")
        return str(video_id)

    def create_paused_ad(self, media_path: Path, ad_proposal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Etapa 1: Cria o criativo (imagem ou vídeo com 1º frame como capa) e o anúncio como PAUSED.
        """
        page_id = self.assets.get("page_id")
        adset_id = self.assets.get("default_adset_id")
        form_id = self.assets.get("lead_gen_form_id")
        ig_id = self.assets.get("instagram_user_id")

        if not page_id or not adset_id:
            raise ValueError("page_id ou default_adset_id não configurados no Painel (Configurações).")

        defaults = self.config.get("campaign_defaults", {})
        objective = defaults.get("objective", "OUTCOME_LEADS")
        dest_url = defaults.get("destination_url") or "http://fb.me/"

        raw_cta = ad_proposal.get("call_to_action") or defaults.get("default_cta", "APPLY_NOW")
        cta_type = CTA_MAP.get(raw_cta, "APPLY_NOW")

        cta_value: Dict[str, Any] = {"link": dest_url}
        if objective == "OUTCOME_LEADS" and form_id:
            cta_value = {"lead_gen_form_id": form_id, "link": "http://fb.me/"}

        story_spec: Dict[str, Any] = {"page_id": page_id}
        if ig_id:
            story_spec["instagram_user_id"] = ig_id

        if is_video_file(media_path):
            thumb_path, _ = extract_video_frames(media_path)
            video_id = self.upload_video(media_path)
            image_hash = self.upload_image(thumb_path)
            story_spec["video_data"] = {
                "video_id": video_id,
                "image_hash": image_hash,
                "title": ad_proposal.get("headline", ""),
                "message": ad_proposal.get("primary_text", ""),
                "call_to_action": {"type": cta_type, "value": cta_value},
            }
            media_kind = "video"
        else:
            image_hash = self.upload_image(media_path)
            story_spec["link_data"] = {
                "image_hash": image_hash,
                "link": dest_url,
                "message": ad_proposal.get("primary_text", ""),
                "name": ad_proposal.get("headline", ""),
                "call_to_action": {"type": cta_type, "value": cta_value},
            }
            media_kind = "image"

        creative_name = f"AgenteIA - {media_path.stem}"
        creative_res = self._post(f"{self.ad_account_id}/adcreatives", {
            "name": creative_name,
            "object_story_spec": json.dumps(story_spec),
        })
        creative_id = creative_res["id"]

        ad_res = self._post(f"{self.ad_account_id}/ads", {
            "name": creative_name,
            "adset_id": adset_id,
            "creative": json.dumps({"creative_id": creative_id}),
            "status": "PAUSED",
        })

        return {
            "ad_id": ad_res["id"],
            "creative_id": creative_id,
            "image_hash": image_hash,
            "adset_id": adset_id,
            "media_type": media_kind,
            "status": "PAUSED",
        }

    def create_starter_campaign_and_adset(self, daily_budget_brl: float = None) -> Dict[str, Any]:
        """
        Para contas virgens (Cold Start): cria 1 Campanha + 1 Conjunto inicial PAUSED,
        validando antes contra a folga consolidada global da conta (Hard Stop).
        """
        budget_status = self.get_consolidated_budget_status()
        rules = RulesEngine(self.config)

        if budget_status["status"] in ("EXCEEDED", "PROJECTED_EXCEEDED"):
            raise RuntimeError(
                f"Criação bloqueada pelo Hard Stop global: {budget_status.get('alert')}"
            )

        safe_daily = (
            float(daily_budget_brl)
            if daily_budget_brl is not None
            else min(max(6.0, float(budget_status.get("available_daily_budget", 6.0))), 15.0)
        )
        commit_check = rules.can_commit_new_daily_budget(budget_status, safe_daily)
        if not commit_check["allowed"]:
            raise RuntimeError(commit_check["reason"])

        account_name = self.config.get("account_name", "Cliente")
        defaults = self.config.get("campaign_defaults", {})
        objective = defaults.get("objective", "OUTCOME_LEADS")
        daily_cents = int(round(safe_daily * 100))

        targeting_cfg = self.config.get("targeting", {})
        country = (targeting_cfg.get("country") or "BR").upper()
        age_min = int(targeting_cfg.get("age_min", 18))
        age_max = int(targeting_cfg.get("age_max", 55))
        gender_str = str(targeting_cfg.get("gender", "todos")).lower()

        targeting: Dict[str, Any] = {
            "geo_locations": {"countries": [country]},
            "age_min": age_min,
            "age_max": age_max,
        }
        if gender_str in ("masculino", "homens", "1"):
            targeting["genders"] = [1]
        elif gender_str in ("feminino", "mulheres", "2"):
            targeting["genders"] = [2]

        camp_res = self._post(f"{self.ad_account_id}/campaigns", {
            "name": f"[AgenteIA] {account_name} - Inicial",
            "objective": objective,
            "status": "PAUSED",
            "special_ad_categories": json.dumps([]),
        })
        campaign_id = camp_res["id"]

        adset_payload: Dict[str, Any] = {
            "name": f"[AgenteIA] Conjunto Inicial ({country} {age_min}-{age_max})",
            "campaign_id": campaign_id,
            "daily_budget": daily_cents,
            "billing_event": "IMPRESSIONS",
            "optimization_goal": OPTIMIZATION_BY_OBJECTIVE.get(objective, "LINK_CLICKS"),
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "targeting": json.dumps(targeting),
            "status": "PAUSED",
        }
        page_id = self.assets.get("page_id")
        if page_id:
            adset_payload["promoted_object"] = json.dumps({"page_id": page_id})

        adset_res = self._post(f"{self.ad_account_id}/adsets", adset_payload)
        return {
            "campaign_id": campaign_id,
            "adset_id": adset_res["id"],
            "daily_budget_brl": safe_daily,
            "objective": objective,
            "status": "PAUSED",
        }

    def pause_object(self, object_id: str) -> Dict[str, Any]:
        """Pausa um anúncio, conjunto ou campanha mediante aprovação."""
        self._post(object_id, {"status": "PAUSED"})
        return {"id": object_id, "status": "PAUSED"}

    def activate_object(
        self,
        object_id: str,
        object_type: str = "ad",
        new_daily_budget_brl: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Ativa anúncio, conjunto ou campanha após validar o orçamento consolidado global da conta.
        - Anúncio em conjunto já ativo não soma novo gasto diário, mas é bloqueado se a conta já estourou ou projeta estourar.
        - Conjunto/campanha valida também se o novo orçamento diário cabe na folga real até o fim do mês.
        """
        budget_status = self.get_consolidated_budget_status()
        rules = RulesEngine(self.config)

        if budget_status["status"] == "EXCEEDED":
            raise RuntimeError(
                f"Ativação bloqueada pelo Hard Stop: gasto no mês (R$ {budget_status['current_month_spend']:.2f}) "
                f"já atingiu o teto de R$ {budget_status['monthly_max']:.2f}."
            )

        if budget_status["status"] == "PROJECTED_EXCEEDED":
            raise RuntimeError(
                f"Ativação bloqueada pelo Hard Stop: os ativos atuais (R$ {budget_status['active_daily_total']:.2f}/dia) "
                f"já projetam R$ {budget_status['projected_month_total']:.2f} até o fim do mês "
                f"(acima do teto de R$ {budget_status['monthly_max']:.2f}). Reduza orçamentos antes de ativar."
            )

        if object_type in ("adset", "campaign") and new_daily_budget_brl > 0:
            check = rules.can_commit_new_daily_budget(budget_status, new_daily_budget_brl)
            if not check["allowed"]:
                raise RuntimeError(check["reason"])

        self._post(object_id, {"status": "ACTIVE"})
        return {"id": object_id, "ad_id": object_id, "status": "ACTIVE", "budget_health": budget_status}

    def activate_ad(self, ad_id: str) -> Dict[str, Any]:
        return self.activate_object(ad_id, object_type="ad")
