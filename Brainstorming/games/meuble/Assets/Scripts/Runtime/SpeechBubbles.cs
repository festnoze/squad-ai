using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// Idea 7 (BUBBLES): short comic speech bubbles over the inhabitants' heads (and over a robot that bumps the furniture).
    /// One screen space overlay canvas (sorting order 8: under the HUD's 10, the menus' 50 and the touch controls' 30, over
    /// the world and the world space markers) with a pool of <see cref="PoolSize"/> bubbles built once in
    /// <see cref="Init"/>: no allocation per bubble shown, the text is the Strings table's own instance. A bubble is a cream
    /// rounded plate (ProceduralArt.Rounded) with a small tail (a rotated square under the plate) and one line in the display
    /// font (Hud.DisplayFont, DM Serif), placed every LateUpdate at the projection of the speaker's
    /// <see cref="Inhabitant.BubbleAnchor"/> and clamped inside the screen: a bubble is UI, so a wall never hides it, and it
    /// reads the same on PC and on a phone (the HUD's CanvasScaler). It holds <see cref="Hold"/> seconds, then fades over
    /// <see cref="Fade"/>; at most one bubble per speaker (a new line replaces the one up).
    /// <para>
    /// Triggers: GameState's <see cref="GameState.Reacted"/> and <see cref="GameState.RobotBumped"/> events, and the near miss
    /// detected here from the visions on every fixed step (<see cref="StepNearMiss"/>): a walking inhabitant's cone swept over
    /// the still furniture, then lost it, at most once per <see cref="NearMissCooldown"/> per inhabitant. The station glances
    /// (the sentinel's metronome) never count: the sighting must include a walking step. The line is chosen by a seeded
    /// <see cref="System.Random"/> (<see cref="Seed"/>), so tests are deterministic. Nothing shows on the title house (the
    /// title, the level select, the credits), and the end panels clear every bubble but the catch's own line.
    /// </para>
    /// </summary>
    public sealed class SpeechBubbles : MonoBehaviour
    {
        public const int PoolSize = 8;
        public const int SortingOrder = 8;
        /// <summary>Seconds a bubble stays fully up, then the fade.</summary>
        public const float Hold = 2f;
        public const float Fade = 0.35f;
        /// <summary>The pop in: the bubble scales from PopScale to 1 over PopTime.</summary>
        public const float PopTime = 0.14f;
        public const float PopScale = 0.6f;
        /// <summary>Seconds between two near miss lines of the same inhabitant.</summary>
        public const float NearMissCooldown = 10f;
        /// <summary>A near miss sighting lasts at least this (a real sweep) and at most this (a stare is no near miss).</summary>
        public const float NearMissMinSeen = 0.2f;
        public const float NearMissMaxSeen = 3f;
        /// <summary>Where a robot's bubble points: this high over its centre.</summary>
        public const float RobotLift = 0.5f;

        // Reference units (the HUD's 1920 x 1080 canvas).
        private const float FontSize = 30f;
        private const float PadX = 22f;
        private const float BodyHeight = 58f;
        private const float MinWidth = 96f;
        private const float MaxWidth = 560f;
        private const float TailSize = 22f;
        private const float EdgeMargin = 12f;
        // The bubble's bottom (the tail's tip) sits this far above the projected anchor.
        private const float TailGap = 2f;

        private static readonly Color Cream = new Color(0.985f, 0.96f, 0.89f, 1f);
        private static readonly Color Ink = new Color(0.14f, 0.11f, 0.09f, 1f);

        /// <summary>The seed of the line choice; set it before a level for a deterministic sequence (tests).</summary>
        public static int Seed = 20261120;

        private sealed class Bubble
        {
            public RectTransform Root;
            public CanvasGroup Group;
            public RectTransform Tail;
            public RectTransform Body;
            public Text Label;
            public Inhabitant Who;
            public Robot Robot;
            public ReactionKind Kind;
            public float Age;
            public int Variant = -1;
            public bool Active;
            public bool Caught;

            public bool Speaks(Object who) => Active && (Who == who || Robot == who);
        }

        private GameState game;
        private Canvas canvas;
        private readonly Bubble[] pool = new Bubble[PoolSize];
        private System.Random random;
        private LevelInstance level;
        // Near miss state per inhabitant (parallel to level.Inhabitants): the vision, the steps seen still, whether the
        // sighting included a walking step, and the cooldown left in steps.
        private Vision[] visions = new Vision[0];
        private int[] seenSteps = new int[0];
        private bool[] sweptWalking = new bool[0];
        private int[] cooldown = new int[0];

        /// <summary>Bubbles shown since the level was built (tests).</summary>
        public int ShownCount { get; private set; }

        /// <summary>The kind of the last bubble shown (tests).</summary>
        public ReactionKind LastKind { get; private set; }

        /// <summary>The text of the last bubble shown (tests).</summary>
        public string LastText { get; private set; }

        /// <summary>Near misses shown since the level was built (tests).</summary>
        public int NearMissCount { get; private set; }

        /// <summary>Bubbles up right now (fading ones included).</summary>
        public int ActiveCount
        {
            get
            {
                int n = 0;
                foreach (Bubble b in pool)
                {
                    if (b != null && b.Active)
                    {
                        n++;
                    }
                }
                return n;
            }
        }

        /// <summary>Finds or builds the bubbles of <paramref name="game"/>, as a child of it (GameState calls it once).</summary>
        public static SpeechBubbles Ensure(GameState game)
        {
            if (game == null)
            {
                return null;
            }
            SpeechBubbles existing = game.GetComponentInChildren<SpeechBubbles>(true);
            if (existing != null)
            {
                return existing;
            }
            var go = new GameObject("Bubbles", typeof(RectTransform));
            go.transform.SetParent(game.transform, false);
            SpeechBubbles bubbles = go.AddComponent<SpeechBubbles>();
            bubbles.Init(game);
            return bubbles;
        }

        public void Init(GameState owner)
        {
            game = owner;
            random = new System.Random(Seed);
            canvas = gameObject.GetComponent<Canvas>();
            if (canvas == null)
            {
                canvas = gameObject.AddComponent<Canvas>();
                canvas.renderMode = RenderMode.ScreenSpaceOverlay;
                canvas.sortingOrder = SortingOrder;
                var scaler = gameObject.AddComponent<CanvasScaler>();
                scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
                scaler.referenceResolution = new Vector2(1920f, 1080f);
                scaler.matchWidthOrHeight = 0.5f;
            }
            for (int i = 0; i < pool.Length; i++)
            {
                pool[i] = BuildBubble(i);
            }
            if (game != null)
            {
                game.Reacted -= OnReacted;
                game.Reacted += OnReacted;
                game.RobotBumped -= OnRobotBumped;
                game.RobotBumped += OnRobotBumped;
                game.StateChanged -= OnStateChanged;
                game.StateChanged += OnStateChanged;
                game.FixedStepped -= OnFixedStepped;
                game.FixedStepped += OnFixedStepped;
            }
        }

        private void OnDestroy()
        {
            if (game != null)
            {
                game.Reacted -= OnReacted;
                game.RobotBumped -= OnRobotBumped;
                game.StateChanged -= OnStateChanged;
                game.FixedStepped -= OnFixedStepped;
            }
        }

        /// <summary>Tests: a fresh seeded sequence from <see cref="Seed"/>.</summary>
        public void ResetRandom()
        {
            random = new System.Random(Seed);
        }

        private Bubble BuildBubble(int i)
        {
            var root = new GameObject("Bubble" + i, typeof(RectTransform));
            root.transform.SetParent(transform, false);
            var rect = (RectTransform)root.transform;
            rect.anchorMin = rect.anchorMax = Vector2.zero;
            rect.pivot = new Vector2(0.5f, 0f);
            rect.sizeDelta = new Vector2(MinWidth, BodyHeight + TailSize * 0.5f);
            CanvasGroup group = root.AddComponent<CanvasGroup>();
            group.alpha = 0f;
            group.blocksRaycasts = false;
            group.interactable = false;

            // The tail first, so the plate draws over its upper half: a square on its corner, its tip at the root's pivot.
            var tailGo = new GameObject("Tail", typeof(RectTransform));
            tailGo.transform.SetParent(root.transform, false);
            var tail = (RectTransform)tailGo.transform;
            tail.anchorMin = tail.anchorMax = new Vector2(0.5f, 0f);
            tail.pivot = new Vector2(0.5f, 0.5f);
            tail.sizeDelta = new Vector2(TailSize, TailSize);
            tail.anchoredPosition = new Vector2(-10f, TailSize * 0.5f * 1.4142f);
            tail.localRotation = Quaternion.Euler(0f, 0f, 45f);
            Image tailImage = tailGo.AddComponent<Image>();
            tailImage.color = Cream;
            tailImage.raycastTarget = false;

            var bodyGo = new GameObject("Plate", typeof(RectTransform));
            bodyGo.transform.SetParent(root.transform, false);
            var body = (RectTransform)bodyGo.transform;
            body.anchorMin = new Vector2(0.5f, 0f);
            body.anchorMax = new Vector2(0.5f, 0f);
            body.pivot = new Vector2(0.5f, 0f);
            body.sizeDelta = new Vector2(MinWidth, BodyHeight);
            body.anchoredPosition = new Vector2(0f, TailSize * 0.5f);
            Image plate = bodyGo.AddComponent<Image>();
            plate.sprite = ProceduralArt.Rounded;
            plate.type = Image.Type.Sliced;
            plate.color = Cream;
            plate.raycastTarget = false;

            var labelGo = new GameObject("Label", typeof(RectTransform));
            labelGo.transform.SetParent(bodyGo.transform, false);
            var labelRect = (RectTransform)labelGo.transform;
            labelRect.anchorMin = Vector2.zero;
            labelRect.anchorMax = Vector2.one;
            labelRect.offsetMin = new Vector2(PadX, 0f);
            labelRect.offsetMax = new Vector2(-PadX, -2f);
            Text label = labelGo.AddComponent<Text>();
            label.font = Hud.DisplayFont;
            label.fontSize = Mathf.RoundToInt(FontSize);
            label.alignment = TextAnchor.MiddleCenter;
            label.horizontalOverflow = HorizontalWrapMode.Overflow;
            label.verticalOverflow = VerticalWrapMode.Overflow;
            label.color = Ink;
            label.raycastTarget = false;
            label.text = string.Empty;

            root.SetActive(false);
            return new Bubble { Root = rect, Group = group, Tail = tail, Body = body, Label = label };
        }

        // ----- Triggers -----

        private void OnReacted(ReactionKind kind, Inhabitant who)
        {
            if (who == null || Muted(kind))
            {
                return;
            }
            string personality = who.Personality != null ? who.Personality.Id : PersonalityDef.Default;
            Show(kind, personality, who, null);
        }

        private void OnRobotBumped(Robot robot)
        {
            if (robot == null || Muted(ReactionKind.RobotBump))
            {
                return;
            }
            Show(ReactionKind.RobotBump, Reactions.Robot, null, robot);
        }

        private void OnStateChanged(PlayState state)
        {
            // The end panels: every bubble goes; the catch's own line is raised after this and stays.
            if (state != PlayState.Playing)
            {
                ClearAll();
            }
        }

        /// <summary>The title house shows no bubble; a level that ended takes only the catch's line.</summary>
        private bool Muted(ReactionKind kind)
        {
            if (game == null || game.Level == null)
            {
                return true;
            }
            Menu menu = game.Menu;
            if (menu != null && (menu.TitleOpen || menu.LevelSelectOpen || menu.CreditsOpen))
            {
                return true;
            }
            return game.State != PlayState.Playing && kind != ReactionKind.Caught;
        }

        private void Show(ReactionKind kind, string personality, Inhabitant who, Robot robot)
        {
            Object speaker = who != null ? (Object)who : robot;
            Bubble bubble = null;
            foreach (Bubble b in pool)
            {
                if (b.Speaks(speaker))
                {
                    bubble = b;
                    break;
                }
            }
            if (bubble == null)
            {
                bubble = FreeBubble();
            }
            int avoid = bubble.Active && bubble.Kind == kind ? bubble.Variant : -1;
            string text = Reactions.Pick(kind, personality, random, avoid, out int variant);
            if (text == null)
            {
                return;
            }
            bubble.Who = who;
            bubble.Robot = robot;
            bubble.Kind = kind;
            bubble.Variant = variant;
            bubble.Age = 0f;
            bubble.Active = true;
            bubble.Caught = kind == ReactionKind.Caught;
            bubble.Label.text = text;
            float width = Mathf.Clamp(bubble.Label.preferredWidth + 2f * PadX, MinWidth, MaxWidth);
            bubble.Body.sizeDelta = new Vector2(width, BodyHeight);
            bubble.Root.sizeDelta = new Vector2(width, BodyHeight + TailSize * 0.5f);
            bubble.Root.localScale = Vector3.one * PopScale;
            bubble.Group.alpha = 0f;
            bubble.Root.gameObject.SetActive(true);
            ShownCount++;
            LastKind = kind;
            LastText = text;
            if (kind == ReactionKind.NearMiss)
            {
                NearMissCount++;
            }
            Place(bubble);
        }

        /// <summary>A free bubble, else the oldest one up (a catch line is never taken).</summary>
        private Bubble FreeBubble()
        {
            Bubble oldest = null;
            foreach (Bubble b in pool)
            {
                if (!b.Active)
                {
                    return b;
                }
                if (!b.Caught && (oldest == null || b.Age > oldest.Age))
                {
                    oldest = b;
                }
            }
            return oldest ?? pool[0];
        }

        private void Release(Bubble b)
        {
            b.Active = false;
            b.Caught = false;
            b.Who = null;
            b.Robot = null;
            b.Age = 0f;
            b.Group.alpha = 0f;
            b.Root.gameObject.SetActive(false);
        }

        /// <summary>Hides every bubble at once (a level change, an end panel).</summary>
        public void ClearAll()
        {
            foreach (Bubble b in pool)
            {
                if (b != null && b.Active)
                {
                    Release(b);
                }
            }
        }

        /// <summary>Tests: the text of the bubble up over <paramref name="speaker"/> (an Inhabitant or a Robot), or null.</summary>
        public string TextOver(Object speaker)
        {
            foreach (Bubble b in pool)
            {
                if (b != null && b.Speaks(speaker))
                {
                    return b.Label.text;
                }
            }
            return null;
        }

        /// <summary>Tests: the alpha of the bubble up over <paramref name="speaker"/> (0 without one).</summary>
        public float AlphaOver(Object speaker)
        {
            foreach (Bubble b in pool)
            {
                if (b != null && b.Speaks(speaker))
                {
                    return b.Group.alpha;
                }
            }
            return 0f;
        }

        /// <summary>Tests: the screen space position (canvas units, bottom left origin) of the bubble over a speaker.</summary>
        public Vector2 PositionOver(Object speaker)
        {
            foreach (Bubble b in pool)
            {
                if (b != null && b.Speaks(speaker))
                {
                    return b.Root.anchoredPosition;
                }
            }
            return Vector2.zero;
        }

        // ----- The near miss -----

        private void OnFixedStepped()
        {
            if (game == null)
            {
                return;
            }
            if (game.Level != level)
            {
                // A new level: fresh anchors, fresh counters, the same seeded sequence restarted.
                level = game.Level;
                ClearAll();
                ShownCount = 0;
                NearMissCount = 0;
                random = new System.Random(Seed);
                int n = level != null ? level.Inhabitants.Count : 0;
                visions = new Vision[n];
                seenSteps = new int[n];
                sweptWalking = new bool[n];
                cooldown = new int[n];
                for (int i = 0; i < n; i++)
                {
                    Inhabitant who = level.Inhabitants[i];
                    foreach (Vision v in level.Visions)
                    {
                        if (v != null && v.Owner == who)
                        {
                            visions[i] = v;
                            break;
                        }
                    }
                }
            }
            if (level != null)
            {
                StepNearMiss();
            }
        }

        /// <summary>
        /// A near miss: an inhabitant that counts for the catch, awake, unfrozen and in its routine, saw the furniture standing
        /// still (not moving, not carried, hidden or pinned) for NearMissMinSeen to NearMissMaxSeen, with at least one walking
        /// step in the sighting (a sweep, never a station glance), and then lost it while the furniture was still still.
        /// A sighting that ends because the furniture moved is a scare, not a near miss: no line (the catch rule speaks).
        /// </summary>
        private void StepNearMiss()
        {
            FurnitureController furniture = level.Furniture;
            bool playing = game.State == PlayState.Playing && game.Started && !Muted(ReactionKind.NearMiss);
            bool still = furniture != null && !game.FurnitureMoving && !furniture.Carried && !furniture.Hidden && !furniture.Pinned;
            float dt = Time.fixedDeltaTime > 0f ? Time.fixedDeltaTime : Tuning.FixedStep;
            int minSteps = Mathf.Max(1, Mathf.RoundToInt(NearMissMinSeen / dt));
            int maxSteps = Mathf.RoundToInt(NearMissMaxSeen / dt);
            for (int i = 0; i < visions.Length && i < level.Inhabitants.Count; i++)
            {
                if (cooldown[i] > 0)
                {
                    cooldown[i]--;
                }
                Inhabitant who = level.Inhabitants[i];
                Vision v = visions[i];
                InhabitantRoutine routine = who != null ? who.Routine : null;
                PersonalityDef p = who != null ? who.Personality : null;
                bool able = playing && routine != null && v != null && p != null && p.CountsForCatch && !routine.Asleep
                    && !routine.IsFrozen && routine.Mode == InhabitantMode.Routine;
                bool sees = able && v.SeesPlayer;
                if (sees && still)
                {
                    seenSteps[i]++;
                    sweptWalking[i] |= routine.LastActivity == RoutineActivity.Walking;
                    continue;
                }
                if (seenSteps[i] > 0)
                {
                    bool lost = able && !v.SeesPlayer && still;
                    if (lost && sweptWalking[i] && seenSteps[i] >= minSteps && seenSteps[i] <= maxSteps && cooldown[i] == 0)
                    {
                        cooldown[i] = Mathf.RoundToInt(NearMissCooldown / dt);
                        Show(ReactionKind.NearMiss, p.Id, who, null);
                    }
                    seenSteps[i] = 0;
                    sweptWalking[i] = false;
                }
            }
        }

        // ----- Placement and fade -----

        private void LateUpdate()
        {
            if (game == null)
            {
                return;
            }
            bool paused = GamePause.IsPaused;
            float dt = Application.isPlaying && !paused ? Time.deltaTime : 0f;
            bool muted = game.Level == null || (game.Menu != null && (game.Menu.TitleOpen || game.Menu.LevelSelectOpen || game.Menu.CreditsOpen));
            foreach (Bubble b in pool)
            {
                if (b == null || !b.Active)
                {
                    continue;
                }
                bool gone = muted || (b.Who == null && b.Robot == null);
                if (!gone && !b.Caught && game.State != PlayState.Playing)
                {
                    gone = true;
                }
                if (gone)
                {
                    Release(b);
                    continue;
                }
                b.Age += dt;
                if (b.Age >= Hold + Fade)
                {
                    Release(b);
                    continue;
                }
                float pop = Mathf.SmoothStep(PopScale, 1f, Mathf.Clamp01(b.Age / PopTime));
                b.Root.localScale = Vector3.one * pop;
                float alpha = b.Age < Hold ? Mathf.Clamp01(b.Age / (PopTime * 0.5f)) : 1f - Mathf.Clamp01((b.Age - Hold) / Fade);
                b.Group.alpha = Place(b) ? alpha : 0f;
            }
        }

        /// <summary>Puts the bubble at the projection of its speaker's anchor; false when the anchor is behind the camera.</summary>
        private bool Place(Bubble b)
        {
            Camera cam = Camera.main;
            if (cam == null)
            {
                return false;
            }
            Vector3 world = b.Who != null ? b.Who.BubbleAnchor : b.Robot.Position + Vector3.up * RobotLift;
            Vector3 sp = cam.WorldToScreenPoint(world);
            if (sp.z <= 0f)
            {
                return false;
            }
            float scale = canvas != null && canvas.scaleFactor > 0f ? canvas.scaleFactor : 1f;
            Vector2 size = ((RectTransform)transform).rect.size;
            var p = new Vector2(sp.x / scale, sp.y / scale + TailGap);
            float halfWidth = b.Root.sizeDelta.x * 0.5f;
            float height = b.Root.sizeDelta.y;
            p.x = Mathf.Clamp(p.x, EdgeMargin + halfWidth, size.x - EdgeMargin - halfWidth);
            p.y = Mathf.Clamp(p.y, EdgeMargin, size.y - EdgeMargin - height);
            b.Root.anchoredPosition = p;
            return true;
        }
    }
}
