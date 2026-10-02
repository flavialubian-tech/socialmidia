"""Camada de persistência (SQLite) da Social Mídia Autônoma.

Todas as tabelas dos módulos 0 a 4 são criadas aqui, para que os módulos
conversem entre si desde o início (ex.: um "Assunto Quente" do Módulo 1 vira
um conteúdo no Módulo 2, que vira um card no Kanban do Módulo 3, que recebe
métricas no Dashboard).

Uso básico:
    from database import init_db, get_connection
    init_db()
    with get_connection() as conn:
        conn.execute("SELECT * FROM personas")
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SOCIALMIDIA_DB_PATH", BASE_DIR / "data" / "socialmidia.db"))

# Incrementar sempre que uma migração for adicionada em MIGRATIONS.
SCHEMA_VERSION = 1

# Valores controlados (espelhados nos CHECKs do schema)
PLATAFORMAS = ("instagram", "tiktok", "youtube", "multiplataforma")
STATUS_KANBAN = ("ideia", "roteiro_pronto", "em_edicao", "postado")
STATUS_KANBAN_LABELS = {
    "ideia": "Ideias no Radar",
    "roteiro_pronto": "Roteiros Prontos",
    "em_edicao": "Em Edição",
    "postado": "Postado",
}
NIVEIS_FUNIL = ("topo", "meio", "fundo")
MARCOS_METRICAS = (7, 14)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA_V1 = """
-- =========================================================
-- MÓDULO 1 — CÉREBRO
-- =========================================================
CREATE TABLE IF NOT EXISTS personas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                TEXT    NOT NULL UNIQUE,
    plataforma          TEXT    NOT NULL DEFAULT 'instagram'
                        CHECK (plataforma IN ('instagram','tiktok','youtube','multiplataforma')),
    publico_alvo        TEXT    NOT NULL DEFAULT '',
    tom_de_voz          TEXT    NOT NULL DEFAULT '',
    palavras_proibidas  TEXT    NOT NULL DEFAULT '[]',   -- JSON: lista de strings
    descricao           TEXT    NOT NULL DEFAULT '',
    ativo               INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0,1)),
    criado_em           TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    atualizado_em       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Cada execução do Radar de Audiência sobre uma URL
CREATE TABLE IF NOT EXISTS radar_buscas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id          INTEGER REFERENCES personas(id) ON DELETE SET NULL,
    url                 TEXT    NOT NULL,
    plataforma          TEXT    NOT NULL DEFAULT 'desconhecida',
    metodo_coleta       TEXT    NOT NULL DEFAULT 'manual',  -- apify | bs4 | selenium | manual
    status              TEXT    NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente','coletando','analisando','concluido','erro')),
    total_comentarios   INTEGER NOT NULL DEFAULT 0,
    erro                TEXT,
    agendada            INTEGER NOT NULL DEFAULT 0 CHECK (agendada IN (0,1)),  -- v2: schedule
    criado_em           TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS comentarios (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    busca_id            INTEGER NOT NULL REFERENCES radar_buscas(id) ON DELETE CASCADE,
    autor               TEXT,
    texto               TEXT    NOT NULL,
    curtidas            INTEGER NOT NULL DEFAULT 0,
    publicado_em        TEXT,
    coletado_em         TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Resultado da IA sobre os comentários de uma busca
CREATE TABLE IF NOT EXISTS analises_audiencia (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    busca_id            INTEGER NOT NULL REFERENCES radar_buscas(id) ON DELETE CASCADE,
    persona_id          INTEGER REFERENCES personas(id) ON DELETE SET NULL,
    dores               TEXT    NOT NULL DEFAULT '[]',   -- JSON: [{dor, evidencia, frequencia}]
    dicionario          TEXT    NOT NULL DEFAULT '[]',   -- JSON: [{termo, significado}]
    tendencias          TEXT    NOT NULL DEFAULT '[]',   -- JSON: [{tema, motivo}]
    resumo              TEXT    NOT NULL DEFAULT '',
    modelo_llm          TEXT,
    criado_em           TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- "Assuntos Quentes": ponte entre o Módulo 1 (e o Dashboard) e o Módulo 2
CREATE TABLE IF NOT EXISTS assuntos_quentes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id          INTEGER REFERENCES personas(id) ON DELETE SET NULL,
    analise_id          INTEGER REFERENCES analises_audiencia(id) ON DELETE SET NULL,
    conteudo_origem_id  INTEGER REFERENCES conteudos(id) ON DELETE SET NULL,  -- quando vem de "Reciclar"
    tema                TEXT    NOT NULL,
    descricao           TEXT    NOT NULL DEFAULT '',
    intensidade         INTEGER NOT NULL DEFAULT 50 CHECK (intensidade BETWEEN 0 AND 100),
    origem              TEXT    NOT NULL DEFAULT 'radar'
                        CHECK (origem IN ('radar','reciclagem','manual')),
    status              TEXT    NOT NULL DEFAULT 'novo'
                        CHECK (status IN ('novo','em_uso','usado','descartado')),
    criado_em           TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- =========================================================
-- MÓDULO 2 — MÁQUINA DE CONTEÚDO
-- =========================================================
-- Termômetro de Validação
CREATE TABLE IF NOT EXISTS validacoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    assunto_id          INTEGER REFERENCES assuntos_quentes(id) ON DELETE SET NULL,
    tema                TEXT    NOT NULL,
    score_viralizacao   INTEGER CHECK (score_viralizacao BETWEEN 0 AND 100),
    concorrentes        TEXT    NOT NULL DEFAULT '[]',   -- JSON: [{titulo, url, resumo}]
    lacuna              TEXT    NOT NULL DEFAULT '',
    criado_em           TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- =========================================================
-- MÓDULO 3 — COFRE DE IDEIAS (o card do Kanban)
-- =========================================================
CREATE TABLE IF NOT EXISTS conteudos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id          INTEGER REFERENCES personas(id) ON DELETE SET NULL,
    assunto_id          INTEGER REFERENCES assuntos_quentes(id) ON DELETE SET NULL,
    validacao_id        INTEGER REFERENCES validacoes(id) ON DELETE SET NULL,
    conteudo_pai_id     INTEGER REFERENCES conteudos(id) ON DELETE SET NULL,  -- versão reciclada
    titulo              TEXT    NOT NULL,
    funil               TEXT    CHECK (funil IN ('topo','meio','fundo')),
    formato             TEXT,                             -- Vídeo POV, Voiceover, Carrossel...
    gancho              TEXT    NOT NULL DEFAULT '',
    roteiro             TEXT    NOT NULL DEFAULT '[]',   -- JSON: [{audio, tela}]
    legenda             TEXT    NOT NULL DEFAULT '',
    hashtags            TEXT    NOT NULL DEFAULT '[]',   -- JSON: lista de strings
    referencias         TEXT    NOT NULL DEFAULT '[]',   -- JSON: lista de URLs/notas
    status              TEXT    NOT NULL DEFAULT 'ideia'
                        CHECK (status IN ('ideia','roteiro_pronto','em_edicao','postado')),
    url_publicacao      TEXT,
    data_postagem       TEXT,                             -- 'YYYY-MM-DD'
    criado_em           TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    atualizado_em       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Linha do tempo do Dossiê
CREATE TABLE IF NOT EXISTS historico_conteudo (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    conteudo_id         INTEGER NOT NULL REFERENCES conteudos(id) ON DELETE CASCADE,
    evento              TEXT    NOT NULL,   -- criado | status_alterado | roteiro_editado | reciclado ...
    detalhes            TEXT    NOT NULL DEFAULT '',
    criado_em           TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- =========================================================
-- MÓDULO 0 — DASHBOARD
-- =========================================================
CREATE TABLE IF NOT EXISTS metricas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    conteudo_id         INTEGER NOT NULL REFERENCES conteudos(id) ON DELETE CASCADE,
    marco_dias          INTEGER NOT NULL CHECK (marco_dias IN (7,14)),
    views               INTEGER NOT NULL DEFAULT 0 CHECK (views >= 0),
    saves               INTEGER NOT NULL DEFAULT 0 CHECK (saves >= 0),
    shares              INTEGER NOT NULL DEFAULT 0 CHECK (shares >= 0),
    comments            INTEGER NOT NULL DEFAULT 0 CHECK (comments >= 0),
    likes               INTEGER NOT NULL DEFAULT 0 CHECK (likes >= 0),
    registrado_em       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (conteudo_id, marco_dias)
);

-- =========================================================
-- MÓDULO 4 — ESTÚDIO
-- =========================================================
CREATE TABLE IF NOT EXISTS templates_carrossel (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id          INTEGER REFERENCES personas(id) ON DELETE SET NULL,
    nome                TEXT    NOT NULL,
    caminho_imagem      TEXT    NOT NULL,
    fonte               TEXT,
    tamanho_fonte       INTEGER NOT NULL DEFAULT 64,
    cor_texto           TEXT    NOT NULL DEFAULT '#FFFFFF',
    margem              INTEGER NOT NULL DEFAULT 80,
    criado_em           TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS jobs_midia (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    conteudo_id         INTEGER REFERENCES conteudos(id) ON DELETE SET NULL,
    tipo                TEXT    NOT NULL CHECK (tipo IN ('video','carrossel')),
    arquivo_entrada     TEXT,
    arquivo_saida       TEXT,
    status              TEXT    NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente','processando','concluido','erro')),
    erro                TEXT,
    criado_em           TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- =========================================================
-- CONFIGURAÇÕES GERAIS (provedor de LLM, limiares do Dashboard...)
-- =========================================================
CREATE TABLE IF NOT EXISTS configuracoes (
    chave               TEXT PRIMARY KEY,
    valor               TEXT NOT NULL
);

-- =========================================================
-- Índices
-- =========================================================
CREATE INDEX IF NOT EXISTS idx_comentarios_busca      ON comentarios(busca_id);
CREATE INDEX IF NOT EXISTS idx_analises_busca         ON analises_audiencia(busca_id);
CREATE INDEX IF NOT EXISTS idx_assuntos_persona       ON assuntos_quentes(persona_id, status);
CREATE INDEX IF NOT EXISTS idx_conteudos_status       ON conteudos(status, persona_id);
CREATE INDEX IF NOT EXISTS idx_historico_conteudo     ON historico_conteudo(conteudo_id);
CREATE INDEX IF NOT EXISTS idx_metricas_conteudo      ON metricas(conteudo_id);

-- =========================================================
-- Triggers: atualizado_em automático
-- =========================================================
CREATE TRIGGER IF NOT EXISTS trg_personas_atualizado
AFTER UPDATE ON personas FOR EACH ROW WHEN NEW.atualizado_em = OLD.atualizado_em
BEGIN
    UPDATE personas SET atualizado_em = datetime('now','localtime') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_conteudos_atualizado
AFTER UPDATE ON conteudos FOR EACH ROW WHEN NEW.atualizado_em = OLD.atualizado_em
BEGIN
    UPDATE conteudos SET atualizado_em = datetime('now','localtime') WHERE id = NEW.id;
END;

-- Registra no Dossiê toda mudança de coluna do Kanban
CREATE TRIGGER IF NOT EXISTS trg_conteudos_status
AFTER UPDATE OF status ON conteudos FOR EACH ROW WHEN NEW.status <> OLD.status
BEGIN
    INSERT INTO historico_conteudo (conteudo_id, evento, detalhes)
    VALUES (NEW.id, 'status_alterado', OLD.status || ' -> ' || NEW.status);
END;
"""

CONFIGURACOES_PADRAO = {
    "llm_provedor": "ollama",          # ollama | openai | anthropic
    "llm_modelo_ollama": "llama3.1",
    "llm_modelo_openai": "gpt-4o-mini",
    "llm_modelo_anthropic": "claude-sonnet-5-5",
    "llm_temperatura": "0.7",
    "radar_limite_comentarios": "300",
    "metricas_limiar_views": "10000",  # acima disso o Dashboard sugere "Reciclar este tema"
    "metricas_limiar_saves": "500",
}

# Migrações futuras: {versao: "SQL"}. Executadas em ordem quando user_version < versao.
MIGRATIONS: dict[int, str] = {
    1: SCHEMA_V1,
}


# ---------------------------------------------------------------------------
# Conexão
# ---------------------------------------------------------------------------
def _connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, detect_types=0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # leituras do Streamlit não bloqueiam escritas
    return conn


@contextmanager
def get_connection(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Abre uma conexão, faz commit ao final (ou rollback em caso de erro) e fecha."""
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> None:
    """Cria/migra o schema e insere as configurações padrão. Idempotente."""
    with get_connection(db_path) as conn:
        versao_atual = conn.execute("PRAGMA user_version").fetchone()[0]
        for versao in sorted(MIGRATIONS):
            if versao > versao_atual:
                conn.executescript(MIGRATIONS[versao])
                conn.execute(f"PRAGMA user_version = {versao}")
        conn.executemany(
            "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)",
            CONFIGURACOES_PADRAO.items(),
        )


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def to_json(valor: Any) -> str:
    return json.dumps(valor if valor is not None else [], ensure_ascii=False)


def from_json(texto: str | None, padrao: Any = None) -> Any:
    if not texto:
        return [] if padrao is None else padrao
    try:
        return json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        return [] if padrao is None else padrao


def row_to_dict(row: sqlite3.Row | None, campos_json: tuple[str, ...] = ()) -> dict | None:
    if row is None:
        return None
    dados = dict(row)
    for campo in campos_json:
        if campo in dados:
            dados[campo] = from_json(dados[campo])
    return dados


# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------
def get_config(chave: str, padrao: str | None = None) -> str | None:
    with get_connection() as conn:
        row = conn.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,)).fetchone()
    return row["valor"] if row else padrao


def set_config(chave: str, valor: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO configuracoes (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (chave, str(valor)),
        )


# ---------------------------------------------------------------------------
# Personas (base do Módulo 1)
# ---------------------------------------------------------------------------
_PERSONA_JSON = ("palavras_proibidas",)


def listar_personas(somente_ativas: bool = True) -> list[dict]:
    sql = "SELECT * FROM personas"
    if somente_ativas:
        sql += " WHERE ativo = 1"
    sql += " ORDER BY nome COLLATE NOCASE"
    with get_connection() as conn:
        return [row_to_dict(r, _PERSONA_JSON) for r in conn.execute(sql)]


def obter_persona(persona_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
    return row_to_dict(row, _PERSONA_JSON)


def criar_persona(
    nome: str,
    plataforma: str = "instagram",
    publico_alvo: str = "",
    tom_de_voz: str = "",
    palavras_proibidas: list[str] | None = None,
    descricao: str = "",
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO personas (nome, plataforma, publico_alvo, tom_de_voz,
                                     palavras_proibidas, descricao)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (nome.strip(), plataforma, publico_alvo, tom_de_voz,
             to_json(palavras_proibidas or []), descricao),
        )
        return cur.lastrowid


def atualizar_persona(persona_id: int, **campos: Any) -> None:
    permitidos = {"nome", "plataforma", "publico_alvo", "tom_de_voz",
                  "palavras_proibidas", "descricao", "ativo"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    if not campos:
        return
    if "palavras_proibidas" in campos:
        campos["palavras_proibidas"] = to_json(campos["palavras_proibidas"])
    sets = ", ".join(f"{k} = ?" for k in campos)
    with get_connection() as conn:
        conn.execute(f"UPDATE personas SET {sets} WHERE id = ?", (*campos.values(), persona_id))


def excluir_persona(persona_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM personas WHERE id = ?", (persona_id,))


# ---------------------------------------------------------------------------
# Radar de Audiência (Módulo 1)
# ---------------------------------------------------------------------------
_ANALISE_JSON = ("dores", "dicionario", "tendencias")


def criar_busca(url: str, plataforma: str, metodo_coleta: str, persona_id: int | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO radar_buscas (url, plataforma, metodo_coleta, persona_id) VALUES (?, ?, ?, ?)",
            (url, plataforma, metodo_coleta, persona_id),
        )
        return cur.lastrowid


def atualizar_busca(busca_id: int, **campos: Any) -> None:
    permitidos = {"status", "total_comentarios", "erro", "plataforma", "metodo_coleta"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    if not campos:
        return
    sets = ", ".join(f"{k} = ?" for k in campos)
    with get_connection() as conn:
        conn.execute(f"UPDATE radar_buscas SET {sets} WHERE id = ?", (*campos.values(), busca_id))


def listar_buscas(persona_id: int | None = None, limite: int = 50) -> list[dict]:
    sql = """SELECT b.*, p.nome AS persona,
                    (SELECT a.id FROM analises_audiencia a WHERE a.busca_id = b.id
                     ORDER BY a.id DESC LIMIT 1) AS analise_id
             FROM radar_buscas b LEFT JOIN personas p ON p.id = b.persona_id"""
    params: list[Any] = []
    if persona_id:
        sql += " WHERE b.persona_id = ?"
        params.append(persona_id)
    sql += " ORDER BY b.id DESC LIMIT ?"
    params.append(limite)
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def excluir_busca(busca_id: int) -> None:
    """Remove a busca, seus comentários e análises (assuntos quentes gerados são mantidos)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM radar_buscas WHERE id = ?", (busca_id,))


def salvar_comentarios(busca_id: int, comentarios: list[dict]) -> int:
    linhas = [
        (busca_id, c.get("autor"), c["texto"], int(c.get("curtidas") or 0), c.get("publicado_em"))
        for c in comentarios
        if (c.get("texto") or "").strip()
    ]
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO comentarios (busca_id, autor, texto, curtidas, publicado_em) VALUES (?, ?, ?, ?, ?)",
            linhas,
        )
        conn.execute("UPDATE radar_buscas SET total_comentarios = ? WHERE id = ?", (len(linhas), busca_id))
    return len(linhas)


def listar_comentarios(busca_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT autor, texto, curtidas, publicado_em FROM comentarios WHERE busca_id = ? "
            "ORDER BY curtidas DESC, id",
            (busca_id,),
        )
        return [dict(r) for r in rows]


def salvar_analise(busca_id: int, persona_id: int | None, analise: dict, modelo_llm: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO analises_audiencia (busca_id, persona_id, dores, dicionario, tendencias,
                                               resumo, modelo_llm)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (busca_id, persona_id, to_json(analise.get("dores")), to_json(analise.get("dicionario")),
             to_json(analise.get("tendencias")), analise.get("resumo", ""), modelo_llm),
        )
        return cur.lastrowid


def obter_analise(analise_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT a.*, b.url, b.plataforma, b.total_comentarios, p.nome AS persona
               FROM analises_audiencia a
               JOIN radar_buscas b ON b.id = a.busca_id
               LEFT JOIN personas p ON p.id = a.persona_id
               WHERE a.id = ?""",
            (analise_id,),
        ).fetchone()
    return row_to_dict(row, _ANALISE_JSON)


# ---------------------------------------------------------------------------
# Assuntos Quentes (ponte Módulo 1 -> Módulo 2)
# ---------------------------------------------------------------------------
def criar_assunto_quente(
    tema: str,
    descricao: str = "",
    intensidade: int = 50,
    persona_id: int | None = None,
    analise_id: int | None = None,
    origem: str = "radar",
    conteudo_origem_id: int | None = None,
) -> int | None:
    """Cria o assunto; retorna None se já existe um igual ainda ativo para a mesma persona."""
    tema = tema.strip()
    intensidade = max(0, min(100, int(intensidade)))
    with get_connection() as conn:
        duplicado = conn.execute(
            """SELECT id FROM assuntos_quentes
               WHERE lower(tema) = lower(?) AND persona_id IS ? AND status IN ('novo','em_uso')""",
            (tema, persona_id),
        ).fetchone()
        if duplicado:
            return None
        cur = conn.execute(
            """INSERT INTO assuntos_quentes (tema, descricao, intensidade, persona_id, analise_id,
                                             origem, conteudo_origem_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tema, descricao, intensidade, persona_id, analise_id, origem, conteudo_origem_id),
        )
        return cur.lastrowid


def listar_assuntos_quentes(persona_id: int | None = None, status: tuple[str, ...] | None = ("novo",)) -> list[dict]:
    sql = """SELECT q.*, p.nome AS persona FROM assuntos_quentes q
             LEFT JOIN personas p ON p.id = q.persona_id WHERE 1 = 1"""
    params: list[Any] = []
    if persona_id:
        sql += " AND q.persona_id = ?"
        params.append(persona_id)
    if status:
        sql += f" AND q.status IN ({', '.join('?' * len(status))})"
        params.extend(status)
    sql += " ORDER BY q.intensidade DESC, q.id DESC"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def atualizar_status_assunto(assunto_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE assuntos_quentes SET status = ? WHERE id = ?", (status, assunto_id))


# ---------------------------------------------------------------------------
# Alertas de métricas (base do Módulo 0)
# ---------------------------------------------------------------------------
def listar_alertas_metricas(hoje: date | None = None) -> list[dict]:
    """Conteúdos 'postado' que já passaram de 7/14 dias sem métricas registradas."""
    hoje_str = (hoje or date.today()).isoformat()
    sql = """
        SELECT c.id AS conteudo_id, c.titulo, c.data_postagem, p.nome AS persona,
               m.marco AS marco_dias,
               CAST(julianday(?) - julianday(c.data_postagem) AS INTEGER) AS dias_desde_postagem
        FROM conteudos c
        CROSS JOIN (SELECT 7 AS marco UNION ALL SELECT 14) m
        LEFT JOIN personas p ON p.id = c.persona_id
        WHERE c.status = 'postado'
          AND c.data_postagem IS NOT NULL
          AND julianday(?) - julianday(c.data_postagem) >= m.marco
          AND NOT EXISTS (SELECT 1 FROM metricas mt
                          WHERE mt.conteudo_id = c.id AND mt.marco_dias = m.marco)
        ORDER BY c.data_postagem, m.marco
    """
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, (hoje_str, hoje_str))]


def contar_conteudos_por_status() -> dict[str, int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS total FROM conteudos GROUP BY status")
        contagem = {s: 0 for s in STATUS_KANBAN}
        contagem.update({r["status"]: r["total"] for r in rows})
    return contagem


if __name__ == "__main__":
    init_db()
    print(f"Banco inicializado em: {DB_PATH} (schema v{SCHEMA_VERSION}) — {datetime.now():%d/%m/%Y %H:%M}")
