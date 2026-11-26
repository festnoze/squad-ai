using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace OutOfSight.Core
{
    /// <summary>ADSSHOP: a product bought once and kept (No ads), or bought again and again (a tip).</summary>
    public enum ProductKind
    {
        NonConsumable,
        Consumable,
    }

    /// <summary>ADSSHOP: the entitlement keys a product grants (<see cref="ShopProduct.Grants"/>) and the game reads.</summary>
    public static class Entitlements
    {
        /// <summary>No more automatic ads (an opt-in rewarded ad stays possible).</summary>
        public const string NoAds = "no_ads";

        /// <summary>Every level of the play order is playable (SaveStore.IsUnlocked).</summary>
        public const string AllLevels = "all_levels";
    }

    /// <summary>ADSSHOP: one item of the shop catalog (Resources/Config/shop.json "products").</summary>
    public sealed class ShopProduct
    {
        /// <summary>The game's own id (save file, logs); lower case letters, digits, '_' and '.'.</summary>
        public string Id;

        /// <summary>The store's product id (Google Play Console); <see cref="Id"/> when not given.</summary>
        public string StoreId;

        public ProductKind Kind = ProductKind.NonConsumable;

        /// <summary>Shown when the store gives no localized price (the Simulated store, an offline device).</summary>
        public string PriceLabel = string.Empty;

        /// <summary>The Strings keys of the shown title and description (English and French live in Core.Strings).</summary>
        public string TitleKey;
        public string DescriptionKey;

        /// <summary>The entitlements a delivered purchase grants (<see cref="Entitlements"/>); empty for a tip.</summary>
        public List<string> Grants = new List<string>();

        public bool Enabled = true;

        public bool Consumable => Kind == ProductKind.Consumable;
    }

    /// <summary>
    /// ADSSHOP (docs/next/progress/ADSSHOP.md): the shop configuration and product catalog, read from
    /// Resources/Config/shop.json over <see cref="Defaults"/>. The catalog in the file replaces the default one as a whole;
    /// an entry without a valid id, a duplicate id or a malformed entry is skipped, never failing the rest. Pure data.
    /// </summary>
    public sealed class ShopConfig
    {
        public const string ProviderNone = "none";
        public const string ProviderSimulated = "simulated";
        public const string ProviderUnityIap = "unity_iap";

        /// <summary>The shop page shows at most this many products (the page has no scroll).</summary>
        public const int MaxShownProducts = 5;

        /// <summary>Master switch: false hides the Shop button everywhere.</summary>
        public bool Enabled = true;

        /// <summary>"none", "simulated" (purchases succeed locally, development only) or "unity_iap" (Google Play Billing).</summary>
        public string Provider = ProviderNone;

        /// <summary>Where the Shop button shows on the title page.</summary>
        public bool ShowOnAndroid = true;
        public bool ShowOnWindows;
        public bool ShowInEditor;

        public List<ShopProduct> Products = new List<ShopProduct>();

        private static readonly Regex IdPattern = new Regex("^[a-z0-9][a-z0-9_.]*$");

        /// <summary>True for a valid product id (Google Play's own rule: lower case letters, digits, '_' and '.').</summary>
        public static bool IsValidId(string id) => !string.IsNullOrEmpty(id) && id.Length <= 100 && IdPattern.IsMatch(id);

        /// <summary>The code defaults: no store, and the catalog the shipped shop.json starts from.</summary>
        public static ShopConfig Defaults()
        {
            var config = new ShopConfig();
            config.Products.Add(Product("no_ads", ProductKind.NonConsumable, "2,99 €", "shop.noAds", Entitlements.NoAds));
            config.Products.Add(Product("premium_pack", ProductKind.NonConsumable, "3,99 €", "shop.premium", Entitlements.NoAds, Entitlements.AllLevels));
            config.Products.Add(Product("all_levels", ProductKind.NonConsumable, "1,99 €", "shop.allLevels", Entitlements.AllLevels));
            config.Products.Add(Product("tip_coffee", ProductKind.Consumable, "0,99 €", "shop.coffee"));
            return config;
        }

        private static ShopProduct Product(string id, ProductKind kind, string price, string keyPrefix, params string[] grants)
        {
            return new ShopProduct
            {
                Id = id,
                StoreId = id,
                Kind = kind,
                PriceLabel = price,
                TitleKey = keyPrefix + ".title",
                DescriptionKey = keyPrefix + ".desc",
                Grants = new List<string>(grants),
            };
        }

        /// <summary>The enabled products, in catalog order (the shop shows the first <see cref="MaxShownProducts"/>).</summary>
        public List<ShopProduct> EnabledProducts()
        {
            var list = new List<ShopProduct>();
            foreach (ShopProduct p in Products)
            {
                if (p != null && p.Enabled)
                {
                    list.Add(p);
                }
            }
            return list;
        }

        /// <summary>The product with the game id <paramref name="id"/>, or null.</summary>
        public ShopProduct Find(string id)
        {
            if (string.IsNullOrEmpty(id))
            {
                return null;
            }
            foreach (ShopProduct p in Products)
            {
                if (p != null && p.Id == id)
                {
                    return p;
                }
            }
            return null;
        }

        /// <summary>The product with the store id <paramref name="storeId"/> (or, failing that, that game id), or null.</summary>
        public ShopProduct FindByStoreId(string storeId)
        {
            if (string.IsNullOrEmpty(storeId))
            {
                return null;
            }
            foreach (ShopProduct p in Products)
            {
                if (p != null && p.StoreId == storeId)
                {
                    return p;
                }
            }
            return Find(storeId);
        }

        /// <summary>True when the Shop button shows on this platform (<paramref name="editor"/> wins over the other two).</summary>
        public bool ShowsOn(bool android, bool windows, bool editor)
        {
            if (!Enabled)
            {
                return false;
            }
            if (editor)
            {
                return ShowInEditor;
            }
            return android ? ShowOnAndroid : windows && ShowOnWindows; // MUTATION:SHOP_PLATFORM
        }

        /// <summary>The store provider this run uses: "none" when the shop is off or may not run here (batch mode, the probe).</summary>
        public string ResolveProvider(bool runtimeAllowed)
        {
            if (!runtimeAllowed || !Enabled)
            {
                return ProviderNone;
            }
            string name = AdConfig.NormalizeName(Provider);
            return string.IsNullOrEmpty(name) ? ProviderNone : name;
        }

        /// <summary>
        /// The defaults with every field present in <paramref name="json"/> applied. "products", when it is a list, replaces
        /// the default catalog (an invalid entry is skipped). Never throws: not JSON or not an object returns the defaults
        /// with <paramref name="problem"/> set.
        /// </summary>
        public static ShopConfig Parse(string json, out string problem)
        {
            problem = null;
            try
            {
                if (string.IsNullOrWhiteSpace(json))
                {
                    problem = "empty";
                    return Defaults();
                }
                if (!(JToken.Parse(json) is JObject root))
                {
                    problem = "not a JSON object";
                    return Defaults();
                }
                ShopConfig config = Defaults();
                config.Enabled = AdConfig.Bool(root["enabled"], config.Enabled);
                config.Provider = AdConfig.NormalizeName(AdConfig.Str(root["provider"], config.Provider)) ?? ProviderNone;
                config.ShowOnAndroid = AdConfig.Bool(root["showOnAndroid"], config.ShowOnAndroid);
                config.ShowOnWindows = AdConfig.Bool(root["showOnWindows"], config.ShowOnWindows);
                config.ShowInEditor = AdConfig.Bool(root["showInEditor"], config.ShowInEditor);
                if (root["products"] is JArray products)
                {
                    config.Products = new List<ShopProduct>();
                    foreach (JToken entry in products)
                    {
                        ShopProduct product = ParseProduct(entry as JObject);
                        if (product != null && config.Find(product.Id) == null)
                        {
                            config.Products.Add(product);
                        }
                    }
                }
                return config;
            }
            catch (Exception e)
            {
                problem = e.GetType().Name + ": " + e.Message;
                return Defaults();
            }
        }

        /// <summary>One catalog entry, or null when it has no valid id. Unknown "type" values read as non-consumable.</summary>
        private static ShopProduct ParseProduct(JObject obj)
        {
            if (obj == null)
            {
                return null;
            }
            string id = AdConfig.Str(obj["id"], null)?.Trim();
            if (!IsValidId(id))
            {
                return null;
            }
            string storeId = AdConfig.Str(obj["storeId"], null)?.Trim();
            string type = AdConfig.NormalizeName(AdConfig.Str(obj["type"], null));
            var product = new ShopProduct
            {
                Id = id,
                StoreId = IsValidId(storeId) ? storeId : id,
                Kind = type == "consumable" ? ProductKind.Consumable : ProductKind.NonConsumable,
                PriceLabel = AdConfig.Str(obj["priceLabel"], string.Empty),
                TitleKey = AdConfig.Str(obj["titleKey"], "shop." + id + ".title"),
                DescriptionKey = AdConfig.Str(obj["descriptionKey"], "shop." + id + ".desc"),
                Grants = AdConfig.StrList(obj["grants"], new List<string>()),
                Enabled = AdConfig.Bool(obj["enabled"], true),
            };
            return product;
        }
    }
}
