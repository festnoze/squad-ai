using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace OutOfSight.Core
{
    /// <summary>
    /// ADSSHOP (docs/next/progress/ADSSHOP.md): what the player bought, saved as SaveData "purchases" (the save version
    /// stays 1: a save without it loads with nothing bought). Owned holds the non-consumable product ids, Entitlements the
    /// keys their grants opened (<see cref="Core.Entitlements"/>), Consumed the count of each consumable bought. The
    /// entitlements are stored, not derived from the catalog, so a product later disabled or renamed in shop.json keeps
    /// what it granted. Like the options, a malformed object never fails the save: it only reads as empty.
    /// </summary>
    public sealed class SavePurchases
    {
        [JsonProperty("owned")] public List<string> Owned = new List<string>();
        [JsonProperty("entitlements")] public List<string> Entitlements = new List<string>();
        [JsonProperty("consumed")] public Dictionary<string, int> Consumed = new Dictionary<string, int>();

        /// <summary>True when the non-consumable <paramref name="productId"/> was bought.</summary>
        public bool Owns(string productId) => productId != null && Owned != null && Owned.Contains(productId);

        /// <summary>True when a purchase granted <paramref name="key"/>.</summary>
        public bool HasEntitlement(string key) => key != null && Entitlements != null && Entitlements.Contains(key);

        /// <summary>How many times the consumable <paramref name="productId"/> was bought.</summary>
        public int ConsumedCount(string productId)
        {
            return productId != null && Consumed != null && Consumed.TryGetValue(productId, out int count) ? count : 0;
        }

        /// <summary>
        /// True when <paramref name="product"/> needs no new purchase: a non-consumable already owned, or one whose every
        /// grant is already held (No ads after the Premium pack). A consumable is never owned.
        /// </summary>
        public bool CoveredBy(ShopProduct product)
        {
            if (product == null || product.Consumable)
            {
                return false;
            }
            if (Owns(product.Id))
            {
                return true;
            }
            if (product.Grants == null || product.Grants.Count == 0)
            {
                return false;
            }
            foreach (string grant in product.Grants)
            {
                if (!HasEntitlement(grant))
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>
        /// Records a delivered purchase: a non-consumable joins Owned once, a consumable's count goes up by one, and every
        /// grant joins Entitlements once. True when the save changed (a repeated delivery of a non-consumable, as a restore
        /// makes, changes nothing).
        /// </summary>
        public bool Grant(ShopProduct product)
        {
            if (product == null || string.IsNullOrEmpty(product.Id))
            {
                return false;
            }
            Owned = Owned ?? new List<string>();
            Entitlements = Entitlements ?? new List<string>();
            Consumed = Consumed ?? new Dictionary<string, int>();
            bool changed = false;
            if (product.Consumable)
            {
                Consumed[product.Id] = ConsumedCount(product.Id) + 1;
                changed = true;
            }
            else if (!Owned.Contains(product.Id)) // MUTATION:PURCHASE_OWNED_ONCE
            {
                Owned.Add(product.Id);
                changed = true;
            }
            if (product.Grants != null)
            {
                foreach (string grant in product.Grants)
                {
                    if (!string.IsNullOrEmpty(grant) && !Entitlements.Contains(grant))
                    {
                        Entitlements.Add(grant);
                        changed = true;
                    }
                }
            }
            return changed;
        }

        /// <summary>
        /// Parses the "purchases" object defensively: missing or not an object is empty; a list holding anything but
        /// strings keeps its strings; a count that is not a positive integer is skipped. Never throws.
        /// </summary>
        public static SavePurchases Parse(JToken token)
        {
            var purchases = new SavePurchases();
            if (!(token is JObject obj))
            {
                return purchases;
            }
            purchases.Owned = AdConfig.StrList(obj["owned"], new List<string>());
            purchases.Entitlements = AdConfig.StrList(obj["entitlements"], new List<string>());
            if (obj["consumed"] is JObject consumed)
            {
                foreach (JProperty p in consumed.Properties())
                {
                    if (p.Value.Type == JTokenType.Integer && !string.IsNullOrEmpty(p.Name))
                    {
                        long count = p.Value.Value<long>();
                        if (count > 0)
                        {
                            purchases.Consumed[p.Name] = (int)System.Math.Min(int.MaxValue, count);
                        }
                    }
                }
            }
            return purchases;
        }
    }
}
