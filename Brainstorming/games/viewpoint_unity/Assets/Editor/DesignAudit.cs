using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEditor;
using UnityEngine;
using Viewpoint;

namespace Viewpoint.Editor
{
    /// <summary>
    /// Level DESIGN audit, port of the original <c>tools/design_audit.gd</c>
    /// (PRD 17.4). Run it from the menu, or headless:
    /// <code>
    /// Unity -batchmode -nographics -projectPath games/viewpoint_unity \
    ///       -executeMethod Viewpoint.Editor.DesignAudit.RunBatch -quit
    /// </code>
    /// <para>
    /// The unit suites answer "is this data well formed"; this tool answers the
    /// other question, the one that actually decides whether a level is any good:
    /// "can a player standing at the spawn, with the tools this level hands him,
    /// reach everything the level asks him to reach, and never lock himself out".
    /// </para>
    /// <para>
    /// It is geometric and conservative on purpose. It works on the level data
    /// alone, models the world as a set of standable rectangles, and walks them
    /// with the CINEMATIC BUDGET of PRD 13.3:
    /// </para>
    /// <code>
    ///   jump             +1.50, horizontal reach 4.6 m
    ///   one crate        +1.30 to stand on, so +2.80 with the jump on top
    ///   two crates       +2.60, so +4.10
    ///   console/corniche +1.17, so +2.67
    ///   stairs           +4.62, so +6.12, run 7.0 m
    ///   walkway                 deck 9 m out, then a jump off its end: 13.6 m
    ///   backdrop ramp    the painted wall of a photo aimed 50 degrees up is a
    ///                    slope from +5.4 to +10.1, so it needs stairs to board
    /// </code>
    /// <para>
    /// Every number errs on the side of the PLAYER: the audit only reports what
    /// is out of reach even with the most generous reading of the tools
    /// available, so a report line is a real defect, never a maybe.
    /// </para>
    /// <para>
    /// Everything here is DESIGN space (PRD 4.1: x right, y up, -z forward),
    /// exactly like the authored data and like <see cref="PhotoMath"/>. Nothing
    /// is mirrored, because nothing is ever handed to a Unity transform: the
    /// audit never builds a scene. That is also why the anchor of a declared
    /// shot is built by hand below instead of with Quaternion.LookRotation,
    /// which speaks the mirrored, left handed convention.
    /// </para>
    /// </summary>
    public static class DesignAudit
    {
        // --- Height gained over the surface you stand on, jump included ------

        public const float LiftJump = 1.50f;
        public const float LiftOneCrate = 2.80f;
        public const float LiftTwoCrates = 4.10f;
        public const float LiftConsole = 2.67f;
        public const float LiftStairs = 6.12f;

        /// <summary>
        /// Two flights: place one from the ground, climb it, place the second
        /// from its landing. 4.62 twice, plus the jump.
        /// </summary>
        public const float LiftTwoStairs = 10.75f;

        // --- Horizontal reach, tool by tool ---------------------------------

        public const float ReachJump = 4.6f;

        /// <summary>
        /// The number that decides whether a puzzle is a puzzle. Jump velocity
        /// 6.5 against gravity 14 gives 0.929 s of flight; at the 8 m/s sprint
        /// that is 7.43 m of gap, cleared with no photo and no thought. A
        /// walkway deck is 8 m long, so NO FLAT GAP CAN EVER BE MADE MANDATORY:
        /// a crossing that has to resist the sprint needs a rise as well as a
        /// distance.
        /// </summary>
        public const float ReachSprint = 7.43f;

        public const float ReachStairs = 7.0f;

        /// <summary>
        /// A walkway deck runs from 1 m to 9 m in front of the placer, and its
        /// far end is a standing spot like any other: 9 m of deck plus a 4.6 m
        /// jump.
        /// </summary>
        public const float ReachWalkway = 13.6f;

        /// <summary>
        /// A prop this big on every axis or smaller is a crate: a photo of it is
        /// loose, so it can be dropped and stacked. Same threshold as
        /// <see cref="PhotoCapture.LooseMaxExtent"/>.
        /// </summary>
        public const float CrateMax = 1.6f;

        /// <summary>Interact range, so two pickups closer than this fight over the same ray.</summary>
        public const float PickupClearance = 0.7f;

        /// <summary>Above this, an item sitting on a surface is floating rather than standing.</summary>
        public const float StandingSlack = 0.5f;

        /// <summary>Eye height of the player, which is where a placement is anchored from.</summary>
        public const float EyeHeight = 1.62f;

        /// <summary>How far the lens prints, the same 12 m as <see cref="PhotoCapture.CaptureDepth"/>.</summary>
        public const float LensDepth = 12.0f;

        /// <summary>Slabs this thin are paint, not furniture: they are markers, never steps.</summary>
        const float MarkerMaxHeight = 0.2f;

        /// <summary>The two decor tints that declare a placement marker (PRD 13.4).</summary>
        static readonly string[] MarkerColors = { "teal", "accent" };

        // --- What the last run actually looked at -----------------------------
        //
        // An audit that walks NOTHING reports no defect, and a caller cannot tell
        // that apart from a clean sheet: same empty list, same exit code 0. These
        // two counters are the evidence that the walk happened, and the EditMode
        // gate asserts on them, so an audit gutted by a bad data load fails loudly
        // instead of certifying the levels it never opened.

        /// <summary>Levels the last audit walked. 25 on the shipped data.</summary>
        public static int LastLevelsAudited { get; private set; }

        /// <summary>
        /// Placements, marker slabs, standable surfaces, printable batteries and
        /// declared shots the last audit examined one by one. 340 on the shipped
        /// data (25 levels, 128 targets, 51 markers, 116 standable surfaces, 14
        /// printable batteries, 6 declared shots); a number near zero means the
        /// audit examined nothing.
        /// </summary>
        public static int LastInspections { get; private set; }

        // --- Entry points ----------------------------------------------------

        /// <summary>Audits every level and writes the report to the Editor console.</summary>
        [MenuItem("VIEWPOINT/Audit Level Design")]
        public static void Run()
        {
            Auditor auditor = RunAudit();
            string report = auditor.Format();
            if (auditor.Defects.Count == 0)
            {
                Debug.Log(report);
            }
            else
            {
                // An Editor console line that is not an error scrolls away
                // unnoticed, and a level defect must not be allowed to.
                Debug.LogError(report);
            }
        }

        /// <summary>
        /// The same audit for a headless run: prints the report and EXITS 1 when
        /// anything was found. The exit code is the whole point. A batch method
        /// that only logs leaves the process at 0, which in CI is indistinguishable
        /// from a pass, so a broken level would ship green.
        /// </summary>
        public static void RunBatch()
        {
            string report;
            int found;
            try
            {
                Auditor auditor = RunAudit();
                report = auditor.Format();
                found = auditor.Defects.Count;
            }
            catch (System.Exception error)
            {
                // A crash is not a pass either: the data could not be read, so
                // nothing was verified.
                System.Console.WriteLine("VIEWPOINT audit: l'audit a echoue: " + error);
                Debug.LogError("VIEWPOINT audit: l'audit a echoue: " + error);
                EditorApplication.Exit(1);
                return;
            }
            // Written to stdout as well as to the Unity log, so the report is
            // readable whatever -logFile the caller chose.
            System.Console.WriteLine(report);
            Debug.Log(report);
            EditorApplication.Exit(found > 0 ? 1 : 0);
        }

        /// <summary>
        /// Every defect as one formatted line, newest data every call. This is
        /// the shape the EditMode gate test consumes: it asserts the list is
        /// empty, so the audit fails the suite instead of needing to be
        /// remembered.
        /// </summary>
        public static List<string> Collect()
        {
            return Lines(RunAudit());
        }

        /// <summary>
        /// The same audit on ONE level handed in from outside the catalog, WITHOUT
        /// touching <see cref="LastLevelsAudited"/> or <see cref="LastInspections"/>.
        /// <para>
        /// The harness needs this as a positive control. On the shipped data the
        /// audit is expected to report nothing, so an audit whose checks had all
        /// been gutted would return the same empty list and read exactly like a
        /// clean sheet: a green gate that verified nothing. Feeding it a level
        /// with a known defect is the only way to tell the two apart, and the
        /// shipped data (correctly) cannot supply one.
        /// </para>
        /// <para>
        /// The level is audited as if it were the first, so REDITE has nothing
        /// earlier to compare its subtitle against.
        /// </para>
        /// </summary>
        public static List<string> CollectFor(LevelDef def)
        {
            Auditor auditor = new Auditor();
            auditor.AuditOne(0, def);
            return Lines(auditor);
        }

        static List<string> Lines(Auditor auditor)
        {
            List<string> lines = new List<string>();
            for (int i = 0; i < auditor.Defects.Count; i++)
            {
                Defect defect = auditor.Defects[i];
                lines.Add(string.Format(CultureInfo.InvariantCulture, "Niveau {0} - {1} : [{2}] {3}",
                    defect.Level, defect.Name, defect.Code, defect.Message));
            }
            return lines;
        }

        /// <summary>One full pass over the data, publishing what it looked at.</summary>
        static Auditor RunAudit()
        {
            Auditor auditor = new Auditor();
            auditor.AuditAll();
            LastLevelsAudited = auditor.LevelsAudited;
            LastInspections = auditor.Inspections;
            return auditor;
        }

        // --- Records ---------------------------------------------------------

        sealed class Defect
        {
            public int Level;
            public string Name;
            public string Code;
            public string Message;
        }

        /// <summary>A surface a player can stand on, as a rectangle plus its top height.</summary>
        struct Surface
        {
            public float Top;
            public float MinX, MaxX, MinZ, MaxZ;
            public string Kind;
        }

        /// <summary>A solid volume that swallows whatever stands inside it.</summary>
        struct Solid
        {
            public Vector3 Pos, Size;
            public string Kind;
        }

        /// <summary>Something the level asks the player to touch.</summary>
        struct Target
        {
            public Vector3 Pos;
            public string What;

            /// <summary>
            /// True for the pickups that float on purpose (a photo hangs at chest
            /// height so it reads as an object, not as litter): their height above
            /// the ground is art direction, not a defect.
            /// </summary>
            public bool Hovers;
        }

        /// <summary>
        /// The placement anchor of a declared shot: an orthonormal DESIGN space
        /// frame at the player's eye, -z along the line of sight, rolled by the
        /// wheel. Columns X, Y, Z, exactly like the Basis the original built with
        /// <c>Transform3D().looking_at(aim - eye, Vector3.UP)</c>.
        /// </summary>
        struct Anchor
        {
            public Vector3 Origin;
            public Vector3 X, Y, Z;

            /// <param name="origin">Where the placer stands, at eye height.</param>
            /// <param name="aim">The world point the shot is aimed at.</param>
            /// <param name="rollSteps">Wheel steps of 90 degrees (2 = upside down).</param>
            public static Anchor LookingAt(Vector3 origin, Vector3 aim, int rollSteps)
            {
                Vector3 forward = (aim - origin).normalized;
                // Godot's Basis.looking_at: z is BACKWARD, x = up cross z,
                // y = z cross x. Right handed, which design space is.
                Vector3 z = -forward;
                Vector3 x = Vector3.Cross(Vector3.up, z);
                if (x.sqrMagnitude < 1e-8f)
                {
                    // A perfectly vertical shot has no lateral reference. No level
                    // authors one; pick design forward so the frame stays finite
                    // instead of collapsing to zero and reporting nonsense.
                    x = Vector3.Cross(DesignSpace.DesignForward, z);
                }
                x = x.normalized;
                Vector3 y = Vector3.Cross(z, x);

                // The wheel rolls about the line of sight (the axis -z = forward).
                // X and Y are both perpendicular to it, so Rodrigues collapses to a
                // plane rotation: forward cross X == -Y and forward cross Y == X.
                //
                // The SIGN is the on-screen contract of PRD 6.4, not a sign copied
                // from GDScript: at one step ToWorld sends a photo-space point
                // (x, y) to (y, -x) of the unrolled frame, so what was on the right
                // ends up at the bottom. That is one quarter turn CLOCKWISE as the
                // player sees it, the same turn PhotoPlacer.RollRotation performs in
                // Unity space with AngleAxis(-90 * steps, forward). The shipped data
                // only declares roll 0 and roll 2, where the sign cancels, so the
                // levels do not pin it: the derivation does.
                float angle = rollSteps * Mathf.PI * 0.5f;
                float cos = Mathf.Cos(angle);
                float sin = Mathf.Sin(angle);

                Anchor anchor = new Anchor();
                anchor.Origin = origin;
                anchor.X = x * cos - y * sin;
                anchor.Y = y * cos + x * sin;
                anchor.Z = z;
                return anchor;
            }

            /// <summary>Photo space to world, the original's <c>anchor * point</c>.</summary>
            public Vector3 ToWorld(Vector3 local)
            {
                return Origin + X * local.x + Y * local.y + Z * local.z;
            }

            /// <summary>
            /// World to photo space, the original's <c>anchor.affine_inverse() *
            /// point</c>. The basis is orthonormal, so the inverse is its transpose
            /// and depth is <c>-result.z</c>, the PhotoMath convention.
            /// </summary>
            public Vector3 ToLocal(Vector3 world)
            {
                Vector3 offset = world - Origin;
                return new Vector3(Vector3.Dot(offset, X), Vector3.Dot(offset, Y), Vector3.Dot(offset, Z));
            }
        }

        // --- The audit -------------------------------------------------------

        sealed class Auditor
        {
            public readonly List<Defect> Defects = new List<Defect>();

            /// <summary>Levels actually walked, and things actually examined.</summary>
            public int LevelsAudited;

            public int Inspections;

            int _level;
            LevelDef _def;
            List<Solid> _solidCache;

            public void AuditAll()
            {
                for (int i = 0; i < LevelDefs.Count; i++)
                {
                    AuditOne(i, LevelDefs.GetDef(i));
                }
            }

            /// <summary>
            /// One level, numbered by its index so REDITE can look back at the
            /// levels before it. A null def is skipped and counts for nothing:
            /// the counters must never claim a level that was not walked.
            /// </summary>
            public void AuditOne(int index, LevelDef def)
            {
                _level = index;
                _def = def;
                _solidCache = null;
                if (def == null)
                {
                    return;
                }
                LevelsAudited++;
                Inspections++;
                Audit(def);
            }

            public string Format()
            {
                StringBuilder text = new StringBuilder();
                text.AppendLine();
                text.AppendLine("=== VIEWPOINT audit de level design ===");
                if (Defects.Count == 0)
                {
                    text.AppendLine(string.Format(CultureInfo.InvariantCulture,
                        "  aucun defaut de level design sur {0} niveaux", LevelDefs.Count));
                    text.AppendLine("=======================================");
                    return text.ToString();
                }
                int current = -1;
                for (int i = 0; i < Defects.Count; i++)
                {
                    Defect defect = Defects[i];
                    if (defect.Level != current)
                    {
                        current = defect.Level;
                        text.AppendLine();
                        text.AppendLine(string.Format(CultureInfo.InvariantCulture,
                            "  Niveau {0} - {1}", current, defect.Name));
                    }
                    text.AppendLine(string.Format(CultureInfo.InvariantCulture,
                        "    [{0}] {1}", defect.Code, defect.Message));
                }
                text.AppendLine();
                text.AppendLine(string.Format(CultureInfo.InvariantCulture,
                    "  {0} defauts sur {1} niveaux", Defects.Count, LevelDefs.Count));
                text.AppendLine("=======================================");
                return text.ToString();
            }

            void Report(string code, string message)
            {
                Defect defect = new Defect();
                defect.Level = _level + 1;
                defect.Name = _def != null && !string.IsNullOrEmpty(_def.Name) ? _def.Name : "?";
                defect.Code = code;
                defect.Message = message;
                Defects.Add(defect);
            }

            // --- The world as rectangles -------------------------------------

            /// <summary>
            /// Every surface a player can stand on. Platforms and decor blocks are
            /// solid boxes; a roofed cage is a box you can stand on as well (its
            /// roof carries collision).
            /// </summary>
            List<Surface> Surfaces(LevelDef def)
            {
                List<Surface> result = new List<Surface>();
                for (int i = 0; i < def.Platforms.Count; i++)
                {
                    result.Add(SurfaceOf(def.Platforms[i].Pos, def.Platforms[i].Size, "sol"));
                }
                for (int i = 0; i < def.Decor.Count; i++)
                {
                    Vector3 size = def.Decor[i].Size;
                    // Marker slabs are paint, not furniture: standing on one is
                    // standing on the floor under it.
                    if (size.y <= MarkerMaxHeight)
                    {
                        continue;
                    }
                    result.Add(SurfaceOf(def.Decor[i].Pos, size, "decor"));
                }
                for (int i = 0; i < def.Erasables.Count; i++)
                {
                    result.Add(SurfaceOf(def.Erasables[i].Pos, def.Erasables[i].Size, "bloc lavande"));
                }
                for (int i = 0; i < def.Cages.Count; i++)
                {
                    CageDef cage = def.Cages[i];
                    if (!cage.Roof)
                    {
                        continue;
                    }
                    // Cage pos is the center of its FLOOR, so the roof is a full
                    // size.y up.
                    result.Add(SurfaceOf(cage.Pos + new Vector3(0f, cage.Size.y * 0.5f, 0f), cage.Size, "toit de cage"));
                }
                return result;
            }

            static Surface SurfaceOf(Vector3 center, Vector3 size, string kind)
            {
                Surface surface = new Surface();
                surface.Top = center.y + size.y * 0.5f;
                surface.MinX = center.x - size.x * 0.5f;
                surface.MaxX = center.x + size.x * 0.5f;
                surface.MinZ = center.z - size.z * 0.5f;
                surface.MaxZ = center.z + size.z * 0.5f;
                surface.Kind = kind;
                return surface;
            }

            /// <summary>Solid volumes that swallow whatever stands inside them.</summary>
            List<Solid> Solids(LevelDef def)
            {
                if (_solidCache != null)
                {
                    return _solidCache;
                }
                List<Solid> result = new List<Solid>();
                for (int i = 0; i < def.Platforms.Count; i++)
                {
                    result.Add(SolidOf(def.Platforms[i].Pos, def.Platforms[i].Size, "plateforme"));
                }
                for (int i = 0; i < def.Decor.Count; i++)
                {
                    Vector3 size = def.Decor[i].Size;
                    if (size.y <= MarkerMaxHeight)
                    {
                        continue;
                    }
                    result.Add(SolidOf(def.Decor[i].Pos, size, "decor"));
                }
                for (int i = 0; i < def.Erasables.Count; i++)
                {
                    result.Add(SolidOf(def.Erasables[i].Pos, def.Erasables[i].Size, "bloc lavande"));
                }
                _solidCache = result;
                return result;
            }

            static Solid SolidOf(Vector3 pos, Vector3 size, string kind)
            {
                Solid solid = new Solid();
                solid.Pos = pos;
                solid.Size = size;
                solid.Kind = kind;
                return solid;
            }

            /// <summary>Horizontal gap between two surfaces, zero when they overlap or touch.</summary>
            static float Gap(Surface a, Surface b)
            {
                float dx = Mathf.Max(Mathf.Max(a.MinX - b.MaxX, b.MinX - a.MaxX), 0f);
                float dz = Mathf.Max(Mathf.Max(a.MinZ - b.MaxZ, b.MinZ - a.MaxZ), 0f);
                return new Vector2(dx, dz).magnitude;
            }

            static bool Covers(Surface surface, Vector3 point)
            {
                return point.x >= surface.MinX - 0.05f && point.x <= surface.MaxX + 0.05f
                    && point.z >= surface.MinZ - 0.05f && point.z <= surface.MaxZ + 0.05f;
            }

            // --- The tools the level hands out -------------------------------

            /// <summary>
            /// How many crates the player can drop in this level: one per "caisse"
            /// photo, plus one per film as long as there is something crate sized
            /// to photograph.
            /// </summary>
            int CrateCount(LevelDef def)
            {
                int crates = 0;
                for (int i = 0; i < def.Photos.Count; i++)
                {
                    if (def.Photos[i].Id == "caisse")
                    {
                        crates++;
                    }
                }
                if (def.Camera != null && HasCrateModel(def))
                {
                    crates += def.Camera.Films;
                }
                return crates;
            }

            bool HasCrateModel(LevelDef def)
            {
                for (int i = 0; i < def.Decor.Count; i++)
                {
                    if (IsCrateSized(def.Decor[i].Size))
                    {
                        return true;
                    }
                }
                for (int i = 0; i < def.Erasables.Count; i++)
                {
                    if (IsCrateSized(def.Erasables[i].Size))
                    {
                        return true;
                    }
                }
                return false;
            }

            static bool IsCrateSized(Vector3 size)
            {
                return size.x <= CrateMax && size.y <= CrateMax && size.z <= CrateMax;
            }

            /// <summary>
            /// The photo ids this level hands out, nested photos included: a photo
            /// inside a photo is a tool too, once the outer one is placed.
            /// </summary>
            List<string> PhotoIds(LevelDef def)
            {
                List<string> ids = new List<string>();
                for (int i = 0; i < def.Photos.Count; i++)
                {
                    string id = def.Photos[i].Id;
                    if (!ids.Contains(id))
                    {
                        ids.Add(id);
                    }
                    PhotoDef photo = PhotoDefs.GetDef(id);
                    if (photo == null || photo.Props == null)
                    {
                        continue;
                    }
                    for (int p = 0; p < photo.Props.Count; p++)
                    {
                        PhotoProp prop = photo.Props[p];
                        if (prop.Kind == "photo" && !ids.Contains(prop.Id))
                        {
                            ids.Add(prop.Id);
                        }
                    }
                }
                return ids;
            }

            /// <summary>The highest step this level can offer over a surface, jump included.</summary>
            float MaxLift(LevelDef def)
            {
                float lift = LiftJump;
                List<string> ids = PhotoIds(def);
                if (ids.Contains("escalier"))
                {
                    lift = Mathf.Max(lift, LiftStairs);
                }
                if (ids.Contains("console") || ids.Contains("corniche"))
                {
                    lift = Mathf.Max(lift, LiftConsole);
                }
                int crates = CrateCount(def);
                if (crates >= 2)
                {
                    lift = Mathf.Max(lift, LiftTwoCrates);
                }
                else if (crates == 1)
                {
                    lift = Mathf.Max(lift, LiftOneCrate);
                }
                // A camera can photograph a piece of ground or a wall and put it
                // back as a step, which is at least as good as one crate.
                if (def.Camera != null)
                {
                    lift = Mathf.Max(lift, LiftOneCrate);
                }
                // A second flight placed from the landing of the first.
                int flights = 0;
                for (int i = 0; i < def.Photos.Count; i++)
                {
                    if (def.Photos[i].Id == "escalier")
                    {
                        flights++;
                    }
                }
                if (flights >= 2)
                {
                    lift = Mathf.Max(lift, LiftTwoStairs);
                }
                return lift;
            }

            float MaxReach(LevelDef def)
            {
                float reach = ReachJump;
                List<string> ids = PhotoIds(def);
                if (ids.Contains("passerelle"))
                {
                    reach = Mathf.Max(reach, ReachWalkway);
                }
                if (ids.Contains("escalier"))
                {
                    reach = Mathf.Max(reach, ReachStairs);
                }
                // A shot of anything long enough turns into a plank; the walkway is
                // the most generous thing in the game, so a camera is worth that
                // reach.
                if (def.Camera != null)
                {
                    reach = Mathf.Max(reach, ReachWalkway);
                }
                return reach;
            }

            // --- Reachability ------------------------------------------------

            /// <summary>
            /// Indices of the surfaces the player can be standing on, walking out
            /// from the spawn. Going down is always free (falling costs nothing
            /// above kill_y); going up costs at most <see cref="MaxLift"/>.
            /// </summary>
            HashSet<int> Reachable(LevelDef def, List<Surface> surfaces)
            {
                return Walk(def, surfaces, MaxLift(def), MaxReach(def), null);
            }

            /// <summary>
            /// The same walk with EMPTY HANDS: one jump, sprinting, and this time
            /// the walls count. Whatever this reaches is free, and a level whose
            /// whole solution sits inside it has no puzzle.
            /// </summary>
            HashSet<int> ReachableBarehanded(LevelDef def, List<Surface> surfaces)
            {
                return Walk(def, surfaces, LiftJump, ReachSprint, Walls(def));
            }

            /// <summary>
            /// The blocks that actually stop a walk: a slab tall enough not to be
            /// jumped (more than 1.5 m over the ground it stands on) AND wide
            /// enough to span the platform it sits on, so there is no walking
            /// around it. A tower or a crate is not a wall, it is scenery you
            /// skirt; only a full width barrier counts, which is exactly the thing
            /// a photo is meant to pierce.
            /// </summary>
            List<Solid> Walls(LevelDef def)
            {
                List<Solid> result = new List<Solid>();
                List<Solid> solids = Solids(def);
                for (int s = 0; s < solids.Count; s++)
                {
                    Vector3 pos = solids[s].Pos;
                    Vector3 size = solids[s].Size;
                    for (int p = 0; p < def.Platforms.Count; p++)
                    {
                        Vector3 platformPos = def.Platforms[p].Pos;
                        Vector3 platformSize = def.Platforms[p].Size;
                        float platformTop = platformPos.y + platformSize.y * 0.5f;
                        if (pos.y + size.y * 0.5f <= platformTop + LiftJump)
                        {
                            continue;
                        }
                        if (pos.y - size.y * 0.5f > platformTop + 1.75f)
                        {
                            continue;
                        }
                        bool spansX = size.x >= platformSize.x * 0.9f;
                        bool spansZ = size.z >= platformSize.z * 0.9f;
                        if (spansX || spansZ)
                        {
                            result.Add(solids[s]);
                            break;
                        }
                    }
                }
                return result;
            }

            /// <summary>
            /// True when the straight line from a to b runs into one of the walls.
            /// The player can step around scenery, never through a barrier.
            /// </summary>
            static bool Blocked(List<Solid> walls, Surface a, Surface b)
            {
                return CrossesWall(walls,
                    new Vector2((a.MinX + a.MaxX) * 0.5f, (a.MinZ + a.MaxZ) * 0.5f),
                    new Vector2((b.MinX + b.MaxX) * 0.5f, (b.MinZ + b.MaxZ) * 0.5f));
            }

            /// <summary>
            /// The same test between two world points. Needed because a single
            /// platform often runs on BOTH sides of its wall (level 4 is one 28 m
            /// corridor cut in two), so surface connectivity alone cannot see the
            /// barrier at all.
            /// </summary>
            static bool CrossesWall(List<Solid> walls, Vector2 from, Vector2 to)
            {
                if (walls == null || walls.Count == 0)
                {
                    return false;
                }
                for (int w = 0; w < walls.Count; w++)
                {
                    Vector3 pos = walls[w].Pos;
                    Vector3 size = walls[w].Size;
                    // The footprint, as Godot's Rect2: lower bound inclusive,
                    // upper bound exclusive, so has_point matches exactly.
                    float minX = pos.x - size.x * 0.5f;
                    float minZ = pos.z - size.z * 0.5f;
                    float maxX = minX + size.x;
                    float maxZ = minZ + size.z;
                    for (int step = 0; step <= 40; step++)
                    {
                        Vector2 point = Vector2.Lerp(from, to, step / 40f);
                        if (point.x >= minX && point.y >= minZ && point.x < maxX && point.y < maxZ)
                        {
                            return true;
                        }
                    }
                }
                return false;
            }

            HashSet<int> Walk(LevelDef def, List<Surface> surfaces, float lift, float reach, List<Solid> walls)
            {
                Vector3 spawn = def.Spawn;
                List<int> start = new List<int>();
                for (int i = 0; i < surfaces.Count; i++)
                {
                    if (Covers(surfaces[i], spawn) && surfaces[i].Top <= spawn.y + 0.2f)
                    {
                        start.Add(i);
                    }
                }
                return WalkFrom(surfaces, start, lift, reach, walls);
            }

            /// <summary>
            /// The same flood, from wherever you already stand. Used to answer the
            /// other half of the question: not "can he get there" but "can he get
            /// BACK". A battery at the bottom of a pit he cannot climb out of is
            /// not a battery he can spend, it is a reason to restart the level.
            /// </summary>
            static HashSet<int> WalkFrom(List<Surface> surfaces, List<int> start, float lift, float reach, List<Solid> walls)
            {
                List<int> open = new List<int>();
                HashSet<int> seen = new HashSet<int>();
                for (int i = 0; i < start.Count; i++)
                {
                    if (seen.Add(start[i]))
                    {
                        open.Add(start[i]);
                    }
                }
                while (open.Count > 0)
                {
                    int current = open[open.Count - 1];
                    open.RemoveAt(open.Count - 1);
                    for (int i = 0; i < surfaces.Count; i++)
                    {
                        if (seen.Contains(i))
                        {
                            continue;
                        }
                        if (Gap(surfaces[current], surfaces[i]) > reach)
                        {
                            continue;
                        }
                        float climb = surfaces[i].Top - surfaces[current].Top;
                        if (climb > lift)
                        {
                            continue;
                        }
                        if (Blocked(walls, surfaces[current], surfaces[i]))
                        {
                            continue;
                        }
                        seen.Add(i);
                        open.Add(i);
                    }
                }
                return seen;
            }

            /// <summary>The surface an item stands on: the highest one under it that covers it.</summary>
            static int Support(List<Surface> surfaces, Vector3 point)
            {
                int best = -1;
                for (int i = 0; i < surfaces.Count; i++)
                {
                    if (!Covers(surfaces[i], point))
                    {
                        continue;
                    }
                    if (surfaces[i].Top > point.y + 0.06f)
                    {
                        continue;
                    }
                    if (best < 0 || surfaces[i].Top > surfaces[best].Top)
                    {
                        best = i;
                    }
                }
                return best;
            }

            bool InsideSolid(LevelDef def, Vector3 point, float margin, out Solid hit)
            {
                List<Solid> solids = Solids(def);
                for (int i = 0; i < solids.Count; i++)
                {
                    Vector3 pos = solids[i].Pos;
                    Vector3 size = solids[i].Size;
                    if (Mathf.Abs(point.x - pos.x) < size.x * 0.5f - margin
                        && Mathf.Abs(point.z - pos.z) < size.z * 0.5f - margin
                        && point.y > pos.y - size.y * 0.5f + margin
                        && point.y < pos.y + size.y * 0.5f - margin)
                    {
                        hit = solids[i];
                        return true;
                    }
                }
                hit = new Solid();
                return false;
            }

            bool InsideSolid(LevelDef def, Vector3 point, out Solid hit)
            {
                return InsideSolid(def, point, 0.05f, out hit);
            }

            /// <summary>
            /// Every battery of a level, whatever list it comes from. Lead counts:
            /// it is worth one battery to a teleporter, which is all this tally is
            /// about.
            /// </summary>
            static List<Vector3> AllFreeBatteries(LevelDef def)
            {
                List<Vector3> result = new List<Vector3>();
                result.AddRange(def.Batteries);
                result.AddRange(def.SealedBatteries);
                return result;
            }

            static bool InAnyCage(LevelDef def, Vector3 point)
            {
                for (int i = 0; i < def.Cages.Count; i++)
                {
                    if (InCage(def.Cages[i], point))
                    {
                        return true;
                    }
                }
                return false;
            }

            static bool InSealedCage(LevelDef def, Vector3 point)
            {
                for (int i = 0; i < def.Cages.Count; i++)
                {
                    if (def.Cages[i].Sealed && InCage(def.Cages[i], point))
                    {
                        return true;
                    }
                }
                return false;
            }

            /// <summary>Cage pos is the center of the FLOOR, size the whole enclosure.</summary>
            static bool InCage(CageDef cage, Vector3 point)
            {
                return Mathf.Abs(point.x - cage.Pos.x) <= cage.Size.x * 0.5f
                    && Mathf.Abs(point.z - cage.Pos.z) <= cage.Size.z * 0.5f
                    && point.y >= cage.Pos.y - 0.05f
                    && point.y <= cage.Pos.y + cage.Size.y;
            }

            static bool IsMarker(DecorDef decor)
            {
                for (int i = 0; i < MarkerColors.Length; i++)
                {
                    if (MarkerColors[i] == decor.Color)
                    {
                        return true;
                    }
                }
                return false;
            }

            // --- The audit itself --------------------------------------------

            void Audit(LevelDef def)
            {
                List<Surface> surfaces = Surfaces(def);
                HashSet<int> reachable = Reachable(def, surfaces);

                // What the level asks the player to touch. A battery locked in a
                // steel cage is deliberately NOT in this list: it is a model to
                // photograph, and the unit suite already proves the level hands out
                // a camera for it.
                List<Target> targets = new List<Target>();
                for (int i = 0; i < def.Batteries.Count; i++)
                {
                    if (!InSealedCage(def, def.Batteries[i]))
                    {
                        targets.Add(MakeTarget(def.Batteries[i], "une pile", false));
                    }
                }
                for (int i = 0; i < def.SealedBatteries.Count; i++)
                {
                    targets.Add(MakeTarget(def.SealedBatteries[i], "une pile plombee", false));
                }
                for (int i = 0; i < def.Photos.Count; i++)
                {
                    targets.Add(MakeTarget(def.Photos[i].Pos, "la photo " + def.Photos[i].Id, true));
                }
                if (def.Camera != null)
                {
                    targets.Add(MakeTarget(def.Camera.Pos, "l'appareil photo", true));
                }
                targets.Add(MakeTarget(def.Teleporter.Pos, "le teleporteur", false));

                for (int t = 0; t < targets.Count; t++)
                {
                    Inspections++;
                    Vector3 pos = targets[t].Pos;
                    int support = Support(surfaces, pos);
                    if (support < 0)
                    {
                        Report("VIDE", targets[t].What + " flotte : aucune surface sous elle");
                        continue;
                    }
                    float drop = pos.y - surfaces[support].Top;
                    // Everything must stay within arm's reach of its support,
                    // hovering pickups included: 1.7 m is the interaction range.
                    float slack = targets[t].Hovers ? 1.7f : StandingSlack;
                    if (drop > slack)
                    {
                        Report("FLOTTE", string.Format(CultureInfo.InvariantCulture,
                            "{0} est a {1} m au dessus de son appui", targets[t].What, F2(drop)));
                    }
                    if (!reachable.Contains(support))
                    {
                        Report("HORS_ATTEINTE", string.Format(CultureInfo.InvariantCulture,
                            "{0} repose sur un {1} inaccessible (sommet a {2} m, elevation max du niveau {3} m)",
                            targets[t].What, surfaces[support].Kind, F2(surfaces[support].Top), F2(MaxLift(def))));
                    }
                    Solid swallowed;
                    if (InsideSolid(def, pos + new Vector3(0f, 0.35f, 0f), out swallowed))
                    {
                        Report("ENCASTRE", targets[t].What + " est prise dans un " + swallowed.Kind);
                    }
                }

                // Two pickups sharing the same spot fight over the interaction ray.
                for (int i = 0; i < targets.Count; i++)
                {
                    for (int j = i + 1; j < targets.Count; j++)
                    {
                        float apart = Vector3.Distance(targets[i].Pos, targets[j].Pos);
                        if (apart < PickupClearance)
                        {
                            Report("COLLE", string.Format(CultureInfo.InvariantCulture,
                                "{0} et {1} se disputent le meme rayon ({2} m d'ecart)",
                                targets[i].What, targets[j].What, F2(apart)));
                        }
                    }
                }

                // The spawn itself.
                Vector3 spawn = def.Spawn;
                Solid spawnSolid;
                if (InsideSolid(def, spawn, out spawnSolid))
                {
                    Report("SPAWN", "le joueur apparait dans un " + spawnSolid.Kind);
                }
                if (InSealedCage(def, spawn))
                {
                    Report("SPAWN", "le joueur apparait dans une cage d'acier");
                }

                // Marker slabs: they exist to be seen and stood on, so they must lie
                // on a surface the player can reach and must not be buried.
                for (int i = 0; i < def.Decor.Count; i++)
                {
                    DecorDef decor = def.Decor[i];
                    if (!IsMarker(decor))
                    {
                        continue;
                    }
                    Inspections++;
                    Vector3 pos = decor.Pos;
                    int support = Support(surfaces, pos + new Vector3(0f, 0.1f, 0f));
                    if (support < 0)
                    {
                        Report("REPERE", string.Format(CultureInfo.InvariantCulture,
                            "un repere de pose flotte en {0}, {1}", F1(pos.x), F1(pos.z)));
                        continue;
                    }
                    if (!reachable.Contains(support))
                    {
                        Report("REPERE", string.Format(CultureInfo.InvariantCulture,
                            "un repere de pose en {0}, {1} est sur une surface inaccessible", F1(pos.x), F1(pos.z)));
                    }
                    if (InSealedCage(def, pos))
                    {
                        Report("REPERE", "un repere de pose est enferme dans une cage d'acier");
                    }
                }

                // One way drops: a surface you can only leave by dying. Tolerated
                // when the teleporter is down there (the level ends), flagged
                // otherwise.
                float lift = MaxLift(def);
                float reach = MaxReach(def);
                Vector3 telePos = def.Teleporter.Pos;
                for (int i = 0; i < surfaces.Count; i++)
                {
                    Inspections++;
                    if (!reachable.Contains(i))
                    {
                        continue;
                    }
                    bool trapped = true;
                    for (int j = 0; j < surfaces.Count; j++)
                    {
                        if (i == j)
                        {
                            continue;
                        }
                        if (Gap(surfaces[i], surfaces[j]) > reach)
                        {
                            continue;
                        }
                        if (surfaces[j].Top - surfaces[i].Top <= lift)
                        {
                            trapped = false;
                            break;
                        }
                    }
                    if (trapped && !Covers(surfaces[i], telePos))
                    {
                        Report("PIEGE", string.Format(CultureInfo.InvariantCulture,
                            "un {0} a {1} m est un cul de sac : on y descend, on n'en remonte pas",
                            surfaces[i].Kind, F2(surfaces[i].Top)));
                    }
                }

                // TRIVIALITY. A level that hands out photos or a camera is making a
                // promise: that its tools are needed. Walk it again with empty
                // hands, sprinting, and count what a player who never touches a
                // photo can carry to the teleporter. If that already meets the
                // requirement, the level is a corridor.
                HashSet<int> freeHands = ReachableBarehanded(def, surfaces);
                List<Solid> walls = Walls(def);
                Vector2 spawnFlat = new Vector2(spawn.x, spawn.z);
                bool hasTools = def.Photos.Count > 0 || def.Camera != null;
                if (hasTools)
                {
                    // A battery behind bars costs a photo whatever the bars are made
                    // of: steel is never opened, lavender is opened by spending a
                    // placement. Neither is free, so neither counts here.
                    int teleSupport = Support(surfaces, telePos);
                    bool teleFree = teleSupport >= 0 && freeHands.Contains(teleSupport)
                        && !CrossesWall(walls, spawnFlat, new Vector2(telePos.x, telePos.z));
                    int freeBatteries = 0;
                    List<Vector3> batteries = AllFreeBatteries(def);
                    for (int i = 0; i < batteries.Count; i++)
                    {
                        Vector3 batteryPos = batteries[i];
                        if (InAnyCage(def, batteryPos))
                        {
                            continue;
                        }
                        int support = Support(surfaces, batteryPos);
                        if (support < 0 || !freeHands.Contains(support))
                        {
                            continue;
                        }
                        if (CrossesWall(walls, spawnFlat, new Vector2(batteryPos.x, batteryPos.z)))
                        {
                            continue;
                        }
                        // And the way back, with the same empty hands.
                        if (teleSupport >= 0)
                        {
                            List<int> from = new List<int>();
                            from.Add(support);
                            if (!WalkFrom(surfaces, from, LiftJump, ReachSprint, walls).Contains(teleSupport))
                            {
                                continue;
                            }
                        }
                        freeBatteries++;
                    }
                    int required = def.Teleporter.Required;
                    if (freeBatteries >= required && teleFree)
                    {
                        Report("TRIVIALE", string.Format(CultureInfo.InvariantCulture,
                            "{0} piles sur {1} requises et le teleporteur sont atteignables en sprintant, sans poser une seule photo",
                            freeBatteries, required));
                    }
                }

                // THE LENS IGNORES DISTANCE AND OCCLUSION. It prints anything framed
                // between 0.5 m and 12 m, through bars, over ledges, across a void.
                // So a CLIMB is only a climb if what waits at the top cannot simply
                // be shot from the bottom: one photo, and the copy drops at the
                // player's feet.
                //
                // The flag needs both halves to mean anything. The battery must sit
                // where the level clearly built a way up to it (reachable WITH the
                // tools, not barehanded), and it must be printable from a free
                // standing spot. A battery on an island no tool can reach is not a
                // defect: shooting it from across the void IS the level (that is
                // level 19, and it must stay clean).
                //
                // Lead is the answer whenever a climb has to stay a climb: it cannot
                // be printed, so height stays height. Leaden batteries are not in
                // this loop.
                if (def.Camera != null)
                {
                    for (int b = 0; b < def.Batteries.Count; b++)
                    {
                        Inspections++;
                        Vector3 batteryPos = def.Batteries[b];
                        // A battery behind bars is a MODEL, whatever the bars are
                        // made of: reaching it was never the plan, printing it was.
                        if (InAnyCage(def, batteryPos))
                        {
                            continue;
                        }
                        int support = Support(surfaces, batteryPos);
                        if (support < 0 || freeHands.Contains(support) || !reachable.Contains(support))
                        {
                            continue;
                        }
                        float closest = float.PositiveInfinity;
                        for (int i = 0; i < surfaces.Count; i++)
                        {
                            if (!freeHands.Contains(i))
                            {
                                continue;
                            }
                            Vector3 stand = new Vector3(
                                Mathf.Clamp(batteryPos.x, surfaces[i].MinX, surfaces[i].MaxX),
                                surfaces[i].Top + EyeHeight,
                                Mathf.Clamp(batteryPos.z, surfaces[i].MinZ, surfaces[i].MaxZ));
                            closest = Mathf.Min(closest,
                                Vector3.Distance(stand, batteryPos + new Vector3(0f, 0.35f, 0f)));
                        }
                        if (closest <= LensDepth)
                        {
                            Report("TRIVIALE", string.Format(CultureInfo.InvariantCulture,
                                "une pile perchee a {0} m est a {1} m d'un sol libre : l'objectif la copie d'en bas et la montee construite pour elle devient facultative (rendez-la plombee, ou eloignez-la de plus de {2} m)",
                                F2(surfaces[support].Top), F1(closest), F0(LensDepth)));
                        }
                    }
                }

                // A walkway exists to cross something. If every gap this level
                // offers is already within a sprinting jump (7.43 m), the photo is
                // scenery.
                if (PhotoIds(def).Contains("passerelle"))
                {
                    float realGap = 0f;
                    for (int i = 0; i < surfaces.Count; i++)
                    {
                        if (!freeHands.Contains(i))
                        {
                            continue;
                        }
                        for (int j = 0; j < surfaces.Count; j++)
                        {
                            if (i == j || freeHands.Contains(j))
                            {
                                continue;
                            }
                            realGap = Mathf.Max(realGap, Gap(surfaces[i], surfaces[j]));
                        }
                    }
                    if (realGap <= ReachSprint)
                    {
                        Report("TRIVIALE", string.Format(CultureInfo.InvariantCulture,
                            "la passerelle ne franchit rien : le plus large gouffre du niveau ({0} m) passe au saut sprinte ({1} m)",
                            F2(realGap), F2(ReachSprint)));
                    }
                }

                // THE INTENDED SHOT, when the marker declares it. A marker says
                // where to STAND; on its own that has never been enough, because
                // what a placement actually does depends on where the player LOOKS,
                // and no test could see that. A marker may therefore carry three
                // more fields (PRD 13.5):
                //
                //   "photo" : the id it serves        "aim" : the world point to look at
                //   "roll"  : quarter turns of the wheel (2 = the photo upside down)
                //
                // With those, the whole placement is reproducible and two things get
                // checked that used to cost a playthrough to discover.
                for (int i = 0; i < def.Decor.Count; i++)
                {
                    DecorDef decor = def.Decor[i];
                    if (!decor.HasAim || string.IsNullOrEmpty(decor.Photo))
                    {
                        continue;
                    }
                    Inspections++;
                    AuditShot(def, surfaces, decor);
                }

                // Teaching: a level that introduces nothing and repeats an earlier
                // subtitle is a filler level.
                string subtitle = def.Subtitle == null ? string.Empty : def.Subtitle;
                for (int j = 0; j < _level; j++)
                {
                    LevelDef earlier = LevelDefs.GetDef(j);
                    string other = earlier == null || earlier.Subtitle == null ? string.Empty : earlier.Subtitle;
                    if (other == subtitle)
                    {
                        Report("REDITE", string.Format(CultureInfo.InvariantCulture,
                            "sous-titre identique a celui du niveau {0}", j + 1));
                    }
                }
            }

            static Target MakeTarget(Vector3 pos, string what, bool hovers)
            {
                Target target = new Target();
                target.Pos = pos;
                target.What = what;
                target.Hovers = hovers;
                return target;
            }

            /// <summary>
            /// Replays one declared placement and checks the two things that decide
            /// whether it was worth making.
            /// </summary>
            void AuditShot(LevelDef def, List<Surface> surfaces, DecorDef marker)
            {
                string photoId = marker.Photo;
                PhotoDef photo = PhotoDefs.GetDef(photoId);
                if (photo == null)
                {
                    Report("REPERE", "un repere annonce la photo " + photoId + ", absente du catalogue");
                    return;
                }
                Vector3 pos = marker.Pos;
                int support = Support(surfaces, pos + new Vector3(0f, 0.1f, 0f));
                if (support < 0)
                {
                    // Already reported as a floating marker above.
                    return;
                }
                Vector3 eye = new Vector3(pos.x, surfaces[support].Top + EyeHeight, pos.z);
                Vector3 aim = marker.Aim;
                if (Vector3.Distance(eye, aim) < 0.5f)
                {
                    Report("REPERE", "un repere vise un point ou se tient deja le joueur");
                    return;
                }

                // The anchor: the camera looking at the aim point, rolled by the wheel.
                Anchor anchor = Anchor.LookingAt(eye, aim, marker.Roll);

                // A. THE PAINTED WALL IS SOLID, and it stands at the photo's own
                // depth, square across the line of sight. So whatever the shot is
                // aimed AT must be nearer than that wall, or the placement seals it
                // away: that is how a battery ends up walled in, and how a flight of
                // stairs ends up facing a cliff of sky 1.2 m above its last step.
                PhotoBackdrop backdrop = photo.Backdrop;
                if (backdrop != null)
                {
                    float depth = backdrop.Depth;
                    float toAim = Vector3.Distance(eye, aim);
                    if (toAim > depth)
                    {
                        Report("EMMURE", string.Format(CultureInfo.InvariantCulture,
                            "la pose de {0} vise a {1} m alors que son fond peint se plante a {2} m : la cible finit derriere un mur plein",
                            photoId, F1(toAim), F1(depth)));
                    }

                    // A bis. AND SO MUST EVERYTHING THE SHOT IS SUPPOSED TO WIN.
                    // Aiming short of the wall is not enough: the wall is as wide as
                    // the frame, so a battery standing behind its plane and inside
                    // its span is sealed away by the very placement meant to reach
                    // it. This is the failure that costs a whole level and shows
                    // nothing on screen until it is too late.
                    float half = PhotoMath.HalfExtentAt(depth, PhotoMath.PhotoFovDeg);
                    List<Vector3> batteries = AllFreeBatteries(def);
                    for (int i = 0; i < batteries.Count; i++)
                    {
                        Vector3 local = anchor.ToLocal(batteries[i] + new Vector3(0f, 0.35f, 0f));
                        if (-local.z <= depth)
                        {
                            continue;
                        }
                        if (Mathf.Abs(local.x) <= half * PhotoMath.PhotoAspect && Mathf.Abs(local.y) <= half)
                        {
                            Report("EMMURE", string.Format(CultureInfo.InvariantCulture,
                                "la pose de {0} depuis ce repere plante son mur a {1} m devant une pile qui est a {2} m : elle devient inaccessible",
                                photoId, F1(depth), F1(-local.z)));
                        }
                    }
                }

                // B. THE PROPS MUST LAND SOMEWHERE THEY EXIST. Grey ground and decor
                // are permanent, so a slab that materializes inside one of them is
                // simply a photo thrown away, with nothing on screen to say so.
                int buried = 0;
                int total = 0;
                List<Primitive> prims = PhotoDefs.ExpandProps(photo);
                for (int i = 0; i < prims.Count; i++)
                {
                    Primitive prim = prims[i];
                    if (prim.Kind == "battery" || prim.Kind == "photo_item")
                    {
                        continue;
                    }
                    if (prim.Loose)
                    {
                        continue;
                    }
                    total++;
                    Solid hit;
                    if (InsideSolid(def, anchor.ToWorld(prim.Center), 0.15f, out hit))
                    {
                        buried++;
                    }
                }
                if (total > 0 && buried == total)
                {
                    Report("ENTERRE", "la pose de " + photoId
                        + " depuis ce repere materialise tout son contenu a l'interieur d'un bloc permanent : la photo est perdue");
                }
                else if (buried > 0)
                {
                    Report("ENTERRE", string.Format(CultureInfo.InvariantCulture,
                        "la pose de {0} depuis ce repere enterre {1} de ses {2} elements dans un bloc permanent",
                        photoId, buried, total));
                }
            }
        }

        // --- Number formatting, the original's %.0f, %.1f and %.2f -----------

        static string F0(float value)
        {
            return value.ToString("0", CultureInfo.InvariantCulture);
        }

        static string F1(float value)
        {
            return value.ToString("0.0", CultureInfo.InvariantCulture);
        }

        static string F2(float value)
        {
            return value.ToString("0.00", CultureInfo.InvariantCulture);
        }
    }
}
