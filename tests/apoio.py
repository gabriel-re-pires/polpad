"""Apoio comum aos testes."""

from __future__ import annotations


class CofreFalso:
    """Cofre de credenciais em memória.

    Os testes precisam de um: o cofre real é o Credential Manager do
    usuário, e salvar uma configuração de teste apagaria as credenciais
    verdadeiras dele.
    """

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
