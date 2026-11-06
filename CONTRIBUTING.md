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
.venv\Scripts\python tools\build_exe.py --instalador
```

No Windows gera a pasta `dist\Polpad\` e o instalador `dist\Polpad-Setup.exe`
(precisa do Inno Setup 6: `winget install JRSoftware.InnoSetup`). No Linux,
`.venv/bin/python tools/build_exe.py` gera `dist/Polpad`, e
`dist/Polpad --instalar-no-menu` o põe no menu de aplicativos.

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
   bate com a versão do código, gera `Polpad-Setup.exe` e
   `Polpad-linux-x86_64.tar.gz`, confere que os dois instalam e abrem e cria
   um **rascunho** de release com eles e o `SHA256SUMS.txt`.
4. No rascunho, escreva as novidades, anexe o `firmware-*.bin` se houver
   firmware novo e publique como **pré-lançamento**. Assim dá para baixar e
   testar sem que o aviso de atualização chegue aos usuários.
5. Aprovada nos testes, edite o release e tire o pré-lançamento: a versão
   vira a oficial, os links do README passam a apontar para ela e o Polpad
   instalado nos computadores avisa da atualização.

O firmware gravado pelo aplicativo vem do release oficial mais recente que
tenha um `firmware-*.bin`.

## Ensaio da atualização, antes de publicar

A variável `POLPAD_RELEASES_URL` troca o endereço que o Polpad consulta por
uma lista local no formato da API do GitHub. Com ela dá para ensaiar uma
atualização sem publicar nada:

1. Gere e instale a versão atual (por exemplo 0.5.0).
2. Gere um segundo instalador com a versão trocada só no build (0.5.1, sem
   commit) e crie uma pasta com ele, o `SHA256SUMS.txt` dos dois arquivos e
   um `releases.json` com os dois releases (`tag_name`, `assets` com
   `name`, `size` e `browser_download_url` apontando para
   `http://127.0.0.1:8765/...`).
3. Sirva a pasta: `python -m http.server 8765 --bind 127.0.0.1` (outra
   porta, se a 8765 estiver em uso).
4. Abra o Polpad instalado com
   `POLPAD_RELEASES_URL=http://127.0.0.1:8765/releases.json` e confira:
   - o aviso da 0.5.1 no canto da tela e o X escondendo-o;
   - **Atualizar** baixando, instalando e reabrindo na 0.5.1;
   - na página de versão, voltar para a 0.5.0 (perfis preservados e um
     backup novo);
   - a atualização automática ligada: download em segundo plano e
     instalação ao sair pela bandeja;
   - a rede caindo no meio do download (pare o servidor): mensagem com
     **Tentar de novo** e nada instalado;
   - a desinstalação pelo Windows, mantendo `%APPDATA%\Polpad`.
