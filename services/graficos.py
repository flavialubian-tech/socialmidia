"""Gráficos do Dashboard (Plotly).

Regras seguidas: uma série por gráfico (uma cor só, sem legenda), um único eixo, marcas finas
com ponta arredondada, grade discreta, tooltip ao passar o mouse e textos em tons neutros.
Cores validadas (contraste >= 3:1) para fundo claro e escuro.
"""

from __future__ import annotations

import plotly.graph_objects as go

TEMAS = {
    "light": {"serie": "#2a78d6", "texto": "#0b0b0b", "texto2": "#52514e", "grade": "#e7e6e2",
              "superficie": "#fcfcfb"},
    "dark": {"serie": "#3987e5", "texto": "#ffffff", "texto2": "#c3c2b7", "grade": "#383835",
             "superficie": "#1a1a19"},
}
CONFIG_PLOTLY = {"displayModeBar": False, "locale": "pt-BR"}


def _br(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def _layout(fig: go.Figure, tema: str, altura: int) -> go.Figure:
    t = TEMAS.get(tema, TEMAS["light"])
    fig.update_layout(
        height=altura, margin={"l": 8, "r": 16, "t": 8, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "sans-serif", "size": 13, "color": t["texto2"]},
        showlegend=False, bargap=0.45, barcornerradius=4,
        hoverlabel={"bgcolor": t["superficie"], "bordercolor": t["grade"], "font": {"color": t["texto"]}},
        separators=",.",
    )
    eixos = {"gridcolor": t["grade"], "zeroline": False, "linecolor": t["grade"], "automargin": True,
             "tickfont": {"color": t["texto2"], "size": 12}, "title_font": {"color": t["texto2"], "size": 12}}
    fig.update_xaxes(**eixos)
    fig.update_yaxes(**eixos)
    return fig


def _rotulo_curto(texto: str, limite: int = 38) -> str:
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def barras_top_views(linhas: list[dict], tema: str = "light", top: int = 10) -> go.Figure:
    """Ranking horizontal dos posts com mais views (métrica mais recente de cada um)."""
    dados = sorted([l for l in linhas if l["views"] is not None], key=lambda l: l["views"])[-top:]
    t = TEMAS.get(tema, TEMAS["light"])
    fig = go.Figure(go.Bar(
        x=[l["views"] for l in dados],
        y=[f"#{l['id']} {_rotulo_curto(l['titulo'])}" for l in dados],
        orientation="h", marker={"color": t["serie"]},
        customdata=[[l["titulo"], l["formato"] or "—", l["marco_dias"], _br(l["saves"])] for l in dados],
        hovertemplate="<b>%{customdata[0]}</b><br>%{x:,.0f} views em %{customdata[2]} dias<br>"
                      "%{customdata[3]} salvamentos · %{customdata[1]}<extra></extra>",
    ))
    fig.update_xaxes(title_text="Views", rangemode="tozero", tickformat=",d")
    fig.update_yaxes(showgrid=False)
    return _layout(fig, tema, max(220, 40 * len(dados) + 60))


def barras_salvamento_por_formato(linhas: list[dict], tema: str = "light") -> go.Figure:
    """Taxa média de salvamento (salvamentos / views) por formato — o que o público guarda."""
    grupos: dict[str, list[float]] = {}
    for l in linhas:
        if l["views"]:
            grupos.setdefault(l["formato"] or "Sem formato", []).append(l["saves"] / l["views"])
    dados = sorted(((f, sum(v) / len(v), len(v)) for f, v in grupos.items()), key=lambda d: d[1])
    t = TEMAS.get(tema, TEMAS["light"])
    fig = go.Figure(go.Bar(
        x=[d[1] * 100 for d in dados], y=[_rotulo_curto(d[0], 30) for d in dados], orientation="h",
        marker={"color": t["serie"]}, customdata=[[d[0], d[2]] for d in dados],
        hovertemplate="<b>%{customdata[0]}</b><br>%{x:.1f}% de salvamento<br>"
                      "média de %{customdata[1]} post(s)<extra></extra>",
    ))
    fig.update_xaxes(title_text="Taxa de salvamento (%)", rangemode="tozero", ticksuffix="%")
    fig.update_yaxes(showgrid=False)
    return _layout(fig, tema, max(220, 44 * len(dados) + 60))


def linha_views_no_tempo(linhas: list[dict], tema: str = "light") -> go.Figure:
    """Views de cada post pela data de publicação (linha fina com marcadores)."""
    dados = [l for l in linhas if l["views"] is not None]
    t = TEMAS.get(tema, TEMAS["light"])
    fig = go.Figure(go.Scatter(
        x=[l["data_postagem"] for l in dados], y=[l["views"] for l in dados], mode="lines+markers",
        line={"color": t["serie"], "width": 2},
        marker={"color": t["serie"], "size": 9, "line": {"color": t["superficie"], "width": 2}},
        customdata=[[l["titulo"], l["formato"] or "—"] for l in dados],
        hovertemplate="<b>%{customdata[0]}</b><br>%{x|%d/%m/%Y} · %{customdata[1]}<br>"
                      "%{y:,.0f} views<extra></extra>",
    ))
    fig.update_xaxes(title_text="Data da postagem", tickformat="%d/%m", showgrid=False)
    fig.update_yaxes(title_text="Views", rangemode="tozero", tickformat=",d")
    return _layout(fig, tema, 300)
