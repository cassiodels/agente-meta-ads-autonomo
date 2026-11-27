"""
Painel de Controle Visual do Agente de IA Meta Ads (Streamlit).
100% compatível com uso local (PC) e remoto (VPS).
Centraliza onboarding, upload múltiplo de criativos, Persona estruturada revisável com IA,
todas as travas de orçamento/aprendizado, ativos Meta e atualizações sem tocar em arquivos ou código.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st

from core.skills.copy_refiner import CopyRefiner

load_dotenv(override=True)


def _update_env_in_place(env_path: Path, updates: dict) -> None:
    """Atualiza chaves diretamente no arquivo .env sem usar arquivo temporário/os.replace
    (evita Errno 16 Device or resource busy em bind mounts de arquivo único no Docker)."""
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = {k: str(v).strip() for k, v in updates.items()}
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                new_lines.append(f"{key}={remaining.pop(key)}")
                continue
        new_lines.append(line)
    for key, val in remaining.items():
        new_lines.append(f"{key}={val}")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")
    for key, val in updates.items():
        os.environ[key] = str(val).strip()

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
ACCOUNTS_DIR = BASE_DIR / "accounts"
TEMPLATE_DIR = ACCOUNTS_DIR / "cliente_modelo"
DOCS_DIR = BASE_DIR / "docs"

OBJECTIVES = ["OUTCOME_LEADS", "OUTCOME_TRAFFIC", "OUTCOME_ENGAGEMENT", "OUTCOME_SALES"]
CTAS = ["APPLY_NOW", "LEARN_MORE", "SEND_WHATSAPP_MESSAGE", "SHOP_NOW"]
GENDERS = ["todos", "masculino", "feminino"]
MEDIA_EXTS = {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".m4v", ".avi"}

st.set_page_config(page_title="Agente Meta Ads", page_icon="🤖", layout="wide")
st.title("🤖 Painel de Gestão — Agente Meta Ads")
st.caption("Sistema Autônomo com Supervisão Humana (Multi-Account | Local & VPS)")


def _create_client(name: str, ad_account_id: str, monthly_max: float) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", name.lower().strip()).strip("_") or "novo_cliente"
    target = ACCOUNTS_DIR / slug
    if target.exists():
        raise ValueError(f"Já existe uma pasta de cliente '{slug}'.")
    shutil.copytree(TEMPLATE_DIR, target)
    cfg_path = target / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["account_name"] = name.strip()
    clean_id = ad_account_id.strip()
    cfg["meta_ad_account_id"] = clean_id if clean_id.startswith("act_") else f"act_{clean_id}"
    cfg["budget"]["monthly_max_brl"] = float(monthly_max)
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    (target / "memory.json").write_text(
        json.dumps({"account_name": name.strip(), "insights_rankeados": [], "angulos_testados": {}, "historico_feedbacks": []},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return slug


# Sidebar: Seleção e Criação Guiada de Cliente
st.sidebar.header("🏢 Clientes")
available_accounts = sorted(
    d.name for d in ACCOUNTS_DIR.iterdir()
    if d.is_dir() and d.name != "cliente_modelo" and (d / "config.json").exists()
)

with st.sidebar.expander("➕ Cadastrar Novo Cliente", expanded=(len(available_accounts) == 0)):
    new_name = st.text_input("Nome da Empresa:", placeholder="Ex: Minha Loja")
    new_act_id = st.text_input("ID da Conta Meta (act_...):", placeholder="act_123456789")
    new_max = st.number_input("Teto Mensal Inicial (R$):", min_value=50.0, value=200.0, step=50.0)
    if st.button("Criar Cliente"):
        if not new_name.strip() or not new_act_id.strip():
            st.error("Preencha o nome e o ID da conta de anúncios.")
        else:
            try:
                slug = _create_client(new_name, new_act_id, new_max)
                st.success(f"Cliente '{slug}' criado!")
                st.rerun()
            except Exception as e:
                st.error(str(e))

if not available_accounts:
    st.info(
        "👋 Bem-vindo! Nenhum cliente cadastrado ainda.\n\n"
        "**Passo 1:** Cadastre seu primeiro cliente na barra lateral à esquerda (`➕ Cadastrar Novo Cliente`).\n"
        "**Passo 2:** Preencha a **Persona & Regras do Negócio** e aprove o texto gerado pela IA.\n"
        "**Passo 3:** Configure seus tokens na aba **Configurações**, use **Autodetectar Ativos** e envie seus criativos!"
    )
    st.stop()

selected_account = st.sidebar.selectbox("Cliente Ativo:", available_accounts)
account_path = ACCOUNTS_DIR / selected_account
config_file = account_path / "config.json"
persona_file = account_path / "persona.md"
persona_form_file = account_path / "persona_form.json"

config_data = json.loads(config_file.read_text(encoding="utf-8"))
persona_text = persona_file.read_text(encoding="utf-8") if persona_file.exists() else ""
persona_form = json.loads(persona_form_file.read_text(encoding="utf-8")) if persona_form_file.exists() else {}

budget_cfg = config_data.setdefault("budget", {})
guard_cfg = config_data.setdefault("guardrails", {})
notif_cfg = config_data.setdefault("notifications", {})
defaults_cfg = config_data.setdefault("campaign_defaults", {"objective": "OUTCOME_LEADS", "destination_url": "", "default_cta": "APPLY_NOW"})
target_cfg = config_data.setdefault("targeting", {"country": "BR", "region_note": "Brasil inteiro", "age_min": 18, "age_max": 55, "gender": "todos"})
meta_assets = config_data.setdefault("meta_assets", {})

# Abas Principais (100% sem código)
tab_dashboard, tab_persona, tab_config, tab_update = st.tabs([
    "📊 Visão Geral & Criativos",
    "🎯 Persona & Regras do Negócio",
    "⚙️ Configurações, Travas & Tokens",
    "🔄 Atualizações",
])

# ------------------------------------------------------------------ ABA 1: VISÃO GERAL & CRIATIVOS
with tab_dashboard:
    st.subheader(f"Status da Conta: {config_data.get('account_name', selected_account)}")
    monthly_max = float(budget_cfg.get("monthly_max_brl", 200.0))
    max_cpa = float(guard_cfg.get("max_acceptable_cpa_brl", 10.0))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Teto Mensal", f"R$ {monthly_max:.2f}")
    col2.metric("CPA Máximo", f"R$ {max_cpa:.2f}")
    col3.metric("Conta Meta", config_data.get("meta_ad_account_id", "-"))
    col4.metric("Objetivo Padrão", defaults_cfg.get("objective", "OUTCOME_LEADS"))

    st.write("---")
    st.subheader("🎨 Enviar Criativos (Imagens ou Vídeos)")
    st.caption("Funciona tanto no PC quanto na VPS. Para vídeos, o 1º frame será usado como capa e preview no Telegram.")
    uploads = st.file_uploader(
        "Selecione uma ou várias mídias (PNG, JPG, MP4, MOV):",
        type=["png", "jpg", "jpeg", "mp4", "mov"],
        accept_multiple_files=True,
    )
    assets_dir = account_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if uploads:
        saved = []
        for up in uploads:
            (assets_dir / up.name).write_bytes(up.getbuffer())
            saved.append(up.name)
        st.success(f"✅ {len(saved)} arquivo(s) salvo(s): {', '.join(saved)}")

    existing_media = sorted(f for f in assets_dir.iterdir() if f.is_file() and f.suffix.lower() in MEDIA_EXTS)
    if existing_media:
        st.markdown("**Arquivos salvos na pasta de criativos:**")
        for f in existing_media:
            c_name, c_del = st.columns([5, 1])
            c_name.write(f"• `{f.name}` ({round(f.stat().st_size / 1024, 1)} KB)")
            if c_del.button("🗑️ Remover", key=f"del_{selected_account}_{f.name}"):
                f.unlink(missing_ok=True)
                st.rerun()
    else:
        st.info("Nenhum criativo enviado ainda para esta conta.")

    st.write("---")
    st.info("💡 Dispara agora a auditoria diária consolidada (Central de Operações) para o Telegram:")
    if st.button("🚀 Executar Rotina Diária Agora"):
        with st.spinner("Consultando Meta e enviando Central no Telegram..."):
            res = subprocess.run(["python", "main.py"], cwd=str(BASE_DIR), capture_output=True, text=True)
        if res.returncode == 0:
            st.success("✅ Rotina executada! Verifique o seu Telegram.")
        else:
            st.error(f"Erro ao executar main.py:\n{res.stderr or res.stdout}")

# ------------------------------------------------------------------ ABA 2: PERSONA ESTRUTURADA + REVISÃO
with tab_persona:
    st.subheader("🎯 Persona e Diretrizes da Marca (Sem editar arquivos)")
    st.caption("Preencha os campos abaixo com suas palavras. A IA vai estruturar uma prévia para você revisar antes de salvar oficialmente.")

    obj_idx = OBJECTIVES.index(defaults_cfg.get("objective", "OUTCOME_LEADS")) if defaults_cfg.get("objective") in OBJECTIVES else 0
    cta_idx = CTAS.index(defaults_cfg.get("default_cta", "APPLY_NOW")) if defaults_cfg.get("default_cta") in CTAS else 0

    with st.form("form_persona_fields"):
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            f_niche = st.text_area("1. O que a empresa faz / Nicho:", value=persona_form.get("niche", ""), height=90,
                                   placeholder="Ex: Grupo VIP de ofertas Tech & Gamer, ou Clínica odontológica...")
            f_diff = st.text_area("2. Diferencial (Por que clicar agora?):", value=persona_form.get("differential", ""), height=90,
                                  placeholder="Ex: Cupons verificados todo dia, sem spam e acesso gratuito.")
            f_obj = st.selectbox("3. Objetivo principal das campanhas:", OBJECTIVES, index=obj_idx)
            if f_obj == "OUTCOME_LEADS":
                st.caption("ℹ️ Recomendação: para campanhas de cadastro (OUTCOME_LEADS), deixe um formulário já criado na Página e os Termos de Leads aceitos na Meta.")
            f_audience = st.text_area("4. Público-alvo (idade, gênero, interesses):", value=persona_form.get("audience", ""), height=80,
                                      placeholder="Ex: Homens 18-40 anos interessados em PC Gamer e hardware.")
            f_region = st.text_input("5. Região de atendimento:", value=persona_form.get("region", target_cfg.get("region_note", "Brasil inteiro")),
                                     placeholder="Ex: Brasil inteiro ou São Paulo - SP")
        with p_col2:
            f_pains = st.text_area("6. Principais dores / objeções do cliente:", value=persona_form.get("pains", ""), height=90,
                                   placeholder="Ex: Medo de pagar caro ou cair em site falso.")
            f_tone = st.text_area("7. Tom de voz e referências de linguagem (opcional):", value=persona_form.get("tone", ""), height=90,
                                  placeholder="Ex: Descontraído, divertido, com memes leves sem exagero.")
            f_notes = st.text_area("8. Observações e Regras Obrigatórias do Negócio:", value=persona_form.get("mandatory_notes", ""), height=110,
                                   placeholder="Ex: Deixar claro que NÃO vendemos produtos, apenas compartilhamos ofertas. Nunca prometer ganhos.")
            f_url = st.text_input("9. Link de destino (quando NÃO usar formulário):", value=persona_form.get("destination_url", defaults_cfg.get("destination_url", "")),
                                  placeholder="https://seusite.com.br")
            f_cta = st.selectbox("10. Botão CTA preferido:", CTAS, index=cta_idx)

        gen_draft = st.form_submit_button("✨ Gerar / Otimizar Persona com IA (para revisão)")

    if gen_draft:
        form_payload = {
            "account_name": config_data.get("account_name", selected_account),
            "niche": f_niche.strip(),
            "differential": f_diff.strip(),
            "objective": f_obj,
            "audience": f_audience.strip(),
            "region": f_region.strip(),
            "pains": f_pains.strip(),
            "tone": f_tone.strip(),
            "mandatory_notes": f_notes.strip(),
            "destination_url": f_url.strip(),
            "default_cta": f_cta,
        }
        persona_form_file.write_text(json.dumps(form_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        with st.spinner("Estruturando persona otimizada para revisão..."):
            refiner = CopyRefiner(persona_text, {}, os.getenv("GEMINI_API_KEY", ""))
            draft_md, used_ai = refiner.optimize_persona(form_payload)
        st.session_state[f"persona_draft_{selected_account}"] = draft_md
        if used_ai:
            st.success("✅ Rascunho otimizado pela IA gerado abaixo! Revise e aprove antes de gravar.")
        else:
            st.warning("⚠️ Gemini indisponível no momento; gerei o rascunho estruturado padrão abaixo para você revisar.")

    st.write("---")
    st.subheader("📝 Revisão da Persona antes de Salvar Oficialmente")
    draft_key = f"persona_draft_{selected_account}"
    current_draft = st.session_state.get(draft_key, persona_text)
    edited_persona = st.text_area(
        "Confira e ajuste o texto abaixo se necessário. Ele só passa a valer quando você clicar em Aprovar e Salvar:",
        value=current_draft,
        height=280,
    )
    if st.button("✅ Aprovar e Salvar Persona Oficial"):
        persona_file.write_text(edited_persona, encoding="utf-8")
        # Sincronizar defaults de campanha se formulário já tiver sido salvo
        if persona_form_file.exists():
            saved_form = json.loads(persona_form_file.read_text(encoding="utf-8"))
            config_data["campaign_defaults"] = {
                "objective": saved_form.get("objective", defaults_cfg.get("objective", "OUTCOME_LEADS")),
                "destination_url": saved_form.get("destination_url", defaults_cfg.get("destination_url", "")),
                "default_cta": saved_form.get("default_cta", defaults_cfg.get("default_cta", "APPLY_NOW")),
            }
            config_file.write_text(json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8")
        st.session_state.pop(draft_key, None)
        st.success("✅ Persona oficial aprovada e salva com sucesso!")

# ------------------------------------------------------------------ ABA 3: CONFIGURAÇÕES COMPLETAS & TOKENS
with tab_config:
    st.subheader("⚙️ Configurações Completas da Conta & Travas")

    if st.button("🔍 Autodetectar Ativos da Conta (Cold Start)"):
        from core.skills.cold_start import ColdStart
        with st.spinner("Consultando Meta API para identificar Página, Instagram e Formulário..."):
            try:
                cs = ColdStart(os.getenv("META_ACCESS_TOKEN", ""), config_data.get("meta_ad_account_id", ""))
                res = cs.apply_to_config(config_file)
                if res["is_virgin_account"]:
                    st.warning("⚠️ Conta virgem detectada (sem campanhas). Preencha a Página abaixo e crie a campanha inicial pelo Telegram.")
                elif res["updated_fields"]:
                    st.success(f"✅ Campos preenchidos automaticamente: {', '.join(res['updated_fields'])}.")
                    st.rerun()
                else:
                    st.info("ℹ️ Todos os ativos detectáveis já estão preenchidos.")
                if res["missing"]:
                    st.warning(f"Faltam preencher: {', '.join(res['missing'])}")
            except Exception as e:
                st.error(f"Erro ao consultar Meta API: {e}")

    with st.form("form_config"):
        c1, c2 = st.columns(2)
        with c1:
            acc_name = st.text_input("Nome da Empresa:", value=config_data.get("account_name", selected_account))
            new_act_id = st.text_input("ID da Conta de Anúncios (act_...):", value=config_data.get("meta_ad_account_id", ""))
            new_budget = st.number_input("Teto Máximo Mensal (R$):", min_value=50.0, max_value=100000.0,
                                         value=float(budget_cfg.get("monthly_max_brl", 200.0)), step=50.0)
            new_cpa = st.number_input("CPA Máximo Aceitável (R$):", min_value=1.0, max_value=5000.0,
                                      value=float(guard_cfg.get("max_acceptable_cpa_brl", 10.0)), step=1.0)
        with c2:
            new_learn_days = st.number_input("Dias mínimos da Fase de Aprendizado:", min_value=1, max_value=14,
                                             value=int(guard_cfg.get("min_learning_phase_days", 3)), step=1)
            new_var_pct = st.number_input("Variação Máxima Diária de Orçamento (%):", min_value=5.0, max_value=50.0,
                                          value=float(guard_cfg.get("max_daily_budget_change_pct", 20.0)), step=5.0)
            new_hour = st.text_input("Horário do Relatório Diário (HH:MM):", value=notif_cfg.get("daily_report_hour", "08:00"))

        st.write("---")
        st.subheader("🌍 Segmentação Padrão (para Cold Start / Novas Campanhas)")
        t1, t2, t3, t4, t5 = st.columns(5)
        with t1:
            t_country = st.text_input("País (ISO):", value=target_cfg.get("country", "BR"))
        with t2:
            t_region = st.text_input("Região (nota):", value=target_cfg.get("region_note", "Brasil inteiro"))
        with t3:
            t_age_min = st.number_input("Idade mín:", min_value=18, max_value=65, value=int(target_cfg.get("age_min", 18)))
        with t4:
            t_age_max = st.number_input("Idade máx:", min_value=18, max_value=65, value=int(target_cfg.get("age_max", 55)))
        with t5:
            g_idx = GENDERS.index(target_cfg.get("gender", "todos")) if target_cfg.get("gender") in GENDERS else 0
            t_gender = st.selectbox("Gênero:", GENDERS, index=g_idx)

        st.write("---")
        st.subheader("📱 Ativos da Conta Meta")
        a1, a2 = st.columns(2)
        with a1:
            page_id = st.text_input("ID da Página do Facebook:", value=meta_assets.get("page_id", ""))
            ig_id = st.text_input("ID da Conta do Instagram:", value=meta_assets.get("instagram_user_id", ""))
            form_id = st.text_input("ID do Formulário de Cadastro:", value=meta_assets.get("lead_gen_form_id", ""))
        with a2:
            camp_id = st.text_input("ID da Campanha Padrão:", value=meta_assets.get("default_campaign_id", ""))
            adset_id = st.text_input("ID do Conjunto Padrão:", value=meta_assets.get("default_adset_id", ""))

        st.write("---")
        st.subheader("🔑 Chaves de Acesso e Tokens Globais (.env)")
        meta_token = st.text_input("Meta Access Token:", value=os.getenv("META_ACCESS_TOKEN", ""), type="password")
        tg_token = st.text_input("Telegram Bot Token:", value=os.getenv("TELEGRAM_BOT_TOKEN", ""), type="password")
        tg_chat_id = st.text_input("Telegram Chat ID:", value=os.getenv("TELEGRAM_CHAT_ID", ""))
        gemini_token = st.text_input("Gemini API Key:", value=os.getenv("GEMINI_API_KEY", ""), type="password")

        if st.form_submit_button("💾 Salvar Todas as Configurações"):
            clean_act = new_act_id.strip()
            config_data["account_name"] = acc_name.strip()
            config_data["meta_ad_account_id"] = clean_act if clean_act.startswith("act_") else f"act_{clean_act}"
            config_data["budget"]["monthly_max_brl"] = float(new_budget)
            config_data["guardrails"] = {
                "min_learning_phase_days": int(new_learn_days),
                "max_daily_budget_change_pct": float(new_var_pct),
                "max_acceptable_cpa_brl": float(new_cpa),
            }
            config_data["notifications"]["daily_report_hour"] = new_hour.strip()
            config_data["targeting"] = {
                "country": t_country.strip().upper() or "BR",
                "region_note": t_region.strip(),
                "age_min": int(t_age_min),
                "age_max": int(t_age_max),
                "gender": t_gender,
            }
            config_data["meta_assets"] = {
                "page_id": page_id.strip(),
                "instagram_user_id": ig_id.strip(),
                "lead_gen_form_id": form_id.strip(),
                "default_campaign_id": camp_id.strip(),
                "default_adset_id": adset_id.strip(),
            }
            config_file.write_text(json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8")

            _update_env_in_place(ENV_PATH, {
                "META_ACCESS_TOKEN": meta_token,
                "TELEGRAM_BOT_TOKEN": tg_token,
                "TELEGRAM_CHAT_ID": tg_chat_id.strip(),
                "GEMINI_API_KEY": gemini_token,
            })
            st.success("✅ Configurações, travas, segmentação, ativos e tokens salvos com sucesso!")

# ------------------------------------------------------------------ ABA 4: ATUALIZAÇÕES
with tab_update:
    st.subheader("🔄 Atualização de Modelos de IA e Estratégias Meta")
    if st.button("🌐 Verificar Modelos e Atualizar Agora"):
        from core.model_manager import ModelManager
        with st.spinner("Consultando API de modelos do Gemini..."):
            mm = ModelManager(os.getenv("GEMINI_API_KEY", ""))
            ativos = mm.chain(force_refresh=True)
            for w in mm.warnings:
                st.warning(w)
            st.success(f"✅ Modelos prontos (ordem de prioridade): {', '.join(ativos)}")

    st.write("---")
    st.subheader("⬇️ Atualizar Código do Sistema (Git)")
    st.caption("Baixa as últimas melhorias do GitHub mantendo intactos os seus clientes, senhas (.env) e memórias.")
    if st.button("⬇️ Baixar Atualizações do GitHub"):
        res = subprocess.run(["git", "pull", "origin", "main"], cwd=str(BASE_DIR), capture_output=True, text=True)
        if res.returncode == 0:
            st.success(f"✅ Sistema atualizado!\n\n{res.stdout}")
        else:
            st.error(f"❌ Não foi possível atualizar via Git:\n{res.stderr}")

    playbook_file = DOCS_DIR / "playbook_meta.md"
    if playbook_file.exists():
        st.markdown("---")
        st.markdown(playbook_file.read_text(encoding="utf-8"))
