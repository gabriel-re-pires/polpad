#!/usr/bin/env python3
"""
Keycaps do Polpad com padrão topográfico em duas cores (base + linhas).

Um único campo de "relevo" cobre o macropad inteiro, então as curvas de nível
continuam de uma tecla para a vizinha, como num mapa. As linhas ficam embutidas
no topo (inlay) com PROFUNDIDADE_LINHA de espessura, e a superfície continua lisa.

Teclas com ícone: qualquer SVG (formas preenchidas viram branco, tecla preta).
    --icone A1=icones/meu.svg --icone A3=icones/outro.svg
    A1 = 1ª tecla da linha de cima (a de 3 teclas), A3 = a 3ª, ao lado da borda.

Saída:
    stl_topo/polpad_18_keycaps.3mf    -> cada keycap é UM objeto com 2 partes
    stl_topo/polpad_mesa_BASE.stl     -> cor 1 (preto)   } mesmas coordenadas,
    stl_topo/polpad_mesa_LINHAS.stl   -> cor 2 (branco)  } importar juntas

Uso:
    python gerar_keycaps_topo.py                  # semente padrão
    python gerar_keycaps_topo.py --semente 7      # outro "mapa"
    python gerar_keycaps_topo.py --folga 0.10     # folga do encaixe MX

Dependências: pip install manifold3d trimesh numpy shapely contourpy
"""
import argparse
import math
import os
import zipfile

import contourpy
import numpy as np
import shapely
from manifold3d import CrossSection, FillRule, JoinType, Manifold
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

import gerar_keycaps as G

# ---------------------------------------------------------------------------
# Parâmetros do padrão
# ---------------------------------------------------------------------------
LARGURA_LINHA = 0.60       # mm (mínimo seguro p/ bico 0.4)
ESPACO_LINHAS = 2.3        # mm, distância média entre curvas de nível
PROFUNDIDADE_LINHA = 0.8   # mm de material branco (0.6 já fica acinzentado sobre preto)
GAP_MINIMO = 0.5           # mm, faixas pretas mais finas que isso viram linha
ESCALA_RELEVO = 9.0        # mm, tamanho típico dos "morros"
DISTORCAO = 3.0            # mm, quanto o relevo é "torcido" (look orgânico)
MARGEM_TOPO = 0.25         # mm, recuo das linhas em relação à borda do topo
RES = 0.08                 # mm, resolução da grade do campo
ICONE_TAM = 9.0            # mm, maior dimensão do ícone no topo
ICONES_PADRAO = {          # linha de cima (troque A1/A3 pelos seus SVGs com --icone)
    "A1": "icones/exemplo_brilho.svg",
    "A2": "icones/terminal.svg",
    "A3": "icones/exemplo_play.svg",
}
# Legendas: números em sequência por linha (esq.->dir.), coluna da direita = letras
LEGENDAS_PADRAO = {
    "B1": "1", "B2": "2", "B3": "3", "B4": "4", "B5": "A",
    "C1": "5", "C2": "6", "C3": "7", "C4": "8", "C5": "B",
    "D1": "9", "D2": "10", "D3": "11", "D4": "12", "D5": "C",
}
ALTURA_LEGENDA = 5.0       # mm, altura dos números/letras
FONTE = "DejaVu Sans"      # fonte (negrito); vem junto com o matplotlib

# Posição X de cada tecla (mesmo passo do PCB, 19.05 mm)
COLUNAS = {"A": [0.0, 19.05, 38.1]}
for _l in "BCD":
    COLUNAS[_l] = [-38.1, -19.05, 0.0, 19.05, 38.1]


# ---------------------------------------------------------------------------
# Campo de relevo
# ---------------------------------------------------------------------------
def ruido_suave(shape, sigma_px, rng):
    """Ruído gaussiano filtrado no domínio da frequência (sem scipy)."""
    w = rng.standard_normal(shape)
    fy = np.fft.fftfreq(shape[0])[:, None]
    fx = np.fft.fftfreq(shape[1])[None, :]
    filtro = np.exp(-2 * (np.pi * sigma_px) ** 2 * (fx ** 2 + fy ** 2))
    r = np.real(np.fft.ifft2(np.fft.fft2(w) * filtro))
    return (r - r.mean()) / r.std()


def campo_relevo(semente):
    rng = np.random.default_rng(semente)
    xs = np.arange(-52, 52 + RES, RES)
    ys = np.arange(-48, 48 + RES, RES)
    X, Y = np.meshgrid(xs, ys)
    s = ESCALA_RELEVO / RES
    # distorção de domínio: amostra o relevo em coordenadas "torcidas"
    wx = ruido_suave(X.shape, s * 1.6, rng) * DISTORCAO
    wy = ruido_suave(X.shape, s * 1.6, rng) * DISTORCAO
    base = ruido_suave(X.shape, s, rng) + 0.45 * ruido_suave(X.shape, s * 0.5, rng)
    ix = np.clip(np.round((X + wx - xs[0]) / RES).astype(int), 0, len(xs) - 1)
    iy = np.clip(np.round((Y + wy - ys[0]) / RES).astype(int), 0, len(ys) - 1)
    f = base[iy, ix]
    # suaviza de novo para tirar o serrilhado da amostragem
    fy = np.fft.fftfreq(f.shape[0])[:, None]
    fx = np.fft.fftfreq(f.shape[1])[None, :]
    f = np.real(np.fft.ifft2(np.fft.fft2(f) * np.exp(-2 * (np.pi * 3) ** 2 * (fx ** 2 + fy ** 2))))
    gy, gx = np.gradient(f, RES)
    passo = np.median(np.hypot(gx, gy)) * ESPACO_LINHAS
    niveis = np.arange(f.min() + passo / 2, f.max(), passo)
    return xs, ys, f, niveis


def linhas_globais(xs, ys, f, niveis):
    """Curvas de nível; trechos em "penhasco" (curvas apertadas demais) são cortados."""
    gen = contourpy.contour_generator(xs, ys, f)
    gy, gx = np.gradient(f, RES)
    grad = np.hypot(gx, gy)
    passo = niveis[1] - niveis[0]
    espaco_min = LARGURA_LINHA + GAP_MINIMO + 0.15
    curvas = []
    for nv in niveis:
        for seg in gen.lines(nv):
            if len(seg) < 2:
                continue
            ix = np.clip(np.round((seg[:, 0] - xs[0]) / RES).astype(int), 0, len(xs) - 1)
            iy = np.clip(np.round((seg[:, 1] - ys[0]) / RES).astype(int), 0, len(ys) - 1)
            ok = passo / np.maximum(grad[iy, ix], 1e-9) >= espaco_min
            # quebra a curva nos trechos apertados
            ini = None
            for k, bom in enumerate(np.append(ok, False)):
                if bom and ini is None:
                    ini = k
                elif not bom and ini is not None:
                    if k - ini >= 2:
                        curvas.append(LineString(seg[ini:k]))
                    ini = None
    return curvas


# ---------------------------------------------------------------------------
# Recorte por tecla (2D, no plano do topo)
# ---------------------------------------------------------------------------
def topo_2d():
    m = G.TOPO_LADO / 2 - MARGEM_TOPO
    r = max(G.RAIO_CANTO_TOPO - MARGEM_TOPO, 0.1)
    return box(-m + r, -m + r, m - r, m - r).buffer(r, quad_segs=16)


def faixas_tecla(curvas, cx, cy):
    janela = topo_2d()
    janela_g = shapely.affinity.translate(janela, cx, cy)
    perto = [c for c in curvas if c.intersects(janela_g.buffer(1))]
    if not perto:
        return Polygon()
    faixas = unary_union([c.buffer(LARGURA_LINHA / 2, quad_segs=8) for c in perto])
    faixas = shapely.affinity.translate(faixas, -cx, -cy).intersection(janela)
    # fecha faixas pretas estreitas demais (viram branco)
    faixas = faixas.buffer(GAP_MINIMO / 2, quad_segs=8).buffer(-GAP_MINIMO / 2, quad_segs=8)
    faixas = faixas.intersection(janela)
    # tira lascas brancas finas demais (sobras do recorte na borda)
    faixas = faixas.buffer(-0.22, quad_segs=8).buffer(0.22, quad_segs=8)
    polys = [p for p in getattr(faixas, "geoms", [faixas]) if p.area > 0.25]
    return unary_union(polys) if polys else Polygon()


def secao_para_shapely(cs):
    """CrossSection -> shapely. Os contornos não se cruzam, então a regra
    par-ímpar (XOR de todos os anéis) reconstrói ilhas dentro de furos."""
    g = Polygon()
    for c in cs.to_polygons():
        if len(c) >= 3:
            g = g.symmetric_difference(Polygon(np.asarray(c)))
    return g


def para_crosssection(geom):
    aneis = []
    for p in getattr(geom, "geoms", [geom]):
        if p.is_empty or p.geom_type != "Polygon":
            continue
        aneis.append(np.asarray(p.exterior.coords)[:-1])
        for h in p.interiors:
            aneis.append(np.asarray(h.coords)[:-1])
    return CrossSection(aneis, FillRule.EvenOdd)



# ---------------------------------------------------------------------------
# Ícones SVG
# ---------------------------------------------------------------------------
def _contornos_svg(elem):
    from svgelements import Arc, Close, CubicBezier, Line, Move, Path, QuadraticBezier
    p = Path(elem)
    p.reify()
    aneis = []
    for sp in p.as_subpaths():
        pts = []
        for seg in Path(sp):
            if isinstance(seg, Move):
                pts.append((seg.end.x, seg.end.y))
            elif isinstance(seg, (Line, Close)):
                if seg.end is not None:
                    pts.append((seg.end.x, seg.end.y))
            else:  # curvas: amostra
                n = 32 if isinstance(seg, (CubicBezier, Arc)) else 20
                for t in np.linspace(0, 1, n)[1:]:
                    q = seg.point(t)
                    pts.append((q.x, q.y))
        if len(pts) >= 3:
            a = np.array(pts, float)
            a[:, 1] *= -1  # SVG tem y para baixo
            aneis.append(a)
    return aneis


def svg_para_secao(caminho, tamanho=ICONE_TAM):
    """Formas preenchidas do SVG -> CrossSection branca centrada (mm).
    Um retângulo/forma que cobre quase todo o desenho é tratado como fundo:
    é ignorado, e formas da mesma cor do fundo viram recortes (pretas)."""
    from svgelements import SVG, Shape
    svg = SVG.parse(caminho, reify=True)
    formas = []
    for e in svg.elements():
        if not isinstance(e, Shape):
            continue
        if e.fill is None or e.fill.value is None:
            continue
        aneis = _contornos_svg(e)
        if not aneis:
            continue
        regra = FillRule.EvenOdd if str(e.values.get("fill-rule", "nonzero")).strip() == "evenodd" \
            else FillRule.NonZero
        formas.append((CrossSection(aneis, regra), int(e.fill.value)))
    if not formas:
        raise ValueError(f"{caminho}: nenhuma forma preenchida encontrada")
    total = CrossSection()
    for f, _ in formas:
        total = total + f
    x0, y0, x1, y1 = total.bounds()
    area_caixa = (x1 - x0) * (y1 - y0)
    fundo = [c for f, c in formas if f.area() > 0.85 * area_caixa]
    cor_fundo = fundo[0] if fundo else None
    branco = CrossSection()
    for f, c in formas:
        if f.area() > 0.85 * area_caixa:
            continue
        branco = branco - f if (cor_fundo is not None and c == cor_fundo) else branco + f
    b = branco.bounds()
    esc = tamanho / max(b[2] - b[0], b[3] - b[1])
    branco = branco.translate([-(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2]).scale([esc, esc])
    return branco


def texto_para_secao(texto, altura=ALTURA_LEGENDA):
    """Texto -> CrossSection branca centrada (mm), em negrito."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath
    tp = TextPath((0, 0), texto, size=10, prop=FontProperties(family=FONTE, weight="bold"))
    aneis = [np.asarray(p) for p in tp.to_polygons(closed_only=True) if len(p) >= 3]
    cs = CrossSection(aneis, FillRule.NonZero)
    x0, y0, x1, y1 = cs.bounds()
    esc = altura / (y1 - y0)
    return cs.translate([-(x0 + x1) / 2, -(y0 + y1) / 2]).scale([esc, esc])


def checar_detalhes(secao, nome):
    fino = secao - secao.offset(-GAP_MINIMO / 2, JoinType.Round).offset(GAP_MINIMO / 2, JoinType.Round)
    pct = 100 * fino.area() / max(secao.area(), 1e-9)
    if pct > 3:
        print(f"  aviso {nome}: {pct:.0f}% do desenho tem traços < {GAP_MINIMO} mm "
              f"(podem sumir na impressão; aumente ICONE_TAM ou engrosse o SVG)")

# ---------------------------------------------------------------------------
# Keycap em duas partes
# ---------------------------------------------------------------------------
def keycap_duas_cores(linha, folga, secao):
    """secao: CrossSection (2D, plano do topo) do que fica branco."""
    corpo, theta, H = G.keycap(linha, folga)
    if secao.is_empty():
        return corpo, Manifold()
    # mesma esfera do dish usada em G.keycap, só que maior: "casca" de espessura d
    rs = (G.DISH_RAIO_BORDA ** 2 + G.DISH_PROF ** 2) / (2 * G.DISH_PROF)
    n = np.array([0, -math.sin(math.radians(theta)), math.cos(math.radians(theta))])
    centro = np.array([0, 0, H]) + n * (rs - G.DISH_PROF)
    casca = Manifold.sphere(rs + PROFUNDIDADE_LINHA, G.SEG * 2).translate(centro.tolist())
    prisma = secao.extrude(10).translate([0, 0, -6])
    prisma = G.no_plano_topo(prisma, theta, H)
    ferramenta = casca ^ prisma          # passa acima do topo: sem faces coincidentes
    linhas = corpo ^ ferramenta
    base = corpo - ferramenta
    return base, linhas


# ---------------------------------------------------------------------------
# 3MF: cada keycap = 1 objeto com 2 partes (base preta + desenho branco)
# ---------------------------------------------------------------------------
def _xml_malha(oid, nome, tm, pindex):
    v = "".join(f'<vertex x="{a:.6f}" y="{b:.6f}" z="{c:.6f}"/>' for a, b, c in tm.vertices)
    t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tm.faces)
    return (f'<object id="{oid}" name="{nome}" type="model" pid="1" pindex="{pindex}">'
            f'<mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh></object>')


def salvar_3mf(caminho, pecas):
    """pecas: lista de (nome, Manifold base, Manifold desenho)."""
    objs, itens, oid = [], [], 2
    for nome, base, des in pecas:
        comp = []
        for parte, m, pidx in (("base_preta", base, 0), ("desenho_branco", des, 1)):
            if m.is_empty():
                continue
            objs.append(_xml_malha(oid, f"{nome}_{parte}", G.para_trimesh(m), pidx))
            comp.append(f'<component objectid="{oid}"/>')
            oid += 1
        objs.append(f'<object id="{oid}" name="{nome}" type="model"><components>{"".join(comp)}'
                    f'</components></object>')
        itens.append(f'<item objectid="{oid}"/>')
        oid += 1
    modelo = ('<?xml version="1.0" encoding="UTF-8"?>'
              '<model unit="millimeter" xml:lang="pt-BR" '
              'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
              '<metadata name="Title">Polpad keycaps</metadata><resources>'
              '<basematerials id="1"><base name="Preto" displaycolor="#111111FF"/>'
              '<base name="Branco" displaycolor="#F2F2F2FF"/></basematerials>'
              + "".join(objs) + "</resources><build>" + "".join(itens) + "</build></model>")
    tipos = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/'
             'package/2006/content-types"><Default Extension="rels" ContentType="application/'
             'vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" '
             'ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", tipos)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", modelo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--semente", type=int, default=36)
    ap.add_argument("--folga", type=float, default=0.15)
    ap.add_argument("--saida", default="stl_topo")
    ap.add_argument("--icone", action="append", default=[], metavar="TECLA=arquivo.svg",
                    help="ex.: --icone A3=icones/meu.svg (pode repetir)")
    ap.add_argument("--sem-icones", action="store_true", help="não usa os ícones de exemplo")
    ap.add_argument("--legenda", action="append", default=[], metavar="TECLA=texto",
                    help="ex.: --legenda B1=Esc (pode repetir)")
    ap.add_argument("--sem-legendas", action="store_true",
                    help="teclas sem ícone ficam com o padrão topográfico")
    a = ap.parse_args()
    icones = {} if a.sem_icones else dict(ICONES_PADRAO)
    legendas = {} if a.sem_legendas else dict(LEGENDAS_PADRAO)
    for item in a.legenda:
        tecla, txt = item.split("=", 1)
        legendas[tecla.strip().upper()] = txt
    for item in a.icone:
        tecla, arq = item.split("=", 1)
        icones[tecla.strip().upper()] = arq
    os.makedirs(a.saida, exist_ok=True)

    xs, ys, f, niveis = campo_relevo(a.semente)
    curvas = linhas_globais(xs, ys, f, niveis)

    base_all, lin_all = Manifold(), Manifold()
    mapa = []  # para a prévia
    pecas = []  # para o 3MF
    janela_cs = para_crosssection(topo_2d())
    passo = 22.0
    for j, linha in enumerate("ABCD"):
        for i, cx in enumerate(COLUNAS[linha]):
            cy = G.LINHAS_Y[linha]
            tecla = f"{linha}{i + 1}"
            if tecla in icones:
                secao = svg_para_secao(icones[tecla]) ^ janela_cs
                checar_detalhes(secao, tecla)
                fx = secao_para_shapely(secao)
            elif tecla in legendas:
                secao = texto_para_secao(legendas[tecla]) ^ janela_cs
                checar_detalhes(secao, tecla)
                fx = secao_para_shapely(secao)
            else:
                fx = faixas_tecla(curvas, cx, cy)
                secao = para_crosssection(fx) if not fx.is_empty else CrossSection()
            mapa.append((cx, cy, fx))
            base, lin = keycap_duas_cores(linha, a.folga, secao)
            # posição na mesa (linha A tem 3 teclas: alinhadas à direita como no PCB)
            col = i + (2 if linha == "A" else 0)
            t = [(col - 2) * passo, (1.5 - j) * passo, 0]
            base_all += base.translate(t)
            lin_all += lin.translate(t)
            pecas.append((f"keycap_{tecla}", base.translate(t), lin.translate(t)))
            origem = (os.path.basename(icones[tecla]) if tecla in icones else
                      f'legenda "{legendas[tecla]}"' if tecla in legendas else "topográfico")
            print(f"tecla {tecla}: {origem:24s} volume branco {lin.volume():5.1f} mm³")

    G.para_trimesh(base_all).export(os.path.join(a.saida, "polpad_mesa_BASE.stl"))
    G.para_trimesh(lin_all).export(os.path.join(a.saida, "polpad_mesa_LINHAS.stl"))
    salvar_3mf(os.path.join(a.saida, "polpad_18_keycaps.3mf"), pecas)
    np.save(os.path.join(a.saida, "_mapa.npy"), np.array(
        [(cx, cy, shapely.to_wkt(g)) for cx, cy, g in mapa], dtype=object), allow_pickle=True)
    print("ok ->", a.saida)


if __name__ == "__main__":
    main()
