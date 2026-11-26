using System.Threading.Tasks;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using UnityEngine.Video;

namespace OutOfSight
{
    /// <summary>
    /// ADSSHOP: the development ad provider. Its "ad" is a full-screen overlay (<see cref="SimulatedAdOverlay"/>) with a
    /// countdown of <see cref="AdConfig.PreferredMaxDurationSeconds"/> and a skip button that unlocks after
    /// <see cref="AdConfig.SkippableAfterSeconds"/>, so the frequency rules, the audio pause and the end-of-level flow can
    /// be tried without any SDK, account or network. Its privacy options form is a notice standing in for Google UMP.
    /// Never ship it: a non-editor run logs a warning at initialization.
    /// </summary>
    public sealed class SimulatedAdProvider : IAdProvider
    {
        private AdConfig config = AdConfig.Defaults();

        public string Name => AdConfig.ProviderSimulated;
        public bool Initialized { get; private set; }
        public bool SupportsPrivacyOptions => Initialized;

        public Task<bool> aInitialize(AdConfig adConfig)
        {
            config = adConfig ?? AdConfig.Defaults();
            Initialized = true;
            if (!Application.isEditor)
            {
                Debug.LogWarning("[Ads] the Simulated ad provider runs in a player build: set \"provider\" in Resources/Config/ads.json to a real network before release");
            }
            return Task.FromResult(true);
        }

        public bool IsReady(AdFormat format) => Initialized && SimulatedAdOverlay.Current == null;

        public Task<AdShowResult> aShow(AdFormat format, string placement)
        {
            if (!IsReady(format))
            {
                return Task.FromResult(AdShowResult.Of(AdOutcome.NotReady));
            }
            return SimulatedAdOverlay.aShowAd(format, placement, config.PreferredMaxDurationSeconds, config.SkippableAfterSeconds,
                config.SimulatedVideo);
        }

        public async Task<bool> aShowPrivacyOptions()
        {
            if (!Initialized || SimulatedAdOverlay.Current != null)
            {
                return false;
            }
            await SimulatedAdOverlay.aShowNotice(Strings.Get("ads.privacyTitle"), Strings.Get("ads.privacyBody"));
            return true;
        }
    }

    /// <summary>
    /// ADSSHOP: the Simulated provider's full-screen overlay, above every menu (sorting order 200). It swallows every
    /// pointer and keeps the UI selection on its own button, so no press reaches the win or fail panel behind it. Runs on
    /// unscaled time (the game is paused under it). Destroyed early (a scene reload), it completes as skipped.
    /// </summary>
    public sealed class SimulatedAdOverlay : MonoBehaviour
    {
        /// <summary>The overlay on screen, or null.</summary>
        public static SimulatedAdOverlay Current { get; private set; }

        /// <summary>The overlay's button (Skip, or Close on a notice).</summary>
        public Button ActionButton { get; private set; }

        private TaskCompletionSource<AdShowResult> done;
        private AdFormat format;
        private bool notice;
        private float duration;
        private float skipAfter;
        private float elapsed;
        private Text countdown;
        private Text actionLabel;
        private VideoPlayer video;
        private RenderTexture videoTexture;
        private static bool missingVideoLogged;

        private static readonly Color Backdrop = new Color(0.02f, 0.015f, 0.01f, 0.95f);
        private static readonly Color Card = new Color(0.16f, 0.105f, 0.08f, 1f);
        private static readonly Color Ink = new Color(1f, 0.94f, 0.82f, 1f);
        private static readonly Color Accent = new Color(0.96f, 0.8f, 0.58f, 0.95f);

        /// <summary>
        /// Shows a fake ad; completes with Completed at the end (rewarded when <paramref name="adFormat"/> is), Skipped on
        /// skip. ADVIDEO: with a <paramref name="videoPath"/> VideoClip under Resources, the ad plays it full screen for its
        /// own length (the text card when it is missing or fails to play).
        /// </summary>
        public static Task<AdShowResult> aShowAd(AdFormat adFormat, string placement, int durationSeconds, int skippableAfterSeconds,
            string videoPath = null)
        {
            SimulatedAdOverlay overlay = Create(false);
            overlay.format = adFormat;
            VideoClip clip = string.IsNullOrEmpty(videoPath) ? null : Resources.Load<VideoClip>(videoPath);
            if (clip == null && !string.IsNullOrEmpty(videoPath) && !missingVideoLogged)
            {
                // ADSEVERY: no clip ships in the build any more (a streamed source comes later): say so once, not per ad.
                missingVideoLogged = true;
                Debug.Log($"[Ads] no VideoClip at Resources/{videoPath}: the simulated ad shows its text card");
            }
            float length = clip != null && clip.length > 0.5 ? (float)clip.length : Mathf.Max(1, durationSeconds);
            overlay.duration = length;
            overlay.skipAfter = Mathf.Clamp(skippableAfterSeconds, 0f, length);
            string kind = adFormat == AdFormat.Rewarded ? "rewarded" : "interstitial";
            overlay.Build(Strings.Get("ads.simulated"), string.Format(Strings.Get("ads.simulatedBody"), kind, placement ?? "-"));
            if (clip != null)
            {
                overlay.PlayVideo(clip);
            }
            return overlay.done.Task;
        }

        /// <summary>
        /// ADVIDEO: the clip over the backdrop and the card (letterboxed, its aspect kept), under the badge, the countdown
        /// and the skip button. Its sound goes straight to the device (Direct output), so it plays while AdService keeps
        /// the game's own audio paused and silent; at the options' volume.
        /// </summary>
        private void PlayVideo(VideoClip clip)
        {
            int width = Mathf.Max(1, (int)clip.width);
            int height = Mathf.Max(1, (int)clip.height);
            videoTexture = new RenderTexture(width, height, 0) { name = "SimulatedAdVideo" };
            var screen = new GameObject("AdVideo", typeof(RectTransform));
            screen.transform.SetParent(transform, false);
            screen.transform.SetSiblingIndex(1); // just above the backdrop, below the badge, card, countdown and button
            var black = screen.AddComponent<Image>();
            black.color = Color.black;
            black.raycastTarget = false;
            Stretch((RectTransform)screen.transform);
            var picture = new GameObject("Picture", typeof(RectTransform));
            picture.transform.SetParent(screen.transform, false);
            var raw = picture.AddComponent<RawImage>();
            raw.texture = videoTexture;
            raw.raycastTarget = false;
            Stretch((RectTransform)picture.transform);
            var fit = picture.AddComponent<AspectRatioFitter>();
            fit.aspectMode = AspectRatioFitter.AspectMode.FitInParent;
            fit.aspectRatio = (float)width / height;

            video = gameObject.AddComponent<VideoPlayer>();
            video.playOnAwake = false;
            video.isLooping = false;
            video.source = VideoSource.VideoClip;
            video.clip = clip;
            video.renderMode = VideoRenderMode.RenderTexture;
            video.targetTexture = videoTexture;
            video.timeUpdateMode = VideoTimeUpdateMode.UnscaledGameTime;
            video.audioOutputMode = VideoAudioOutputMode.Direct;
            float volume = AudioMute.Apply(SaveStore.AppliedVolume);
            for (ushort track = 0; track < clip.audioTrackCount; track++)
            {
                video.EnableAudioTrack(track, true);
                video.SetDirectAudioVolume(track, volume);
            }
            // The video replaces the text card; a failure brings the card back.
            Transform card = transform.Find("AdCard");
            if (card != null)
            {
                card.gameObject.SetActive(false);
            }
            video.errorReceived += (source, message) =>
            {
                Debug.LogWarning("[Ads] the simulated ad video failed, the text card instead: " + message);
                screen.SetActive(false);
                if (card != null)
                {
                    card.gameObject.SetActive(true);
                }
            };
            video.Play();
        }

        /// <summary>Shows a notice with a Close button (the Simulated privacy form); completes when closed.</summary>
        public static Task<AdShowResult> aShowNotice(string title, string body)
        {
            SimulatedAdOverlay overlay = Create(true);
            overlay.Build(title, body);
            return overlay.done.Task;
        }

        private static SimulatedAdOverlay Create(bool asNotice)
        {
            if (Current != null)
            {
                Destroy(Current.gameObject);
            }
            var go = new GameObject(asNotice ? "SimulatedNotice" : "SimulatedAd", typeof(RectTransform));
            SimulatedAdOverlay overlay = go.AddComponent<SimulatedAdOverlay>();
            overlay.notice = asNotice;
            overlay.done = new TaskCompletionSource<AdShowResult>();
            Current = overlay;
            return overlay;
        }

        private void Build(string title, string body)
        {
            Font font = Main.Instance != null && Main.Instance.Hud != null && Main.Instance.Hud.Font != null
                ? Main.Instance.Hud.Font
                : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            Font display = Hud.DisplayFont != null ? Hud.DisplayFont : font;

            var canvas = gameObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 200;
            var scaler = gameObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);
            scaler.matchWidthOrHeight = 0.5f;
            gameObject.AddComponent<GraphicRaycaster>();

            Image back = NewImage(transform, "Backdrop", null, Backdrop);
            back.raycastTarget = true; // swallows every click and tap meant for the panels behind
            Stretch(back.rectTransform);

            Text badge = NewText(transform, "AdBadge", Strings.AdsLabel, 30, Accent, font);
            badge.alignment = TextAnchor.UpperLeft;
            Place(badge.rectTransform, new Vector2(0f, 1f), new Vector2(48f, -36f), new Vector2(600f, 44f));

            Image card = NewImage(transform, "AdCard", ProceduralArt.Rounded, Card);
            card.type = Image.Type.Sliced;
            Place(card.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, 40f), new Vector2(1100f, 520f));
            Text heading = NewText(card.transform, "AdTitle", title, 72, Ink, display);
            Place(heading.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, 110f), new Vector2(1040f, 110f));
            Text text = NewText(card.transform, "AdBody", body, 34, Ink, font);
            text.horizontalOverflow = HorizontalWrapMode.Wrap;
            Place(text.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, -40f), new Vector2(980f, 160f));

            countdown = NewText(transform, "AdCountdown", string.Empty, 32, Accent, font);
            Place(countdown.rectTransform, new Vector2(0.5f, 0f), new Vector2(0f, 150f), new Vector2(900f, 50f));

            ActionButton = Hud.MenuButton(transform, "AdAction", notice ? Strings.AdsClose : Strings.AdsSkip, font, null);
            Place((RectTransform)ActionButton.transform, new Vector2(1f, 0f), new Vector2(-60f, 50f), new Vector2(360f, 84f));
            actionLabel = ActionButton.GetComponentInChildren<Text>(true);
            ActionButton.navigation = new Navigation { mode = Navigation.Mode.None };
            ActionButton.onClick.AddListener(OnAction);
            ActionButton.interactable = notice || skipAfter <= 0f;
            Refresh();
            KeepSelection();
        }

        private void Update()
        {
            if (done == null || done.Task.IsCompleted)
            {
                return;
            }
            if (!notice)
            {
                elapsed += Time.unscaledDeltaTime;
                if (elapsed >= duration)
                {
                    Finish(new AdShowResult { Outcome = AdOutcome.Completed, Rewarded = format == AdFormat.Rewarded });
                    return;
                }
                ActionButton.interactable = elapsed >= skipAfter;
                Refresh();
            }
            KeepSelection();
        }

        /// <summary>The selection stays on the overlay's button: Enter or gamepad A never submits a panel behind it.</summary>
        private void KeepSelection()
        {
            EventSystem events = EventSystem.current;
            if (events != null && ActionButton != null && events.currentSelectedGameObject != ActionButton.gameObject)
            {
                events.SetSelectedGameObject(ActionButton.gameObject);
            }
        }

        private void Refresh()
        {
            if (notice || countdown == null)
            {
                return;
            }
            int left = Mathf.Max(0, Mathf.CeilToInt(duration - elapsed));
            countdown.text = string.Format(Strings.Get("ads.endsIn"), left);
            if (actionLabel != null)
            {
                actionLabel.text = elapsed >= skipAfter
                    ? Strings.AdsSkip
                    : string.Format(Strings.Get("ads.skipIn"), Mathf.Max(1, Mathf.CeilToInt(skipAfter - elapsed)));
            }
        }

        private void OnAction()
        {
            if (notice)
            {
                Finish(AdShowResult.Of(AdOutcome.Completed));
            }
            else if (elapsed >= skipAfter)
            {
                // A skipped rewarded ad forfeits its reward, as on a real network.
                Finish(AdShowResult.Of(elapsed >= duration ? AdOutcome.Completed : AdOutcome.Skipped));
            }
        }

        private void Finish(AdShowResult result)
        {
            if (done != null && !done.Task.IsCompleted)
            {
                done.TrySetResult(result);
            }
            if (EventSystem.current != null && ActionButton != null && EventSystem.current.currentSelectedGameObject == ActionButton.gameObject)
            {
                EventSystem.current.SetSelectedGameObject(null);
            }
            Destroy(gameObject);
        }

        private void OnDestroy()
        {
            if (Current == this)
            {
                Current = null;
            }
            if (video != null)
            {
                video.Stop();
            }
            if (videoTexture != null)
            {
                videoTexture.Release();
                Destroy(videoTexture);
            }
            done?.TrySetResult(AdShowResult.Of(AdOutcome.Skipped, "overlay destroyed"));
        }

        // ----- Construction helpers (the Menu's own style, kept local). -----

        private static Image NewImage(Transform parent, string name, Sprite sprite, Color color)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var image = go.AddComponent<Image>();
            image.sprite = sprite;
            image.color = color;
            image.raycastTarget = false;
            return image;
        }

        private static Text NewText(Transform parent, string name, string value, int size, Color color, Font face)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var text = go.AddComponent<Text>();
            text.font = face;
            text.fontSize = size;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = color;
            text.text = value;
            text.raycastTarget = false;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            return text;
        }

        private static void Place(RectTransform rect, Vector2 anchor, Vector2 offset, Vector2 size)
        {
            rect.anchorMin = rect.anchorMax = anchor;
            rect.pivot = anchor;
            rect.anchoredPosition = offset;
            rect.sizeDelta = size;
        }

        private static void Stretch(RectTransform rect)
        {
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }
    }
}
