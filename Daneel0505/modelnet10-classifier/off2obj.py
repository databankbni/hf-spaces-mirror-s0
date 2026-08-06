#!/usr/bin/env python3
"""
Convert one representative ModelNet10 OFF mesh per class into a web-ready OBJ for the web app.

Usage:
    python off2obj.py <ModelNet10_dir> meshes
      - <ModelNet10_dir> is the extracted ModelNet10 folder (has subfolders bathtub/, bed/, ...).
      - Picks the first mesh in each class's train/ folder, centres + normalises it, fixes the
        up-axis (ModelNet is Z-up; viewers are Y-up), and writes meshes/<class>.obj.

    python off2obj.py --files chair=path/to/a.off table=path/to/b.off  meshes
      - Convert specific files instead (class=path pairs).
"""
import os, sys
import numpy as np

CLASSES = ["bathtub","bed","chair","desk","dresser","monitor","night_stand","sofa","table","toilet"]


def load_off(path):
    with open(path) as f:
        data = f.read()
    toks = data.split()
    i = 0
    if toks[0].upper() == "OFF":
        i = 1
    elif toks[0].upper().startswith("OFF"):      # "OFF8" stuck-together case
        toks[0] = toks[0][3:]; i = 0
    nv, nf = int(toks[i]), int(toks[i+1]); i += 3
    verts = np.array([[float(toks[i+3*k]), float(toks[i+3*k+1]), float(toks[i+3*k+2])]
                      for k in range(nv)], dtype=float)
    i += 3*nv
    faces = []
    for _ in range(nf):
        k = int(toks[i]); i += 1
        poly = [int(toks[i+j]) for j in range(k)]; i += k
        for t in range(1, k-1):                   # fan-triangulate any polygon
            faces.append((poly[0], poly[t], poly[t+1]))
    return verts, faces


def normalize(verts, zup_to_yup=True):
    v = verts.astype(float).copy()
    if zup_to_yup:                                # Z-up -> Y-up: (x,y,z) -> (x, z, -y)
        v = np.stack([v[:,0], v[:,2], -v[:,1]], axis=1)
    center = (v.max(0) + v.min(0)) / 2.0
    v -= center
    scale = np.abs(v).max()
    if scale > 0:
        v /= scale
    return v


def write_obj(verts, faces, path):
    with open(path, "w") as f:
        for x, y, z in verts:
            f.write(f"v {x:.5f} {y:.5f} {z:.5f}\n")
        for a, b, c in faces:
            f.write(f"f {a+1} {b+1} {c+1}\n")
    return len(verts), len(faces)


def first_off(modelnet_dir, cls):
    for sub in ("train", "test", ""):
        d = os.path.join(modelnet_dir, cls, sub)
        if os.path.isdir(d):
            offs = sorted(x for x in os.listdir(d) if x.lower().endswith(".off"))
            if offs:
                return os.path.join(d, offs[0])
    return None


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    out = args[-1]
    os.makedirs(out, exist_ok=True)
    jobs = []
    if args[0] == "--files":
        for pair in args[1:-1]:
            cls, p = pair.split("=", 1)
            jobs.append((cls, p))
    else:
        root = args[0]
        for cls in CLASSES:
            p = first_off(root, cls)
            if p: jobs.append((cls, p))
            else: print(f"  ! no OFF found for {cls}")
    for cls, p in jobs:
        try:
            v, faces = load_off(p)
            v = normalize(v)
            nv, nf = write_obj(v, faces, os.path.join(out, f"{cls}.obj"))
            print(f"  {cls:12s} <- {os.path.basename(p):24s}  {nv} verts, {nf} faces")
        except Exception as e:
            print(f"  ! {cls}: {e}")
    print(f"Done -> {out}/  (upload this folder's .obj files into your Space)")


if __name__ == "__main__":
    main()
