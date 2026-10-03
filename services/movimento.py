"""Curvas de movimento (easing). Nada no Estúdio se move de forma linear."""

from __future__ import annotations


def limitar(x: float, minimo: float = 0.0, maximo: float = 1.0) -> float:
    return max(minimo, min(maximo, x))


def progresso(t: float, inicio: float, duracao: float) -> float:
    """0 antes do início, 1 depois do fim, proporcional no meio (sempre limitado)."""
    if duracao <= 0:
        return 1.0 if t >= inicio else 0.0
    return limitar((t - inicio) / duracao)


def ease_out_cubic(p: float) -> float:
    p = limitar(p)
    return 1 - (1 - p) ** 3


def ease_in_out_cubic(p: float) -> float:
    p = limitar(p)
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def ease_out_back(p: float, exagero: float = 1.70158) -> float:
    """Passa um pouco do ponto e volta — dá o efeito de 'pop'."""
    p = limitar(p)
    c3 = exagero + 1
    return 1 + c3 * (p - 1) ** 3 + exagero * (p - 1) ** 2


def misturar(a: float, b: float, p: float) -> float:
    return a + (b - a) * p
