import io

p = "Assets/Scripts/Runtime/GhostView.cs"
s = io.open(p, encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:80]
    s = s.replace(old, new)


rep("""        private Mesh mesh;
        private MeshRenderer meshRenderer;
        private Mesh ringsMesh;
        private MeshRenderer ringsRenderer;
        private Vector3 builtSize = new Vector3(-1f, -1f, -1f);
""", """        private Mesh mesh;
        private MeshRenderer meshRenderer;
        private Mesh ringsMesh;
        private MeshRenderer ringsRenderer;
        private Vector3 builtSize = new Vector3(-1f, -1f, -1f);

        // M4: the seat ghost (its own object, so Show and Hide never touch it) and the office chair's stop ring.
        private Mesh seatMesh;
        private MeshRenderer seatRenderer;
        private Transform seatTransform;
        private Vector3 seatBuiltSize = new Vector3(-1f, -1f, -1f);
        private Mesh stopMesh;
        private MeshRenderer stopRenderer;
        private Transform stopTransform;
""")

rep("""            ringsMesh = new Mesh { name = "DecoyRings" };
            rings.AddComponent<MeshFilter>().sharedMesh = ringsMesh;
            ringsRenderer = rings.AddComponent<MeshRenderer>();
            Setup(ringsRenderer, material);
        }
""", """            ringsMesh = new Mesh { name = "DecoyRings" };
            rings.AddComponent<MeshFilter>().sharedMesh = ringsMesh;
            ringsRenderer = rings.AddComponent<MeshRenderer>();
            Setup(ringsRenderer, material);

            // M4: built here at boot with the rest, so the object count never changes across levels (step 09).
            // Same material: no new material for the budgets (PRD 7.4).
            var seat = new GameObject("SeatGhost");
            seat.transform.SetParent(transform.parent, false);
            seatTransform = seat.transform;
            seatMesh = new Mesh { name = "SeatGhost" };
            seat.AddComponent<MeshFilter>().sharedMesh = seatMesh;
            seatRenderer = seat.AddComponent<MeshRenderer>();
            Setup(seatRenderer, material);

            var stop = new GameObject("StopRing");
            stop.transform.SetParent(transform.parent, false);
            stopTransform = stop.transform;
            stopMesh = new Mesh { name = "StopRing" };
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var triangles = new List<int>();
            AddRing(Vector3.zero, StopRingRadius, StopRingWidth, vertices, normals, triangles);
            // A short cross in the middle marks the exact point.
            AddBar(new Vector3(StopMarkLength, RingHeight, StopRingWidth * 0.5f), vertices, normals, triangles);
            AddBar(new Vector3(StopRingWidth * 0.5f, RingHeight, StopMarkLength), vertices, normals, triangles);
            stopMesh.SetVertices(vertices);
            stopMesh.SetNormals(normals);
            stopMesh.SetTriangles(triangles, 0);
            stopMesh.RecalculateBounds();
            stop.AddComponent<MeshFilter>().sharedMesh = stopMesh;
            stopRenderer = stop.AddComponent<MeshRenderer>();
            Setup(stopRenderer, material);
        }
""")

rep("""        /// <summary>The chair of FurnitureKit.Chair (seat, four legs, backrest) and the tolerance ring, in one mesh.</summary>
        private void Rebuild(Vector3 size)
        {
            builtSize = size;
            float seatTop""", """        /// <summary>The chair of FurnitureKit.Chair (seat, four legs, backrest) and the tolerance ring, in one mesh.</summary>
        private void Rebuild(Vector3 size)
        {
            builtSize = size;
            BuildGhost(mesh, size, Tuning.DisplacementTolerance);
        }

        /// <summary>A ghost chair of <paramref name="size"/> inside a floor ring of <paramref name="ringRadius"/>, into <paramref name="target"/>.</summary>
        private static void BuildGhost(Mesh target, Vector3 size, float ringRadius)
        {
            float seatTop""")

rep("""            AddRing(Vector3.zero, vertices, normals, triangles);

            mesh.Clear();
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
        }

        /// <summary>A flat band on the floor, centered on DisplacementTolerance (the material is double sided).</summary>
        private static void AddRing(Vector3 center, List<Vector3> vertices, List<Vector3> normals, List<int> triangles)
        {
            int ringStart = vertices.Count;
            float inner = Tuning.DisplacementTolerance - RingWidth * 0.5f;
            float outer = Tuning.DisplacementTolerance + RingWidth * 0.5f;
""", """            AddRing(Vector3.zero, ringRadius, RingWidth, vertices, normals, triangles);

            target.Clear();
            target.SetVertices(vertices);
            target.SetNormals(normals);
            target.SetTriangles(triangles, 0);
            target.RecalculateBounds();
        }

        /// <summary>A flat band on the floor, centered on DisplacementTolerance (the material is double sided).</summary>
        private static void AddRing(Vector3 center, List<Vector3> vertices, List<Vector3> normals, List<int> triangles)
        {
            AddRing(center, Tuning.DisplacementTolerance, RingWidth, vertices, normals, triangles);
        }

        /// <summary>A flat band on the floor of <paramref name="radius"/> and <paramref name="width"/>.</summary>
        private static void AddRing(Vector3 center, float radius, float width, List<Vector3> vertices, List<Vector3> normals, List<int> triangles)
        {
            int ringStart = vertices.Count;
            float inner = radius - width * 0.5f;
            float outer = radius + width * 0.5f;
""")

rep("""        private void OnDestroy()
        {
            DestroyMesh(mesh);
            DestroyMesh(ringsMesh);
        }
""", """        /// <summary>A flat floor quad of half extents <paramref name="half"/> (x and z) at height half.y, centered on the origin.</summary>
        private static void AddBar(Vector3 half, List<Vector3> vertices, List<Vector3> normals, List<int> triangles)
        {
            int a = vertices.Count;
            vertices.Add(new Vector3(-half.x, half.y, -half.z));
            vertices.Add(new Vector3(-half.x, half.y, half.z));
            vertices.Add(new Vector3(half.x, half.y, half.z));
            vertices.Add(new Vector3(half.x, half.y, -half.z));
            for (int i = 0; i < 4; i++)
            {
                normals.Add(Vector3.up);
            }
            triangles.Add(a);
            triangles.Add(a + 1);
            triangles.Add(a + 2);
            triangles.Add(a);
            triangles.Add(a + 2);
            triangles.Add(a + 3);
        }

        private void OnDestroy()
        {
            DestroyMesh(mesh);
            DestroyMesh(ringsMesh);
            DestroyMesh(seatMesh);
            DestroyMesh(stopMesh);
        }
""")

start = s.index("        // ----- M4 (docs/CONTRACT_M4.md amendment 9.3). STUB landed by the integrator")
end = s.index("        public void ShowStopRing(Vector3? point)")
end = s.index("        }\n", end) + len("        }\n")
s = s[:start] + io.open("scratchpad/bodies/ghost_m4.txt", encoding="utf-8").read() + s[end:]
s = s.replace("    \n        // ----- M4", "\n        // ----- M4")
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
