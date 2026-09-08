"""Unit-economics model for ad- and IAP-monetized mobile games.

Pure stdlib. Run it to print the tables used in MOBILE_GAMES_BUSINESS_PLAN.md:

    python mobile_games_model.py

Every number below is an assumption to test, sourced from the September 2026
benchmarks quoted in the plan. Change the dataclasses, rerun, paste.
"""
from __future__ import annotations

from dataclasses import dataclass

USD_TO_EUR = 0.92
STORE_FEE = 0.15          # Apple Small Business Program / Google Play first 1M USD
HORIZON_DAYS = 180        # lifetime window used to turn retention into "player-days"


# --------------------------------------------------------------------------- retention
@dataclass(frozen=True)
class Retention:
    name: str
    d1: float
    d7: float
    d30: float

    def curve(self, day: int) -> float:
        """Piecewise power-law interpolation through D1, D7, D30, decaying after D30."""
        if day <= 0:
            return 1.0
        if day <= 7:
            return _powlaw(1, self.d1, 7, self.d7, day)
        if day <= 30:
            return _powlaw(7, self.d7, 30, self.d30, day)
        # After D30 keep the D7->D30 slope, which is already steep.
        return _powlaw(7, self.d7, 30, self.d30, day)

    def player_days(self) -> float:
        """Expected active days per install over the horizon (day 0 counts as 1)."""
        return 1.0 + sum(self.curve(d) for d in range(1, HORIZON_DAYS + 1))


def _powlaw(x0: float, y0: float, x1: float, y1: float, x: float) -> float:
    import math
    b = math.log(y1 / y0) / math.log(x1 / x0)
    return y0 * (x / x0) ** b


RETENTIONS = {
    "weak": Retention("weak (below industry average)", 0.20, 0.06, 0.02),
    "average": Retention("industry average 2026", 0.26, 0.10, 0.04),
    "good": Retention("hybrid-casual publisher bar", 0.35, 0.15, 0.06),
}


# --------------------------------------------------------------------------- monetization
@dataclass(frozen=True)
class AdMix:
    """Impressions per DAU per day and blended eCPM (USD per 1,000) for a geo mix."""
    name: str
    rewarded_per_dau: float
    rewarded_ecpm: float
    interstitial_per_dau: float
    interstitial_ecpm: float
    banner_per_dau: float
    banner_ecpm: float

    def arpdau_usd(self) -> float:
        return (self.rewarded_per_dau * self.rewarded_ecpm
                + self.interstitial_per_dau * self.interstitial_ecpm
                + self.banner_per_dau * self.banner_ecpm) / 1000.0


# Blended eCPMs: an organic French indie audience is maybe 30% tier 1, the rest lower
# tiers, so the blend is far below the 15-30 USD rewarded eCPM quoted for the US.
AD_MIXES = {
    "low": AdMix("low: mixed geos, light ad load", 1.0, 6.0, 2.0, 3.0, 15.0, 0.30),
    "mid": AdMix("mid: 40% tier 1, hybrid-casual ad load", 2.0, 10.0, 3.0, 5.0, 20.0, 0.50),
    "high": AdMix("high: US-heavy, aggressive ad load", 3.0, 18.0, 4.0, 8.0, 25.0, 1.00),
}


@dataclass(frozen=True)
class IapMix:
    """Lifetime IAP per install, before store fee."""
    name: str
    remove_ads_conv: float     # share of installs buying the remove-ads pack
    remove_ads_price: float    # USD
    payer_conv: float          # share of installs buying skins / powerups / passes
    arppu: float               # lifetime USD per paying user

    def gross_per_install_usd(self) -> float:
        return self.remove_ads_conv * self.remove_ads_price + self.payer_conv * self.arppu


IAP_MIXES = {
    "none": IapMix("ads only", 0.0, 0.0, 0.0, 0.0),
    "low": IapMix("remove-ads only, weak conversion", 0.005, 2.99, 0.0, 0.0),
    "mid": IapMix("remove-ads + cosmetics, casual conversion", 0.010, 2.99, 0.015, 9.0),
    "high": IapMix("remove-ads + skins + starter/battle pass", 0.015, 3.99, 0.030, 16.0),
}


# --------------------------------------------------------------------------- economics
def ltv_usd(ret: Retention, ads: AdMix, iap: IapMix, remove_ads_kills_ads: bool = True) -> dict:
    """Net lifetime value per install in USD, after store fee on IAP."""
    days = ret.player_days()
    ad_share = 1.0 - (iap.remove_ads_conv if remove_ads_kills_ads else 0.0)
    ad_ltv = ads.arpdau_usd() * days * ad_share
    iap_ltv = iap.gross_per_install_usd() * (1 - STORE_FEE)
    return {"player_days": days, "ad_ltv": ad_ltv, "iap_ltv": iap_ltv, "ltv": ad_ltv + iap_ltv}


@dataclass(frozen=True)
class Scenario:
    name: str
    installs_per_month: int
    retention: str
    ads: str
    iap: str
    note: str


SCENARIOS = [
    Scenario("A. Typical release, no marketing", 500, "weak", "low", "low",
             "What most of the 100 indie releases look like"),
    Scenario("B. Decent ASO, small community", 3_000, "average", "mid", "mid",
             "Store optimization, a devlog, a subreddit post that worked"),
    Scenario("C. Well-optimized organic ceiling", 12_000, "average", "mid", "mid",
             "Upper bound quoted for organic-only games (200-500 installs/day)"),
    Scenario("D. Featured or viral month", 60_000, "good", "mid", "mid",
             "A store feature or a creator video; rarely repeats"),
    Scenario("E. The 1-in-100 hit with a publisher", 300_000, "good", "high", "high",
             "Publisher buys installs; you keep 30-50% of net revenue (not modeled here)"),
]


def steady_state_revenue(sc: Scenario) -> dict:
    ret, ads, iap = RETENTIONS[sc.retention], AD_MIXES[sc.ads], IAP_MIXES[sc.iap]
    v = ltv_usd(ret, ads, iap)
    monthly_usd = sc.installs_per_month * v["ltv"]      # steady state: cohorts overlap
    return {**v, "monthly_usd": monthly_usd, "monthly_eur": monthly_usd * USD_TO_EUR,
            "yearly_eur": monthly_usd * USD_TO_EUR * 12}


# --------------------------------------------------------------------------- costs
@dataclass(frozen=True)
class GameCost:
    dev_hours: int = 250          # prototype to store-ready hybrid-casual game with agents
    live_hours_per_month: int = 10
    hour_value_eur: float = 30.0  # imputed, same convention as ideas3.md
    cash_fixed_eur: float = 350.0 # Apple 99 USD/yr, Google 25 USD, icons, SFX, LLM usage
    cash_monthly_eur: float = 60.0  # LLM usage, tooling, capture tools


def game_pnl(sc: Scenario, cost: GameCost, months: int = 12) -> dict:
    rev = steady_state_revenue(sc)
    # Ramp: cohorts take ~3 months to reach steady state; count 9.5 steady months of 12.
    ramp_factor = (months - 2.5) / months
    revenue = rev["monthly_eur"] * months * ramp_factor
    cash_cost = cost.cash_fixed_eur + cost.cash_monthly_eur * months
    labor = (cost.dev_hours + cost.live_hours_per_month * months) * cost.hour_value_eur
    return {"revenue_eur": revenue, "cash_cost_eur": cash_cost, "labor_eur": labor,
            "cash_result_eur": revenue - cash_cost,
            "economic_result_eur": revenue - cash_cost - labor,
            "hours": cost.dev_hours + cost.live_hours_per_month * months}


def breakeven_installs_per_month(ret: str, ads: str, iap: str, cost: GameCost, months: int = 12) -> float:
    v = ltv_usd(RETENTIONS[ret], AD_MIXES[ads], IAP_MIXES[iap])["ltv"] * USD_TO_EUR
    total_cost = cost.cash_fixed_eur + cost.cash_monthly_eur * months + \
        (cost.dev_hours + cost.live_hours_per_month * months) * cost.hour_value_eur
    ramp_factor = (months - 2.5) / months
    return total_cost / (v * months * ramp_factor)


# --------------------------------------------------------------------------- report
def fmt(x: float, nd: int = 2) -> str:
    return f"{x:,.{nd}f}"


def main() -> None:
    print("## Retention -> player-days per install (180-day horizon)")
    print("| Curve | D1 | D7 | D30 | Player-days |")
    print("|---|---|---|---|---|")
    for r in RETENTIONS.values():
        print(f"| {r.name} | {r.d1:.0%} | {r.d7:.0%} | {r.d30:.0%} | {fmt(r.player_days(), 1)} |")

    print("\n## Ad ARPDAU by mix (USD)")
    print("| Mix | Rewarded/DAU x eCPM | Interstitial/DAU x eCPM | Banner/DAU x eCPM | ARPDAU |")
    print("|---|---|---|---|---|")
    for a in AD_MIXES.values():
        print(f"| {a.name} | {a.rewarded_per_dau:g} x {a.rewarded_ecpm:g} | "
              f"{a.interstitial_per_dau:g} x {a.interstitial_ecpm:g} | "
              f"{a.banner_per_dau:g} x {a.banner_ecpm:g} | {fmt(a.arpdau_usd(), 3)} |")

    print("\n## Net LTV per install (USD) by retention x monetization")
    print("| Retention | Ads only (mid) | Ads mid + IAP low | Ads mid + IAP mid | Ads high + IAP high |")
    print("|---|---|---|---|---|")
    for rk, r in RETENTIONS.items():
        cells = []
        for ak, ik in (("mid", "none"), ("mid", "low"), ("mid", "mid"), ("high", "high")):
            v = ltv_usd(r, AD_MIXES[ak], IAP_MIXES[ik])
            cells.append(f"{fmt(v['ltv'])} (ads {fmt(v['ad_ltv'])} / iap {fmt(v['iap_ltv'])})")
        print(f"| {r.name} | " + " | ".join(cells) + " |")

    print("\n## Scenarios: steady-state revenue per game")
    print("| Scenario | Installs/month | LTV USD | Revenue EUR/month | Revenue EUR/year | Note |")
    print("|---|---|---|---|---|---|")
    for sc in SCENARIOS:
        r = steady_state_revenue(sc)
        print(f"| {sc.name} | {sc.installs_per_month:,} | {fmt(r['ltv'])} | "
              f"{fmt(r['monthly_eur'], 0)} | {fmt(r['yearly_eur'], 0)} | {sc.note} |")

    cost = GameCost()
    print(f"\n## 12-month P&L per game (dev {cost.dev_hours} h, live {cost.live_hours_per_month} h/month, "
          f"labor valued {cost.hour_value_eur:g} EUR/h, cash {cost.cash_fixed_eur:g} + {cost.cash_monthly_eur:g}/month)")
    print("| Scenario | Revenue EUR | Cash costs EUR | Cash result EUR | Imputed labor EUR | Economic result EUR | Hours |")
    print("|---|---|---|---|---|---|---|")
    for sc in SCENARIOS:
        p = game_pnl(sc, cost)
        print(f"| {sc.name} | {fmt(p['revenue_eur'], 0)} | {fmt(p['cash_cost_eur'], 0)} | "
              f"{fmt(p['cash_result_eur'], 0)} | {fmt(p['labor_eur'], 0)} | {fmt(p['economic_result_eur'], 0)} | {p['hours']} |")

    print("\n## Installs per month needed to break even over 12 months (cash + imputed labor)")
    print("| Retention | Ads only (mid) | Ads mid + IAP mid | Ads high + IAP high |")
    print("|---|---|---|---|")
    for rk in RETENTIONS:
        cells = [fmt(breakeven_installs_per_month(rk, a, i, cost), 0)
                 for a, i in (("mid", "none"), ("mid", "mid"), ("high", "high"))]
        print(f"| {RETENTIONS[rk].name} | " + " | ".join(cells) + " |")

    print("\n## Paid acquisition: LTV vs CPI (USD), payback needs LTV >= 1.3 x CPI")
    cpis = {"Android EU casual": 0.53, "Android US casual": 1.50, "iOS EU casual": 1.70, "iOS US puzzle": 3.00}
    print("| Retention x monetization | LTV | " + " | ".join(cpis) + " |")
    print("|---|---|" + "---|" * len(cpis))
    for rk, ak, ik in (("average", "mid", "mid"), ("good", "mid", "mid"), ("good", "high", "high")):
        v = ltv_usd(RETENTIONS[rk], AD_MIXES[ak], IAP_MIXES[ik])["ltv"]
        cells = ["OK" if v >= 1.3 * c else f"no ({fmt(v / c, 2)}x)" for c in cpis.values()]
        print(f"| {rk} / ads {ak} / iap {ik} | {fmt(v)} | " + " | ".join(cells) + " |")

    print("\n## Portfolio: 4 prototypes a year, kill 3 at soft launch, 1 reaches scenario B or C")
    proto = GameCost(dev_hours=80, live_hours_per_month=0, cash_fixed_eur=80, cash_monthly_eur=0)
    killed = 3 * (proto.dev_hours * proto.hour_value_eur + proto.cash_fixed_eur)
    for target in SCENARIOS[1:3]:
        p = game_pnl(target, cost)
        total_hours = 3 * proto.dev_hours + p["hours"]
        econ = p["economic_result_eur"] - killed
        cash = p["cash_result_eur"] - 3 * proto.cash_fixed_eur
        print(f"- Survivor = {target.name}: cash result {fmt(cash, 0)} EUR, economic result {fmt(econ, 0)} EUR, "
              f"{total_hours} h in the year ({fmt(total_hours / 48, 1)} h/week)")


if __name__ == "__main__":
    main()
