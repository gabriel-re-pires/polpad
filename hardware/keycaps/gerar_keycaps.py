#!/usr/bin/env python3
"""
Gerador de keycaps esculpidas (encaixe Cherry MX) para o Polpad.

Perfil "concha" no estilo MDA/SA baixo: o topo de cada linha é tangente a um
cilindro imaginário, compensando a inclinação de 7° do case. A linha de trás
inclina para o usuário, a da frente inclina para trás, formando uma "concha"
suave sob os dedos.

Uso:
    python gerar_keycaps.py                 # gera tudo com folga padrão (0.15 mm)
    python gerar_keycaps.py --folga 0.10    # encaixe mais justo

Dependências: pip install manifold3d trimesh numpy
"""
import argparse
import math
import os

import numpy as np
import trimesh
from manifold3d import CrossSection, JoinType, Manifold

# ---------------------------------------------------------------------------
# Geometria do Polpad (medida em hardware/case/*.stl)
# ---------------------------------------------------------------------------
INCLINACAO_CASE = 7.0  # graus, face superior da bandeja (mais alta atrás)
# centro Y de cada linha no case (mm); +Y = fundo (lado do display)
LINHAS_Y = {"A": 30.58, "B": 6.06, "C": -13.94, "D": -33.94}
TECLAS_POR_LINHA = {"A": 3, "B": 5, "C": 5, "D": 5}

# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------
RAIO_CONCHA = 286.0      # mm, raio do cilindro que as linhas tangenciam
LINHA_BASE = "B"         # linha mais baixa da concha (topo paralelo à placa)
ALTURA_BASE = 8.5        # mm, da borda inferior ao topo (borda do dish) na linha base

BASE_LADO = 18.2         # mm, lado da base (passo 19.05)
TOPO_LADO = 12.8         # mm, lado do topo
RAIO_CANTO_BASE = 1.5
RAIO_CANTO_TOPO = 2.5
BOJO_LATERAL = 0.35      # mm, quanto as laterais "estufam" (lado convexo, estilo SA)

DISH_PROF = 1.0          # mm, profundidade do dish esférico no centro
DISH_RAIO_BORDA = 8.5    # mm, raio do círculo onde a esfera cruza o plano do topo

PAREDE = 1.6             # mm (4 filetes de 0.4)
TETO_MIN = 1.2           # mm de material sob o fundo do dish
CHANFRO_INTERNO = 2.5    # mm, chanfro 45° teto/parede: imprime sem suporte

# ---------------------------------------------------------------------------
# Haste / encaixe Cherry MX
# Especificação Cherry (fenda da keycap): cruz 4,1 (+0,05) mm, braços 1,17 ±0,02 mm.
# Haste do switch: braço horizontal ~1,2-1,25 mm, vertical ~1,1-1,15 mm, cruz ~4,0 mm.
# A folga soma ao nominal para compensar o FDM (furos saem menores).
# ---------------------------------------------------------------------------
CRUZ_COMPR = 4.10
CRUZ_BRACO_H = 1.25      # braço horizontal (eixo X, ao longo da linha)
CRUZ_BRACO_V = 1.17      # braço vertical (eixo Y)
CRUZ_PROF = 4.0          # profundidade do soquete (curso do switch)
HASTE_DIAM = 5.5         # cilindro da haste (cabe dentro de switches BOX)
CHANFRO_ENTRADA = 0.4    # alarga a boca da cruz (anti "pé de elefante")

SEG = 96


def quad_arred(lado, raio):
    return CrossSection.square([lado - 2 * raio, lado - 2 * raio], center=True).offset(
        raio, JoinType.Round, circular_segments=SEG // 2
    )


def placa(lado, raio, esp=0.01):
    return quad_arred(lado, raio).extrude(esp).translate([0, 0, -esp / 2])


def perfil_linha(linha):
    """Inclinação do topo (graus, + = alto atrás) e altura no centro."""
    d = LINHAS_Y[linha] - LINHAS_Y[LINHA_BASE]
    theta = math.degrees(math.asin(d / RAIO_CONCHA))
    altura = ALTURA_BASE + RAIO_CONCHA * (1 - math.cos(math.radians(theta)))
    return theta, altura


def semilado_externo(z, altura):
    """Semi-lado do casco na altura z (interpolação linear base->topo)."""
    t = min(max(z / altura, 0), 1)
    return (BASE_LADO + (TOPO_LADO - BASE_LADO) * t) / 2


def no_plano_topo(m, theta, z_centro):
    return m.rotate([theta, 0, 0]).translate([0, 0, z_centro])


def keycap(linha, folga):
    theta, H = perfil_linha(linha)

    # ---- casco externo: casca convexa de fatias -------------------------
    fatias = [placa(BASE_LADO, RAIO_CANTO_BASE).translate([0, 0, 0.005])]
    for t in (0.3, 0.6):
        z = t * H
        lado = BASE_LADO + (TOPO_LADO - BASE_LADO) * t + 2 * BOJO_LATERAL * math.sin(math.pi * t)
        r = RAIO_CANTO_BASE + (RAIO_CANTO_TOPO - RAIO_CANTO_BASE) * t
        fatias.append(no_plano_topo(placa(lado, r), theta * t, z))
    fatias.append(no_plano_topo(placa(TOPO_LADO, RAIO_CANTO_TOPO), theta, H))
    casco = Manifold.batch_hull(fatias)

    # ---- dish esférico ---------------------------------------------------
    rs = (DISH_RAIO_BORDA ** 2 + DISH_PROF ** 2) / (2 * DISH_PROF)
    n = np.array([0, -math.sin(math.radians(theta)), math.cos(math.radians(theta))])
    centro = np.array([0, 0, H]) + n * (rs - DISH_PROF)
    esfera = Manifold.sphere(rs, SEG * 2).translate(centro.tolist())
    casco = casco - esfera

    # ---- cavidade interna (teto chanfrado a 45°) -------------------------
    zt = H - DISH_PROF - TETO_MIN               # teto no centro
    z1 = zt - CHANFRO_INTERNO
    s0 = semilado_externo(0, H) - PAREDE
    s1 = semilado_externo(z1, H) - PAREDE
    cav = Manifold.batch_hull([
        placa(2 * s0, max(RAIO_CANTO_BASE - PAREDE, 0.3)).translate([0, 0, -1]),
        placa(2 * s0, max(RAIO_CANTO_BASE - PAREDE, 0.3)).translate([0, 0, 0]),
        no_plano_topo(placa(2 * s1, 0.6), theta, z1),
        no_plano_topo(placa(2 * (s1 - CHANFRO_INTERNO), 0.6), theta, zt),
    ])
    corpo = casco - cav

    # ---- haste com cone 45° até o teto (sem suporte) ---------------------
    r = HASTE_DIAM / 2
    topo_haste = zt + 0.6
    haste = Manifold.cylinder(topo_haste, r, r, SEG)
    if topo_haste > CRUZ_PROF:
        h_cone = min(topo_haste - CRUZ_PROF, 3.0)
        haste += Manifold.cylinder(h_cone, r, r + h_cone, SEG).translate([0, 0, topo_haste - h_cone])
    corpo += haste ^ casco  # nunca sai do casco

    # ---- soquete em cruz com chanfro de entrada --------------------------
    L = CRUZ_COMPR + folga
    wh = CRUZ_BRACO_H + folga / 2
    wv = CRUZ_BRACO_V + folga / 2
    cruz = Manifold()
    c = CHANFRO_ENTRADA
    for (sx, sy) in ((L, wh), (wv, L)):
        reta = CrossSection.square([sx, sy], center=True).extrude(CRUZ_PROF + 1).translate([0, 0, -1])
        boca = Manifold.batch_hull([
            CrossSection.square([sx + 2 * c, sy + 2 * c], center=True).extrude(1).translate([0, 0, -1]),
            CrossSection.square([sx, sy], center=True).extrude(0.01).translate([0, 0, c]),
        ])
        cruz += reta + boca
    corpo -= cruz

    # ---- marca de linha: n entalhes na borda de trás (A=1 ... D=4) -------
    idx = "ABCD".index(linha) + 1
    for i in range(idx):
        x = (i - (idx - 1) / 2) * 2.0
        ent = Manifold.cube([0.9, PAREDE * 3, 0.6], center=False).translate(
            [x - 0.45, BASE_LADO / 2 - PAREDE * 2, -0.01])
        corpo -= ent

    return corpo, theta, H


def peca_teste(folga, n_pontos):
    """Haste curta com o mesmo soquete, para testar o encaixe no switch."""
    base = placa(10, 1.5, 2.0).translate([0, 0, 6.0])
    haste = Manifold.cylinder(6.0, HASTE_DIAM / 2, HASTE_DIAM / 2, SEG)
    p = base + haste
    for i in range(n_pontos):  # bolinhas no topo = índice da folga
        x = (i - (n_pontos - 1) / 2) * 1.8
        p += Manifold.sphere(0.6, 24).translate([x, 0, 7.0])
    L = CRUZ_COMPR + folga
    for (sx, sy) in ((L, CRUZ_BRACO_H + folga / 2), (CRUZ_BRACO_V + folga / 2, L)):
        c = CHANFRO_ENTRADA
        p -= CrossSection.square([sx, sy], center=True).extrude(CRUZ_PROF + 1).translate([0, 0, -1])
        p -= Manifold.batch_hull([
            CrossSection.square([sx + 2 * c, sy + 2 * c], center=True).extrude(1).translate([0, 0, -1]),
            CrossSection.square([sx, sy], center=True).extrude(0.01).translate([0, 0, c]),
        ])
    return p


def para_trimesh(m):
    # remove microarestas (< 2 µm) que colapsariam no float32 do STL
    mesh = m.simplify(0.002).to_mesh()
    return trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folga", type=float, default=0.15, help="folga do soquete em mm (padrão 0.15)")
    ap.add_argument("--saida", default="stl")
    a = ap.parse_args()
    os.makedirs(a.saida, exist_ok=True)

    caps = {}
    for linha in "ABCD":
        m, th, H = keycap(linha, a.folga)
        caps[linha] = m
        tm = para_trimesh(m)
        nome = f"keycap_linha{linha}_x{TECLAS_POR_LINHA[linha]}.stl"
        tm.export(os.path.join(a.saida, nome))
        print(f"linha {linha}: topo {th:+.1f}° (efetivo {th + INCLINACAO_CASE:+.1f}° na mesa), "
              f"altura {H:.2f} mm, volume {tm.volume / 1000:.2f} cm³, estanque={tm.is_watertight} -> {nome}")

    # mesa com as 18 (cabe folgado na Ender-3 V3 SE)
    todas = Manifold()
    passo = 22.0
    for j, linha in enumerate("ABCD"):
        for i in range(TECLAS_POR_LINHA[linha]):
            todas += caps[linha].translate([(i - 2) * passo, (1.5 - j) * passo, 0])
    para_trimesh(todas).export(os.path.join(a.saida, "polpad_18_keycaps_mesa.stl"))

    # peças de teste de encaixe
    teste = Manifold()
    folgas = [0.05, 0.10, 0.15, 0.20, 0.25]
    for k, f in enumerate(folgas):
        teste += peca_teste(f, k + 1).translate([(k - 2) * 14, 0, 0])
    para_trimesh(teste).export(os.path.join(a.saida, "teste_encaixe_folgas.stl"))
    print("teste de encaixe: 1 bolinha = 0.05 ... 5 bolinhas = 0.25 mm")


if __name__ == "__main__":
    main()
