// Prueft eine .abc-Datei mit der ECHTEN Alembic-Bibliothek.
// Bauen: g++ -std=c++14 -I/tmp/deps/include -o /tmp/abc_check abc_check.cpp \
//            -L/tmp/deps/lib -lAlembic -lImath-3_2 -Wl,-rpath,/tmp/deps/lib
#include <Alembic/AbcGeom/All.h>
#include <Alembic/AbcCoreOgawa/All.h>
#include <iostream>
#include <iomanip>

using namespace Alembic::AbcGeom;
using namespace Alembic::Abc;

static void walk(IObject obj, int depth)
{
    std::string pad(depth * 2, ' ');
    const AbcA::MetaData &md = obj.getMetaData();
    std::cout << pad << obj.getFullName()
              << "  schema='" << md.get("schema")
              << "' base='" << md.get("schemaBaseType") << "'\n";

    if (IPolyMesh::matches(md))
    {
        IPolyMesh mesh(obj, kWrapExisting);
        IPolyMeshSchema &s = mesh.getSchema();
        std::cout << pad << "  PolyMesh, " << s.getNumSamples() << " Sample(s)\n";

        IPolyMeshSchema::Sample samp;
        s.get(samp);
        size_t np = samp.getPositions()->size();
        size_t ni = samp.getFaceIndices()->size();
        size_t nc = samp.getFaceCounts()->size();
        std::cout << pad << "  P=" << np << " faceIndices=" << ni
                  << " faceCounts=" << nc << "\n";

        Abc::Box3d b = samp.getSelfBounds();
        std::cout << std::fixed << std::setprecision(4)
                  << pad << "  selfBnds min (" << b.min[0] << ", " << b.min[1]
                  << ", " << b.min[2] << ")  max (" << b.max[0] << ", "
                  << b.max[1] << ", " << b.max[2] << ")\n";

        // Erste drei Punkte als Fingerabdruck
        const V3f *p = samp.getPositions()->get();
        for (size_t i = 0; i < 3 && i < np; ++i)
            std::cout << pad << "  P[" << i << "] = " << p[i][0] << ", "
                      << p[i][1] << ", " << p[i][2] << "\n";
    }

    for (size_t i = 0; i < obj.getNumChildren(); ++i)
        walk(obj.getChild(i), depth + 1);
}

int main(int argc, char **argv)
{
    if (argc < 2) { std::cerr << "Aufruf: abc_check DATEI.abc\n"; return 2; }

    IArchive archive(Alembic::AbcCoreOgawa::ReadArchive(), argv[1]);
    if (!archive.valid())
    {
        std::cerr << "UNGUELTIG: " << argv[1] << "\n";
        return 1;
    }
    std::cout << "Archiv gueltig. Alembic-Version der Datei: "
              << archive.getArchiveVersion() << "\n";
    walk(archive.getTop(), 0);
    std::cout << "OK\n";
    return 0;
}
