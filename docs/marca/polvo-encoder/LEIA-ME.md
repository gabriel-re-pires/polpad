# Polvo-Encoder: ícone do software do macropad

O polvo é visto de cima, com 8 braços girando em volta da cabeça como um encoder girando.

## Cores

| Nome  | Hex       | Uso |
|-------|-----------|-----|
| Roxo  | `#7A2EF0` | Cor de destaque, a principal |
| Preto | `#0E0B14` | Fundo escuro, ou ícone em lugares claros |
| Branco| `#FFFFFF` | Fundo claro, ou ícone sobre roxo/preto |

Texto branco sobre o roxo tem contraste de 6:1 (passa no WCAG AA).
O roxo sobre o preto tem contraste de 3,2:1, que basta para ícone e não para texto pequeno.

## Pastas

- `svg/`: vetores (512×512). Se precisar editar, use estes arquivos.
  - Arquivos sem "fundo" têm fundo transparente: `polvo-roxo`, `polvo-preto`, `polvo-branco`.
  - Arquivos "fundo" são quadrados com fundo: roxo/branco, roxo/preto, branco/preto, preto/branco e o extra branco/roxo.
- `svg/pequeno/`: versão simplificada, com 6 braços mais grossos e olhos maiores.
  Use em tamanhos de 24 px para baixo. Com 8 braços, nesse tamanho o polvo vira um borrão.
- `png/<variante>/`: 16, 24, 32, 48, 64, 128, 256, 512 e 1024 px. Os de 16 e 24 px já usam a versão pequena.
- `ico/`: um `.ico` por variante, cada um com 16, 24, 32, 48, 64, 128 e 256 px dentro.
  As variantes com fundo viram um bloco de cantos arredondados, como ícone de app.
- `favicon/`: pronto para site ou documentação: `favicon.ico`, `favicon.svg`, `apple-touch-icon.png`, `icon-192.png` e `icon-512.png`.

## Qual usar onde

| Lugar | Arquivo |
|-------|---------|
| Ícone do .exe / janela (Windows) | `ico/polvo-roxo-fundo-preto.ico`, ou `ico/polvo-roxo.ico` se quiser sem fundo |
| Ícone na bandeja do sistema (tray) | `ico/polvo-branco.ico` com barra escura, `ico/polvo-preto.ico` com barra clara |
| Linux (.desktop) | `png/polvo-roxo-fundo-preto/…-256.png` ou `svg/polvo-roxo-fundo-preto.svg` |
| Avatar do GitHub / redes | `png/polvo-branco-fundo-roxo/…-512.png` |
| README / docs | `svg/polvo-roxo.svg` |
| Site | pasta `favicon/` |

## Regras rápidas

- Não estique, não gire e não mude as cores fora das três acima.
- Deixe um respiro em volta de pelo menos 1/4 da largura do polvo.
- Abaixo de 24 px, use sempre a versão `pequeno`.
