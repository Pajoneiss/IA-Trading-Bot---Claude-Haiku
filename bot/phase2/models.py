"""
Phase 2 - Models
Dataclasses para decisões de IA padronizadas
"""
from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime


@dataclass
class OpenDecision:
    """Decisão de ABRIR trade"""
    action: Literal["open"] = "open"
    symbol: str = ""
    side: Literal["long", "short"] = "long"
    style: Literal["scalp", "swing"] = "swing"
    source: str = ""  # "claude_swing" ou "openai_scalp"
    confidence: float = 0.0  # 0.0 a 1.0
    reason: str = ""
    strategy: str = ""
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    stop_loss_pct: float = 2.0
    risk_profile: Literal["AGGRESSIVE", "BALANCED", "CONSERVATIVE"] = "BALANCED"
    risk_amount_usd: float = 0.0
    capital_alloc_usd: float = 0.0
    
    # Campos opcionais para confluências
    confluences: list = field(default_factory=list)
    timeframe_analysis: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Converte para dict"""
        return {
            'action': self.action,
            'symbol': self.symbol,
            'side': self.side,
            'style': self.style,
            'source': self.source,
            'confidence': self.confidence,
            'reason': self.reason,
            'strategy': self.strategy,
            'stop_loss_price': self.stop_loss_price,
            'take_profit_price': self.take_profit_price,
            'stop_loss_pct': self.stop_loss_pct,
            'risk_profile': self.risk_profile,
            'risk_amount_usd': self.risk_amount_usd,
            'capital_alloc_usd': self.capital_alloc_usd,
            'confluences': self.confluences,
            'timeframe_analysis': self.timeframe_analysis
        }


@dataclass
class ManageDecision:
    """Decisão de GERENCIAR trade existente"""
    action: Literal["manage"] = "manage"
    symbol: str = ""
    style: Literal["scalp", "swing"] = "swing"
    source: str = ""
    manage_decision: dict = field(default_factory=dict)
    
    # Campos específicos de gestão
    close_pct: float = 0.0  # 0.0 a 1.0
    new_stop_price: Optional[float] = None
    new_take_profit_price: Optional[float] = None
    reason: str = ""
    r_multiple: Optional[float] = None  # Quantos R está
    
    def to_dict(self) -> dict:
        """Converte para dict"""
        return {
            'action': self.action,
            'symbol': self.symbol,
            'style': self.style,
            'source': self.source,
            'manage_decision': {
                'close_pct': self.close_pct,
                'new_stop_price': self.new_stop_price,
                'new_take_profit_price': self.new_take_profit_price,
                'reason': self.reason,
                'r_multiple': self.r_multiple
            }
        }


@dataclass
class SkipDecision:
    """Decisão de PULAR entrada"""
    action: Literal["skip"] = "skip"
    symbol: str = ""
    style: Literal["scalp", "swing"] = "swing"
    source: str = ""
    reason: str = ""
    
    def to_dict(self) -> dict:
        """Converte para dict"""
        return {
            'action': self.action,
            'symbol': self.symbol,
            'style': self.style,
            'source': self.source,
            'reason': self.reason
        }


@dataclass
class QualityGateResult:
    """Resultado da avaliação do Quality Gate"""
    approved: bool = False
    confidence_score: float = 0.0  # Score final após ajustes
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    adjustments: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Converte para dict"""
        return {
            'approved': self.approved,
            'confidence_score': self.confidence_score,
            'reasons': self.reasons,
            'warnings': self.warnings,
            'adjustments': self.adjustments
        }
