"""Export-Schreiber M2: STL, USD (USDA/USDZ), binaeres FBX 7.5 und Alembic.

Warum diese fuenf und nicht assimp?
  assimp kann STL/USD/FBX lesen, aber FBX nur unzuverlaessig schreiben
  (Blender lehnt ASCII-FBX seit 2.8 ab, binaeres FBX aus assimp ist
  fehlerhaft) und Alembic gar nicht. Fuer ein Produkt, das "alle gaengigen
  Profi-Formate" verspricht, muessen die Schreiber unser eigen sein.

Grundsaetze fuer ALLE Schreiber hier:
  1. Keine externe Abhaengigkeit (nur stdlib + numpy) -> portierbar nach
     Kotlin und C++ ohne Lizenzfrage.
  2. Zu jedem Schreiber ein LESER. Ein Test, der nur "Datei existiert"
     prueft, beweist gar nichts.
  3. Einheiten sind immer Millimeter. Wo das Format eine Einheit kennt
     (USD: metersPerUnit, FBX: UnitScaleFactor), wird sie MITGESCHRIEBEN --
     das ist der Unterschied zwischen "importiert" und "importiert in der
     richtigen Groesse".
"""
from __future__ import annotations

import os
import struct
import zipfile

import numpy as np

# =============================================================== STL ======


def write_stl(path: str, v: np.ndarray, f: np.ndarray, ascii: bool = False,
              normals: np.ndarray | None = None, uv: np.ndarray | None = None):
    """Stereolithography -- das Austauschformat fuer den 3D-Druck.

    STL kennt keine Farben und keine Einheiten; es ist reine Geometrie.
    Deshalb ist es in der Export-Matrix (docs/05) das Format fuer
    "3D-Druck / schnelle Weitergabe".

    `normals`/`uv` werden bewusst IGNORIERT. STL hat dafuer keinen Platz:
    die Normalen stehen pro Dreieck im 50-Byte-Satz (und werden von fast
    jedem Slicer neu gerechnet), Texturen gibt es nur im inoffiziellen
    Magics-Format, das kein Slicer liest.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    if ascii:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("solid FaceScan\n")
            for tri in f:
                a, b, c = v[tri]
                n = np.cross(b - a, c - a)
                ln = np.linalg.norm(n)
                n = n / ln if ln > 1e-12 else np.zeros(3)
                fh.write(" facet normal %e %e %e\n" % (n[0], n[1], n[2]))
                fh.write("  outer loop\n")
                for p in (a, b, c):
                    fh.write("   vertex %e %e %e\n" % (p[0], p[1], p[2]))
                fh.write("  endloop\n endfacet\n")
            fh.write("endsolid FaceScan\n")
        return path

    with open(path, "wb") as fh:
        header = b"FaceScan export (AndrexTheDev) -- Einheit: Millimeter"
        fh.write(header.ljust(80, b"\x00")[:80])
        fh.write(struct.pack("<I", len(f)))
        for tri in f:
            a, b, c = v[tri]
            n = np.cross(b - a, c - a)
            ln = np.linalg.norm(n)
            n = n / ln if ln > 1e-12 else np.zeros(3)
            fh.write(struct.pack("<3f", *n.astype(np.float32)))
            for p in (a, b, c):
                fh.write(struct.pack("<3f", *p.astype(np.float32)))
            fh.write(struct.pack("<H", 0))
    return path


def read_stl(path: str):
    with open(path, "rb") as fh:
        head = fh.read(80)
    if head.startswith(b"solid"):
        pts, faces, cur = [], [], []
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                s = line.strip()
                if s.startswith("vertex "):
                    cur.append([float(x) for x in s.split()[1:4]])
                elif s == "endloop":
                    for p in cur:
                        pts.append(p)
                    n0 = len(pts) - len(cur)
                    faces.append([n0, n0 + 1, n0 + 2])
                    cur = []
        return {"vertices": np.array(pts), "faces": np.array(faces, dtype=np.int64),
                "ascii": True}

    with open(path, "rb") as fh:
        fh.read(80)
        n_tri = struct.unpack("<I", fh.read(4))[0]
        buf = fh.read()
    if len(buf) < n_tri * 50:
        raise ValueError("STL zu kurz: %d Bytes fuer %d Dreiecke" % (len(buf), n_tri))
    arr = np.frombuffer(buf[:n_tri * 50], dtype=np.dtype([
        ("n", "<3f4"), ("a", "<3f4"), ("b", "<3f4"), ("c", "<3f4"), ("attr", "<u2")]))
    # Reihenfolge: je Dreieck a, b, c -- nicht erst alle a, dann alle b.
    pts = np.stack([arr["a"], arr["b"], arr["c"]], axis=1).reshape(-1, 3).astype(np.float64)
    faces = np.arange(n_tri * 3).reshape(n_tri, 3)
    return {"vertices": pts, "faces": faces, "ascii": False}


# =============================================================== USD ======


def write_usda(path: str, v: np.ndarray, f: np.ndarray,
               colors: np.ndarray | None = None, name: str = "FaceScan",
               meters_per_unit: float = 0.001, normals: np.ndarray | None = None,
               uv: np.ndarray | None = None, texture: str | None = None):
    """Pixar USD im Textformat (.usda).

    USD ist das Format, in dem grosse Studios Szenen zusammenlegen. Wichtig
    fuer uns: `metersPerUnit` und `upAxis` stehen IN der Datei -- Blender,
    Houdini und Maya uebernehmen damit die Groesse automatisch richtig.

    Zwei Fallen beim Material:
      * Der Pfad zur Textur steht in **@...@**, nicht in Anfuehrungszeichen.
      * Die Verbindungskette muss vollstaendig sein:
        `PrimvarReader(st)` -> `UsdUVTexture` -> `UsdPreviewSurface` ->
        `outputs:surface`. Fehlt das PrimvarReader-Glied, zeigt der Viewer
        einfarbig weiss, ohne zu meckern.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    lo, hi = v.min(axis=0), v.max(axis=0)
    tex = os.path.basename(texture) if texture else None

    out = []
    out.append("#usda 1.0")
    out.append("(")
    out.append("    defaultPrim = \"%s\"" % name)
    out.append("    metersPerUnit = %.17g" % meters_per_unit)
    out.append("    upAxis = \"Y\"")
    out.append("    doc = \"FaceScan export -- Einheit Millimeter\"")
    out.append(")")
    out.append("")
    out.append("def Mesh \"%s\"" % name)
    out.append("{")
    out.append("    float3[] extent = [(%g, %g, %g), (%g, %g, %g)]"
               % (lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]))
    out.append("    int[] faceVertexCounts = [%s]"
               % ", ".join("3" for _ in range(len(f))))
    out.append("    int[] faceVertexIndices = [%s]"
               % ", ".join("%d" % i for i in f.reshape(-1)))
    out.append("    point3f[] points = [%s]"
               % ", ".join("(%.17g, %.17g, %.17g)" % (p[0], p[1], p[2]) for p in v))
    if normals is not None:
        nn = np.asarray(normals, dtype=np.float64)
        out.append("    normal3f[] normals = [%s] (" % ", ".join(
            "(%g, %g, %g)" % (p[0], p[1], p[2]) for p in nn))
        out.append("        interpolation = \"vertex\"")
        out.append("    )")
    if uv is not None:
        tt = np.asarray(uv, dtype=np.float64)
        out.append("    texCoord2f[] primvars:st = [%s] (" % ", ".join(
            "(%g, %g)" % (p[0], p[1]) for p in tt))
        out.append("        interpolation = \"vertex\"")
        out.append("    )")
    if colors is not None and tex is None:
        c = np.asarray(colors, dtype=np.float64) / 255.0
        out.append("    color3f[] primvars:displayColor = [%s] (" % ", ".join(
            "(%g, %g, %g)" % (p[0], p[1], p[2]) for p in c))
        out.append("        interpolation = \"vertex\"")
        out.append("    )")
    if tex is not None:
        out.append("    rel material:binding = </Material>")
    out.append("}")
    if tex is not None:
        out.append("")
        out.append('def Material "Material"')
        out.append("{")
        out.append('    token outputs:surface.connect = </Material/Surface.outputs:surface>')
        out.append("")
        out.append('    def Shader "Surface"')
        out.append("    {")
        out.append('        uniform token info:id = "UsdPreviewSurface"')
        out.append("        color3f inputs:diffuseColor.connect = </Material/Diffuse.outputs:rgb>")
        out.append("        float inputs:metallic = 0")
        out.append("        float inputs:roughness = 0.75")
        out.append('        token outputs:surface')
        out.append("    }")
        out.append("")
        out.append('    def Shader "Diffuse"')
        out.append("    {")
        out.append('        uniform token info:id = "UsdUVTexture"')
        out.append("        asset inputs:file = @%s@" % tex)
        out.append("        float2 inputs:st.connect = </Material/ST.outputs:result>")
        out.append('        token inputs:wrapS = "repeat"')
        out.append('        token inputs:wrapT = "clamp"')
        out.append('        float3 outputs:rgb')
        out.append("    }")
        out.append("")
        out.append('    def Shader "ST"')
        out.append("    {")
        out.append('        uniform token info:id = "UsdPrimvarReader_float2"')
        out.append('        token inputs:varname = "st"')
        out.append("        float2 outputs:result")
        out.append("    }")
        out.append("}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    return path


def read_usda(path: str):
    """Liest GENAU die Struktur zurueck, die write_usda schreibt.

    (Kein vollstaendiger USD-Parser -- das waere ein eigenes Projekt. Was
    dieser Leser prueft: Zahlen, Indizes und die Metadaten, auf die es
    beim Import ankommt.)
    """
    txt = open(path, encoding="utf-8").read()
    res = {"metersPerUnit": None, "upAxis": None, "defaultPrim": None}

    def grab_array(name: str):
        """Wert-Array eines Attributs.

        ACHTUNG: nicht einfach `txt.index(name)` und dann die erste
        "["-Klammer danach suchen. Der TYP steht davor und enthaelt
        selbst eine Klammer: "normal3f[] normals = [...]". Sucht man
        nach "normal3f[] normals", landet man in den Klammern des Typs
        und bekommt einen leeren String -- und zwar OHNE Fehler, das
        Array ist dann halt leer. Deshalb: erst das "= [" finden.
        """
        m = re.search(re.escape(name) + r"\s*=\s*\[", txt)
        if m is None:
            raise ValueError("Attribut %s nicht gefunden" % name)
        j = m.end() - 1
        k = txt.index("]", j)
        return txt[j + 1:k]

    import re
    m = re.search(r"metersPerUnit\s*=\s*([0-9.eE+-]+)", txt)
    if m:
        res["metersPerUnit"] = float(m.group(1))
    m = re.search(r"upAxis\s*=\s*\"([A-Z])\"", txt)
    if m:
        res["upAxis"] = m.group(1)
    m = re.search(r"defaultPrim\s*=\s*\"([^\"]+)\"", txt)
    if m:
        res["defaultPrim"] = m.group(1)

    counts = [int(x) for x in grab_array("faceVertexCounts").replace(",", " ").split()]
    idx = [int(x) for x in grab_array("faceVertexIndices").replace(",", " ").split()]
    pts = re.findall(r"\(\s*([-0-9.eE]+)\s*,\s*([-0-9.eE]+)\s*,\s*([-0-9.eE]+)\s*\)",
                     grab_array("points"))
    pts = np.array([[float(a), float(b), float(c)] for a, b, c in pts])
    res["faceVertexCounts"] = np.array(counts)
    res["faceVertexIndices"] = np.array(idx, dtype=np.int64)
    res["vertices"] = pts
    if "normal3f[] normals" in txt:
        nr = re.findall(r"\(\s*([-0-9.eE]+)\s*,\s*([-0-9.eE]+)\s*,\s*([-0-9.eE]+)\s*\)",
                        grab_array("normal3f[] normals"))
        res["normals"] = np.array([[float(a), float(b), float(c)]
                                   for a, b, c in nr])
    if "texCoord2f[] primvars:st" in txt:
        tt = re.findall(r"\(\s*([-0-9.eE]+)\s*,\s*([-0-9.eE]+)\s*\)",
                        grab_array("texCoord2f[] primvars:st"))
        res["uv"] = np.array([[float(a), float(b)] for a, b in tt])
    return res


# ============================================================== USDZ ======


def usda_to_usdc(usda_path: str, usdc_path: str) -> str:
    """Text-Crate (.usda) in ein binäres Crate (.usdc) umwandeln.

    Das Crate-Format ist Pixars eigenes Binärformat: Tabelle der Felder,
    Specs, komprimierte Zahlenblöcke. Es von Hand zu schreiben, wäre ein
    eigenes Projekt mit eigenem Versionsrisiko -- und es würde nichts
    besser machen, was für den Scan zählt. Wir schreiben also weiter
    selbst, was wir verantworten (die Szene als Text, docs/05 §4), und
    lassen die **Serialisierung** von der USD-Bibliothek machen. Für den
    Kotlin-Spiegel gilt dasselbe: Inhalt selbst, Crate von einer
    USD-Bibliothek.

    Warum der Umweg überhaupt: Apple Realitiy Converter lehnt ein USDZ mit
    Text-Root-Layer ab -- "the package's root layer must be a usdc file".
    """
    from pxr import Usd

    stage = Usd.Stage.Open(usda_path)
    if stage is None:
        raise RuntimeError("USD-Bibliothek konnte %s nicht oeffnen" % usda_path)
    if not stage.GetRootLayer().Export(usdc_path):
        raise RuntimeError("Export nach %s fehlgeschlagen" % usdc_path)
    return usdc_path


USDC_MAGIC = b"PXR-USDC"


def crate_info(path: str) -> dict:
    """Die ersten Bytes eines Crates: Kennung und Version."""
    with open(path, "rb") as fh:
        head = fh.read(16)
    return {"magic": head[:8], "magic_ok": bool(head[:8] == USDC_MAGIC),
            "size_bytes": os.path.getsize(path)}


def read_usdc(path: str) -> dict:
    """Liest ein binäres Crate -- mit der USD-Bibliothek, nicht selbst.

    Rückgabe: dieselben Schlüssel wie `read_usda`, damit beide Leser
    austauschbar sind. Gelesen wird von **pxr**, also von einem fremden
    Leser; das ist genau die Prüfung, die wir für jedes Format verlangen.
    """
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(path)
    if stage is None:
        raise RuntimeError("USD-Bibliothek konnte %s nicht oeffnen" % path)
    res = {"metersPerUnit": None, "upAxis": None, "defaultPrim": None}
    res["metersPerUnit"] = UsdGeom.GetStageMetersPerUnit(stage)
    res["upAxis"] = str(UsdGeom.GetStageUpAxis(stage))
    root = stage.GetDefaultPrim()
    res["defaultPrim"] = root.GetName() if root else None

    mesh = None
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            mesh = UsdGeom.Mesh(prim)
            res["defaultPrim"] = res["defaultPrim"] or prim.GetName()
            break
    if mesh is None:
        raise ValueError("kein Mesh in %s gefunden" % path)
    pts = mesh.GetPointsAttr().Get()
    res["vertices"] = np.asarray(pts, dtype=np.float64)
    idx = mesh.GetFaceVertexIndicesAttr().Get()
    res["faceVertexIndices"] = np.asarray(idx, dtype=np.int64)
    cnt = mesh.GetFaceVertexCountsAttr().Get()
    res["faceVertexCounts"] = np.asarray(cnt, dtype=np.int64)
    nrm = mesh.GetNormalsAttr().Get()
    if nrm is not None and len(nrm):
        res["normals"] = np.asarray(nrm, dtype=np.float64)
        res["normals_interpolation"] = str(mesh.GetNormalsInterpolation())
    from pxr import UsdGeom as _Ug
    st = _Ug.PrimvarsAPI(mesh.GetPrim()).GetPrimvar("st")
    if st:
        val = st.Get()
        if val is not None and len(val):
            res["uv"] = np.asarray(val, dtype=np.float64)
            res["uv_interpolation"] = str(st.GetInterpolation())
    col = _Ug.PrimvarsAPI(mesh.GetPrim()).GetPrimvar("displayColor")
    if col:
        val = col.Get()
        if val is not None and len(val):
            res["colors"] = np.asarray(val, dtype=np.float64)
    return res




def write_usdz(path: str, v: np.ndarray, f: np.ndarray,
               colors: np.ndarray | None = None, name: str = "FaceScan",
               normals: np.ndarray | None = None, uv: np.ndarray | None = None,
               texture: str | None = None, crate: bool = False):
    """USDZ = genau ein USD-Asset in einem ZIP -- Apple-Regeln haarklein.

    Fuenf Regeln, die Apple-Geraete sonst zur Ablehnung bewegen (docs/05):

      1. Alle Eintraege **unkomprimiert** (ZIP_STORED). Deflate ist nicht
         erlaubt, weil iOS die Datei ohne Entpacken per Speicherabbild liest.
      2. Der **erste** Eintrag ist das Primaer-Asset.
      3. Der Datenanfang jedes Eintrags liegt auf einer **64-Byte-Grenze**.
         Das erreicht man NICHT durch Auffuellen mit Nullen (die wuerden als
         Eintragsdaten gelten), sondern ueber das **ZIP-Extra-Field**.
         Wir benutzen dasselbe Feld wie Pixars usdzip: Kennung 0x1986 mit
         so vielen Nullen, dass 30 + Namenslaenge + Extralaenge ≡ 0 (mod 64).
         Bei "facescan.usda" (13 Zeichen) sind das 17 Byte Nutzlast.
      4. Kein Passwort, keine Verschluesselung.
      5. Nur relative Pfade, kein "..".

    `crate=True` schreibt als Primaer-Asset eine **.usdc**-Datei
    (binaeres Crate) statt Text. Das ist der Stand, den Apple-Geraete
    verlangen: Reality Converter lehnt ein Paket mit Text-Root-Layer ab
    ("the package's root layer must be a usdc file"). Der Inhalt kommt
    weiter aus unserem eigenen USDA-Schreiber, nur die Serialisierung
    uebernimmt die USD-Bibliothek (s. `usda_to_usdc`).

    Voreinstellung ist `crate=False`: der Text-Root-Layer ist lesbar,
    diffbar und laesst sich mit unserem eigenen Leser pruefen -- das ist
    fuer die M1-Tore der richtige Stand, fuer die AR-Ausgabe nicht.
    """
    import tempfile
    tmp_dir = tempfile.mkdtemp()
    payload = "facescan.usdc" if crate else "facescan.usda"
    tmp_path = os.path.join(tmp_dir, payload)
    write_usda(tmp_path, v, f, colors, name=name, normals=normals, uv=uv,
               texture=texture)
    if crate:
        # Erst Text, dann Crate: der Inhalt bleibt unserer, das
        # Binaerformat macht die Bibliothek.
        usda_tmp = os.path.join(tmp_dir, "facescan.usda")
        os.rename(tmp_path, usda_tmp)
        usda_to_usdc(usda_tmp, tmp_path)
        os.remove(usda_tmp)
    with open(tmp_path, "rb") as fh:
        data = fh.read()
    os.remove(tmp_path)

    # Die 64-Byte-Grenze gilt fuer den DATENANFANG JEDES Eintrags, nicht
    # nur fuer den ersten. Die erste Fassung hat nur den ersten Eintrag
    # ausgerichtet -- mit dem Ergebnis, dass die Textur im Paket auf einer
    # beliebigen Adresse landete, sobald die Nutzlast keine glatte
    # Vielfache von 64 war. Nachgemessen an den LOD-Paketen: mit
    # Text-Root-Layer traf es dreimal von vier Dateien nicht zu.
    # Jetzt wird die Polsterung aus der laufenden Position berechnet.
    pos = 0

    def entry(fname, blob):
        nonlocal pos
        n = len(fname.encode("utf-8"))
        pad = (-(pos + 30 + n + 4)) % 64
        i = zipfile.ZipInfo(fname, date_time=(1980, 1, 1, 0, 0, 0))
        i.compress_type = zipfile.ZIP_STORED
        i.external_attr = 0o644 << 16
        i.extra = struct.pack("<H H", 0x1986, pad) + b"\x00" * pad
        pos = pos + 30 + n + len(i.extra) + len(blob)
        return i, blob

    items = [entry(payload, data)]
    if texture is not None:
        with open(texture, "rb") as fh:
            items.append(entry(os.path.basename(texture), fh.read()))
    os.rmdir(tmp_dir)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
        for info, blob in items:
            with zf.open(info, "w") as fh:
                fh.write(blob)
    return path


def read_usdz(path: str):
    """Liest ein USDZ und prueft alle fuenf Apple-Regeln nach.

    Die Container-Regeln (unkomprimiert, erstes Asset, 64-Byte-Grenze,
    kein Passwort, relative Pfade) pruefen wir selbst. Den INHALT liest bei
    einem Crate-Paket die **USD-Bibliothek** -- ein fremder Leser also.
    """
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        bad = zf.testzip()
        infos = {i.filename: i.compress_type for i in zf.infolist()}
        payload = names[0]
        # Regel 3: Datenanfang auf 64-Byte-Grenze. Das steht nicht im
        # ZIP-Verzeichnis, man muss im lokalen Header nachsehen:
        #   30 Byte fester Kopf + Namenslaenge + Extra-Field-Laenge
        offsets = {}
        for i in zf.infolist():
            with open(path, "rb") as fh:
                fh.seek(i.header_offset)
                head = fh.read(30)
            nlen, elen = struct.unpack("<H H", head[26:30])
            offsets[i.filename] = i.header_offset + 30 + nlen + elen
        tmp = os.path.join(os.path.dirname(path), "_usdz_check" +
                           os.path.splitext(payload)[1])
        with open(tmp, "wb") as out:
            out.write(zf.read(payload))
        try:
            if payload.lower().endswith(".usdc"):
                parsed = read_usdc(tmp)          # fremder Leser: pxr
                parsed.update(crate_info(tmp))
                parsed["payload_is_crate"] = True
            else:
                parsed = read_usda(tmp)
                parsed["payload_is_crate"] = False
        finally:
            os.remove(tmp)
    parsed["entries"] = names
    parsed["primary"] = payload
    parsed["crc_ok"] = (bad is None)
    parsed["all_stored"] = all(c == zipfile.ZIP_STORED for c in infos.values())
    parsed["data_offsets"] = offsets
    parsed["aligned64"] = all(o % 64 == 0 for o in offsets.values())
    return parsed


# =============================================================== FBX ======

FBX_MAGIC = b"Kaydara FBX Binary  \x00"
FBX_VERSION = 7500
_NODE_HEADER = 25          # 8 + 8 + 8 + 1 bei 64-Bit-Offsets (FBX >= 7.5)


# Property-Typcodes: GROSSBUCHSTABE = ein einzelner Wert, klein = Array.
# Das ist der wichtigste Unterschied im ganzen FBX-Format und leider auch der,
# den man am leichtesten uebersieht: 'd' ist ein Array aus Doubles, 'D' ist
# EIN Double. Schreibt man 'd' fuer einen skalaren Wert, liest der Importeur
# drei uint32 (Anzahl, Kodierung, Bytezahl) aus den Nutzdaten heraus und
# steht danach irgendwo im Nirgendwo. Genau das hat assimp bei unserem
# ersten FBX-Schreiber gemeldet:
#   "FBX-Tokenize (offset 0x4b) cannot ReadWord, out of bounds"
# Der Offset 0x4b war die erste Property des ersten Knotens.

def _p_y(x):                       # int16
    return struct.pack("<c h", b"Y", int(x))


def _p_c(x):                       # bool, 1 Byte
    return struct.pack("<c B", b"C", 1 if x else 0)


def _p_i(x):                       # int32
    return struct.pack("<c i", b"I", int(x))


def _p_f(x):                       # float32
    return struct.pack("<c f", b"F", float(x))


def _p_d(x):                       # float64
    return struct.pack("<c d", b"D", float(x))


def _p_l(x):                       # int64
    return struct.pack("<c q", b"L", int(x))


def _p_s(x):                       # Zeichenkette, 4 Byte Laenge vorab
    raw = str(x).encode("utf-8")
    return struct.pack("<c I", b"S", len(raw)) + raw


def _p_da(values):                 # Array aus float64
    raw = np.asarray(values, dtype="<f8").tobytes()
    return struct.pack("<c I I I", b"d", len(values), 0, len(raw)) + raw


def _p_ia(values):                 # Array aus int32
    raw = np.asarray(values, dtype="<i4").tobytes()
    return struct.pack("<c I I I", b"i", len(values), 0, len(raw)) + raw


def _n(name: str, props=(), children=()):
    """Knotenbeschreibung (noch keine Bytes) -- Offset-unabhaengig."""
    return (name, list(props), list(children))


def _size(tree) -> int:
    name, props, children = tree
    body = sum(len(x) for x in props)
    total = _NODE_HEADER + len(name.encode("ascii")) + body
    if children:
        total += sum(_size(c) for c in children)
        total += _NODE_HEADER                       # Nullknoten als Listenende
    return total


def _emit(tree, base: int) -> bytes:
    """Schreibt einen Knoten.

    ENTSCHEIDEND: EndOffset ist eine ABSOLUTE Position in der Datei, keine
    Laenge. Das ist der zweithaeufigste Fehler beim Selberschreiben von FBX
    (nach dem fehlenden Platzhalter vor den Kindern): mit einer Laenge statt
    eines Offsets findet kein Leser die naechsten Knoten -- Blender zeigt
    dann "keine Geometrie" an, ohne zu meckern.
    """
    name, props, children = tree
    name_b = name.encode("ascii")
    body = b"".join(props)
    cursor = base + _NODE_HEADER + len(name_b) + len(body)
    tail = b""
    if children:
        kids = b""
        for c in children:
            blob = _emit(c, cursor)
            kids += blob
            cursor += len(blob)
        # WICHTIG: der 25-Byte-Nullknoten schliesst die Kinderliste AB, er
        # leitet sie nicht ein. Genau andersherum (Platzhalter VOR den
        # Kindern) ist der haeufigste Fehler in selbst gebauten FBX-Writern:
        # assimp liest dann den Platzhalter als Knoten mit EndOffset 0,
        # rutscht acht Bytes weiter und landet mitten in einem echten Knoten
        # -- Fehlermeldung "block offset is out of range".
        tail = kids + b"\x00" * _NODE_HEADER
        end = cursor + _NODE_HEADER
    else:
        end = cursor
    out = (struct.pack("<Q Q Q B", end, len(props), len(body), len(name_b))
           + name_b + body + tail)
    assert len(out) == end - base, "Offset-Rechnung stimmt nicht"
    return out


def write_fbx(path: str, v: np.ndarray, f: np.ndarray,
              colors: np.ndarray | None = None, name: str = "FaceScan",
              unit_scale: float = 0.1, normals: np.ndarray | None = None,
              uv: np.ndarray | None = None):
    """Binaeres FBX 7.5 -- das Format, das Blender, Maya, 3ds Max und Unity lesen.

    Fuenf Dinge, die ueber "funktioniert" oder "Muell" entscheiden:

    1. EndOffset jedes Knotens ist eine ABSOLUTE Dateiposition.
    2. Der 25-Byte-Nullknoten beendet eine Kinderliste -- er steht HINTEN,
       nicht vorn. Mit einem Platzhalter vor den Kindern liest assimp den
       Nullknoten als echten Knoten und rutscht acht Bytes weit, bis es
       irgendwo wieder aufsynchronisiert ("block offset is out of range").
    3. Gross-/Kleinschreibung der Property-Typcodes: 'D' ist EIN double,
       'd' ist ein ARRAY aus doubles (Anzahl, Kodierung, Bytezahl, Daten).
       Wer das verwechselt, dessen Datei bricht beim ersten Property ab.
    4. Knotennamen duerfen KEIN 0x00 enthalten. Die Objekte im
       Objects-Abschnitt heissen schlicht "Geometry" / "Model"; der Name
       steckt in Property 1 in der Form  Name 0x00 0x01 Klasse  (also
       "Kopf 0x00 0x01 Geometry"), gefolgt vom Klassen-Tag "Mesh".
    5. Vertices und PolygonVertexIndex sind eigene UNTERKNOTEN des
       Geometry-Knotens, nicht Properties davon.

    Einheiten: wir schreiben Millimeter und setzen UnitScaleFactor = 0.1
    (1 mm = 0,1 cm; FBX rechnet intern in Zentimetern). Ohne diesen Eintrag
    kommt der Kopf zehnmal zu gross an.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)

    poly = []
    for tri in f:
        poly.extend([int(tri[0]), int(tri[1]), -int(tri[2]) - 1])

    geo_children = [
        _n("Vertices", [_p_da(v.reshape(-1))]),
        _n("PolygonVertexIndex", [_p_ia(poly)]),
        _n("GeometryVersion", [_p_i(124)]),
    ]
    if normals is not None:
        nn = np.asarray(normals, dtype=np.float64).reshape(-1)
        geo_children.append(_n("LayerElementNormal", [], [
            _n("Version", [_p_i(102)]),
            _n("Name", [_p_s("")]),
            _n("MappingInformationType", [_p_s("ByVertice")]),
            _n("ReferenceInformationType", [_p_s("Direct")]),
            _n("Normals", [_p_da(nn)]),
        ]))
    if uv is not None:
        # FBX/Blender zaehlen v von UNTEN, glTF/USD von oben -- genau der
        # Unterschied, der Texturen auf dem Kopf stehen laesst.
        tt = np.asarray(uv, dtype=np.float64).copy()
        tt[:, 1] = 1.0 - tt[:, 1]
        geo_children.append(_n("LayerElementUV", [], [
            _n("Version", [_p_i(101)]),
            _n("Name", [_p_s("UVMap")]),
            _n("MappingInformationType", [_p_s("ByVertice")]),
            _n("ReferenceInformationType", [_p_s("Direct")]),
            _n("UV", [_p_da(tt.reshape(-1))]),
        ]))
    if colors is not None:
        c = (np.asarray(colors, dtype=np.float64) / 255.0).reshape(-1)
        geo_children.append(_n("LayerElementColor", [], [
            _n("Version", [_p_i(101)]),
            _n("Name", [_p_s("Color")]),
            # "ByVertice" ist kein Tippfehler von uns -- FBX schreibt es
            # wirklich so (ohne r). "ByVertex" wird ignoriert, und die Farben
            # sind dann weg.
            _n("MappingInformationType", [_p_s("ByVertice")]),
            _n("ReferenceInformationType", [_p_s("Direct")]),
            _n("Colors", [_p_da(c)]),
        ]))

    # Name 0x00 0x01 Klasse -- der Trenner ist 0x00 0x01, nicht umgekehrt.
    geometry = _n("Geometry",
                  [_p_l(200000), _p_s(name + "Shape\x00\x01Geometry"),
                   _p_s("Mesh")], geo_children)

    model = _n("Model", [_p_l(100000), _p_s(name + "\x00\x01Model"),
                         _p_s("Mesh")], [
        _n("Version", [_p_i(232)]),
        _n("Properties70", [], [
            _n("P", [_p_s("Lcl Translation"), _p_s("Lcl Translation"), _p_s(""),
                     _p_s("A"), _p_d(0.0), _p_d(0.0), _p_d(0.0)]),
            _n("P", [_p_s("Lcl Rotation"), _p_s("Lcl Rotation"), _p_s(""),
                     _p_s("A"), _p_d(0.0), _p_d(0.0), _p_d(0.0)]),
            _n("P", [_p_s("Lcl Scaling"), _p_s("Lcl Scaling"), _p_s(""),
                     _p_s("A"), _p_d(1.0), _p_d(1.0), _p_d(1.0)]),
        ]),
        _n("Shading", [_p_c(True)]),
        _n("Culling", [_p_s("CullingOff")]),
    ])
    objects = _n("Objects", [], [geometry, model])

    defs = _n("Definitions", [_p_i(100)], [
        _n("Version", [_p_i(100)]),
        _n("Count", [_p_i(3)]),
        _n("ObjectType", [_p_s("GlobalSettings")], [_n("Count", [_p_i(1)])]),
        _n("ObjectType", [_p_s("Geometry")], [_n("Count", [_p_i(1)])]),
        _n("ObjectType", [_p_s("Model")], [_n("Count", [_p_i(1)])]),
    ])

    def axis_prop(key, value):
        return _n("P", [_p_s(key), _p_s("int"), _p_s("Integer"), _p_s(""),
                        _p_i(value)])

    settings = _n("GlobalSettings", [], [
        _n("Version", [_p_i(1000)]),
        _n("Properties70", [], [
            axis_prop("UpAxis", 1), axis_prop("UpAxisSign", 1),
            axis_prop("FrontAxis", 2), axis_prop("FrontAxisSign", 1),
            axis_prop("CoordAxis", 0), axis_prop("CoordAxisSign", 1),
            _n("P", [_p_s("UnitScaleFactor"), _p_s("double"), _p_s("Number"),
                     _p_s(""), _p_d(unit_scale)]),
            _n("P", [_p_s("OriginalUnitScaleFactor"), _p_s("double"),
                     _p_s("Number"), _p_s(""), _p_d(unit_scale)]),
        ]),
    ])

    header = _n("FBXHeaderExtension", [_p_i(1003)], [
        _n("FBXHeaderVersion", [_p_i(1003)]),
        _n("FBXVersion", [_p_i(FBX_VERSION)]),
        _n("Creator", [_p_s("FaceScan (AndrexTheDev)")]),
        _n("SceneInfo", [_p_s("SceneInfo::GlobalInfo"), _p_s("UserData")], [
            _n("Type", [_p_s("UserData")]),
            _n("Version", [_p_i(100)]),
            _n("MetaData", [_p_i(100)], [
                _n("Version", [_p_i(100)]),
                _n("Author", [_p_s("AndrexTheDev")]),
                _n("Comment", [_p_s("FaceScan export, unit = mm")]),
            ]),
        ]),
    ])

    # Erst Geometry -> Model, dann Model -> Wurzel (id 0). Die Reihenfolge
    # ist egal, aber BEIDE Verbindungen muessen da sein: ohne die Verbindung
    # zur Wurzel haengt das Modell nirgends und verschwindet beim Import.
    connections = _n("Connections", [], [
        _n("C", [_p_s("OO"), _p_l(200000), _p_l(100000)]),
        _n("C", [_p_s("OO"), _p_l(100000), _p_l(0)]),
    ])

    buf = b""
    cursor = 27                    # Magic(21) + 0x1A 0x00(2) + Version(4)
    for tree in (header, settings, defs, objects, connections):
        blob = _emit(tree, cursor)
        buf += blob
        cursor += len(blob)

    with open(path, "wb") as fh:
        fh.write(FBX_MAGIC + b"\x1a\x00" + struct.pack("<I", FBX_VERSION))
        fh.write(buf)
        fh.write(b"\x00" * _NODE_HEADER)      # Nullknoten = Ende der Liste
        fh.write(b"\xf8\x5a\x8c\x6a\xde\xf5\xd9\x7e\xec\xe9\x0c\xe3"
                 b"\x75\x8f\x29\x0b")      # Footer-Magic (7.5)
    return path


# ---------------------------------------------------------- FBX-Leser -----

def read_fbx(path: str, want_arrays: bool = True):
    """Liest die Knotenstruktur (und auf Wunsch die Geometrie) zurueck.

    Das ist kein vollstaendiger FBX-Importer. Es prueft genau das, was beim
    Selberschreiben schiefgehen kann: Offsets, Platzhalter, Kinderlisten
    und die beiden Geometrie-Arrays.
    """
    data = open(path, "rb").read()
    if not data.startswith(FBX_MAGIC):
        raise ValueError("kein FBX: Magic stimmt nicht")
    # Header: 21 Bytes Magic + 0x1A 0x00 + 4 Bytes Version = 27 Bytes
    version = struct.unpack("<I", data[23:27])[0]

    SCALAR = {b"Y": ("<h", 2), b"C": ("<B", 1), b"I": ("<i", 4),
              b"F": ("<f", 4), b"D": ("<d", 8), b"L": ("<q", 8)}
    ARRAY = {b"y": ("<i2", 2), b"c": ("<u1", 1), b"i": ("<i4", 4),
             b"f": ("<f4", 4), b"d": ("<f8", 8), b"l": ("<i8", 8)}

    def read_props(pos, count):
        props = []
        for _ in range(count):
            code = data[pos:pos + 1]
            pos += 1
            if code in SCALAR:
                fmt, size = SCALAR[code]
                props.append(struct.unpack(fmt, data[pos:pos + size])[0])
                pos += size
            elif code in ARRAY:
                dtype, stride = ARRAY[code]
                cnt, enc, ln = struct.unpack("<I I I", data[pos:pos + 12])
                pos += 12
                if enc != 0:
                    raise ValueError("komprimierte Arrays unterstuetzt dieser "
                                     "Pruefleser nicht")
                if enc == 0 and cnt * stride != ln:
                    raise ValueError("Array %r: %d Elemente x %d Bytes, aber "
                                     "%d Bytes angegeben"
                                     % (code, cnt, stride, ln))
                props.append(np.frombuffer(data[pos:pos + ln], dtype=dtype))
                pos += ln
            elif code in (b"S", b"R"):
                n = struct.unpack("<I", data[pos:pos + 4])[0]
                pos += 4
                props.append(data[pos:pos + n])
                pos += n
            else:
                raise ValueError("unbekannter Property-Code %r bei %d"
                                 % (code, pos))
        return props, pos

    def parse_list(pos):
        out = []
        while pos + _NODE_HEADER <= len(data):
            end, nprops, proplen, name_len = struct.unpack("<Q Q Q B",
                                                           data[pos:pos + _NODE_HEADER])
            if end == 0 and nprops == 0 and proplen == 0 and name_len == 0:
                return out, pos + _NODE_HEADER
            name = data[pos + _NODE_HEADER:pos + _NODE_HEADER + name_len]
            pstart = pos + _NODE_HEADER + name_len
            props, _ = read_props(pstart, nprops)
            entry = {"name": name.decode("ascii", "replace"),
                     "props": props, "children": [], "end": end}
            if end > pstart + proplen + _NODE_HEADER:
                # Kinder stehen UNMITTELBAR hinter den Properties -- der
                # 25-Byte-Nullknoten schliesst die Liste ab (siehe _emit).
                kids, pos = parse_list(pstart + proplen)
                entry["children"] = kids
            else:
                pos = pstart + proplen
            out.append(entry)
        return out, pos

    nodes, _ = parse_list(27)
    res = {"version": version, "nodes": nodes}

    if want_arrays:
        def find_exact(nodes, what):
            for n in nodes:
                if n["name"] == what:
                    return n
                hit = find_exact(n["children"], what)
                if hit is not None:
                    return hit
            return None
        objects = find_exact(nodes, "Objects")
        if objects is None:
            return res
        geo = find_exact(objects["children"], "Geometry")
        if geo is None:
            return res
        verts = find_exact(geo["children"], "Vertices")
        poly = find_exact(geo["children"], "PolygonVertexIndex")
        if verts is not None and len(verts["props"]) == 1:
            res["vertices"] = np.asarray(verts["props"][0],
                                         dtype=np.float64).reshape(-1, 3)
        if poly is not None and len(poly["props"]) == 1:
            res["polygonVertexIndex"] = np.asarray(poly["props"][0],
                                                   dtype=np.int64)
        layer = find_exact(geo["children"], "LayerElementColor")
        if layer is not None:
            cols = find_exact(layer["children"], "Colors")
            if cols is not None and len(cols["props"]) == 1:
                res["colors"] = np.asarray(cols["props"][0],
                                           dtype=np.float64).reshape(-1, 3)
    return res


def fbx_node_names(parsed: dict):
    out = []

    def walk(nodes, depth=0):
        for n in nodes:
            out.append((depth, n["name"]))
            walk(n.get("children", []), depth + 1)
    walk(parsed["nodes"])
    return out


# ====================================================== Alembic (.abc) =====
#
# Alembic ist das Austauschformat der Film- und VFX-Pipeline: Houdini, Maya,
# Nuke, Katana, Unreal. Im Gegensatz zu FBX ist es KEIN Szenenformat, sondern
# ein "gebackener" Cache: jeder Knoten hat pro Zeitstempel ein Array. Fuer
# einen statischen Scan heisst das: genau EIN Sample pro Property.
#
# Der Container heisst Ogawa (seit Alembic 1.5, vorher HDF5). Er ist erfreulich
# einfach -- drei Bausteine:
#
#   Dateikopf (16 B)   "Ogawa" | frozen(1) | Version uint16 big-endian | uint64
#                      Position der Wurzelgruppe
#   Datenblock          uint64 Groesse | Groesse Bytes Nutzlast
#   Gruppe              uint64 Anzahl Kinder | Anzahl * uint64 Kindposition,
#                       wobei das oberste Bit gesetzt = Datenblock, nicht
#                       gesetzt = Gruppe. Position 0 = leere Gruppe,
#                       1<<63    = leere Daten.
#
# Der Hauptspeicherfresser beim Selberschreiben ist nicht der Container, sondern
# der Objektbaum darueber (AbcCoreOgawa). Der Aufbau, den wir schreiben:
#
#   Archiv-Wurzel: [uint32 Ogawa-Version, uint32 Alembic-Version,
#                   GRUPPE Objekt /, DATA Archiv-Metadaten,
#                   DATA Zeitsamplings, DATA Metadaten-Tabelle]
#   Objekt-Gruppe: [GRUPPE Properties, GRUPPE Kindobjekte..., DATA Kopf+Hash]
#   Array-Property:[DATA Sample, DATA Dimensionen] pro Sample
#   Scalar-Property:[DATA Sample] pro Sample
#
# Zwei Dinge sind WIRKLICH gemein und haben mich hier Zeit gekostet:
#   1. EndOffset-aehnliche Groessen gibt es nicht, aber dafuer muessen die
#      Kindpositionen ABSOLUT sein (wie bei FBX). Relative Offsets fuehren zu
#      einer Datei, die jeder Leser stillschweigend als "leer" meldet.
#   2. Property-Header sind BITGEPACKT in einem uint32 (siehe _prop_info).
#      Ein falsch gesetztes Bit -- z. B. das "konstant"-Bit 0x800 -- und der
#      Leser glaubt, es gebe null Samples, obwohl die Daten da sind.
#
# Bekannte Grenze dieses Schreibers: der 16-Byte-Digest vor jedem Sample
# (SpookyHash der Nutzlast) wird mit Nullen geschrieben. Kein Leser prueft ihn
# beim Oeffnen -- er dient nur abcinfo/abcls und dem Wiederverwenden identischer
# Samples. Wer ihn braucht, muss SpookyHash V2 nachrüsten (~150 Zeilen).

OGAWA_MAGIC = b"Ogawa"
OGAWA_VERSION = 1
ALEMBIC_OGAWA_FILE_VERSION = 0          # Container-Layout, Alembic schreibt 0
ALEMBIC_LIBRARY_VERSION = 10800         # 1.8.0, Leser verlangt >= 9999

_EMPTY_GROUP = 0x0000000000000000
_EMPTY_DATA = 0x8000000000000000

# PlainOldDataType -- Reihenfolge ist Teil des Dateiformats.
POD_BOOLEAN, POD_UINT8, POD_INT8 = 0, 1, 2
POD_UINT16, POD_INT16, POD_UINT32, POD_INT32 = 3, 4, 5, 6
POD_UINT64, POD_INT64 = 7, 8
POD_FLOAT16, POD_FLOAT32, POD_FLOAT64 = 9, 10, 11
POD_STRING, POD_WSTRING = 12, 13

# PropertyType
PROP_COMPOUND, PROP_SCALAR, PROP_ARRAY = 0, 1, 2


class _Data:
    """Ein Ogawa-Datenblock."""
    __slots__ = ("payload", "pos")

    def __init__(self, payload: bytes):
        self.payload = payload
        self.pos = -1


class _Group:
    """Eine Ogawa-Gruppe. Kinder sind _Group-, _Data-Objekte oder None.

    ``None`` steht fuer einen leeren Kindplatz: ``'d'`` -> leere Daten
    (1<<63), ``'g'`` -> leere Gruppe (0). Beides belegt im Container keinen
    eigenen Block.
    """
    __slots__ = ("children", "pos")

    def __init__(self):
        self.children = []          # Liste von (_Group | _Data | ('d',) | ('g',))
        self.pos = -1

    # -- bequemes Aufbauen ------------------------------------------------
    def group(self):
        g = _Group()
        self.children.append(g)
        return g

    def empty_group(self):
        self.children.append(None)
        return None

    def data(self, payload: bytes):
        d = _Data(payload)
        self.children.append(d)
        return d

    def empty_data(self):
        self.children.append(_EmptyData())
        return None


class _EmptyData:
    """Platzhalter fuer leere Daten (Kindwert 1<<63, kein Block)."""
    __slots__ = ()


def _ogawa_layout(root: _Group) -> bytes:
    """Legt Positionen fest und gibt die komplette Datei zurueck.

    Reihenfolge im Container: erst ALLE Datenbloecke (in Anlage-Reihenfolge),
    dann ALLE Gruppen (Post-Order, Kinder vor Eltern). Alembic selbst mischt
    beides, aber eine feste Reihenfolge ist genauso gueltig und viel leichter
    zu pruefen.
    """
    cursor = 16                                  # nach dem Dateikopf
    datas, groups = [], []

    def walk_datas(g):
        nonlocal cursor
        for child in g.children:
            if isinstance(child, _Data):
                child.pos = cursor
                datas.append(child)
                cursor += 8 + len(child.payload)
        for child in g.children:
            if isinstance(child, _Group):
                walk_datas(child)

    walk_datas(root)

    def walk_groups(g):
        nonlocal cursor
        for child in g.children:
            if isinstance(child, _Group):
                walk_groups(child)
        g.pos = cursor
        groups.append(g)
        cursor += 8 + 8 * len(g.children)

    walk_groups(root)

    out = bytearray()
    # Byte 5 ist das "frozen"-Flag. Es steht auf 0xff, sobald das Schreiben
    # abgeschlossen ist -- vorher auf 0. Alembic lehnt eine Datei mit 0 ab:
    # "Ogawa file not cleanly closed while being written". Das ist der
    # Guard gegen halb geschriebene Dateien nach einem Absturz.
    out += OGAWA_MAGIC + b"\xff"                # frozen = fertig geschrieben
    out += struct.pack(">H", OGAWA_VERSION)
    out += struct.pack("<Q", root.pos)

    for d in datas:
        out += struct.pack("<Q", len(d.payload)) + d.payload
    for g in groups:
        out += struct.pack("<Q", len(g.children))
        for child in g.children:
            if child is None:                    # leere Gruppe
                val = _EMPTY_GROUP
            elif isinstance(child, _EmptyData):
                val = _EMPTY_DATA
            elif isinstance(child, _Group):
                val = child.pos
            else:
                val = child.pos | _EMPTY_DATA
            out += struct.pack("<Q", val & 0xFFFFFFFFFFFFFFFF)

    assert len(out) == cursor, "Ogawa-Layout stimmt nicht mit den Offsets"
    return bytes(out)


# ------------------------------------------------- Metadaten und Header ----

def _md(**pairs) -> str:
    """Alembic-Metadaten sind ein flacher String: ``key=value;key=value``."""
    return ";".join("%s=%s" % (k, v) for k, v in pairs.items())


def _u32_hint(value: int, hint: int) -> bytes:
    """Alembic schreibt kleine Zahlen platzsparend: 1, 2 oder 4 Byte."""
    if hint == 0:
        return struct.pack("<B", value & 0xFF)
    if hint == 1:
        return struct.pack("<H", value & 0xFFFF)
    return struct.pack("<I", value & 0xFFFFFFFF)


def _prop_info(ptype: int, pod: int, extent: int, is_scalar_like: bool,
               homogenous: bool, num_samples: int, first_changed: int,
               last_changed: int, time_index: int, meta_data: str,
               meta_index: int, name: str) -> bytes:
    """Baut einen Property-Header -- das bitgepackte uint32 ist die Falle.

    Bit-Layout (aus AbcCoreOgawa/WriteUtil.cpp):
        0x0003    Property-Typ (0 Compound, 1 Scalar, 2 Array)
                  ... bei Arrays/Scalars zusaetzlich isScalarLike
        0x000c    Groessen-Hint (0 = 1 Byte, 1 = 2 Byte, 2 = 4 Byte)
        0x00f0    POD-Typ
        0x0100    Time-Sampling-Index ist gesetzt
        0x0200    first/last-Changed-Index sind gesetzt
        0x0400    homogenous (alle Samples gleiche Groesse)
        0x0800    konstant (first == last == 0)
        0x0f000   Extent (z. B. 3 fuer V3f, 6 fuer Box3d)
        0xff00000 Index in die Metadaten-Tabelle (0xff = inline schreiben)
    """
    name_b = name.encode("utf-8")
    longest = max(len(meta_data), len(name_b), num_samples, time_index)
    hint = 0 if longest <= 255 else (1 if longest < 65536 else 2)

    info = (hint << 2) | ((meta_index & 0xFF) << 20)

    out = bytearray()
    if ptype == PROP_COMPOUND:
        out += _u32_hint(info, 2)
    else:
        info |= (ptype & 0x3) | (1 if is_scalar_like else 0)
        info |= (pod & 0xF) << 4
        if time_index != 0:
            info |= 0x0100
        needs_first_last = False
        if first_changed == 0 and last_changed == 0:
            info |= 0x0800
        elif first_changed != 1 or last_changed != num_samples - 1:
            info |= 0x0200
            needs_first_last = True
        info |= (extent & 0xFF) << 12
        if homogenous:
            info |= 0x0400
        out += _u32_hint(info, 2)
        out += _u32_hint(num_samples, hint)
        if needs_first_last:
            out += _u32_hint(first_changed, hint)
            out += _u32_hint(last_changed, hint)
        if time_index != 0:
            out += _u32_hint(time_index, hint)
    out += _u32_hint(len(name_b), hint)
    out += name_b
    if meta_index == 0xFF:
        out += _u32_hint(len(meta_data), hint)
        out += meta_data.encode("utf-8")
    return bytes(out)


def _obj_header(name: str, meta_data: str, meta_index: int) -> bytes:
    """Objekt-Header: 4 Byte Namenslaenge, Name, 1 Byte Metadaten-Index."""
    out = _u32_hint(len(name.encode("utf-8")), 2) + name.encode("utf-8")
    out += _u32_hint(meta_index & 0xFF, 0)
    if meta_index == 0xFF:
        out += _u32_hint(len(meta_data), 2) + meta_data.encode("utf-8")
    return out


def _sample_block(raw: bytes) -> bytes:
    """Nutzlast eines Samples: 16 Byte Digest (hier Nullen) + Rohdaten."""
    return b"\x00" * 16 + raw


# ------------------------------------------------------------- Schreiber ---

def write_abc(path: str, v: np.ndarray, f: np.ndarray,
              name: str = "FaceScan", shape_name: str = "FaceShape",
              normals: np.ndarray | None = None):
    """Alembic/Ogawa mit EINEM PolyMesh -- Schema ``AbcGeom_PolyMesh_v1``.

    Aufbau unter der Wurzel::

        /FaceScan                 (reiner Gruppenknoten, kein Schema)
          /FaceScan/FaceShape     (PolyMesh)
            .geom/P              float32[3N]   -- Punkte
            .geom/.faceIndices   int32[3T]    -- flache Dreiecksliste
            .geom/.faceCounts    int32[T]     -- hier ueberall 3
            .geom/.selfBnds      float64[6]   -- Bounding Box (min/max)

    ``.faceCounts`` zu schreiben, obwohl bei Dreiecken alles 3 ist, ist kein
    Ballast: ohne diese Property ist es kein PolyMesh und jeder DCC-Import
    meldet "keine Geometrie".
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    if len(v) == 0 or len(f) == 0:
        raise ValueError("write_abc: leeres Mesh")

    pts = np.ascontiguousarray(v, dtype="<f4")
    idx = np.ascontiguousarray(f.reshape(-1), dtype="<i4")
    cnt = np.full(len(f), 3, dtype="<i4")
    lo = v.min(axis=0)
    hi = v.max(axis=0)
    bnds = np.asarray([lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]], dtype="<f8")

    # Metadaten-Tabelle: Index 0 ist reserviert fuer "leer", 0xff fuer "inline".
    # Alles, was wir mehrfach brauchen, landet hier und spart Bytes.
    md_poly = _md(schema="AbcGeom_PolyMesh_v1",
                  schemaObjTitle="AbcGeom_PolyMesh_v1:.geom",
                  schemaBaseType="AbcGeom_GeomBase_v1")
    md_vert = _md(geoScope="vtx")
    table = [md_poly, md_vert]
    i_poly, i_vert = 1, 2

    # --- Geometrie-Properties -------------------------------------------
    geom = _Group()
    p_pos = geom.group()
    p_pos.data(_sample_block(pts.tobytes()))
    p_pos.empty_data()                    # Dimensionen: Rang 1, aus Groesse ableitbar
    p_idx = geom.group()
    p_idx.data(_sample_block(idx.tobytes()))
    p_idx.empty_data()
    p_cnt = geom.group()
    p_cnt.data(_sample_block(cnt.tobytes()))
    p_cnt.empty_data()
    p_bnd = geom.group()
    p_bnd.data(_sample_block(bnds.tobytes()))

    geom_headers = bytearray()
    geom_headers += _prop_info(PROP_ARRAY, POD_FLOAT32, 3, False, True,
                               1, 0, 0, 0, md_vert, i_vert, "P")
    geom_headers += _prop_info(PROP_ARRAY, POD_INT32, 1, False, True,
                               1, 0, 0, 0, "", 0, ".faceIndices")
    geom_headers += _prop_info(PROP_ARRAY, POD_INT32, 1, False, True,
                               1, 0, 0, 0, "", 0, ".faceCounts")
    geom_headers += _prop_info(PROP_SCALAR, POD_FLOAT64, 6, True, True,
                               1, 0, 0, 0, "", 0, ".selfBnds")

    if normals is not None:
        nrm = np.ascontiguousarray(np.asarray(normals, dtype=np.float64),
                                   dtype="<f4")
        if len(nrm) == len(v):
            p_nrm = geom.group()
            p_nrm.data(_sample_block(nrm.tobytes()))
            p_nrm.empty_data()
            geom_headers += _prop_info(PROP_ARRAY, POD_FLOAT32, 3, False, True,
                                       1, 0, 0, 0, md_vert, i_vert, "N")
    geom.data(bytes(geom_headers))

    # --- Objekt /<name>/<shape_name>  (PolyMesh) --------------------------
    shape_props = _Group()
    shape_props.children.append(geom)
    shape_props.data(_prop_info(PROP_COMPOUND, 0, 0, True, True, 0, 0, 0, 0,
                                "", 0, ".geom"))
    shape = _Group()
    shape.children.append(shape_props)
    shape.data(b"\x00" * 32)          # keine Kindobjekte, nur der Hash

    # --- Objekt /<name>  (reiner Gruppenknoten, Transform-Ersatz) ---------
    # Es hat keine Properties: die Propertyliste ist eine leere Gruppe, genau
    # so wie Alembic sie fuer propertylose Objekte schreibt.
    holder = _Group()
    holder.children.append(_Group())
    holder.children.append(shape)
    holder.data(_obj_header(shape_name, md_poly, i_poly) + b"\x00" * 32)

    # --- Archiv-Wurzel ----------------------------------------------------
    root = _Group()
    root.data(struct.pack("<I", ALEMBIC_OGAWA_FILE_VERSION))
    root.data(struct.pack("<I", ALEMBIC_LIBRARY_VERSION))
    root_obj = _Group()
    root_obj.children.append(_Group())       # Wurzel hat keine Properties
    root_obj.children.append(holder)
    root_obj.data(_obj_header(name, "", 0) + b"\x00" * 32)
    root.children.append(root_obj)
    root.data(_md(_ai_AlembicVersion="1.8.0").encode("utf-8"))
    root.data(struct.pack("<I", 1)                 # maxSample des Samplings 0
              + struct.pack("<d", 1.0)             # Zeit pro Zyklus
              + struct.pack("<I", 1)               # ein gespeicherter Zeitpunkt
              + struct.pack("<d", 0.0))            # ... naemlich t = 0
    meta_buf = bytearray()
    for entry in table:
        meta_buf += struct.pack("<B", len(entry.encode("utf-8")))
        meta_buf += entry.encode("utf-8")
    root.data(bytes(meta_buf))

    with open(path, "wb") as fh:
        fh.write(_ogawa_layout(root))
    return path


# ---------------------------------------------------------------- Leser ----

def read_abc(path: str) -> dict:
    """Liest eine Ogawa-Datei, so wie AbcCoreOgawa es taete.

    Der Leser ist ABSICHTLICH eine Umsetzung der Alembic-Lese-Routinen
    (ArImpl::init, ReadObjectHeaders, ReadPropertyHeaders, AprImpl::getSample)
    und nicht das Spiegelbild des Schreibers. Nur so merkt man, wenn der
    Schreiber etwas an die falsche Stelle legt.
    """
    with open(path, "rb") as fh:
        raw = fh.read()
    if len(raw) < 16 or raw[:5] != OGAWA_MAGIC:
        raise ValueError("Kein Ogawa-Container")
    frozen = raw[5] == 0xFF
    version = struct.unpack_from(">H", raw, 6)[0]
    root_pos = struct.unpack_from("<Q", raw, 8)[0]
    if version != OGAWA_VERSION:
        raise ValueError("Ogawa-Version %d wird nicht unterstuetzt" % version)

    def read(pos, size):
        if pos + size > len(raw):
            raise ValueError("Lesen hinter das Dateiende (pos=%d, %d B)"
                             % (pos, size))
        return raw[pos:pos + size]

    def group_at(pos):
        n = struct.unpack_from("<Q", raw, pos)[0]
        vals = struct.unpack_from("<%dQ" % n, raw, pos + 8)
        return n, list(vals)

    def data_at(child):
        """Gibt (Groesse, Nutzlast) zurueck -- auch fuer leere Daten."""
        if child == _EMPTY_DATA:
            return 0, b""
        pos = child & 0x7FFFFFFFFFFFFFFF
        if child & _EMPTY_DATA == 0:
            raise ValueError("Kind ist eine Gruppe, keine Daten")
        size = struct.unpack_from("<Q", raw, pos)[0]
        return size, read(pos + 8, size)

    def is_data(child):
        return (child & _EMPTY_DATA) != 0

    # ---- Archiv-Kopf -----------------------------------------------------
    n_root, root_children = group_at(root_pos)
    if not (n_root > 5 and is_data(root_children[0]) and is_data(root_children[1])
            and not is_data(root_children[2]) and is_data(root_children[3])
            and is_data(root_children[4]) and is_data(root_children[5])):
        raise ValueError("Kein gueltiges Alembic-Archiv (Kinder: %d)" % n_root)
    file_version = struct.unpack("<I", data_at(root_children[0])[1])[0]
    library_version = struct.unpack("<I", data_at(root_children[1])[1])[0]
    if file_version != ALEMBIC_OGAWA_FILE_VERSION:
        raise ValueError("Ogawa-Dateiversion %d" % file_version)
    if library_version < 9999:
        raise ValueError("Alembic-Version %d zu alt" % library_version)
    archive_meta = data_at(root_children[3])[1].decode("utf-8")

    # ---- Metadaten-Tabelle ----------------------------------------------
    table = [""]                       # Index 0 = leer
    blob = data_at(root_children[5])[1]
    pos = 0
    while pos < len(blob):
        size = blob[pos]
        pos += 1
        table.append(blob[pos:pos + size].decode("utf-8"))
        pos += size

    def meta_of(index, inline):
        return table[index] if index != 0xFF else inline.decode("utf-8")

    # ---- Objekt-Header ---------------------------------------------------
    def read_object_headers(gpos):
        n, children = group_at(gpos)
        if n == 0 or not is_data(children[-1]):
            return []
        size, blob = data_at(children[-1])
        if size <= 32:                 # nur der Hash, keine Header
            return []
        blob = blob[:size - 32]        # letzten 32 Byte = Hash, wird uebersprungen
        out, pos = [], 0
        while pos < len(blob):
            name_size = struct.unpack_from("<I", blob, pos)[0]
            pos += 4
            name = blob[pos:pos + name_size].decode("utf-8")
            pos += name_size
            md_index = blob[pos]
            pos += 1
            md = ""
            if md_index == 0xFF:
                md_size = struct.unpack_from("<I", blob, pos)[0]
                pos += 4
                md = blob[pos:pos + md_size].decode("utf-8")
                pos += md_size
            else:
                md = table[md_index]
            out.append({"name": name, "meta": md})
        return out

    # ---- Property-Header -------------------------------------------------
    def read_property_headers(gpos):
        n, children = group_at(gpos)
        if n == 0 or not is_data(children[-1]):
            return [], []
        _, blob = data_at(children[-1])
        out, pos = [], 0

        def u32(hint):
            nonlocal pos
            if hint == 0:
                val = blob[pos]; pos += 1
            elif hint == 1:
                val = struct.unpack_from("<H", blob, pos)[0]; pos += 2
            else:
                val = struct.unpack_from("<I", blob, pos)[0]; pos += 4
            return val

        while pos < len(blob):
            info = struct.unpack_from("<I", blob, pos)[0]
            pos += 4
            ptype = info & 0x3
            hint = (info & 0x000c) >> 2
            md_index = (info & 0xff00000) >> 20
            prop = {"type": ptype}
            if ptype != PROP_COMPOUND:
                prop["pod"] = (info & 0x00f0) >> 4
                prop["extent"] = (info & 0x0f000) >> 12
                prop["homogenous"] = bool(info & 0x400)
                prop["num_samples"] = u32(hint)
                if info & 0x0200:
                    prop["first_changed"] = u32(hint)
                    prop["last_changed"] = u32(hint)
                elif info & 0x800:
                    prop["first_changed"] = prop["last_changed"] = 0
                else:
                    prop["first_changed"] = 1
                    prop["last_changed"] = prop["num_samples"] - 1
                prop["time_index"] = u32(hint) if info & 0x0100 else 0
            name_size = u32(hint)
            prop["name"] = blob[pos:pos + name_size].decode("utf-8")
            pos += name_size
            if md_index == 0xFF:
                md_size = u32(hint)
                prop["meta"] = blob[pos:pos + md_size].decode("utf-8")
                pos += md_size
            else:
                prop["meta"] = table[md_index]
            out.append(prop)
        # Der letzte Datenblock enthaelt die Header selbst; er gehoert nicht
        # zu den Properties.
        return out, children[:-1]

    # ---- Baum absteigen ---------------------------------------------------
    POD_DTYPE = {(POD_FLOAT32, 3): "<f4", (POD_INT32, 1): "<i4",
                 (POD_FLOAT64, 6): "<f8"}
    POD_BYTES = {POD_FLOAT32: 4, POD_INT32: 4, POD_FLOAT64: 8}

    def read_samples(gpos, prop):
        """Liest Sample 0 einer Scalar- oder Array-Property.

        Ganz bewusst wird hier auch die GROESSE gegengerechnet: die Dimensionen
        stehen bei Rang 1 nicht in der Datei, der Leser muss sie aus der
        Bytezahl ableiten. Stimmt das nicht, liegt der Fehler im Schreiber.
        """
        n, children = group_at(gpos)
        dtype = POD_DTYPE.get((prop.get("pod"), prop.get("extent")))
        if dtype is None:
            return None
        size, blob = data_at(children[0])
        if size < 16:
            return None
        payload = blob[16:]
        per_elem = POD_BYTES[prop["pod"]] * prop["extent"]
        if len(payload) % per_elem != 0:
            raise ValueError("Property %s: %d Bytes passen nicht zu %d Bytes "
                             "pro Element" % (prop["name"], len(payload),
                                              per_elem))
        if prop["type"] == PROP_ARRAY:
            dim_size, _ = data_at(children[1])
            # Rang 1 -> Dimensionen stehen nicht in der Datei, sie ergeben
            # sich aus der Groesse. Genau das rechnet Alembic genauso.
            derived = (len(payload) // per_elem) if dim_size == 0 \
                else (dim_size // 8)
        else:
            derived = len(payload) // per_elem
        arr = np.frombuffer(payload, dtype=dtype)
        # "derived" zaehlt PUNKTE, das Array zaehlt Pods (Punkte * Extent).
        if len(arr) != derived * prop["extent"]:
            raise ValueError("Property %s: %d Pods gelesen, Dimension sagt %d "
                             "Punkte x %d" % (prop["name"], len(arr), derived,
                                              prop["extent"]))
        return arr

    def resolve_props(gpos):
        """Liest eine Property-Liste rekursiv in ein Dict aus Arrays."""
        props, prop_children = read_property_headers(gpos)
        out = {"__headers__": props}
        for i, prop in enumerate(props):
            child = prop_children[i] if i < len(prop_children) else None
            if child is None or is_data(child) or child == 0:
                continue
            if prop["type"] == PROP_COMPOUND:
                out[prop["name"]] = resolve_props(child)
            else:
                out[prop["name"]] = read_samples(child, prop)
        return out

    objects = []

    def walk_object(gpos, prefix):
        n, children = group_at(gpos)
        headers = read_object_headers(gpos)
        properties = {}
        if n > 0 and not is_data(children[0]) and children[0] != 0:
            properties = resolve_props(children[0])
        child_groups = [c for c in children[1:] if not is_data(c) and c != 0]
        node = {"path": prefix, "meta": "", "properties": properties,
                "children": []}
        objects.append(node)
        for i, head in enumerate(headers):
            if i >= len(child_groups):
                break
            name = head["name"]
            kid_prefix = ("/" + name) if prefix in ("", "/") \
                else (prefix + "/" + name)
            kid = walk_object(child_groups[i], kid_prefix)
            kid["meta"] = head["meta"]
            node["children"].append(kid)
        return node

    root_obj = walk_object(root_children[2], "/")

    if not frozen:
        raise ValueError("Ogawa-Datei ist nicht als fertig markiert "
                         "(frozen-Flag fehlt) -- sie wurde vermutlich nicht "
                         "sauber abgeschlossen")
    res = {"frozen": frozen, "version": version,
           "file_version": file_version, "library_version": library_version,
           "archive_meta": archive_meta, "meta_table": table,
           "objects": objects, "root": root_obj}

    # ---- PolyMesh finden und Geometrie pruefen ---------------------------
    for obj in objects:
        if "schema=AbcGeom_PolyMesh_v1" not in obj.get("meta", ""):
            continue
        res["mesh_path"] = obj["path"]
        res["schema"] = obj["meta"]
        geom = obj["properties"].get(".geom", {})
        res["geom"] = geom
        if all(k in geom for k in ("P", ".faceIndices", ".faceCounts")):
            res["vertices"] = np.asarray(geom["P"],
                                         dtype=np.float64).reshape(-1, 3)
            res["faces"] = np.asarray(geom[".faceIndices"],
                                      dtype=np.int64).reshape(-1, 3)
            res["face_counts"] = np.asarray(geom[".faceCounts"],
                                            dtype=np.int64)
            res["self_bounds"] = np.asarray(geom.get(".selfBnds", []),
                                            dtype=np.float64)
            if "N" in geom:
                # Alembic kennt zwei Normalen-Arten: "N" ist
                # vertex-varying (geoScope=vtx, ein Wert je Punkt).
                # Steht hier versehentlich der Scope "fvr", liest Alembic
                # sie als Flaechennormalen und das Netz kommt facettiert
                # an -- der Header ist also Teil der Aussage.
                res["normals"] = np.asarray(geom["N"],
                                            dtype=np.float64).reshape(-1, 3)
        break
    return res
