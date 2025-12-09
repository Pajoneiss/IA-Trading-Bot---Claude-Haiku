"""
Phase 8 - Paper Trading & Shadow Mode
"""
from bot.phase8.execution_config import ExecutionMode, SHADOW_CONFIGS
from bot.phase8.paper_portfolio import PaperPortfolio
from bot.phase8.execution_manager import ExecutionManager

__all__ = [
    'ExecutionMode',
    'SHADOW_CONFIGS',
    'PaperPortfolio',
    'ExecutionManager'
]
