# 🚀 Guia de Instalação na VPS & Roteiro de QA Real

Este guia cobre a instalação completa em uma **VPS Linux (Ubuntu/Debian)** usando **Docker (recomendado)** — ou a alternativa nativa com `venv` + `systemd` — e traz o **Roteiro de QA** passo a passo para validar cada fluxo em produção.

---

## Parte 1 — Instalação na VPS

### Por que usar Docker na VPS?
- Isola Python 3.12 e as bibliotecas gráficas exigidas pelo `opencv-python-headless` (extração de frames de vídeo), evitando conflitos com o sistema operacional da VPS.
- Sobe o **Bot do Telegram (24/7)** e o **Painel Web (Streamlit)** com um único comando e reinício automático (`restart: unless-stopped`).
- Mantém seus clientes (`./accounts`), logs de uso/modelos (`./config`) e chaves (`./.env`) salvos fora do container, preservando 100% dos dados ao atualizar.

---

### Opção A: Instalação com Docker (Recomendado)

#### 1. Instalar Docker e Docker Compose na VPS (Ubuntu/Debian)
```bash
sudo apt update && sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version && docker compose version
```

#### 2. Clonar o repositório e preparar o `.env`
```bash
git clone https://github.com/cassiodels/agente-meta-ads-autonomo.git
cd agente-meta-ads-autonomo
cp .env.example .env
nano .env
```
Preencha no `.env`:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `META_ACCESS_TOKEN`
- `GEMINI_API_KEY`

*(Dica: certifique-se de que as pastas `accounts/` e `config/` existem antes de subir).*

#### 3. Subir o Bot e o Painel
```bash
docker compose up -d --build
docker compose ps
docker compose logs -f bot
```
*(Pressione `Ctrl+C` para sair dos logs sem parar o container).*

#### 4. Acessar o Painel Web com segurança (Túnel SSH)
Por segurança, o `docker-compose.yml` expõe a porta `8501` apenas em `127.0.0.1` na VPS (não aberta para a internet pública).
No terminal do **seu computador local (Windows PowerShell/CMD)**, abra um túnel SSH:
```bash
ssh -L 8501:localhost:8501 usuario@IP_DA_SUA_VPS
```
Com o túnel aberto, acesse no seu navegador local:
👉 `http://localhost:8501`

#### 5. Configurar agendamentos diário e mensal (`crontab -e`)
Na VPS, crie a pasta de logs e abra o agendador:
```bash
mkdir -p ~/agente-meta-ads-autonomo/logs
crontab -e
```
Adicione ao final (ajustando o caminho se necessário):
```cron
# Todo dia às 08:00 — envia Central consolidada e alertas no Telegram
0 8 * * * cd ~/agente-meta-ads-autonomo && docker compose exec -T bot python main.py >> logs/daily.log 2>&1

# Todo dia 1º às 09:00 — gera e envia o relatório mensal simplificado
0 9 1 * * cd ~/agente-meta-ads-autonomo && docker compose exec -T bot python -m core.skills.monthly_report >> logs/monthly.log 2>&1
```

#### 6. Como atualizar no futuro sem perder dados
```bash
cd ~/agente-meta-ads-autonomo
git pull origin main
docker compose up -d --build
```

---

### Opção B: Alternativa Nativa sem Docker (`venv` + `systemd`)
Caso prefira rodar direto no Linux sem Docker:
1. Instale Python 3.11+, `git` e libs de sistema (`sudo apt install -y python3-venv git libglib2.0-0 libgl1`).
2. Clone o repositório, crie o ambiente virtual e instale as dependências:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copie `.env.example` para `.env` e preencha suas chaves.
4. Configure o serviço 24/7 usando [deploy/agente-meta-bot.service](file:///d:/_Estudos/Agente%20de%20IA%20MetaADS/deploy/agente-meta-bot.service) e os agendamentos usando [deploy/crontab.example](file:///d:/_Estudos/Agente%20de%20IA%20MetaADS/deploy/crontab.example).

---

## Parte 2 — Roteiro de QA Real na VPS (Checklist de 9 Testes)

Execute os testes abaixo em sequência para validar o MVP completo em ambiente real:

### QA 1 — Containers no ar & Acesso Seguro ao Painel
- [ ] Rodar `docker compose ps` na VPS e confirmar `agente-meta-bot` e `agente-meta-panel` com status `Up`.
- [ ] Abrir o túnel SSH (`ssh -L 8501:localhost:8501 ...`) e abrir `http://localhost:8501` no navegador.
- **Resultado esperado:** Painel carrega sem erros e sem expor a porta `8501` publicamente.

### QA 2 — Onboarding de Cliente & Padrões Seguros
- [ ] Na barra lateral (`➕ Cadastrar Novo Cliente`), criar um cliente (ou verificar um existente).
- **Resultado esperado:** Pasta criada em `accounts/<slug>/` com teto mensal padrão **R$ 200,00** e CPA máximo padrão **R$ 10,00**.

### QA 3 — Persona Estruturada em 2 Etapas (Revisão antes de Salvar)
- [ ] Na aba **🎯 Persona & Regras do Negócio**, preencher os 10 campos (incluindo *Observações e Regras Obrigatórias*).
- [ ] Clicar em **✨ Gerar / Otimizar Persona com IA (para revisão)**.
- [ ] Conferir que o rascunho aparece editável na tela **sem sobrescrever** o arquivo oficial ainda; editar uma palavra e clicar em **✅ Aprovar e Salvar Persona Oficial**.
- **Resultado esperado:** Arquivo `accounts/<slug>/persona.md` e `persona_form.json` salvos corretamente na VPS.

### QA 4 — Cold Start (`Autodetectar Ativos`) & Configurações
- [ ] Na aba **⚙️ Configurações, Travas & Tokens**, clicar em **🔍 Autodetectar Ativos da Conta (Cold Start)**.
- [ ] Conferir `page_id`, `instagram_user_id`, `lead_gen_form_id`, campanha e conjunto padrão preenchidos e clicar em **💾 Salvar Todas as Configurações**.
- **Resultado esperado:** Dados persistidos no `config.json` sem erro de API.

### QA 5 — Upload Múltiplo de Imagem e Vídeo pelo Navegador
- [ ] Na aba **📊 Visão Geral & Criativos**, enviar **1 imagem (`.png`/`.jpg`)** e **1 vídeo curto (`.mp4`)** (com o 1º frame sendo a capa desejada).
- [ ] Testar também o botão **🗑️ Remover** em um arquivo de teste descartável.
- **Resultado esperado:** Os arquivos aparecem na lista do painel e dentro de `accounts/<slug>/assets/` na VPS.

### QA 6 — Central no Telegram & Diagnóstico Real
- [ ] No Telegram, enviar `/menu` para o bot.
- [ ] Clicar em **Auditar &lt;Nome do Cliente&gt;**.
- **Resultado esperado:** Exibe gasto do mês vs teto, `frequency` real e o diagnóstico do `AdAuditor` (e, caso haja anúncio com Stop-Loss ou conta virgem, exibe os botões correspondentes).

### QA 7 — Fluxo de Vídeo + Preview do 1º Frame + Botão `✏️ Ajustar`
- [ ] Dentro da conta no Telegram, clicar em **✨ Analisar criativo e gerar copy** selecionando o vídeo (ou imagem).
- [ ] Conferir que chegou no Telegram a **foto do 1º frame** com `[VÍDEO - Capa: 1º Frame]` + copy seguindo a Persona.
- [ ] Clicar em **✏️ Ajustar**, enviar uma instrução curta (ex.: *"Deixe o título mais curto e direto"*) e aguardar a nova versão.
- **Resultado esperado:** Copy reescrita conforme pedido e feedback registrado com nota em `accounts/<slug>/memory.json`.

### QA 8 — Publicação em 2 Etapas na Meta (`PAUSED` → `ACTIVE`)
- [ ] Clicar em **✅ Aprovar** na proposta.
- [ ] Abrir o Gerenciador de Anúncios da Meta (ou conferir pelos IDs retornados) e confirmar que o anúncio foi criado com status **PAUSADO** (gasto R$ 0,00) e com o **1º frame** como capa (se vídeo).
- [ ] Decidir se clica em **🚀 Ativar Anúncio Agora** (checando o `RulesEngine`) ou em **🔙 Manter Pausado e Voltar**.
- *(Opcional em conta de teste virgem)*: testar **🏗️ Criar Campanha/Conjunto Inicial (PAUSED)** e confirmar criação pausada na Meta.

### QA 9 — Rotina Diária, Relatório Mensal & Atualização Sem Perder Dados
- [ ] Rodar manualmente na VPS: `docker compose exec -T bot python main.py` e confirmar entrega da Central no Telegram.
- [ ] Rodar manualmente: `docker compose exec -T bot python -m core.skills.monthly_report` e conferir geração do `.md` em `accounts/<slug>/reports/` + envio no Telegram.
- [ ] Rodar `git pull origin main` na VPS e confirmar que `.env` e `accounts/<slug>/` permanecem intactos.
