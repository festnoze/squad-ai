// Owned by traits-ui (wave D-2). docs/BIOME_TRAITS.md section 7.2 (presentation of the kill rewards), HUD part:
// - RewardChips: a compact indicator of the human's current speed level (KillSpeedBoost: "+20 %" and one pip per level
//   up to the cap) and shield time (KillShield: a ring that empties with the seconds left), right of the pause button.
//   Each chip fades in only while it means something (a multiplier above 1, a live shield). They poll SimView every frame
//   (SpeedMultiplier, IsShielded, ShieldEndTime) on the sim render clock, so they slow down with the slow motion and stop
//   while paused, like the area count-up.
// - RewardTally: what the human earned this round (lands inherited, the speed level reached, shields), fed by
//   Hud.OnSimEvent and read by ResultsScreen for the reward items of its stats line.
// "-uidemo rewards" shows both chips with demo values (screenshots only).
using System;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    /// <summary>The human's kill rewards of the current round (Hud feeds it, ResultsScreen reads it).</summary>
    public sealed class RewardTally
    {
        /// <summary>Kills that gave the victim's land (TerritoryInherited events of the human).</summary>
        public int Inherited;
        /// <summary>Cells received through those events.</summary>
        public int InheritedCells;
        /// <summary>The highest SpeedMultiplier announced by SpeedBoosted (1 when none).</summary>
        public double SpeedMultiplier = 1.0;
        /// <summary>Shields started by the human's kills.</summary>
        public int Shields;
        /// <summary>The human's last chased return came after its spark was put out by a shield (results WHY line).</summary>
        public bool LastChasedReturnQuenched;

        public bool Any => Inherited > 0 || SpeedMultiplier > 1.0 + 1e-9 || Shields > 0;

        public void Reset()
        {
            Inherited = 0;
            InheritedCells = 0;
            SpeedMultiplier = 1.0;
            Shields = 0;
            LastChasedReturnQuenched = false;
        }

        /// <summary>
        /// The reward items appended to the results stats line (" · "-joined, current language), or null when the human
        /// earned nothing: "2 terrains pris", "vitesse +20 %", "1 bouclier".
        /// </summary>
        public string StatsItems(int language)
        {
            if (!Any) return null;
            var sb = new System.Text.StringBuilder();
            if (Inherited > 0) Append(sb, Strings.Count("results.stat.inherit", Inherited, language));
            if (SpeedMultiplier > 1.0 + 1e-9)
                Append(sb, Strings.FormatIn(language, "results.stat.speed", TraitText.Percent(SpeedMultiplier - 1.0, language)));
            if (Shields > 0) Append(sb, Strings.Count("results.stat.shields", Shields, language));
            return sb.ToString();
        }

        private static void Append(System.Text.StringBuilder sb, string item)
        {
            if (sb.Length > 0) sb.Append(" · ");
            sb.Append(item);
        }
    }

    /// <summary>The speed level and shield chips of the HUD.</summary>
    public sealed class RewardChips
    {
        public const float ChipHeight = 64f;
        public const float ChipGap = 14f;
        public const float FadeSeconds = 0.15f;
        public const int MaxPips = 6;
        /// <summary>The shield chip pulses in its last second.</summary>
        public const float ShieldWarnSeconds = 1f;

        private readonly RectTransform root;
        private readonly RectTransform speedRect, shieldRect;
        private readonly CanvasGroup speedGroup, shieldGroup;
        private readonly Image speedIcon, shieldIcon, shieldRing, shieldTrack;
        private readonly Image[] pips = new Image[MaxPips];
        private readonly Text speedText, shieldText;
        private float speedAlpha, shieldAlpha, pulse;
        private long speedKey = long.MinValue, shieldKey = long.MinValue;

        /// <param name="parent">The HUD safe area.</param>
        /// <param name="topLeft">Left edge and vertical center of the first chip (TopLeft anchored, reference units).</param>
        public RewardChips(RectTransform parent, Vector2 topLeft)
        {
            root = UiKit.Rect("RewardChips", parent);
            root.anchorMin = root.anchorMax = UiKit.TopLeft;
            root.pivot = new Vector2(0f, 0.5f);
            root.sizeDelta = new Vector2(600f, ChipHeight);
            root.anchoredPosition = topLeft;

            // Speed: bolt icon, "+20 %", pips.
            speedRect = Chip("Speed", out speedGroup);
            speedIcon = UiKit.Img(speedRect, "Icon", TraitIcons.Get(TraitId.KillSpeedBoost), UiKit.Light);
            UiKit.Place(speedIcon.rectTransform, new Vector2(0f, 0.5f), new Vector2(38f, 0f), new Vector2(40f, 40f));
            speedText = UiKit.Label(speedRect, "Text", 40, UiKit.Light, TextAnchor.MiddleLeft);
            RectTransform st = speedText.rectTransform;
            st.anchorMin = st.anchorMax = new Vector2(0f, 0.5f);
            st.pivot = new Vector2(0f, 0.5f);
            st.sizeDelta = new Vector2(160f, ChipHeight);
            st.anchoredPosition = new Vector2(64f, 0f);
            for (int i = 0; i < MaxPips; i++)
            {
                pips[i] = UiKit.Img(speedRect, "Pip" + i, UiKit.CircleSprite, UiKit.Light);
                UiKit.Place(pips[i].rectTransform, new Vector2(0f, 0.5f), Vector2.zero, new Vector2(15f, 15f));
                pips[i].enabled = false;
            }

            // Shield: a ring that empties around the shield icon, and the seconds left.
            shieldRect = Chip("Shield", out shieldGroup);
            shieldTrack = UiKit.Img(shieldRect, "Track", UiKit.RingSprite, UiKit.WithAlpha(UiKit.Light, 0.22f));
            UiKit.Place(shieldTrack.rectTransform, new Vector2(0f, 0.5f), new Vector2(36f, 0f), new Vector2(54f, 54f));
            shieldRing = UiKit.Img(shieldRect, "Ring", UiKit.RingSprite, UiKit.Light);
            UiKit.Place(shieldRing.rectTransform, new Vector2(0f, 0.5f), new Vector2(36f, 0f), new Vector2(54f, 54f));
            shieldRing.type = Image.Type.Filled;
            shieldRing.fillMethod = Image.FillMethod.Radial360;
            shieldRing.fillOrigin = (int)Image.Origin360.Top;
            shieldRing.fillClockwise = false;
            shieldIcon = UiKit.Img(shieldRect, "Icon", TraitIcons.Get(TraitId.KillShield), UiKit.Light);
            UiKit.Place(shieldIcon.rectTransform, new Vector2(0f, 0.5f), new Vector2(36f, 0f), new Vector2(32f, 32f));
            shieldText = UiKit.Label(shieldRect, "Text", 40, UiKit.Light, TextAnchor.MiddleLeft);
            RectTransform ht = shieldText.rectTransform;
            ht.anchorMin = ht.anchorMax = new Vector2(0f, 0.5f);
            ht.pivot = new Vector2(0f, 0.5f);
            ht.sizeDelta = new Vector2(140f, ChipHeight);
            ht.anchoredPosition = new Vector2(70f, 0f);

            Hide();
        }

        /// <summary>True while the speed chip is (fading) visible (tests).</summary>
        public bool SpeedVisible => speedGroup.alpha > 0.001f;

        /// <summary>True while the shield chip is (fading) visible (tests).</summary>
        public bool ShieldVisible => shieldGroup.alpha > 0.001f;

        public string SpeedText => speedText.text;

        public string ShieldText => shieldText.text;

        /// <summary>Fill of the shield ring (1 just after the kill, 0 at the end).</summary>
        public float ShieldFill => shieldRing.fillAmount;

        /// <summary>Pips lit / drawn (tests).</summary>
        public int PipsLit { get; private set; }
        public int PipsDrawn { get; private set; }

        /// <summary>Hides both chips at once (a new session).</summary>
        public void Hide()
        {
            speedAlpha = shieldAlpha = 0f;
            speedGroup.alpha = shieldGroup.alpha = 0f;
            speedKey = shieldKey = long.MinValue;
        }

        /// <summary>
        /// One frame: speedMultiplier (1 = no bonus), perKill and cap of KillSpeedBoost (0 when unknown), the seconds of
        /// shield left (0 or less = none) and its full duration, the human's color for the accents.
        /// </summary>
        public void Tick(float dt, double speedMultiplier, double perKill, double cap, double shieldLeft, double shieldDuration, Color human)
        {
            bool speedOn = speedMultiplier > 1.0 + 1e-6;
            bool shieldOn = shieldLeft > 1e-6;
            speedAlpha = Mathf.MoveTowards(speedAlpha, speedOn ? 1f : 0f, dt / FadeSeconds);
            shieldAlpha = Mathf.MoveTowards(shieldAlpha, shieldOn ? 1f : 0f, dt / FadeSeconds);
            speedGroup.alpha = speedAlpha;
            shieldGroup.alpha = shieldAlpha;
            Color accent = UiKit.Lighten(human, 0.25f);

            float x = 0f;
            if (speedOn || speedAlpha > 0f)
            {
                if (speedOn) SetSpeed(speedMultiplier, perKill, cap, accent);
                speedRect.anchoredPosition = new Vector2(x, 0f);
                x += speedRect.sizeDelta.x + ChipGap;
            }
            if (shieldOn || shieldAlpha > 0f)
            {
                if (shieldOn) SetShield(shieldLeft, shieldDuration, accent, dt);
                shieldRect.anchoredPosition = new Vector2(x, 0f);
            }
        }

        private void SetSpeed(double multiplier, double perKill, double cap, Color accent)
        {
            double bonus = multiplier - 1.0;
            int levels = perKill > 1e-9 ? (int)Math.Round(bonus / perKill) : 0;
            int maxLevels = perKill > 1e-9 && cap > 1e-9 ? (int)Math.Round(cap / perKill) : 0;
            maxLevels = Mathf.Clamp(maxLevels, 0, MaxPips);
            levels = Mathf.Clamp(levels, 0, Mathf.Max(maxLevels, 0));
            long key = ((long)Math.Round(bonus * 1000.0) * 16 + levels) * 16 + maxLevels;
            key = key * 4 + Strings.Language;
            speedIcon.color = accent;
            if (key == speedKey) return;
            speedKey = key;
            speedText.text = Strings.Format("hud.speed", TraitText.Percent(bonus, Strings.Language));
            float textWidth = speedText.preferredWidth;
            float pipsX = 64f + textWidth + 14f;
            for (int i = 0; i < MaxPips; i++)
            {
                bool drawn = i < maxLevels;
                pips[i].enabled = drawn;
                if (!drawn) continue;
                pips[i].rectTransform.anchoredPosition = new Vector2(pipsX + 7.5f + i * 21f, 0f);
                pips[i].color = i < levels ? accent : UiKit.WithAlpha(UiKit.Light, 0.25f);
            }
            PipsLit = maxLevels > 0 ? levels : 0;
            PipsDrawn = maxLevels;
            float width = maxLevels > 0 ? pipsX + maxLevels * 21f + 14f : 64f + textWidth + 26f;
            speedRect.sizeDelta = new Vector2(width, ChipHeight);
        }

        private void SetShield(double left, double duration, Color accent, float dt)
        {
            float fill = duration > 1e-6 ? Mathf.Clamp01((float)(left / duration)) : 1f;
            shieldRing.fillAmount = fill;
            pulse += dt;
            float warn = left < ShieldWarnSeconds ? 0.5f + 0.5f * Mathf.Sin(pulse * Mathf.PI * 2f * 4f) : 1f;
            shieldRing.color = UiKit.WithAlpha(accent, 0.55f + 0.45f * warn);
            shieldIcon.color = UiKit.WithAlpha(UiKit.Light, 0.7f + 0.3f * warn);
            long key = (long)Math.Ceiling(left * 10.0 - 1e-6) * 4 + Strings.Language;
            if (key == shieldKey) return;
            shieldKey = key;
            shieldText.text = Strings.Format("hud.seconds", Strings.Decimal(Math.Max(0.0, Math.Ceiling(left * 10.0 - 1e-6) / 10.0), 1));
            float width = 70f + shieldText.preferredWidth + 24f;
            shieldRect.sizeDelta = new Vector2(width, ChipHeight);
        }

        private RectTransform Chip(string name, out CanvasGroup group)
        {
            RectTransform chip = UiKit.Rect(name, root);
            chip.anchorMin = chip.anchorMax = new Vector2(0f, 0.5f);
            chip.pivot = new Vector2(0f, 0.5f);
            chip.sizeDelta = new Vector2(200f, ChipHeight);
            group = chip.gameObject.AddComponent<CanvasGroup>();
            group.interactable = false;
            group.blocksRaycasts = false;
            Image bg = UiKit.Rounded(chip, "Background", UiKit.WithAlpha(UiKit.Navy, 0.8f), ChipHeight * 0.5f);
            UiKit.Stretch(bg.rectTransform);
            return chip;
        }
    }
}
