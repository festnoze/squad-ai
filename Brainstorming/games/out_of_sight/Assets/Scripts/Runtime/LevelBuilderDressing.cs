using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// DRESSING (2026-11-24, docs/next/progress/DRESSING.md): the room dressing of a level, visual only.
    /// <list type="bullet">
    /// <item>Decor items (<see cref="LevelDef.Decor"/>): each baked mesh of <see cref="DressingLibrary"/> stands on its host's top
    /// (host frame position and yaw from the data, the top at the host's height), drawn with the wall material and merged into
    /// the floor renderer (Floor layer, no shadow): no collider, no occluder, no NavMesh source, no material and no draw call of
    /// its own. A throw drapes over the drawn sofa's real backrest (<see cref="SofaBackrest"/>: its side, top and
    /// thickness), flat on its top, centred on it, its depth fitted to it (<see cref="DecorKinds.ThrowDepthScale"/>).</item>
    /// <item>Furniture looks (<see cref="PropDef.Dress"/>): the walnut coffee table or media console replaces the prop's
    /// procedural visual, box fitted to the prop (a TV unit's cabinet part, the TV then standing on its top centre, scaled into
    /// the rest of the box as the procedural screen was); the prop keeps exactly its colliders and occluder flag
    /// (FurnitureKit.Build with no visual). The looks of a level draw as one renderer of the wall material on the prop's layer,
    /// shadowed, which replaces the procedural renderers they stand for.</item>
    /// <item>Without the wall material or the library (textures off, dressing off) nothing is dressed: every prop keeps its
    /// procedural visual and no decor is built.</item>
    /// </list>
    /// </summary>
    public static partial class LevelBuilder
    {
        private const string DressingScope = "Dressing";

        /// <summary>The name of the renderer the furniture looks combine into.</summary>
        public const string DressingName = "Dressing";

        /// <summary>The prefix of a decor item's own renderer when the renderers are not combined.</summary>
        public const string DecorPrefix = "Decor ";

        /// <summary>
        /// Draws the furniture look of <paramref name="prop"/> under <paramref name="host"/>; false (nothing drawn: the caller
        /// builds the procedural visual) when the prop names none or it cannot be drawn.
        /// </summary>
        private static bool DressProp(LevelInstance level, PropDef prop, Transform host, Batch batch)
        {
            if (string.IsNullOrEmpty(prop.Dress))
            {
                return false;
            }
            Material material = WallArray.Material;
            DressingLibrary.Entry look = DressingLibrary.Lookup(prop.Dress);
            if (material == null || look == null)
            {
                return false;
            }
            if (DecorKinds.IsKitchenLook(prop.Dress))
            {
                return DressKitchen(level, prop, host, batch, material);
            }
            Vector3 s = prop.Size;
            float body = s.y;
            DressingLibrary.Entry tv = null;
            if (prop.Dress == DecorKinds.WalnutMediaConsole && prop.Kind == PropKinds.TvUnit)
            {
                body = TvCabinetHeight(s.y);
                if (s.y - body > 1e-3f)
                {
                    tv = DressingLibrary.Lookup(DecorKinds.FlatScreenTv);
                }
            }
            // The looks face +z in their GLB (the console's doors): the prop's front is its local -z, so they turn by 180.
            Quaternion turn = Quaternion.Euler(0f, 180f, 0f);
            Vector3 lookScale = Fit(look, new Vector3(s.x, body, s.z));
            AddDressing(level, batch, host, prop, look, new Vector3(0f, 0f, 0f), turn, lookScale, material, true, s.y);
            if (tv != null)
            {
                Vector3 size = tv.Size;
                float k = Mathf.Min((s.y - body) / Mathf.Max(size.y, 1e-3f), s.x * 0.9f / Mathf.Max(size.x, 1e-3f), s.z / Mathf.Max(size.z, 1e-3f));
                AddDressing(level, batch, host, prop, tv, new Vector3(0f, body, 0f), turn, Vector3.one * k, material, true, s.y);
            }
            else if (DecorKinds.CarriesTopTv(prop.Kind, prop.Dress) && (tv = DressingLibrary.Lookup(DecorKinds.FlatScreenTv)) != null)
            {
                // COHERENCE: a low counter or cabinet dressed as the media console carries the TV on its top (visual only, above
                // the prop's colliders), against its back, screen to its front: a TV stand reads as one, never as a bare cabinet.
                // TVBIG: twice the delivered TV, its foot made shallower when the console is (see DecorKinds.TopTvDepthScale).
                Rect footprint = DecorKinds.TopTvFootprint(s);
                float k = DecorKinds.TopTvScale(s);
                AddDressing(level, batch, host, prop, tv, new Vector3(0f, s.y, footprint.center.y), turn,
                    new Vector3(k, k, DecorKinds.TopTvDepthScale(s)), material, true, s.y);
            }
            return true;
        }

        /// <summary>
        /// KITCHEN (docs/next/progress/KITCHEN.md): lays the modules of a kitchen look (<see cref="DecorKinds.KitchenRun"/>)
        /// side by side along the prop's longer horizontal side, scaled together to its exact length, its height (one y scale
        /// for the whole run, from its tallest module, so every worktop stays level) and its depth. The fronts face the prop's
        /// local -z for a run along x, local -x for a run along z (turn such a prop by 180 degrees to face +x: its collider box
        /// is the same). False (nothing drawn) when a module is not baked.
        /// </summary>
        private static bool DressKitchen(LevelInstance level, PropDef prop, Transform host, Batch batch, Material material)
        {
            Vector3 s = prop.Size;
            bool alongZ = s.z > s.x + 1e-3f;
            float length = alongZ ? s.z : s.x;
            float depth = alongZ ? s.x : s.z;
            var modules = new List<DressingLibrary.Entry>();
            float native = 0f;
            float tallest = 0f;
            foreach (string id in DecorKinds.KitchenRun(prop.Dress, length))
            {
                DressingLibrary.Entry e = DressingLibrary.Lookup(id);
                if (e == null)
                {
                    return false;
                }
                modules.Add(e);
                native += e.Size.x;
                tallest = Mathf.Max(tallest, e.Size.y);
            }
            if (modules.Count == 0)
            {
                return false;
            }
            float kx = length / Mathf.Max(native, 1e-4f);
            float ky = s.y / Mathf.Max(tallest, 1e-4f);
            // The modules face +z in their GLB: a half turn faces local -z, a quarter turn back faces local -x (width along z).
            Quaternion turn = Quaternion.Euler(0f, alongZ ? -90f : 180f, 0f);
            float at = -length * 0.5f;
            foreach (DressingLibrary.Entry e in modules)
            {
                float width = e.Size.x * kx;
                float centre = at + width * 0.5f;
                at += width;
                var scale = new Vector3(kx, ky, depth / Mathf.Max(e.Size.z, 1e-4f));
                Vector3 position = alongZ ? new Vector3(0f, 0f, centre) : new Vector3(centre, 0f, 0f);
                AddDressing(level, batch, host, prop, e, position, turn, scale, material, true, s.y);
            }
            return true;
        }

        /// <summary>The cabinet height of a TV unit of height <paramref name="height"/>, as FurnitureKit.TvUnit builds it (no TV under 0.25 m left).</summary>
        public static float TvCabinetHeight(float height)
        {
            float cabinet = Mathf.Clamp(height * 0.45f, 0.25f, 0.55f);
            return height - cabinet >= 0.25f ? cabinet : height;
        }

        /// <summary>The per axis scale that fits the entry's bounds into <paramref name="box"/> (its yaw a half turn: x and z keep their axes).</summary>
        private static Vector3 Fit(DressingLibrary.Entry entry, Vector3 box)
        {
            Vector3 n = entry.Size;
            return new Vector3(box.x / Mathf.Max(n.x, 1e-4f), box.y / Mathf.Max(n.y, 1e-4f), box.z / Mathf.Max(n.z, 1e-4f));
        }

        /// <summary>Builds every decor item of <paramref name="def"/> on its host (<paramref name="hosts"/>: the props' groups by name).</summary>
        private static void BuildDecor(LevelInstance level, LevelDef def, Batch batch, Dictionary<string, Transform> hosts)
        {
            if (def.Decor == null || def.Decor.Count == 0)
            {
                return;
            }
            Material material = WallArray.Material;
            if (material == null || DressingLibrary.Disabled || DressingLibrary.Load() == null)
            {
                return;
            }
            foreach (DecorDef d in def.Decor)
            {
                if (d == null)
                {
                    continue;
                }
                if (DecorKinds.IsFloor(d.Host))
                {
                    BuildFloorDecor(level, def, batch, d, material);
                    continue;
                }
                PropDef prop = def.Props.Find(p => p != null && p.Name == d.Host);
                DressingLibrary.Entry entry = DressingLibrary.Lookup(d.Kind);
                if (prop == null || entry == null || !DecorKinds.IsItem(d.Kind) || !hosts.TryGetValue(d.Host, out Transform host))
                {
                    level.DressingProblems.Add($"{d.Kind} on {d.Host}: no such host or decor mesh");
                    continue;
                }
                Vector3 scale = Vector3.one;
                float z = d.Z;
                float yaw = d.Yaw;
                float top = prop.SizeY;
                if (d.Kind == DecorKinds.SofaThrow)
                {
                    // THROWFIX: on the drawn sofa's real backrest (its side, top and thickness), draped flat over its top.
                    SofaBackrest(prop, host, out float centre, out float depth, out top);
                    bool back = centre < 0f;
                    z = centre + (back ? -d.Z : d.Z);
                    // Yaw 0 hangs the long side behind the backrest: a backrest on -z turns the throw by a half turn.
                    yaw += back ? 180f : 0f;
                    scale.z = DecorKinds.ThrowDepthScale(depth);
                    entry = DrapedThrow(entry, depth, scale.z);
                }
                var position = new Vector3(d.X, top, z);
                Quaternion rotation = Quaternion.Euler(0f, yaw, 0f);
                // Combined, it joins the floor renderer; not combined (LevelBuilder.CombineRenderers off), its own renderer on the host.
                batch.Add(host, DecorPrefix + d.Kind, entry.mesh, position, rotation, scale, material, Layers.Floor, Surface.Plain,
                    ShadowCastingMode.Off, FloorScope, FloorName);
                level.Dressing.Add(Placement(level, host, prop, entry, position, rotation, scale, false, top));
            }
        }

        /// <summary>
        /// THROWFIX (docs/next/progress/COHERENCE.md): the backrest of the sofa <paramref name="prop"/> as it is drawn under
        /// <paramref name="host"/>, in the host's frame: its centre line z (its side: + or -), its thickness and its top. A
        /// model sofa: its measured backrest (ModelCatalog.Entry.backrestTop and backrestSpan) through the model's box fit; the
        /// procedural sofa (or a model with no measured backrest): FurnitureKit.Sofa's own (DecorKinds.SofaBackDepth, on +z).
        /// </summary>
        public static void SofaBackrest(PropDef prop, Transform host, out float centre, out float depth, out float top)
        {
            Vector3 s = prop.Size;
            ModelCatalog.Entry m = ModelCatalog.Lookup(prop.Model);
            if (m != null && !m.rigged && m.HasBackrest && host != null && ModelKit.ModelRootsUnder(host).Count > 0)
            {
                float yaw = ModelMath.SnapYaw(m.yawOffset);
                Vector3 scale = ModelMath.BoxScale(m.nativeSize, s, yaw);
                Vector3 position = ModelMath.FitPosition(m.boundsCenter, m.nativeSize, scale, yaw);
                Vector3 a = ModelMath.ApplyFit(new Vector3(m.boundsCenter.x, m.backrestTop, m.backrestSpan.x), position, scale, yaw);
                Vector3 b = ModelMath.ApplyFit(new Vector3(m.boundsCenter.x, m.backrestTop, m.backrestSpan.y), position, scale, yaw);
                // A quarter turned model would run its backrest along x: not a sofa this handles, the procedural one stands in.
                if (Mathf.Abs(a.z - b.z) > 0.02f)
                {
                    centre = (a.z + b.z) * 0.5f;
                    depth = Mathf.Abs(a.z - b.z);
                    top = a.y;
                    return;
                }
            }
            depth = DecorKinds.SofaBackDepth(s);
            centre = s.z * 0.5f - depth * 0.5f;
            top = s.y;
        }

        /// <summary>The throw draped per mesh and backrest thickness (mm): every sofa of one thickness shares one mesh.</summary>
        private static readonly Dictionary<(int, int), DressingLibrary.Entry> Draped = new Dictionary<(int, int), DressingLibrary.Entry>();

        /// <summary>The depth bin of the throw's crest profile (native metres).</summary>
        private const float DrapeBin = 0.002f;

        /// <summary>
        /// THROWFIX: the delivered throw is folded over a rounded crest (its top a narrow cap, 7 cm deep at its sides' gap), so a
        /// square backrest's top corners stood above it and swallowed it: only the hanging sides and fringes showed, low. This
        /// lays it over a square backrest <paramref name="backDepth"/> thick (the throw at <paramref name="depthScale"/>): the cap
        /// between the backrest's two faces lies flat <see cref="DecorKinds.ThrowClearance"/> above the top, and each hanging
        /// side is lifted by the cap's drop at its face, so it hangs from the backrest's edge, outside it, unchanged. The entry's
        /// own mesh when it cannot be read.
        /// </summary>
        private static DressingLibrary.Entry DrapedThrow(DressingLibrary.Entry entry, float backDepth, float depthScale)
        {
            if (entry.mesh == null || !entry.mesh.isReadable)
            {
                return entry;
            }
            var key = (entry.mesh.GetInstanceID(), Mathf.RoundToInt(backDepth * 1000f));
            if (Draped.TryGetValue(key, out DressingLibrary.Entry cached) && cached.mesh != null)
            {
                return cached;
            }
            Vector3[] vertices = entry.mesh.vertices;
            Vector3[] normals = entry.mesh.normals;
            // The top envelope of the sheet across its depth: its highest vertex in each bin.
            var envelope = new SortedDictionary<int, float>();
            foreach (Vector3 v in vertices)
            {
                int bin = Mathf.RoundToInt(v.z / DrapeBin);
                if (!envelope.TryGetValue(bin, out float y) || v.y > y)
                {
                    envelope[bin] = v.y;
                }
            }
            var zs = new List<float>();
            var ys = new List<float>();
            foreach (KeyValuePair<int, float> kv in envelope)
            {
                zs.Add(kv.Key * DrapeBin);
                ys.Add(kv.Value);
            }
            float half = backDepth * 0.5f / Mathf.Max(depthScale, 1e-4f);
            // Each side is lifted by the height of its first row beyond the face, not the cap's height at the face: the cap
            // then stays flat to that row, over the backrest's edge, and never dips into its corner.
            float dropBack = RowBeyond(zs, ys, -half, false);
            float dropFront = RowBeyond(zs, ys, half, true);
            float lift = DecorKinds.ThrowClearance;
            for (int i = 0; i < vertices.Length; i++)
            {
                Vector3 v = vertices[i];
                if (v.z < -half)
                {
                    v.y += lift - dropBack;
                }
                else if (v.z > half)
                {
                    v.y += lift - dropFront;
                }
                else if (v.y < (v.z < 0f ? dropBack : dropFront) - 1e-4f)
                {
                    // A fold of a hanging side reaching back under the top (below the side's first row): it stays on its
                    // side, lifted with it and pushed out to the backrest's face, so its triangles never tear up to the top.
                    bool front = v.z >= 0f;
                    v.y += lift - (front ? dropFront : dropBack);
                    v.z = front ? half + DrapeBin : -half - DrapeBin;
                }
                else
                {
                    v.y = lift;
                    if (i < normals.Length)
                    {
                        normals[i] = new Vector3(0f, normals[i].y < 0f ? -1f : 1f, 0f);
                    }
                }
                vertices[i] = v;
            }
            Mesh mesh = Object.Instantiate(entry.mesh);
            mesh.name = entry.mesh.name + " draped " + key.Item2;
            mesh.vertices = vertices;
            if (normals.Length == vertices.Length)
            {
                mesh.normals = normals;
            }
            mesh.RecalculateBounds();
            var draped = new DressingLibrary.Entry
            {
                id = entry.id, mesh = mesh, boundsMin = mesh.bounds.min, boundsMax = mesh.bounds.max, triangles = entry.triangles,
            };
            Draped[key] = draped;
            return draped;
        }

        /// <summary>
        /// The envelope's height at its first bin beyond <paramref name="face"/> (toward +z when <paramref name="front"/>, else
        /// toward -z); 0 when the sheet has none there.
        /// </summary>
        private static float RowBeyond(List<float> zs, List<float> ys, float face, bool front)
        {
            if (front)
            {
                for (int i = 0; i < zs.Count; i++)
                {
                    if (zs[i] > face)
                    {
                        return ys[i];
                    }
                }
            }
            else
            {
                for (int i = zs.Count - 1; i >= 0; i--)
                {
                    if (zs[i] < face)
                    {
                        return ys[i];
                    }
                }
            }
            return 0f;
        }

        /// <summary>
        /// BEDROOM (docs/next/progress/BEDROOM.md): a floor item (host "floor") at its absolute X, Z and Yaw, on the floor under
        /// it (a split level's floor height, a rug's top when it lies on a rug), merged into the floor renderer like every decor
        /// item: no collider, no occluder, no NavMesh source.
        /// </summary>
        private static void BuildFloorDecor(LevelInstance level, LevelDef def, Batch batch, DecorDef d, Material material)
        {
            DressingLibrary.Entry entry = DressingLibrary.Lookup(d.Kind);
            if (entry == null || !DecorKinds.IsItem(d.Kind) || !DecorKinds.AllowsFloor(d.Kind))
            {
                level.DressingProblems.Add($"{d.Kind} on the floor: no such floor decor mesh");
                return;
            }
            Transform root = level.Root.transform;
            Vector3 position = def.Floor.OnFloor(new Vector3(d.X, 0f, d.Z));
            if (def.Rugs.Exists(r => r != null && r.Contains(position)))
            {
                position.y += RugHeight;
            }
            Quaternion rotation = Quaternion.Euler(0f, d.Yaw, 0f);
            batch.Add(root, DecorPrefix + d.Kind, entry.mesh, position, rotation, Vector3.one, material, Layers.Floor, Surface.Plain,
                ShadowCastingMode.Off, FloorScope, FloorName);
            level.Dressing.Add(Placement(level, root, new PropDef { Name = DecorKinds.FloorHost }, entry, position, rotation, Vector3.one,
                false, position.y));
        }

        private static void AddDressing(LevelInstance level, Batch batch, Transform host, PropDef prop, DressingLibrary.Entry entry, Vector3 position,
            Quaternion rotation, Vector3 scale, Material material, bool look, float top)
        {
            // The mesh's root is on its contact point, its bounds may not be centred: the box fit centres them on the prop.
            Vector3 centre = (entry.boundsMin + entry.boundsMax) * 0.5f;
            position -= rotation * Vector3.Scale(new Vector3(centre.x, entry.boundsMin.y, centre.z), scale);
            // On the prop's layer, as the procedural visual it replaces (no collider: the layer only sorts the renderer).
            batch.Add(host, DressingName + " " + entry.id, entry.mesh, position, rotation, scale, material, host.gameObject.layer, Surface.Plain,
                ShadowCastingMode.On, DressingScope, DressingName);
            level.Dressing.Add(Placement(level, host, prop, entry, position, rotation, scale, look, top));
        }

        private static DressingPlacement Placement(LevelInstance level, Transform host, PropDef prop, DressingLibrary.Entry entry, Vector3 position,
            Quaternion rotation, Vector3 scale, bool look, float top)
        {
            Matrix4x4 toRoot = level.Root.transform.worldToLocalMatrix * host.localToWorldMatrix * Matrix4x4.TRS(position, rotation, scale);
            var bounds = new Bounds(toRoot.MultiplyPoint3x4(entry.boundsMin), Vector3.zero);
            for (int i = 1; i < 8; i++)
            {
                var corner = new Vector3((i & 1) != 0 ? entry.boundsMax.x : entry.boundsMin.x, (i & 2) != 0 ? entry.boundsMax.y : entry.boundsMin.y,
                    (i & 4) != 0 ? entry.boundsMax.z : entry.boundsMin.z);
                bounds.Encapsulate(toRoot.MultiplyPoint3x4(corner));
            }
            float hostTop = (level.Root.transform.worldToLocalMatrix * host.localToWorldMatrix).MultiplyPoint3x4(new Vector3(0f, top, 0f)).y;
            return new DressingPlacement { Id = entry.id, Host = prop.Name, Look = look, Bounds = bounds, HostTop = hostTop };
        }

        /// <summary>
        /// Records every decor item standing in one of the lamps RoomLights put on a prop top (a table, desk or bedside lamp):
        /// the data must leave that spot free. The audit fails on any.
        /// </summary>
        private static void CheckDecorLamps(LevelInstance level, RoomLights lights)
        {
            if (lights == null)
            {
                return;
            }
            foreach (DressingPlacement p in level.Dressing)
            {
                // BEDROOM: a bedside lamp item is the lamp itself: RoomLights puts its glow in the item's bulb (RoomLights.Bedside).
                if (p.Look || p.Id == DecorKinds.BedsideLamp)
                {
                    continue;
                }
                foreach (Bounds lamp in lights.Lamps)
                {
                    if (lamp.Intersects(p.Bounds))
                    {
                        level.DressingProblems.Add($"{p.Id} on {p.Host} stands in a lamp at ({lamp.center.x:0.00}, {lamp.center.z:0.00})");
                    }
                }
            }
        }
    }
}
