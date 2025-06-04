"""
Portfolio definition with weights and sectors.
"""
from src.core.types import PortfolioWeight, PortfolioWeights


def get_default_portfolio() -> PortfolioWeights:
    """Get the default portfolio weights."""
    portfolio_dict = {
        # Core Technology & AI Infrastructure (39%)
        "MSFT": PortfolioWeight("MSFT", 0.13, "Technology"),
        "AAPL": PortfolioWeight("AAPL", 0.05, "Technology"),
        "AVGO": PortfolioWeight("AVGO", 0.09, "Technology"),
        "NVDA": PortfolioWeight("NVDA", 0.10, "Technology"),
        "PLTR": PortfolioWeight("PLTR", 0.03, "Technology"),
        
        # Manufacturing, EV & Advanced Processes (15%)
        "TSLA": PortfolioWeight("TSLA", 0.02, "Consumer Discretionary"),
        "TSM": PortfolioWeight("TSM", 0.05, "Technology"),
        "MRVL": PortfolioWeight("MRVL", 0.04, "Technology"),
        "ASML": PortfolioWeight("ASML", 0.02, "Technology"),
        "MU": PortfolioWeight("MU", 0.02, "Technology"),
        
        # Defense & Military (13%)
        "RNMBY": PortfolioWeight("RNMBY", 0.06, "Industrials"),
        "SAABY": PortfolioWeight("SAABY", 0.07, "Industrials"),
        
        # Defense ETF & Industrial Base (8%)
        "ITA": PortfolioWeight("ITA", 0.07, "ETF"),
        "ETN": PortfolioWeight("ETN", 0.01, "Industrials"),
        
        # Gold & Silver (12%)
        "GLD": PortfolioWeight("GLD", 0.10, "Commodities"),
        "SLV": PortfolioWeight("SLV", 0.02, "Commodities"),
        
        # AI Applications/Data & Enterprise Software (13%)
        "ORCL": PortfolioWeight("ORCL", 0.05, "Technology"),
        "VRT": PortfolioWeight("VRT", 0.02, "Technology"),
        "XLP": PortfolioWeight("XLP", 0.05, "ETF"),
    }
    
    portfolio = PortfolioWeights(portfolio_dict)
    
    # Validate weights sum to 1
    if not portfolio.validate():
        total = sum(w.weight for w in portfolio.values())
        raise ValueError(f"Portfolio weights must sum to 1.0, got {total}")
    
    return portfolio


def get_sector_allocations(portfolio: PortfolioWeights) -> dict:
    """Calculate sector allocations from portfolio."""
    sector_weights = {}
    
    for weight in portfolio.values():
        sector = weight.sector or "Other"
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight.weight
    
    return sector_weights 