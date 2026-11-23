using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// First-time tips (idea 3, docs/next/progress/TIPS.md): one short sentence on a dark plate above the HUD band, with a
    /// small amber chevron bobbing over the HUD element it talks about (the eye, a gauge) or over a world spot (the rug the
    /// furniture stands on, the nearby decoy). Built by <see cref="Hud.Init"/> as a nested Canvas of the HUD.
    ///
    /// Triggers, read after every fixed step (<see cref="GameState.FixedStepped"/>, so the step's state is final) and only
    /// while the level runs (started, playing): the freeze tip when the furniture moves and a human watcher's cone turns
    /// toward it (or the caught rule's grace already runs); the eye tip when the eye opens calm (seen, still); the creak
    /// tip on the first creak warning; the suspicion tip on the first rise of the highest suspicion; the rug tip the first
    /// time the furniture stands on a rug; the decoy tip the first time a decoy of its kind is within reach (level 3). Each
    /// tip has the levels it may show on (<see cref="TipDef"/>) and shows once per save: SaveData.Tips holds the keys, the
    /// entry is written once the tip was shown for <see cref="TipDef.MinSeconds"/> (a tip cut short comes back).
    ///
    /// Never blocks input: the dismissal reads the devices directly (a new press after MinSeconds) and consumes nothing.
    /// Pause-safe: the plate hides and its clock stops while paused, under a menu or an end panel. Never before the
    /// player's first input (GameState.Started: since AUTOSTART the world steps under the title card, but the furniture is
    /// out of play there, so nothing a tip talks about can happen). A new level or a restart clears the plate.
    /// </summary>
    public sealed class Tips : MonoBehaviour
    {
        /// <summary>Tests force the tips on or off; null uses <see cref="DefaultEnabled"/>.</summary>
        public static bool? EnabledOverride;

        /// <summary>On in a player and in editor play; off under --probe and --look, whose shots and steps never expect a plate.</summary>
        public static bool DefaultEnabled => !(Probe.Requested || SaveStore.LookRequested);

        public static bool Enabled => EnabledOverride ?? DefaultEnabled;

        /// <summary>The key of the tip on screen (fading out included), or null.</summary>
        public string ShownKey => shown != null ? shown.Key : null;

        /// <summary>The sentence as shown (tokens resolved), or null.</summary>
        public string ShownText => shown != null && line != null ? line.text : null;

        /// <summary>The plate is drawn now (its Canvas on, not faded out).</summary>
        public bool Visible => shown != null && canvas != null && canvas.enabled && group != null && group.alpha > 0.01f;

        /// <summary>The shown tip was counted as shown (written to the save).</summary>
        public bool Committed { get; private set; }

        /// <summary>Unscaled seconds the shown tip has been drawn (pauses excluded).</summary>
        public float ShownSeconds { get; private set; }

        /// <summary>Tips committed since the HUD was built (tests).</summary>
        public int CommittedCount { get; private set; }

        /// <summary>The chevron's centre in screen pixels (tests), valid while <see cref="PointerVisible"/>.</summary>
        public Vector2 PointerScreen { get; private set; }

        /// <summary>The chevron is drawn (a world spot off screen hides it, the plate stays).</summary>
        public bool PointerVisible => Visible && pointer != null && pointer.enabled;

        /// <summary>Why the last <see cref="Trigger"/> refused, or null when it showed (tests).</summary>
        public string LastRefusal { get; private set; }

        // Layout in reference pixels (1920 x 1080, the HUD's scaler): the plate's bottom row (above the sat-on row at
        // 222 + 76), the plate's padding and widest text, the chevron's size and its bob.
        private const float RowY = 312f;
        private const float PadX = 34f;
        private const float PadY = 14f;
        private const float MaxTextWidth = 1100f;
        private const float EdgeMargin = 24f;
        private const float PointerSize = 44f;
        private const float PointerGap = 10f;
        private const float BobPixels = 6f;
        private const int FontSize = 34;
        private const float FadeIn = 6f;
        private const float FadeOut = 4f;

        private static readonly Color PlateColor = new Color(0.12f, 0.1f, 0.14f, 0.86f);
        private static readonly Color InkColor = new Color(1f, 0.9f, 0.62f, 1f);
        private static readonly Color PointerColor = new Color(1f, 0.74f, 0.28f, 1f);

        private Hud hud;
        private GameState game;
        private Canvas canvas;
        private CanvasGroup group;
        private RectTransform plate;
        private Text line;
        private Image pointer;
        private RectTransform pointerRect;

        private TipDef shown;
        private Vector3 worldAnchor;
        private bool dismissing;
        private Hud.HintDevice shownDevice;
        private string shownLanguage;

        // Trackers of the fixed step rules: one previous angle per inhabitant, the last eye, warning and suspicion, and
        // which level build they belong to.
        private float[] previousAngles = new float[0];
        private HudEye lastEye = HudEye.Closed;
        private bool lastWarning;
        private float lastSuspicion;
        private string trackedLevel;
        private int trackedRestarts = -1;
        private readonly Vector3[] corners = new Vector3[4];

        /// <summary>Builds the component and its Canvas under the HUD (called once by Hud.Init).</summary>
        public static Tips Build(Hud hud)
        {
            var go = new GameObject("Tips", typeof(RectTransform));
            go.transform.SetParent(hud.transform, false);
            var rect = (RectTransform)go.transform;
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
            Tips tips = go.AddComponent<Tips>();
            tips.hud = hud;
            tips.canvas = go.AddComponent<Canvas>();
            tips.group = go.AddComponent<CanvasGroup>();
            tips.group.interactable = false;
            tips.group.blocksRaycasts = false;
            tips.group.alpha = 0f;

            var plateGo = new GameObject("TipPlate", typeof(RectTransform));
            plateGo.transform.SetParent(go.transform, false);
            tips.plate = (RectTransform)plateGo.transform;
            tips.plate.anchorMin = tips.plate.anchorMax = Vector2.zero;
            tips.plate.pivot = new Vector2(0.5f, 0f);
            var plateImage = plateGo.AddComponent<Image>();
            plateImage.sprite = ProceduralArt.Rounded;
            plateImage.type = Image.Type.Sliced;
            plateImage.color = PlateColor;
            plateImage.raycastTarget = false;

            var lineGo = new GameObject("TipLine", typeof(RectTransform));
            lineGo.transform.SetParent(plateGo.transform, false);
            tips.line = lineGo.AddComponent<Text>();
            tips.line.font = hud.Font;
            tips.line.fontSize = FontSize;
            tips.line.alignment = TextAnchor.MiddleCenter;
            tips.line.color = InkColor;
            tips.line.raycastTarget = false;
            tips.line.horizontalOverflow = HorizontalWrapMode.Wrap;
            tips.line.verticalOverflow = VerticalWrapMode.Overflow;
            // The label always carries a sentence (the built player check refuses an empty label).
            tips.line.text = Strings.Get(TipDef.Eye);
            var shadow = lineGo.AddComponent<Shadow>();
            shadow.effectColor = new Color(0f, 0f, 0f, 0.65f);
            shadow.effectDistance = new Vector2(2f, -3f);
            var lineRect = (RectTransform)lineGo.transform;
            lineRect.anchorMin = lineRect.anchorMax = new Vector2(0.5f, 0.5f);
            lineRect.pivot = new Vector2(0.5f, 0.5f);
            hud.Labels["TipLine"] = tips.line;

            var pointerGo = new GameObject("TipPointer", typeof(RectTransform));
            pointerGo.transform.SetParent(go.transform, false);
            tips.pointerRect = (RectTransform)pointerGo.transform;
            tips.pointerRect.anchorMin = tips.pointerRect.anchorMax = Vector2.zero;
            tips.pointerRect.pivot = new Vector2(0.5f, 0.5f);
            tips.pointerRect.sizeDelta = new Vector2(PointerSize, PointerSize);
            // The chevron sprite points up; turned round it points down at the element.
            tips.pointerRect.localRotation = Quaternion.Euler(0f, 0f, 180f);
            tips.pointer = pointerGo.AddComponent<Image>();
            tips.pointer.sprite = ProceduralArt.Chevron;
            tips.pointer.color = PointerColor;
            tips.pointer.raycastTarget = false;

            tips.canvas.enabled = false;
            return tips;
        }

        /// <summary>Hud.ShowLevel: a new level or a restart drops the plate and forgets the step trackers.</summary>
        public void OnLevelShown()
        {
            Clear();
            ResetTrackers();
        }

        /// <summary>Hud.Relocalize: the shown sentence in the new language.</summary>
        public void Relocalize()
        {
            if (shown != null)
            {
                SetText();
            }
        }

        /// <summary>Drops the shown tip at once (no fade), committing nothing more.</summary>
        public void Clear()
        {
            shown = null;
            dismissing = false;
            Committed = false;
            ShownSeconds = 0f;
            if (group != null)
            {
                group.alpha = 0f;
            }
            if (canvas != null)
            {
                canvas.enabled = false;
            }
        }

        /// <summary>The shown tip starts its fade out now (an input, the timer, or a test).</summary>
        public void Dismiss()
        {
            if (shown != null)
            {
                dismissing = true;
            }
        }

        /// <summary>The save already holds this tip.</summary>
        public static bool ShownInSave(string key)
        {
            SaveData data = SaveStore.Current;
            return data != null && data.Tips != null && data.Tips.Contains(key);
        }

        /// <summary>
        /// Asks for a tip (the step rules call this; tests too). Refused, with <see cref="LastRefusal"/> set, when the tips are
        /// off, no level runs, the key is unknown, the tip does not apply to the level, the save holds it, or another tip is
        /// on screen (the freeze tip replaces the eye tip: it is the one that matters). <paramref name="world"/> is the spot
        /// a world tip points at (ignored by the HUD anchors).
        /// </summary>
        public bool Trigger(string key, Vector3 world = default)
        {
            LastRefusal = null;
            if (!Enabled)
            {
                return Refuse("tips off");
            }
            if (game == null || game.Level == null || game.Def == null || game.State != PlayState.Playing || !game.Started)
            {
                return Refuse("no running level");
            }
            TipDef tip = TipDef.Find(key);
            if (tip == null)
            {
                return Refuse("unknown tip " + key);
            }
            if (!tip.AppliesTo(game.Def.Id))
            {
                return Refuse(key + " does not apply to " + game.Def.Id);
            }
            if (ShownInSave(key))
            {
                return Refuse(key + " already shown in this save");
            }
            if (shown != null)
            {
                bool preempt = key == TipDef.Freeze && shown.Key == TipDef.Eye && !dismissing && !Committed;
                if (!preempt)
                {
                    return Refuse(shown.Key + " is on screen");
                }
            }
            shown = tip;
            worldAnchor = world;
            dismissing = false;
            Committed = false;
            ShownSeconds = 0f;
            group.alpha = 0f;
            SetText();
            Layout();
            return true;
        }

        private bool Refuse(string why)
        {
            LastRefusal = why;
            return false;
        }

        private void OnDestroy()
        {
            if (game != null)
            {
                game.FixedStepped -= OnFixedStepped;
            }
        }

        private void Update()
        {
            if (hud == null)
            {
                return;
            }
            if (game != hud.Game)
            {
                if (game != null)
                {
                    game.FixedStepped -= OnFixedStepped;
                }
                game = hud.Game;
                if (game != null)
                {
                    game.FixedStepped += OnFixedStepped;
                }
                ResetTrackers();
            }
            if (shown == null)
            {
                return;
            }
            bool drawable = hud.Visible && !GamePause.IsPaused && game != null && game.State == PlayState.Playing
                && !hud.FailVisible && !hud.WinVisible;
            if (!drawable)
            {
                // Hidden under a menu, a pause or an end panel; the clock stops. An end panel drops the tip for good: its
                // level is over (a restart shows a fresh card anyway).
                if (canvas.enabled)
                {
                    canvas.enabled = false;
                }
                if (game != null && game.State != PlayState.Playing)
                {
                    Clear();
                }
                return;
            }
            if (!canvas.enabled)
            {
                canvas.enabled = true;
            }
            if (shownDevice != hud.Device || shownLanguage != Strings.Language)
            {
                SetText();
            }
            float dt = Time.unscaledDeltaTime;
            if (dismissing)
            {
                group.alpha = Mathf.MoveTowards(group.alpha, 0f, dt * FadeOut);
                if (group.alpha <= 0f)
                {
                    Clear();
                    return;
                }
            }
            else
            {
                ShownSeconds += dt;
                group.alpha = Mathf.MoveTowards(group.alpha, 1f, dt * FadeIn);
                if (!Committed && ShownSeconds >= TipDef.MinSeconds)
                {
                    Commit();
                }
                if (ShownSeconds >= TipDef.ShowSeconds || (ShownSeconds >= TipDef.MinSeconds && RawPress()))
                {
                    dismissing = true;
                }
            }
            Layout();
        }

        /// <summary>Writes the shown tip to the save (once per save), so it never shows again.</summary>
        private void Commit()
        {
            Committed = true;
            CommittedCount++;
            SaveData data = SaveStore.Current;
            if (data == null)
            {
                return;
            }
            if (data.Tips == null)
            {
                data.Tips = new List<string>();
            }
            if (!data.Tips.Contains(shown.Key))
            {
                data.Tips.Add(shown.Key);
                SaveStore.Save();
            }
        }

        /// <summary>A new press on any device this frame, read without consuming anything (InputReader's latches untouched).</summary>
        private static bool RawPress()
        {
            Keyboard k = Keyboard.current;
            if (k != null && k.anyKey.wasPressedThisFrame)
            {
                return true;
            }
            Gamepad g = Gamepad.current;
            if (g != null && (g.buttonSouth.wasPressedThisFrame || g.buttonWest.wasPressedThisFrame || g.buttonEast.wasPressedThisFrame
                || g.buttonNorth.wasPressedThisFrame || g.startButton.wasPressedThisFrame))
            {
                return true;
            }
            Touchscreen t = Touchscreen.current;
            return t != null && t.primaryTouch.press.wasPressedThisFrame;
        }

        /// <summary>The sentence for the current language and device: {move} from tips.move.*, then {action}/{careful} as the HUD does.</summary>
        private void SetText()
        {
            if (shown == null || line == null)
            {
                return;
            }
            shownDevice = hud.Device;
            shownLanguage = Strings.Language;
            string device = shownDevice == Hud.HintDevice.Gamepad ? "gamepad" : shownDevice == Hud.HintDevice.Touch ? "touch" : "keyboard";
            string text = Strings.Get(shown.Key).Replace(TipDef.MoveToken, Strings.Get(TipDef.MoveKey(device)));
            line.text = Hud.ResolveHintTokens(text, shownDevice);
            // Measure: the unwrapped width first, then the wrapped height at the width kept.
            var lineRect = (RectTransform)line.transform;
            lineRect.sizeDelta = new Vector2(MaxTextWidth, 0f);
            float width = Mathf.Min(MaxTextWidth, line.preferredWidth + 4f);
            lineRect.sizeDelta = new Vector2(width, 0f);
            float height = Mathf.Max(FontSize * 1.2f, line.preferredHeight);
            lineRect.sizeDelta = new Vector2(width, height);
            plate.sizeDelta = new Vector2(width + 2f * PadX, height + 2f * PadY);
        }

        /// <summary>One frame of placement: the plate on its row under the anchor's x, the chevron bobbing over the anchor.</summary>
        private void Layout()
        {
            if (shown == null || hud == null)
            {
                return;
            }
            float scale = hud.ScaleFactor > 0f ? hud.ScaleFactor : 1f;
            Vector2 size = ((RectTransform)hud.transform).rect.size;
            Vector2 target;
            bool pointerOn = true;
            float plateY = RowY;
            switch (shown.Anchor)
            {
                case TipAnchor.CreakGauge:
                    target = TopCentre(hud.CreakAnchor, scale, out pointerOn);
                    break;
                case TipAnchor.SuspicionGauge:
                    target = TopCentre(hud.SuspicionAnchor, scale, out pointerOn);
                    break;
                case TipAnchor.World:
                    target = Project(worldAnchor, scale, size, out pointerOn);
                    // The plate rides above a spot that is low on screen, so it never covers what it points at.
                    plateY = Mathf.Clamp(target.y + PointerSize + PointerGap + 12f, RowY, size.y - plate.sizeDelta.y - EdgeMargin);
                    if (!pointerOn)
                    {
                        target = new Vector2(size.x * 0.5f, RowY);
                        plateY = RowY;
                    }
                    break;
                default:
                    target = TopCentre(hud.EyeAnchor, scale, out pointerOn);
                    break;
            }
            float halfWidth = plate.sizeDelta.x * 0.5f;
            float x = Mathf.Clamp(target.x, halfWidth + EdgeMargin, Mathf.Max(halfWidth + EdgeMargin, size.x - halfWidth - EdgeMargin));
            plate.anchoredPosition = new Vector2(x, plateY);
            pointer.enabled = pointerOn;
            if (pointerOn)
            {
                float bob = BobPixels * (0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 5f));
                var at = new Vector2(target.x, target.y + PointerGap + PointerSize * 0.5f + bob);
                pointerRect.anchoredPosition = at;
                PointerScreen = at * scale;
            }
        }

        /// <summary>The top centre of a HUD RectTransform in reference pixels from the screen's bottom left.</summary>
        private Vector2 TopCentre(RectTransform rect, float scale, out bool valid)
        {
            valid = rect != null;
            if (!valid)
            {
                return new Vector2(((RectTransform)hud.transform).rect.width * 0.5f, RowY);
            }
            rect.GetWorldCorners(corners);
            // In a Screen Space Overlay canvas the corners are screen pixels: 0 bottom left, 1 top left, 2 top right.
            float x = (corners[1].x + corners[2].x) * 0.5f / scale;
            float y = Mathf.Max(corners[1].y, corners[2].y) / scale;
            return new Vector2(x, y);
        }

        /// <summary>A world spot in reference pixels; off screen or behind the camera, the pointer is not drawn.</summary>
        private Vector2 Project(Vector3 world, float scale, Vector2 size, out bool onScreen)
        {
            if (hud.View == null)
            {
                onScreen = false;
                return Vector2.zero;
            }
            Vector3 sp = hud.View.WorldToScreenPoint(world);
            var p = new Vector2(sp.x, sp.y) / scale;
            onScreen = sp.z > 0f && p.x >= 0f && p.x <= size.x && p.y >= 0f && p.y <= size.y;
            return p;
        }

        private void ResetTrackers()
        {
            previousAngles = new float[0];
            lastEye = HudEye.Closed;
            lastWarning = false;
            lastSuspicion = 0f;
            trackedLevel = game != null && game.Def != null ? game.Def.Id : null;
            trackedRestarts = game != null ? game.Restarts : -1;
        }

        /// <summary>After every fixed step: the situations of the six tips, in the precedence of <see cref="TipDef.All"/>.</summary>
        private void OnFixedStepped()
        {
            if (!Enabled || game == null || game.Level == null || game.Def == null)
            {
                return;
            }
            if (game.Def.Id != trackedLevel || game.Restarts != trackedRestarts)
            {
                ResetTrackers();
            }
            FurnitureController f = game.Furniture;
            if (f == null || game.State != PlayState.Playing || !game.Started)
            {
                return;
            }
            GameRules rules = game.Rules ?? GameRules.M1;
            bool free = !f.Carried && !f.Hidden && !f.Pinned;
            bool moving = game.FurnitureMoving && free;

            // Freeze: moving while a human cone turns this way, or already seen moving (the grace runs).
            bool turning = ConeTurningToward(f);
            if (moving && (game.SeenMoving > 0f || turning))
            {
                Trigger(TipDef.Freeze);
            }

            // Creak: the first warning.
            bool warning = rules.Creak && game.Creak.Warning && free;
            if (warning && !lastWarning)
            {
                Trigger(TipDef.Creak);
            }
            lastWarning = warning;

            // Suspicion: the first rise of the highest suspicion.
            float suspicion = game.MaxSuspicion;
            if (rules.DisplacementMemory && suspicion > 0.005f && suspicion > lastSuspicion + 1e-4f)
            {
                Trigger(TipDef.Suspicion);
            }
            lastSuspicion = suspicion;

            // Decoy: a decoy of the furniture's kind within reach (level 3), pointed at.
            if (rules.DisplacementMemory && free && NearestSameKindDecoy(f, out Vector3 decoyAt))
            {
                Trigger(TipDef.Decoy, decoyAt);
            }

            // Rug: the furniture stands on a rug, pointed at its centre.
            if (free && RugUnder(f, out Vector3 rugAt))
            {
                Trigger(TipDef.Rug, rugAt);
            }

            // Eye: it opened calm (seen, still: nothing happens).
            HudEye eye = game.EyeState;
            if (eye == HudEye.Calm && lastEye == HudEye.Closed && !moving)
            {
                Trigger(TipDef.Eye);
            }
            lastEye = eye;
        }

        /// <summary>
        /// A human watcher (counts for the catch, awake) within <see cref="TipDef.ApproachRangeFactor"/> of its range whose eye
        /// forward turned toward the furniture since the previous step (<see cref="TipDef.ConeTurnsToward"/>).
        /// </summary>
        private bool ConeTurningToward(FurnitureController f)
        {
            List<Inhabitant> inhabitants = game.Level.Inhabitants;
            if (previousAngles.Length != inhabitants.Count)
            {
                previousAngles = new float[inhabitants.Count];
                for (int i = 0; i < previousAngles.Length; i++)
                {
                    previousAngles[i] = 999f;
                }
            }
            bool turning = false;
            Vector3 at = f.transform.position;
            for (int i = 0; i < inhabitants.Count; i++)
            {
                Inhabitant h = inhabitants[i];
                InhabitantRoutine r = h != null ? h.Routine : null;
                PersonalityDef p = h != null ? h.Personality : null;
                if (r == null || p == null || !p.CountsForCatch || r.Asleep)
                {
                    previousAngles[i] = 999f;
                    continue;
                }
                Vector3 eye = r.EyePosition;
                var to = new Vector2(at.x - eye.x, at.z - eye.z);
                float distance = to.magnitude;
                Vector3 forward = r.EyeForward;
                float angle = distance > 1e-4f ? Vector2.Angle(new Vector2(forward.x, forward.z), to) : 0f;
                if (distance <= r.ViewRange * TipDef.ApproachRangeFactor && TipDef.ConeTurnsToward(angle, previousAngles[i], r.HalfAngle))
                {
                    turning = true;
                }
                previousAngles[i] = angle;
            }
            return turning;
        }

        /// <summary>The nearest decoy of the furniture's kind within <see cref="TipDef.DecoyNearMetres"/> (planar), a little above its floor.</summary>
        private bool NearestSameKindDecoy(FurnitureController f, out Vector3 at)
        {
            at = Vector3.zero;
            float best = TipDef.DecoyNearMetres;
            bool found = false;
            Vector3 here = f.transform.position;
            foreach (Decoy decoy in game.Level.Decoys)
            {
                if (decoy == null || !string.Equals(decoy.Kind, f.Kind, System.StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }
                Vector3 pos = decoy.Pose.Position;
                float distance = new Vector2(pos.x - here.x, pos.z - here.z).magnitude;
                if (distance <= best)
                {
                    best = distance;
                    at = new Vector3(pos.x, pos.y + decoy.Size.y, pos.z);
                    found = true;
                }
            }
            return found;
        }

        /// <summary>The rug the furniture's centre stands on (a soft room is not a rug), pointed at its centre on the floor.</summary>
        private bool RugUnder(FurnitureController f, out Vector3 at)
        {
            at = Vector3.zero;
            LevelDef def = game.Def;
            if (def.Rugs == null)
            {
                return false;
            }
            Vector3 here = f.transform.position;
            foreach (RugDef rug in def.Rugs)
            {
                if (rug != null && rug.Contains(here))
                {
                    at = new Vector3(rug.X, def.FloorHeightAt(rug.X, rug.Z) + 0.05f, rug.Z);
                    return true;
                }
            }
            return false;
        }
    }
}
