# 📋 Planejamento e Arquitetura - Agente Autônomo Meta Ads (Multi-Account)

> **Documento de Especificação Técnica e Decisões de Design**  
> *Data de Criação: 25/11/2026*

---

## 1. 🎯 Visão Geral do Projeto
O objetivo é desenvolver um agente inteligente para gestão, análise, otimização e criação de campanhas no **Meta Ads**, operando em regime de **Piloto Automático Supervisionado (Human-in-the-Loop)**.

O agente automatiza a rotina operacional pesada (análise de métricas, geração de copys, preparação de criativos e verificação de compliance), mas **sempre solicita confirmação humana antes de aplicar mudanças financeiras ou colocar novos anúncios no ar**.

---

## 2. 🛡️ Princípios e Travas de Segurança (Hard Rules)

1. **Confirmação Obrigatória de Orçamento:**
   - O agente **nunca** altera orçamentos ou migra verbas de forma autônoma. Ele gera a recomendação fundamentada e aguarda a aprovação.
2. **Respeito Absoluto à Fase de Aprendizado:**
   - Conjuntos de anúncios em fase de aprendizado (ou com alterações recentes dentro da janela mínima de 48-72h ou volume mínimo de eventos) não sofrem intervenção para evitar reiniciar o algoritmo da Meta.
3. **Compliance com as Políticas da Meta:**
   - Regras rígidas de conformidade publicitária integradas para impedir promessas exageradas, nichos sensíveis e termos vetados, evitando bloqueios na conta.
4. **Teto Orçamentário Inviolável:**
   - Verificação em nível de código para garantir que o gasto mensal projetado nunca ultrapasse o orçamento estipulado pelo cliente.

---

## 3. 🏢 Arquitetura Multi-Tenant (Isolamento por Cliente/Conta)

O sistema foi desenhado para ser **100% modular**, permitindo gerenciar a Empresa A, B, C sem contaminação de dados, criativos ou orçamentos.

### Estrutura de Diretórios:
```text
Agente de IA MetaADS/
├── .env                          # Credenciais globais (Tokens da Meta, Telegram Bot Token)
├── .gitignore                    # Proteção contra commit de chaves e dados sensíveis
├── main.py                       # Orquestrador da rotina diária
├── core/                         # Motor compartilhado (lógica invariante)
│   ├── meta_client.py            # Integração com a Meta Marketing API
│   ├── rules_engine.py           # Regras rígidas (orçamento, fase de aprendizado)
│   ├── copy_engine.py            # Geração de copys alinhadas à persona
│   ├── telegram_bot.py           # Envio de relatórios e botões de aprovação
│   └── report_generator.py       # Compilação de relatórios diários e mensais
│
├── accounts/                     # Diretório de clientes (isolamento total)
│   ├── cliente_modelo/           # Template de configuração de conta
│   │   ├── config.json           # ID da conta (act_XXX), teto de orçamento, metas de CPA
│   │   ├── persona.md            # Tom de voz, dores, público-alvo e nicho
│   │   ├── assets/               # Imagens e vídeos deste cliente específico
│   │   ├── reports/              # Logs diários e relatórios mensais simplificados
│   │   └── state.json            # Estado atual e histórico de aprovações
│
└── docs/                         # Documentações e decisões de arquitetura
    └── architecture_decision.md
```

---

## 4. 📲 Interface do Usuário e Rotina Operacional

- **Interface Principal:** Bot interativo no **Telegram**.
- **Rotina Diária:**
  1. O agente acorda em horário agendado (ou sob demanda).
  2. Coleta métricas de performance da conta.
  3. Compara o desempenho com metas e regras de aprendizado.
  4. Envia mensagem consolidada no Telegram:
     - Resumo de gastos e métricas do dia/mês.
     - Ações recomendadas (ex.: pausar anúncio ruim, subir novo anúncio com imagem da pasta `assets/`).
     - Botões inline: `[ ✅ Aprovar ]`, `[ ✏️ Ajustar ]`, `[ ❌ Ignorar ]`.
- **Relatório Mensal:**
  - Relatório consolidado em linguagem simples e executiva, explicando o que foi feito, onde a verba foi alocada e os resultados obtidos (ideal para apresentação a diretores/clientes sem conhecimento técnico).

---

## 8. 🏢 Gestão Multi-Cliente Avançada, Cold Start & Auditoria de Ativos

Para permitir escala limpa para dezenas de clientes sem sobrecarregar a rotina:

### 1. Central de Operações no Telegram (Fila de Navegação Interativa):
- O agente não dispara mensagens isoladas por cliente de forma caótica.
- Dispara uma **Central Consolidada Matinal** listando todos os clientes e seus status (`OK` vs `Ação Pendente`).
- Botões inline permitem auditar o Cliente A, aprovar/ajustar a ação, e voltar automaticamente para a lista para continuar revisando os próximos clientes até todos estarem concluídos (`[ 🔙 Voltar ao Menu Geral ]`).

### 2. Protocolo de "Cold Start" para Contas Novas / Virgens:
- O `AdAuditor` identifica contas sem histórico ou sem campanhas ativas.
- Em vez de tentar otimizações inexistentes, aciona o **Protocolo de Lançamento Inicial**:
  - Sugere orçamento diário de teste controlado (R$ 10 - R$ 15/dia).
  - Configura Advantage+ Audience aberta (respeitando idade/gênero da `persona.md`).
  - Prepara teste A/B com as duas primeiras variações da pasta `assets/`.

### 3. Auditoria Preventiva de Ativos (Pixel & WhatsApp):
- Antes de sugerir campanhas com objetivo de mensagens para WhatsApp ou conversões de site:
  - O agente consulta a Meta API (`act_XXX/adspixels` e ativos vinculados).
  - Se o Pixel ou número de WhatsApp não estiverem configurados na infraestrutura da Meta, o agente bloqueia a recomendação para evitar rejeição e orienta o uso temporário de Formulários Nativos de Cadastro.


Inspirado nos padrões de engenharia de agentes modernos (Claude Code, Anthropic Agentic Patterns):

### 1. Divisão em Habilidades Especialistas (`core/skills/`):
- **`AdAuditor` (Estrategista Crítico):**
  - Avalia se o momento exige `MANTER`, `AJUSTAR_COPY`, `SOLICITAR_NOVO_CRIATIVO` ou `SUGERIR_AJUSTE_ORCAMENTO`.
  - Se faltar criativo na pasta `assets/`, gera um **Briefing Prático de Produção** para o usuário gravar/criar.
  - Sugere aumento ou redução de orçamento (nunca altera sem que o usuário modifique pelo painel).
- **`CopyRefiner` (Redator & Copiloto com Loop de Feedback):**
  - Gera variações iniciais e suporta o botão `[ ✏️ Ajustar ]` do Telegram, refinando a copy com base no feedback textual do usuário.
- **`ComplianceGuard` (Auditor de Políticas e Isenção):**
  - Valida regras da Meta e garante a presença obrigatória da cláusula de isenção (*"Não somos loja e não vendemos produtos"*).
- **`AudienceManager` (Gestor de Públicos):**
  - Monitora saturação e cria Públicos Personalizados e Semelhantes (Lookalike 1%) via Meta Graph API.
- **`MetaPublisher` (Executor Seguro):**
  - Publica e altera anúncios na API apenas sob confirmação explícita.

### 2. Memória Persistente (`accounts/{cliente}/memory.json`):
- Registra o histórico de aprendizado da conta:
  - Ângulos de copy que performaram com alto CTR/CPA baixo (`WINNERS`).
  - Ângulos rejeitados pelo público (`LOSERS`), evitando repetições de testes falhos.
  - Histórico de feedbacks do usuário no Telegram.


Para que qualquer pessoa (mesmo sem conhecimento de código ou terminal) consiga operar e gerenciar o agente:
1. **Painel Web Local / Web UI Simples (ex: Streamlit / FastAPI):**
   - Permite preencher e salvar chaves de API (`.env`).
   - Permite definir ou alterar o teto mensal de orçamento por cliente de forma visual (ex: R$ 200,00/mês).
   - Visualização rápida dos relatórios diários e histórico de aprovações.
2. **Botão "Atualizar Conhecimento do Agente" (Auto-Update via Busca Web & LLM):**
   - O agente consulta a internet por novidades na Graph API da Meta e tendências de tráfego pago.
   - Atualiza automaticamente o `playbook_meta.md` e os arquivos de configuração com as práticas mais recentes.


- [x] **Fase 1:** Inicialização do Git (`.gitignore`, commits semânticos) e documentação de arquitetura.
- [x] **Fase 2:** Criação e configuração das credenciais (Meta Developers, Telegram Bot & Gemini).
- [x] **Fase 3:** Construção do esqueleto de contas isoladas (`accounts/`) e travas de segurança (`rules_engine`).
- [x] **Fase 4:** Integração de leitura real (conta, campanhas, anúncios individuais, `frequency` real, alerta de erro 190).
- [x] **Fase 5:** Motor de criativos (imagem & vídeo com 1º frame como capa), memória rankeada e publicação em 2 etapas (`PAUSED` -> `ACTIVE`).
- [x] **Fase 6:** Painel Web sem código (PC & VPS, persona revisável), relatório mensal e templates de deploy em VPS.

---

## 9. 🎬 Refinamentos Finais do MVP (26/11/2026)
- **Vídeos no MVP:** `core/video_utils.py` extrai obrigatoriamente o **1º frame** (capa na Meta + preview no Telegram) + 2 frames ao longo do vídeo para visão multimodal econômica, e `MetaPublisher` envia via `advideos` + `video_data`.
- **Auditoria Real & Stop-Loss:** `MetaClient` consulta `frequency`, `reach` e `get_ad_insights`, permitindo ao `AdAuditor` identificar anúncios caros individuais (`PAUSAR_ANUNCIO`) e contas sem campanhas (`COLD_START`).
- **Criação Inicial `PAUSED`:** `MetaPublisher.create_starter_campaign_and_adset` cria campanha e conjunto iniciais pausados para contas virgens usando a segmentação e orçamento do painel.
- **Regras Agnósticas ao Nicho:** Removido qualquer hardcode de nicho do `ComplianceGuard`; particularidades ficam no campo livre *Observações e Regras Obrigatórias* da Persona.
- **Painel 100% Sem Código:** `app.py` (local & VPS) centraliza onboarding, upload múltiplo de mídias, revisão editável da Persona otimizada por IA antes de salvar oficialmente, travas, segmentação, ativos e atualização via `git pull`.

---

## 10. 🔮 Backlog da v2 (Não implementar no MVP)
- **Nota de Otimização / Saúde da Conta (Score 0–10 ou 0–100):** Indicador simples no relatório diário e no painel para o usuário saber de imediato se a conta de anúncios está indo bem ou não (ponderando CPA vs. meta, CTR, frequência e uso do orçamento).
- **Automação de Direct / Comentários no Instagram:** Envio automático de link por mensagem direta para quem comentar em posts.
- **Análise de Conteúdo Orgânico:** Leitura e aproveitamento de posts orgânicos do Instagram da marca.


