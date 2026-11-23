import numpy as np, shapely, math, matplotlib, trimesh, sys
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from shapely.plotting import plot_polygon
import gerar_keycaps_topo as T, gerar_keycaps as G
pasta=sys.argv[1] if len(sys.argv)>1 else "stl_topo"  # uso: python previa_topo.py [pasta]
mapa=np.load(f"{pasta}/_mapa.npy",allow_pickle=True)
# --- vista de cima, layout real ---
fig,ax=plt.subplots(figsize=(9,8),facecolor="#111")
ax.set_facecolor("#1b1b1f")
for cx,cy,wkt in mapa:
    top=shapely.affinity.translate(T.topo_2d().buffer(T.MARGEM_TOPO),cx,cy)
    plot_polygon(top,ax=ax,add_points=False,facecolor="#0b0b0c",edgecolor="#333",linewidth=1)
    g=shapely.affinity.translate(shapely.from_wkt(wkt),cx,cy)
    if not g.is_empty: plot_polygon(g,ax=ax,add_points=False,facecolor="#f2f2f2",edgecolor="none")
ax.set_aspect("equal"); ax.axis("off"); ax.set_xlim(-50,50); ax.set_ylim(-45,42)
ax.set_title("Topo das 18 teclas no layout do Polpad (display em cima à esquerda)",color="w")
plt.tight_layout(); plt.savefig("topo_mapa.png",dpi=130,facecolor="#111")
# --- render 3D da mesa ---
b=trimesh.load(f"{pasta}/polpad_mesa_BASE.stl"); l=trimesh.load(f"{pasta}/polpad_mesa_LINHAS.stl")
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
fig=plt.figure(figsize=(11,9),facecolor="#d9d9de"); ax=fig.add_subplot(111,projection="3d"); ax.set_facecolor("#d9d9de")
light=np.array([0.35,-0.45,1.0]); light/=np.linalg.norm(light)
V=[];C=[]
for m,col in ((b,(0.09,0.09,0.10)),(l,(0.95,0.95,0.95))):
    v=m.vertices[m.faces]; sh=np.clip(m.face_normals@light,0,1)*0.6+0.4
    keep=m.face_normals[:,2]>-0.2
    V.append(v[keep]); C.append(np.clip(np.array(col)[None,:]*sh[keep,None]+ (0.05 if col[0]<.5 else 0),0,1))
# lift white a hair to win z-fighting in painter's algorithm
V[1]=V[1]+np.array([0,0,0.03])
ax.add_collection3d(Poly3DCollection(np.vstack(V),facecolors=np.vstack(C),edgecolors="none"))
ax.set_xlim(-55,55); ax.set_ylim(-55,55); ax.set_zlim(-5,30); ax.set_box_aspect((1,1,0.32))
ax.view_init(elev=48,azim=-70); ax.set_axis_off()
plt.tight_layout(); plt.savefig("render_topo.png",dpi=120,bbox_inches="tight",facecolor="#d9d9de")
