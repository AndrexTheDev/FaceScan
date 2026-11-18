package com.andrexthedev.facescan.scan

/**
 * Reine Strukturdiagnose eines Dreiecksnetzes: Randkanten, nicht-mannigfaltige
 * Kanten und Zusammenhangskomponenten.
 *
 * Was das ist: eine Aussage über die Verdrahtung der exportierten Flächen.
 * Was das NICHT ist: ein Qualitäts-, Genauigkeits- oder Vollständigkeitsurteil.
 * Ein Netz mit vielen Randkanten kann korrekt sein (ein offenes Teilnetz hat
 * immer einen Rand); ein geschlossenes Netz kann trotzdem falsch geformt sein.
 *
 * Gezählt werden Kanten über ihre sortierten Endpunkte, damit die Reihenfolge
 * der Dreiecksindizes keine Rolle spielt. Nicht referenzierte Punkte zählen
 * nicht als eigene Komponente.
 */
object PartialMeshTopology {
    data class Report(
        val vertexCount: Int,
        val triangleCount: Int,
        /** Kanten mit genau einem angrenzenden Dreieck. */
        val boundaryEdges: Int,
        /** Kanten mit drei oder mehr angrenzenden Dreiecken (im Teilnetz ein Fehler). */
        val nonManifoldEdges: Int,
        /** Zusammenhangskomponenten über Dreieckskanten; 0 bei leerem Netz. */
        val components: Int,
        /** Größte Komponente in Dreiecken; 0 bei leerem Netz. */
        val largestComponentTriangles: Int
    )

    fun inspect(vertexCount: Int, triangles: IntArray): Report {
        require(vertexCount >= 0)
        require(triangles.size % 3 == 0)
        require(triangles.all { it in 0 until vertexCount })
        val triangleCount = triangles.size / 3
        if (triangleCount == 0) return Report(vertexCount, 0, 0, 0, 0, 0)

        // Kante -> Anzahl angrenzender Dreiecke.
        val edgeUse = HashMap<Long, Int>(triangleCount * 3 / 2)
        fun key(a: Int, b: Int): Long {
            val low = minOf(a, b).toLong()
            val high = maxOf(a, b).toLong()
            return (low shl 32) or high
        }
        // Union-Find über die Punkte, die tatsächlich in Flächen vorkommen.
        val parent = IntArray(vertexCount) { it }
        fun find(x: Int): Int {
            var root = x
            while (parent[root] != root) root = parent[root]
            var node = x
            while (parent[node] != root) { val next = parent[node]; parent[node] = root; node = next }
            return root
        }
        fun union(a: Int, b: Int) {
            val ra = find(a); val rb = find(b)
            if (ra != rb) parent[if (ra < rb) rb else ra] = if (ra < rb) ra else rb
        }
        val referenced = BooleanArray(vertexCount)
        for (t in 0 until triangleCount) {
            val a = triangles[3 * t]; val b = triangles[3 * t + 1]; val c = triangles[3 * t + 2]
            referenced[a] = true; referenced[b] = true; referenced[c] = true
            union(a, b); union(b, c)
            for ((p, q) in listOf(a to b, b to c, c to a)) {
                val k = key(p, q)
                edgeUse[k] = (edgeUse[k] ?: 0) + 1
            }
        }
        var boundary = 0
        var nonManifold = 0
        for (count in edgeUse.values) {
            if (count == 1) boundary++
            else if (count > 2) nonManifold++
        }
        // Dreiecke je Wurzel zählen.
        val perRoot = HashMap<Int, Int>()
        for (t in 0 until triangleCount) perRoot[find(triangles[3 * t])] = (perRoot[find(triangles[3 * t])] ?: 0) + 1
        return Report(
            vertexCount = vertexCount,
            triangleCount = triangleCount,
            boundaryEdges = boundary,
            nonManifoldEdges = nonManifold,
            components = perRoot.size,
            largestComponentTriangles = perRoot.values.maxOrNull() ?: 0
        )
    }

    fun inspect(mesh: PartialFaceMesh.Mesh): Report = inspect(mesh.vertices.size, mesh.triangles)

    /**
     * Kurzfassung für Dateiköpfe und JSON-Extras. Feste Reihenfolge, damit der
     * Text unabhängig geprüft werden kann.
     */
    fun describe(report: Report): String =
        "vertices=${report.vertexCount} triangles=${report.triangleCount} " +
            "boundaryEdges=${report.boundaryEdges} nonManifoldEdges=${report.nonManifoldEdges} " +
            "components=${report.components} largestComponentTriangles=${report.largestComponentTriangles}"
}
