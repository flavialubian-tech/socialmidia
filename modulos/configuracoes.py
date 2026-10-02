"""Configurações gerais: provedor de IA, modelos e chaves de API."""

import os

import streamlit as st

import database as db
from services.llm import CHAVES_API, PROVEDORES, ConfigLLM, LLMError, testar_conexao

st.title("⚙️ Configurações")

# ---------------------------------------------------------------------------
# Inteligência Artificial
# ---------------------------------------------------------------------------
st.subheader("🤖 Inteligência Artificial")
provedores = list(PROVEDORES)
provedor_atual = db.get_config("llm_provedor", "ollama")

with st.form("form_llm"):
    provedor = st.radio("Provedor padrão", provedores, index=provedores.index(provedor_atual),
                        format_func=PROVEDORES.get, horizontal=True)
    c1, c2, c3 = st.columns(3)
    modelos = {
        "ollama": c1.text_input("Modelo Ollama", db.get_config("llm_modelo_ollama", ""),
                                help="Precisa estar baixado: `ollama pull llama3.1`"),
        "openai": c2.text_input("Modelo OpenAI", db.get_config("llm_modelo_openai", "")),
        "anthropic": c3.text_input("Modelo Claude", db.get_config("llm_modelo_anthropic", "")),
    }
    temperatura = st.slider("Criatividade (temperatura)", 0.0, 1.0,
                            float(db.get_config("llm_temperatura", "0.7")), 0.1,
                            help="Mais baixo = respostas mais previsíveis; mais alto = mais criativas.")
    if st.form_submit_button("💾 Salvar", type="primary"):
        db.set_config("llm_provedor", provedor)
        db.set_config("llm_temperatura", temperatura)
        for nome, modelo in modelos.items():
            db.set_config(f"llm_modelo_{nome}", modelo.strip())
        st.success("Configurações salvas!")

if st.button("🔌 Testar conexão com a IA"):
    provedor = db.get_config("llm_provedor")
    cfg = ConfigLLM(provedor, db.get_config(f"llm_modelo_{provedor}", ""), 0.0)
    with st.spinner(f"Chamando {cfg.rotulo}..."):
        try:
            st.success(f"Funcionou! Resposta: {testar_conexao(cfg)}")
        except LLMError as exc:
            st.error(str(exc))

# ---------------------------------------------------------------------------
# Chaves de API
# ---------------------------------------------------------------------------
st.subheader("🔑 Chaves de API")
st.caption("As chaves do arquivo `.env` têm prioridade. As salvas aqui ficam apenas no banco local deste computador.")

SEGREDOS = {
    CHAVES_API["openai"]: "OpenAI",
    CHAVES_API["anthropic"]: "Anthropic (Claude)",
    "APIFY_API_TOKEN": "Apify (coleta automática de comentários)",
    "OLLAMA_BASE_URL": "Endereço do Ollama",
}

for nome, rotulo in SEGREDOS.items():
    no_env = bool(os.getenv(nome))
    salvo = db.get_config(f"segredo_{nome}")
    c1, c2 = st.columns([3, 1])
    if no_env:
        c1.text_input(rotulo, value="definida no .env", disabled=True, key=f"seg_{nome}")
        continue
    valor = c1.text_input(rotulo, type="default" if nome == "OLLAMA_BASE_URL" else "password",
                          placeholder="configurada ✔" if salvo else "não configurada", key=f"seg_{nome}")
    c2.write("")
    c2.write("")
    if c2.button("Salvar", key=f"salvar_{nome}", disabled=not valor.strip()):
        db.set_config(f"segredo_{nome}", valor.strip())
        st.toast(f"{rotulo} salvo.", icon="🔑")
        st.rerun()

# ---------------------------------------------------------------------------
# Radar
# ---------------------------------------------------------------------------
st.subheader("📡 Radar de Audiência")
limite = st.number_input("Limite padrão de comentários por coleta", 50, 1000,
                         int(db.get_config("radar_limite_comentarios", "300")), 50)
if limite != int(db.get_config("radar_limite_comentarios", "300")):
    db.set_config("radar_limite_comentarios", int(limite))
    st.toast("Limite atualizado.")
