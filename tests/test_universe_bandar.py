import pandas as pd
from pathlib import Path
from interday_liquidity_screener.ticker_universe import load_universe_tickers

def test_load_universe_tickers_bandar(tmp_path, monkeypatch):
    csv_path = Path("data/output/bandar_scan_results.csv")
    mock_df = pd.DataFrame([{"ticker": "MAPI.JK"}, {"ticker": "BBRI.JK"}])
    
    monkeypatch.setattr("pandas.read_csv", lambda *args, **kwargs: mock_df)
    
    original_exists = Path.exists
    def mock_exists(self):
        if self == csv_path:
            return True
        return original_exists(self)
    monkeypatch.setattr(Path, "exists", mock_exists)
    
    tickers = load_universe_tickers("bandar")
    assert tickers == ["MAPI.JK", "BBRI.JK"]
