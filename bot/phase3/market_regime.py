"""
Phase 3 - Market Regime Analyzer
Classifica mercado em regimes e ajusta estratégia
"""
import logging
from typing import Dict, Any, List, Optional
from statistics import mean, stdev

logger = logging.getLogger(__name__)


class MarketRegimeAnalyzer:
    """
    Analisa regime de mercado combinando:
    - Estrutura técnica multi-timeframe
    - Market Intelligence (Fear & Greed, BTC Dom, Alt Season)
    - Volatilidade (ATR)
    
    Regimes:
    - TREND_BULL: Tendência de alta clara
    - TREND_BEAR: Tendência de baixa clara
    - RANGE_CHOP: Lateral, sem direção
    - PANIC_HIGH_VOL: Volatilidade extrema
    - LOW_VOL_DRIFT: Drift de baixa volatilidade
    """
    
    # Thresholds configuráveis
    FG_PANIC_LOW = 20          # Fear & Greed abaixo = panic
    FG_PANIC_HIGH = 80         # Fear & Greed acima = euphoria
    FG_NEUTRAL_MIN = 40        # Range neutro
    FG_NEUTRAL_MAX = 60
    
    ATR_HIGH_FACTOR = 1.5      # ATR > média * 1.5 = high vol
    ATR_LOW_FACTOR = 0.6       # ATR < média * 0.6 = low vol
    
    TREND_MIN_SWINGS = 3       # Mínimo de swings para confirmar tendência
    RANGE_MAX_RANGE_PCT = 3.0  # Range < 3% = consolidação
    
    def __init__(self, logger_instance=None, technical_analysis=None):
        """
        Inicializa Market Regime Analyzer
        
        Args:
            logger_instance: Logger opcional
            technical_analysis: TechnicalAnalysis da Phase 2
        """
        self.logger = logger_instance or logger
        self.technical_analysis = technical_analysis
        
        self.logger.info("[MARKET REGIME] Inicializado")
    
    def evaluate(self,
                symbol: str,
                candles_m15: List[Dict[str, Any]],
                candles_h1: List[Dict[str, Any]],
                market_intel: Optional[Dict[str, Any]] = None,
                ema_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Avalia regime de mercado atual
        
        Args:
            symbol: Símbolo do ativo
            candles_m15: Candles 15m normalizados
            candles_h1: Candles 1h normalizados
            market_intel: Market Intelligence (Fear & Greed, etc)
            ema_context: Contexto EMA do EMACrossAnalyzer (para fresh cross detection)
            
        Returns:
            {
                'regime': 'TREND_BULL' | 'TREND_BEAR' | 'RANGE_CHOP' | 'PANIC_HIGH_VOL' | 'LOW_VOL_DRIFT',
                'trend_bias': 'long' | 'short' | 'neutral',
                'volatility': 'high' | 'normal' | 'low',
                'risk_off': bool,
                'notes': str
            }
        """
        try:
            # Valida inputs
            if not candles_h1 or len(candles_h1) < 20:
                return self._neutral_regime("Poucos candles H1")
            
            if not candles_m15 or len(candles_m15) < 20:
                return self._neutral_regime("Poucos candles 15m")
            
            # 1. Análise de volatilidade
            volatility_info = self._analyze_volatility(candles_h1)
            
            # 2. Análise de tendência H1
            trend_h1 = self._analyze_trend(candles_h1, "H1")
            
            # 3. Análise de tendência 15m
            trend_m15 = self._analyze_trend(candles_m15, "15m")
            
            # 4. Market Intelligence
            mi_info = self._analyze_market_intel(market_intel)
            
            # 5. Classifica regime
            regime_info = self._classify_regime(
                volatility_info=volatility_info,
                trend_h1=trend_h1,
                trend_m15=trend_m15,
                mi_info=mi_info,
                symbol=symbol,
                ema_context=ema_context
            )
            
            # Log do regime
            self.logger.info(
                f"[MARKET REGIME] {symbol} regime={regime_info['regime']}, "
                f"bias={regime_info['trend_bias']}, vol={regime_info['volatility']}, "
                f"risk_off={regime_info['risk_off']}"
            )
            
            self.logger.debug(f"[MARKET REGIME] {symbol} notes: {regime_info['notes']}")
            
            return regime_info
            
        except Exception as e:
            self.logger.error(f"[MARKET REGIME] Erro ao avaliar {symbol}: {e}", exc_info=True)
            return self._neutral_regime(f"Erro: {e}")
    
    def _analyze_volatility(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analisa volatilidade via ATR"""
        try:
            if len(candles) < 14:
                return {'level': 'normal', 'atr': 0, 'atr_pct': 0}
            
            # Calcula True Range para últimos 14 candles
            true_ranges = []
            for i in range(1, min(len(candles), 20)):
                high = candles[i].get('high', 0)
                low = candles[i].get('low', 0)
                prev_close = candles[i-1].get('close', 0)
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)
            
            if not true_ranges:
                return {'level': 'normal', 'atr': 0, 'atr_pct': 0}
            
            # ATR = média dos TRs
            atr = mean(true_ranges[-14:])
            atr_mean = mean(true_ranges)
            
            # ATR como % do preço
            current_price = candles[-1].get('close', 1)
            atr_pct = (atr / current_price * 100) if current_price > 0 else 0
            
            # Classifica volatilidade
            if atr > atr_mean * self.ATR_HIGH_FACTOR:
                level = 'high'
            elif atr < atr_mean * self.ATR_LOW_FACTOR:
                level = 'low'
            else:
                level = 'normal'
            
            return {
                'level': level,
                'atr': round(atr, 4),
                'atr_pct': round(atr_pct, 2),
                'atr_mean': round(atr_mean, 4)
            }
            
        except Exception as e:
            self.logger.debug(f"[MARKET REGIME] Erro ao calcular volatilidade: {e}")
            return {'level': 'normal', 'atr': 0, 'atr_pct': 0}
    
    def _analyze_trend(self, candles: List[Dict[str, Any]], timeframe: str) -> Dict[str, Any]:
        """
        Analisa tendência via swing highs/lows + EMAs (fallback mais tolerante)
        
        [Claude Trend Refactor] Data: 2024-12-11
        - Adicionado análise por EMA como alternativa menos exigente
        - EMA200 + EMA50 cross para detectar tendência mesmo sem swings perfeitos
        """
        try:
            if len(candles) < 10:
                return {'direction': 'neutral', 'strength': 0}
            
            # === MÉTODO 1: EMA ANALYSIS (mais tolerante) ===
            ema_trend = self._analyze_trend_by_ema(candles)
            
            # === MÉTODO 2: SWING ANALYSIS (mais rigoroso) ===
            swing_trend = self._analyze_trend_by_swings(candles)
            
            # Combina: Se EMA detecta tendência clara, usa EMA
            # Se EMA neutro mas swing detecta, usa swing
            # Prioriza EMA porque é mais estável
            if ema_trend['direction'] != 'neutral':
                return {
                    'direction': ema_trend['direction'],
                    'strength': ema_trend['strength'],
                    'method': 'ema',
                    'ema_data': ema_trend
                }
            elif swing_trend['direction'] != 'neutral':
                return {
                    'direction': swing_trend['direction'],
                    'strength': swing_trend['strength'],
                    'method': 'swing',
                    'swing_data': swing_trend
                }
            
            return {'direction': 'neutral', 'strength': 0.3, 'method': 'none'}
            
        except Exception as e:
            self.logger.debug(f"[MARKET REGIME] Erro ao analisar tendência: {e}")
            return {'direction': 'neutral', 'strength': 0}
    
    def _analyze_trend_by_ema(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        [Claude Trend Refactor] Análise de tendência por EMAs
        
        Critérios SIMPLES e TOLERANTES:
        - BULLISH: Preço > EMA200 E EMA50 > EMA200
        - BEARISH: Preço < EMA200 E EMA50 < EMA200
        - NEUTRAL: caso contrário
        """
        try:
            if len(candles) < 200:
                # Fallback com menos candles: usa EMA50 + EMA21
                return self._analyze_trend_by_short_ema(candles)
            
            # Extrai closes
            closes = [c.get('close', 0) for c in candles if c.get('close')]
            if len(closes) < 200:
                return self._analyze_trend_by_short_ema(candles)
            
            # Calcula EMAs
            ema50 = self._calculate_ema(closes, 50)
            ema200 = self._calculate_ema(closes, 200)
            
            current_price = closes[-1]
            
            # Verifica alinhamento
            price_above_200 = current_price > ema200
            ema50_above_200 = ema50 > ema200
            
            # Distância do preço à EMA200 (para strength)
            distance_pct = abs(current_price - ema200) / ema200 * 100 if ema200 > 0 else 0
            
            if price_above_200 and ema50_above_200:
                direction = 'bullish'
                # Strength aumenta com distância do preço à EMA200
                strength = min(0.9, 0.6 + (distance_pct / 10))
            elif not price_above_200 and not ema50_above_200:
                direction = 'bearish'
                strength = min(0.9, 0.6 + (distance_pct / 10))
            else:
                direction = 'neutral'
                strength = 0.3
            
            return {
                'direction': direction,
                'strength': round(strength, 2),
                'ema50': round(ema50, 4),
                'ema200': round(ema200, 4),
                'price': current_price,
                'distance_pct': round(distance_pct, 2)
            }
            
        except Exception as e:
            self.logger.debug(f"[MARKET REGIME] Erro na análise EMA: {e}")
            return {'direction': 'neutral', 'strength': 0}
    
    def _analyze_trend_by_short_ema(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Análise com EMAs mais curtas quando não há dados suficientes para 200
        Usa EMA21 + EMA50
        """
        try:
            closes = [c.get('close', 0) for c in candles if c.get('close')]
            if len(closes) < 50:
                return {'direction': 'neutral', 'strength': 0}
            
            ema21 = self._calculate_ema(closes, 21)
            ema50 = self._calculate_ema(closes, 50)
            current_price = closes[-1]
            
            price_above_50 = current_price > ema50
            ema21_above_50 = ema21 > ema50
            
            if price_above_50 and ema21_above_50:
                return {'direction': 'bullish', 'strength': 0.65}
            elif not price_above_50 and not ema21_above_50:
                return {'direction': 'bearish', 'strength': 0.65}
            
            return {'direction': 'neutral', 'strength': 0.3}
            
        except Exception:
            return {'direction': 'neutral', 'strength': 0}
    
    def _calculate_ema(self, values: List[float], period: int) -> float:
        """Calcula EMA de uma lista de valores"""
        if len(values) < period:
            return sum(values) / len(values) if values else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period  # SMA inicial
        
        for value in values[period:]:
            ema = (value - ema) * multiplier + ema
        
        return ema
    
    def _analyze_trend_by_swings(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Análise original por swing highs/lows (separada para clareza)"""
        try:
            # Identifica swing highs e lows
            highs = []
            lows = []
            
            window = 3
            for i in range(window, len(candles) - window):
                high = candles[i].get('high', 0)
                low = candles[i].get('low', 0)
                
                # Swing high
                is_swing_high = all(
                    high >= candles[j].get('high', 0)
                    for j in range(i - window, i + window + 1)
                    if j != i
                )
                if is_swing_high:
                    highs.append(high)
                
                # Swing low
                is_swing_low = all(
                    low <= candles[j].get('low', 0)
                    for j in range(i - window, i + window + 1)
                    if j != i
                )
                if is_swing_low:
                    lows.append(low)
            
            # Precisa de pelo menos 3 swings
            if len(highs) < self.TREND_MIN_SWINGS or len(lows) < self.TREND_MIN_SWINGS:
                return {'direction': 'neutral', 'strength': 0}
            
            # Analisa progressão
            recent_highs = highs[-3:]
            recent_lows = lows[-3:]
            
            # Higher highs + higher lows = bullish
            higher_highs = all(recent_highs[i] > recent_highs[i-1] for i in range(1, len(recent_highs)))
            higher_lows = all(recent_lows[i] > recent_lows[i-1] for i in range(1, len(recent_lows)))
            
            # Lower highs + lower lows = bearish
            lower_highs = all(recent_highs[i] < recent_highs[i-1] for i in range(1, len(recent_highs)))
            lower_lows = all(recent_lows[i] < recent_lows[i-1] for i in range(1, len(recent_lows)))
            
            if higher_highs and higher_lows:
                direction = 'bullish'
                strength = 0.8
            elif lower_highs and lower_lows:
                direction = 'bearish'
                strength = 0.8
            else:
                direction = 'neutral'
                strength = 0.3
            
            return {
                'direction': direction,
                'strength': strength,
                'highs_count': len(highs),
                'lows_count': len(lows)
            }
            
        except Exception as e:
            return {'direction': 'neutral', 'strength': 0}
    
    def _analyze_market_intel(self, market_intel: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Analisa Market Intelligence"""
        if not market_intel:
            return {'fg_level': 'neutral', 'risk_off': False}
        
        try:
            fg_data = market_intel.get('fear_greed', {})
            fg_value = fg_data.get('value', 50)
            
            # Classifica Fear & Greed
            if fg_value < self.FG_PANIC_LOW:
                fg_level = 'extreme_fear'
                risk_off = True
            elif fg_value > self.FG_PANIC_HIGH:
                fg_level = 'extreme_greed'
                risk_off = True
            elif fg_value < self.FG_NEUTRAL_MIN:
                fg_level = 'fear'
                risk_off = False
            elif fg_value > self.FG_NEUTRAL_MAX:
                fg_level = 'greed'
                risk_off = False
            else:
                fg_level = 'neutral'
                risk_off = False
            
            return {
                'fg_level': fg_level,
                'fg_value': fg_value,
                'risk_off': risk_off
            }
            
        except Exception as e:
            self.logger.debug(f"[MARKET REGIME] Erro ao analisar MI: {e}")
            return {'fg_level': 'neutral', 'risk_off': False}
    
    def _classify_regime(self,
                        volatility_info: Dict,
                        trend_h1: Dict,
                        trend_m15: Dict,
                        mi_info: Dict,
                        symbol: str,
                        ema_context: Dict = None) -> Dict[str, Any]:
        """
        Classifica regime baseado em todos os fatores.
        
        [Core Strategy Refactor] Agora considera:
        - Fresh EMA cross como sinal forte (mesmo sem strength alto)
        - Threshold de strength reduzido de 0.6 para 0.4
        - Cross recente no 30m/15m aumenta probabilidade de trend
        """
        
        vol_level = volatility_info.get('level', 'normal')
        h1_direction = trend_h1.get('direction', 'neutral')
        m15_direction = trend_m15.get('direction', 'neutral')
        h1_strength = trend_h1.get('strength', 0)
        m15_strength = trend_m15.get('strength', 0)
        fg_level = mi_info.get('fg_level', 'neutral')
        risk_off = mi_info.get('risk_off', False)
        
        notes = []
        
        # [NEW] Detecta fresh cross do EMA context
        has_fresh_bull_cross = False
        has_fresh_bear_cross = False
        if ema_context:
            states = ema_context.get('states', {})
            for tf in ['30m', '1h']:
                state = states.get(tf, {})
                if isinstance(state, dict):
                    cross = state.get('last_cross_direction')
                    bars = state.get('bars_since_last_cross', 99)
                    is_fresh = state.get('is_fresh_cross', False)
                elif hasattr(state, 'last_cross_direction'):
                    cross = state.last_cross_direction
                    bars = state.bars_since_last_cross or 99
                    is_fresh = state.is_fresh_cross
                else:
                    continue
                
                # Cross é "fresh" se < 8 barras
                if cross == 'bull' and (is_fresh or bars < 8):
                    has_fresh_bull_cross = True
                    notes.append(f"Fresh bull cross {tf}")
                elif cross == 'bear' and (is_fresh or bars < 8):
                    has_fresh_bear_cross = True
                    notes.append(f"Fresh bear cross {tf}")
        
        # PANIC_HIGH_VOL: volatilidade extrema
        if vol_level == 'high' and fg_level in ['extreme_fear', 'extreme_greed']:
            regime = 'PANIC_HIGH_VOL'
            trend_bias = 'neutral'
            risk_off = True
            notes.append(f"Volatilidade alta ({volatility_info.get('atr_pct', 0):.2f}%) + {fg_level}")
        
        # LOW_VOL_DRIFT: baixa volatilidade sem direção
        elif vol_level == 'low' and h1_direction == 'neutral' and not has_fresh_bull_cross and not has_fresh_bear_cross:
            regime = 'LOW_VOL_DRIFT'
            trend_bias = 'neutral'
            notes.append(f"Volatilidade baixa + sem tendência clara")
        
        # TREND_BULL: tendência de alta
        # [CHANGED] Threshold reduzido de 0.6 para 0.4, OU fresh bull cross
        elif (h1_direction == 'bullish' and m15_direction in ['bullish', 'neutral'] and h1_strength > 0.4) or \
             (has_fresh_bull_cross and h1_direction != 'bearish'):
            regime = 'TREND_BULL'
            trend_bias = 'long'
            if has_fresh_bull_cross:
                notes.append(f"Fresh bull cross detectado!")
            notes.append(f"H1 {h1_direction} (strength={h1_strength:.2f})")
        
        # TREND_BEAR: tendência de baixa
        # [CHANGED] Threshold reduzido de 0.6 para 0.4, OU fresh bear cross
        elif (h1_direction == 'bearish' and m15_direction in ['bearish', 'neutral'] and h1_strength > 0.4) or \
             (has_fresh_bear_cross and h1_direction != 'bullish'):
            regime = 'TREND_BEAR'
            trend_bias = 'short'
            if has_fresh_bear_cross:
                notes.append(f"Fresh bear cross detectado!")
            notes.append(f"H1 {h1_direction} (strength={h1_strength:.2f})")
        
        # RANGE_CHOP: sem direção clara
        else:
            regime = 'RANGE_CHOP'
            trend_bias = 'neutral'
            notes.append(f"H1 {h1_direction}, 15m {m15_direction}, strength={h1_strength:.2f}")
        
        # Adiciona info de volatilidade
        notes.append(f"vol={vol_level}")
        
        # Adiciona info de Fear & Greed
        if fg_level != 'neutral':
            notes.append(f"FG={fg_level}")
        
        return {
            'regime': regime,
            'trend_bias': trend_bias,
            'volatility': vol_level,
            'risk_off': risk_off,
            'notes': ' | '.join(notes),
            'raw_data': {
                'h1_direction': h1_direction,
                'm15_direction': m15_direction,
                'h1_strength': h1_strength,
                'vol_level': vol_level,
                'atr_pct': volatility_info.get('atr_pct', 0),
                'fg_level': fg_level,
                'fg_value': mi_info.get('fg_value', 50)
            }
        }
    
    def _neutral_regime(self, reason: str) -> Dict[str, Any]:
        """Retorna regime neutro padrão"""
        return {
            'regime': 'RANGE_CHOP',
            'trend_bias': 'neutral',
            'volatility': 'normal',
            'risk_off': False,
            'notes': f'Regime neutro: {reason}',
            'raw_data': {}
        }
