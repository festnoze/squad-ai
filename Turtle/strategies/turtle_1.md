# Modern Turtle Bot Rulepacks (2025)

> Six rule lists inspired by the original 1983 Turtle rules, updated for today’s markets.  
> Keep everything 100% systematic—no discretionary overrides.

---

## 1. Breakout & Trend-Entry Rules
- Dual-channel logic:  
  - System 1: Enter on 20-day breakout **only if** previous trade in that market was a loser.  
  - System 2: Otherwise wait for 55-day breakout.
- Confirm on daily close above/below the channel (ignore intraday spikes).
- Equities/ETFs: prefer 50-/100-day channels to cut noise; crypto: single 100-day channel.
- Volatility gate: trade only when ATR ≥ 1.2 × its own 180-day median (skip dead markets).
- No trade if price is within 0.25 × ATR of the channel after the close (avoid marginal signals).

## 2. Stop-Loss & Exit Rules
- Initial stop = 2 × ATR from entry price.
- Move stop to breakeven once trade gains +1 × ATR.
- Trailing exits:  
  - System 1 → 10-day opposite channel.  
  - System 2 → 20-day opposite channel.
- Time stop: exit any position older than 80 trading days if not already closed.
- Gap protection (crypto/single stocks): if open–close gap > 2 × ATR against you, flatten immediately.

## 3. Position Sizing & Risk Caps
- Unit risk = 1% of equity per entry (half of the original Turtles’ 2%).
- Size formula: `contracts = (0.01 × Equity) / (ATR × PointValue)` (round down).
- Portfolio heat (sum of open risk) ≤ 25% of equity.
- Correlation cap: when |ρ30d| > 0.6 between two markets, cut the second position’s size in half.
- Asset-class VaR cap: expected 1-day VaR per asset class ≤ 6% of equity.

## 4. Pyramiding Rules
- Add max 4 additional units, each at +0.5 × ATR in favorable direction, while heat ≤ 25%.
- Skip add-ons if ≥ 2 of last 5 trades in that instrument were losers (whipsaw brake).
- Crypto tweak: max 2 add-ons, spaced 0.25 × ATR (gap risk is higher).

## 5. Portfolio & Universe Rules
- Minimum breadth: ≥ 30 liquid markets spanning rates, FX, equity indexes, energies, metals, ags, softs, crypto (optional).
- Use micro futures/contracts (e.g., CME Micros) for accounts < $100k to keep sizing granular.
- Liquidity gate: trade only instruments with ≥ $5m ADV and < 3 price-limit days in the past 12 months.
- Roll futures 5 business days before first notice day; for perpetual swaps, rebalance weekly to avoid funding spikes.

## 6. Execution & Ops
- Enter using VWAP/time-sliced orders during the most liquid 2 hours of the session.
- Recompute ATRs, correlations, and sizes after each settlement close (not intraday).
- Slippage guard: if realized slippage > 1.5 × modeled, reduce unit risk or widen entry filters.
- Daily sanity checks: data integrity, margin availability, overnight risk limits.

## 7. Monitoring & Metrics
- Track: CAGR, max DD, MAR (CAGR/DD), Sharpe (daily), hit rate, average R-multiple, heat utilization.
- Month-end rebalance: update equity, recompute 1% unit, recheck class caps.
- Annual parameter review: only adjust if statistically significant over multi-decade walk-forward tests.

---

### Minimal Config Skeleton (YAML)

```yaml
risk:
  unit_pct: 0.01
  max_heat_pct: 0.25
  class_var_pct: 0.06
entries:
  sys1_breakout_days: 20
  sys2_breakout_days: 55
  confirm_on_close: true
  vol_gate_atr_mult: 1.2
exits:
  stop_init_atr_mult: 2.0
  breakeven_trigger_atr: 1.0
  trail_sys1_days: 10
  trail_sys2_days: 20
  time_stop_days: 80
pyramiding:
  max_addons: 4
  addon_step_atr: 0.5
  whipsaw_brake_losses: 2
portfolio:
  min_markets: 30
  corr_cap: 0.6
  liquidity_adv_usd: 5000000
execution:
  vwap_slice_hours: 2
  roll_days_before_fnd: 5
monitoring:
  slippage_factor_limit: 1.5