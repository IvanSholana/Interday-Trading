"""Adjusted Price Handler.

Implements AdjustedPriceHandler for dual-price logic. Prepares DataFrames
with both adjusted_close (for indicator calculations like MA, RSI, ATR) and
close_raw (for IDX tick-size validation in trade plans). Detects corporate
actions (splits/dividends) and provides fallback when adjusted close is
unavailable.
"""
