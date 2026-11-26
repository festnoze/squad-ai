// ADSSHOP (docs/next/progress/ADSSHOP.md): the Unity IAP adapter (com.unity.purchasing 5.x, Google Play Billing on
// Android), compiled only with the scripting define symbol OOS_IAP_UNITY once the package is installed. Without the
// symbol this file is empty and the project compiles without the package. Optional local receipt validation needs a
// second symbol, OOS_IAP_RECEIPT_VALIDATION, once the GooglePlayTangle class was generated (Services > In-App
// Purchasing > Receipt Validation Obfuscator). Lives outside the game's asmdefs (Assembly-CSharp), which references the
// package's auto-referenced assemblies and the game's own. Written against the IAP 5 API; not compiled here, since the
// package is not installed yet: check the first build with the symbol for API drift.
#if OOS_IAP_UNITY
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Purchasing;
#if OOS_IAP_RECEIPT_VALIDATION
using UnityEngine.Purchasing.Security;
#endif

namespace OutOfSight.Adapters
{
    /// <summary>
    /// ADSSHOP: <see cref="IStoreProvider"/> over Unity IAP 5 (StoreController). Products are the catalog's
    /// (shop.json: id, storeId, type). The two-step flow: a pending order is granted first (<see cref="Delivered"/>, which
    /// StoreService saves), then confirmed, so a crash in between only re-delivers it at the next launch. At connection
    /// the existing purchases are fetched, so a reinstall gets its non-consumables back without pressing Restore.
    /// </summary>
    public sealed class UnityIapStoreProvider : IStoreProvider
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void Register()
        {
            StoreProviderRegistry.Register(ShopConfig.ProviderUnityIap, () => new UnityIapStoreProvider());
        }

        private StoreController store;
        private ShopConfig config;
        private bool connected;
        private TaskCompletionSource<bool> fetching;
        private TaskCompletionSource<PurchaseResult> buying;
        private string buyingId;

        public string Name => ShopConfig.ProviderUnityIap;
        public bool Ready { get; private set; }
        public event Action<string> Delivered;

        public async Task<bool> aInitialize(ShopConfig shop)
        {
            config = shop;
            try
            {
                store = UnityIAPServices.StoreController();
                // Every event before Connect: a purchase pending since the last session may arrive at once.
                store.OnPurchasePending += OnPurchasePending;
                store.OnPurchaseConfirmed += OnPurchaseConfirmed;
                store.OnPurchaseFailed += OnPurchaseFailed;
                store.OnPurchaseDeferred += OnPurchaseDeferred;
                store.OnStoreConnected += () => connected = true;
                store.OnStoreDisconnected += failure =>
                {
                    connected = false;
                    Debug.LogWarning("[Shop] unity_iap: store disconnected: " + failure.Message);
                    fetching?.TrySetResult(false);
                };
                store.OnProductsFetched += products => fetching?.TrySetResult(true);
                store.OnProductsFetchFailed += failure =>
                {
                    Debug.LogWarning("[Shop] unity_iap: product fetch failed: " + failure.FailureReason);
                    fetching?.TrySetResult(false);
                };
                store.OnPurchasesFetched += OnPurchasesFetched;
                store.OnPurchasesFetchFailed += failure => Debug.LogWarning("[Shop] unity_iap: purchase fetch failed: " + failure.Message);

                await store.Connect();
                if (!connected)
                {
                    return false;
                }
                fetching = new TaskCompletionSource<bool>();
                store.FetchProducts(Definitions());
                Ready = await fetching.Task;
                fetching = null;
                if (Ready)
                {
                    store.FetchPurchases();
                }
                return Ready;
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Shop] unity_iap: initialization failed: " + e.Message);
                return false;
            }
        }

        private List<ProductDefinition> Definitions()
        {
            var list = new List<ProductDefinition>();
            foreach (ShopProduct p in config.Products)
            {
                if (p == null)
                {
                    continue;
                }
                ProductType type = p.Consumable ? ProductType.Consumable : ProductType.NonConsumable;
                list.Add(p.StoreId == p.Id ? new ProductDefinition(p.Id, type) : new ProductDefinition(p.Id, p.StoreId, type));
            }
            return list;
        }

        public string LocalizedPrice(string productId)
        {
            Product product = Ready ? store.GetProductById(productId) : null;
            return product != null && product.metadata != null ? product.metadata.localizedPriceString : null;
        }

        public Task<PurchaseResult> aPurchase(ShopProduct product)
        {
            Product item = Ready && product != null ? store.GetProductById(product.Id) : null;
            if (item == null || !item.availableToPurchase)
            {
                return Task.FromResult(PurchaseResult.Of(PurchaseOutcome.Unavailable, product?.Id));
            }
            if (buying != null)
            {
                return Task.FromResult(PurchaseResult.Of(PurchaseOutcome.Unavailable, product.Id, "busy"));
            }
            buying = new TaskCompletionSource<PurchaseResult>();
            buyingId = product.Id;
            try
            {
                store.PurchaseProduct(item);
            }
            catch (Exception e)
            {
                Finish(PurchaseResult.Of(PurchaseOutcome.Failed, product.Id, e.Message));
            }
            return buying != null ? buying.Task : Task.FromResult(PurchaseResult.Of(PurchaseOutcome.Failed, product.Id));
        }

        public Task<bool> aRestorePurchases()
        {
            if (!Ready)
            {
                return Task.FromResult(false);
            }
            var restored = new TaskCompletionSource<bool>();
            try
            {
                // Each restored purchase comes back through OnPurchasePending (then OnPurchasesFetched for the confirmed ones).
                store.RestoreTransactions((success, error) =>
                {
                    if (!success)
                    {
                        Debug.LogWarning("[Shop] unity_iap: restore failed: " + error);
                    }
                    restored.TrySetResult(success);
                });
                store.FetchPurchases();
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Shop] unity_iap: restore failed: " + e.Message);
                restored.TrySetResult(false);
            }
            return restored.Task;
        }

        // ----- Store events -----

        private void OnPurchasePending(PendingOrder order)
        {
            bool valid = Validate(order);
            foreach (CartItem item in order.CartOrdered.Items())
            {
                string id = item.Product != null ? item.Product.definition.id : null;
                if (valid && id != null)
                {
                    // Granted (saved) before the confirmation: a crash in between only re-delivers it next launch.
                    Delivered?.Invoke(id);
                }
                if (id == buyingId)
                {
                    Finish(PurchaseResult.Of(valid ? PurchaseOutcome.Purchased : PurchaseOutcome.Failed, id, valid ? null : "invalid receipt"));
                }
            }
            if (valid)
            {
                store.ConfirmPurchase(order);
            }
        }

        private void OnPurchaseConfirmed(Order order)
        {
            if (order is FailedOrder failed)
            {
                Debug.LogWarning($"[Shop] unity_iap: confirmation failed: {failed.FailureReason} {failed.Details}");
            }
        }

        private void OnPurchaseFailed(FailedOrder failed)
        {
            string id = FirstId(failed);
            PurchaseOutcome outcome;
            switch (failed.FailureReason)
            {
                case PurchaseFailureReason.UserCancelled:
                    outcome = PurchaseOutcome.Cancelled;
                    break;
                case PurchaseFailureReason.DuplicateTransaction:
                    // Google Play's "item already owned": grant it again, harmlessly.
                    outcome = PurchaseOutcome.AlreadyOwned;
                    if (id != null)
                    {
                        Delivered?.Invoke(id);
                    }
                    break;
                case PurchaseFailureReason.ProductUnavailable:
                case PurchaseFailureReason.PurchasingUnavailable:
                    outcome = PurchaseOutcome.Unavailable;
                    break;
                default:
                    outcome = PurchaseOutcome.Failed;
                    break;
            }
            Debug.Log($"[Shop] unity_iap: purchase of {id} failed: {failed.FailureReason} {failed.Details}");
            if (id == null || id == buyingId)
            {
                Finish(PurchaseResult.Of(outcome, id ?? buyingId, failed.Details));
            }
        }

        private void OnPurchaseDeferred(DeferredOrder deferred)
        {
            // Google Play's pending payments (cash, parental approval): granted later through OnPurchasePending.
            string id = FirstId(deferred);
            if (id == null || id == buyingId)
            {
                Finish(PurchaseResult.Of(PurchaseOutcome.Pending, id ?? buyingId));
            }
        }

        private void OnPurchasesFetched(Orders orders)
        {
            // The confirmed non-consumables the account owns (a reinstall, another device): granted again, idempotently.
            foreach (ConfirmedOrder order in orders.ConfirmedOrders)
            {
                foreach (CartItem item in order.CartOrdered.Items())
                {
                    string id = item.Product != null ? item.Product.definition.id : null;
                    ShopProduct product = config.Find(id);
                    if (product != null && !product.Consumable)
                    {
                        Delivered?.Invoke(id);
                    }
                }
            }
        }

        private static string FirstId(Order order)
        {
            if (order == null || order.CartOrdered == null)
            {
                return null;
            }
            foreach (CartItem item in order.CartOrdered.Items())
            {
                if (item.Product != null)
                {
                    return item.Product.definition.id;
                }
            }
            return null;
        }

        private void Finish(PurchaseResult result)
        {
            TaskCompletionSource<PurchaseResult> pending = buying;
            buying = null;
            buyingId = null;
            pending?.TrySetResult(result);
        }

        /// <summary>Local Google Play receipt validation when OOS_IAP_RECEIPT_VALIDATION is defined; true otherwise.</summary>
        private static bool Validate(PendingOrder order)
        {
#if OOS_IAP_RECEIPT_VALIDATION && UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                var validator = new CrossPlatformValidator(GooglePlayTangle.Data(), Application.identifier);
                validator.Validate(order.Info.Receipt);
                return true;
            }
            catch (IAPSecurityException e)
            {
                Debug.LogWarning("[Shop] unity_iap: invalid receipt, not granted: " + e.Message);
                return false;
            }
#else
            return true;
#endif
        }
    }
}
#endif
