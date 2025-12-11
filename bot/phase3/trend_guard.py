"""
Phase 3 - TrendGuard
[Claude Trend Refactor] Data: 2024-12-11 - Regra dura de alinhamento com tendência

Obriga operações a serem A FAVOR da tendência principal.
Bloqueia aberturas contra-tendência baseado no trend_bias.
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class TrendBias(Enum):
    """Direção da tendência principal"""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


@dataclass
class TrendGuardResult:
    """Resultado da avaliação do TrendGuard"""
    allowed: bool
    original_action: str
    original_side: str
    trend_bias: str
    regime: str
    reason: str
    warnings: List[str]


class TrendGuard:
    """
    TrendGuard - Surfista de Tendência
    
    Regras DURAS:
    - trend_bias == "long" → Bloqueia open_short, flip_short
    - trend_bias == "short" → Bloqueia open_long, flip_long
    - trend_bias == "neutral" → Opera seletivamente (thresholds mais altos)
    
    Sempre permite: hold, close, reduce, parciais
    """
    
    # Ações que podem ser bloqueadas
    BLOCKABLE_ACTIONS = ['open', 'open_long', 'open_short', 'flip', 'increase']
    
    # Confidence mínima em neutral para permitir entrada
    MIN_CONFIDENCE_NEUTRAL = 0.85
    
    # Modos e suas tolerâncias
    MODE_CONFIG = {
        "CONSERVADOR": {
            "allow_neutral_entries": False,  # Não opera em neutral
            "min_confidence_neutral": 0.80,  # Reduzido de 0.90
        },
        "BALANCEADO": {
            "allow_neutral_entries": True,
            "min_confidence_neutral": 0.72,  # Reduzido de 0.85
        },
        "AGRESSIVO": {
            "allow_neutral_entries": True,
            "min_confidence_neutral": 0.65,  # Reduzido de 0.78
        },
    }
    
    def __init__(self, mode_manager=None, logger_instance=None):
        """
        Inicializa TrendGuard
        
        Args:
            mode_manager: TradingModeManager para obter modo atual
            logger_instance: Logger opcional
        """
        self.mode_manager = mode_manager
        self.log = logger_instance or logger
        self.log.info("[TREND GUARD] 🛡️ Inicializado - Protegendo contra trades contra-tendência")
    
    def get_current_mode(self) -> str:
        """Retorna modo atual"""
        if self.mode_manager:
            return self.mode_manager.current_mode.value
        return "BALANCEADO"
    
    def evaluate(self, 
                 decision: Dict[str, Any],
                 regime_info: Dict[str, Any],
                 confidence: float = 0.0) -> TrendGuardResult:
        """
        Avalia se a decisão está alinhada com a tendência.
        
        Args:
            decision: Decisão da IA (action, side, symbol, etc)
            regime_info: Info do regime (regime, trend_bias, etc)
            confidence: Confiança da decisão
            
        Returns:
            TrendGuardResult com allowed=True/False e razões
        """
        action = decision.get('action', 'hold').lower()
        side = decision.get('side', '').lower()
        symbol = decision.get('symbol', 'UNKNOWN')
        
        # Normaliza side
        if side == 'buy':
            side = 'long'
        elif side == 'sell':
            side = 'short'
        
        # Normaliza action (open_long -> open + long)
        if action == 'open_long':
            action = 'open'
            side = 'long'
        elif action == 'open_short':
            action = 'open'
            side = 'short'
        
        # Extrai trend_bias e regime
        trend_bias = regime_info.get('trend_bias', 'neutral').lower()
        regime = regime_info.get('regime', 'RANGE_CHOP')
        
        # Resultado base
        result = TrendGuardResult(
            allowed=True,
            original_action=action,
            original_side=side,
            trend_bias=trend_bias,
            regime=regime,
            reason="",
            warnings=[]
        )
        
        # Ações que sempre passam
        if action in ['hold', 'close', 'reduce', 'partial_close', 'skip']:
            result.reason = f"Ação '{action}' sempre permitida"
            return result
        
        # Se não é ação bloqueável, passa
        if action not in self.BLOCKABLE_ACTIONS:
            result.reason = f"Ação '{action}' não bloqueável"
            return result
        
        # Agora avalia alinhamento
        mode = self.get_current_mode()
        mode_config = self.MODE_CONFIG.get(mode, self.MODE_CONFIG["BALANCEADO"])
        
        # === REGRA 1: TREND_BIAS LONG ===
        if trend_bias == 'long':
            if side == 'short':
                result.allowed = False
                result.reason = f"❌ BLOQUEADO: {action.upper()} {side.upper()} contra tendência LONG"
                self.log.warning(
                    f"[TREND GUARD] 🚫 {symbol}: {action} {side} BLOQUEADO | "
                    f"trend_bias={trend_bias} | regime={regime}"
                )
                return result
            
            # Long alinhado
            result.reason = f"✅ Alinhado: {action} {side} com tendência LONG"
            return result
        
        # === REGRA 2: TREND_BIAS SHORT ===
        elif trend_bias == 'short':
            if side == 'long':
                result.allowed = False
                result.reason = f"❌ BLOQUEADO: {action.upper()} {side.upper()} contra tendência SHORT"
                self.log.warning(
                    f"[TREND GUARD] 🚫 {symbol}: {action} {side} BLOQUEADO | "
                    f"trend_bias={trend_bias} | regime={regime}"
                )
                return result
            
            # Short alinhado
            result.reason = f"✅ Alinhado: {action} {side} com tendência SHORT"
            return result
        
        # === REGRA 3: NEUTRAL / RANGE ===
        else:
            # Em neutral, depende do modo
            if not mode_config["allow_neutral_entries"]:
                result.allowed = False
                result.reason = f"❌ BLOQUEADO: Modo {mode} não permite entradas em NEUTRAL"
                self.log.warning(
                    f"[TREND GUARD] 🚫 {symbol}: {action} {side} BLOQUEADO em NEUTRAL | "
                    f"mode={mode}"
                )
                return result
            
            # Permite mas exige confidence alta
            min_conf = mode_config["min_confidence_neutral"]
            if confidence < min_conf:
                result.allowed = False
                result.reason = f"❌ BLOQUEADO: Confidence {confidence:.2f} < {min_conf:.2f} em NEUTRAL"
                self.log.warning(
                    f"[TREND GUARD] 🚫 {symbol}: {action} {side} BLOQUEADO | "
                    f"confidence={confidence:.2f} insuficiente para NEUTRAL (min={min_conf:.2f})"
                )
                return result
            
            # Permite com warning
            result.warnings.append(f"⚠️ Operando em regime NEUTRAL - gestão defensiva recomendada")
            result.reason = f"✅ Permitido em NEUTRAL com confidence alta ({confidence:.2f} >= {min_conf:.2f})"
            self.log.info(
                f"[TREND GUARD] ⚠️ {symbol}: {action} {side} PERMITIDO em NEUTRAL | "
                f"confidence={confidence:.2f} | mode={mode}"
            )
            return result
    
    def check_increase_alignment(self,
                                  current_side: str,
                                  regime_info: Dict[str, Any],
                                  current_pnl_pct: float = 0.0) -> Tuple[bool, str]:
        """
        Verifica se pode aumentar posição (pyramiding).
        
        Regras:
        - Só aumenta SE trend_bias continua alinhado
        - Posição deve estar em lucro
        - Regime deve ser de tendência (não range)
        
        Args:
            current_side: 'long' ou 'short'
            regime_info: Info do regime atual
            current_pnl_pct: PnL atual da posição em %
            
        Returns:
            (allowed, reason)
        """
        trend_bias = regime_info.get('trend_bias', 'neutral')
        regime = regime_info.get('regime', 'RANGE_CHOP')
        
        # Bloqueia aumentos em range
        if regime in ['RANGE_CHOP', 'LOW_VOL_DRIFT', 'PANIC_HIGH_VOL']:
            return False, f"Pyramiding bloqueado em regime {regime}"
        
        # Verifica alinhamento
        if current_side == 'long' and trend_bias != 'long':
            return False, f"Pyramiding LONG bloqueado: trend_bias={trend_bias}"
        
        if current_side == 'short' and trend_bias != 'short':
            return False, f"Pyramiding SHORT bloqueado: trend_bias={trend_bias}"
        
        # Verifica lucro mínimo para pyramid
        min_pnl_for_pyramid = 0.5  # 0.5% mínimo
        if current_pnl_pct < min_pnl_for_pyramid:
            return False, f"Pyramiding bloqueado: PnL {current_pnl_pct:.2f}% < {min_pnl_for_pyramid}%"
        
        return True, f"Pyramiding permitido: {current_side} alinhado com {trend_bias}, PnL={current_pnl_pct:.2f}%"
    
    def log_evaluation(self, result: TrendGuardResult, symbol: str):
        """Loga resultado da avaliação de forma detalhada"""
        status = "✅ PERMITIDO" if result.allowed else "🚫 BLOQUEADO"
        
        self.log.info(
            f"[TREND GUARD] {status} {symbol}: "
            f"action={result.original_action}, side={result.original_side}, "
            f"trend_bias={result.trend_bias}, regime={result.regime}"
        )
        self.log.info(f"[TREND GUARD] Razão: {result.reason}")
        
        for warning in result.warnings:
            self.log.warning(f"[TREND GUARD] {warning}")


# Função standalone para uso rápido
def check_trend_alignment(action: str, 
                          side: str, 
                          trend_bias: str,
                          confidence: float = 0.0,
                          mode: str = "BALANCEADO") -> Tuple[bool, str]:
    """
    Verificação rápida de alinhamento sem instanciar a classe.
    
    Args:
        action: 'open', 'increase', etc
        side: 'long' ou 'short'
        trend_bias: 'long', 'short' ou 'neutral'
        confidence: Confiança da decisão
        mode: Modo de trading
        
    Returns:
        (allowed, reason)
    """
    # Ações sempre permitidas
    if action in ['hold', 'close', 'reduce', 'skip']:
        return True, "Ação sempre permitida"
    
    # trend_bias long -> só long
    if trend_bias == 'long' and side == 'short':
        return False, f"Short bloqueado em tendência LONG"
    
    # trend_bias short -> só short
    if trend_bias == 'short' and side == 'long':
        return False, f"Long bloqueado em tendência SHORT"
    
    # neutral -> depende
    if trend_bias == 'neutral':
        min_conf = TrendGuard.MODE_CONFIG.get(mode, {}).get("min_confidence_neutral", 0.85)
        if confidence < min_conf:
            return False, f"Confidence {confidence:.2f} insuficiente para NEUTRAL (min={min_conf:.2f})"
    
    return True, "Alinhado com tendência"
