"""
Core Strategy - Trend Follower Multi-Timeframe
===============================================
Estratégia determinística CORE que pode ser backtestada.

HIERARQUIA DE TIMEFRAMES:
- 1D: Filtro macro ("clima" do mercado)
- 4H: Timeframe operacional principal (chefe da tendência)
- 1H: Confirmação secundária
- 15M: Gatilho de entrada e gestão

INDICADORES CORE:
- EMA 9/26 (já existe no EMA Cross Analyzer)
- ADX (força da tendência)
- MACD/Histograma (momentum)

Autor: Claude (Core Strategy Refactor)
Data: 2024-12-11
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from bot.indicators import TechnicalIndicators


class TrendBias(Enum):
    """Viés de tendência"""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class TrendStrength(Enum):
    """Força da tendência"""
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


@dataclass
class TimeframeAnalysis:
    """Análise de um timeframe específico"""
    timeframe: str
    trend_bias: TrendBias
    trend_strength: TrendStrength
    
    # EMAs
    ema9: float = 0.0
    ema26: float = 0.0
    ema_cross: str = "none"  # "bull_cross", "bear_cross", "none"
    bars_since_cross: int = 0
    
    # ADX
    adx: float = 0.0
    plus_di: float = 0.0
    minus_di: float = 0.0
    
    # MACD
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    
    # Preço
    current_price: float = 0.0
    price_vs_ema26_pct: float = 0.0  # % do preço em relação à EMA26


@dataclass
class SymbolAnalysis:
    """Análise completa de um símbolo"""
    symbol: str
    timestamp: str
    
    # Análises por timeframe
    daily: Optional[TimeframeAnalysis] = None
    h4: Optional[TimeframeAnalysis] = None
    h1: Optional[TimeframeAnalysis] = None
    m15: Optional[TimeframeAnalysis] = None
    
    # Trend bias consolidado (vem do 4H)
    trend_bias: TrendBias = TrendBias.NEUTRAL
    
    # Modificadores
    daily_climate: str = "neutral"  # "strong_bull", "strong_bear", "neutral"
    h1_confirmation: str = "aligned"  # "aligned", "divergent", "neutral"
    
    # Setup válido?
    has_valid_setup: bool = False
    setup_type: str = "none"  # "entry_long", "entry_short", "add", "partial", "none"
    setup_reason: str = ""
    
    # Ajustes de agressividade
    size_multiplier: float = 1.0
    confidence_adjustment: float = 0.0


@dataclass
class CoreConfig:
    """Configuração da estratégia CORE"""
    # ADX thresholds
    adx_strong: float = 25.0
    adx_moderate: float = 20.0
    adx_weak: float = 15.0
    
    # MACD histogram thresholds
    macd_strong_threshold: float = 0.0  # > 0 = bullish momentum
    
    # EMA cross freshness (barras)
    fresh_cross_1d: int = 3
    fresh_cross_4h: int = 5
    fresh_cross_1h: int = 8
    fresh_cross_15m: int = 12
    
    # Overextension (% do preço vs EMA26)
    max_overextension_1d: float = 8.0
    max_overextension_4h: float = 5.0
    max_overextension_1h: float = 4.0
    max_overextension_15m: float = 3.0
    
    # Size multipliers por clima
    size_mult_aligned: float = 1.0
    size_mult_divergent: float = 0.5
    size_mult_neutral: float = 0.3


class CoreStrategy:
    """
    Estratégia CORE - Trend Follower Multi-Timeframe
    
    Lógica determinística que pode ser:
    1. Executada sem IA
    2. Backtestada
    3. Usada como filtro antes de chamar IA
    """
    
    def __init__(self, config: Optional[CoreConfig] = None, logger_instance=None):
        self.config = config or CoreConfig()
        self.logger = logger_instance or logging.getLogger(__name__)
        self.indicators = TechnicalIndicators()
    
    def analyze_timeframe(
        self,
        candles: List[Dict],
        timeframe: str
    ) -> Optional[TimeframeAnalysis]:
        """
        Analisa um timeframe específico.
        
        Args:
            candles: Lista de candles OHLCV
            timeframe: "1d", "4h", "1h", "15m"
            
        Returns:
            TimeframeAnalysis ou None se dados insuficientes
        """
        if not candles or len(candles) < 50:
            return None
        
        # Extrai preços
        closes = self._extract_closes(candles)
        highs = self._extract_highs(candles)
        lows = self._extract_lows(candles)
        
        if len(closes) < 30:
            return None
        
        current_price = closes[-1]
        
        # EMAs
        ema9 = self.indicators.calculate_ema(closes, 9)
        ema26 = self.indicators.calculate_ema(closes, 26)
        
        if ema9 is None or ema26 is None:
            return None
        
        # ADX
        adx_result = self.indicators.calculate_adx(highs, lows, closes, 14)
        adx = adx_result['adx'] if adx_result else 0
        plus_di = adx_result['plus_di'] if adx_result else 0
        minus_di = adx_result['minus_di'] if adx_result else 0
        
        # MACD
        macd_result = self.indicators.calculate_macd(closes, 12, 26, 9)
        macd_line = macd_result['macd_line'] if macd_result else 0
        macd_signal = macd_result['signal_line'] if macd_result else 0
        macd_histogram = macd_result['histogram'] if macd_result else 0
        
        # Detecta cross
        ema_cross, bars_since = self._detect_ema_cross(closes, 9, 26)
        
        # Calcula trend bias e strength
        trend_bias, trend_strength = self._determine_trend(
            ema9, ema26, adx, macd_histogram, plus_di, minus_di
        )
        
        # % do preço vs EMA26
        price_vs_ema26_pct = ((current_price - ema26) / ema26) * 100
        
        return TimeframeAnalysis(
            timeframe=timeframe,
            trend_bias=trend_bias,
            trend_strength=trend_strength,
            ema9=ema9,
            ema26=ema26,
            ema_cross=ema_cross,
            bars_since_cross=bars_since,
            adx=adx,
            plus_di=plus_di,
            minus_di=minus_di,
            macd_line=macd_line,
            macd_signal=macd_signal,
            macd_histogram=macd_histogram,
            current_price=current_price,
            price_vs_ema26_pct=price_vs_ema26_pct
        )
    
    def analyze_symbol(
        self,
        symbol: str,
        candles_1d: List[Dict],
        candles_4h: List[Dict],
        candles_1h: List[Dict],
        candles_15m: List[Dict]
    ) -> SymbolAnalysis:
        """
        Análise completa de um símbolo em todos os timeframes.
        
        Returns:
            SymbolAnalysis com trend_bias e setup detection
        """
        from datetime import datetime
        
        analysis = SymbolAnalysis(
            symbol=symbol,
            timestamp=datetime.now().isoformat()
        )
        
        # Analisa cada timeframe
        analysis.daily = self.analyze_timeframe(candles_1d, "1d")
        analysis.h4 = self.analyze_timeframe(candles_4h, "4h")
        analysis.h1 = self.analyze_timeframe(candles_1h, "1h")
        analysis.m15 = self.analyze_timeframe(candles_15m, "15m")
        
        # Trend bias vem do 4H (chefe da tendência)
        if analysis.h4:
            analysis.trend_bias = analysis.h4.trend_bias
        
        # Determina clima do 1D
        analysis.daily_climate = self._get_daily_climate(analysis.daily)
        
        # Confirmação do 1H
        analysis.h1_confirmation = self._get_h1_confirmation(
            analysis.h4, analysis.h1
        )
        
        # Detecta setup válido
        analysis.has_valid_setup, analysis.setup_type, analysis.setup_reason = \
            self._detect_setup(analysis)
        
        # Calcula ajustes de agressividade
        analysis.size_multiplier, analysis.confidence_adjustment = \
            self._calculate_adjustments(analysis)
        
        # Log
        self.logger.info(
            f"[CORE] {symbol}: trend_bias={analysis.trend_bias.value}, "
            f"climate={analysis.daily_climate}, h1_conf={analysis.h1_confirmation}, "
            f"setup={analysis.has_valid_setup} ({analysis.setup_type})"
        )
        
        return analysis
    
    def _determine_trend(
        self,
        ema9: float,
        ema26: float,
        adx: float,
        macd_histogram: float,
        plus_di: float,
        minus_di: float
    ) -> Tuple[TrendBias, TrendStrength]:
        """
        Determina trend bias e strength baseado nos indicadores.
        
        Regras:
        - BULL: EMA9 > EMA26 AND ADX >= threshold AND MACD hist >= 0
        - BEAR: EMA9 < EMA26 AND ADX >= threshold AND MACD hist <= 0
        - NEUTRAL: caso contrário
        """
        # EMA cross direction
        ema_bullish = ema9 > ema26
        ema_bearish = ema9 < ema26
        
        # ADX strength
        if adx >= self.config.adx_strong:
            strength = TrendStrength.STRONG
        elif adx >= self.config.adx_moderate:
            strength = TrendStrength.MODERATE
        elif adx >= self.config.adx_weak:
            strength = TrendStrength.WEAK
        else:
            strength = TrendStrength.NONE
        
        # MACD momentum
        macd_bullish = macd_histogram >= 0
        macd_bearish = macd_histogram <= 0
        
        # DI confirmation
        di_bullish = plus_di > minus_di
        di_bearish = minus_di > plus_di
        
        # Determina bias
        if ema_bullish and (adx >= self.config.adx_weak) and macd_bullish:
            return TrendBias.LONG, strength
        elif ema_bearish and (adx >= self.config.adx_weak) and macd_bearish:
            return TrendBias.SHORT, strength
        else:
            return TrendBias.NEUTRAL, TrendStrength.NONE
    
    def _detect_ema_cross(
        self,
        closes: List[float],
        fast_period: int,
        slow_period: int
    ) -> Tuple[str, int]:
        """
        Detecta cruzamento de EMAs e há quantas barras ocorreu.
        
        Returns:
            (cross_type, bars_since_cross)
        """
        if len(closes) < slow_period + 10:
            return "none", 0
        
        # Calcula EMAs para as últimas N barras
        for i in range(1, min(50, len(closes) - slow_period)):
            idx = len(closes) - i
            prev_idx = idx - 1
            
            ema_fast_curr = self.indicators.calculate_ema(closes[:idx+1], fast_period)
            ema_slow_curr = self.indicators.calculate_ema(closes[:idx+1], slow_period)
            ema_fast_prev = self.indicators.calculate_ema(closes[:prev_idx+1], fast_period)
            ema_slow_prev = self.indicators.calculate_ema(closes[:prev_idx+1], slow_period)
            
            if None in [ema_fast_curr, ema_slow_curr, ema_fast_prev, ema_slow_prev]:
                continue
            
            # Bull cross: fast cruza de baixo para cima
            if ema_fast_prev <= ema_slow_prev and ema_fast_curr > ema_slow_curr:
                return "bull_cross", i
            
            # Bear cross: fast cruza de cima para baixo
            if ema_fast_prev >= ema_slow_prev and ema_fast_curr < ema_slow_curr:
                return "bear_cross", i
        
        return "none", 0
    
    def _get_daily_climate(self, daily: Optional[TimeframeAnalysis]) -> str:
        """Determina clima do mercado baseado no 1D"""
        if not daily:
            return "neutral"
        
        if daily.trend_bias == TrendBias.LONG and daily.trend_strength in [TrendStrength.STRONG, TrendStrength.MODERATE]:
            return "strong_bull"
        elif daily.trend_bias == TrendBias.SHORT and daily.trend_strength in [TrendStrength.STRONG, TrendStrength.MODERATE]:
            return "strong_bear"
        
        return "neutral"
    
    def _get_h1_confirmation(
        self,
        h4: Optional[TimeframeAnalysis],
        h1: Optional[TimeframeAnalysis]
    ) -> str:
        """Verifica se 1H confirma ou diverge do 4H"""
        if not h4 or not h1:
            return "neutral"
        
        # Alinhado: mesma direção
        if h4.trend_bias == h1.trend_bias:
            return "aligned"
        
        # Divergente: direções opostas
        if (h4.trend_bias == TrendBias.LONG and h1.trend_bias == TrendBias.SHORT) or \
           (h4.trend_bias == TrendBias.SHORT and h1.trend_bias == TrendBias.LONG):
            return "divergent"
        
        return "neutral"
    
    def _detect_setup(self, analysis: SymbolAnalysis) -> Tuple[bool, str, str]:
        """
        Detecta se existe setup válido para operar.
        
        Regras:
        - 4H define direção
        - 15M dá gatilho (cross na direção)
        - 1H não pode estar fortemente contra
        
        Returns:
            (has_setup, setup_type, reason)
        """
        if not analysis.h4 or not analysis.m15:
            return False, "none", "Dados insuficientes"
        
        # Se 4H está neutral, não opera
        if analysis.trend_bias == TrendBias.NEUTRAL:
            return False, "none", "4H neutral - aguardando direção"
        
        # Se 1H está fortemente divergente, não opera
        if analysis.h1_confirmation == "divergent" and analysis.h1:
            if analysis.h1.trend_strength in [TrendStrength.STRONG, TrendStrength.MODERATE]:
                return False, "none", "1H divergente forte - aguardando alinhamento"
        
        # Verifica gatilho no 15M
        m15 = analysis.m15
        
        # LONG SETUP
        if analysis.trend_bias == TrendBias.LONG:
            # Cross bullish recente no 15M
            if m15.ema_cross == "bull_cross" and m15.bars_since_cross <= self.config.fresh_cross_15m:
                return True, "entry_long", f"15M bull cross há {m15.bars_since_cross} barras, 4H bullish"
            
            # 15M alinhado e pullback (preço perto da EMA26)
            if m15.trend_bias == TrendBias.LONG and abs(m15.price_vs_ema26_pct) < 1.5:
                return True, "entry_long", "15M bullish + pullback para EMA26"
        
        # SHORT SETUP
        elif analysis.trend_bias == TrendBias.SHORT:
            # Cross bearish recente no 15M
            if m15.ema_cross == "bear_cross" and m15.bars_since_cross <= self.config.fresh_cross_15m:
                return True, "entry_short", f"15M bear cross há {m15.bars_since_cross} barras, 4H bearish"
            
            # 15M alinhado e repique
            if m15.trend_bias == TrendBias.SHORT and abs(m15.price_vs_ema26_pct) < 1.5:
                return True, "entry_short", "15M bearish + repique para EMA26"
        
        return False, "none", "Sem gatilho no 15M"
    
    def _calculate_adjustments(self, analysis: SymbolAnalysis) -> Tuple[float, float]:
        """
        Calcula ajustes de tamanho e confidence baseado no contexto.
        
        Returns:
            (size_multiplier, confidence_adjustment)
        """
        size_mult = 1.0
        conf_adj = 0.0
        
        # Ajuste por clima do 1D
        if analysis.daily_climate == "strong_bull":
            if analysis.trend_bias == TrendBias.LONG:
                size_mult *= 1.2
                conf_adj += 0.05
            elif analysis.trend_bias == TrendBias.SHORT:
                size_mult *= 0.5
                conf_adj -= 0.10
        elif analysis.daily_climate == "strong_bear":
            if analysis.trend_bias == TrendBias.SHORT:
                size_mult *= 1.2
                conf_adj += 0.05
            elif analysis.trend_bias == TrendBias.LONG:
                size_mult *= 0.5
                conf_adj -= 0.10
        
        # Ajuste por confirmação do 1H
        if analysis.h1_confirmation == "aligned":
            size_mult *= self.config.size_mult_aligned
            conf_adj += 0.05
        elif analysis.h1_confirmation == "divergent":
            size_mult *= self.config.size_mult_divergent
            conf_adj -= 0.10
        
        # Clamp
        size_mult = max(0.2, min(1.5, size_mult))
        conf_adj = max(-0.20, min(0.15, conf_adj))
        
        return size_mult, conf_adj
    
    def has_valid_setup(self, analysis: SymbolAnalysis) -> bool:
        """Retorna se existe setup válido (para pre-check antes de chamar IA)"""
        return analysis.has_valid_setup
    
    def get_trend_bias(self, analysis: SymbolAnalysis) -> str:
        """Retorna trend_bias como string para compatibilidade"""
        return analysis.trend_bias.value
    
    # ========================================================================
    # Helpers para extração de dados
    # ========================================================================
    
    def _extract_closes(self, candles: List[Dict]) -> List[float]:
        """Extrai preços de fechamento"""
        closes = []
        for c in candles:
            close = self._get_candle_value(c, 'close')
            if close is not None:
                closes.append(close)
        return closes
    
    def _extract_highs(self, candles: List[Dict]) -> List[float]:
        """Extrai preços máximos"""
        highs = []
        for c in candles:
            high = self._get_candle_value(c, 'high')
            if high is not None:
                highs.append(high)
        return highs
    
    def _extract_lows(self, candles: List[Dict]) -> List[float]:
        """Extrai preços mínimos"""
        lows = []
        for c in candles:
            low = self._get_candle_value(c, 'low')
            if low is not None:
                lows.append(low)
        return lows
    
    def _get_candle_value(self, candle: Any, field: str) -> Optional[float]:
        """Extrai valor do candle (suporta vários formatos)"""
        if isinstance(candle, dict):
            # Dict com campos nomeados
            for key in [field, field.capitalize(), field[0]]:
                if key in candle:
                    try:
                        return float(candle[key])
                    except:
                        pass
        elif isinstance(candle, (list, tuple)):
            # Lista OHLCV
            idx_map = {'open': 1, 'high': 2, 'low': 3, 'close': 4, 'volume': 5}
            if field in idx_map and len(candle) > idx_map[field]:
                try:
                    return float(candle[idx_map[field]])
                except:
                    pass
        return None


# ============================================================================
# Funções de conveniência
# ============================================================================

_core_strategy: Optional[CoreStrategy] = None

def get_core_strategy(logger_instance=None) -> CoreStrategy:
    """Retorna instância singleton da Core Strategy"""
    global _core_strategy
    if _core_strategy is None:
        _core_strategy = CoreStrategy(logger_instance=logger_instance)
    return _core_strategy


def check_setup(
    symbol: str,
    candles_1d: List[Dict],
    candles_4h: List[Dict],
    candles_1h: List[Dict],
    candles_15m: List[Dict],
    logger_instance=None
) -> Tuple[bool, str, SymbolAnalysis]:
    """
    Função de conveniência para verificar setup.
    
    Returns:
        (has_setup, trend_bias, full_analysis)
    """
    strategy = get_core_strategy(logger_instance)
    analysis = strategy.analyze_symbol(symbol, candles_1d, candles_4h, candles_1h, candles_15m)
    return analysis.has_valid_setup, analysis.trend_bias.value, analysis
