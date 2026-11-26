using System;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// ADSSHOP (docs/next/progress/ADSSHOP.md): the Shop page, a page of the title screen opened by its Shop button
    /// (Menu.OpenShop), built only when <see cref="StoreService.ShopVisible"/>. It follows the Options and Credits pages'
    /// style: the same dim and warm side band, the display face heading under the short red rule, one row per catalog
    /// product (its name and line from Core.Strings, its price from the store or the catalog, "Owned" once bought), then
    /// Restore purchases, Ad privacy choices (when the ad network offers a consent form) and Back, with a status line.
    /// Up and down walk the rows and wrap (keyboard, D-pad, stick), A or a click buys, Escape or gamepad B goes back
    /// (Menu.Update), a tap works on touch.
    /// </summary>
    public sealed class ShopPage : MonoBehaviour
    {
        /// <summary>One product row.</summary>
        public sealed class Row
        {
            public ShopProduct Product;
            public Button Button;
            public Text Title;
            public Text Description;
            public Text Price;
        }

        public bool IsOpen { get; private set; }

        public IReadOnlyList<Row> Rows => rows;
        public Button RestoreButton { get; private set; }
        public Button PrivacyButton { get; private set; }
        public Button BackButton { get; private set; }

        /// <summary>The status line (the last purchase's outcome, "One moment...").</summary>
        public Text Status { get; private set; }

        /// <summary>The first product row, else Back.</summary>
        public Selectable DefaultSelectable => rows.Count > 0 ? rows[0].Button : BackButton;

        private readonly List<Row> rows = new List<Row>();
        private Canvas canvas;
        private Font font;
        private Font display;
        private Dictionary<string, Text> labels;
        private Action click;
        private string statusKey;

        // The Options page's palette and metrics (Menu keeps them private; the values are the same).
        private static readonly Color Dim = new Color(0.05f, 0.035f, 0.025f, 0.55f);
        private static readonly Color Panel = new Color(0.1f, 0.066f, 0.05f, 0.84f);
        private static readonly Color Ink = new Color(1f, 0.94f, 0.82f, 1f);
        private static readonly Color DetailInk = new Color(1f, 0.94f, 0.82f, 0.78f);
        private static readonly Color Accent = new Color(0.96f, 0.8f, 0.58f, 0.95f);
        private static readonly Color OwnedInk = new Color(0.62f, 0.85f, 0.55f, 0.95f);
        private static readonly Color Red = new Color(0.82f, 0.2f, 0.16f, 1f);
        private const float Top = 270f;
        private const float RowStep = 96f;
        private const float RowHeight = 86f;
        private const float RowWidth = 820f;
        private const float PlainStep = 68f;
        private const float PlainHeight = 62f;
        private const float BackY = Top - 10f * PlainStep;
        private const float PriceWidth = 190f;

        // ----- BIGBUTTONS (docs/next/progress/BIGBUTTONS.md): the touch layout, set by Menu (TouchLayout.Active) -----
        // Up to five product rows 108 high and 14 apart, from y 340 (under the red rule) down to y -256 at most, 940 wide so
        // the longest French line ("Sans pub et tous les niveaux débloqués, pour moins cher.") fits at the bigger size; then
        // Restaurer les achats, Confidentialité des pubs (when offered) and Retour side by side in one bottom row 104 high
        // (its centre at y -392, or higher above a bottom safe margin; 1408 wide, inside a 4:3 tablet's 1663 units), the
        // status line between the two. The PC layout is remembered and put back exactly.
        private const float TouchTop = 340f;
        private const float TouchRowHeight = 108f;
        private const float TouchRowGap = 14f;
        private const float TouchRowWidth = 940f;
        private const float TouchMinRowHeight = 72f;
        private const float TouchPlainY = -392f;
        private const float TouchPlainHeight = 104f;
        private const float TouchPlainGap = 24f;
        private const float TouchRestoreWidth = 520f;
        private const float TouchPrivacyWidth = 540f;
        private const float TouchBackWidth = 300f;
        private const float TouchStatusHeight = 60f;
        private const float TouchStatusGap = 12f;
        private const float TouchStatusWidth = 1300f;
        private const float TouchBottomMargin = 24f;
        private const float TouchSideGap = 40f;
        private const float TouchIconSize = 60f;
        private const float TouchIconInset = 16f;
        private const float TouchLabelOffset = 92f;
        private const int TouchTitleSize = 38;
        private const int TouchDescriptionSize = 26;
        private const int TouchPriceSize = 40;
        private const int TouchPlainSize = 40;
        private const float TouchBandWidth = 2400f;

        private readonly TouchLayout.Memory touchMemory = new TouchLayout.Memory();
        private bool touchLayout;
        private float touchX;
        private float touchPlainY;

        /// <summary>BIGBUTTONS: the page is laid out for touch now (bigger rows, a bottom row of plain buttons).</summary>
        public bool TouchLayoutOn => touchLayout;

        /// <summary>
        /// BIGBUTTONS: the touch layout (<paramref name="touch"/>) or back to the exact PC layout. <paramref name="safe"/> is
        /// the screen's unsafe margins and <paramref name="half"/> half the canvas height, in reference units (Menu passes
        /// TouchLayout.SafeInsets and TouchLayout.CanvasHeight).
        /// </summary>
        public void SetTouchLayout(bool touch, Vector4 safe, float half)
        {
            touchMemory.Restore();
            touchLayout = touch;
            if (touch)
            {
                touchX = Mathf.Max(Tuning.OptionsMargin, safe.x + TouchSideGap);
                float dx = touchX - Tuning.OptionsMargin;
                if (transform.Find("Band") is RectTransform band)
                {
                    touchMemory.Keep(band).sizeDelta = new Vector2(TouchBandWidth, 0f);
                }
                if (dx > 0f)
                {
                    foreach (string name in new[] { "ShopTitle", "ShopRule" })
                    {
                        if (transform.Find(name) is RectTransform moved)
                        {
                            touchMemory.Keep(moved).anchoredPosition += new Vector2(dx, 0f);
                        }
                    }
                }
                touchPlainY = Mathf.Max(TouchPlainY, -half + safe.z + TouchBottomMargin + TouchPlainHeight * 0.5f);
                float statusY = touchPlainY + TouchPlainHeight * 0.5f + TouchStatusGap + TouchStatusHeight * 0.5f;
                float rowsBottom = statusY + TouchStatusHeight * 0.5f + TouchStatusGap;
                float height = TouchLayout.FitRows(TouchTop, rowsBottom, Mathf.Max(1, rows.Count), TouchRowGap, TouchRowHeight, TouchMinRowHeight);
                for (int i = 0; i < rows.Count; i++)
                {
                    TouchRow(rows[i], TouchTop - height * 0.5f - i * (height + TouchRowGap), height);
                }
                TouchPlain(RestoreButton);
                TouchPlain(PrivacyButton);
                TouchPlain(BackButton);
                if (Status != null)
                {
                    Place(touchMemory.Keep(Status.rectTransform), new Vector2(0f, 0.5f), new Vector2(touchX, statusY),
                        new Vector2(TouchStatusWidth, TouchStatusHeight));
                }
            }
            Refresh();
        }

        /// <summary>BIGBUTTONS: one product row in the touch layout, taller and wider, its three texts bigger.</summary>
        private void TouchRow(Row row, float y, float height)
        {
            Place(touchMemory.Keep((RectTransform)row.Button.transform), new Vector2(0f, 0.5f), new Vector2(touchX, y),
                new Vector2(TouchRowWidth, height));
            if (row.Title != null)
            {
                touchMemory.Keep(row.Title).fontSize = TouchTitleSize;
            }
            touchMemory.Keep(row.Description).fontSize = TouchDescriptionSize;
            touchMemory.Keep(row.Price).fontSize = TouchPriceSize;
            row.Price.rectTransform.sizeDelta = new Vector2(PriceWidth, height);
        }

        /// <summary>BIGBUTTONS: a plain button (Restore, privacy, Back) at the bottom row's height, its icon and label bigger.</summary>
        private void TouchPlain(Button button)
        {
            if (button == null)
            {
                return;
            }
            var rect = (RectTransform)button.transform;
            touchMemory.Keep(rect).sizeDelta = new Vector2(rect.sizeDelta.x, TouchPlainHeight);
            Transform icon = button.transform.Find(button.name + "Icon");
            if (icon is RectTransform iconRect)
            {
                Place(touchMemory.Keep(iconRect), new Vector2(0f, 0.5f), new Vector2(TouchIconInset, 0f), new Vector2(TouchIconSize, TouchIconSize));
            }
            if (labels.TryGetValue(button.name + "Label", out Text text))
            {
                touchMemory.Keep(text).fontSize = TouchPlainSize;
                if (icon != null)
                {
                    text.rectTransform.offsetMin = new Vector2(TouchLabelOffset, 0f);
                    text.rectTransform.offsetMax = new Vector2(-TouchIconInset, 0f);
                }
            }
        }

        /// <summary>BIGBUTTONS: Restore, the privacy button (when shown) and Back side by side, left to right, in the bottom row.</summary>
        private void PlaceBottomRow(bool privacy)
        {
            float x = touchX;
            PlaceInRow(RestoreButton, ref x, TouchRestoreWidth);
            if (privacy)
            {
                PlaceInRow(PrivacyButton, ref x, TouchPrivacyWidth);
            }
            PlaceInRow(BackButton, ref x, TouchBackWidth);
        }

        private void PlaceInRow(Button button, ref float x, float width)
        {
            Place((RectTransform)button.transform, new Vector2(0f, 0.5f), new Vector2(x, touchPlainY), new Vector2(width, TouchPlainHeight));
            x += width + TouchPlainGap;
        }

        private static void LinkSides(Selectable selectable, Selectable left, Selectable right)
        {
            Navigation nav = selectable.navigation;
            nav.selectOnLeft = left;
            nav.selectOnRight = right;
            selectable.navigation = nav;
        }

        /// <summary>Builds the page (hidden) under <paramref name="parent"/>, the Menu's root canvas.</summary>
        public static ShopPage Create(Transform parent, Font font, Dictionary<string, Text> labels, Action click, Action onBack)
        {
            var go = new GameObject("ShopPage", typeof(RectTransform));
            go.transform.SetParent(parent, false);
            Stretch((RectTransform)go.transform);
            ShopPage page = go.AddComponent<ShopPage>();
            page.font = font;
            page.display = Hud.DisplayFont != null ? Hud.DisplayFont : font;
            page.labels = labels ?? new Dictionary<string, Text>();
            page.click = click;
            page.Build(onBack);
            StoreService.Changed += page.OnStoreChanged;
            return page;
        }

        private void OnDestroy()
        {
            StoreService.Changed -= OnStoreChanged;
        }

        /// <summary>Shows or hides the page (Menu.Apply); opening refreshes every row and clears the status line.</summary>
        public void SetOpen(bool open)
        {
            IsOpen = open;
            if (open)
            {
                SetStatus(null);
                Refresh();
            }
            if (canvas != null && canvas.enabled != open)
            {
                canvas.enabled = open;
            }
        }

        /// <summary>Strings.LanguageChanged: every text again in the current language.</summary>
        public void Relocalize()
        {
            Refresh();
        }

        private void OnStoreChanged()
        {
            if (IsOpen)
            {
                Refresh();
            }
        }

        private void Build(Action onBack)
        {
            canvas = gameObject.AddComponent<Canvas>();
            // A nested Canvas raycasts its own graphics only.
            gameObject.AddComponent<GraphicRaycaster>();
            canvas.enabled = false;

            Stretch(NewImage(transform, "Dim", null, Dim).rectTransform);
            Image band = NewImage(transform, "Band", ProceduralArt.SideFade, Panel);
            band.rectTransform.anchorMin = new Vector2(0f, 0f);
            band.rectTransform.anchorMax = new Vector2(0f, 1f);
            band.rectTransform.pivot = new Vector2(0f, 0.5f);
            band.rectTransform.anchoredPosition = Vector2.zero;
            band.rectTransform.sizeDelta = new Vector2(Tuning.OptionsPanelWidth, 0f);

            var left = new Vector2(0f, 0.5f);
            Text title = NewText(transform, "ShopTitle", Strings.ShopTitle, 92, Ink, display);
            title.alignment = TextAnchor.MiddleLeft;
            Place(title.rectTransform, left, new Vector2(Tuning.OptionsMargin, Top + 155f), new Vector2(760f, 110f));
            Image rule = NewImage(transform, "ShopRule", null, Red);
            Place(rule.rectTransform, left, new Vector2(Tuning.OptionsMargin + 4f, Top + 95f), new Vector2(84f, 6f));

            rows.Clear();
            List<ShopProduct> products = StoreService.ShownProducts();
            for (int i = 0; i < products.Count; i++)
            {
                rows.Add(BuildRow(products[i], i));
            }

            BackButton = PlainButton("ShopBack", Strings.SelectBack, BackY, UiIconLibrary.Back);
            PrivacyButton = PlainButton("ShopPrivacy", Strings.ShopPrivacy, BackY + PlainStep, null);
            RestoreButton = PlainButton("ShopRestore", Strings.ShopRestore, BackY + 2f * PlainStep, UiIconLibrary.Reset);
            BackButton.onClick.AddListener(() => onBack?.Invoke());
            RestoreButton.onClick.AddListener(() =>
            {
                click?.Invoke();
                aRestore();
            });
            PrivacyButton.onClick.AddListener(() =>
            {
                click?.Invoke();
                aPrivacy();
            });

            Status = NewText(transform, "ShopStatus", string.Empty, 26, Accent, font);
            Status.alignment = TextAnchor.MiddleLeft;
            Status.horizontalOverflow = HorizontalWrapMode.Wrap;
            Place(Status.rectTransform, left, new Vector2(Tuning.OptionsMargin + 450f, BackY), new Vector2(700f, 70f));
            Refresh();
        }

        private Row BuildRow(ShopProduct product, int index)
        {
            string name = "ShopProduct" + index;
            Button button = Hud.MenuButton(transform, name, string.Empty, font, labels);
            Place((RectTransform)button.transform, new Vector2(0f, 0.5f), new Vector2(Tuning.OptionsMargin, Top - index * RowStep),
                new Vector2(RowWidth, RowHeight));
            Style(button);
            var row = new Row { Product = product, Button = button };
            row.Title = labels.TryGetValue(name + "Label", out Text label) ? label : null;
            if (row.Title != null)
            {
                row.Title.fontSize = 34;
                row.Title.color = Ink;
                row.Title.alignment = TextAnchor.MiddleLeft;
                RectTransform t = row.Title.rectTransform;
                t.anchorMin = new Vector2(0f, 0.5f);
                t.anchorMax = new Vector2(1f, 1f);
                t.offsetMin = new Vector2(26f, -2f);
                t.offsetMax = new Vector2(-PriceWidth - 20f, -4f);
            }
            row.Description = NewText(button.transform, name + "Description", string.Empty, 22, DetailInk, font);
            row.Description.alignment = TextAnchor.MiddleLeft;
            RectTransform d = row.Description.rectTransform;
            d.anchorMin = new Vector2(0f, 0f);
            d.anchorMax = new Vector2(1f, 0.5f);
            d.offsetMin = new Vector2(26f, 4f);
            d.offsetMax = new Vector2(-PriceWidth - 20f, 0f);
            row.Price = NewText(button.transform, name + "Price", string.Empty, 34, Accent, font);
            row.Price.alignment = TextAnchor.MiddleRight;
            Place(row.Price.rectTransform, new Vector2(1f, 0.5f), new Vector2(-24f, 0f), new Vector2(PriceWidth, RowHeight));
            button.onClick.AddListener(() =>
            {
                click?.Invoke();
                aBuy(row.Product);
            });
            return row;
        }

        /// <summary>Every row's texts, the privacy button's presence and the up and down chain.</summary>
        public void Refresh()
        {
            foreach (Row row in rows)
            {
                bool covered = StoreService.IsCovered(row.Product);
                if (row.Title != null)
                {
                    row.Title.text = Strings.Get(row.Product.TitleKey);
                }
                row.Description.text = Strings.Get(row.Product.DescriptionKey);
                row.Price.text = covered ? Strings.ShopOwned : StoreService.PriceOf(row.Product);
                row.Price.color = covered ? OwnedInk : Accent;
            }
            SetLabel(BackButton, Strings.SelectBack);
            SetLabel(RestoreButton, Strings.ShopRestore);
            SetLabel(PrivacyButton, Strings.ShopPrivacy);
            bool privacy = AdService.PrivacyOptionsAvailable;
            if (PrivacyButton.gameObject.activeSelf != privacy)
            {
                PrivacyButton.gameObject.SetActive(privacy);
            }
            if (touchLayout)
            {
                // BIGBUTTONS: the touch layout's bottom row, left to right, closing up when the privacy button is hidden.
                PlaceBottomRow(privacy);
            }
            else
            {
                // Restore sits right above Back, or above the privacy button when it shows.
                ((RectTransform)RestoreButton.transform).anchoredPosition = new Vector2(Tuning.OptionsMargin, BackY + (privacy ? 2f : 1f) * PlainStep);
            }
            var chain = new List<Selectable>();
            foreach (Row row in rows)
            {
                chain.Add(row.Button);
            }
            chain.Add(RestoreButton);
            if (privacy)
            {
                chain.Add(PrivacyButton);
            }
            chain.Add(BackButton);
            Chain(chain);
            if (touchLayout)
            {
                // BIGBUTTONS: left and right walk the bottom row too (up and down keep the PC chain).
                LinkSides(RestoreButton, null, privacy ? PrivacyButton : BackButton);
                if (privacy)
                {
                    LinkSides(PrivacyButton, RestoreButton, BackButton);
                }
                LinkSides(BackButton, privacy ? PrivacyButton : RestoreButton, null);
            }
            if (Status != null)
            {
                Status.text = statusKey != null ? Strings.Get(statusKey) : string.Empty;
            }
        }

        private void SetStatus(string key)
        {
            statusKey = key;
            if (Status != null)
            {
                Status.text = key != null ? Strings.Get(key) : string.Empty;
            }
        }

        private async void aBuy(ShopProduct product)
        {
            if (product == null || StoreService.Busy)
            {
                return;
            }
            SetStatus("shop.busy");
            PurchaseResult result = await StoreService.aPurchase(product.Id);
            if (this == null)
            {
                return;
            }
            switch (result.Outcome)
            {
                case PurchaseOutcome.Purchased:
                    SetStatus(product.Consumable ? "shop.thanks" : "shop.purchased");
                    break;
                case PurchaseOutcome.AlreadyOwned:
                    SetStatus("shop.alreadyOwned");
                    break;
                case PurchaseOutcome.Cancelled:
                    SetStatus("shop.cancelled");
                    break;
                case PurchaseOutcome.Pending:
                    SetStatus("shop.pending");
                    break;
                case PurchaseOutcome.Unavailable:
                    SetStatus("shop.unavailable");
                    break;
                default:
                    SetStatus("shop.failed");
                    break;
            }
            Refresh();
        }

        private async void aRestore()
        {
            if (StoreService.Busy)
            {
                return;
            }
            SetStatus("shop.busy");
            bool ok = await StoreService.aRestorePurchases();
            if (this == null)
            {
                return;
            }
            SetStatus(ok ? "shop.restored" : StoreService.Provider != null && StoreService.Provider.Ready ? "shop.restoreFailed" : "shop.unavailable");
            Refresh();
        }

        private async void aPrivacy()
        {
            bool ok = await AdService.aShowPrivacyOptions();
            if (this == null)
            {
                return;
            }
            SetStatus(ok ? null : "shop.privacyFailed");
            Refresh();
        }

        // ----- Construction helpers (the Menu's own style, kept local). -----

        private Button PlainButton(string name, string label, float y, Sprite icon)
        {
            Button button = Hud.MenuButton(transform, name, label, font, labels);
            Place((RectTransform)button.transform, new Vector2(0f, 0.5f), new Vector2(Tuning.OptionsMargin, y), new Vector2(420f, PlainHeight));
            Style(button);
            labels.TryGetValue(name + "Label", out Text text);
            if (text != null)
            {
                text.color = Ink;
                text.fontSize = 34;
            }
            if (icon != null)
            {
                Image glyph = NewImage(button.transform, name + "Icon", icon, Ink);
                glyph.preserveAspect = true;
                Place(glyph.rectTransform, new Vector2(0f, 0.5f), new Vector2(Tuning.OptionsIconInset, 0f),
                    new Vector2(Tuning.OptionsIconSize, Tuning.OptionsIconSize));
                if (text != null)
                {
                    text.alignment = TextAnchor.MiddleLeft;
                    text.rectTransform.offsetMin = new Vector2(Tuning.OptionsLabelOffset, 0f);
                    text.rectTransform.offsetMax = new Vector2(-Tuning.OptionsIconInset, 0f);
                }
            }
            return button;
        }

        private static void SetLabel(Button button, string text)
        {
            Text label = button != null ? button.GetComponentInChildren<Text>(true) : null;
            if (label != null)
            {
                label.text = text;
            }
        }

        /// <summary>The Options rows' colours: warm brown at rest, the chair's red when selected.</summary>
        private static void Style(Button button)
        {
            ColorBlock colors = button.colors;
            colors.normalColor = new Color(0.17f, 0.115f, 0.085f, 0.74f);
            colors.highlightedColor = new Color(0.36f, 0.25f, 0.18f, 0.92f);
            colors.selectedColor = new Color(0.8f, 0.2f, 0.16f, 0.97f);
            colors.pressedColor = new Color(0.55f, 0.12f, 0.09f, 1f);
            button.colors = colors;
        }

        /// <summary>Up and down move through <paramref name="items"/> in order, and wrap.</summary>
        private static void Chain(List<Selectable> items)
        {
            for (int i = 0; i < items.Count; i++)
            {
                items[i].navigation = new Navigation
                {
                    mode = Navigation.Mode.Explicit,
                    selectOnUp = items[(i + items.Count - 1) % items.Count],
                    selectOnDown = items[(i + 1) % items.Count],
                };
            }
        }

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

        private Text NewText(Transform parent, string name, string value, int size, Color color, Font face)
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
            var shadow = go.AddComponent<Shadow>();
            shadow.effectColor = new Color(0.05f, 0.03f, 0.02f, 0.5f);
            shadow.effectDistance = new Vector2(1f, -1.5f);
            labels[name] = text;
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
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }
    }
}
