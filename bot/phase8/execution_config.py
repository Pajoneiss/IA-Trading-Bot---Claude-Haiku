"""
Phase 8 - Execution Configuration
Modos: LIVE, PAPER_ONLY, SHADOW
"""
from enum import Enum


class ExecutionMode(Enum):
    """Modos de execução"""
    LIVE = "LIVE"              # Ordens reais
    PAPER_ONLY = "PAPER_ONLY"  # Apenas simulação
    SHADOW = "SHADOW"          # Real + Shadow experiments


# Shadow Experiments Configuration
SHADOW_CONFIGS = {
    "aggressive_swing": {
        "enabled": True,
        "style": "SWING",
        "symbols": ["BTCUSDC", "ETHUSDC"],
        "risk_multiplier": 1.5,
        "take_profit_multiplier": 1.2,
        "stop_loss_multiplier": 1.1,
        "notes": "Testar swing mais agressivo em BTC/ETH"
    },
    "conservative_scalp": {
        "enabled": True,
        "style": "SCALP",
        "symbols": ["APTUSDC", "SUIUSDC", "NEARUSDC"],
        "risk_multiplier": 0.7,
        "take_profit_multiplier": 0.8,
        "stop_loss_multiplier": 0.9,
        "notes": "Scalp conservador em altcoins"
    }
}


def get_active_shadow_configs():
    """Retorna shadow configs ativos"""
    return {k: v for k, v in SHADOW_CONFIGS.items() if v.get("enabled", False)}
