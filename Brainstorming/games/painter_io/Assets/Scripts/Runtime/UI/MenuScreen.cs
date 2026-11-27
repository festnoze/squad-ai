// Owned by BI since wave B-2 (written by B4). Contract 15.2 and 25.1: the menu over the attract match. Title "Painter.io" in big rounded coral letters with a glossy
// look (layered highlight and navy shadow copies), 4 round color swatches (Palette.HumanColor), a big "JOUER" button, a small
// Options button and the best score line ("Meilleur : 34 % · 5 victoires", from SaveData). No opaque background: the attract
// match runs behind, with soft navy gradients at the top and bottom for legibility. Contract 25.1: three biome cards
// (Liquide, Feu, Électricité) with a small animated procedural preview each; the selected card is highlighted, and a pick
// calls GameDirector.SelectBiome (saved, applied at once to the attract match behind the menu). The swatches and the JOUER
// button show the current biome's colors.
//
// Wave C: the cards sit in a CardRow scaled down when a horizontal safe-area inset leaves less than its width (robust-08);
// a soft navy CardsScrim behind the cards and the swatches and opaque unselected card faces keep the attract puddles out
// of the picker (feel-06); a full-screen AttractCover fades the ended attract board to navy and the next match back in
// (rules-11); only the selected card's preview animates, at 15 repaints per second (perf-08).
//
// Wave D F1 (logo): the title is the Painter.io wordmark image of the current biome (Resources/UI/logo_<biome>.png, made
// by tools/logo/make_logo.py), in the title's place. A biome change crossfades to the new variant (the new image fades in
// over the old one, so the logo never turns see-through); idle, the logo breathes very slightly and a soft shine sweeps
// across the letters every few seconds (a band masked by Resources/UI/logo_mask.png). The text title stays as the
// fallback, shown only when no logo texture loads.
//
// Wave D-2 (traits-ui, docs/BIOME_TRAITS.md sections 5 and 7.2): each biome card shows the icons of its active traits
// (TraitChipRow, over the bottom of its preview), and the rules of the selected biome are listed under the cards
// (BiomeRulesView: icon, name and a one-line description per trait; "Regles classiques" when the biome rules are off).
// The sets come from BiomeTraitTable.Resolve (defaults, saved matrix, command line, master switch) and are refreshed on
// Relabel (SaveData.Changed) and when the selection changes. To make room, the color picker, JOUER, Options and the
// best line moved down (the gaps between them are tighter; the cards and the title are unchanged).
//
// Rule v1.7 (contract 31, countries first): the "Pays" button is gone; JOUER opens the country screen (EuropeScreen: the
// map and the progression), where "Jouer ce pays" starts the round. The classic square arena is not reachable from here.
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    public sealed class MenuScreen : UiScreen
    {
        /// <summary>Title center below the safe top and its rect height.</summary>
        public const float TitleY = 340f;
        public const float TitleHeight = 240f;
        /// <summary>
        /// Gate C: on screens taller than 9:16 (Expand gives a canvas taller than 1920), the title moves down by this share
        /// of the extra height, so the empty band between the title and the 'Biome' label is split above and below it.
        /// 9:16, landscape and square screens are unchanged.
        /// </summary>
        public const float TallTitleShare = 0.5f;
        public const float SwatchSize = 120f;
        public const float SwatchSpacing = 176f;
        /// <summary>Wave D-2: swatch row center above the safe bottom (was 790, moved down for the rules list).</summary>
        public const float SwatchY = 655f;
        /// <summary>Wave D-2: 'Ta couleur' label, JOUER, Options and best line centers above the safe bottom.</summary>
        public const float ColorLabelY = 765f;
        public const float PlayY = 455f;
        public const float OptionsY = 270f;
        public const float BestY = 145f;
        /// <summary>
        /// Wave D-2: the rules list of the selected biome, center above the safe bottom and size (5 rows of 36 plus the
        /// padding of its backing panel), between the cards (selected bottom at about 1010) and the color label (top 795).
        /// </summary>
        public const float RulesY = 900f;
        public const float RulesWidth = 1000f;
        public const float RulesHeight = 200f;
        /// <summary>Wave D-2: trait chips of a card, center below the card face's top (over the preview's bottom edge).</summary>
        public const float CardChipsY = -142f;
        /// <summary>Opacity of the trait chips of an unselected card.</summary>
        public const float UnselectedChipAlpha = 0.72f;
        public const float CardWidth = 290f;
        public const float CardHeight = 250f;
        public const float CardSpacing = 320f;
        public const float CardsY = 1150f;
        /// <summary>Rim width of a card (outside its face).</summary>
        public const float CardRim = 7f;
        /// <summary>Scale of the selected card.</summary>
        public const float SelectedCardScale = 1.06f;
        /// <summary>Full width of the card row with the selected card scaled up, rims included (2 x 481).</summary>
        public const float CardRowWidth = 962f;
        /// <summary>Minimum margin kept between the card row and the safe area's sides (both sides together).</summary>
        public const float CardRowMargin = 32f;
        /// <summary>Repaints per second of the selected card's preview (the unselected cards show a still frame).</summary>
        public const float PreviewRepaintsPerSecond = 15f;
        /// <summary>Height of the 'Biome' label above the cards.</summary>
        public const float BiomeLabelHeight = 60f;
        /// <summary>CardsScrim: navy alpha, extent below the swatch row and above the 'Biome' label (reference units).</summary>
        public const float ScrimAlpha = 0.45f;
        public const float ScrimBelowSwatches = 40f;
        public const float ScrimAboveLabel = 30f;
        /// <summary>AttractCover: navy alpha over an ended attract board, fade time, and hold after the restart.</summary>
        public const float AttractCoverMax = 0.85f;
        public const float AttractCoverFadeSeconds = 0.5f;
        public const float AttractCoverRestartHold = 0.2f;
        /// <summary>
        /// The cover seals to fully opaque over this time, starting this long before GameSession.AttractRestartDelay
        /// elapses, so the board swap itself is never seen (the last 15 % of the old board would otherwise vanish in
        /// one frame).
        /// </summary>
        public const float AttractCoverSealSeconds = 0.3f;
        public const float AttractCoverSealLead = 0.45f;

        /// <summary>Wave D F1: Resources path prefix of the wordmark images (logo_liquid, logo_fire, logo_electric).</summary>
        public const string LogoResourcePrefix = "UI/logo_";
        /// <summary>Resources path of the shine mask (the letters and the pearl, without shadow or glow).</summary>
        public const string LogoMaskResource = "UI/logo_mask";
        /// <summary>Logo rect (reference units), centered where the text title is; the textures are 1600 x 640.</summary>
        public const float LogoWidth = 1000f;
        public const float LogoHeight = 400f;
        /// <summary>Seconds of the crossfade to the new biome's variant.</summary>
        public const float LogoCrossfadeSeconds = 0.35f;
        /// <summary>Idle: one breath (scale 1 +/- LogoBreathAmount) every LogoBreathSeconds.</summary>
        public const float LogoBreathSeconds = 3.6f;
        public const float LogoBreathAmount = 0.012f;
        /// <summary>Idle shine: a sweep of LogoShineSweepSeconds every LogoShinePeriodSeconds, the first one after the delay.</summary>
        public const float LogoShinePeriodSeconds = 5.5f;
        public const float LogoShineSweepSeconds = 1.1f;
        public const float LogoShineFirstDelay = 2.6f;
        public const float LogoShineAlpha = 0.42f;

        private sealed class Card
        {
            public BiomeId Biome;
            public RectTransform Root;
            public Image Rim, Face, Preview;
            public Text Name;
            public BiomePreview Painter;
            public bool WasSelected;
            public TraitChipRow Chips;
            public float ChipAlpha = -1f;
        }

        private readonly Card[] cards = new Card[BiomeTheme.Count];
        // Wave D-2: the resolved trait set of each biome (BiomeTraitTable.Resolve), refreshed by RefreshTraits.
        private readonly List<TraitSpec>[] biomeTraits = new List<TraitSpec>[BiomeTheme.Count];
        private bool classicRules;
        private BiomeRulesView rules;
        private BiomeId rulesBiome;
        private bool rulesShown;
        private float rulesWidthSeen = -1f;
        private readonly Text biomeLabel;
        private readonly RectTransform cardRow;
        private float cardRowWidthSeen = -1f;
        private float titleHeightSeen = -1f;
        private float previewClock, previewTimer;

        // Attract cover (rules-11).
        private readonly Image attractCover;
        private float coverAlpha;
        private Simulation coverSim;
        private float sinceRestart = float.PositiveInfinity;
        private float sinceEnded;

        private static readonly Color TitleCoral = new Color32(0xF2, 0x67, 0x4F, 0xFF);
        private static readonly Color TitleHighlight = new Color32(0xFF, 0xC9, 0xBC, 0xFF);

        private readonly Text[] titleLayers = new Text[3];
        /// <summary>Vertical offsets of the title layers (shadow, highlight, face) from the title line.</summary>
        private static readonly float[] TitleLayerOffsetY = { -12f, 4f, 0f };

        // Logo (wave D F1).
        private readonly RectTransform logoRoot;
        private readonly Image logoBack, logoFront;
        private readonly RectTransform shineBand;
        private readonly Image shineImage;
        private readonly Sprite[] logoSprites = new Sprite[BiomeTheme.Count];
        private bool logoLoaded;
        private BiomeId logoBiome;
        private bool logoBiomeKnown;
        private float logoFade = 1f;
        private float logoClock;
        private readonly Text colorLabel, bestLine, playLabel, optionsLabel;
        private readonly Image playBg;
        private readonly RectTransform playRect;
        private readonly Image[] swatches = new Image[4];
        private readonly Image[] swatchRings = new Image[4];
        private float playPulse;
        private bool interactable = true;

        public MenuScreen(UiRoot root) : base(root, "Menu", UiRoot.MenuOrder)
        {
            // Legibility gradients over the attract match (whole screen width, outside the safe area).
            Image top = UiKit.Img(CanvasRect, "TopShade", UiKit.GradientSprite, UiKit.WithAlpha(UiKit.Navy, 0.62f));
            RectTransform tr = top.rectTransform;
            tr.anchorMin = new Vector2(0f, 0.62f);
            tr.anchorMax = new Vector2(1f, 1f);
            tr.offsetMin = tr.offsetMax = Vector2.zero;
            tr.SetAsFirstSibling();
            Image bottom = UiKit.Img(CanvasRect, "BottomShade", UiKit.GradientSprite, UiKit.WithAlpha(UiKit.Navy, 0.8f));
            RectTransform br = bottom.rectTransform;
            br.anchorMin = new Vector2(0f, 0f);
            br.anchorMax = new Vector2(1f, 0.56f);
            br.offsetMin = br.offsetMax = Vector2.zero;
            br.localEulerAngles = new Vector3(0f, 0f, 180f);
            br.SetSiblingIndex(1);

            // rules-11: navy cover over the world (under the shades and the content), faded in over an ended attract board.
            attractCover = UiKit.FullScreen(CanvasRect, "AttractCover", UiKit.WithAlpha(UiKit.Navy, 0f), false);
            attractCover.rectTransform.SetAsFirstSibling();
            attractCover.enabled = false;

            // feel-06: soft navy scrim behind the 'Biome' label, the cards, the color label and the swatches, on the same
            // BottomCenter references as those elements, as wide as the whole canvas (it overhangs the safe area's sides)
            // and drawn first in the safe area so every content element sits on top of it.
            float scrimBottom = SwatchY - (SwatchSize + 34f) * 0.5f - ScrimBelowSwatches;
            float scrimTop = CardsY + CardHeight * 0.5f + 52f + BiomeLabelHeight * 0.5f + ScrimAboveLabel;
            Image scrim = UiKit.Img(Safe, "CardsScrim", UiKit.SoftBandSprite, UiKit.WithAlpha(UiKit.Navy, ScrimAlpha));
            scrim.type = Image.Type.Sliced;
            scrim.fillCenter = true;
            RectTransform sr = scrim.rectTransform;
            sr.anchorMin = new Vector2(0f, 0f);
            sr.anchorMax = new Vector2(1f, 0f);
            sr.pivot = new Vector2(0.5f, 0f);
            sr.offsetMin = new Vector2(-UiKit.RefWidth, scrimBottom - UiKit.SoftBandFeatherPixels);
            sr.offsetMax = new Vector2(UiKit.RefWidth, scrimTop + UiKit.SoftBandFeatherPixels);
            sr.SetAsFirstSibling();

            // Title: navy shadow, light highlight (peeks out at the upper left like the liquid's specular rim), coral face.
            Vector2[] offsets = { new Vector2(6f, TitleLayerOffsetY[0]), new Vector2(-4f, TitleLayerOffsetY[1]), new Vector2(0f, TitleLayerOffsetY[2]) };
            Color[] colors = { UiKit.WithAlpha(UiKit.Navy, 0.85f), TitleHighlight, TitleCoral };
            for (int i = 0; i < 3; i++)
            {
                Text t = UiKit.Label(Safe, "Title" + i, 172, colors[i], TextAnchor.MiddleCenter, false, true);
                UiKit.Place(t.rectTransform, UiKit.TopCenter, new Vector2(0f, -TitleY) + offsets[i], new Vector2(1000f, TitleHeight));
                titleLayers[i] = t;
            }

            // Wave D F1: the wordmark image in the title's place (the text layers above stay as the fallback).
            logoRoot = UiKit.Rect("Logo", Safe);
            UiKit.Place(logoRoot, UiKit.TopCenter, new Vector2(0f, -TitleY), new Vector2(LogoWidth, LogoHeight));
            logoBack = UiKit.Img(logoRoot, "LogoBack", null, Color.white);
            logoFront = UiKit.Img(logoRoot, "LogoFront", null, Color.white);
            logoBack.preserveAspect = logoFront.preserveAspect = true;
            UiKit.Stretch(logoBack.rectTransform);
            UiKit.Stretch(logoFront.rectTransform);
            Sprite mask = LoadLogoSprite(LogoMaskResource);
            if (mask != null)
            {
                Image maskImage = UiKit.Img(logoRoot, "LogoShineMask", mask, Color.white);
                maskImage.preserveAspect = true;
                UiKit.Stretch(maskImage.rectTransform);
                maskImage.gameObject.AddComponent<Mask>().showMaskGraphic = false;
                shineImage = UiKit.Img(maskImage.transform, "Shine", UiKit.ShineSprite, UiKit.WithAlpha(Color.white, 0f));
                shineBand = shineImage.rectTransform;
                UiKit.Place(shineBand, UiKit.Center, Vector2.zero, new Vector2(LogoHeight * 0.26f, LogoHeight * 1.7f));
                shineBand.localEulerAngles = new Vector3(0f, 0f, -24f);
            }
            for (int i = 0; i < logoSprites.Length; i++) logoSprites[i] = LoadLogoSprite(LogoResourcePrefix + BiomeTheme.CommandNameOf((BiomeId)i));
            BindLogo(BiomeTheme.Current.Id, true);
            BiomeTheme.Changed += OnBiomeChanged;

            // Biome cards (25.1): name and an animated preview each, the selected one highlighted.
            biomeLabel = UiKit.Label(Safe, "BiomeLabel", 40, UiKit.WithAlpha(UiKit.Light, 0.85f), TextAnchor.MiddleCenter);
            UiKit.Place(biomeLabel.rectTransform, UiKit.BottomCenter, new Vector2(0f, CardsY + CardHeight * 0.5f + 52f), new Vector2(800f, BiomeLabelHeight));
            // robust-08: the three cards live in one row, scaled down only when the safe area is narrower than the row.
            cardRow = UiKit.Rect("CardRow", Safe);
            UiKit.Place(cardRow, UiKit.BottomCenter, new Vector2(0f, CardsY), new Vector2(CardRowWidth, CardHeight));
            BiomeId selectedAtStart = BiomeTheme.Current.Id;
            for (int i = 0; i < cards.Length; i++)
            {
                var biome = (BiomeId)i;
                var card = new Card { Biome = biome, WasSelected = biome == selectedAtStart };
                float x = (i - (cards.Length - 1) * 0.5f) * CardSpacing;
                card.Root = UiKit.Rect("BiomeCard" + i, cardRow);
                UiKit.Place(card.Root, UiKit.Center, new Vector2(x, 0f), new Vector2(CardWidth, CardHeight));
                Image shadow = UiKit.Rounded(card.Root, "Shadow", UiKit.WithAlpha(UiKit.Navy, 0.55f), 40f);
                UiKit.Stretch(shadow.rectTransform);
                shadow.rectTransform.offsetMin = new Vector2(-2f, -12f);
                shadow.rectTransform.offsetMax = new Vector2(2f, -4f);
                card.Rim = UiKit.Rounded(card.Root, "Rim", UiKit.Light, 42f);
                UiKit.Stretch(card.Rim.rectTransform);
                card.Rim.rectTransform.offsetMin = new Vector2(-CardRim, -CardRim);
                card.Rim.rectTransform.offsetMax = new Vector2(CardRim, CardRim);
                Button b = UiKit.Btn(card.Root, "Face", new Vector2(CardWidth, CardHeight), UiKit.PanelNavy, 36f, 0, UiKit.Light,
                                     () => PickBiome(biome), out _);
                UiKit.Stretch((RectTransform)b.transform);
                card.Face = (Image)b.targetGraphic;
                card.Painter = new BiomePreview(biome);   // paints its first (still) frame
                card.Preview = UiKit.Img(b.transform, "Preview", card.Painter.Sprite, Color.white);
                UiKit.Place(card.Preview.rectTransform, new Vector2(0.5f, 1f), new Vector2(0f, -22f - 73f), new Vector2(240f, 146f));
                card.Name = UiKit.Label(b.transform, "Name", 42, UiKit.Light, TextAnchor.MiddleCenter);
                UiKit.Place(card.Name.rectTransform, new Vector2(0.5f, 0f), new Vector2(0f, 42f), new Vector2(CardWidth, 60f));
                // Wave D-2: the biome's active traits as small icons over the bottom edge of the preview.
                card.Chips = new TraitChipRow(b.transform, "Traits", UiKit.TopCenter, new Vector2(0f, CardChipsY));
                cards[i] = card;
            }
            // Wave D-2: the rules of the selected biome, between the cards and the color picker.
            rules = new BiomeRulesView(Safe, UiKit.BottomCenter, new Vector2(0f, RulesY), new Vector2(RulesWidth, RulesHeight));
            // Color picker.
            colorLabel = UiKit.Label(Safe, "ColorLabel", 40, UiKit.WithAlpha(UiKit.Light, 0.85f), TextAnchor.MiddleCenter);
            UiKit.Place(colorLabel.rectTransform, UiKit.BottomCenter, new Vector2(0f, ColorLabelY), new Vector2(800f, 60f));
            for (int i = 0; i < 4; i++)
            {
                int colorIndex = i;
                float x = (i - 1.5f) * SwatchSpacing;
                Image ringImg = UiKit.Img(Safe, "SwatchRing" + i, UiKit.RingSprite, UiKit.Light);
                UiKit.Place(ringImg.rectTransform, UiKit.BottomCenter, new Vector2(x, SwatchY), new Vector2(SwatchSize + 34f, SwatchSize + 34f));
                swatchRings[i] = ringImg;
                Button b = UiKit.Btn(Safe, "Swatch" + i, new Vector2(SwatchSize, SwatchSize), Palette.ColorAt(i), SwatchSize * 0.5f, 0,
                                     UiKit.Light, () => PickColor(colorIndex), out _);
                Image img = (Image)b.targetGraphic;
                img.sprite = UiKit.CircleSprite;
                img.type = Image.Type.Simple;
                UiKit.Place((RectTransform)b.transform, UiKit.BottomCenter, new Vector2(x, SwatchY), new Vector2(SwatchSize, SwatchSize));
                // A small specular dot so the swatches read as paint drops.
                Image glint = UiKit.Img(b.transform, "Glint", UiKit.CircleSprite, new Color(1f, 1f, 1f, 0.55f));
                UiKit.Place(glint.rectTransform, UiKit.Center, new Vector2(-24f, 26f), new Vector2(26f, 20f));
                swatches[i] = img;
            }

            // JOUER (rimmed so it stays readable over an attract puddle of the same color).
            playRect = UiKit.PrimaryButton(Safe, "Play", new Vector2(600f, 176f), Palette.ColorOf(0), 84, OnPlay, out playBg, out playLabel);
            UiKit.Place(playRect, UiKit.BottomCenter, new Vector2(0f, PlayY), new Vector2(600f, 176f));

            // Options (small, centered: rule v1.7 removed the "Pays" button, JOUER opens the countries) and the best line.
            Image optionsShadow = UiKit.Rounded(Safe, "OptionsShadow", UiKit.WithAlpha(UiKit.Navy, 0.55f), 54f);
            UiKit.Place(optionsShadow.rectTransform, UiKit.BottomCenter, new Vector2(0f, OptionsY - 8f), new Vector2(344f, 108f));
            Button options = UiKit.Btn(Safe, "Options", new Vector2(340f, 104f), UiKit.NavyLight, 52f, 44,
                                       UiKit.Light, OnOptions, out optionsLabel);
            UiKit.Place((RectTransform)options.transform, UiKit.BottomCenter, new Vector2(0f, OptionsY), new Vector2(340f, 104f));
            bestLine = UiKit.Label(Safe, "Best", 40, UiKit.WithAlpha(UiKit.Light, 0.9f), TextAnchor.MiddleCenter);
            UiKit.Place(bestLine.rectTransform, UiKit.BottomCenter, new Vector2(0f, BestY), new Vector2(1000f, 60f));
            RefreshTraits();
        }

        public void SetInteractable(bool value)
        {
            interactable = value;
        }

        protected override bool AcceptsInput => interactable;

        public override void Relabel()
        {
            string title = Strings.Get("menu.title");
            for (int i = 0; i < titleLayers.Length; i++) titleLayers[i].text = title;
            ApplyTitleFallback();   // the text title is only the fallback of the logo
            colorLabel.text = Strings.Get("menu.color");
            biomeLabel.text = Strings.Get("menu.biome");
            for (int i = 0; i < cards.Length; i++)
            {
                if (cards[i] != null) cards[i].Name.text = Strings.Get(BiomeTheme.Get(cards[i].Biome).NameKey);
            }
            playLabel.text = Strings.Get("menu.play");
            optionsLabel.text = Strings.Get("menu.options");
            int wins = SaveData.Wins;
            bestLine.text = Strings.Format("menu.best", Strings.Area(SaveData.BestArea), Strings.Count("menu.wins", wins));
            RefreshTraits();   // SaveData.Changed (biome rules toggle, trait matrix, language) triggers a relabel
        }

        // ------------------------------------------------------------------------------------------------------------
        // Biome traits (wave D-2).

        /// <summary>The enabled traits of a biome as the menu shows them (BiomeTraitTable.Resolve at the last refresh).</summary>
        internal List<TraitSpec> TraitsShown(BiomeId biome)
        {
            List<TraitSpec> l = biomeTraits[(int)BiomeTheme.Clamp((int)biome)];
            return l ?? new List<TraitSpec>();
        }

        /// <summary>True when the menu shows "Regles classiques" (biome rules off or -classic).</summary>
        internal bool ClassicRulesShown => classicRules;

        /// <summary>The rules list under the cards (tests).</summary>
        internal BiomeRulesView Rules => rules;

        /// <summary>The trait chips of a biome card (tests).</summary>
        internal TraitChipRow ChipsOf(BiomeId biome)
        {
            Card c = cards[(int)BiomeTheme.Clamp((int)biome)];
            return c != null ? c.Chips : null;
        }

        /// <summary>
        /// Re-reads every biome's trait set (BiomeTraitTable.Resolve: table, saved matrix, command line, master switch) and
        /// redraws the card chips and the rules list. Called at construction and on every Relabel.
        /// </summary>
        public void RefreshTraits()
        {
            classicRules = !SaveData.BiomeRulesOn || LaunchArgs.Classic;
            for (int i = 0; i < biomeTraits.Length; i++)
            {
                List<TraitSpec> specs;
                try
                {
                    specs = classicRules ? new List<TraitSpec>() : TraitText.Enabled(BiomeTraitTable.Resolve((BiomeId)i));
                }
                catch (System.Exception e)
                {
                    Debug.LogWarning("[PainterIO] menu traits of " + (BiomeId)i + " failed: " + e.Message);
                    specs = new List<TraitSpec>();
                }
                biomeTraits[i] = specs;
                if (cards[i] != null) cards[i].ChipAlpha = -1f;   // redraw
            }
            rulesShown = false;
            TickTraits();
        }

        /// <summary>Card chips (dimmed on unselected cards) and the rules list of the selected biome.</summary>
        private void TickTraits()
        {
            BiomeId selected = BiomeTheme.Current.Id;
            for (int i = 0; i < cards.Length; i++)
            {
                Card c = cards[i];
                if (c == null || c.Chips == null) continue;
                float alpha = c.Biome == selected ? 1f : UnselectedChipAlpha;
                if (Mathf.Abs(alpha - c.ChipAlpha) < 1e-4f) continue;
                c.ChipAlpha = alpha;
                c.Chips.Show(biomeTraits[i], alpha);
            }
            if (rules == null || (rulesShown && rulesBiome == selected)) return;
            rulesBiome = selected;
            rulesShown = true;
            rules.Show(biomeTraits[(int)selected], classicRules);
        }

        public override void Tick(float dt)
        {
            int h = Palette.HumanColor;
            for (int i = 0; i < 4; i++)
            {
                bool sel = i == h;
                float target = sel ? 1.12f : 0.92f;
                RectTransform rt = swatches[i].rectTransform;
                float s = Mathf.MoveTowards(rt.localScale.x, target, dt * 2.5f);
                rt.localScale = new Vector3(s, s, 1f);
                swatchRings[i].enabled = sel;
                swatchRings[i].rectTransform.localScale = new Vector3(s, s, 1f);
                swatches[i].color = Palette.ColorAt(i);
            }
            playBg.color = Palette.ColorAt(h);
            FitCardRow();
            TickCards(dt);
            TickTraits();
            TickLogo(dt);
            TickAttractCover(dt);
            playPulse += dt;
            float p = 1f + 0.025f * Mathf.Sin(playPulse * 2.6f);
            playRect.localScale = new Vector3(p, p, 1f);
        }

        protected override void OnShow()
        {
            // Shown from another state: the cover starts clear and tracks the current attract simulation.
            coverAlpha = 0f;
            sinceRestart = float.PositiveInfinity;
            sinceEnded = 0f;
            GameSession s = Session;
            coverSim = s != null ? s.Sim : null;
            ApplyCover();
        }

        /// <summary>
        /// robust-08: scale of the card row for a safe area of the given width (reference units): 1 when the row and its
        /// margin fit, smaller when a horizontal inset leaves less room. Unknown widths give 1.
        /// </summary>
        internal static float CardRowScale(float safeWidth)
        {
            if (!(safeWidth > 1f)) return 1f;
            return Mathf.Clamp(Mathf.Min(1f, (safeWidth - CardRowMargin) / CardRowWidth), 0.1f, 1f);
        }

        /// <summary>
        /// Gate C: the title's distance below the safe top for a safe area of the given height (reference units): TitleY up
        /// to the 1920 design height, then TitleY plus TallTitleShare of the extra height. Unknown heights give TitleY.
        /// </summary>
        internal static float TitleYFor(float safeHeight)
        {
            if (!(safeHeight > UiKit.RefHeight) || float.IsInfinity(safeHeight)) return TitleY;
            return TitleY + (safeHeight - UiKit.RefHeight) * TallTitleShare;
        }

        private void FitCardRow()
        {
            float h = Safe.rect.height;
            if (Mathf.Abs(h - titleHeightSeen) >= 0.01f)
            {
                titleHeightSeen = h;
                float y = TitleYFor(h);
                for (int i = 0; i < titleLayers.Length; i++)
                {
                    if (titleLayers[i] == null) continue;
                    RectTransform rt = titleLayers[i].rectTransform;
                    rt.anchoredPosition = new Vector2(rt.anchoredPosition.x, -y + TitleLayerOffsetY[i]);
                }
                if (logoRoot != null) logoRoot.anchoredPosition = new Vector2(0f, -y);
            }
            float w = Safe.rect.width;
            if (rules != null && w > 1f && Mathf.Abs(w - rulesWidthSeen) >= 0.01f)
            {
                // Wave D-2: the rules list keeps a margin inside a narrow safe area (it scales its rows to fit).
                rulesWidthSeen = w;
                rules.Rect.sizeDelta = new Vector2(Mathf.Min(RulesWidth, w - CardRowMargin), RulesHeight);
                rulesShown = false;
            }
            if (Mathf.Abs(w - cardRowWidthSeen) < 0.01f) return;
            cardRowWidthSeen = w;
            float s = CardRowScale(w);
            cardRow.localScale = new Vector3(s, s, 1f);
        }

        /// <summary>
        /// rules-11: the cover alpha for one frame. While the attract round has ended it rises to AttractCoverMax over
        /// AttractCoverFadeSeconds; after the restart it holds for AttractCoverRestartHold seconds (the territory field
        /// rebuilds), then falls to 0 at the same rate. secondsSinceRestart is +infinity when no restart is pending.
        /// </summary>
        internal static float AttractCoverAlpha(bool ended, float secondsSinceRestart, float current, float dt)
        {
            return AttractCoverAlpha(ended, 0f, secondsSinceRestart, current, dt);
        }

        /// <summary>
        /// AttractCoverAlpha with the seal: once the round has been over for GameSession.AttractRestartDelay minus
        /// AttractCoverSealLead seconds, the cover goes on from AttractCoverMax to fully opaque over AttractCoverSealSeconds,
        /// so the restart swaps the board under an opaque cover.
        /// </summary>
        internal static float AttractCoverAlpha(bool ended, float secondsSinceEnded, float secondsSinceRestart, float current, float dt)
        {
            dt = Mathf.Max(0f, dt);
            float step = dt * AttractCoverMax / AttractCoverFadeSeconds;
            if (ended)
            {
                float a = Mathf.MoveTowards(current, AttractCoverMax, step);
                bool seal = secondsSinceEnded >= GameSession.AttractRestartDelay - AttractCoverSealLead;
                if (seal && current >= AttractCoverMax - 1e-4f)
                    a = Mathf.MoveTowards(current, 1f, dt * (1f - AttractCoverMax) / AttractCoverSealSeconds);
                return a;
            }
            if (secondsSinceRestart < AttractCoverRestartHold) return current;
            return Mathf.MoveTowards(current, 0f, step);
        }

        private void TickAttractCover(float dt)
        {
            if (!Visible) return;
            GameSession s = Session;
            bool ended = false;
            if (s != null && s.IsAttract && !s.IsClosed)
            {
                Simulation sim = s.Sim;
                if (sim != coverSim)
                {
                    // A new Simulation: GameSession.RestartAttract swapped it (or the menu got a new attract session).
                    if (coverSim != null) sinceRestart = 0f;
                    coverSim = sim;
                }
                ended = sim != null && sim.Ended;
            }
            if (sinceRestart < float.PositiveInfinity) sinceRestart += dt;
            sinceEnded = ended ? sinceEnded + dt : 0f;
            coverAlpha = AttractCoverAlpha(ended, sinceEnded, sinceRestart, coverAlpha, dt);
            if (!ended && coverAlpha <= 0f) sinceRestart = float.PositiveInfinity;
            ApplyCover();
        }

        private void ApplyCover()
        {
            attractCover.color = UiKit.WithAlpha(UiKit.Navy, coverAlpha);
            attractCover.enabled = coverAlpha > 0.002f;
        }

        /// <summary>The cover alpha (tests, probe).</summary>
        internal float AttractCoverValue => coverAlpha;

        /// <summary>Paint calls received by a biome card's preview since it was built (tests).</summary>
        internal int PreviewPaintCount(BiomeId biome)
        {
            Card c = cards[(int)biome];
            return c != null && c.Painter != null ? c.Painter.PaintCount : 0;
        }

        /// <summary>
        /// The biome cards: the selected one is scaled up with a light rim, the others are dimmed on an opaque face. Only
        /// the selected preview animates (PreviewRepaintsPerSecond); a card that loses the selection repaints once and then
        /// keeps that still frame.
        /// </summary>
        private void TickCards(float dt)
        {
            BiomeId selected = BiomeTheme.Current.Id;
            Card animated = null;
            for (int i = 0; i < cards.Length; i++)
            {
                Card c = cards[i];
                if (c == null) continue;
                bool sel = c.Biome == selected;
                float s = Mathf.MoveTowards(c.Root.localScale.x, sel ? SelectedCardScale : 0.94f, dt * 1.5f);
                c.Root.localScale = new Vector3(s, s, 1f);
                c.Rim.enabled = sel;
                c.Face.color = sel ? UiKit.NavyLight : UiKit.PanelNavy;
                c.Preview.color = sel ? Color.white : new Color(0.72f, 0.72f, 0.78f, 1f);
                c.Name.color = sel ? UiKit.Light : UiKit.WithAlpha(UiKit.Light, 0.7f);
                if (c.WasSelected && !sel && c.Painter != null) c.Painter.Paint(previewClock);
                c.WasSelected = sel;
                if (sel) animated = c;
            }
            if (!Visible) return;
            previewClock += dt;
            previewTimer += dt;
            const float interval = 1f / PreviewRepaintsPerSecond;
            if (previewTimer + 1e-4f < interval) return;
            previewTimer = Mathf.Min(previewTimer - interval, interval);
            if (previewTimer < 0f) previewTimer = 0f;
            if (animated != null && animated.Painter != null) animated.Painter.Paint(previewClock);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Logo (wave D F1).

        /// <summary>True when a logo texture loaded and is shown instead of the text title (tests, probe).</summary>
        internal bool LogoShown => logoLoaded && logoFront != null && logoFront.enabled && logoFront.sprite != null;

        /// <summary>The biome whose variant the logo shows or fades to (tests).</summary>
        internal BiomeId LogoBiome => logoBiome;

        /// <summary>The front layer's crossfade progress, 1 when settled (tests).</summary>
        internal float LogoFade => logoFade;

        /// <summary>
        /// The idle shine position for a clock value: -1 before a sweep (band off the left side), 0..1 across the logo
        /// during a sweep, 2 between sweeps. First sweep after LogoShineFirstDelay, then one every LogoShinePeriodSeconds.
        /// </summary>
        internal static float ShinePhase(float clock)
        {
            if (!(clock >= LogoShineFirstDelay)) return -1f;
            float t = (clock - LogoShineFirstDelay) % LogoShinePeriodSeconds;
            return t < LogoShineSweepSeconds ? t / LogoShineSweepSeconds : 2f;
        }

        /// <summary>A Resources sprite, or a sprite made from the texture when it was imported as a plain texture.</summary>
        private static Sprite LoadLogoSprite(string path)
        {
            try
            {
                Sprite s = Resources.Load<Sprite>(path);
                if (s != null) return s;
                Texture2D tex = Resources.Load<Texture2D>(path);
                if (tex == null) return null;
                s = Sprite.Create(tex, new UnityEngine.Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect);
                s.name = tex.name;
                return s;
            }
            catch (System.Exception e)
            {
                Debug.LogWarning("[PainterIO] logo " + path + " failed to load: " + e.Message);
                return null;
            }
        }

        private Sprite LogoSpriteFor(BiomeId biome)
        {
            int k = (int)biome;
            Sprite s = k >= 0 && k < logoSprites.Length ? logoSprites[k] : null;
            return s != null ? s : logoSprites[(int)BiomeId.Liquid];
        }

        /// <summary>Shows the biome's variant: at once, or by fading it in over the current one.</summary>
        private void BindLogo(BiomeId biome, bool instant)
        {
            if (logoFront == null) return;
            if (logoBiomeKnown && biome == logoBiome) return;
            Sprite next = LogoSpriteFor(biome);
            logoBiome = biome;
            logoBiomeKnown = true;
            bool wasLoaded = logoLoaded;
            logoLoaded = next != null;
            if (!logoLoaded)
            {
                logoFront.enabled = logoBack.enabled = false;
                if (wasLoaded) ApplyTitleFallback();
                return;
            }
            if (instant || logoFront.sprite == null || logoFront.sprite == next || !Visible)
            {
                logoFront.sprite = next;
                logoFront.enabled = true;
                logoFront.color = Color.white;
                logoBack.enabled = false;
                logoFade = 1f;
            }
            else
            {
                // The old variant stays fully opaque underneath while the new one fades in on top.
                logoBack.sprite = logoFront.sprite;
                logoBack.color = Color.white;
                logoBack.enabled = true;
                logoFront.sprite = next;
                logoFront.color = UiKit.WithAlpha(Color.white, 0f);
                logoFront.enabled = true;
                logoFade = 0f;
            }
            if (!wasLoaded) ApplyTitleFallback();
        }

        /// <summary>The text title is drawn only while no logo texture is shown.</summary>
        private void ApplyTitleFallback()
        {
            for (int i = 0; i < titleLayers.Length; i++)
            {
                if (titleLayers[i] != null) titleLayers[i].enabled = !logoLoaded;
            }
        }

        private void OnBiomeChanged(BiomeTheme theme)
        {
            // The screen may outlive its objects (an EditMode test destroys the UiRoot): unsubscribe then.
            if (logoRoot == null)
            {
                BiomeTheme.Changed -= OnBiomeChanged;
                return;
            }
            if (theme != null) BindLogo(theme.Id, false);
        }

        private void TickLogo(float dt)
        {
            if (logoRoot == null) return;
            if (!logoBiomeKnown || BiomeTheme.Current.Id != logoBiome) BindLogo(BiomeTheme.Current.Id, false);
            if (logoFade < 1f)
            {
                logoFade = Mathf.Min(1f, logoFade + dt / LogoCrossfadeSeconds);
                float a = logoFade * logoFade * (3f - 2f * logoFade);
                logoFront.color = UiKit.WithAlpha(Color.white, a);
                if (logoFade >= 1f) logoBack.enabled = false;
            }
            if (!Visible)
            {
                logoClock = 0f;
                return;
            }
            logoClock += dt;
            float breath = 1f + LogoBreathAmount * Mathf.Sin(logoClock * (2f * Mathf.PI / LogoBreathSeconds));
            logoRoot.localScale = new Vector3(breath, 2f - breath, 1f);
            if (shineBand != null)
            {
                float phase = ShinePhase(logoClock);
                bool on = logoLoaded && phase >= 0f && phase <= 1f;
                shineImage.enabled = on;
                if (on)
                {
                    float x = Mathf.Lerp(-LogoWidth * 0.5f - LogoHeight * 0.4f, LogoWidth * 0.5f + LogoHeight * 0.4f, phase);
                    shineBand.anchoredPosition = new Vector2(x, 0f);
                    float fade = Mathf.Sin(phase * Mathf.PI);
                    shineImage.color = UiKit.WithAlpha(Color.white, LogoShineAlpha * fade);
                }
            }
        }

        private void PickBiome(BiomeId biome)
        {
            GameDirector d = Director;
            if (d != null) d.SelectBiome(biome);
            else BiomeTheme.SetCurrent(biome);
        }
        private void PickColor(int colorIndex)
        {
            Palette.HumanColor = colorIndex;
        }

        /// <summary>Rule v1.7 (countries first): JOUER opens the country screen (map and progression), never the square arena.</summary>
        private void OnPlay()
        {
            if (Root != null) Root.OpenEurope();
        }

        private void OnOptions()
        {
            if (Root != null) Root.OpenOptions();
        }
    }
}
