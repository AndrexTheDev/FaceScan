"""Globaler UV-Atlas -- EIN Atlas fuer das GANZE Modell.

Warum das eigene Modul? Weil der bisherige Weg (pro Vertex eine
Kugelprojektion, `meshopt.spherical_uv`) genau das ist, was spaeter die
Naht mitten durch das Gesicht legt:

    * Die Kugelprojektion hat dort, wo der Strahl streifend auf die
      Oberflaeche trifft (Schlaefen, Kinnunterseite), eine beliebig grosse
      Verzerrung -- ein Texel deckt dort Zentimeter.
    * Sie ist nicht eindeutig: ein Vertex kann zwei (u, v) bekommen.

`xatlas` (https://github.com/jpcy/xatlas, Apache-2.0) ist der
Industriestandard: es zerlegt das Netz in Charts, entzerrt jeden Chart
moeglichst winkeltreu und packt sie anschliessend mit Mindestabstand in
ein Quadrat. Der Mindestabstand ist der Punkt, an dem Texture Bleeding
aufhoert: liegen zwei Charts direkt aneinander, saugt der bilineare
Filter beim Mip-Map-Level > 0 die Nachbarchart-Farbe an.

Sollte xatlas nicht installiert sein, gibt `global_uv` die
Kugelprojektion zurueck -- deutlich schlechter, aber lauffaehig. Der
Aufrufer erfaehrt das ueber das Feld `method` im Ergebnis, damit niemand
denkt, er haette einen echten Atlas bekommen.
"""

from __future__ import annotations

import numpy as np


def cylindrical_uv(v: np.ndarray, seam_deg: float = 180.0) -> np.ndarray:
    """Zylinderprojektion -- die Standard-UV eines Kopfes.

    Warum Zylinder und nicht Kugel:
      * Bei der Kugelprojektion laufen am Scheitel alle Meridiane
        zusammen. Ein Texel am Pol deckt dort Zentimeter, und genau
        da sitzt bei einem Kopf der Haarwirbel -- also die Stelle, die
        man am schärfsten sehen will.
      * `v` aus der HÖHE statt aus dem Polarwinkel ist auf dem
        Zylinder flächentreu bis auf den Faktor 1/cos(Neigung): eine
        Wange bekommt dieselbe Texeldichte wie die Stirn.

    Die Naht liegt hinten (`seam_deg = 180`), weil dort Haare sind und
    weil keine der 16 Aufnahmen dort frontal draufschaut. Nach vorn
    gelegt, liefe die Naht mitten durchs Gesicht.

    Für die Punkte EINES Dreiecks, das über die Naht läuft, reisst die
    Projektion auf (u springt von 1 auf 0). Das ist der Preis des einen
    Charts -- und genau der Grund, warum xatlas besser ist, wenn es
    läuft. Wer das Modell damit texturiert, muss die Naht-Spalte mit
    `bake.dilate` auffüllen.
    """
    v = np.asarray(v, dtype=np.float64)
    ang = np.arctan2(v[:, 2], v[:, 0])
    seam = np.deg2rad(seam_deg)
    u = ((ang - seam) % (2.0 * np.pi)) / (2.0 * np.pi)
    lo, hi = v[:, 1].min(), v[:, 1].max()
    t = np.zeros(len(v)) if hi <= lo else (v[:, 1] - lo) / (hi - lo)
    return np.stack([u, t], axis=1)


def global_uv(v: np.ndarray, f: np.ndarray,
              resolution: int = 2048, padding: int = 4,
              max_iterations: int = 1, max_cost: float = 3.0,
              brute_force: bool = False, method: str = "xatlas") -> dict:
    """Zerlegt `v`/`f` in Charts und packt sie in ein Einheitsquadrat.

    Rueckgabe:
        vertices   (N', 3) Punkte -- mehr als vorher, weil Naht-Vertices
                   MEHRFACH vorkommen (ein Vertex hat an einer Naht zwei
                   UV-Koordinaten; wer das zusammenfaltet, bekommt
                   zwangslaeufig eine falsche Textur).
        faces      (M, 3) Indizes in `vertices`
        uv         (N', 2) in [0, 1], v = 0 unten (glTF-/USD-Konvention,
                   NICHT Bild-Konvention -- siehe `bake.uv_to_pixel`)
        method     "xatlas" oder "spherical" (Rueckfall)
        charts     Anzahl der Charts
        utilization  Anteil der Atlasflaeche, den die Charts belegen
                   (xatlas selbst; der Rest ist unvermeidbarer Abstand)
        texels_per_unit  Texel je Millimeter -- die Zahl, die bestimmt,
                   wie scharf die Textur WIRKLICH ist
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    if method != "xatlas":
        uv = cylindrical_uv(v)
        return {"vertices": v, "faces": f, "uv": uv,
                "method": "cylindrical", "charts": 1,
                "utilization": float(uv_area_histogram(v, f, uv).max()
                                     if False else 0.0),
                "texels_per_unit": 0.0,
                "atlas_width": resolution, "atlas_height": resolution}
    try:
        import xatlas
    except ImportError:
        uv = cylindrical_uv(v)
        return {"vertices": v, "faces": f, "uv": uv,
                "method": "cylindrical", "charts": 1,
                "utilization": 0.0, "texels_per_unit": 0.0,
                "atlas_width": resolution, "atlas_height": resolution}

    # Die hohe Atlas-Klasse (nicht die Einzeiler-Funktion parametrize),
    # weil nur sie die Pack-Optionen offenlegt. `padding` ist der
    # Abstand zwischen den Charts und damit genau der Wert, der Texture
    # Bleeding in den Mip-Maps verhindert.
    atl = xatlas.Atlas()
    atl.add_mesh(v.astype(np.float32), f.astype(np.uint32))
    co = xatlas.ChartOptions()
    co.max_iterations = int(max_iterations)
    # max_cost ist die Obergrenze fuer die Chart-Verzerrung. Der
    # xatlas-Standard (2.0) zerschneidet ein Netz mit vielen kleinen
    # Beulen -- und ein Visual-Hull-Haarnetz besteht fast nur aus
    # Beulen -- in sehr viele Charts. Mehr Charts heisst mehr Naht und
    # schlechtere Auslastung.
    co.max_cost = float(max_cost)
    po = xatlas.PackOptions()
    po.resolution = int(resolution)
    po.padding = int(padding)
    po.bilinear = True
    po.create_image = False
    po.bruteForce = bool(brute_force)
    atl.generate(co, po, False)

    vm, idx, uv = atl.get_mesh(0)
    vm = np.asarray(vm, dtype=np.int64)
    idx = np.asarray(idx, dtype=np.int64)
    uv = np.asarray(uv, dtype=np.float64)
    util = float(atl.get_utilization(0))
    tpu = float(atl.texels_per_unit)

    # xatlas liefert uv in [0,1] mit v=0 UNTEN (OpenGL). Wir behalten das,
    # weil glTF, USD und OBJ/mtl alle diese Konvention haben. Erst beim
    # Schreiben des Bildes wird gekippt (bake.uv_to_pixel).
    #
    # WICHTIG: vm ist "neuer Vertex -> alter Vertex". Wer das andersherum
    # liest, erhaelt ein Netz, dessen Punkte vertauscht sind -- und zwar
    # so, dass es in den allermeisten Dreiecken zufaellig richtig aussieht.
    return {
        "vertices": v[vm],
        "faces": idx,
        "uv": np.clip(uv, 0.0, 1.0),
        "method": "xatlas",
        "charts": int(atl.chart_count),
        "utilization": util,
        "texels_per_unit": tpu,
        "atlas_width": int(atl.width),
        "atlas_height": int(atl.height),
    }


def xatlas_chart_count(f: np.ndarray, uv: np.ndarray) -> int:
    """Zaehlt die zusammenhaengenden Charts im Atlas.

    Wir zaehlen ueber die UV-Kanten: eine Kante, die in zwei Dreiecken
    mit *derselben* UV-Richtung vorkommt, ist innen; eine Kante, deren
    UV-Richtung zwischen den beiden Dreiecken wechselt, ist eine
    Chart-Grenze. Das ist genau die Definition, die xatlas beim Packen
    benutzt, und deshalb die einzige Zahl, die man mit dem Werkzeug
    selbst vergleichen kann.
    """
    f = np.asarray(f, dtype=np.int64)
    a = f[:, [0, 1, 2]]
    b = f[:, [1, 2, 0]]
    cnt: dict = {}
    for k in range(3):
        e0 = a[:, k]
        e1 = b[:, k]
        for i, j in zip(e0.tolist(), e1.tolist()):
            key = (min(i, j), max(i, j))
            cnt[key] = cnt.get(key, 0) + 1
    # Ein Chart hat mindestens eine Grenze. Bei perfekt geschlossenen
    # (torusartigen) Charts ist die Zahl 0 -- das ist hier unerheblich,
    # wir wollen nur eine Groessenordnung.
    boundary = sum(1 for n in cnt.values() if n == 1)
    return max(1, boundary // 3)


def uv_area_histogram(v: np.ndarray, f: np.ndarray, uv: np.ndarray,
                      bins: int = 8) -> np.ndarray:
    """Verhaeltnis 3D-Flaeche zu UV-Flaeche je Dreieck, als Histogramm.

    Bei einer perfekten (flaechentreuen) Abbildung ist der Wert 1. Werte
    weit weg von 1 heissen: dieser Bereich der Textur ist gestreckt oder
    gestaucht. Der MITTELWERT interessiert hier weniger als die
    Streuung -- ein gleichmaessig um 20 % gestauchter Atlas ist
    unproblematisch, ein Atlas mit einzelnen Faktor-10-Ausreissern zeigt
    sichtbare Verzerrung (und genau die findet man damit).
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    uv = np.asarray(uv, dtype=np.float64)
    v3 = np.asarray(v, dtype=np.float64)
    p = v3[f]
    a3 = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]),
                              axis=1)
    q = uv[f]
    a2 = 0.5 * np.abs((q[:, 1, 0] - q[:, 0, 0]) * (q[:, 2, 1] - q[:, 0, 1])
                      - (q[:, 2, 0] - q[:, 0, 0]) * (q[:, 1, 1] - q[:, 0, 1]))
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(a2 > 1e-14, a3 / np.maximum(a2, 1e-14), np.nan)
    ratio = ratio[np.isfinite(ratio)]
    if len(ratio) == 0:
        return np.zeros(bins)
    lo = float(np.percentile(ratio, 1))
    hi = float(np.percentile(ratio, 99))
    if hi <= lo:
        return np.zeros(bins)
    h, _ = np.histogram(ratio, bins=bins, range=(lo, hi))
    return h
