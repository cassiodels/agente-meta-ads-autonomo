# 🤖 Agente de IA para Gestão de Tráfego Meta Ads (Multi-Account)

Sistema modular para gestão, auditoria, criação de copys e publicação assistida de anúncios (imagens e vídeos) no **Meta Ads (Facebook & Instagram)**, operando em modelo **Human-in-the-Loop** via **Telegram** e **Painel Web (Streamlit)**.

---

## ✨ Principais Recursos do MVP

- **🏢 Arquitetura Multi-Tenant Isolada:** Cada cliente possui sua própria pasta em `accounts/<cliente>/` (`config.json`, `persona.md`, `persona_form.json`, `memory.json`, `assets/`, `reports/`, `state.json`), sem risco de mistura de dados. Dados reais de clientes ficam fora do Git via `.gitignore`.
- **🖥️ Painel Web 100% Sem Código (`app.py` + `INICIAR_PAINEL.bat`):** Compatível com uso local (PC) e remoto (VPS):
  - Onboarding guiado de novos clientes (teto padrão inicial R$ 200,00 e CPA padrão R$ 10,00).
  - Upload múltiplo de imagens/vídeos (`assets/`) e gerenciamento visual.
  - Formulário de Persona em 10 campos com **geração otimizada pela IA e revisão editável** antes de salvar o `persona.md` oficial.
  - Configuração completa de travas, segmentação, ativos Meta e tokens, além de atualização via `git pull`.
- **🎬 Suporte a Imagens e Vídeos (`video_utils.py` + `MetaPublisher`):**
  - Para vídeos (`.mp4`/`.mov`), extrai obrigatoriamente o **1º frame** (capa oficial na Meta e preview no Telegram) + até 2 frames ao longo do vídeo para análise multimodal econômica no Gemini.
- **🛡️ Auditoria Real & Travas Rígidas (`AdAuditor`, `RulesEngine`, `ComplianceGuard`):**
  - Lê `frequency` real e métricas por anúncio individual (`get_ad_insights`) para acionar **Stop-Loss** em anúncios caros mediante aprovação.
  - Teto mensal inviolável, respeito à fase de aprendizado e alerta imediato no Telegram se o token da Meta expirar (erro `190`).
  - Regras específicas do negócio definidas livremente nas Observações da Persona (sem hardcodes por nicho).
- **📲 Central de Operações no Telegram & Publicação em 2 Etapas:**
  - Menu consolidado multi-clientes (`AgencyHub`) + fluxo `[✅ Aprovar]` / `[✏️ Ajustar]` / `[❌ Rejeitar]`.
  - Criação de Campanha e Conjunto iniciais `PAUSED` para contas virgens (`ColdStart` + `create_starter_campaign_and_adset`).
  - Publicação de anúncio em 2 etapas: cria como **`PAUSED`** (gasto zero) e libera botão **`[🚀 Ativar Anúncio Agora]`**.
- **👁️ Visão Multimodal & Memória Rankeada (`ModelManager` + `MemoryManager`):**
  - Cadeia configurável (`gemini-4-hydrogen` + fallback `flash-lite`), redimensionamento de imagem (`<= 768px`) e ranking Top 10 de aprendizados por nota de importância (1 a 10).

---

## 📁 Estrutura do Projeto

```text
Agente de IA MetaADS/
├── INICIAR_PAINEL.bat               # Atalho 1-clique para abrir o painel no Windows
├── app.py                           # Painel Web completo (Streamlit, PC & VPS)
├── main.py                          # Orquestrador diário unificado (AgencyHub + alertas)
├── config/
│   └── models.json                  # Cadeia de modelos Gemini e limites de saída
├── core/
│   ├── meta_client.py               # Leitura Meta Marketing API (conta, campanhas, anúncios, erro 190)
│   ├── rules_engine.py              # Regras rígidas (teto mensal e fase de aprendizado)
│   ├── model_manager.py             # Descoberta de modelos, retries e log de uso
│   ├── memory_manager.py            # Memória rankeada por nota de importância
│   ├── asset_manager.py             # Scanner de criativos novos
│   ├── video_utils.py               # Extração do 1º frame (capa) + 2 frames para visão IA
│   ├── agency_hub.py                # Consolidado multi-cliente
│   ├── telegram_notifier.py         # Envio de relatórios e alertas
│   ├── telegram_interactive_bot.py  # Bot polling interativo (aprovar/ajustar/pausar/ativar)
│   └── skills/
│       ├── ad_auditor.py            # Diagnóstico crítico (Cold Start, Stop-Loss, saturação, escala)
│       ├── cold_start.py            # Autodetecção de ativos da Meta
│       ├── compliance_guard.py      # Validador de políticas globais da Meta
│       ├── copy_refiner.py          # Visão multimodal, otimização de persona e refinamento
│       ├── meta_publisher.py        # Publicação em 2 etapas (imagem/vídeo) e estrutura inicial
│       ├── audience_manager.py      # Gestão de públicos na Meta
│       └── monthly_report.py        # Relatório mensal simplificado
├── accounts/
│   └── cliente_modelo/              # Template público para criação de novos clientes
├── deploy/
│   ├── agente-meta-bot.service      # Serviço systemd (24/7 em VPS Linux)
│   └── crontab.example              # Agendamento diário e mensal
└── docs/
    ├── architecture_decision.md     # Decisões técnicas e roadmap
    └── playbook_meta.md             # Boas práticas ODAX e métricas
```

---

## 🚀 Como Usar

1. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Inicie o Painel Web:**
   - No Windows, dê dois cliques em `INICIAR_PAINEL.bat` (ou rode `streamlit run app.py`).
   - Cadastre o cliente, preencha a **Persona & Regras** (revise e aprove o texto gerado), configure seus tokens e use **🔍 Autodetectar Ativos**.
   - Envie imagens ou vídeos na aba **Visão Geral & Criativos**.
3. **Inicie o bot interativo:**
   ```bash
   python -m core.telegram_interactive_bot
   ```

---

## ☁️ Deploy em VPS Linux

1. Clone o repositório na VPS e instale `requirements.txt`.
2. Configure o cliente e `.env` diretamente pelo Painel Web (`streamlit run app.py`) ou copiando seus arquivos locais.
3. Copie `deploy/agente-meta-bot.service` para `/etc/systemd/system/` e ative:
   ```bash
   sudo systemctl enable --now agente-meta-bot
   ```
4. Configure os agendamentos no `crontab -e` usando `deploy/crontab.example`.
5. Para atualizar sem perder dados locais, clique em **⬇️ Baixar Atualizações do GitHub** no painel (ou rode `git pull`).
