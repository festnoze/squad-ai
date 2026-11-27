// Owned by traits-ui (wave D-2). docs/BIOME_TRAITS.md section 5 (UI) and 7.2 (rule texts gain the kill rewards): the
// menu shows the traits of every biome.
// - TraitChipRow: the small round trait icons on a biome card (navy chip, light icon, saffron rim for the kill rewards of
//   section 7), at most MaxChips, then a "+N" chip.
// - BiomeRulesView: under the cards, the rules of the selected biome, one row per trait: icon, name and its one-line
//   description (TraitText, FR / EN). More traits than MaxDetailedRows (a custom trait matrix) switch to two columns of
//   icon + name. "Regles classiques" (SaveData.BiomeRulesOn off, or -classic) and an empty biome get one line instead.
// Both read only the RuleTraits they are given (MenuScreen passes BiomeTraitTable.Resolve of each biome, refreshed on
// SaveData.Changed); nothing here knows which trait belongs to which biome. Unused texts are disabled, never left blank.
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    /// <summary>The trait icons of one biome card.</summary>
    public sealed class TraitChipRow
    {
        public const float ChipSize = 40f;
        public const float IconSize = 30f;
        public const float Gap = 5f;
        /// <summary>Chips drawn at most; more traits show MaxChips - 1 chips and a "+N" chip.</summary>
        public const int MaxChips = 5;

        private readonly RectTransform root;
        private readonly RectTransform[] chips = new RectTransform[MaxChips];
        private readonly Image[] bgs = new Image[MaxChips];
        private readonly Image[] rims = new Image[MaxChips];
        private readonly Image[] icons = new Image[MaxChips];
        private readonly Text more;
        private int shown;

        public TraitChipRow(Transform parent, string name, Vector2 anchor, Vector2 position)
        {
            root = UiKit.Rect(name, parent);
            UiKit.Place(root, anchor, position, new Vector2(MaxChips * (ChipSize + Gap), ChipSize));
            for (int i = 0; i < MaxChips; i++)
            {
                RectTransform chip = UiKit.Rect("Chip" + i, root);
                UiKit.Place(chip, UiKit.Center, Vector2.zero, new Vector2(ChipSize, ChipSize));
                bgs[i] = UiKit.Img(chip, "Bg", UiKit.CircleSprite, UiKit.WithAlpha(UiKit.Navy, 0.88f));
                UiKit.Stretch(bgs[i].rectTransform);
                rims[i] = UiKit.Img(chip, "Rim", UiKit.RingSprite, UiKit.WithAlpha(UiKit.Light, 0.35f));
                UiKit.Stretch(rims[i].rectTransform);
                icons[i] = UiKit.Img(chip, "Icon", null, UiKit.Light);
                UiKit.Place(icons[i].rectTransform, UiKit.Center, Vector2.zero, new Vector2(IconSize, IconSize));
                chips[i] = chip;
                chip.gameObject.SetActive(false);
            }
            more = UiKit.Label(chips[MaxChips - 1], "More", 22, UiKit.Light, TextAnchor.MiddleCenter, false);
            UiKit.Stretch(more.rectTransform);
            more.enabled = false;
        }

        /// <summary>Number of chips shown (tests).</summary>
        public int ChipCount => shown;

        /// <summary>The "+N" text, or null when every trait has its own chip (tests).</summary>
        public string MoreText => more.enabled ? more.text : null;

        /// <summary>The sprite of chip i (tests).</summary>
        public Sprite IconAt(int i) => i >= 0 && i < MaxChips && chips[i].gameObject.activeSelf ? icons[i].sprite : null;

        /// <summary>Shows the specs' icons, centered, at the given opacity (the unselected cards are dimmed).</summary>
        public void Show(List<TraitSpec> specs, float alpha)
        {
            int count = specs != null ? specs.Count : 0;
            bool overflow = count > MaxChips;
            int chipsUsed = overflow ? MaxChips : count;
            int iconChips = overflow ? MaxChips - 1 : count;
            float width = chipsUsed * ChipSize + Mathf.Max(0, chipsUsed - 1) * Gap;
            for (int i = 0; i < MaxChips; i++)
            {
                bool on = i < chipsUsed;
                if (chips[i].gameObject.activeSelf != on) chips[i].gameObject.SetActive(on);
                if (!on) continue;
                chips[i].anchoredPosition = new Vector2(-width * 0.5f + ChipSize * 0.5f + i * (ChipSize + Gap), 0f);
                bool isMore = i >= iconChips;
                bgs[i].color = UiKit.WithAlpha(UiKit.Navy, 0.88f * alpha);
                icons[i].enabled = !isMore;
                if (!isMore)
                {
                    TraitId id = specs[i].Id;
                    icons[i].sprite = TraitIcons.Get(id);
                    icons[i].color = UiKit.WithAlpha(UiKit.Light, alpha);
                    rims[i].color = TraitText.IsKillReward(id) ? UiKit.WithAlpha(UiKit.Saffron, 0.95f * alpha) : UiKit.WithAlpha(UiKit.Light, 0.35f * alpha);
                }
                else rims[i].color = UiKit.WithAlpha(UiKit.Light, 0.35f * alpha);
            }
            more.enabled = overflow;
            if (overflow)
            {
                more.text = Strings.Format("menu.rules_more", (count - iconChips).ToString(System.Globalization.CultureInfo.InvariantCulture));
                more.color = UiKit.WithAlpha(UiKit.Light, alpha);
            }
            shown = chipsUsed;
        }
    }

    /// <summary>The rules of the selected biome under the menu cards.</summary>
    public sealed class BiomeRulesView
    {
        /// <summary>Rows with their description; more traits switch to the compact two-column list.</summary>
        public const int MaxDetailedRows = 5;
        public const int MaxRows = 12;
        public const float RowHeight = 36f;
        public const float ChipSize = 34f;
        public const float IconSize = 26f;
        public const int NameFont = 30;
        public const int DescFont = 28;
        public const float CompactColumnWidth = 470f;

        private sealed class Row
        {
            public RectTransform Root;
            public Image Bg, Rim, Icon;
            public Text Name, Desc;
        }

        /// <summary>Padding of the navy backing panel around the rows (each side, then top and bottom).</summary>
        public const float PanelPadX = 26f, PanelPadY = 9f;
        public const float PanelAlpha = 0.74f;

        private readonly RectTransform root;
        private readonly RectTransform block;
        private readonly Image panel;
        private readonly Row[] rows = new Row[MaxRows];
        private readonly Text line;
        private int visibleRows;

        public BiomeRulesView(Transform parent, Vector2 anchor, Vector2 center, Vector2 size)
        {
            root = UiKit.Rect("BiomeRules", parent);
            UiKit.Place(root, anchor, center, size);
            // A soft navy panel behind the rows keeps them readable over the attract match.
            panel = UiKit.Rounded(root, "Panel", UiKit.WithAlpha(UiKit.Navy, PanelAlpha), 26f);
            UiKit.Place(panel.rectTransform, UiKit.Center, Vector2.zero, size);
            block = UiKit.Rect("Block", root);
            UiKit.Place(block, UiKit.Center, Vector2.zero, size);
            for (int i = 0; i < MaxRows; i++)
            {
                var r = new Row { Root = UiKit.Rect("Row" + i, block) };
                r.Root.anchorMin = r.Root.anchorMax = UiKit.Center;
                r.Root.pivot = new Vector2(0f, 0.5f);
                r.Root.sizeDelta = new Vector2(size.x, RowHeight);
                r.Bg = UiKit.Img(r.Root, "Bg", UiKit.CircleSprite, UiKit.WithAlpha(UiKit.Navy, 0.9f));
                UiKit.Place(r.Bg.rectTransform, new Vector2(0f, 0.5f), new Vector2(ChipSize * 0.5f, 0f), new Vector2(ChipSize, ChipSize));
                r.Rim = UiKit.Img(r.Root, "Rim", UiKit.RingSprite, UiKit.WithAlpha(UiKit.Light, 0.35f));
                UiKit.Place(r.Rim.rectTransform, new Vector2(0f, 0.5f), new Vector2(ChipSize * 0.5f, 0f), new Vector2(ChipSize, ChipSize));
                r.Icon = UiKit.Img(r.Root, "Icon", null, UiKit.Light);
                UiKit.Place(r.Icon.rectTransform, new Vector2(0f, 0.5f), new Vector2(ChipSize * 0.5f, 0f), new Vector2(IconSize, IconSize));
                r.Name = UiKit.Label(r.Root, "Name", NameFont, UiKit.Light, TextAnchor.MiddleLeft);
                r.Desc = UiKit.Label(r.Root, "Desc", DescFont, UiKit.WithAlpha(UiKit.Light, 0.8f), TextAnchor.MiddleLeft);
                foreach (Text t in new[] { r.Name, r.Desc })
                {
                    RectTransform tr = t.rectTransform;
                    tr.anchorMin = tr.anchorMax = new Vector2(0f, 0.5f);
                    tr.pivot = new Vector2(0f, 0.5f);
                    tr.sizeDelta = new Vector2(600f, RowHeight + 8f);
                }
                rows[i] = r;
                r.Root.gameObject.SetActive(false);
                r.Name.enabled = r.Desc.enabled = false;
            }
            line = UiKit.Label(block, "Line", DescFont, UiKit.WithAlpha(UiKit.Light, 0.78f), TextAnchor.MiddleCenter);
            UiKit.Place(line.rectTransform, UiKit.Center, Vector2.zero, new Vector2(size.x, RowHeight + 8f));
            line.enabled = false;
        }

        public RectTransform Rect => root;

        /// <summary>Trait rows on screen (0 when the single line shows).</summary>
        public int VisibleRows => visibleRows;

        /// <summary>The single line ("Regles classiques ...", "Aucune regle ..."), or null when trait rows show.</summary>
        public string LineText => line.enabled ? line.text : null;

        /// <summary>"name|description" of row i (description empty in the compact list), for tests.</summary>
        public string RowText(int i)
        {
            if (i < 0 || i >= visibleRows) return null;
            return rows[i].Name.text + "|" + (rows[i].Desc.enabled ? rows[i].Desc.text : "");
        }

        /// <summary>
        /// Shows the specs of the selected biome (ascending id). classic: the master switch or -classic is off, so the line
        /// "Regles classiques" replaces the rows; an empty list in a biome-rules game shows "Aucune regle speciale".
        /// </summary>
        public void Show(List<TraitSpec> specs, bool classic)
        {
            int count = specs != null ? specs.Count : 0;
            if (classic || count == 0)
            {
                HideRows(0);
                visibleRows = 0;
                line.enabled = true;
                line.text = Strings.Get(classic ? "menu.rules_classic" : "menu.rules_none");
                float lineScale = Mathf.Min(1f, root.sizeDelta.x / Mathf.Max(1f, line.preferredWidth + 2f * PanelPadX));
                block.localScale = new Vector3(lineScale, lineScale, 1f);
                panel.rectTransform.sizeDelta = new Vector2((line.preferredWidth + 2f * PanelPadX) * lineScale, (RowHeight + 2f * PanelPadY) * lineScale);
                return;
            }
            line.enabled = false;
            int n = Mathf.Min(count, MaxRows);
            bool compact = n > MaxDetailedRows;
            float maxWidth = 0f;
            for (int i = 0; i < n; i++)
            {
                Row r = rows[i];
                TraitSpec s = specs[i];
                if (!r.Root.gameObject.activeSelf) r.Root.gameObject.SetActive(true);
                r.Icon.sprite = TraitIcons.Get(s.Id);
                r.Rim.color = TraitText.IsKillReward(s.Id) ? UiKit.WithAlpha(UiKit.Saffron, 0.95f) : UiKit.WithAlpha(UiKit.Light, 0.35f);
                r.Name.enabled = true;
                r.Name.text = TraitText.Name(s.Id);
                float x = ChipSize + 14f;
                r.Name.rectTransform.anchoredPosition = new Vector2(x, 0f);
                float nameWidth = r.Name.preferredWidth;
                r.Name.rectTransform.sizeDelta = new Vector2(nameWidth + 8f, RowHeight + 8f);
                x += nameWidth;
                r.Desc.enabled = !compact;
                if (!compact)
                {
                    r.Desc.text = TraitText.Describe(s);
                    x += 14f;
                    r.Desc.rectTransform.anchoredPosition = new Vector2(x, 0f);
                    float descWidth = r.Desc.preferredWidth;
                    r.Desc.rectTransform.sizeDelta = new Vector2(descWidth + 8f, RowHeight + 8f);
                    x += descWidth;
                }
                r.Root.sizeDelta = new Vector2(x, RowHeight);
                maxWidth = Mathf.Max(maxWidth, x);
            }
            HideRows(n);
            visibleRows = n;

            // Layout: one left-aligned column centered as a block, or two columns of icon + name.
            int perColumn = compact ? (n + 1) / 2 : n;
            float columnWidth = compact ? CompactColumnWidth : maxWidth;
            int columns = compact ? 2 : 1;
            float blockWidth = compact ? columns * columnWidth : maxWidth;
            float blockHeight = perColumn * RowHeight;
            for (int i = 0; i < n; i++)
            {
                int col = compact ? i / perColumn : 0;
                int row = compact ? i % perColumn : i;
                float left = -blockWidth * 0.5f + col * columnWidth;
                float y = blockHeight * 0.5f - RowHeight * (row + 0.5f);
                rows[i].Root.anchoredPosition = new Vector2(left, y);
            }
            // Fit the block and its panel in the view (long English lines, many traits): scale down, never up.
            Vector2 size = root.sizeDelta;
            float panelW = blockWidth + 2f * PanelPadX, panelH = blockHeight + 2f * PanelPadY;
            float scale = 1f;
            if (panelW > size.x) scale = Mathf.Min(scale, size.x / panelW);
            if (panelH > size.y) scale = Mathf.Min(scale, size.y / panelH);
            block.localScale = new Vector3(scale, scale, 1f);
            panel.rectTransform.sizeDelta = new Vector2(panelW * scale, panelH * scale);
        }

        /// <summary>Size of the backing panel (tests: it holds every row).</summary>
        public Vector2 PanelSize => panel.rectTransform.sizeDelta;

        /// <summary>Scale applied to the rows to fit the view (1 unless they are too wide or too many).</summary>
        public float RowScale => block.localScale.x;

        private void HideRows(int from)
        {
            for (int i = from; i < MaxRows; i++)
            {
                Row r = rows[i];
                r.Name.enabled = r.Desc.enabled = false;
                if (r.Root.gameObject.activeSelf) r.Root.gameObject.SetActive(false);
            }
        }
    }
}
