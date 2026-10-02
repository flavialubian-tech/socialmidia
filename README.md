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

## Testes

```bash
pip install pytest
python -m pytest -q
```
