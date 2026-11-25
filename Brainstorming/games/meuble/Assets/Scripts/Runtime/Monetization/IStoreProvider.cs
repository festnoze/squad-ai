using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>ADSSHOP: how a purchase attempt ended.</summary>
    public enum PurchaseOutcome
    {
        /// <summary>Paid and delivered (the grant is saved before this result returns).</summary>
        Purchased,
        /// <summary>The store says the player already owns it (it is granted again, harmlessly).</summary>
        AlreadyOwned,
        /// <summary>The player backed out of the store's dialog.</summary>
        Cancelled,
        /// <summary>Waiting for an approval or a slow payment: delivered later, through <see cref="IStoreProvider.Delivered"/>.</summary>
        Pending,
        Failed,
        /// <summary>No store (not connected, the product unknown to it, or no store at all on this platform).</summary>
        Unavailable,
    }

    /// <summary>ADSSHOP: the result of <see cref="IStoreProvider.aPurchase"/>.</summary>
    public struct PurchaseResult
    {
        public PurchaseOutcome Outcome;
        public string ProductId;
        public string Error;

        public static PurchaseResult Of(PurchaseOutcome outcome, string productId, string error = null)
        {
            return new PurchaseResult { Outcome = outcome, ProductId = productId, Error = error };
        }

        public override string ToString() => $"{ProductId}: {Outcome}" + (Error != null ? " (" + Error + ")" : string.Empty);
    }

    /// <summary>
    /// ADSSHOP (docs/next/progress/ADSSHOP.md): one store behind <see cref="StoreService"/>. A provider raises
    /// <see cref="Delivered"/> on the main thread for every purchase the store hands over (a new one, a restored one, one
    /// left pending by an earlier session) BEFORE it finishes (confirms) the transaction: StoreService saves the grant in
    /// that event, so a crash in between only means the store delivers it again. To plug another store: implement this,
    /// register it with <see cref="StoreProviderRegistry.Register"/> from a [RuntimeInitializeOnLoadMethod], and set
    /// "provider" in Resources/Config/shop.json.
    /// </summary>
    public interface IStoreProvider
    {
        /// <summary>The registry name ("none", "simulated", "unity_iap"...).</summary>
        string Name { get; }

        /// <summary>Connected, with the catalog's products fetched.</summary>
        bool Ready { get; }

        /// <summary>A purchase to grant, by the catalog's game id (<see cref="ShopProduct.Id"/>).</summary>
        event Action<string> Delivered;

        /// <summary>Connects to the store and fetches the catalog's products. True when ready.</summary>
        Task<bool> aInitialize(ShopConfig config);

        /// <summary>The store's localized price of a product ("2,99 €"), or null when unknown.</summary>
        string LocalizedPrice(string productId);

        /// <summary>Buys <paramref name="product"/>; completes once the store answered. Never throws.</summary>
        Task<PurchaseResult> aPurchase(ShopProduct product);

        /// <summary>Asks the store to deliver every owned non-consumable again. True when the store answered. Never throws.</summary>
        Task<bool> aRestorePurchases();
    }

    /// <summary>ADSSHOP: the store names <see cref="StoreService"/> can create. "none" and "simulated" are built in.</summary>
    public static class StoreProviderRegistry
    {
        private static readonly Dictionary<string, Func<IStoreProvider>> Factories = new Dictionary<string, Func<IStoreProvider>>
        {
            { ShopConfig.ProviderNone, () => new NoStoreProvider() },
            { ShopConfig.ProviderSimulated, () => new SimulatedStoreProvider() },
        };

        public static void Register(string name, Func<IStoreProvider> factory)
        {
            string key = AdConfig.NormalizeName(name);
            if (string.IsNullOrEmpty(key) || factory == null)
            {
                return;
            }
            Factories[key] = factory;
        }

        public static bool Has(string name)
        {
            string key = AdConfig.NormalizeName(name);
            return key != null && Factories.ContainsKey(key);
        }

        /// <summary>A new provider of that name, or null when none is registered (its package or define symbol is missing).</summary>
        public static IStoreProvider Create(string name)
        {
            string key = AdConfig.NormalizeName(name);
            if (key == null || !Factories.TryGetValue(key, out Func<IStoreProvider> factory))
            {
                return null;
            }
            try
            {
                return factory();
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[Shop] cannot create the store '{key}': {e.Message}");
                return null;
            }
        }
    }

    /// <summary>ADSSHOP: no store: every purchase is Unavailable.</summary>
    public sealed class NoStoreProvider : IStoreProvider
    {
        public string Name => ShopConfig.ProviderNone;
        public bool Ready => false;

        public event Action<string> Delivered
        {
            add { }
            remove { }
        }

        public Task<bool> aInitialize(ShopConfig config) => Task.FromResult(false);
        public string LocalizedPrice(string productId) => null;

        public Task<PurchaseResult> aPurchase(ShopProduct product)
        {
            return Task.FromResult(PurchaseResult.Of(PurchaseOutcome.Unavailable, product?.Id));
        }

        public Task<bool> aRestorePurchases() => Task.FromResult(false);
    }

    /// <summary>
    /// ADSSHOP: the development store. Every purchase succeeds after a short pause, locally (no money, no account); a
    /// restore delivers the owned products again from the save. The prices shown are the catalog's priceLabel. Never ship
    /// it: a non-editor run logs a warning at initialization.
    /// </summary>
    public sealed class SimulatedStoreProvider : IStoreProvider
    {
        /// <summary>The fake store's answer time, in milliseconds.</summary>
        public static int DelayMs = 500;

        public string Name => ShopConfig.ProviderSimulated;
        public bool Ready { get; private set; }
        public event Action<string> Delivered;

        public Task<bool> aInitialize(ShopConfig config)
        {
            Ready = true;
            if (!Application.isEditor)
            {
                Debug.LogWarning("[Shop] the Simulated store runs in a player build: purchases are free. Set \"provider\" in Resources/Config/shop.json to unity_iap before release");
            }
            return Task.FromResult(true);
        }

        public string LocalizedPrice(string productId) => null;

        public async Task<PurchaseResult> aPurchase(ShopProduct product)
        {
            if (product == null)
            {
                return PurchaseResult.Of(PurchaseOutcome.Unavailable, null);
            }
            await Task.Delay(DelayMs);
            Delivered?.Invoke(product.Id);
            return PurchaseResult.Of(PurchaseOutcome.Purchased, product.Id);
        }

        public async Task<bool> aRestorePurchases()
        {
            await Task.Delay(DelayMs);
            SavePurchases purchases = SaveStore.Current.Purchases;
            if (purchases != null && purchases.Owned != null)
            {
                foreach (string id in new List<string>(purchases.Owned))
                {
                    Delivered?.Invoke(id);
                }
            }
            return true;
        }
    }
}
