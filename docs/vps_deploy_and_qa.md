# 🚀 Guia de Instalação na VPS & Roteiro de QA Real

Este guia foi escrito para que **qualquer pessoa** (mesmo iniciante, ou com ajuda de um chat de IA) consiga instalar e testar o **Agente de IA Meta Ads** em uma **VPS Linux (Ubuntu/Debian)** usando **Docker (recomendado)** — sem precisar editar código.

---

## Parte 0 — Antes de Começar: Onde Conseguir as 4 Chaves

Você vai precisar de 4 chaves para preencher o arquivo `.env` durante a instalação:

1. **`TELEGRAM_BOT_TOKEN`:**
   - No Telegram, pesquise por **`@BotFather`** → envie `/newbot` → escolha um nome e um usuário terminado em `bot` → copie o token gerado.
2. **`TELEGRAM_CHAT_ID`:**
   - No Telegram, pesquise por **`@userinfobot`** → clique em **Começar** → copie o número `Id:` exibido.
   - *Importante:* abra o seu bot recém-criado e clique em **Começar** (`/start`) para ele poder te enviar mensagens.
3. **`META_ACCESS_TOKEN`:**
   - Acesse [developers.facebook.com](https://developers.facebook.com/), crie um App do tipo **Outro → Empresarial** e adicione o produto **Marketing API**.
   - **Importante para criar anúncios (evita erro `1885183`):** em **Configurações → Básico**, preencha uma URL de Política de Privacidade e Categoria do App e alterne o App no topo da tela de **Desenvolvimento** para **Modo Público / Ao Vivo (Live)**. *(Para gerenciar contas do seu próprio Business Manager em acesso Standard, ligar o Modo Público já libera a criação de anúncios sem precisar aguardar App Review).*
   - Em **Marketing API → Ferramentas**, marque **`ads_management`**, **`ads_read`**, **`pages_manage_ads`** e **`pages_read_engagement`** e clique em **Gerar Token**.
4. **`GEMINI_API_KEY`:**
   - Acesse [aistudio.google.com](https://aistudio.google.com/), clique em **Get API key → Create API key** e copie a chave.

---

## Parte 1 — Instalação na VPS com Docker (Recomendado)

### Por que Docker?
- Isola Python 3.12 e as bibliotecas de vídeo (`opencv-python-headless`), evitando erros de sistema na VPS.
- Sobe o **Bot do Telegram (24/7)** e o **Painel Web** com 1 comando e reinício automático.
- Salva seus clientes (`accounts/`), configurações (`config/`) e chaves (`.env`) fora do container — nada se perde ao atualizar.

### Passo 1 — Instalar Docker e Docker Compose na VPS (Ubuntu/Debian)
Conectado à sua VPS via SSH, rode:
```bash
sudo apt update && sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version && docker compose version
```

### Passo 2 — Baixar o projeto e criar o `.env`
```bash
git clone https://github.com/cassiodels/agente-meta-ads-autonomo.git
cd agente-meta-ads-autonomo
cp .env.example .env
nano .env
```
Cole suas 4 chaves obtidas na Parte 0 (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `META_ACCESS_TOKEN`, `GEMINI_API_KEY`).  
Para salvar no `nano`: pressione `Ctrl+O`, depois `Enter`, e `Ctrl+X` para sair.

### Passo 3 — Subir o Bot e o Painel
```bash
docker compose up -d --build
docker compose ps
docker compose logs -f bot
```
*(Pressione `Ctrl+C` para sair da visualização de logs sem desligar o bot).*

### Passo 4 — Abrir o Painel Web com segurança no seu navegador
Por segurança, a porta `8501` do painel não fica aberta para a internet pública. Para acessá-la:
1. **No seu computador (Windows/Mac)**, abra **outro terminal** (PowerShell ou CMD — sem fechar o da VPS) e rode:
   ```bash
   ssh -L 8501:localhost:8501 usuario@IP_DA_SUA_VPS
   ```
2. Deixe esse terminal aberto e acesse no seu navegador:
   👉 `http://localhost:8501`

### Passo 5 — Configurar agendamentos diário e mensal (`crontab -e`)
Na VPS, rode:
```bash
mkdir -p ~/agente-meta-ads-autonomo/logs
crontab -e
```
Adicione ao final (se for a primeira vez, escolha `nano` quando perguntar o editor):
```cron
# Todo dia às 08:00 — envia Central consolidada e alertas no Telegram
0 8 * * * cd ~/agente-meta-ads-autonomo && docker compose exec -T bot python main.py >> logs/daily.log 2>&1

# Todo dia 1º às 09:00 — gera e envia o relatório mensal simplificado
0 9 1 * * cd ~/agente-meta-ads-autonomo && docker compose exec -T bot python -m core.skills.monthly_report >> logs/monthly.log 2>&1
```

### Passo 6 — Como atualizar no futuro sem perder dados
```bash
cd ~/agente-meta-ads-autonomo
git pull origin main
docker compose up -d --build
```

---

### Alternativa Nativa sem Docker (`venv` + `systemd`)
Caso prefira rodar direto no Linux sem Docker:
1. Instale dependências de sistema: `sudo apt install -y python3-venv git libglib2.0-0 libgl1`
2. Crie o ambiente e instale os pacotes:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copie `.env.example` para `.env` e preencha suas 4 chaves.
4. Use os arquivos `deploy/agente-meta-bot.service` e `deploy/crontab.example` da própria pasta do projeto para configurar o serviço 24/7 e o cron.

---

## Parte 2 — Roteiro de QA Real na VPS (Checklist de 9 Testes)

Execute na ordem abaixo para validar tudo em ambiente real:

### QA 1 — Containers no ar & Acesso ao Painel
- [ ] Rodar `docker compose ps` na VPS e confirmar `agente-meta-bot` e `agente-meta-panel` com status `Up`.
- [ ] Abrir o túnel SSH em outro terminal e acessar `http://localhost:8501`.
- **Esperado:** Painel abre normalmente no navegador sem expor a porta `8501` publicamente.

### QA 2 — Cadastro de Cliente & Padrões Seguros
- [ ] Na barra lateral (`➕ Cadastrar Novo Cliente`), informar Nome da Empresa e ID da conta Meta (`act_...`) e clicar em **Criar Cliente**.
- **Esperado:** Cliente criado com teto mensal global padrão **R$ 200,00** e CPA máximo padrão **R$ 10,00**.

### QA 3 — Persona em 2 Etapas (Revisão antes de Salvar)
- [ ] Na aba **🎯 Persona & Regras do Negócio**, preencher os 10 campos (incluindo *Observações e Regras Obrigatórias*).
- [ ] Clicar em **✨ Gerar / Otimizar Persona com IA (para revisão)**.
- [ ] Conferir o rascunho na caixa de revisão, ajustar algo se quiser e clicar em **✅ Aprovar e Salvar Persona Oficial**.
- **Esperado:** `persona.md` oficial salvo apenas após sua aprovação.

### QA 4 — Cold Start (`Autodetectar Ativos`) & Configurações
- [ ] Na aba **⚙️ Configurações, Travas & Tokens**, clicar em **🔍 Autodetectar Ativos da Conta (Cold Start)**.
- [ ] Conferir Página, Instagram, Formulário, Campanha e Conjunto preenchidos (ou preencher manualmente se for conta virgem) e clicar em **💾 Salvar Todas as Configurações**.
- **Esperado:** Tudo salvo sem erros (inclusive atualização do `.env` sem `Errno 16`).

### QA 5 — Upload Múltiplo, Catalogação com IA & Remoção Permanente (Painel Web)
- [ ] Na aba **📊 Visão Geral & Criativos**, enviar **1 imagem (`.png`/`.jpg`)** e **1 vídeo curto (`.mp4`)** (com o 1º frame sendo a capa desejada), além de **1 arquivo descartável** para testar remoção.
- [ ] Clicar em **🗑️ Remover** no arquivo descartável.
- [ ] Clicar em **🧠 Catalogar Criativos Novos com IA**.
- **Esperado:** O arquivo descartável some imediatamente da tela e do disco (sem reaparecer após o reload) e os criativos restantes ficam marcados como `✅ Catalogado` com resumo e recomendação de uso.

### QA 6 — Central no Telegram & Orçamento Consolidado Real
- [ ] No **Telegram**, enviar `/menu` para o bot e clicar em **Auditar &lt;Nome do Cliente&gt;**.
- **Esperado:** Exibe o bloco **Orçamento Consolidado da Conta** (Teto Mensal, Gasto no Mês, Ativos Hoje/dia, Projeção Fim do Mês, Folga Real e Topologia recomendada) e o diagnóstico real do `AdAuditor`.

### QA 7 — Escolha Autônoma do Criativo + Preview do 1º Frame + `✏️ Ajustar` / `🔀 Trocar Criativo` (Telegram)
- [ ] Ainda dentro da conta no **Telegram**, clicar em **✨ Sugerir Melhor Criativo e Gerar Copy**.
- [ ] Conferir que o agente escolheu autonomamente o criativo do catálogo explicando o motivo estratégico (`🧠 Escolha estratégica`), enviou o **1º frame** se for vídeo (`[VÍDEO - Capa: 1º Frame]`) e gerou a copy alinhada à Persona.
- [ ] Testar o botão **✏️ Ajustar** enviando uma instrução curta (e, se houver mais de 1 criativo, testar opcionalmente **🔀 Trocar Criativo**).
- **Esperado:** Copy reescrita com aprendizado salvo em `memory.json`, e troca de criativo funcionando sem erros.

### QA 8 — Publicação em 2 Etapas na Meta (`PAUSED` → `ACTIVE`) & Trava Global
- [ ] Clicar em **✅ Aprovar** na proposta no **Telegram** (lembrando que o App no Meta Developers precisa estar em **Modo Público / Live**).
- [ ] Conferir pelos IDs retornados (e no Gerenciador de Anúncios) que o anúncio entrou como **PAUSADO** (gasto R$ 0,00) com o **1º frame** como capa (se vídeo).
- [ ] Decidir entre **🚀 Ativar Anúncio Agora** (validado pelo Hard Stop global da conta) ou **🔙 Manter Pausado e Voltar**.

### QA 9 — Rotina Diária, Relatório Mensal & Atualização Segura
- [ ] Rodar na VPS: `docker compose exec -T bot python main.py` e confirmar entrega da Central consolidada no Telegram.
- [ ] Rodar na VPS: `docker compose exec -T bot python -m core.skills.monthly_report` e confirmar geração do relatório mensal + envio no Telegram.
- [ ] Rodar `git pull origin main` e confirmar que `.env` e `accounts/` permanecem intactos.
