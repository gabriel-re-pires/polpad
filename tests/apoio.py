"""Apoio comum aos testes."""

from __future__ import annotations

from typing import Any


class CofreFalso:
    """Cofre em memória: salvar uma configuração de teste no cofre real
    apagaria as credenciais do usuário."""

    def __init__(self, disponivel: bool = True) -> None:
        self.disponivel = disponivel
        self.guardados: dict[str, str] = {}

    def store(self, name: str, value: str) -> bool:
        if not self.disponivel:
            return False
        if value:
            self.guardados[name] = value
        else:
            self.guardados.pop(name, None)
        return True

    def load(self, name: str) -> str:
        if not self.disponivel:
            return ""
        return self.guardados.get(name, "")


class RespostaFalsa:
    """Resposta HTTP mínima no formato que o código usa do ``requests``."""

    def __init__(
        self,
        payload: Any = None,
        conteudo: bytes = b"",
        erro: Exception | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self._conteudo = conteudo
        self._erro = erro
        self.headers = headers or {}

    @property
    def text(self) -> str:
        return self._conteudo.decode("utf-8")

    def raise_for_status(self) -> None:
        if self._erro is not None:
            raise self._erro

    def json(self) -> Any:
        return self._payload

    def iter_content(self, chunk_size: int = 1) -> Any:
        for inicio in range(0, len(self._conteudo), chunk_size):
            yield self._conteudo[inicio : inicio + chunk_size]


class ClienteFalso:
    """Substitui o ``requests``: uma resposta única ou um dict URL → resposta."""

    def __init__(
        self, resposta: RespostaFalsa | Exception | dict[str, RespostaFalsa | Exception]
    ) -> None:
        self._resposta = resposta
        self.chamadas: list[str] = []

    def get(self, url: str, **kwargs: Any) -> RespostaFalsa:
        self.chamadas.append(url)
        resposta = self._resposta
        if isinstance(resposta, dict):
            resposta = resposta[url]
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
