using System;
using System.Collections.Generic;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// The catalog of every photo in the game (PRD 6.3), the registry of the
    /// photos taken in game (cliche_N), the prop expansion of PRD 6.2 and the
    /// computed polaroid thumbnail of PRD 6.9.
    ///
    /// A photo is pure data: props expressed in photo space (x right, y up,
    /// -z forward, origin at the eye of the placer). The same expansion feeds the
    /// thumbnail, the offscreen snap and the 3D materialization, so what the
    /// picture shows is what gets built.
    ///
    /// Everything here stays in DESIGN space: the z mirror belongs to
    /// DesignSpace.ToUnity, where PhotoContent sets a local position.
    /// </summary>
    public static class PhotoDefs
    {
        public const int ThumbSize = 256;

        /// Square picture area inside the polaroid frame, in pixels, measured from
        /// the TOP of the image like the original Image (PRD 6.9).
        public const int ThumbInnerX = 24;
        public const int ThumbInnerY = 16;
        public const int ThumbInnerSize = 208;

        const int StairSteps = 8;

        static Dictionary<string, PhotoDef> _catalog;
        static string[] _catalogIds;

        /// Photos taken in game with the camera (PRD 7.2): same shape as the static
        /// catalog, registered under cliche_N ids. They live for one level only.
        static readonly Dictionary<string, PhotoDef> _dynamic = new Dictionary<string, PhotoDef>();
        static int _dynamicCounter;

        static readonly Dictionary<string, Texture2D> _thumbCache = new Dictionary<string, Texture2D>();

        static void EnsureLoaded()
        {
            if (_catalog != null)
            {
                return;
            }
            _catalog = PhotoJson.LoadPhotos();
            List<string> ids = new List<string>(_catalog.Keys);
            // Ordinal so the order is the same on every machine, like the original
            // PackedStringArray.sort().
            ids.Sort(StringComparer.Ordinal);
            _catalogIds = ids.ToArray();
        }

        /// <summary>Static catalog only, sorted: the level data and the tests enumerate these.</summary>
        public static string[] AllIds()
        {
            EnsureLoaded();
            return (string[])_catalogIds.Clone();
        }

        /// <summary>The definition behind an id, dynamic first, or null when unknown.</summary>
        public static PhotoDef GetDef(string id)
        {
            if (id == null)
            {
                return null;
            }
            PhotoDef def;
            if (_dynamic.TryGetValue(id, out def))
            {
                return def;
            }
            EnsureLoaded();
            if (_catalog.TryGetValue(id, out def))
            {
                return def;
            }
            return null;
        }

        /// <summary>Registers a photo taken in game and returns its cliche_N id.</summary>
        public static string RegisterDynamic(PhotoDef def)
        {
            if (def == null)
            {
                throw new ArgumentNullException("def");
            }
            // The counter is never reset: two shots of the same level, and two
            // shots either side of a ClearDynamic, must never share an id.
            _dynamicCounter++;
            string id = "cliche_" + _dynamicCounter;
            _dynamic[id] = def;
            return id;
        }

        /// <summary>Drops every photo taken in game, and their cached thumbnails.</summary>
        public static void ClearDynamic()
        {
            foreach (string id in _dynamic.Keys)
            {
                _thumbCache.Remove(id);
            }
            _dynamic.Clear();
        }

        /// <summary>How many real batteries materialize when this photo is placed.</summary>
        public static int BatteryCount(string id)
        {
            PhotoDef def = GetDef(id);
            if (def == null || def.Props == null)
            {
                return 0;
            }
            int total = 0;
            for (int i = 0; i < def.Props.Count; i++)
            {
                if (def.Props[i].Kind == "battery")
                {
                    total++;
                }
            }
            return total;
        }

        /// <summary>
        /// Batteries reachable through this photo, following nested photo props
        /// (photo in photo chains). The visited set guards against catalog cycles.
        /// </summary>
        public static int BatteryCountRecursive(string id, HashSet<string> visited = null)
        {
            if (visited == null)
            {
                visited = new HashSet<string>();
            }
            if (!visited.Add(id))
            {
                return 0;
            }
            int total = BatteryCount(id);
            PhotoDef def = GetDef(id);
            if (def == null || def.Props == null)
            {
                return total;
            }
            for (int i = 0; i < def.Props.Count; i++)
            {
                PhotoProp prop = def.Props[i];
                if (prop.Kind == "photo")
                {
                    total += BatteryCountRecursive(prop.Id, visited);
                }
            }
            return total;
        }

        // ----------------------------------------------------------- expansion

        /// <summary>
        /// Expands one authored prop into elementary primitives (PRD 6.2).
        /// An unknown kind warns and yields nothing.
        /// </summary>
        public static List<Primitive> ExpandProp(PhotoProp prop)
        {
            List<Primitive> result = new List<Primitive>();
            if (prop == null)
            {
                return result;
            }
            Vector3 pos = prop.Pos;
            Vector3 size = prop.Size;
            string color = string.IsNullOrEmpty(prop.Color) ? "stone" : prop.Color;

            switch (prop.Kind)
            {
                case "box":
                case "cylinder":
                    // Only a box can be loose: a loose cylinder has no meaning in the data.
                    result.Add(Prim(prop.Kind, pos, size, color, prop.Kind == "box" && prop.Loose, null));
                    return result;

                case "battery":
                    // pos is the BASE of the battery, the primitive is its center.
                    result.Add(Prim("battery", pos + new Vector3(0f, 0.35f, 0f),
                        new Vector3(0.36f, 0.7f, 0.36f), "battery", false, null));
                    return result;

                case "photo":
                    result.Add(Prim("photo_item", pos, new Vector3(0.72f, 0.82f, 0.06f), "frame", false, prop.Id));
                    return result;

                case "bridge":
                {
                    float railY = pos.y + size.y * 0.5f + 0.4f;
                    result.Add(Prim("box", pos, size, color, false, null));
                    result.Add(Prim("box", new Vector3(pos.x - size.x * 0.5f + 0.05f, railY, pos.z),
                        new Vector3(0.1f, 0.8f, size.z), "wood_dark", false, null));
                    result.Add(Prim("box", new Vector3(pos.x + size.x * 0.5f - 0.05f, railY, pos.z),
                        new Vector3(0.1f, 0.8f, size.z), "wood_dark", false, null));
                    return result;
                }

                case "stairs":
                {
                    // Eight steps rising away from the camera. Each step is a full
                    // pillar from the ground to its own top, not a slab, so the
                    // flight is solid from below. Steps never inherit "loose".
                    float stepH = size.y / StairSteps;
                    float stepD = size.z / StairSteps;
                    for (int i = 0; i < StairSteps; i++)
                    {
                        float top = (i + 1) * stepH;
                        result.Add(Prim("box",
                            new Vector3(pos.x, pos.y + top * 0.5f, pos.z - (i + 0.5f) * stepD),
                            new Vector3(size.x, top, stepD), color, false, null));
                    }
                    return result;
                }

                case "arch":
                {
                    float columnH = size.y - 0.4f;
                    result.Add(Prim("box", new Vector3(pos.x - size.x * 0.5f + 0.25f, pos.y + columnH * 0.5f, pos.z),
                        new Vector3(0.5f, columnH, size.z), color, false, null));
                    result.Add(Prim("box", new Vector3(pos.x + size.x * 0.5f - 0.25f, pos.y + columnH * 0.5f, pos.z),
                        new Vector3(0.5f, columnH, size.z), color, false, null));
                    result.Add(Prim("box", new Vector3(pos.x, pos.y + size.y - 0.2f, pos.z),
                        new Vector3(size.x, 0.4f, size.z), color, false, null));
                    return result;
                }
            }

            Debug.LogWarning("PhotoDefs: unknown prop kind '" + prop.Kind + "'");
            return result;
        }

        /// <summary>Concatenates the expansion of every prop of a definition.</summary>
        public static List<Primitive> ExpandProps(PhotoDef def)
        {
            List<Primitive> result = new List<Primitive>();
            if (def == null || def.Props == null)
            {
                return result;
            }
            for (int i = 0; i < def.Props.Count; i++)
            {
                result.AddRange(ExpandProp(def.Props[i]));
            }
            return result;
        }

        static Primitive Prim(string kind, Vector3 center, Vector3 size, string color, bool loose, string photoId)
        {
            Primitive prim = new Primitive();
            prim.Kind = kind;
            prim.Center = center;
            prim.Size = size;
            prim.Color = color;
            prim.Loose = loose;
            prim.PhotoId = photoId;
            return prim;
        }

        // ----------------------------------------------------------- thumbnail

        /// <summary>
        /// Computed polaroid picture of the photo content: pinhole projection of
        /// every primitive onto the photo plane, painter sorted back to front.
        /// Pure, deterministic, cached; the fallback under a headless run.
        /// </summary>
        public static Texture2D Thumbnail(string id)
        {
            string key = id ?? string.Empty;
            Texture2D cached;
            if (_thumbCache.TryGetValue(key, out cached) && cached != null)
            {
                return cached;
            }

            // The picture is painted in IMAGE space (row 0 at the top), like the
            // original Image, and the rows are flipped once when the texture is
            // filled, because a Unity Texture2D stores row 0 at the bottom.
            Color32[] pixels = new Color32[ThumbSize * ThumbSize];
            FillRect(pixels, 0, 0, ThumbSize, ThumbSize, Palette.Get("frame"));

            PhotoDef def = GetDef(key);
            string topKey = "sky_top";
            string bottomKey = "sky_horizon";
            if (def != null && def.Backdrop != null)
            {
                topKey = def.Backdrop.Top;
                bottomKey = def.Backdrop.Bottom;
            }
            Color topColor = Palette.Get(topKey);
            Color bottomColor = Palette.Get(bottomKey);
            for (int y = 0; y < ThumbInnerSize; y++)
            {
                Color rowColor = Color.Lerp(topColor, bottomColor, (float)y / (ThumbInnerSize - 1));
                FillRect(pixels, ThumbInnerX, ThumbInnerY + y, ThumbInnerSize, 1, rowColor);
            }

            List<Primitive> prims = ExpandProps(def);
            prims.Sort(CompareByDepth);
            for (int i = 0; i < prims.Count; i++)
            {
                DrawPrimitive(pixels, prims[i]);
            }

            Texture2D texture = new Texture2D(ThumbSize, ThumbSize, TextureFormat.RGBA32, false);
            texture.name = "thumb_" + key;
            texture.filterMode = FilterMode.Point;
            texture.wrapMode = TextureWrapMode.Clamp;
            Color32[] flipped = new Color32[pixels.Length];
            for (int y = 0; y < ThumbSize; y++)
            {
                int source = y * ThumbSize;
                int target = (ThumbSize - 1 - y) * ThumbSize;
                for (int x = 0; x < ThumbSize; x++)
                {
                    flipped[target + x] = pixels[source + x];
                }
            }
            texture.SetPixels32(flipped);
            texture.Apply();

            _thumbCache[key] = texture;
            return texture;
        }

        /// Back to front: the most negative z is the furthest away and is painted first.
        static int CompareByDepth(Primitive a, Primitive b)
        {
            return a.Center.z.CompareTo(b.Center.z);
        }

        static void DrawPrimitive(Color32[] pixels, Primitive prim)
        {
            Vector3 center = prim.Center;
            Vector3 size = prim.Size;

            float loX = float.PositiveInfinity;
            float loY = float.PositiveInfinity;
            float hiX = float.NegativeInfinity;
            float hiY = float.NegativeInfinity;
            for (int ix = 0; ix < 2; ix++)
            {
                for (int iy = 0; iy < 2; iy++)
                {
                    for (int iz = 0; iz < 2; iz++)
                    {
                        Vector3 corner = center + new Vector3(
                            size.x * (ix == 0 ? -0.5f : 0.5f),
                            size.y * (iy == 0 ? -0.5f : 0.5f),
                            size.z * (iz == 0 ? -0.5f : 0.5f));
                        // A corner at or behind the pinhole has no projection.
                        if (corner.z > -0.05f)
                        {
                            continue;
                        }
                        Vector2 projected = PhotoMath.ProjectPoint(corner, PhotoMath.PhotoFovDeg, PhotoMath.PhotoAspect);
                        loX = Mathf.Min(loX, projected.x);
                        loY = Mathf.Min(loY, projected.y);
                        hiX = Mathf.Max(hiX, projected.x);
                        hiY = Mathf.Max(hiY, projected.y);
                    }
                }
            }
            if (loX > hiX)
            {
                return;
            }

            // Normalized [-1, 1] with y up, to pixels inside the picture area with
            // y down (the original _to_pixels).
            int x0 = ToPixelX(loX);
            int x1 = ToPixelX(hiX);
            int y0 = ToPixelY(hiY);
            int y1 = ToPixelY(loY);
            int width = Mathf.Max(x1 - x0, 1);
            int height = Mathf.Max(y1 - y0, 1);

            int clipX0 = Mathf.Max(x0, ThumbInnerX);
            int clipY0 = Mathf.Max(y0, ThumbInnerY);
            int clipX1 = Mathf.Min(x0 + width, ThumbInnerX + ThumbInnerSize);
            int clipY1 = Mathf.Min(y0 + height, ThumbInnerY + ThumbInnerSize);
            if (clipX1 <= clipX0 || clipY1 <= clipY0)
            {
                return;
            }
            int rectW = clipX1 - clipX0;
            int rectH = clipY1 - clipY0;

            float depth = Mathf.Clamp(-center.z / 16f, 0f, 0.35f);
            Color color = Darken(Palette.Get(prim.Color), depth);

            if (prim.Kind == "battery")
            {
                int tipH = Mathf.Max((int)(rectH * 0.2f), 1);
                if (tipH > rectH)
                {
                    tipH = rectH;
                }
                FillRect(pixels, clipX0, clipY0, rectW, tipH, Palette.Get("battery_tip"));
                if (rectH > tipH)
                {
                    FillRect(pixels, clipX0, clipY0 + tipH, rectW, rectH - tipH, color);
                }
            }
            else if (prim.Kind == "photo_item")
            {
                // A polaroid inside the picture: white frame around a darker inset.
                FillRect(pixels, clipX0, clipY0, rectW, rectH, color);
                int inset = Mathf.Max(rectW / 6, 1);
                int insetW = rectW - inset * 2;
                int insetH = rectH - inset * 2;
                if (insetW > 0 && insetH > 0)
                {
                    FillRect(pixels, clipX0 + inset, clipY0 + inset, insetW, insetH,
                        Darken(Palette.Get("photo_back"), depth));
                }
            }
            else
            {
                FillRect(pixels, clipX0, clipY0, rectW, rectH, color);
            }
        }

        static int ToPixelX(float normalized)
        {
            return ThumbInnerX + Truncate((normalized * 0.5f + 0.5f) * ThumbInnerSize);
        }

        static int ToPixelY(float normalized)
        {
            return ThumbInnerY + Truncate((1f - (normalized * 0.5f + 0.5f)) * ThumbInnerSize);
        }

        /// <summary>
        /// Truncation toward zero of the offset INSIDE the picture area, before the
        /// origin is added: the original rounds the same way and in the same order
        /// (_to_pixels), and for a negative offset the two orders disagree by one
        /// pixel. A corner near the pinhole projects far outside the frame, so the
        /// value is clamped first to keep the cast defined.
        /// </summary>
        static int Truncate(float offset)
        {
            return (int)Mathf.Clamp(offset, -100000f, 100000f);
        }

        /// Distance shading: the palette color pulled toward black, alpha untouched.
        static Color Darken(Color color, float amount)
        {
            Color shaded = Color.Lerp(color, Color.black, amount);
            shaded.a = color.a;
            return shaded;
        }

        /// Fills a rect given in image space (row 0 at the top), clipped to the image.
        static void FillRect(Color32[] pixels, int x, int y, int width, int height, Color color)
        {
            int x0 = Mathf.Max(x, 0);
            int y0 = Mathf.Max(y, 0);
            int x1 = Mathf.Min(x + width, ThumbSize);
            int y1 = Mathf.Min(y + height, ThumbSize);
            Color32 packed = color;
            for (int row = y0; row < y1; row++)
            {
                int offset = row * ThumbSize;
                for (int column = x0; column < x1; column++)
                {
                    pixels[offset + column] = packed;
                }
            }
        }
    }
}
