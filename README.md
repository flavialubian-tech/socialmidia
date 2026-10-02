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
  m1_cerebro.py         # Personas + Radar de Audiência
  m2_maquina_conteudo.py
  m3_cofre_ideias.py    # Kanban
  m4_estudio.py         # Vídeo automático + carrosséis
services/               # lógica sem Streamlit: llm.py, scraper.py, video.py, carrossel.py...
data/                   # banco, uploads, templates e exportações (fora do git)
```
