# 🚀 Social Mídia Autônoma

App desktop local (Streamlit + SQLite) para pesquisa, roteirização, gestão e edição de conteúdo para Instagram/TikTok.

## Como rodar

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # preencha as chaves que for usar
streamlit run app.py
```

O banco é criado automaticamente em `data/socialmidia.db`.

## Estrutura

```
app.py                  # entrada + menu lateral
database.py             # schema SQLite, migrações e acesso aos dados
modulos/                # uma página Streamlit por módulo (só interface)
  m0_dashboard.py       # Centro de Comando
  m1_cerebro.py         # Personas, Radar de Audiência, Assuntos Quentes, Histórico
  m2_maquina_conteudo.py
  m3_cofre_ideias.py    # Kanban
  m4_estudio.py         # Vídeo automático + carrosséis
  configuracoes.py      # provedor de IA, modelos e chaves de API
services/               # lógica sem Streamlit
  llm.py                # Ollama / OpenAI / Claude via LangChain + respostas em JSON
  scraper.py            # coleta de comentários (Apify) e importação manual (.txt/.csv)
  radar.py              # comentários -> IA -> Dores, Dicionário e Assuntos Quentes
  rastreador.py         # piloto automático: palavras-chave agendadas (APScheduler)
  maquina.py            # Termômetro de Validação, funil/formato e geração do roteiro
  cofre.py              # edição com registro no Dossiê e reciclagem de posts
worker.py               # roda o piloto automático com o app fechado
tests/                  # testes automatizados (IA simulada, sem custo)
data/                   # banco, uploads, templates e exportações (fora do git)
```

## Módulo 1 — Cérebro

1. **⚙️ Configurações**: escolha o provedor de IA. Para usar o **Ollama** (gratuito), instale em
   https://ollama.com e rode `ollama pull llama3.1`. Para OpenAI/Claude, informe a chave.
2. **👤 Personas**: cadastre cada perfil (público-alvo, tom de voz, palavras proibidas).
3. **📡 Radar de Audiência**: cole a URL de um post (coleta automática pela Apify, requer
   `APIFY_API_TOKEN`) ou cole/envie os comentários manualmente.
4. A IA gera **Dores**, **Dicionário do público** e **Alertas de Tendência**, que viram
   **🔥 Assuntos Quentes** e alimentam o Módulo 2.

### 🤖 Rastreador Automático (piloto automático)

Na aba **Rastreador Automático**, cadastre palavras-chave (ex.: `limpeza porcelanato manchado`).
No dia e horário configurados (padrão: **sexta às 08:00**), o app busca na Apify os vídeos mais
quentes de cada palavra, lê os comentários e envia **dores e tendências** para Assuntos Quentes.

- Funciona em segundo plano enquanto o app estiver aberto. Se o computador estiver desligado no
  horário, a rodada acontece assim que o app for aberto.
- Para rodar **com o app fechado**, use o worker:
  - `python worker.py` → fica rodando e respeita a agenda;
  - `python worker.py --agora` → roda só o que está pendente e encerra. Ideal para o
    **Agendador de Tarefas do Windows** (ou `cron` no Mac/Linux) toda sexta-feira.
- No Instagram, a busca usa a hashtag equivalente (`#limpezaporcelanatomanchado`).

## Módulo 2 — Máquina de Conteúdo

1. **Tema**: escolha um 🔥 Assunto Quente (ou escreva um tema livre), a persona e a plataforma.
2. **🌡️ Termômetro**: busca os vídeos concorrentes na Apify e calcula o **Score de Viralização**
   (50% números reais — views e engajamento — e 50% avaliação da IA), mostra os concorrentes e
   aponta a **Lacuna**. Validações dos últimos 7 dias são reaproveitadas para economizar créditos.
3. **Funil e Formato**: Topo, Meio ou Fundo; a IA sugere os 3 melhores formatos.
4. **Roteiro**: gancho de 3s, roteiro técnico (Áudio x Tela) ou lâminas do carrossel, legenda,
   CTA e hashtags — tudo editável. **Salvar no Cofre** envia para "Roteiros Prontos" (Módulo 3).

## Módulo 3 — Cofre de Ideias (Kanban)

- Colunas: **💡 Ideias no Radar → 📝 Roteiros Prontos → 🎬 Em Edição → ✅ Postado**. Use ◀ ▶ nos cards.
- Ao mover para **Postado**, informe a data (e o link): o Dashboard pede as métricas 7 e 14 dias depois.
- Filtros por persona, plataforma, funil e busca por texto.
- **💡 Nova ideia** cria um card simples; o botão **⚙️** leva a ideia para a Máquina de Conteúdo e,
  ao salvar o roteiro lá, o próprio card avança para "Roteiros Prontos" (sem duplicar).
- **📂 Dossiê**: roteiro editável, referências (Assunto Quente, validação, lacuna, links), linha do
  tempo de tudo o que aconteceu com o card e métricas.
- **♻️ Reciclar** (cards postados): a IA reescreve o conteúdo em outro formato, usando o original e
  as métricas dele; a nova versão vira um card em "Roteiros Prontos", ligada ao post de origem.

> Os nomes e formatos dos coletores da Apify ficam em `services/scraper.py`
> (`ATORES_APIFY`, `ATORES_BUSCA_APIFY`, `_input_apify`, `_input_busca`).

## Testes

```bash
pip install pytest
python -m pytest -q
```
