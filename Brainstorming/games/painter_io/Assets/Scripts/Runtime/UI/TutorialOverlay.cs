// Owned by B4, then by game-flow in wave C. Contract 15.4: the tutorial, saved flags SaveData.TutExitDone, TutCutDone,
// TutLassoDone and (wave C) TutSelfCrossDone.
// - Step 0 (first 3 rounds, while Session.AwaitingStart): "Glisse ton doigt pour diriger" with an animated hand tracing an
//   arc in the lower third; hides on Begin.
// - Step 1 (after Begin, until the first capture): "Sors de ta couleur et reviens pour agrandir ton terrain." (then
//   TutExitDone = true).
// - Step 2 (first time the human's trail is cut): "On a coupé ton trait ! Rentre avant l'étincelle pour rester en vie." (the
//   line as changed by the user in contract 24, v1.4: a saved return survives but captures nothing),
//   with a pointer anchored on the retraction front (on the SparkEdgeIndicator when the front is off screen) for as long as
//   it is shown. Hides when the human is eliminated or home. TutCutDone only after a chased return home, or after 2.5 s of
//   real time on screen.
// - Step 3 (first ring pickup only): "Lasso ! Recroise ton fil pour enfermer une poche, puis rentre." (then TutLassoDone).
// - Step 4 (wave C, rules-01, owned by game-flow since wave C): after the human crossed its own trail without a charge
//   (LassoCrossNoCharge, rules R8 and R16 unchanged: nothing is shown at the crossing itself), the next UNCHASED return
//   shows "Recroiser ton fil ouvre ta boucle : rentre sans le recroiser pour tout peindre." (key tut.selfcross) for 4.0 s
//   of visible time, without pointer. A chased return just drops it (the saved toast already explains the loss); a new
//   exit cancels a pending lesson, and hides the bubble once it has been on screen for 2.5 s; a spark catch or the
//   elimination cancel both. TutSelfCrossDone is set once the bubble stayed visible for 2.5 s. "-uidemo selfcross" forces
//   the bubble during play for screenshots (dev aid, like "-uidemo hint").
// Lesson timers (wave C, rules-05): only time where the bubble is really on screen counts (CountsAsVisible), never the
// time behind the pause panel, the ready gate after a pause or the death beat.
// A step whose flag is set never shows again. Flags are written only by sessions that count for stats (real rounds), so
// DevShot, probe, test sessions and batch-mode runs never change the player's saved progress.
using PainterIO.Core;
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    public sealed class TutorialOverlay : UiScreen
    {
        public const int StepZeroRounds = 3;
        public const float CutDoneSeconds = 2.5f;
        public const float LassoSeconds = 5f;
        /// <summary>Wave C (rules-01): visible seconds of the self-crossing bubble.</summary>
        public const float SelfCrossSeconds = 4f;
        /// <summary>Wave C (rules-01): visible seconds after which the self-crossing lesson counts as learnt (saved flag).</summary>
        public const float SelfCrossDoneSeconds = 2.5f;
        /// <summary>Wave C (rules-05): bubble alpha from which the bubble counts as really on screen.</summary>
        public const float VisibleAlpha = 0.95f;
        public const float BubbleWidth = 880f;
        public const float BubbleY = -560f;

        /// <summary>The tutorial bubbles, by priority Cut > Lasso > SelfCross > Exit (None: no bubble wanted).</summary>
        public enum Bubble { None, Exit, Cut, Lasso, SelfCross }

        /// <summary>
        /// What one frame of the overlay reads from the director and the session. Tick builds it from the live game;
        /// EditMode tests pass their own to TickCore (no GameDirector needed).
        /// </summary>
        public struct TickInputs
        {
            /// <summary>The bound real session is the director's, State == Playing, and it has a human.</summary>
            public bool Live;
            public bool HumanAlive;
            /// <summary>The human is alive with a spark on its trail (its trail was cut and is being retracted).</summary>
            public bool HumanHasSpark;
            public bool AwaitingStart;
            public bool Paused;
            /// <summary>GameDirector.InResultsBeat (death beat or end beat).</summary>
            public bool InBeat;
        }

        private static readonly Color BubbleColor = new Color32(0xF3, 0xEE, 0xE8, 0xF2);
        private static readonly Color BubbleText = new Color32(0x15, 0x1D, 0x38, 0xFF);

        // Step 0.
        private readonly CanvasGroup hintGroup;
        private readonly Text hintText;
        private readonly RectTransform hand;
        private readonly Image[] trail = new Image[14];
        private readonly float[] trailAge = new float[14];
        private float handT, hintAlpha, trailTimer;
        private int trailNext;

        // Bubble and pointer.
        private readonly CanvasGroup bubbleGroup;
        private readonly RectTransform bubbleRect;
        private readonly Text bubbleText;
        private readonly CanvasGroup pointerGroup;
        private readonly RectTransform line, arrow, ring;
        private float bubbleAlpha, pointerAlpha, ringPhase;
        private Bubble shown = Bubble.None;

        // Session state.
        private GameSession session;
        private bool exitDone, cutActive, cutShown, cutDone, lassoActive, lassoShown;
        private float cutVisible, lassoTime, lassoEndAt = -1f;
        private bool selfCrossPending, selfCrossShown, selfCrossActive, selfCrossDone;
        private float selfCrossTime;

        /// <summary>
        /// The bubble's rect (TopCenter anchored in Safe, size BubbleWidth x 180), read by Hud to keep a toast below it
        /// when the leaderboard is open (wave C gate: replaces the lookup of the "Bubble" child by name).
        /// </summary>
        public RectTransform BubbleRect => bubbleRect;

        /// <summary>The bubble's current fade alpha (0 hidden, 1 fully shown), as drawn by its CanvasGroup.</summary>
        public float BubbleAlpha => bubbleGroup != null ? bubbleGroup.alpha : 0f;

        public TutorialOverlay(UiRoot root) : base(root, "Tutorial", UiRoot.TutorialOrder)
        {
            // Step 0: hint and hand in the lower third.
            RectTransform hint = UiKit.Rect("SteerHint", Safe);
            UiKit.Place(hint, new Vector2(0.5f, 0f), new Vector2(0f, 560f), new Vector2(900f, 520f));
            hintGroup = hint.gameObject.AddComponent<CanvasGroup>();
            hintGroup.alpha = 0f;
            hintText = UiKit.Label(hint, "Text", 50, UiKit.Light, TextAnchor.MiddleCenter);
            UiKit.Place(hintText.rectTransform, new Vector2(0.5f, 1f), new Vector2(0f, -40f), new Vector2(900f, 80f));
            for (int i = 0; i < trail.Length; i++)
            {
                Image dot = UiKit.Img(hint, "Trail" + i, UiKit.CircleSprite, UiKit.WithAlpha(UiKit.Light, 0f));
                UiKit.Place(dot.rectTransform, UiKit.Center, Vector2.zero, new Vector2(22f, 22f));
                trail[i] = dot;
                trailAge[i] = 99f;
            }
            hand = BuildHand(hint);

            // Bubble.
            bubbleRect = UiKit.Rect("Bubble", Safe);
            UiKit.Place(bubbleRect, UiKit.TopCenter, new Vector2(0f, BubbleY), new Vector2(BubbleWidth, 180f));
            bubbleGroup = bubbleRect.gameObject.AddComponent<CanvasGroup>();
            bubbleGroup.alpha = 0f;
            Image shadow = UiKit.Rounded(bubbleRect, "Shadow", UiKit.WithAlpha(UiKit.Navy, 0.55f), 44f);
            UiKit.Stretch(shadow.rectTransform);
            shadow.rectTransform.offsetMin = new Vector2(6f, -10f);
            shadow.rectTransform.offsetMax = new Vector2(6f, -10f);
            Image bg = UiKit.Rounded(bubbleRect, "Background", BubbleColor, 44f);
            UiKit.Stretch(bg.rectTransform);
            bubbleText = UiKit.Paragraph(bubbleRect, "Text", 46, BubbleText, TextAnchor.MiddleCenter, BubbleWidth - 90f, false);
            UiKit.Stretch(bubbleText.rectTransform);
            bubbleText.rectTransform.offsetMin = new Vector2(45f, 24f);
            bubbleText.rectTransform.offsetMax = new Vector2(-45f, -24f);

            // Pointer: leader line, arrow head and a pulsing ring on the target.
            RectTransform pointer = UiKit.Rect("Pointer", CanvasRect);
            UiKit.Stretch(pointer);
            pointerGroup = pointer.gameObject.AddComponent<CanvasGroup>();
            pointerGroup.alpha = 0f;
            Image lineImg = UiKit.Rounded(pointer, "Line", UiKit.WithAlpha(BubbleColor, 0.9f), 4f);
            line = lineImg.rectTransform;
            line.anchorMin = line.anchorMax = UiKit.Center;
            line.pivot = new Vector2(0f, 0.5f);
            line.sizeDelta = new Vector2(100f, 8f);
            Image arrowImg = UiKit.Img(pointer, "Arrow", UiKit.TriangleSprite, BubbleColor);
            arrow = arrowImg.rectTransform;
            UiKit.Place(arrow, UiKit.Center, Vector2.zero, new Vector2(40f, 40f));
            Image ringImg = UiKit.Img(pointer, "Ring", UiKit.RingSprite, Color.white);
            ring = ringImg.rectTransform;
            UiKit.Place(ring, UiKit.Center, Vector2.zero, new Vector2(110f, 110f));
        }

        protected override bool BlocksRaycasts => false;

        protected override bool AcceptsInput => false;

        /// <summary>True while the first-cut bubble is shown (tests, other packages).</summary>
        public bool CutBubbleVisible => shown == Bubble.Cut;

        /// <summary>The bubble the last Tick wanted on screen (None while paused, in the ready gate or the death beat).</summary>
        public Bubble WantedBubble { get; private set; }

        /// <summary>The bubble whose text is on screen (it can still be fading out while WantedBubble is None).</summary>
        public Bubble ShownBubble => shown;

        /// <summary>The first-cut lesson counts as done in this session (chased return, or 2.5 s really on screen).</summary>
        public bool CutLessonDone => cutDone;

        /// <summary>Real seconds the first-cut bubble has been really on screen (CountsAsVisible) in this session.</summary>
        public float CutVisibleSeconds => cutVisible;

        /// <summary>An uncharged self-crossing waits for the next return (rules-01).</summary>
        public bool SelfCrossPending => selfCrossPending;

        /// <summary>The self-crossing lesson counts as learnt in this session (2.5 s on screen, or the bubble ran its course).</summary>
        public bool SelfCrossLessonDone => selfCrossDone;

        /// <summary>
        /// Wave C (rules-05): a lesson timer advances only while its bubble is really on screen: a bubble is wanted (so not
        /// paused, not in the ready gate, not in the death beat), its text is the one shown, and it is faded in.
        /// </summary>
        public static bool CountsAsVisible(Bubble shown, Bubble want, float alpha)
        {
            return want != Bubble.None && shown == want && alpha >= VisibleAlpha;
        }

        public void Bind(GameSession s)
        {
            if (s == session) return;   // attract restarts re-raise SessionStarted with the same session
            session = s;
            exitDone = cutActive = cutShown = cutDone = lassoActive = lassoShown = false;
            selfCrossPending = selfCrossShown = selfCrossActive = selfCrossDone = false;
            cutVisible = lassoTime = selfCrossTime = 0f;
            lassoEndAt = -1f;
            WantedBubble = Bubble.None;
            shown = Bubble.None;
            bubbleAlpha = pointerAlpha = 0f;
            bubbleGroup.alpha = 0f;
            pointerGroup.alpha = 0f;
        }

        public override void Relabel()
        {
            hintText.text = Strings.Get("hint.steer");
            if (shown != Bubble.None) SetBubbleText(shown);
        }

        /// <summary>Handles a session event; returns true when it started the lasso bubble (the HUD then skips its toast).</summary>
        public bool OnSimEvent(GameSession s, SimEvent e)
        {
            if (s != session || s.IsAttract) return false;
            int h = s.HumanIndex;
            if (h < 0 || e.Player != h) return false;
            switch (e.Type)
            {
                case SimEventType.Return:
                    if (e.Cells != null && e.Cells.Length > 0 && !exitDone)
                    {
                        exitDone = true;
                        if (Persist(s) && !SaveData.TutExitDone) SaveData.TutExitDone = true;
                    }
                    if (cutActive)
                    {
                        if (e.Chased) MarkCutDone(s);
                        cutActive = false;
                    }
                    if (selfCrossPending)
                    {
                        // A chased return just drops the lesson: the saved toast already explains the lost loop.
                        selfCrossPending = false;
                        if (!e.Chased && !SaveData.TutSelfCrossDone)
                        {
                            selfCrossActive = true;
                            selfCrossShown = true;
                            selfCrossTime = 0f;
                        }
                    }
                    break;
                case SimEventType.Exit:
                    // A new excursion: a pending lesson belongs to the previous one. The bubble gives way too, but only
                    // once it has been read (SelfCrossDoneSeconds on screen): the edge flicker of 23.3 raises Exit events
                    // along the territory border and must not blink the lesson away before it could be read.
                    selfCrossPending = false;
                    if (selfCrossDone) selfCrossActive = false;
                    break;
                case SimEventType.LassoCrossNoCharge:
                    if (!selfCrossShown && !SaveData.TutSelfCrossDone) selfCrossPending = true;
                    break;
                case SimEventType.Cut:
                    if (!cutShown && !SaveData.TutCutDone)
                    {
                        cutShown = true;
                        cutActive = true;
                        cutVisible = 0f;
                    }
                    break;
                case SimEventType.SparkCaught:
                case SimEventType.Eliminated:
                    cutActive = false;
                    lassoActive = false;
                    selfCrossPending = false;
                    selfCrossActive = false;
                    break;
                case SimEventType.RingPicked:
                    if (!lassoShown && !SaveData.TutLassoDone)
                    {
                        lassoShown = true;
                        lassoActive = true;
                        lassoTime = 0f;
                        lassoEndAt = LassoSeconds;
                        if (Persist(s)) SaveData.TutLassoDone = true;
                        return true;
                    }
                    break;
                case SimEventType.LassoPocket:
                    if (lassoActive) lassoEndAt = Mathf.Min(lassoEndAt, lassoTime + 1.2f);
                    break;
            }
            return false;
        }

        public override void Tick(float dt)
        {
            TickCore(dt, ReadInputs());
        }

        /// <summary>The frame inputs of Tick, read from the director and the bound session.</summary>
        private TickInputs ReadInputs()
        {
            GameSession s = session;
            GameDirector d = Director;
            var k = new TickInputs
            {
                Live = s != null && s == Session && !s.IsAttract && s.HumanIndex >= 0 && d != null && d.State == GameState.Playing,
            };
            if (!k.Live) return k;
            PlayerState p = s.Sim.Players[s.HumanIndex];
            k.HumanAlive = s.HumanAlive;
            k.HumanHasSpark = p.Alive && p.Spark != null;
            k.AwaitingStart = s.AwaitingStart;
            k.Paused = d.IsPaused;
            k.InBeat = d.InResultsBeat;
            return k;
        }

        /// <summary>One frame of the overlay from explicit inputs (Tick passes the live game's; EditMode tests pass their own).</summary>
        public void TickCore(float dt, TickInputs k)
        {
            GameSession s = session;
            bool live = k.Live;
            bool humanAlive = live && k.HumanAlive;

            // Step 0.
            bool hintOn = live && humanAlive && ((k.AwaitingStart && !k.Paused && SaveData.RoundsPlayed < StepZeroRounds) || UiRoot.DemoShows("hint"));
            hintAlpha = Mathf.MoveTowards(hintAlpha, hintOn ? 1f : 0f, dt / (hintOn ? 0.25f : 0.15f));
            hintGroup.alpha = hintAlpha;
            if (hintAlpha > 0f) AnimateHand(dt);

            // Bubble choice: cut, then lasso, then self-crossing, then exit.
            if (cutActive && live && !k.HumanHasSpark) cutActive = false;
            if (lassoActive)
            {
                lassoTime += dt;
                if (lassoTime >= lassoEndAt) lassoActive = false;
            }
            Bubble want = Bubble.None;
            if (live && humanAlive && !k.InBeat && !k.AwaitingStart && !k.Paused)
            {
                if (cutActive) want = Bubble.Cut;
                else if (lassoActive) want = Bubble.Lasso;
                else if (selfCrossActive || UiRoot.DemoShows("selfcross")) want = Bubble.SelfCross;
                else if (!exitDone && !SaveData.TutExitDone) want = Bubble.Exit;
            }
            WantedBubble = want;
            if (want != Bubble.None && want != shown)
            {
                shown = want;
                SetBubbleText(want);
                bubbleAlpha = Mathf.Min(bubbleAlpha, 0.2f);
            }
            bubbleAlpha = Mathf.MoveTowards(bubbleAlpha, want != Bubble.None ? 1f : 0f, dt / (want != Bubble.None ? 0.2f : 0.12f));
            if (bubbleAlpha <= 0f && want == Bubble.None) shown = Bubble.None;

            // Lesson timers (rules-05): only the time the bubble is really on screen counts, never the time behind the
            // pause panel, in the ready gate after a pause or in the death beat (want is None there).
            bool visible = CountsAsVisible(shown, want, bubbleAlpha);
            if (cutActive && live && want == Bubble.Cut && visible)
            {
                cutVisible += dt;
                if (cutVisible >= CutDoneSeconds) MarkCutDone(s);
            }
            if (selfCrossActive && live && want == Bubble.SelfCross && visible)
            {
                selfCrossTime += dt;
                if (selfCrossTime >= SelfCrossDoneSeconds) MarkSelfCrossDone(s);
                if (selfCrossTime >= SelfCrossSeconds) selfCrossActive = false;
            }
            // Gate B: the fade-out uses a cubic curve. A linear fade of a light bubble over the dark ground left an empty
            // grey slab on screen (the dark text loses its contrast long before the background disappears).
            float groupAlpha = want == Bubble.None ? bubbleAlpha * bubbleAlpha * bubbleAlpha : bubbleAlpha;
            bubbleGroup.alpha = groupAlpha;
            float bob = want == Bubble.Cut ? 0f : Mathf.Sin(Time.unscaledTime * 2.2f) * 4f;
            bubbleRect.anchoredPosition = new Vector2(0f, BubbleY + bob + 16f * (1f - bubbleAlpha));

            // Pointer on the retraction front.
            bool pointerOn = false;
            if (shown == Bubble.Cut && want == Bubble.Cut && TryFrontScreen(s, out Vector2 target)) pointerOn = PlacePointer(target, dt);
            pointerAlpha = Mathf.MoveTowards(pointerAlpha, pointerOn ? 1f : 0f, dt / 0.15f);
            pointerGroup.alpha = pointerAlpha * groupAlpha;
        }

        // ------------------------------------------------------------------------------------------------------------

        private void MarkCutDone(GameSession s)
        {
            if (cutDone) return;
            cutDone = true;
            if (Persist(s) && !SaveData.TutCutDone) SaveData.TutCutDone = true;
        }

        private void MarkSelfCrossDone(GameSession s)
        {
            if (selfCrossDone) return;
            selfCrossDone = true;
            if (Persist(s) && !SaveData.TutSelfCrossDone) SaveData.TutSelfCrossDone = true;
        }

        /// <summary>Flags are saved only by real rounds (CountsForStats), never by batch-mode test runs.</summary>
        private static bool Persist(GameSession s)
        {
            return s != null && s.CountsForStats && !Application.isBatchMode;
        }

        private void SetBubbleText(Bubble b)
        {
            string key;
            switch (b)
            {
                case Bubble.Cut: key = "tut.cut"; break;
                case Bubble.Lasso: key = "tut.lasso"; break;
                case Bubble.SelfCross: key = "tut.selfcross"; break;
                default: key = "tut.exit"; break;
            }
            bubbleText.text = Strings.Get(key);
            float h = Mathf.Max(130f, bubbleText.preferredHeight + 56f);
            bubbleRect.sizeDelta = new Vector2(BubbleWidth, h);
        }

        /// <summary>Screen position of the human's retraction front, or of the SparkEdgeIndicator when it is off screen.</summary>
        private bool TryFrontScreen(GameSession s, out Vector2 screen)
        {
            screen = Vector2.zero;
            if (s == null || s.HumanIndex < 0) return false;
            PlayerState p = s.Sim.Players[s.HumanIndex];
            if (!p.Alive || p.Spark == null || p.Trail.IsEmpty) return false;
            double sr = s.RenderSparkS(s.HumanIndex);
            if (double.IsNaN(sr)) return false;
            Camera cam = Camera.main;
            if (cam == null) return false;
            Vec2d w = p.Trail.PointAt(sr);
            Vector3 sp = cam.WorldToScreenPoint(new Vector3((float)w.X, (float)w.Y, 0f));
            float margin = 40f;
            bool onScreen = sp.z > 0f && sp.x >= margin && sp.x <= Screen.width - margin && sp.y >= margin && sp.y <= Screen.height - margin;
            if (onScreen)
            {
                screen = sp;
                return true;
            }
            // Gate B: a direct read of the static indicator state (was a reflection probe, fragile under IL2CPP stripping).
            if (SparkEdgeIndicator.IsVisible)
            {
                screen = SparkEdgeIndicator.ScreenPosition;
                if (!float.IsNaN(screen.x) && !float.IsNaN(screen.y)) return true;
            }
            // Fallback: the front direction clamped onto the screen edge (where the edge chevron sits).
            float inset = 80f;
            screen = new Vector2(Mathf.Clamp(sp.x, inset, Screen.width - inset), Mathf.Clamp(sp.y, inset, Screen.height - inset));
            return true;
        }

        private bool PlacePointer(Vector2 targetScreen, float dt)
        {
            if (!RectTransformUtility.ScreenPointToLocalPointInRectangle(CanvasRect, targetScreen, null, out Vector2 target)) return false;
            var corners = new Vector3[4];
            bubbleRect.GetWorldCorners(corners);   // overlay canvas: world = screen pixels (0 bottom-left, 2 top-right)
            float left = corners[0].x, right = corners[2].x, bottom = corners[0].y, top = corners[2].y;
            float inset = Mathf.Min(70f, (right - left) * 0.25f);
            Vector2 startScreen;
            if (targetScreen.y < bottom) startScreen = new Vector2(Mathf.Clamp(targetScreen.x, left + inset, right - inset), bottom);
            else if (targetScreen.y > top) startScreen = new Vector2(Mathf.Clamp(targetScreen.x, left + inset, right - inset), top);
            else startScreen = new Vector2(targetScreen.x < (left + right) * 0.5f ? left : right, Mathf.Clamp(targetScreen.y, bottom, top));
            RectTransformUtility.ScreenPointToLocalPointInRectangle(CanvasRect, startScreen, null, out Vector2 start);

            ringPhase += dt * 2.4f;
            float pulse = 0.5f + 0.5f * Mathf.Sin(ringPhase * Mathf.PI * 2f);
            ring.anchoredPosition = target;
            float rs = 1f + 0.22f * pulse;
            ring.localScale = new Vector3(rs, rs, 1f);
            ring.GetComponent<Image>().color = new Color(1f, 1f, 1f, 0.65f + 0.35f * pulse);

            Vector2 dir = target - start;
            float dist = dir.magnitude;
            float ringRadius = 55f * rs + 14f;
            if (dist < ringRadius + 30f)
            {
                line.localScale = Vector3.zero;
                arrow.localScale = Vector3.zero;
                return true;
            }
            dir /= dist;
            float len = dist - ringRadius - 18f;
            float angle = Mathf.Atan2(dir.y, dir.x) * Mathf.Rad2Deg;
            line.localScale = Vector3.one;
            line.anchoredPosition = start;
            line.sizeDelta = new Vector2(Mathf.Max(0f, len), 8f);
            line.localEulerAngles = new Vector3(0f, 0f, angle);
            arrow.localScale = Vector3.one;
            arrow.anchoredPosition = start + dir * (len + 10f);
            arrow.localEulerAngles = new Vector3(0f, 0f, angle - 90f);
            return true;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Step 0 hand.

        private static RectTransform BuildHand(RectTransform parent)
        {
            RectTransform root = UiKit.Rect("Hand", parent);
            UiKit.Place(root, UiKit.Center, Vector2.zero, new Vector2(10f, 10f));
            // Silhouette pieces in hand space, fingertip at the origin: (center, size, radius, rotation).
            BuildHandLayer(root, "Shadow", UiKit.WithAlpha(UiKit.Navy, 0.55f), new Vector2(7f, -10f));
            BuildHandLayer(root, "Fill", UiKit.Light, Vector2.zero);
            root.localEulerAngles = new Vector3(0f, 0f, 12f);
            return root;
        }

        private static void BuildHandLayer(RectTransform root, string name, Color color, Vector2 offset)
        {
            RectTransform layer = UiKit.Rect(name, root);
            UiKit.Place(layer, UiKit.Center, offset, new Vector2(10f, 10f));
            Piece(layer, color, new Vector2(0f, -58f), new Vector2(40f, 136f), 20f, 0f);      // index finger
            Piece(layer, color, new Vector2(30f, -158f), new Vector2(124f, 124f), 42f, 0f);   // palm
            Piece(layer, color, new Vector2(40f, -104f), new Vector2(38f, 74f), 19f, 0f);     // middle finger (folded)
            Piece(layer, color, new Vector2(70f, -112f), new Vector2(36f, 66f), 18f, 0f);     // ring finger
            Piece(layer, color, new Vector2(95f, -126f), new Vector2(32f, 56f), 16f, 0f);     // little finger
            Piece(layer, color, new Vector2(-30f, -160f), new Vector2(38f, 92f), 19f, 42f);   // thumb
        }

        private static void Piece(RectTransform parent, Color color, Vector2 center, Vector2 size, float radius, float rotation)
        {
            Image img = UiKit.Rounded(parent, "Piece", color, radius);
            UiKit.Place(img.rectTransform, UiKit.Center, center, size);
            img.rectTransform.localEulerAngles = new Vector3(0f, 0f, rotation);
        }

        private void AnimateHand(float dt)
        {
            const float sweep = 1.5f, rest = 0.45f;
            handT += dt;
            if (handT > sweep + rest) handT = 0f;
            float u = Mathf.Clamp01(handT / sweep);
            float e = u * u * (3f - 2f * u);
            // An arc from the lower left to the right, through a crest (the hint area is 900 x 520, center origin).
            Vector2 tip = new Vector2(Mathf.Lerp(-250f, 250f, e), -150f + 170f * Mathf.Sin(Mathf.PI * e));
            hand.anchoredPosition = tip;
            float a = handT <= sweep ? Mathf.Clamp01(u / 0.12f) * Mathf.Clamp01((1f - u) / 0.12f + 0.25f) : 0f;
            SetHandAlpha(Mathf.Clamp01(a));
            float press = handT <= sweep ? 0.94f : 1f;
            hand.localScale = new Vector3(press, press, 1f);

            trailTimer += dt;
            if (handT <= sweep && u > 0.04f && trailTimer >= 0.045f)
            {
                trailTimer = 0f;
                trail[trailNext].rectTransform.anchoredPosition = tip;
                trailAge[trailNext] = 0f;
                trailNext = (trailNext + 1) % trail.Length;
            }
            for (int i = 0; i < trail.Length; i++)
            {
                trailAge[i] += dt;
                float k = Mathf.Clamp01(1f - trailAge[i] / 0.5f);
                trail[i].color = UiKit.WithAlpha(UiKit.Light, 0.75f * k);
                float sz = Mathf.Lerp(8f, 24f, k);
                trail[i].rectTransform.sizeDelta = new Vector2(sz, sz);
            }
        }

        private void SetHandAlpha(float a)
        {
            var group = hand.GetComponent<CanvasGroup>();
            if (group == null)
            {
                group = hand.gameObject.AddComponent<CanvasGroup>();
                group.blocksRaycasts = false;
                group.interactable = false;
            }
            group.alpha = a;
        }
    }
}
