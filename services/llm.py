"""Camada única de acesso a LLMs (Ollama, OpenAI ou Anthropic/Claude) via LangChain.

O provedor e o modelo vêm da tabela `configuracoes`; as chaves de API vêm do
`.env` (prioridade) ou da tela de Configurações.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from database import get_config

PROVEDORES = {
    "ollama": "Ollama (local, gratuito)",
    "openai": "OpenAI (GPT)",
    "anthropic": "Anthropic (Claude)",
}
CHAVES_API = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


class LLMError(RuntimeError):
    """Erro amigável para exibir na interface."""


@dataclass
class ConfigLLM:
    provedor: str
    modelo: str
    temperatura: float

    @property
    def rotulo(self) -> str:
        return f"{self.provedor}:{self.modelo}"


def obter_segredo(nome: str) -> str | None:
    """Lê uma chave do ambiente (.env) ou, em segundo lugar, das configurações salvas."""
    return os.getenv(nome) or get_config(f"segredo_{nome}") or None


def config_atual() -> ConfigLLM:
    provedor = get_config("llm_provedor", "ollama")
    return ConfigLLM(
        provedor=provedor,
        modelo=get_config(f"llm_modelo_{provedor}", ""),
        temperatura=float(get_config("llm_temperatura", "0.7")),
    )


def criar_llm(config: ConfigLLM | None = None, json_mode: bool = False) -> BaseChatModel:
    config = config or config_atual()
    if not config.modelo:
        raise LLMError(f"Nenhum modelo configurado para '{config.provedor}'. Ajuste em ⚙️ Configurações.")

    if config.provedor == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=config.modelo,
            temperature=config.temperatura,
            base_url=obter_segredo("OLLAMA_BASE_URL") or "http://localhost:11434",
            format="json" if json_mode else None,
            num_ctx=8192,  # janela maior que o padrão do Ollama, para caber o lote de comentários
        )

    chave = obter_segredo(CHAVES_API.get(config.provedor, ""))
    if config.provedor == "openai":
        if not chave:
            raise LLMError("OPENAI_API_KEY não configurada. Adicione no .env ou em ⚙️ Configurações.")
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {}
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(model=config.modelo, temperature=config.temperatura, api_key=chave, **kwargs)

    if config.provedor == "anthropic":
        if not chave:
            raise LLMError("ANTHROPIC_API_KEY não configurada. Adicione no .env ou em ⚙️ Configurações.")
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=config.modelo, temperature=config.temperatura, api_key=chave, max_tokens=8000)

    raise LLMError(f"Provedor desconhecido: {config.provedor}")


def _texto_da_resposta(resposta: Any) -> str:
    conteudo = getattr(resposta, "content", resposta)
    if isinstance(conteudo, list):  # alguns provedores devolvem blocos
        conteudo = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in conteudo)
    return str(conteudo)


def extrair_json(texto: str) -> dict:
    """Extrai o primeiro objeto JSON de uma resposta (tolera ```json ... ``` e texto extra)."""
    texto = re.sub(r"```(?:json)?", "", texto).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fim <= inicio:
        raise LLMError("A IA não retornou um JSON válido.")
    try:
        return json.loads(texto[inicio : fim + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"A IA retornou um JSON malformado: {exc}") from exc


def traduzir_erro(exc: Exception) -> str:
    """Transforma erros técnicos dos provedores em mensagens que dizem o que fazer."""
    texto = str(exc)
    baixo = texto.lower()
    if "llama-server" in baixo or ("status code: 500" in baixo and "ollama" in type(exc).__module__.lower()) \
            or "llama runner" in baixo:
        return ("O Ollama travou no meio da análise — quase sempre é falta de memória do computador para o modelo. "
                "Tente: (1) em ⚙️ Configurações, usar um modelo menor no Ollama, como \"llama3.2:3b\" "
                "(rode antes `ollama pull llama3.2:3b`); ou (2) trocar o provedor para o Claude. "
                f"Detalhe técnico: {texto[:200]}")
    if "connection refused" in baixo or "failed to connect" in baixo or "connecterror" in baixo:
        return ("Não consegui falar com a IA. Se estiver usando o Ollama, confira se ele está aberto "
                "(ícone da lhama perto do relógio). Detalhe: " + texto[:200])
    if "401" in baixo or "authentication" in baixo or "invalid x-api-key" in baixo or "incorrect api key" in baixo:
        return "A chave de API foi recusada. Confira a chave em ⚙️ Configurações."
    if "credit balance" in baixo or "insufficient_quota" in baixo or "billing" in baixo:
        return "A conta da IA está sem créditos. Adicione créditos no site do provedor (Billing)."
    return f"Falha ao chamar a IA: {texto}"


def gerar_texto(prompt: str, sistema: str = "", llm: BaseChatModel | None = None) -> str:
    llm = llm or criar_llm()
    mensagens = ([SystemMessage(sistema)] if sistema else []) + [HumanMessage(prompt)]
    try:
        return _texto_da_resposta(llm.invoke(mensagens))
    except LLMError:
        raise
    except Exception as exc:  # erros de rede/credencial do provedor
        raise LLMError(traduzir_erro(exc)) from exc


def gerar_json(prompt: str, sistema: str = "", llm: BaseChatModel | None = None, tentativas: int = 2) -> dict:
    """Pede uma resposta em JSON; se vier inválida, tenta de novo pedindo correção."""
    llm = llm or criar_llm(json_mode=True)
    ultimo_erro: LLMError | None = None
    for _ in range(tentativas):
        resposta = gerar_texto(prompt, sistema, llm)
        try:
            return extrair_json(resposta)
        except LLMError as exc:
            ultimo_erro = exc
            prompt = f"{prompt}\n\nATENÇÃO: responda APENAS com um objeto JSON válido, sem texto antes ou depois."
    raise ultimo_erro or LLMError("Falha ao gerar JSON.")


def testar_conexao(config: ConfigLLM | None = None) -> str:
    return gerar_texto("Responda apenas: OK", llm=criar_llm(config)).strip()
