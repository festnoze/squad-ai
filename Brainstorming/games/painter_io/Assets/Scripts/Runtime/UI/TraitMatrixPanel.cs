// Owned by traits-ui (wave D-2). docs/BIOME_TRAITS.md section 5: the hidden test settings get a trait matrix, one row per
// trait (TraitDefaults.All, 11 rows with the kill rewards of section 7), three checkboxes L / F / E, and "Reinitialiser".
// A tick calls BiomeTraitTable.SetAssigned, which writes SaveData.TraitMatrix: the next round uses it, and GameDirector
// restarts the attract match behind the menu when its traits change (traits-infra). A cell that differs from the default
// table wears a saffron rim, so the player sees what Reinitialiser (SaveData.ResetTraitMatrix) will undo. While the biome
// rules are off ("Regles classiques") the matrix stays editable and a saffron note says it waits.
// Built inside the Options canvas by SettingsPanel, shown in place of the Options panel (its own CanvasGroup).
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    public sealed class TraitMatrixPanel
    {
        public const float PanelWidth = 920f;
        public const float RowHeight = 88f;
        public const float CellSize = 76f;
        public const float ColumnSpacing = 124f;
        public const float HeaderTop = 200f;
        public const float FirstRowTop = 268f;

        private sealed class Cell
        {
            public Image Box, Rim, Check;
        }

        private sealed class Row
        {
            public TraitId Id;
            public Image Rim;
            public Text Name;
            public readonly Cell[] Cells = new Cell[BiomeTheme.Count];
        }

        private readonly RectTransform panel;
        private readonly CanvasGroup group;
        private readonly Text title, note, resetLabel, backLabel;
        private readonly Text[] headers = new Text[BiomeTheme.Count];
        private readonly List<Row> rows = new List<Row>();
        private readonly Image backBg;
        private readonly Action onBack;
        private bool open;

        public TraitMatrixPanel(RectTransform safe, Action onBack)
        {
            this.onBack = onBack;
            IReadOnlyList<TraitId> all = TraitDefaults.All;
            float rowsBottom = FirstRowTop + all.Count * RowHeight;
            float height = rowsBottom + 70f + 130f + 60f;

            panel = UiKit.Rect("TraitMatrix", safe);
            UiKit.Place(panel, UiKit.Center, Vector2.zero, new Vector2(PanelWidth, height));
            group = panel.gameObject.AddComponent<CanvasGroup>();
            Image shadow = UiKit.Rounded(panel, "Shadow", UiKit.WithAlpha(UiKit.Navy, 0.7f), 60f);
            UiKit.Stretch(shadow.rectTransform);
            shadow.rectTransform.offsetMin = new Vector2(-4f, -18f);
            shadow.rectTransform.offsetMax = new Vector2(4f, -6f);
            Image edge = UiKit.Rounded(panel, "Edge", UiKit.WithAlpha(UiKit.Light, 0.16f), 59f);
            UiKit.Stretch(edge.rectTransform);
            edge.rectTransform.offsetMin = new Vector2(-3f, -3f);
            edge.rectTransform.offsetMax = new Vector2(3f, 3f);
            Image bg = UiKit.Rounded(panel, "Background", new Color32(0x22, 0x2F, 0x57, 0xFF), 56f);
            UiKit.Stretch(bg.rectTransform);

            title = UiKit.Label(panel, "Title", 60, UiKit.Saffron, TextAnchor.MiddleCenter, true, true);
            UiKit.Place(title.rectTransform, UiKit.TopCenter, new Vector2(0f, -100f), new Vector2(PanelWidth, 100f));

            for (int b = 0; b < BiomeTheme.Count; b++)
            {
                headers[b] = UiKit.Label(panel, "Header" + b, 46, UiKit.Light, TextAnchor.MiddleCenter, true, true);
                UiKit.Place(headers[b].rectTransform, UiKit.TopCenter, new Vector2(ColumnX(b), -HeaderTop), new Vector2(ColumnSpacing, 70f));
            }

            for (int k = 0; k < all.Count; k++)
            {
                TraitId id = all[k];
                float y = -(FirstRowTop + RowHeight * (k + 0.5f));
                var row = new Row { Id = id };
                // Zebra band for legibility across the wide row.
                if ((k & 1) == 0)
                {
                    Image band = UiKit.Rounded(panel, "Band" + k, UiKit.WithAlpha(UiKit.Light, 0.04f), 30f);
                    UiKit.Place(band.rectTransform, UiKit.TopCenter, new Vector2(0f, y), new Vector2(PanelWidth - 56f, RowHeight - 6f));
                }
                float chipX = -PanelWidth * 0.5f + 58f;
                Image chip = UiKit.Img(panel, "Chip" + k, UiKit.CircleSprite, UiKit.WithAlpha(UiKit.Navy, 0.9f));
                UiKit.Place(chip.rectTransform, UiKit.TopCenter, new Vector2(chipX, y), new Vector2(58f, 58f));
                row.Rim = UiKit.Img(panel, "ChipRim" + k, UiKit.RingSprite,
                                    TraitText.IsKillReward(id) ? UiKit.WithAlpha(UiKit.Saffron, 0.95f) : UiKit.WithAlpha(UiKit.Light, 0.35f));
                UiKit.Place(row.Rim.rectTransform, UiKit.TopCenter, new Vector2(chipX, y), new Vector2(58f, 58f));
                Image icon = UiKit.Img(panel, "Icon" + k, TraitIcons.Get(id), UiKit.Light);
                UiKit.Place(icon.rectTransform, UiKit.TopCenter, new Vector2(chipX, y), new Vector2(44f, 44f));
                row.Name = UiKit.Label(panel, "Name" + k, 38, UiKit.Light, TextAnchor.MiddleLeft);
                RectTransform nr = row.Name.rectTransform;
                nr.anchorMin = nr.anchorMax = UiKit.TopCenter;
                nr.pivot = new Vector2(0f, 0.5f);
                nr.sizeDelta = new Vector2(ColumnX(0) - CellSize * 0.5f - (chipX + 44f) - 8f, RowHeight);
                nr.anchoredPosition = new Vector2(chipX + 44f, y);
                for (int b = 0; b < BiomeTheme.Count; b++)
                {
                    var biome = (BiomeId)b;
                    var cell = new Cell();
                    cell.Rim = UiKit.Rounded(panel, "CellRim" + k + "_" + b, UiKit.WithAlpha(UiKit.Saffron, 0f), 26f);
                    UiKit.Place(cell.Rim.rectTransform, UiKit.TopCenter, new Vector2(ColumnX(b), y), new Vector2(CellSize + 12f, CellSize + 12f));
                    Button btn = UiKit.Btn(panel, "Cell" + k + "_" + b, new Vector2(CellSize, CellSize), UiKit.NavyLight, 20f, 0,
                                           UiKit.Light, () => Toggle(id, biome), out _);
                    UiKit.Place((RectTransform)btn.transform, UiKit.TopCenter, new Vector2(ColumnX(b), y), new Vector2(CellSize, CellSize));
                    cell.Box = (Image)btn.targetGraphic;
                    cell.Check = UiKit.Img(btn.transform, "Check", TraitIcons.Check, UiKit.Navy);
                    UiKit.Place(cell.Check.rectTransform, UiKit.Center, Vector2.zero, new Vector2(CellSize - 16f, CellSize - 16f));
                    row.Cells[b] = cell;
                }
                rows.Add(row);
            }

            note = UiKit.Paragraph(panel, "Note", 30, UiKit.WithAlpha(UiKit.Light, 0.7f), TextAnchor.MiddleCenter, PanelWidth - 100f);
            UiKit.Place(note.rectTransform, UiKit.TopCenter, new Vector2(0f, -(rowsBottom + 40f)), new Vector2(PanelWidth - 100f, 64f));

            Button reset = UiKit.Btn(panel, "Reset", new Vector2(400f, 104f), UiKit.NavyLight, 52f, 42, UiKit.Light, OnReset, out resetLabel);
            UiKit.Place((RectTransform)reset.transform, UiKit.TopCenter, new Vector2(-215f, -(rowsBottom + 70f + 62f)), new Vector2(400f, 104f));
            Button back = UiKit.Btn(panel, "Back", new Vector2(400f, 104f), Palette.ColorOf(0), 52f, 46, UiKit.Light, OnBack, out backLabel);
            UiKit.Place((RectTransform)back.transform, UiKit.TopCenter, new Vector2(215f, -(rowsBottom + 70f + 62f)), new Vector2(400f, 104f));
            backBg = (Image)back.targetGraphic;

            SetOpen(false);
        }

        public RectTransform Rect => panel;

        public bool IsOpen => open;

        /// <summary>Number of trait rows (tests: one per TraitDefaults.All entry).</summary>
        public int RowCount => rows.Count;

        /// <summary>The checkbox state shown for a trait and a biome (tests).</summary>
        public bool IsChecked(TraitId id, BiomeId biome)
        {
            Row r = rows.Find(x => x.Id == id);
            return r != null && r.Cells[(int)biome].Check.enabled;
        }

        /// <summary>True when the cell wears the "differs from the default table" rim (tests).</summary>
        public bool IsMarkedModified(TraitId id, BiomeId biome)
        {
            Row r = rows.Find(x => x.Id == id);
            return r != null && r.Cells[(int)biome].Rim.color.a > 0.01f;
        }

        /// <summary>The note under the matrix (tests).</summary>
        public string NoteText => note.text;

        /// <summary>Simulates a tap on a cell (tests): same path as the button.</summary>
        public void Toggle(TraitId id, BiomeId biome)
        {
            try
            {
                BiomeTraitTable.SetAssigned(id, biome, !BiomeTraitTable.IsAssigned(id, biome));
            }
            catch (Exception e)
            {
                Debug.LogWarning("[PainterIO] trait matrix " + id + " / " + biome + " failed: " + e.Message);
            }
            Refresh();
        }

        public void SetOpen(bool value)
        {
            open = value;
            group.alpha = value ? 1f : 0f;
            group.interactable = value;
            group.blocksRaycasts = value;
            if (value) Refresh();
        }

        public void Relabel()
        {
            title.text = Strings.Get("options.trait_matrix");
            headers[0].text = Strings.Get("options.col_liquid");
            headers[1].text = Strings.Get("options.col_fire");
            headers[2].text = Strings.Get("options.col_electric");
            resetLabel.text = Strings.Get("options.reset");
            backLabel.text = Strings.Get("options.back");
            for (int k = 0; k < rows.Count; k++) rows[k].Name.text = TraitText.Name(rows[k].Id);
            Refresh();
        }

        /// <summary>Re-reads every cell from BiomeTraitTable (the saved matrix over the default table).</summary>
        public void Refresh()
        {
            for (int b = 0; b < BiomeTheme.Count; b++) headers[b].color = ColumnColor((BiomeId)b);
            for (int k = 0; k < rows.Count; k++)
            {
                Row r = rows[k];
                int mask = SafeMask(r.Id);
                int defaults = BiomeTraitTable.DefaultMask(r.Id);
                for (int b = 0; b < BiomeTheme.Count; b++)
                {
                    bool on = (mask & (1 << b)) != 0;
                    bool changed = on != ((defaults & (1 << b)) != 0);
                    Cell c = r.Cells[b];
                    c.Box.color = on ? ColumnColor((BiomeId)b) : UiKit.NavyLight;
                    c.Check.enabled = on;
                    c.Rim.color = UiKit.WithAlpha(UiKit.Saffron, changed ? 0.95f : 0f);
                }
            }
            bool classic = !SaveData.BiomeRulesOn || LaunchArgs.Classic;
            note.text = Strings.Get(classic ? "options.matrix_classic" : "options.matrix_note");
            note.color = classic ? UiKit.Saffron : UiKit.WithAlpha(UiKit.Light, 0.7f);
        }

        /// <summary>Scales the panel to fit the safe area (called every frame while the Options are visible).</summary>
        public void Fit(float availWidth, float availHeight)
        {
            float h = panel.sizeDelta.y, w = panel.sizeDelta.x;
            float s = 1f;
            if (h > 0f && availHeight > 0f) s = Mathf.Min(s, availHeight / h);
            if (w > 0f && availWidth > 0f) s = Mathf.Min(s, availWidth / w);
            panel.localScale = new Vector3(s, s, 1f);
            backBg.color = Palette.ColorAt(Palette.HumanColor);
        }

        // ------------------------------------------------------------------------------------------------------------

        /// <summary>x of a biome column (center of its checkboxes) from the panel center.</summary>
        internal static float ColumnX(int biome)
        {
            float last = PanelWidth * 0.5f - 64f - CellSize * 0.5f;
            return last - (BiomeTheme.Count - 1 - biome) * ColumnSpacing;
        }

        /// <summary>Palette index of each biome's signature color: Liquide teal water, Feu orange flame, Electricite yellow spark.</summary>
        private static readonly int[] ColumnPaletteIndex = { 1, 0, 2 };

        /// <summary>A light tint of the biome's signature color for its column (checked boxes and the header letter).</summary>
        internal static Color ColumnColor(BiomeId biome)
        {
            int b = (int)BiomeTheme.Clamp((int)biome);
            BiomeTheme t = BiomeTheme.Get((BiomeId)b);
            int k = ColumnPaletteIndex[b];
            Color c = t.PlayerColors != null && t.PlayerColors.Length > k ? t.PlayerColors[k] : UiKit.Light;
            return UiKit.Lighten(c, 0.12f);
        }

        private static int SafeMask(TraitId id)
        {
            try
            {
                return BiomeTraitTable.MaskOf(id);
            }
            catch (Exception)
            {
                return BiomeTraitTable.DefaultMask(id);
            }
        }

        private void OnReset()
        {
            SaveData.ResetTraitMatrix();
            Refresh();
        }

        private void OnBack()
        {
            onBack?.Invoke();
        }
    }
}
