using System.Collections.Generic;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// The in-game camera: taking a photo captures EVERYTHING the placement
    /// frustum frames, including the void, into a regular photo definition,
    /// which then flows through the same pipeline as the static catalog (hold,
    /// raise, rotate, place). An empty frame yields an empty photo of sky:
    /// placed, it pierces the world. <see cref="Capture"/> therefore never
    /// returns null.
    /// <para>
    /// What is photographable: every block of the world (platforms, walls,
    /// crates, placed content) and every battery EXCEPT the leaden ones.
    /// Capture is a COPY: the originals stay where they are. Bars, walls and
    /// glass do not block it, the test is purely geometric, and that is exactly
    /// how a steel cage is beaten: the lens reaches through the bars even
    /// though no placement will ever break them.
    /// </para>
    /// <para>
    /// Blocks are captured BY VOLUME, exactly the way a placement carves them:
    /// the photo keeps the part of the block that falls inside the frame,
    /// clipped, not the whole block. That symmetry is what keeps the ground
    /// under your feet working. A block is often far bigger than the frame (a
    /// 12 m platform whose center is behind the player), so a center test would
    /// never copy it while a placement WOULD carve the framed piece away: the
    /// player would blow a hole in the floor and fall through his own photo.
    /// Capturing the clipped volume means a photo puts back precisely what its
    /// own placement removes.
    /// </para>
    /// <para>
    /// One accepted approximation, documented for the level design: a captured
    /// volume is re-expressed axis-aligned in camera space, so a wall shot at
    /// an angle comes back facing the player.
    /// </para>
    /// <para>
    /// SPACES. The anchor arrives as <c>anchorInverse</c>, a Unity world to
    /// anchor matrix, so every matrix product in this file lands in Unity
    /// anchor space (+z forward). Everything this file PRODUCES goes into a
    /// <see cref="PhotoDef"/>, and the rest of the game reads a PhotoDef as
    /// DESIGN space (-z forward). The mirror is therefore applied once, on the
    /// way out of every matrix multiply, by <see cref="ToDesign"/>, and every
    /// piece of frustum math downstream of it is design space (depth is
    /// <c>-z</c>). This is the single easiest thing to get wrong in the port: a
    /// point that skips the mirror lands behind the camera and vanishes.
    /// </para>
    /// </summary>
    public static class PhotoCapture
    {
        /// <summary>Farthest depth the film reaches, and the erase depth of the shot.</summary>
        public const float CaptureDepth = 12f;

        /// <summary>Nearest depth the film reaches: anything closer is not on the picture.</summary>
        public const float CaptureNear = 0.5f;

        /// <summary>
        /// A captured box at most this big on every axis is loose: it falls when
        /// placed. The test is on the ORIGINAL object, not on the clipped piece:
        /// a corner of ground caught in the frame is still ground, not a falling
        /// crate.
        /// </summary>
        public const float LooseMaxExtent = 1.6f;

        /// <summary>Props kept on one film, the farthest dropped.</summary>
        public const int MaxProps = 32;

        /// <summary>
        /// Visual center of a battery above its base. A battery is a point for
        /// the film, and this is the point tested against the frustum: its
        /// origin sits on the floor, which is often just out of frame. Same
        /// value as the y of the battery body in section 5.4 (a 0.5 m cylinder
        /// whose center sits at 0.35), so the film aims at the body, not at
        /// the floor under it.
        /// </summary>
        private static readonly Vector3 BatteryEyeOffset = new Vector3(0f, 0.35f, 0f);

        /// <summary>
        /// One thing the film could take a picture of. Positions and transforms
        /// are Unity world space; <see cref="Size"/> is the full extents of the
        /// box (sizes are the same in both spaces).
        /// </summary>
        public struct CaptureCandidate
        {
            /// <summary>True for a battery (a point at <see cref="Pos"/>, its base), false for a box.</summary>
            public bool IsBattery;

            /// <summary>Battery only: world position of its BASE.</summary>
            public Vector3 Pos;

            /// <summary>Box only: world matrix of the block, origin at the block center.</summary>
            public Matrix4x4 Xform;

            /// <summary>Box only: full extents of the block.</summary>
            public Vector3 Size;

            /// <summary>Palette key of the box.</summary>
            public string Color;
        }

        /// <summary>
        /// Pure core: the part of a box that lies inside the photo frustum,
        /// expressed in DESIGN camera space as a center and a size. False when
        /// the box is out of frame, and then both outputs are zero.
        /// <para>
        /// <paramref name="toCamera"/> maps the box's own space (origin at its
        /// center) to Unity anchor space; the mirror down to design space is
        /// applied here, on the corners.
        /// </para>
        /// <para>
        /// Analytic, in two cases, because fidelity matters more than anything
        /// else here: a photo has to show the objects at their real place and
        /// their real size.
        /// </para>
        /// <list type="bullet">
        /// <item>The box fits ENTIRELY in the frame (all eight corners inside
        /// the frustum, which is convex, so the whole box is): it is kept AS IT
        /// IS, its own size and its own center. Nothing is estimated.</item>
        /// <item>The box straddles the frame: the copy is the intersection of
        /// its camera-space bounds with the frame, computed exactly (no
        /// sampling, so no grid error and no inflating margin). This is the case
        /// of the ground under the player, which a placement carves and a photo
        /// must therefore restore.</item>
        /// </list>
        /// </summary>
        public static bool ClipToFrustum(Vector3 size, Matrix4x4 toCamera, out Vector3 center, out Vector3 clipped, float far = CaptureDepth)
        {
            center = Vector3.zero;
            clipped = Vector3.zero;

            Vector3 lo = new Vector3(float.PositiveInfinity, float.PositiveInfinity, float.PositiveInfinity);
            Vector3 hi = new Vector3(float.NegativeInfinity, float.NegativeInfinity, float.NegativeInfinity);
            bool fullyFramed = true;

            for (int ix = 0; ix < 2; ix++)
            {
                float sx = ix == 0 ? -0.5f : 0.5f;
                for (int iy = 0; iy < 2; iy++)
                {
                    float sy = iy == 0 ? -0.5f : 0.5f;
                    for (int iz = 0; iz < 2; iz++)
                    {
                        float sz = iz == 0 ? -0.5f : 0.5f;
                        // The eight local corners are symmetric about the box
                        // center, so mirroring the local point would only shuffle
                        // the set. The mirror is applied to the RESULT instead.
                        Vector3 local = new Vector3(size.x * sx, size.y * sy, size.z * sz);
                        Vector3 corner = ToDesign(toCamera.MultiplyPoint3x4(local));
                        lo = Vector3.Min(lo, corner);
                        hi = Vector3.Max(hi, corner);
                        if (!PhotoMath.PointInFrustum(corner, PhotoMath.PhotoFovDeg, PhotoMath.PhotoAspect, CaptureNear, far))
                        {
                            fullyFramed = false;
                        }
                    }
                }
            }

            if (fullyFramed)
            {
                center = ToDesign(toCamera.MultiplyPoint3x4(Vector3.zero));
                clipped = size;
                return true;
            }

            // Depth first: outside the frame's depth range there is nothing to keep.
            lo.z = Mathf.Max(lo.z, -far);
            hi.z = Mathf.Min(hi.z, -CaptureNear);
            if (hi.z <= lo.z)
            {
                return false;
            }

            // Then the frame itself, taken at the deepest point of the piece,
            // where the frame is widest: a photo never holds anything outside its
            // own borders. The deepest kept point is lo.z, since -z is forward.
            float half = PhotoMath.HalfExtentAt(-lo.z, PhotoMath.PhotoFovDeg);
            lo.x = Mathf.Max(lo.x, -half * PhotoMath.PhotoAspect);
            hi.x = Mathf.Min(hi.x, half * PhotoMath.PhotoAspect);
            lo.y = Mathf.Max(lo.y, -half);
            hi.y = Mathf.Min(hi.y, half);
            if (hi.x <= lo.x || hi.y <= lo.y)
            {
                return false;
            }

            center = (lo + hi) * 0.5f;
            clipped = hi - lo;
            return true;
        }

        /// <summary>
        /// Pure core, unit-testable: converts world candidates into photo props,
        /// sorted by increasing depth (closest first) and capped at
        /// <see cref="MaxProps"/>. The returned positions are DESIGN space,
        /// relative to the anchor.
        /// </summary>
        /// <param name="candidates">What the film could see, in world space.</param>
        /// <param name="anchorInverse">World to anchor matrix (Unity space).</param>
        public static List<PhotoProp> PropsFrom(List<CaptureCandidate> candidates, Matrix4x4 anchorInverse)
        {
            List<Entry> entries = new List<Entry>();
            if (candidates != null)
            {
                for (int i = 0; i < candidates.Count; i++)
                {
                    CaptureCandidate candidate = candidates[i];
                    if (candidate.IsBattery)
                    {
                        // A battery is a point: the test uses its visual center.
                        // The y offset is untouched by the z mirror, so it can be
                        // added in world space exactly as the original does.
                        Vector3 eye = ToDesign(anchorInverse.MultiplyPoint3x4(candidate.Pos + BatteryEyeOffset));
                        if (!PhotoMath.PointInFrustum(eye, PhotoMath.PhotoFovDeg, PhotoMath.PhotoAspect, CaptureNear, CaptureDepth))
                        {
                            continue;
                        }
                        PhotoProp batteryProp = new PhotoProp();
                        batteryProp.Kind = "battery";
                        // The prop records the BASE, not the tested visual center.
                        batteryProp.Pos = ToDesign(anchorInverse.MultiplyPoint3x4(candidate.Pos));
                        batteryProp.Size = Vector3.zero;
                        batteryProp.Color = "battery";
                        batteryProp.Loose = false;
                        Append(entries, batteryProp, i);
                    }
                    else
                    {
                        Vector3 center;
                        Vector3 clipped;
                        if (!ClipToFrustum(candidate.Size, anchorInverse * candidate.Xform, out center, out clipped))
                        {
                            continue;
                        }
                        string color = candidate.Color;
                        if (string.IsNullOrEmpty(color))
                        {
                            color = "erasable";
                        }
                        PhotoProp boxProp = new PhotoProp();
                        boxProp.Kind = "box";
                        boxProp.Pos = center;
                        boxProp.Size = clipped;
                        boxProp.Color = color;
                        // Loose follows the ORIGINAL object, not the slice taken of it.
                        boxProp.Loose = candidate.Size.x <= LooseMaxExtent
                            && candidate.Size.y <= LooseMaxExtent
                            && candidate.Size.z <= LooseMaxExtent;
                        Append(entries, boxProp, i);
                    }
                }
            }

            entries.Sort(CompareEntries);

            List<PhotoProp> props = new List<PhotoProp>();
            int kept = entries.Count;
            if (kept > MaxProps)
            {
                kept = MaxProps;
            }
            for (int i = 0; i < kept; i++)
            {
                props.Add(entries[i].Prop);
            }
            return props;
        }

        /// <summary>
        /// Scene glue: collects the photographable objects and assembles a
        /// definition. ALWAYS returns a valid def: props possibly empty, always
        /// a sky backdrop.
        /// <para>
        /// It also fires the shutter presentation on its way out (see
        /// <see cref="AnnounceShutter"/>), because being reached is the exact
        /// definition of "a shot was taken". That call changes nothing about
        /// WHEN anything happens, only what the frame looks like.
        /// </para>
        /// </summary>
        /// <param name="anchorInverse">World to anchor matrix (Unity space).</param>
        public static PhotoDef Capture(Matrix4x4 anchorInverse)
        {
            List<CaptureCandidate> candidates = new List<CaptureCandidate>();

            // Everything the eye sees is photographable, permanent ground
            // included: a picture must show what was framed. Whether a block can
            // be CARVED is a different question, answered by the ground language
            // at placement time.
            List<ErasableBlock> blocks = Groups.Snapshot<ErasableBlock>(Groups.Photographable);
            for (int i = 0; i < blocks.Count; i++)
            {
                ErasableBlock block = blocks[i];
                if (block == null)
                {
                    continue;
                }
                CaptureCandidate boxCandidate = new CaptureCandidate();
                boxCandidate.IsBattery = false;
                // The block transform carries no scale: its extents live in
                // BlockSize alone (section 5.2), which is also what lets the
                // carve sample the same volume from -size/2 to +size/2 in the
                // same local space. Scaling a block would double count its size
                // here, and the copy would stop matching the hole it fills.
                boxCandidate.Xform = block.transform.localToWorldMatrix;
                boxCandidate.Size = block.BlockSize;
                boxCandidate.Color = block.ColorKey;
                candidates.Add(boxCandidate);
            }

            // Cages are deliberately ABSENT from this list, and must stay absent.
            // Bars are a lattice, not a volume: the lens goes through them, and
            // what the film keeps is what stands behind. Copying a cage as a
            // solid block would seal its own copied battery inside, which is the
            // exact opposite of the fantasy ("the bars do not stop the lens") and
            // would make every caged battery useless the moment it was
            // photographed. Do not "fix" this by reading the cage group.
            //
            // Batteries are read from the copyable group only: a leaden battery
            // leaves no trace on the film. That is the one thing in the world the
            // camera cannot see, and the levels are built around it.
            List<Battery> batteries = Groups.Snapshot<Battery>(Groups.CopyableBattery);
            for (int i = 0; i < batteries.Count; i++)
            {
                Battery battery = batteries[i];
                if (battery == null)
                {
                    continue;
                }
                CaptureCandidate batteryCandidate = new CaptureCandidate();
                batteryCandidate.IsBattery = true;
                // A battery's origin is its base (section 5.4).
                batteryCandidate.Pos = battery.transform.position;
                batteryCandidate.Size = Vector3.zero;
                batteryCandidate.Color = "battery";
                candidates.Add(batteryCandidate);
            }

            PhotoDef def = new PhotoDef();
            def.Title = "Cliche";
            def.Hint = "Une photo prise sur le vif. Se pose comme les autres.";
            def.Seal = null;
            def.Props = PropsFrom(candidates, anchorInverse);
            // The sky of a shot is scenery three times past what the film
            // reached, so it never stands in the way of what the shot puts back.
            // The carve stops at CaptureDepth, sealed by the copy itself.
            PhotoBackdrop backdrop = new PhotoBackdrop();
            backdrop.Depth = 36f;
            backdrop.Top = "sky_top";
            backdrop.Bottom = "sky_horizon";
            def.Backdrop = backdrop;
            def.EraseDepth = CaptureDepth;

            // The shutter becomes legible as an EVENT (PRD_VISUAL 4.8
            // V-VFX-06), and this single line is the whole of its trigger. It
            // sits at the end of the scene glue because this method is reached
            // if and only if a shot is really taken: PlayerController refuses a
            // shutter pressed with a full hand, with no film left or outside
            // the viewfinder BEFORE it ever calls in, so a refused trigger
            // never flashes (stage 17 of the probe checks that refusal, and it
            // would be a lie on screen to answer it with a flash).
            //
            // Nothing here waits on the animation, and nothing may. The caller
            // clears the viewfinder, spends the film, registers the definition,
            // fills the hand and raises the picture in the same frame, exactly
            // as it did before this line existed: the two leaves, the white
            // flash frame and the polaroid slide are PRESENTATION and lag
            // nothing but themselves. Stage 18 measures the resulting picture
            // against the world to the centimetre on the very frame of the
            // shot, so a capture that waited for its own animation would not be
            // late, it would be wrong.
            AnnounceShutter();
            return def;
        }

        /// <summary>
        /// Starts the HUD's shutter presentation for a shot that has just been
        /// taken (PRD_VISUAL 4.8 V-VFX-06: the leaves closing, a white flash
        /// frame, then the new polaroid sliding up into the raised position).
        /// <para>
        /// The overlay is looked up rather than injected. <see cref="Main"/>
        /// owns exactly one HUD for the life of the game, a shutter press is a
        /// handful of events per level, so the lookup costs nothing measurable
        /// while a cached reference would only be one more thing to invalidate
        /// across a level load or a domain reload. A null answer is the normal
        /// case for the EditMode tests, which call <see cref="Capture"/> with
        /// no game around it, and for a headless probe.
        /// </para>
        /// <para>
        /// Wrapped, and deliberately so. This is the last thing a capture does,
        /// but it still runs INSIDE the caller: an exception thrown by the
        /// presentation would abandon <c>PlayerController.CapturePhoto</c>
        /// before it consumed the film or put the photo in hand, turning a
        /// cosmetic bug into a game that eats a shutter press. That is the
        /// failure mode the README records for an exception in <c>Awake</c>,
        /// and the answer is the one <c>Main.Step</c> gives it: the broken
        /// subsystem says so out loud and the game keeps working.
        /// </para>
        /// </summary>
        private static void AnnounceShutter()
        {
            Hud hud = UnityEngine.Object.FindAnyObjectByType<Hud>();
            if (hud == null)
            {
                return;
            }
            try
            {
                hud.PlayShutter();
            }
            catch (System.Exception e)
            {
                Debug.LogError("[PhotoCapture] The shutter presentation failed: " + e);
            }
        }

        /// <summary>
        /// Mirrors z, turning a Unity anchor-space point into a design-space one.
        /// The mirror is its own inverse, which is why the one conversion helper
        /// of the project serves both directions.
        /// </summary>
        private static Vector3 ToDesign(Vector3 inAnchor)
        {
            return DesignSpace.ToUnity(inAnchor);
        }

        /// <summary>A prop waiting to be sorted, with its depth and its input rank.</summary>
        private struct Entry
        {
            public PhotoProp Prop;
            public float Depth;
            public int Order;
        }

        private static void Append(List<Entry> entries, PhotoProp prop, int order)
        {
            Entry entry = new Entry();
            entry.Prop = prop;
            // -z is forward in design space, so depth is -pos.z.
            entry.Depth = -prop.Pos.z;
            entry.Order = order;
            entries.Add(entry);
        }

        /// <summary>
        /// Closest first. The input rank breaks ties so the cap always drops the
        /// same props: List.Sort is not stable on its own, and the same shot
        /// taken twice must give the same photo.
        /// </summary>
        private static int CompareEntries(Entry a, Entry b)
        {
            if (a.Depth < b.Depth)
            {
                return -1;
            }
            if (a.Depth > b.Depth)
            {
                return 1;
            }
            if (a.Order < b.Order)
            {
                return -1;
            }
            if (a.Order > b.Order)
            {
                return 1;
            }
            return 0;
        }
    }
}
