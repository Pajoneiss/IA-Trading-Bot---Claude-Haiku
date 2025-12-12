"""
Turbo Mode - Modo Simplificado e Agressivo
==========================================
Menos filtros, mais execução, mais lucro.

Filosofia:
- Detecta tendência (EMA simples)
- Entra rápido quando alinhado
- Pyramiding agressivo
- Trailing stop para proteger

Autor: Claude (Trend Refactor v3)
Data: 2024-12-11
"""

import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class TurboTrend(Enum):
    """Tendência simplificada"""
    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


@dataclass
class TurboDecision:
    """Decisão simplificada do Turbo Mode"""
    action: str  # open, close, add, hold
    side: str  # long, short
    confidence: float
    reason: str
    size_multiplier: float = 1.0  # Para pyramiding


class TurboMode:
    """
    Modo simplificado que bypassa a complexidade.
    
    Regras simples:
    1. EMA50 > EMA200 = BULL → só long
    2. EMA50 < EMA200 = BEAR → só short
    3. Momentum forte = entra
    4. Posição em lucro = adiciona
    5. Trailing por EMA21
    """
    
    def __init__(self, config: Optional[Dict] = None, logger_instance=None):
        self.logger = logger_instance or logger
        self.config = config or {}
        
        # Parâmetros simplificados
        self.min_confidence = self.config.get('min_confidence', 0.60)
        self.pyramid_threshold = self.config.get('pyramid_threshold', 0.5)  # 0.5% lucro para add
        self.max_pyramids = self.config.get('max_pyramids', 3)
        self.trailing_ema = 21
        
        self.logger.info("[TURBO] 🚀 Modo Turbo ativado!")
    
    def detect_trend(self, candles: list, symbol: str = "") -> Tuple[TurboTrend, float]:
        """
        Detecta tendência de forma SIMPLES.
        
        Usa apenas:
        - EMA50 vs EMA200
        - Posição do preço
        
        Returns:
            (trend, strength)
        """
        if not candles or len(candles) < 200:
            return TurboTrend.NEUTRAL, 0.0
        
        closes = [self._get_close(c) for c in candles]
        if not closes or len(closes) < 200:
            return TurboTrend.NEUTRAL, 0.0
        
        # Calcula EMAs
        ema50 = self._ema(closes, 50)
        ema200 = self._ema(closes, 200)
        current_price = closes[-1]
        
        if ema50 is None or ema200 is None:
            return TurboTrend.NEUTRAL, 0.0
        
        # Lógica simples
        if ema50 > ema200 and current_price > ema50:
            # BULL forte
            strength = (current_price - ema200) / ema200 * 100  # % acima da EMA200
            strength = min(strength, 5.0) / 5.0  # Normaliza 0-1
            self.logger.debug(f"[TURBO] {symbol} BULL strength={strength:.2f}")
            return TurboTrend.BULL, strength
            
        elif ema50 < ema200 and current_price < ema50:
            # BEAR forte
            strength = (ema200 - current_price) / ema200 * 100
            strength = min(strength, 5.0) / 5.0
            self.logger.debug(f"[TURBO] {symbol} BEAR strength={strength:.2f}")
            return TurboTrend.BEAR, strength
        
        return TurboTrend.NEUTRAL, 0.0
    
    def _get_close(self, candle) -> Optional[float]:
        """Extrai close do candle (vários formatos)"""
        if isinstance(candle, dict):
            for key in ['close', 'c', 'Close']:
                if key in candle:
                    return float(candle[key])
        elif isinstance(candle, (list, tuple)) and len(candle) >= 4:
            return float(candle[4])  # OHLCV
        return None
    
    def _ema(self, values: list, period: int) -> Optional[float]:
        """Calcula EMA simples"""
        if len(values) < period:
            return None
        
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period  # SMA inicial
        
        for price in values[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def should_enter(
        self,
        symbol: str,
        candles: list,
        ai_decision: Dict[str, Any],
        current_position: Optional[Dict] = None
    ) -> TurboDecision:
        """
        Decide se deve entrar no trade.
        
        Lógica:
        1. Detecta tendência
        2. Verifica se AI concorda
        3. Se alinhado → ENTRA
        """
        # Detecta tendência
        trend, strength = self.detect_trend(candles, symbol)
        
        # Extrai decisão da AI
        ai_action = ai_decision.get('action', 'hold')
        ai_side = ai_decision.get('side', ai_decision.get('direction', ''))
        ai_confidence = float(ai_decision.get('confidence', 0))
        
        # Normaliza side
        if ai_action in ['open_long', 'buy']:
            ai_side = 'long'
        elif ai_action in ['open_short', 'sell']:
            ai_side = 'short'
        
        # Se já tem posição, verifica pyramiding
        if current_position:
            return self._check_pyramid(symbol, current_position, trend, strength, ai_confidence)
        
        # Sem posição → verifica entrada
        if trend == TurboTrend.NEUTRAL:
            return TurboDecision(
                action='hold',
                side='',
                confidence=0,
                reason="Tendência neutra - aguardando"
            )
        
        # Mapeia tendência para side esperado
        expected_side = 'long' if trend == TurboTrend.BULL else 'short'
        
        # Verifica alinhamento
        if ai_side == expected_side and ai_confidence >= self.min_confidence:
            # ALINHADO → ENTRA!
            self.logger.info(
                f"[TURBO] ✅ {symbol} ENTRADA {expected_side.upper()} "
                f"| trend={trend.value} strength={strength:.2f} conf={ai_confidence:.2f}"
            )
            return TurboDecision(
                action='open',
                side=expected_side,
                confidence=ai_confidence + (strength * 0.1),  # Boost por força da tendência
                reason=f"Turbo: {trend.value} forte, AI alinhada"
            )
        
        # AI quer ir contra → BLOQUEIA
        if ai_side and ai_side != expected_side:
            self.logger.info(
                f"[TURBO] 🚫 {symbol} AI quer {ai_side} mas tendência é {trend.value}"
            )
            return TurboDecision(
                action='hold',
                side='',
                confidence=0,
                reason=f"Bloqueado: AI {ai_side} contra tendência {trend.value}"
            )
        
        # Confidence baixa
        return TurboDecision(
            action='hold',
            side='',
            confidence=ai_confidence,
            reason=f"Confidence {ai_confidence:.2f} < mínimo {self.min_confidence}"
        )
    
    def _check_pyramid(
        self,
        symbol: str,
        position: Dict,
        trend: TurboTrend,
        strength: float,
        ai_confidence: float
    ) -> TurboDecision:
        """Verifica se deve fazer pyramiding"""
        pos_side = position.get('side', 'long')
        pnl_pct = float(position.get('pnl_pct', position.get('unrealized_pnl_pct', 0)))
        pyramid_count = int(position.get('pyramid_adds', position.get('adds', 0)))
        
        # Verifica alinhamento
        expected_side = 'long' if trend == TurboTrend.BULL else 'short'
        
        if pos_side != expected_side:
            # Posição contra tendência → não adiciona
            return TurboDecision(
                action='hold',
                side=pos_side,
                confidence=0,
                reason=f"Posição {pos_side} contra tendência {trend.value}"
            )
        
        # Verifica condições de pyramid
        if (
            pnl_pct >= self.pyramid_threshold and
            pyramid_count < self.max_pyramids and
            strength > 0.3 and
            ai_confidence >= self.min_confidence
        ):
            # PYRAMID!
            size_mult = 0.5 if pyramid_count == 0 else 0.3  # Primeiro add maior
            
            self.logger.info(
                f"[TURBO] 📈 {symbol} PYRAMID #{pyramid_count+1} "
                f"| PnL={pnl_pct:+.2f}% strength={strength:.2f}"
            )
            return TurboDecision(
                action='add',
                side=pos_side,
                confidence=ai_confidence,
                reason=f"Pyramid: PnL={pnl_pct:+.2f}%, tendência forte",
                size_multiplier=size_mult
            )
        
        return TurboDecision(
            action='hold',
            side=pos_side,
            confidence=ai_confidence,
            reason="Aguardando condições de pyramid"
        )
    
    def get_trailing_stop(
        self,
        symbol: str,
        candles: list,
        position: Dict,
        current_price: float
    ) -> Optional[float]:
        """
        Calcula trailing stop simples baseado em EMA21.
        
        Returns:
            Novo stop price ou None se não deve mover
        """
        if not candles or len(candles) < 25:
            return None
        
        closes = [self._get_close(c) for c in candles]
        ema21 = self._ema(closes, 21)
        
        if ema21 is None:
            return None
        
        pos_side = position.get('side', 'long')
        current_stop = float(position.get('stop_loss', position.get('stop_price', 0)))
        entry_price = float(position.get('entry_price', current_price))
        
        # Offset de 0.3% da EMA para dar espaço
        offset = ema21 * 0.003
        
        if pos_side == 'long':
            # Stop abaixo da EMA21
            new_stop = ema21 - offset
            
            # Só move se for melhor que atual E acima do entry (protege lucro)
            if new_stop > current_stop and new_stop > entry_price:
                self.logger.info(
                    f"[TURBO] 🛡️ {symbol} Trailing: ${current_stop:.2f} → ${new_stop:.2f}"
                )
                return new_stop
        else:
            # Short: stop acima da EMA21
            new_stop = ema21 + offset
            
            if new_stop < current_stop and new_stop < entry_price:
                self.logger.info(
                    f"[TURBO] 🛡️ {symbol} Trailing: ${current_stop:.2f} → ${new_stop:.2f}"
                )
                return new_stop
        
        return None
    
    def evaluate_quick(
        self,
        symbol: str,
        candles: list,
        side: str,
        confidence: float,
        execution_mode: str = "LIVE",
        core_setup: bool = False
    ) -> Tuple[bool, str, float]:
        """
        Avaliação rápida: deve tomar o trade?
        
        [PAPER MODE] Em PAPER_ONLY, é mais permissivo:
        - Tendência neutra → SOFT_REDUCE (risk_mult=0.5) ao invés de BLOCK
        - Core setup válido tem prioridade
        
        Substitui QualityGate, TrendGuard, ChopFilter, etc.
        TUDO EM UMA FUNÇÃO.
        
        Returns:
            (should_trade, reason, risk_multiplier)
        """
        # 1. Detecta tendência
        trend, strength = self.detect_trend(candles, symbol)
        
        is_paper = execution_mode in ["PAPER_ONLY", "PAPER", "SHADOW"]
        
        # 2. Tendência neutra
        if trend == TurboTrend.NEUTRAL:
            # [PAPER MODE] Se PAPER + core_setup válido → permite com risco reduzido
            if is_paper and core_setup:
                self.logger.info(
                    f"[TURBO] ⚠️ {symbol} tendência neutra → risk_mult=0.5 (PAPER + CORE_SETUP)"
                )
                return True, "PAPER: tendência neutra mas CORE setup válido", 0.5
            
            # [PAPER MODE] Mesmo sem core_setup, se confidence alta → permite
            if is_paper and confidence >= 0.75:
                self.logger.info(
                    f"[TURBO] ⚠️ {symbol} tendência neutra → risk_mult=0.5 (PAPER + high conf)"
                )
                return True, "PAPER: tendência neutra mas confidence alta", 0.5
            
            # LIVE ou PAPER sem setup → bloqueia
            return False, "Tendência neutra", 0.0
        
        # 3. Verifica alinhamento
        expected = 'long' if trend == TurboTrend.BULL else 'short'
        if side != expected:
            # [PAPER MODE] Permite contra-tendência com risco muito reduzido
            if is_paper and core_setup and confidence >= 0.80:
                self.logger.info(
                    f"[TURBO] ⚠️ {symbol} contra tendência → risk_mult=0.25 (PAPER experimental)"
                )
                return True, f"PAPER: contra tendência (experimental)", 0.25
            
            return False, f"Contra tendência: quer {side}, tendência é {trend.value}", 0.0
        
        # 4. Confidence mínima (ajustada por força)
        min_conf = self.min_confidence - (strength * 0.1)  # Mais forte = menos exigente
        min_conf = max(min_conf, 0.50)  # Piso de 50%
        
        # [PAPER MODE] Threshold mais baixo
        if is_paper:
            min_conf = min(min_conf, 0.60)
        
        if confidence < min_conf:
            return False, f"Confidence {confidence:.2f} < {min_conf:.2f}", 0.0
        
        # PASSOU!
        # Tendência forte = risco normal, moderada = reduzido
        risk_mult = 1.0 if strength >= 0.5 else 0.75
        
        return True, f"Aprovado: {trend.value} strength={strength:.2f}", risk_mult


# Instância global
_turbo_mode: Optional[TurboMode] = None

def get_turbo_mode(config: Optional[Dict] = None, logger_instance=None) -> TurboMode:
    """Retorna instância singleton do Turbo Mode"""
    global _turbo_mode
    if _turbo_mode is None:
        _turbo_mode = TurboMode(config, logger_instance)
    return _turbo_mode
