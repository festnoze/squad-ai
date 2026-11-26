using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// ADSSHOP (docs/next/progress/ADSSHOP.md): the provider-agnostic shop layer. Main boots it after the save: it reads
    /// Resources/Config/shop.json over the code defaults (<see cref="ShopConfig"/>), decides whether the title page shows a
    /// Shop button on this platform (<see cref="ShopVisible"/>: Android yes, Windows and the editor no, by default; never in
    /// batch mode, the probe or the look agent), creates the store from <see cref="StoreProviderRegistry"/> and connects
    /// it. Every purchase the store delivers is saved at once (<see cref="SaveStore.RecordPurchase"/>); No ads switches the
    /// automatic ads off (<see cref="AdService.NoAdsOwned"/>), All levels opens the whole play order
    /// (<see cref="SaveStore.IsUnlocked"/>).
    /// </summary>
    public static class StoreService
    {
        /// <summary>The catalog's Resources path (Assets/Resources/Config/shop.json).</summary>
        public const string ConfigResource = "Config/shop";

        public static ShopConfig Config { get; private set; } = ShopConfig.Defaults();
        public static IStoreProvider Provider { get; private set; } = new NoStoreProvider();

        /// <summary>The title page shows the Shop button (read once by Menu when it builds the title).</summary>
        public static bool ShopVisible { get; private set; }

        /// <summary>A purchase or a restore is in progress (the shop ignores a second press meanwhile).</summary>
        public static bool Busy { get; private set; }

        /// <summary>Raised on the main thread after a delivered purchase was saved, or the store became ready (prices).</summary>
        public static event Action Changed;

        /// <summary>Main, at boot (after the save). Never throws.</summary>
        public static void Boot()
        {
            try
            {
                Config = LoadConfig();
                bool android = Application.platform == RuntimePlatform.Android;
                bool windows = !android && !Application.isEditor && !Application.isMobilePlatform;
                ShopVisible = AdService.RuntimeAllowed && Config.ShowsOn(android, windows, Application.isEditor)
                    && Config.EnabledProducts().Count > 0;
                UseProvider(ShopVisible ? Config.ResolveProvider(AdService.RuntimeAllowed) : ShopConfig.ProviderNone);
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Shop] boot failed, no shop this session: " + e.Message);
                ShopVisible = false;
                Provider = new NoStoreProvider();
            }
        }

        /// <summary>Resources/Config/shop.json over the code defaults; the defaults (no store) when it is missing or broken.</summary>
        public static ShopConfig LoadConfig()
        {
            TextAsset asset = Resources.Load<TextAsset>(ConfigResource);
            if (asset == null)
            {
                Debug.LogWarning($"[Shop] Resources/{ConfigResource}.json is missing: code defaults (store none)");
                return ShopConfig.Defaults();
            }
            ShopConfig config = ShopConfig.Parse(asset.text, out string problem);
            if (problem != null)
            {
                Debug.LogWarning($"[Shop] Resources/{ConfigResource}.json: {problem}; code defaults kept");
            }
            return config;
        }

        private static void UseProvider(string name)
        {
            if (Provider != null)
            {
                Provider.Delivered -= OnDelivered;
            }
            IStoreProvider provider = StoreProviderRegistry.Create(name);
            if (provider == null)
            {
                Debug.LogWarning($"[Shop] no store registered for '{name}' (package not installed, or its scripting define symbol "
                    + "missing): purchases are unavailable this session");
                provider = new NoStoreProvider();
            }
            Provider = provider;
            Provider.Delivered += OnDelivered;
            Debug.Log($"[Shop] store {provider.Name} (configured '{Config.Provider}'), shop button {(ShopVisible ? "shown" : "hidden")}");
            if (provider.Name != ShopConfig.ProviderNone)
            {
                aInitializeProvider(provider);
            }
        }

        private static async void aInitializeProvider(IStoreProvider provider)
        {
            try
            {
                bool ok = await provider.aInitialize(Config);
                Debug.Log($"[Shop] {provider.Name} ready: {ok}");
                RaiseChanged();
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[Shop] {provider.Name} failed to initialize: {e.Message}");
            }
        }

        /// <summary>The store delivered a product: the grant is saved (idempotent for a non-consumable).</summary>
        private static void OnDelivered(string productId)
        {
            ShopProduct product = Config.Find(productId) ?? Config.FindByStoreId(productId);
            if (product == null)
            {
                Debug.LogWarning($"[Shop] delivered '{productId}', which the catalog does not list: ignored");
                return;
            }
            bool changed = SaveStore.RecordPurchase(product);
            Debug.Log($"[Shop] delivered {product.Id}{(changed ? string.Empty : " (already granted)")}");
            RaiseChanged();
        }

        private static void RaiseChanged()
        {
            try
            {
                Changed?.Invoke();
            }
            catch (Exception e)
            {
                Debug.LogException(e);
            }
        }

        /// <summary>The products the Shop page lists: the enabled ones, at most <see cref="ShopConfig.MaxShownProducts"/>.</summary>
        public static List<ShopProduct> ShownProducts()
        {
            List<ShopProduct> list = Config.EnabledProducts();
            if (list.Count > ShopConfig.MaxShownProducts)
            {
                list.RemoveRange(ShopConfig.MaxShownProducts, list.Count - ShopConfig.MaxShownProducts);
            }
            return list;
        }

        /// <summary>The product needs no new purchase (owned, or every grant already held).</summary>
        public static bool IsCovered(ShopProduct product) => SaveStore.IsCovered(product);

        /// <summary>The store's localized price, else the catalog's priceLabel.</summary>
        public static string PriceOf(ShopProduct product)
        {
            if (product == null)
            {
                return string.Empty;
            }
            string price = null;
            try
            {
                price = Provider?.LocalizedPrice(product.Id);
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Shop] price lookup failed: " + e.Message);
            }
            return string.IsNullOrEmpty(price) ? product.PriceLabel ?? string.Empty : price;
        }

        /// <summary>
        /// Buys <paramref name="productId"/>: AlreadyOwned without asking the store when the save already covers it,
        /// Unavailable while busy or with no store. Never throws.
        /// </summary>
        public static async Task<PurchaseResult> aPurchase(string productId)
        {
            ShopProduct product = Config.Find(productId);
            if (product == null || !product.Enabled)
            {
                return PurchaseResult.Of(PurchaseOutcome.Unavailable, productId, "not in the catalog");
            }
            if (IsCovered(product))
            {
                return PurchaseResult.Of(PurchaseOutcome.AlreadyOwned, productId);
            }
            if (Busy)
            {
                return PurchaseResult.Of(PurchaseOutcome.Unavailable, productId, "busy");
            }
            Busy = true;
            PurchaseResult result;
            try
            {
                result = await Provider.aPurchase(product);
            }
            catch (Exception e)
            {
                result = PurchaseResult.Of(PurchaseOutcome.Failed, productId, e.Message);
            }
            finally
            {
                Busy = false;
            }
            Debug.Log("[Shop] purchase " + result);
            RaiseChanged();
            return result;
        }

        /// <summary>Restore purchases: the store delivers every owned non-consumable again. Never throws.</summary>
        public static async Task<bool> aRestorePurchases()
        {
            if (Busy)
            {
                return false;
            }
            Busy = true;
            bool ok;
            try
            {
                ok = await Provider.aRestorePurchases();
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Shop] restore failed: " + e.Message);
                ok = false;
            }
            finally
            {
                Busy = false;
            }
            Debug.Log("[Shop] restore: " + ok);
            RaiseChanged();
            return ok;
        }
    }
}
