"""Estúdio IA: gera roteiros, imagens, vozes e vídeos com fallback entre modelos."""

from .config import carregar_roteador
from .roteador import Resultado, Roteador, TodosFalharam

__all__ = ["carregar_roteador", "Resultado", "Roteador", "TodosFalharam"]
