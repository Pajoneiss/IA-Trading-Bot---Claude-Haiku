"""
Phase 3 - Market Intelligence
Regime detection + Anti-chop filters + TrendGuard

[Claude Trend Refactor] Data: 2024-12-11 - Adicionado TrendGuard
"""
from bot.phase3.market_regime import MarketRegimeAnalyzer
from bot.phase3.chop_filter import ChopFilter, detect_chop
from bot.phase3.trend_guard import TrendGuard, TrendGuardResult, check_trend_alignment

__all__ = [
    'MarketRegimeAnalyzer',
    'ChopFilter',
    'detect_chop',
    'TrendGuard',
    'TrendGuardResult',
    'check_trend_alignment'
]
