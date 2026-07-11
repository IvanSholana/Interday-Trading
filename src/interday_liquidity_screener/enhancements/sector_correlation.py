"""
P9 Sector/Correlation Guard + Portfolio-Level Risk.

Prevents over-concentration in one sector and checks correlation between
candidates to ensure diversification. Also provides portfolio beta calculation.

Usage:
    from enhancements.sector_correlation import SectorCorrelationGuard
    guard = SectorCorrelationGuard(enabled=True)
    result = guard.check_portfolio(candidates_df, history_dict)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# IDX sector mapping (based on IDX sector classification)
IDX_SECTOR_MAP: dict[str, str] = {
    # Energy & Mining
    "ADRO": "ENERGY", "ITMG": "ENERGY", "PTBA": "ENERGY", "MEDC": "ENERGY",
    "AKRA": "ENERGY", "ELSA": "ENERGY", "ESSA": "ENERGY", "ADMR": "ENERGY",
    # Mining / Metals
    "ANTM": "MINING", "INCO": "MINING", "TINS": "MINING", "MDKA": "MINING",
    "NICL": "MINING", "MBMA": "MINING",
    # Banking
    "BBCA": "BANKING", "BBRI": "BANKING", "BMRI": "BANKING", "BBNI": "BANKING",
    "BRIS": "BANKING", "BBTN": "BANKING", "MEGA": "BANKING",
    # Telco
    "TLKM": "TELCO", "ISAT": "TELCO", "EXCL": "TELCO", "TOWR": "TELCO",
    "MTEL": "TELCO",
    # Consumer
    "UNVR": "CONSUMER", "ICBP": "CONSUMER", "INDF": "CONSUMER", "MYOR": "CONSUMER",
    "SIDO": "CONSUMER", "ACES": "CONSUMER", "AMRT": "CONSUMER",
    # Infrastructure / Property
    "JSMR": "INFRA", "WIKA": "INFRA", "PTPP": "INFRA", "BSDE": "PROPERTY",
    "CTRA": "PROPERTY", "SMRA": "PROPERTY",
    # Healthcare
    "MIKA": "HEALTHCARE", "KLBF": "HEALTHCARE", "SIDO": "HEALTHCARE",
    # Industrial
    "ASII": "INDUSTRIAL", "UNTR": "INDUSTRIAL", "AUTO": "INDUSTRIAL",
    "INTP": "INDUSTRIAL", "SMGR": "INDUSTRIAL",
    # Geothermal / Green Energy
    "PGEO": "GREEN_ENERGY", "BREN": "GREEN_ENERGY",
    # Chemical / Petrochemical
    "BRPT": "CHEMICAL", "TPIA": "CHEMICAL",
    # Plantation
    "AALI": "PLANTATION", "LSIP": "PLANTATION",
    # Technology
    "GOTO": "TECH", "BUKA": "TECH", "EMTK": "TECH",
}


# Dynamic sector cache — separate from the immutable hardcoded map.
# Can be cleared between runs or inspected independently.
_dynamic_sector_cache: dict[str, str] = {}


def get_sector(ticker: str) -> str:
    """Get sector for a ticker. Checks hardcoded map first, then dynamic cache,
    then Stockbit API as last resort before returning 'OTHER'.
    """
    clean = ticker.replace(".JK", "").upper()
    # 1. Hardcoded map (immutable, instant)
    mapped = IDX_SECTOR_MAP.get(clean)
    if mapped:
        return mapped
    # 2. Dynamic cache (previously resolved this process lifetime)
    cached = _dynamic_sector_cache.get(clean)
    if cached:
        return cached
    # 3. API lookup (only called once per ticker per process lifetime)
    dynamic = fetch_sector_from_stockbit(clean)
    _dynamic_sector_cache[clean] = dynamic
    return dynamic


def prefetch_sectors(tickers: list[str]) -> None:
    """Batch-resolve sectors for a list of tickers BEFORE scoring loop.

    Call this once at the start of hybrid screening to avoid synchronous
    HTTP calls inside the iterative sector_check loop. Tickers already in
    hardcoded map or dynamic cache are skipped (no network call).
    """
    import logging
    _logger = logging.getLogger(__name__)
    unmapped = [
        t.replace(".JK", "").upper() for t in tickers
        if t.replace(".JK", "").upper() not in IDX_SECTOR_MAP
        and t.replace(".JK", "").upper() not in _dynamic_sector_cache
    ]
    if not unmapped:
        return
    _logger.info("Prefetching sectors for %d unmapped tickers", len(unmapped))
    for clean in unmapped:
        result = fetch_sector_from_stockbit(clean)
        _dynamic_sector_cache[clean] = result
        if result == "OTHER":
            _logger.debug("Sector fetch for %s returned OTHER (API fail or truly unmapped)", clean)


def clear_sector_cache() -> None:
    """Clear the dynamic sector cache. Call between independent sessions if needed."""
    _dynamic_sector_cache.clear()


def fetch_sector_from_stockbit(ticker: str) -> str:
    """Dynamically fetch sector from Stockbit /emitten/info API.

    Returns sector string or 'OTHER' on failure. Logs a warning on failure
    so silent fallback is visible in logs.
    """
    try:
        from ..stockbit_collector import get_stockbit_token, _headers
        from urllib.request import Request, urlopen
        import json as _json
        import logging

        clean = ticker.replace(".JK", "").upper()
        token = get_stockbit_token()
        if not token:
            return "OTHER"

        url = f"https://exodus.stockbit.com/emitten/{clean}/info"
        headers = _headers(token)
        req = Request(url, headers=headers)
        raw = urlopen(req, timeout=10).read().decode("utf-8")
        data = _json.loads(raw)
        sector = data.get("data", {}).get("sector", "")
        if sector:
            return sector.upper().replace(" ", "_")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "SECTOR_FETCH_FALLBACK: Could not resolve sector for %s (%s) — using OTHER. "
            "Sector guard may be less effective for this ticker.",
            ticker, exc,
        )
    return "OTHER"


@dataclass
class SectorCorrelationGuard:
    """Portfolio diversification and correlation guard."""
    enabled: bool = True
    # Maximum tickers from same sector in shortlist
    max_same_sector: int = 2
    # Maximum pairwise correlation allowed between candidates
    max_correlation: float = 0.75
    # Minimum lookback for correlation calculation
    min_correlation_bars: int = 20
    # Portfolio beta limits
    max_portfolio_beta: float = 1.5
    min_portfolio_beta: float = 0.5

    def sector_check(self, tickers: list[str]) -> dict[str, Any]:
        """Check sector concentration.

        Returns dict with sector counts, violations, and recommended removals.
        Also caps 'OTHER' sector at max_same_sector * 2 to prevent unbounded
        concentration of unmapped tickers.
        """
        if not self.enabled:
            return {"violations": [], "sector_counts": {}}

        sector_counts: dict[str, list[str]] = {}
        for tkr in tickers:
            sector = get_sector(tkr)
            sector_counts.setdefault(sector, []).append(tkr)

        violations: list[dict[str, Any]] = []
        for sector, members in sector_counts.items():
            # "OTHER" gets a larger allowance but is still capped
            limit = self.max_same_sector * 2 if sector == "OTHER" else self.max_same_sector
            if len(members) > limit:
                violations.append({
                    "sector": sector,
                    "tickers": members,
                    "count": len(members),
                    "max_allowed": limit,
                    "remove_suggestion": members[limit:],
                })

        return {
            "sector_counts": {s: len(m) for s, m in sector_counts.items()},
            "sector_tickers": sector_counts,
            "violations": violations,
            "diversified": len(violations) == 0,
        }

    def correlation_check(
        self,
        tickers: list[str],
        histories: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        """Check pairwise correlation between candidates.

        Args:
            tickers: List of ticker symbols.
            histories: Dict mapping ticker → DataFrame with 'close' column.

        Returns:
            Dict with correlation matrix, violations, and average correlation.
        """
        if not self.enabled or len(tickers) < 2:
            return {"violations": [], "avg_correlation": 0.0}

        # Build returns matrix
        returns_data: dict[str, pd.Series] = {}
        for tkr in tickers:
            clean = tkr.replace(".JK", "")
            df = histories.get(tkr) or histories.get(f"{clean}.JK", pd.DataFrame())
            if df.empty or "close" not in df.columns:
                continue
            ret = df["close"].pct_change().dropna().tail(self.min_correlation_bars)
            if len(ret) >= self.min_correlation_bars:
                returns_data[clean] = ret

        if len(returns_data) < 2:
            return {"violations": [], "avg_correlation": 0.0, "note": "insufficient data"}

        # Align and compute correlation
        returns_df = pd.DataFrame(returns_data)
        corr_matrix = returns_df.corr()

        violations: list[dict[str, Any]] = []
        correlations: list[float] = []
        checked_pairs = set()

        for i, t1 in enumerate(corr_matrix.columns):
            for j, t2 in enumerate(corr_matrix.columns):
                if i >= j:
                    continue
                pair = (t1, t2)
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)
                corr_val = float(corr_matrix.loc[t1, t2])
                correlations.append(corr_val)
                if abs(corr_val) > self.max_correlation:
                    violations.append({
                        "pair": [t1, t2],
                        "correlation": round(corr_val, 3),
                        "action": "Consider removing one to improve diversification",
                    })

        return {
            "violations": violations,
            "avg_correlation": round(float(np.mean(correlations)), 3) if correlations else 0.0,
            "max_correlation": round(float(max(correlations)), 3) if correlations else 0.0,
            "pair_count": len(correlations),
            "diversified": len(violations) == 0,
        }

    def compute_portfolio_beta(
        self,
        tickers: list[str],
        histories: dict[str, pd.DataFrame],
        ihsg_history: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """Compute portfolio beta vs IHSG.

        Args:
            tickers: Selected tickers.
            histories: Per-ticker price DataFrames.
            ihsg_history: IHSG (^JKSE) price DataFrame.

        Returns:
            Dict with per-ticker beta and portfolio weighted beta.
        """
        if not self.enabled or ihsg_history is None or ihsg_history.empty:
            return {"portfolio_beta": None, "betas": {}}

        ihsg_ret = ihsg_history["close"].pct_change().dropna().tail(60)
        betas: dict[str, float] = {}

        for tkr in tickers:
            clean = tkr.replace(".JK", "")
            df = histories.get(tkr) or histories.get(f"{clean}.JK", pd.DataFrame())
            if df.empty or "close" not in df.columns:
                continue
            stock_ret = df["close"].pct_change().dropna().tail(60)
            # Align
            aligned = pd.DataFrame({"stock": stock_ret, "ihsg": ihsg_ret}).dropna()
            if len(aligned) < 20:
                continue
            cov = aligned["stock"].cov(aligned["ihsg"])
            var = aligned["ihsg"].var()
            if var > 0:
                betas[clean] = round(cov / var, 3)

        if not betas:
            return {"portfolio_beta": None, "betas": betas}

        # Equal-weight portfolio beta
        portfolio_beta = round(sum(betas.values()) / len(betas), 3)
        return {
            "portfolio_beta": portfolio_beta,
            "betas": betas,
            "within_limits": self.min_portfolio_beta <= portfolio_beta <= self.max_portfolio_beta,
            "assessment": (
                "HIGH_BETA" if portfolio_beta > self.max_portfolio_beta
                else "LOW_BETA" if portfolio_beta < self.min_portfolio_beta
                else "BALANCED"
            ),
        }

    def full_check(
        self,
        tickers: list[str],
        histories: dict[str, pd.DataFrame] | None = None,
        ihsg_history: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """Run all portfolio-level checks."""
        sector = self.sector_check(tickers)
        correlation = self.correlation_check(tickers, histories or {})
        beta = self.compute_portfolio_beta(tickers, histories or {}, ihsg_history)
        return {
            "sector": sector,
            "correlation": correlation,
            "beta": beta,
            "overall_diversified": sector["diversified"] and correlation.get("diversified", True),
        }
