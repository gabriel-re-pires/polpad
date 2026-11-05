# Desenvolvimento do Polpad

## Primeira vez no clone

```bash
git config core.hooksPath .githooks
```

Ativa o hook `commit-msg`: um commit só pode ter como coautores as pessoas
listadas em `.github/coautores` (um e-mail por linha) e não pode trazer
assinaturas automáticas ("Generated with ..."). Para dar coautoria a mais
alguém, acrescente o e-mail dele nessa lista. O formato é o do GitHub:

```
Co-authored-by: Nome <id+usuario@users.noreply.github.com>
```

O workflow **Coautores** aplica a mesma regra a todo PR e push no `main`.

## Ambiente

Python 3.11+.

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m polpad          # ou run.bat
```

No Linux: `python3 -m venv .venv`, `.venv/bin/python -m pip install -e ".[dev]"`
e `./run.sh`.

## Verificações

```powershell
.venv\Scripts\python -m unittest discover -t . -v
.venv\Scripts\ruff check .
.venv\Scripts\mypy
```

## Executável

```powershell
.venv\Scripts\python tools\build_exe.py
```

Gera `dist\Polpad.exe` (Windows) ou `dist/Polpad` (Linux). No Linux,
`tools/instalar_linux.py` põe o executável no menu de aplicativos.

## Versões

Números `MAJOR.MINOR.PATCH`, na sequência iniciada em 0.1.0:

| Mudança | Como sobe | Exemplo |
|---|---|---|
| Funcionalidade nova | MINOR, zerando o PATCH | 0.4.1 → 0.5.0 |
| Só correções | PATCH | 0.5.0 → 0.5.1 |
| Versão descrita no artigo | 1.0.0 | |

- Tag: `v` + número (`v0.5.0`).
- Título do release: `Polpad X.Y.Z`, mais ` + firmware A.B.C` quando o
  release traz firmware.
- O firmware tem numeração própria, no nome do anexo
  (`firmware-2.0.1.bin`).

## Publicar uma versão

1. Atualize a versão em `pyproject.toml` e em `src/polpad/__init__.py`.
2. Faça o commit, crie a tag e envie:

   ```bash
   git tag v0.5.0
   git push origin v0.5.0
   ```

3. O workflow **Executáveis** testa nos dois sistemas, confere que a tag
   bate com a versão do código, gera `Polpad.exe` e
   `Polpad-linux-x86_64.tar.gz`, confere que os dois abrem e cria um
   **rascunho** de release.
4. No rascunho, escreva as novidades, anexe o `firmware-*.bin` e publique.
   O aplicativo grava o firmware do último release publicado.
