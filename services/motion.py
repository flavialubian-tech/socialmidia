"""Motion graphics do Vídeo Automático (Módulo 4).

Tudo é gerado a partir da transcrição, sem arquivos externos:
• Stickers flat design 2D (ícones desenhados aqui, nas cores do app — emoji do sistema muda de
  aparência em cada computador e foge da paleta)
• Tipografia cinética para números e frases de impacto ("3 ERROS", "72 HORAS")
• Abertura com selo do @ (lower third) e CTA final com microanimação de interface (toque no botão)
• Transições nos cortes (flash, zoom com desfoque, glitch)
• Efeitos sonoros sintetizados (whoosh, pop, clique, ding) sincronizados com os elementos
• Acabamento de cinema (cor, vinheta, granulado)

Regras de movimento: nada linear (curvas de services/movimento.py), entradas animam mais de uma
propriedade, elementos entram escalonados e saem mais rápido do que entram.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from services import fontes
from services.movimento import ease_in_out_cubic, ease_out_back, ease_out_cubic, misturar, progresso

VERDE = "#22C55E"
VERMELHO = "#EF4444"
AMARELO = "#FACC15"
LARANJA = "#F97316"
AZUL = "#3B82F6"
ESCURO = "#111111"

# ===========================================================================
# 1. Stickers flat design 2D
# ===========================================================================
ICONES = ("check", "x", "alerta", "ideia", "dinheiro", "tempo", "grafico", "coracao", "estrela", "fogo", "seta")

# palavra (sem acento, minúscula) -> ícone. Radicais com 4+ letras casam pelo começo da palavra.
PALAVRAS_ICONE: list[tuple[str, tuple[str, ...]]] = [
    ("x", ("erro", "errad", "nao", "nunca", "pare", "evite", "evitar", "jamais", "proibid", "pior", "ruim",
           "cuidado com", "mito")),
    ("check", ("certo", "correto", "sim", "funciona", "pode", "verdade", "resolve", "perfeito", "facil")),
    ("alerta", ("atencao", "cuidado", "perigo", "aviso", "risco", "alerta", "importante")),
    ("ideia", ("dica", "ideia", "segredo", "truque", "macete", "descobri", "aprenda", "aprendi")),
    ("dinheiro", ("dinheiro", "reais", "real", "preco", "barat", "caro", "lucr", "vend", "ganh", "economi",
                  "grana", "pag", "invest")),
    ("tempo", ("tempo", "hora", "horas", "minuto", "minutos", "segundo", "rapid", "dia", "dias", "semana")),
    ("grafico", ("cresc", "aument", "result", "resultado", "engaj", "seguidor", "alcance", "escal")),
    ("coracao", ("amo", "amei", "amor", "ador", "paixao", "gosto")),
    ("estrela", ("melhor", "top", "incrivel", "perfeit", "favorit", "sucesso")),
    ("fogo", ("fogo", "viral", "bomb", "quente", "explod", "absurd")),
    ("seta", ("olha", "veja", "aqui", "abaixo", "embaixo", "comenta", "link")),
]


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _limpa(palavra: str) -> str:
    return re.sub(r"[^a-z0-9%$]", "", _sem_acento(palavra))


def icone_da_palavra(palavra: str) -> str | None:
    w = _limpa(palavra)
    if len(w) < 2:
        return None
    for icone, radicais in PALAVRAS_ICONE:
        for r in radicais:
            if " " in r:
                continue
            if w == r or (len(r) >= 4 and w.startswith(r)):
                return icone
    return None


def _estrela(cx, cy, r_ext, r_int, pontas=5):
    pts = []
    for i in range(pontas * 2):
        r = r_ext if i % 2 == 0 else r_int
        ang = -math.pi / 2 + i * math.pi / pontas
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


@lru_cache(maxsize=64)
def desenhar_icone(nome: str, tamanho: int, cor_destaque: str = AMARELO) -> Image.Image:
    """Sticker RGBA: ícone flat + contorno branco + sombra suave (desenhado em 2x e reduzido)."""
    s = tamanho * 2
    forma = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(forma)
    m = s * 0.12  # margem para contorno e sombra
    a, b = m, s - m
    c = s / 2
    lw = max(4, int(s * 0.085))

    if nome == "check":
        d.ellipse((a, a, b, b), fill=VERDE)
        d.line([(s * 0.32, s * 0.52), (s * 0.45, s * 0.65), (s * 0.70, s * 0.38)], fill="white", width=lw,
               joint="curve")
    elif nome == "x":
        d.ellipse((a, a, b, b), fill=VERMELHO)
        d.line([(s * 0.36, s * 0.36), (s * 0.64, s * 0.64)], fill="white", width=lw)
        d.line([(s * 0.64, s * 0.36), (s * 0.36, s * 0.64)], fill="white", width=lw)
    elif nome == "alerta":
        d.polygon([(c, a), (b, b - s * 0.04), (a, b - s * 0.04)], fill=AMARELO)
        d.line([(c, s * 0.40), (c, s * 0.62)], fill=ESCURO, width=lw)
        d.ellipse((c - lw * 0.6, s * 0.70, c + lw * 0.6, s * 0.70 + lw * 1.2), fill=ESCURO)
    elif nome == "ideia":
        d.ellipse((s * 0.26, a, s * 0.74, s * 0.62), fill=AMARELO)
        d.rounded_rectangle((s * 0.38, s * 0.58, s * 0.62, s * 0.80), radius=int(s * 0.04), fill="#9CA3AF")
        d.line([(s * 0.42, s * 0.66), (s * 0.58, s * 0.66)], fill="#6B7280", width=max(2, lw // 3))
        d.line([(s * 0.42, s * 0.73), (s * 0.58, s * 0.73)], fill="#6B7280", width=max(2, lw // 3))
        d.arc((s * 0.34, s * 0.22, s * 0.56, s * 0.44), 180, 270, fill="white", width=max(3, lw // 2))
    elif nome == "dinheiro":
        d.ellipse((a, a, b, b), fill=VERDE)
        d.ellipse((s * 0.2, s * 0.2, s * 0.8, s * 0.8), outline="#16A34A", width=max(3, lw // 2))
        f = fontes.carregar(None, int(s * 0.46))
        d.text((c, c), "$", font=f, fill="white", anchor="mm")
    elif nome == "tempo":
        d.ellipse((a, a, b, b), fill="white", outline=ESCURO, width=lw)
        d.line([(c, c), (c, s * 0.28)], fill=ESCURO, width=lw)
        d.line([(c, c), (s * 0.68, s * 0.58)], fill=VERMELHO, width=lw)
        d.ellipse((c - lw, c - lw, c + lw, c + lw), fill=ESCURO)
    elif nome == "grafico":
        d.rounded_rectangle((a, a, b, b), radius=int(s * 0.12), fill="white")
        for i, (h, cor) in enumerate([(0.25, AZUL), (0.40, AZUL), (0.55, VERDE)]):
            x0 = s * (0.26 + i * 0.17)
            d.rounded_rectangle((x0, s * (0.78 - h), x0 + s * 0.12, s * 0.78), radius=int(s * 0.02), fill=cor)
        d.line([(s * 0.24, s * 0.52), (s * 0.48, s * 0.36), (s * 0.74, s * 0.22)], fill=VERDE, width=max(3, lw // 2))
        d.polygon([(s * 0.78, s * 0.18), (s * 0.66, s * 0.20), (s * 0.75, s * 0.30)], fill=VERDE)
    elif nome == "coracao":
        r = s * 0.2
        d.ellipse((s * 0.5 - 2 * r, s * 0.28, s * 0.5, s * 0.28 + 2 * r), fill=VERMELHO)
        d.ellipse((s * 0.5, s * 0.28, s * 0.5 + 2 * r, s * 0.28 + 2 * r), fill=VERMELHO)
        d.polygon([(s * 0.13, s * 0.45), (s * 0.87, s * 0.45), (c, b)], fill=VERMELHO)
        d.ellipse((s * 0.24, s * 0.34, s * 0.34, s * 0.44), fill="#FCA5A5")
    elif nome == "estrela":
        d.polygon(_estrela(c, s * 0.53, s * 0.40, s * 0.17), fill=AMARELO)
    elif nome == "fogo":
        d.polygon([(c, a), (s * 0.78, s * 0.50), (s * 0.74, s * 0.74), (c, b), (s * 0.26, s * 0.74),
                   (s * 0.22, s * 0.50), (s * 0.38, s * 0.42)], fill=LARANJA)
        d.polygon([(c, s * 0.42), (s * 0.64, s * 0.66), (c, s * 0.82), (s * 0.36, s * 0.66)], fill=AMARELO)
    elif nome == "seta":
        d.rounded_rectangle((s * 0.40, a, s * 0.60, s * 0.58), radius=int(s * 0.05), fill=cor_destaque)
        d.polygon([(s * 0.18, s * 0.50), (s * 0.82, s * 0.50), (c, b)], fill=cor_destaque)
    else:
        raise ValueError(f"Ícone desconhecido: {nome}")

    alfa = forma.getchannel("A")
    contorno = alfa.filter(ImageFilter.MaxFilter(_impar(s * 0.07)))
    sombra = contorno.filter(ImageFilter.GaussianBlur(s * 0.03)).point(lambda v: int(v * 0.45))
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste((0, 0, 0, 255), (0, int(s * 0.03)), sombra)
    img.paste((255, 255, 255, 255), (0, 0), contorno)
    img.alpha_composite(forma)
    return img.resize((tamanho, tamanho), Image.LANCZOS)


def _impar(n: float) -> int:
    n = max(3, int(n))
    return n if n % 2 else n + 1


# ===========================================================================
# 2. Eventos (o que aparece e quando) — derivados da transcrição
# ===========================================================================
_NUMEROS_EXTENSO = {"dois", "tres", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "cem", "mil"}


def _e_numero(palavra: str) -> bool:
    w = _limpa(palavra)
    return bool(re.search(r"\d", w)) or w in _NUMEROS_EXTENSO or w.startswith("r$")


@dataclass
class Evento:
    tipo: str            # sticker | destaque | transicao | abertura | cta
    t: float
    duracao: float
    dados: dict = field(default_factory=dict)


def detectar_eventos(palavras: list[dict], inicios: list[float], duracao: float, *, stickers: bool = True,
                     destaques: bool = True, transicoes: str = "nenhuma", abertura: bool = False,
                     cta: bool = False) -> list[Evento]:
    eventos: list[Evento] = []
    ordenadas = sorted(palavras, key=lambda p: p["inicio"])

    if destaques:
        ultimo = -99.0
        for i, p in enumerate(ordenadas):
            if not _e_numero(p["texto"]) or p["inicio"] - ultimo < 3.0:
                continue
            texto = re.sub(r"[^\wÀ-ú%$,.]", "", p["texto"]).upper().strip(".,")
            if i + 1 < len(ordenadas):
                prox = re.sub(r"[^\wÀ-ú%]", "", ordenadas[i + 1]["texto"]).upper()
                if prox.isalpha() and 2 <= len(prox) <= 12 and ordenadas[i + 1]["inicio"] - p["fim"] < 0.6:
                    texto = f"{texto} {prox}"
            if texto:
                eventos.append(Evento("destaque", p["inicio"], 1.6, {"texto": texto}))
                ultimo = p["inicio"]

    if stickers:
        ultimo, lado = -99.0, 0
        momentos_destaque = [e.t for e in eventos if e.tipo == "destaque"]
        for p in ordenadas:
            icone = icone_da_palavra(p["texto"])
            if not icone or p["inicio"] - ultimo < 2.2:
                continue
            if any(abs(p["inicio"] - t) < 0.9 for t in momentos_destaque):
                continue
            eventos.append(Evento("sticker", p["inicio"], 1.4, {"icone": icone, "lado": lado % 2}))
            ultimo, lado = p["inicio"], lado + 1

    if transicoes and transicoes != "nenhuma":
        estilos = ["flash", "zoom", "glitch"]
        for n, c in enumerate(inicios[1:]):
            estilo = estilos[n % 3] if transicoes == "alternado" else transicoes
            eventos.append(Evento("transicao", c, 0.24, {"estilo": estilo}))

    if abertura:
        eventos.append(Evento("abertura", 0.35, min(3.2, max(1.5, duracao - 0.5))))
    if cta and duracao >= 6:
        inicio_cta = duracao - 2.8
        # nada de sticker/destaque disputando atenção com o CTA final
        eventos = [e for e in eventos if e.tipo not in ("sticker", "destaque") or e.t + e.duracao <= inicio_cta]
        eventos.append(Evento("cta", inicio_cta, 2.8))
    return sorted(eventos, key=lambda e: e.t)


# ===========================================================================
# 3. Desenho dos elementos
# ===========================================================================
def _colar(base: Image.Image, img: Image.Image, cx: float, cy: float, escala: float = 1.0,
           opacidade: float = 1.0) -> None:
    if opacidade <= 0.01 or escala <= 0.01:
        return
    if abs(escala - 1) > 0.01:
        img = img.resize((max(1, int(img.width * escala)), max(1, int(img.height * escala))), Image.BILINEAR)
    if opacidade < 0.99:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda a: int(a * opacidade)))
    base.paste(img, (int(cx - img.width / 2), int(cy - img.height / 2)), img)


@lru_cache(maxsize=128)
def _palavra_cinetica(texto: str, tamanho: int, cor: str, fonte: str | None) -> Image.Image:
    f = fontes.carregar(fonte, tamanho)
    contorno = max(3, tamanho // 12)
    caixa = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), texto, font=f, stroke_width=contorno)
    img = Image.new("RGBA", (caixa[2] - caixa[0] + 8, caixa[3] - caixa[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((4 - caixa[0], 4 - caixa[1]), texto, font=f, fill=cor, stroke_width=contorno,
                             stroke_fill=ESCURO)
    return img


@lru_cache(maxsize=32)
def _cartao_abertura(nome: str, largura: int, cor: str, fonte: str | None) -> tuple[Image.Image, Image.Image]:
    """(avatar, pílula com o @) — peças separadas para entrarem escalonadas."""
    h = max(40, int(largura * 0.11))
    avatar = Image.new("RGBA", (h, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(avatar)
    d.ellipse((0, 0, h - 1, h - 1), fill=cor)
    inicial = (nome.lstrip("@")[:1] or "@").upper()
    d.text((h / 2, h / 2), inicial, font=fontes.carregar(fonte, int(h * 0.55)), fill=ESCURO, anchor="mm")
    f = fontes.carregar(fonte, int(h * 0.42))
    fp = fontes.carregar(str(fontes.FONTE_PADRAO_BOLD), int(h * 0.30))
    largura_txt = int(ImageDraw.Draw(avatar).textlength(nome, font=f))
    chip = "Seguir"
    largura_chip = int(ImageDraw.Draw(avatar).textlength(chip, font=fp)) + int(h * 0.5)
    w = largura_txt + largura_chip + int(h * 1.0)
    pilula = Image.new("RGBA", (w, int(h * 0.82)), (0, 0, 0, 0))
    d = ImageDraw.Draw(pilula)
    d.rounded_rectangle((0, 0, w - 1, pilula.height - 1), radius=pilula.height // 2, fill=(255, 255, 255, 240))
    d.text((int(h * 0.35), pilula.height / 2), nome, font=f, fill=ESCURO, anchor="lm")
    x0 = int(h * 0.35) + largura_txt + int(h * 0.3)
    d.rounded_rectangle((x0, int(pilula.height * 0.2), x0 + largura_chip, int(pilula.height * 0.8)),
                        radius=int(pilula.height * 0.3), fill=cor)
    d.text((x0 + largura_chip / 2, pilula.height / 2), chip, font=fp, fill=ESCURO, anchor="mm")
    return avatar, pilula


CTAS = {
    "salvar": ("SALVA ESSE VÍDEO", "Salvar", "salvar"),
    "seguir": ("SEGUE PRA MAIS DICAS", "Seguir", "seguir"),
    "comentar": ("COMENTA AQUI EMBAIXO", "Comentar", "comentar"),
    "link": ("LINK NA BIO", "Abrir link", "link"),
}


def _icone_cta(tipo: str, s: int, cor: str, preenchido: bool) -> Image.Image:
    img = Image.new("RGBA", (s * 2, s * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    S = s * 2
    lw = max(4, int(S * 0.08))
    preench = cor if preenchido else None
    if tipo == "salvar":
        pts = [(S * 0.28, S * 0.15), (S * 0.72, S * 0.15), (S * 0.72, S * 0.85), (S * 0.5, S * 0.66),
               (S * 0.28, S * 0.85)]
        d.polygon(pts, fill=preench, outline=ESCURO, width=lw)
    elif tipo == "seguir":
        d.ellipse((S * 0.30, S * 0.12, S * 0.62, S * 0.44), fill=preench, outline=ESCURO, width=lw)
        d.pieslice((S * 0.16, S * 0.50, S * 0.76, S * 1.10), 180, 360, fill=preench, outline=ESCURO, width=lw)
        d.line([(S * 0.80, S * 0.30), (S * 0.80, S * 0.58)], fill=ESCURO, width=lw)
        d.line([(S * 0.66, S * 0.44), (S * 0.94, S * 0.44)], fill=ESCURO, width=lw)
    elif tipo == "comentar":
        d.rounded_rectangle((S * 0.12, S * 0.16, S * 0.88, S * 0.70), radius=int(S * 0.14), fill=preench,
                            outline=ESCURO, width=lw)
        d.polygon([(S * 0.30, S * 0.66), (S * 0.46, S * 0.66), (S * 0.26, S * 0.88)], fill=ESCURO)
    else:  # link
        d.rounded_rectangle((S * 0.10, S * 0.36, S * 0.58, S * 0.64), radius=int(S * 0.14), outline=ESCURO, width=lw)
        d.rounded_rectangle((S * 0.42, S * 0.36, S * 0.90, S * 0.64), radius=int(S * 0.14), fill=preench,
                            outline=ESCURO, width=lw)
    return img.resize((s, s), Image.LANCZOS)


@lru_cache(maxsize=16)
def _cartao_cta(tipo: str, largura: int, cor: str, fonte: str | None, preenchido: bool,
                pressionado: bool) -> Image.Image:
    titulo, botao, icone = CTAS.get(tipo, CTAS["salvar"])
    w = int(largura * 0.78)
    h = int(w * 0.62)
    img = Image.new("RGBA", (w, h + 12), (0, 0, 0, 0))
    sombra = Image.new("L", img.size, 0)
    ImageDraw.Draw(sombra).rounded_rectangle((6, 12, w - 6, h + 6), radius=int(w * 0.07), fill=120)
    img.paste((0, 0, 0, 255), (0, 0), sombra.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=int(w * 0.07), fill="white")
    s_icone = int(h * 0.30)
    img.alpha_composite(_icone_cta(icone, s_icone, cor, preenchido), (int(w / 2 - s_icone / 2), int(h * 0.08)))
    f = fontes.carregar(fonte, int(h * 0.12))
    d.text((w / 2, h * 0.52), titulo, font=f, fill=ESCURO, anchor="mm")
    bw, bh = int(w * 0.52), int(h * 0.20)
    encolhe = 0.94 if pressionado else 1.0
    bw2, bh2 = int(bw * encolhe), int(bh * encolhe)
    x0, y0 = int(w / 2 - bw2 / 2), int(h * 0.74 - bh2 / 2)
    d.rounded_rectangle((x0, y0, x0 + bw2, y0 + bh2), radius=bh2 // 2, fill=ESCURO if not preenchido else cor)
    fb = fontes.carregar(str(fontes.FONTE_PADRAO_BOLD), int(bh2 * 0.48))
    d.text((w / 2, h * 0.74), botao, font=fb, fill="white" if not preenchido else ESCURO, anchor="mm")
    return img


class Motion:
    """Aplica os motion graphics sobre cada quadro (já no tamanho final)."""

    def __init__(self, W: int, H: int, eventos: list[Evento], cor_destaque: str = AMARELO, fonte: str | None = None,
                 nome_abertura: str = "", cta_tipo: str = "salvar", acabamento: bool = False,
                 granulado: bool = True):
        self.W, self.H = W, H
        self.eventos = eventos
        self.cor = cor_destaque
        self.fonte = fonte
        self.nome = nome_abertura.strip() or "@seuperfil"
        self.cta_tipo = cta_tipo
        self.acabamento = acabamento
        self.granulado = granulado
        self._vinheta = None
        self._graos: list[np.ndarray] = []
        self._lut = None

    # --- elementos sobre a imagem --------------------------------------------
    def sobrepor(self, img: Image.Image, t: float) -> Image.Image:
        for e in self.eventos:
            if not (e.t - 0.05 <= t <= e.t + e.duracao):
                continue
            metodo = getattr(self, f"_ev_{e.tipo}", None)
            if metodo and e.tipo != "transicao":
                metodo(img, t - e.t, e)
        return img

    def _ev_sticker(self, img: Image.Image, dt: float, e: Evento) -> None:
        tam = int(self.W * 0.17)
        sticker = desenhar_icone(e.dados["icone"], tam, self.cor)
        entrada = progresso(dt, 0, 0.28)
        saida = progresso(dt, e.duracao - 0.16, 0.16)
        escala = ease_out_back(entrada, 2.2) * (1 - ease_out_cubic(saida))
        flutua = math.sin(dt * 6.0) * self.H * 0.004 * (1 - saida)
        cx = self.W * (0.18 if e.dados["lado"] == 0 else 0.82)
        cy = self.H * 0.50 + flutua + misturar(self.H * 0.02, 0, ease_out_cubic(entrada))
        _colar(img, sticker, cx, cy, escala, ease_out_cubic(min(1, entrada * 2)))

    def _ev_destaque(self, img: Image.Image, dt: float, e: Evento) -> None:
        palavras = e.dados["texto"].split()
        tam = int(self.W * 0.13)
        cores = [self.cor, "white"]
        imgs = [_palavra_cinetica(p, tam, cores[i % 2], self.fonte) for i, p in enumerate(palavras)]
        espaco = int(tam * 0.25)
        largura_total = sum(i.width for i in imgs) + espaco * (len(imgs) - 1)
        escala_max = min(1.0, self.W * 0.9 / max(1, largura_total))
        saida = progresso(dt, e.duracao - 0.18, 0.18)
        # barra de destaque (elemento de interface) crescendo atrás das palavras
        pb = ease_out_cubic(progresso(dt, 0.0, 0.25)) * (1 - ease_out_cubic(saida))
        if pb > 0.01:
            camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
            bw = largura_total * escala_max * 1.08 * pb
            bh = max(i.height for i in imgs) * escala_max * 0.55
            cy = self.H * 0.30
            ImageDraw.Draw(camada).rounded_rectangle(
                (self.W / 2 - bw / 2, cy - bh * 0.1, self.W / 2 + bw / 2, cy + bh * 0.9), radius=int(bh * 0.3),
                fill=(17, 17, 17, int(170 * pb)))
            img.paste(camada, (0, 0), camada)
        x = self.W / 2 - largura_total * escala_max / 2
        for i, pimg in enumerate(imgs):
            p = progresso(dt, 0.06 + i * 0.09, 0.30)  # escalonado palavra a palavra
            esc = escala_max * misturar(0.4, 1.0, ease_out_back(p, 2.0)) * misturar(1.0, 0.85, saida)
            op = ease_out_cubic(p) * (1 - ease_out_cubic(saida))
            sobe = misturar(self.H * 0.03, 0, ease_out_cubic(p))
            w_final = pimg.width * escala_max
            _colar(img, pimg, x + w_final / 2, self.H * 0.30 + sobe, esc, op)
            x += w_final + espaco * escala_max

    def _ev_abertura(self, img: Image.Image, dt: float, e: Evento) -> None:
        avatar, pilula = _cartao_abertura(self.nome, self.W, self.cor, self.fonte)
        saida = progresso(dt, e.duracao - 0.25, 0.25)
        y = self.H * 0.80
        pa = progresso(dt, 0, 0.35)
        pp = progresso(dt, 0.12, 0.40)
        x_av = misturar(-avatar.width, self.W * 0.07 + avatar.width / 2, ease_out_back(pa, 1.4))
        x_av -= ease_in_out_cubic(saida) * self.W * 0.6
        _colar(img, avatar, x_av, y, 1.0, 1 - saida)
        x_pi = x_av + avatar.width / 2 + self.W * 0.02 + pilula.width / 2
        x_pi -= misturar(self.W * 0.15, 0, ease_out_cubic(pp))
        _colar(img, pilula, x_pi, y, misturar(0.8, 1.0, ease_out_back(pp)), ease_out_cubic(pp) * (1 - saida))

    def _ev_cta(self, img: Image.Image, dt: float, e: Evento) -> None:
        toque = 1.0  # segundos após a entrada em que o "dedo" toca o botão
        pressionado = toque <= dt < toque + 0.12
        preenchido = dt >= toque + 0.06
        cartao = _cartao_cta(self.cta_tipo, self.W, self.cor, self.fonte, preenchido, pressionado)
        entrada = progresso(dt, 0, 0.40)
        # escurece o fundo para dar foco ao cartão
        escuro = 0.35 * ease_out_cubic(entrada)
        if escuro > 0.01:
            camada = Image.new("RGBA", img.size, (0, 0, 0, int(255 * escuro)))
            img.paste(camada, (0, 0), camada)
        cy = self.H * 0.45 + misturar(self.H * 0.05, 0, ease_out_cubic(entrada))
        _colar(img, cartao, self.W / 2, cy, misturar(0.7, 1.0, ease_out_back(entrada, 1.8)), ease_out_cubic(entrada))
        # microanimação: cursor de toque + onda (ripple) sobre o botão
        h_cartao = int(self.W * 0.78 * 0.62)
        bx, by = self.W / 2, cy - (cartao.height / 2) + h_cartao * 0.74
        chega = progresso(dt, toque - 0.45, 0.45)
        if 0 < chega and dt < toque + 0.6:
            cx = misturar(bx + self.W * 0.25, bx + self.W * 0.06, ease_in_out_cubic(chega))
            cyc = misturar(by + self.H * 0.12, by + self.H * 0.015, ease_in_out_cubic(chega))
            d = ImageDraw.Draw(img, "RGBA")
            r = self.W * 0.035 * (0.85 if pressionado else 1.0)
            d.ellipse((cx - r, cyc - r, cx + r, cyc + r), fill=(255, 255, 255, 230), outline=(17, 17, 17, 255),
                      width=max(2, int(r * 0.15)))
        onda = progresso(dt, toque, 0.45)
        if 0 < onda < 1:
            d = ImageDraw.Draw(img, "RGBA")
            r = self.W * misturar(0.02, 0.22, ease_out_cubic(onda))
            d.ellipse((bx - r, by - r, bx + r, by + r), outline=(255, 255, 255, int(220 * (1 - onda))),
                      width=max(2, int(self.W * 0.008)))

    # --- efeitos sobre o quadro inteiro -----------------------------------------
    def transicao(self, quadro: np.ndarray, t: float) -> np.ndarray:
        for e in self.eventos:
            if e.tipo != "transicao" or not (e.t <= t < e.t + e.duracao):
                continue
            forca = 1 - ease_out_cubic(progresso(t, e.t, e.duracao))
            estilo = e.dados["estilo"]
            if estilo == "flash":
                quadro = (quadro.astype(np.float32) + (255 - quadro.astype(np.float32)) * 0.75 * forca).astype(np.uint8)
            elif estilo == "zoom":
                img = Image.fromarray(quadro)
                acumulado = quadro.astype(np.float32)
                for k, z in enumerate((1.04, 1.08)):
                    w, h = img.size
                    cw, ch = int(w / (1 + (z - 1) * forca)), int(h / (1 + (z - 1) * forca))
                    rec = img.crop(((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2)).resize((w, h))
                    acumulado += np.asarray(rec, dtype=np.float32)
                quadro = (acumulado / 3).astype(np.uint8)
            elif estilo == "glitch":
                dx = int(self.W * 0.025 * forca)
                if dx:
                    out = quadro.copy()
                    out[:, dx:, 0] = quadro[:, :-dx, 0]
                    out[:, :-dx, 2] = quadro[:, dx:, 2]
                    rng = np.random.default_rng(int(t * 1000))
                    for _ in range(4):
                        y0 = int(rng.integers(0, self.H - 20))
                        alt = int(rng.integers(8, max(9, self.H // 18)))
                        out[y0:y0 + alt] = np.roll(out[y0:y0 + alt], int(rng.integers(-3, 4)) * dx, axis=1)
                    quadro = out
        return quadro

    def transicao_ativa(self, t: float) -> bool:
        return any(e.tipo == "transicao" and e.t <= t < e.t + e.duracao for e in self.eventos)

    def finalizar(self, img: Image.Image, t: float) -> Image.Image:
        """Acabamento de cinema: contraste em S, saturação, vinheta e granulado (tudo em C, via Pillow)."""
        if not self.acabamento:
            return img
        if self._lut is None:
            from PIL import ImageChops, ImageEnhance  # noqa: F401  (pré-carrega os módulos)

            x = np.arange(256, dtype=np.float32) / 255
            curva = 0.5 + (x - 0.5) * 1.10 + 0.04 * np.sin((x - 0.5) * np.pi)  # contraste suave em S
            self._lut = list(np.clip(curva * 255, 0, 255).astype(np.uint8)) * 3
            yy, xx = np.mgrid[0:self.H, 0:self.W].astype(np.float32)
            dist = np.sqrt(((xx - self.W / 2) / (self.W / 2)) ** 2 + ((yy - self.H / 2) / (self.H / 2)) ** 2)
            mascara = (1 - 0.32 * np.clip((dist - 0.55) / 0.85, 0, 1) ** 1.6) * 255
            self._vinheta = Image.fromarray(mascara.astype(np.uint8)).convert("RGB")
            rng = np.random.default_rng(7)
            self._graos = [Image.fromarray(np.clip(rng.normal(8, 3, (self.H, self.W)), 0, 16).astype(np.uint8))
                           .convert("RGB") for _ in range(4)]
        from PIL import ImageChops, ImageEnhance

        img = img.point(self._lut)
        img = ImageEnhance.Color(img).enhance(1.12)
        img = ImageChops.multiply(img, self._vinheta)
        if self.granulado:
            img = ImageChops.add(img, self._graos[int(t * 24) % len(self._graos)], 1.0, -8)
        return img


# ===========================================================================
# 4. Efeitos sonoros sintetizados
# ===========================================================================
@lru_cache(maxsize=16)
def sfx(tipo: str, sr: int = 44100) -> np.ndarray:
    rng = np.random.default_rng({"whoosh": 1, "pop": 2, "clique": 3, "ding": 4}.get(tipo, 0))
    if tipo == "whoosh":
        n = int(sr * 0.38)
        ruido = rng.standard_normal(n).astype(np.float32)
        saida = np.empty(n, dtype=np.float32)
        y = 0.0
        for i in range(n):  # passa-baixa com corte subindo e descendo (sensação de "passar")
            p = i / n
            a = 0.02 + 0.25 * math.sin(math.pi * p)
            y += a * (ruido[i] - y)
            saida[i] = y
        env = np.sin(np.linspace(0, np.pi, n)) ** 2
        som = saida * env
    elif tipo == "pop":
        n = int(sr * 0.13)
        tt = np.arange(n) / sr
        freq = 950 * np.exp(-tt * 22) + 220
        som = np.sin(2 * np.pi * np.cumsum(freq) / sr) * np.exp(-tt * 30)
    elif tipo == "clique":
        n = int(sr * 0.035)
        tt = np.arange(n) / sr
        som = (np.sin(2 * np.pi * 2200 * tt) * 0.6 + rng.standard_normal(n) * 0.4) * np.exp(-tt * 140)
    elif tipo == "ding":
        n = int(sr * 0.7)
        tt = np.arange(n) / sr
        som = (np.sin(2 * np.pi * 1320 * tt) + 0.5 * np.sin(2 * np.pi * 1980 * tt)) * np.exp(-tt * 6)
    else:
        raise ValueError(f"Som desconhecido: {tipo}")
    som = som.astype(np.float32)
    return som / (np.abs(som).max() or 1)


SONS_POR_EVENTO = {"transicao": ("whoosh", -0.10), "sticker": ("pop", 0.0), "destaque": ("pop", 0.0),
                   "abertura": ("whoosh", 0.0), "cta": ("ding", 0.0)}
VOLUME_RELATIVO = {"whoosh": 0.55, "pop": 0.45, "clique": 0.5, "ding": 0.35}


def mixar_sfx(audio: np.ndarray, sr: int, eventos: list[Evento], volume: float = 0.5) -> np.ndarray:
    """Soma os efeitos sonoros ao áudio (estéreo float32, -1..1) nos instantes dos eventos."""
    saida = audio.astype(np.float32).copy()
    if saida.ndim == 1:
        saida = np.stack([saida, saida], axis=1)

    def somar(som: np.ndarray, t: float, ganho: float) -> None:
        i0 = max(0, int(t * sr))
        if i0 >= len(saida):
            return
        trecho = som[: len(saida) - i0] * ganho
        saida[i0:i0 + len(trecho)] += trecho[:, None]

    for e in eventos:
        if e.tipo in SONS_POR_EVENTO:
            nome, adianta = SONS_POR_EVENTO[e.tipo]
            somar(sfx(nome, sr), e.t + adianta, VOLUME_RELATIVO[nome] * volume)
        if e.tipo == "cta":  # clique do "dedo" no botão
            somar(sfx("clique", sr), e.t + 1.0, VOLUME_RELATIVO["clique"] * volume)
    pico = np.abs(saida).max()
    if pico > 1.0:  # limitador simples para não distorcer
        saida /= pico
    return saida
