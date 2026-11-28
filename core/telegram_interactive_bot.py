"""
Bot Interativo do Telegram com fila de navegação multi-cliente.
- Mostra orçamento consolidado real da conta (Teto, Gasto, Comprometido Ativo, Projeção e Folga).
- Escolhe autonomamente o melhor criativo do catálogo pré-analisado com base nos insights.
- Permite trocar o criativo escolhido (🔀 Trocar Criativo), ajustar copy (✏️ Ajustar) e publicar em 2 etapas (PAUSED -> ACTIVE).
Segurança: apenas o TELEGRAM_CHAT_ID autorizado é atendido.
"""
import os
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from core.agency_hub import AgencyHub
from core.asset_manager import AssetManager
from core.memory_manager import MemoryManager
from core.meta_client import MetaClient, MetaTokenExpiredError
from core.rules_engine import RulesEngine
from core.skills.ad_auditor import AdAuditor
from core.skills.copy_refiner import CopyRefiner, AIUnavailableError
from core.skills.compliance_guard import ComplianceGuard
from core.skills.meta_publisher import MetaPublisher
from core.video_utils import is_video_file, extract_video_frames

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = BASE_DIR / "accounts"


def _read_json(path: Path, default):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _write_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class TelegramInteractiveBot:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = str(os.getenv("TELEGRAM_CHAT_ID"))
        self.meta_token = os.getenv("META_ACCESS_TOKEN")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

        self.hub = AgencyHub(accounts_dir=ACCOUNTS_DIR, meta_token=self.meta_token)
        self.guard = ComplianceGuard()
        self.awaiting_feedback = None

    def _refresh_env_tokens(self):
        load_dotenv(override=True)
        self.meta_token = os.getenv("META_ACCESS_TOKEN")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.hub.meta_token = self.meta_token

    # ------------------------------------------------------------------ envio
    def _post(self, method: str, payload: dict, files=None):
        url = f"{self.api_url}/{method}"
        if files:
            return requests.post(url, data=payload, files=files, timeout=30)
        return requests.post(url, json=payload, timeout=20)

    def send_message(self, text: str, reply_markup: dict = None, markdown: bool = True):
        payload = {"chat_id": self.chat_id, "text": text}
        if markdown:
            payload["parse_mode"] = "Markdown"
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = self._post("sendMessage", payload)
        if resp.status_code != 200 and markdown:
            payload.pop("parse_mode", None)
            resp = self._post("sendMessage", payload)
        return resp

    def edit_message(self, message_id: int, text: str, reply_markup: dict = None):
        payload = {"chat_id": self.chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = self._post("editMessageText", payload)
        if resp.status_code != 200:
            payload.pop("parse_mode", None)
            self._post("editMessageText", payload)

    def send_photo(self, photo_path: Path, caption: str):
        with open(photo_path, "rb") as f:
            self._post("sendPhoto", {"chat_id": self.chat_id, "caption": caption[:1000]}, files={"photo": f})

    def answer_callback(self, callback_id: str, text: str = ""):
        self._post("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})

    # ------------------------------------------------------------------ telas
    def send_hub_menu(self):
        self._refresh_env_tokens()
        overview = self.hub.scan_all_accounts_overview()
        if any(item.get("token_expired") for item in overview):
            self.send_message(
                "🔑 *ALERTA: Token da Meta expirado (erro 190)!*\n"
                "Atualize o `META_ACCESS_TOKEN` no Painel Web (`app.py`) para retomar o monitoramento.",
                markdown=True,
            )
        menu = self.hub.format_central_menu(overview)
        self.send_message(menu["text"], menu["reply_markup"])

    def _collect_account_diagnosis(self, folder: str, cfg: dict, new_assets: list) -> dict:
        memory = MemoryManager(ACCOUNTS_DIR / folder / "memory.json").load()
        auditor = AdAuditor(cfg, memory, folder_name=folder)
        rules = RulesEngine(cfg)
        meta = MetaClient(self.meta_token, cfg.get("meta_ad_account_id", ""))

        insights_7d = meta.get_insights("last_7d")
        insights_month = meta.get_insights("this_month")
        insights_today = meta.get_insights("today")
        campaigns = meta.get_campaigns()
        adsets = meta.get_adsets()
        ad_insights = meta.get_ad_insights("last_7d")
        ads = meta.get_ads()

        month_spend = float(insights_month[0].get("spend", 0.0)) if insights_month else 0.0
        today_spend = float(insights_today[0].get("spend", 0.0)) if insights_today else 0.0
        budget_status = rules.evaluate_consolidated_account_budget(month_spend, today_spend, campaigns, adsets)

        diag = auditor.evaluate_account_strategy(
            insights_7d=insights_7d[0] if insights_7d else {},
            campaigns=campaigns,
            available_assets=new_assets,
            ad_insights=ad_insights,
            active_ads=ads,
            folder_name=folder,
        )
        return {"diag": diag, "budget": budget_status}

    def show_account(self, folder: str, message_id: int = None):
        self._refresh_env_tokens()
        account_dir = ACCOUNTS_DIR / folder
        cfg = _read_json(account_dir / "config.json", {})
        state = _read_json(account_dir / "state.json", {})
        asset_mgr = AssetManager(account_dir)
        new_assets = asset_mgr.scan_new_assets()
        cataloged = asset_mgr.get_available_cataloged_entries()
        default_adset = (cfg.get("meta_assets") or {}).get("default_adset_id", "")

        lines = [
            f"📂 *{cfg.get('account_name', folder)}*",
            "━━━━━━━━━━━━━━━━━━━━",
            f"• Criativos disponíveis: {len(new_assets)} ({len(cataloged)} catalogados com IA)",
        ]
        buttons = []

        try:
            info = self._collect_account_diagnosis(folder, cfg, new_assets)
            b = info["budget"]
            diag = info["diag"]
            lines.extend([
                f"💰 *Orçamento Consolidado da Conta:*",
                f"   • Teto Mensal: R$ {b['monthly_max']:.2f} | Gasto Mês: R$ {b['current_month_spend']:.2f}",
                f"   • Ativos Hoje: R$ {b['active_daily_total']:.2f}/dia | Projeção Mês: R$ {b['projected_month_total']:.2f}",
                f"   • Folga Real: *R$ {b['available_monthly_budget']:.2f}* (até R$ {b['available_daily_budget']:.2f}/dia)",
                f"   • Topologia: _{b['recommended_topology']}_",
                "",
                f"🧠 *Diagnóstico:* `{diag['action']}`",
                f"   • {diag.get('reason', '')}",
            ])
            if b.get("alert"):
                lines.append(f"\n{b['alert']}")
            if diag.get("briefing"):
                lines.append(f"\n{diag['briefing']}")
            if diag["action"] == "PAUSAR_ANUNCIO" and diag.get("target_ad_id"):
                buttons.append([{
                    "text": f"⏸️ Pausar Anúncio: {diag.get('target_ad_name', '')[:25]}",
                    "callback_data": f"pausead|{folder}|{diag['target_ad_id']}",
                }])
            if diag["action"] == "COLD_START" or not default_adset:
                buttons.append([{
                    "text": "🏗️ Criar Campanha/Conjunto Inicial (PAUSED)",
                    "callback_data": f"initcamp|{folder}",
                }])
        except MetaTokenExpiredError:
            lines.append("🔑 *Token da Meta expirado!* Atualize no Painel Web.")
        except Exception as e:
            lines.append(f"⚠️ Erro ao consultar conta: {str(e)[:140]}")

        if state.get("pending_proposal"):
            lines.append("\n⏳ Há uma proposta aguardando sua decisão.")
            buttons.append([{"text": "📝 Rever proposta pendente", "callback_data": f"review_{folder}"}])
        if state.get("paused_pending_activation"):
            buttons.append([{"text": "🚀 Ativar anúncio pausado pendente", "callback_data": f"activate_{folder}"}])
        if new_assets:
            buttons.append([{"text": "✨ Sugerir Melhor Criativo e Gerar Copy", "callback_data": f"generate_{folder}"}])
        buttons.append([{"text": "🔙 Voltar à Central", "callback_data": "menu_central"}])

        markup = {"inline_keyboard": buttons}
        if message_id:
            self.edit_message(message_id, "\n".join(lines), markup)
        else:
            self.send_message("\n".join(lines), markup)

    def send_proposal(self, folder: str):
        account_dir = ACCOUNTS_DIR / folder
        state = _read_json(account_dir / "state.json", {})
        prop = state.get("pending_proposal")
        if not prop:
            self.send_message("Não há proposta pendente.", markdown=False)
            return
        ad = prop["ad"]
        if isinstance(ad, list) and ad:
            ad = ad[0]
            prop["ad"] = ad
            _write_json(account_dir / "state.json", state)

        asset_path = account_dir / "assets" / prop["asset"]
        if asset_path.exists():
            if is_video_file(asset_path):
                preview_str = ad.get("preview_image_path")
                preview_path = Path(preview_str) if preview_str and Path(preview_str).exists() else extract_video_frames(asset_path)[0]
                self.send_photo(
                    preview_path,
                    f"[VÍDEO - Capa: 1º Frame] {prop['asset']}\nVisão da IA: {ad.get('visual_analysis', '')}",
                )
            else:
                self.send_photo(asset_path, f"Criativo: {prop['asset']}\nVisão da IA: {ad.get('visual_analysis', '')}")

        check = self.guard.validate_ad(ad.get("primary_text", ""), ad.get("headline", ""))
        compliance = "✅ Conforme" if check["compliant"] else "❌ " + "; ".join(check["reasons"])
        selection_line = f"\n🧠 Escolha estratégica: {ad['selection_reason']}\n" if ad.get("selection_reason") else ""
        note = f"\n\n🔧 Ajuste aplicado: {ad['refined_note']}" if ad.get("refined_note") else ""
        text = (
            f"PROPOSTA DE ANÚNCIO ({ad.get('media_type', 'image').upper()}) — {prop['asset']}\n"
            f"{selection_line}\n"
            f"Ângulo: {ad.get('angle', '-')}\n"
            f"Compliance Meta: {compliance}\n\n"
            f"Título: {ad.get('headline')}\n\n"
            f"Texto:\n{ad.get('primary_text')}\n\n"
            f"CTA: {ad.get('call_to_action')}{note}"
        )
        available_assets = AssetManager(account_dir).scan_new_assets()
        row1 = [
            {"text": "✅ Aprovar", "callback_data": f"approve_{folder}"},
            {"text": "✏️ Ajustar", "callback_data": f"adjust_{folder}"},
        ]
        row2 = [{"text": "❌ Rejeitar", "callback_data": f"reject_{folder}"}]
        if len(available_assets) > 1:
            row2.insert(0, {"text": "🔀 Trocar Criativo", "callback_data": f"swap|{folder}"})
        buttons = {"inline_keyboard": [row1, row2, [{"text": "🔙 Voltar à Central", "callback_data": "menu_central"}]]}
        self.send_message(text, buttons, markdown=False)

    # ------------------------------------------------------------------ ações
    def generate_proposal(self, folder: str, forced_asset_name: str = ""):
        self._refresh_env_tokens()
        account_dir = ACCOUNTS_DIR / folder
        asset_mgr = AssetManager(account_dir)
        assets = asset_mgr.scan_new_assets()
        if not assets:
            self.send_message("Nenhum criativo novo na pasta assets.", markdown=False)
            return

        cfg = _read_json(account_dir / "config.json", {})
        persona_file = account_dir / "persona.md"
        persona = persona_file.read_text(encoding="utf-8") if persona_file.exists() else ""
        p_form = _read_json(account_dir / "persona_form.json", {})
        mandatory_notes = p_form.get("mandatory_notes", "")
        default_cta = (cfg.get("campaign_defaults") or {}).get("default_cta", "APPLY_NOW")

        mem_mgr = MemoryManager(account_dir / "memory.json")
        memory = mem_mgr.load()
        top_insights = mem_mgr.get_top_insights()
        refiner = CopyRefiner(persona, memory, self.gemini_key)

        catalog_entries = asset_mgr.get_available_cataloged_entries()
        use_catalog = (not forced_asset_name) and bool(catalog_entries)

        if use_catalog:
            self.send_message("🧠 Escolhendo o melhor criativo do catálogo com base nos insights da conta...", markdown=False)
            try:
                info = self._collect_account_diagnosis(folder, cfg, assets)
                b = info["budget"]
                account_context = (
                    f"Diagnóstico: {info['diag'].get('action')} ({info['diag'].get('reason')})\n"
                    f"Orçamento: Gasto Mês R$ {b['current_month_spend']:.2f} / Teto R$ {b['monthly_max']:.2f} | "
                    f"Projeção R$ {b['projected_month_total']:.2f} | Folga Real R$ {b['available_monthly_budget']:.2f}\n"
                    f"Topologia recomendada: {b['recommended_topology']}"
                )
            except Exception as e:
                account_context = f"Resumo indisponível momentaneamente ({e}). Escolher criativo de maior potencial geral."

            try:
                chosen_name, ad = refiner.select_best_asset_and_generate_ad(
                    catalog_entries=catalog_entries,
                    account_context=account_context,
                    top_insights=top_insights,
                    mandatory_notes=mandatory_notes,
                    default_cta=default_cta,
                )
            except AIUnavailableError:
                self.send_message(
                    "⚠️ A IA (Gemini) está sobrecarregada agora e não consegui montar a proposta. Tente em alguns minutos.",
                    markdown=False,
                )
                return
        else:
            target = next((a for a in assets if a.name == forced_asset_name), assets[0])
            chosen_name = target.name
            self.send_message(f"🧠 Analisando o criativo '{chosen_name}', aguarde...", markdown=False)
            try:
                ad = refiner.create_proposal_from_media(
                    target,
                    top_insights=top_insights,
                    mandatory_notes=mandatory_notes,
                    default_cta=default_cta,
                )
            except AIUnavailableError:
                self.send_message(
                    "⚠️ A IA (Gemini) está sobrecarregada agora e não consegui analisar o criativo. Tente em alguns minutos.",
                    markdown=False,
                )
                return

        state = _read_json(account_dir / "state.json", {})
        state["pending_proposal"] = {"asset": chosen_name, "ad": ad, "created_at": datetime.now().isoformat()}
        _write_json(account_dir / "state.json", state)
        self.send_proposal(folder)

    def show_swap_options(self, folder: str):
        account_dir = ACCOUNTS_DIR / folder
        asset_mgr = AssetManager(account_dir)
        assets = asset_mgr.scan_new_assets()
        catalog = asset_mgr.load_catalog()
        if not assets:
            self.send_message("Nenhum criativo disponível para troca.", markdown=False)
            return

        buttons = []
        for idx, asset in enumerate(assets):
            entry = catalog.get(asset.name, {})
            tag = f" ({entry['theme']})" if entry.get("theme") else ""
            label = f"🎯 {asset.name[:24]}{tag[:25]}"
            buttons.append([{"text": label, "callback_data": f"pick|{folder}|{idx}"}])
        buttons.append([{"text": "🔙 Cancelar e rever atual", "callback_data": f"review_{folder}"}])
        self.send_message("🔀 Escolha outro criativo disponível nesta conta:", {"inline_keyboard": buttons}, markdown=False)

    def apply_feedback(self, folder: str, feedback: str):
        self._refresh_env_tokens()
        account_dir = ACCOUNTS_DIR / folder
        state = _read_json(account_dir / "state.json", {})
        prop = state.get("pending_proposal")
        if not prop:
            self.send_message("Não há proposta pendente para ajustar.", markdown=False)
            return
        persona_file = account_dir / "persona.md"
        persona = persona_file.read_text(encoding="utf-8") if persona_file.exists() else ""
        mem_mgr = MemoryManager(account_dir / "memory.json")
        memory = mem_mgr.load()

        self.send_message("✏️ Ajustando a copy com o seu feedback...", markdown=False)
        refiner = CopyRefiner(persona, memory, self.gemini_key)
        try:
            prop["ad"] = refiner.refine_with_feedback(prop["ad"], feedback)
        except AIUnavailableError:
            self.awaiting_feedback = folder
            self.send_message(
                "⚠️ A IA (Gemini) está sobrecarregada e não consegui aplicar o ajuste. "
                "A copy continua a mesma. Envie o feedback de novo em alguns minutos.",
                markdown=False,
            )
            return
        state["pending_proposal"] = prop
        _write_json(account_dir / "state.json", state)

        score = int(prop["ad"].get("importance_score", 7))
        summary = prop["ad"].get("learning_summary", feedback)
        mem_mgr.add_learning(summary, score=score, category="feedback")
        self.send_proposal(folder)

    def decide(self, folder: str, approved: bool):
        self._refresh_env_tokens()
        account_dir = ACCOUNTS_DIR / folder
        state = _read_json(account_dir / "state.json", {})
        prop = state.pop("pending_proposal", None)
        if not prop:
            self.send_message("Não há proposta pendente.", markdown=False)
            return

        if not approved:
            used = state.setdefault("used_assets", [])
            if prop["asset"] not in used:
                used.append(prop["asset"])
            state.setdefault("rejected_actions", []).append(
                {"asset": prop["asset"], "ad": prop["ad"], "decided_at": datetime.now().isoformat()}
            )
            _write_json(account_dir / "state.json", state)
            self.send_message("❌ Proposta rejeitada e registrada.", markdown=False)
            self.send_hub_menu()
            return

        cfg = _read_json(account_dir / "config.json", {})
        asset_path = account_dir / "assets" / prop["asset"]
        self.send_message("🚀 Subindo criativo para a Meta Ads como PAUSADO...", markdown=False)
        try:
            pub_res = MetaPublisher(self.meta_token, cfg).create_paused_ad(asset_path, prop["ad"])
        except Exception as e:
            state["pending_proposal"] = prop
            _write_json(account_dir / "state.json", state)
            self.send_message(f"❌ Erro ao criar anúncio na Meta: {e}", markdown=False)
            return

        used = state.setdefault("used_assets", [])
        if prop["asset"] not in used:
            used.append(prop["asset"])
        state["paused_pending_activation"] = {
            **pub_res,
            "asset": prop["asset"],
            "ad": prop["ad"],
            "created_at": datetime.now().isoformat(),
        }
        _write_json(account_dir / "state.json", state)

        buttons = {"inline_keyboard": [
            [{"text": "🚀 Ativar Anúncio Agora", "callback_data": f"activate_{folder}"}],
            [{"text": "🔙 Manter Pausado e Voltar", "callback_data": "menu_central"}],
        ]}
        self.send_message(
            f"✅ Anúncio ({pub_res.get('media_type', 'image')}) criado na Meta com status PAUSADO!\n\n"
            f"• Ad ID: {pub_res['ad_id']}\n"
            f"• Creative ID: {pub_res['creative_id']}\n"
            f"• Conjunto: {pub_res['adset_id']}\n\n"
            f"Deseja ativar o anúncio agora?",
            buttons,
            markdown=False,
        )

    def activate_pending_ad(self, folder: str):
        self._refresh_env_tokens()
        account_dir = ACCOUNTS_DIR / folder
        state = _read_json(account_dir / "state.json", {})
        pending = state.get("paused_pending_activation")
        if not pending:
            self.send_message("Nenhum anúncio pausado aguardando ativação.", markdown=False)
            return
        cfg = _read_json(account_dir / "config.json", {})
        try:
            res = MetaPublisher(self.meta_token, cfg).activate_ad(pending["ad_id"])
        except Exception as e:
            self.send_message(f"⚠️ Não foi possível ativar: {e}", markdown=False)
            return
        state.pop("paused_pending_activation", None)
        state.setdefault("approved_actions", []).append(
            {**pending, "status": "ACTIVE", "activated_at": datetime.now().isoformat()}
        )
        _write_json(account_dir / "state.json", state)
        bh = res["budget_health"]
        self.send_message(
            f"🟢 Anúncio {res['ad_id']} ATIVADO na Meta Ads!\n"
            f"Gasto do mês: R$ {bh['current_month_spend']:.2f} | "
            f"Projeção: R$ {bh['projected_month_total']:.2f} / Teto: R$ {bh['monthly_max']:.2f}",
            markdown=False,
        )
        self.send_hub_menu()

    def pause_target_ad(self, folder: str, ad_id: str):
        self._refresh_env_tokens()
        account_dir = ACCOUNTS_DIR / folder
        cfg = _read_json(account_dir / "config.json", {})
        try:
            MetaPublisher(self.meta_token, cfg).pause_object(ad_id)
        except Exception as e:
            self.send_message(f"❌ Erro ao pausar anúncio {ad_id}: {e}", markdown=False)
            return
        MemoryManager(account_dir / "memory.json").add_learning(
            f"Anúncio {ad_id} pausado por Stop-Loss (CPA acima do limite).", score=7, category="stop_loss"
        )
        self.send_message(f"⏸️ Anúncio {ad_id} pausado com sucesso na Meta Ads!", markdown=False)
        self.send_hub_menu()

    def create_starter_structure(self, folder: str):
        self._refresh_env_tokens()
        account_dir = ACCOUNTS_DIR / folder
        cfg_path = account_dir / "config.json"
        cfg = _read_json(cfg_path, {})
        try:
            res = MetaPublisher(self.meta_token, cfg).create_starter_campaign_and_adset()
        except Exception as e:
            self.send_message(f"❌ Erro ao criar campanha/conjunto inicial: {e}", markdown=False)
            return
        assets = cfg.setdefault("meta_assets", {})
        assets["default_campaign_id"] = res["campaign_id"]
        assets["default_adset_id"] = res["adset_id"]
        _write_json(cfg_path, cfg)
        self.send_message(
            f"🏗️ Estrutura inicial criada como PAUSED!\n"
            f"• Campanha ID: {res['campaign_id']} ({res['objective']})\n"
            f"• Conjunto ID: {res['adset_id']} (R$ {res['daily_budget_brl']:.2f}/dia)\n"
            f"Agora já podemos subir os anúncios dentro deste conjunto.",
            markdown=False,
        )
        self.show_account(folder)

    # ------------------------------------------------------------------ polling
    def handle_callback(self, cb: dict):
        data = cb.get("data", "")
        message_id = cb.get("message", {}).get("message_id")
        self.answer_callback(cb["id"])

        if data == "menu_central":
            self.awaiting_feedback = None
            self.send_hub_menu()
            return

        if "|" in data:
            parts = data.split("|")
            action, folder = parts[0], parts[1]
            extra = parts[2] if len(parts) > 2 else ""
        else:
            action, _, folder = data.partition("_")
            extra = ""

        if not (ACCOUNTS_DIR / folder).is_dir():
            self.send_message("Conta não encontrada.", markdown=False)
            return

        if action == "audit":
            self.show_account(folder, message_id)
        elif action == "generate":
            self.generate_proposal(folder)
        elif action == "swap":
            self.show_swap_options(folder)
        elif action == "pick" and extra != "":
            assets = AssetManager(ACCOUNTS_DIR / folder).scan_new_assets()
            idx = int(extra)
            if 0 <= idx < len(assets):
                self.generate_proposal(folder, forced_asset_name=assets[idx].name)
            else:
                self.send_message("Criativo não encontrado na fila atual.", markdown=False)
        elif action == "review":
            self.send_proposal(folder)
        elif action == "adjust":
            self.awaiting_feedback = folder
            self.send_message("✏️ Me diga o que quer mudar (ex.: 'tom mais direto', 'foque no benefício X').",
                              markdown=False)
        elif action == "approve":
            self.decide(folder, True)
        elif action == "reject":
            self.decide(folder, False)
        elif action == "activate":
            self.activate_pending_ad(folder)
        elif action == "pausead" and extra:
            self.pause_target_ad(folder, extra)
        elif action == "initcamp":
            self.create_starter_structure(folder)

    def handle_message(self, msg: dict):
        text = (msg.get("text") or "").strip()
        if self.awaiting_feedback and text and not text.startswith("/"):
            folder, self.awaiting_feedback = self.awaiting_feedback, None
            self.apply_feedback(folder, text)
        elif text in ("/start", "/menu", "/central"):
            self.send_hub_menu()

    def run_polling(self):
        print("🤖 Bot interativo ouvindo o Telegram... (Ctrl+C para parar)")
        offset = None
        while True:
            try:
                params = {"timeout": 30, "allowed_updates": json.dumps(["message", "callback_query"])}
                if offset:
                    params["offset"] = offset
                resp = requests.get(f"{self.api_url}/getUpdates", params=params, timeout=40)
                for upd in resp.json().get("result", []):
                    offset = upd["update_id"] + 1
                    try:
                        if "callback_query" in upd:
                            cb = upd["callback_query"]
                            if str(cb["from"]["id"]) == self.chat_id:
                                self.handle_callback(cb)
                        elif "message" in upd:
                            m = upd["message"]
                            if str(m["chat"]["id"]) == self.chat_id:
                                self.handle_message(m)
                    except Exception as e:
                        print(f"⚠️ Erro ao processar update: {e}")
                        try:
                            self.send_message(f"⚠️ Erro interno ao processar sua ação: {str(e)[:180]}", markdown=False)
                        except Exception:
                            pass
            except requests.RequestException:
                time.sleep(5)
            except KeyboardInterrupt:
                print("Encerrado.")
                break


if __name__ == "__main__":
    TelegramInteractiveBot().run_polling()
