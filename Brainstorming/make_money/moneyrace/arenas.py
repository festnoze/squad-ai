"""Arenas: the places where agents make or lose money each generation.

Contract for every arena:
- run(agents, rng) mutates agent wealth exclusively through agent.credit()
- it returns a summary dict whose "system_delta" equals the total money the
  arena created (positive) or destroyed (negative) across all agents; the
  test suite enforces this accounting, so a new arena cannot silently leak
  or print money.
"""


class Arena:
    name = "arena"

    def run(self, agents, rng):
        raise NotImplementedError


class AuctionArena(Arena):
    """Sealed-bid second-price auctions on items of hidden value.

    Each bidder sees a noisy appraisal of the true value. The winner pays the
    second-highest bid (money leaves the system) and receives the true value
    (money enters the system). Overtrusting a high appraisal is the classic
    winner's curse; shading too much means never winning anything.
    """

    name = "auction"

    def __init__(self, group_size=6, value_low=20.0, value_high=120.0, noise=0.30):
        self.group_size = group_size
        self.value_low = value_low
        self.value_high = value_high
        self.noise = noise

    def run(self, agents, rng):
        pool = [a for a in agents if a.alive]
        delta = 0.0
        sales = 0
        rounds = max(1, len(pool) // 3)
        for _ in range(rounds):
            k = min(self.group_size, len(pool))
            if k < 2:
                break
            group = rng.sample(pool, k)
            true_value = rng.uniform(self.value_low, self.value_high)
            bids = []
            for agent in group:
                signal = true_value * (1.0 + rng.gauss(0.0, self.noise))
                bid = agent.policy.auction_bid(max(0.0, signal), agent.wealth)
                bids.append((bid, agent))
            bids.sort(key=lambda pair: pair[0], reverse=True)
            best_bid, winner = bids[0]
            price = bids[1][0]
            if best_bid <= 0.0 or price <= 0.0:
                continue
            winner.credit(true_value - price)
            delta += true_value - price
            sales += 1
        return {"arena": self.name, "system_delta": delta, "sales": sales}


class MarketArena(Arena):
    """Trade a synthetic price series against the outside world.

    Each generation draws a drift regime (bull, flat, bear), so momentum and
    mean-reversion genes pay off in different regimes. Agents risk a slice of
    their wealth as trading capital; losses are capped at that capital, and
    every position change pays a fee (money burned).
    """

    name = "market"

    def __init__(self, ticks=40, vol=0.02, fee=0.0015):
        self.ticks = ticks
        self.vol = vol
        self.fee = fee

    def run(self, agents, rng):
        prices = [100.0]
        drift = rng.choice([-0.004, 0.0, 0.004])
        for _ in range(self.ticks):
            step = drift + rng.gauss(0.0, self.vol)
            prices.append(max(1.0, prices[-1] * (1.0 + step)))

        delta = 0.0
        for agent in [a for a in agents if a.alive]:
            capital = agent.wealth * (0.10 + 0.40 * agent.genome["risk"])
            if capital <= 0.0:
                continue
            pnl = 0.0
            position = 0.0
            for t in range(5, self.ticks):
                momentum_signal = (prices[t] - prices[t - 5]) / prices[t - 5]
                moving_avg = sum(prices[t - 5:t]) / 5.0
                reversion_signal = (moving_avg - prices[t]) / prices[t]
                target = agent.policy.market_position(momentum_signal, reversion_signal)
                pnl -= abs(target - position) * self.fee * capital
                position = target
                tick_return = prices[t + 1] / prices[t] - 1.0
                pnl += position * capital * tick_return
            pnl = max(pnl, -capital)
            agent.credit(pnl)
            delta += pnl
        return {"arena": self.name, "system_delta": delta,
                "drift": drift, "final_price": round(prices[-1], 2)}


class PredictionArena(Arena):
    """Bet on binary events against a house that misprices them slightly.

    The house quotes a price (implied probability) with some error around the
    true probability; agents receive their own noisy signal. Profit requires
    betting only when the perceived edge beats a confidence threshold, and
    sizing the stake sensibly. The house rakes 2% of winnings.
    """

    name = "prediction"

    def __init__(self, events=3, house_error=0.08, signal_noise=0.15, rake=0.02):
        self.events = events
        self.house_error = house_error
        self.signal_noise = signal_noise
        self.rake = rake

    def run(self, agents, rng):
        delta = 0.0
        bets = 0
        for _ in range(self.events):
            true_prob = rng.uniform(0.15, 0.85)
            price = min(0.95, max(0.05, true_prob + rng.gauss(0.0, self.house_error)))
            outcome = rng.random() < true_prob
            for agent in [a for a in agents if a.alive]:
                signal = min(0.99, max(0.01, true_prob + rng.gauss(0.0, self.signal_noise)))
                bet_yes, stake = agent.policy.prediction_bet(signal, price, agent.wealth)
                if stake <= 0.0:
                    continue
                stake = min(stake, agent.wealth)
                if bet_yes:
                    pnl = stake * (1.0 / price - 1.0) if outcome else -stake
                else:
                    pnl = stake * (1.0 / (1.0 - price) - 1.0) if not outcome else -stake
                if pnl > 0.0:
                    pnl *= (1.0 - self.rake)
                agent.credit(pnl)
                delta += pnl
                bets += 1
        return {"arena": self.name, "system_delta": delta, "bets": bets}


ARENA_REGISTRY = {
    AuctionArena.name: AuctionArena,
    MarketArena.name: MarketArena,
    PredictionArena.name: PredictionArena,
}
