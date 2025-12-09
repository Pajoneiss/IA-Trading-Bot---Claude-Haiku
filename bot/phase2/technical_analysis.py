"""
Phase 2 - Technical Analysis
SMC (Smart Money Concepts) + Price Action + Multi-Timeframe
"""
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TechnicalAnalysis:
    """
    Análise técnica avançada
    
    Features:
    - Multi-timeframe (H4/H1 → 15m/5m)
    - SMC: BOS, CHoCH, Order Blocks, Liquidity
    - Price Action: padrões, velas
    - EMA confluence (opcional)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Inicializa análise técnica"""
        self.config = config or {}
        
        logger.info("[TECHNICAL ANALYSIS] Inicializado")
    
    @staticmethod
    def normalize_candles(raw_candles: List[Any], logger_instance: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        Converte candles no formato bruto da Hyperliquid para um formato padronizado:
        {
            "open": float,
            "high": float,
            "low": float,
            "close": float,
            "volume": float,
            "timestamp": int/float (opcional)
        }
        
        Aceita:
        - Formato Hyperliquid: {'o', 'h', 'l', 'c', 'v', 't'}
        - Formato padrão: {'open', 'high', 'low', 'close', 'volume'}
        - Lista tipo [timestamp, open, high, low, close, volume]
        
        Ignora candles inválidos e loga avisos em nível DEBUG sem quebrar o fluxo.
        Sempre retorna uma lista (possivelmente vazia).
        
        Args:
            raw_candles: Lista de candles em qualquer formato
            logger_instance: Logger opcional para debug
            
        Returns:
            Lista de candles normalizados
        """
        if not raw_candles:
            return []
        
        normalized = []
        log = logger_instance or logger
        
        for item in raw_candles:
            try:
                # CASO 1: Se é lista tipo [timestamp, open, high, low, close, volume]
                if isinstance(item, (list, tuple)):
                    if len(item) >= 5:
                        ts = item[0] if len(item) > 5 else None
                        o, h, l, c, v = item[1:6] if len(item) > 5 else item[:5]
                        
                        candle = {
                            'open': float(o),
                            'high': float(h),
                            'low': float(l),
                            'close': float(c),
                            'volume': float(v)
                        }
                        
                        if ts is not None:
                            candle['timestamp'] = ts
                        
                        normalized.append(candle)
                    else:
                        log.debug(f"[TECHNICAL ANALYSIS] Candle inválido ignorado (lista muito curta): {item}")
                        continue
                
                # CASO 2: Se é dict
                elif isinstance(item, dict):
                    # Tenta pegar valores com prioridade para formato compacto
                    o = item.get('o') or item.get('open')
                    h = item.get('h') or item.get('high')
                    l = item.get('l') or item.get('low')
                    c = item.get('c') or item.get('close')
                    v = item.get('v') or item.get('volume', 0)  # Volume pode ser 0
                    ts = item.get('t') or item.get('timestamp')
                    
                    # Valida campos essenciais
                    if o is None or h is None or l is None or c is None:
                        log.debug(f"[TECHNICAL ANALYSIS] Candle inválido ignorado (campos faltando): {item}")
                        continue
                    
                    candle = {
                        'open': float(o),
                        'high': float(h),
                        'low': float(l),
                        'close': float(c),
                        'volume': float(v)
                    }
                    
                    if ts is not None:
                        candle['timestamp'] = ts
                    
                    normalized.append(candle)
                
                else:
                    log.debug(f"[TECHNICAL ANALYSIS] Candle com tipo desconhecido ignorado: {type(item)}")
                    continue
                    
            except (ValueError, TypeError, KeyError, IndexError) as e:
                log.debug(f"[TECHNICAL ANALYSIS] Candle inválido ignorado: {item} ({e})")
                continue
        
        return normalized
    
    def analyze_structure(self, 
                         candles: List[Dict[str, Any]],
                         timeframe: str = "15m") -> Dict[str, Any]:
        """
        Analisa estrutura de mercado
        
        Args:
            candles: Lista de candles OHLCV
            timeframe: Timeframe (H4, H1, 15m, 5m)
            
        Returns:
            {
                'trend': 'bullish' | 'bearish' | 'ranging',
                'structure': 'BOS' | 'CHoCH' | 'consolidation',
                'key_levels': {'support': [...], 'resistance': [...]},
                'confidence': 0.0-1.0
            }
        """
        # Normaliza candles PRIMEIRO
        candles = self.normalize_candles(candles)
        
        if not candles or len(candles) < 20:
            return self._empty_structure()
        
        try:
            # Identifica topos e fundos
            highs, lows = self._find_swing_points(candles)
            
            # Determina tendência
            trend = self._determine_trend(candles, highs, lows)
            
            # Identifica estrutura (BOS/CHoCH)
            structure = self._identify_structure(candles, highs, lows, trend)
            
            # Níveis-chave
            key_levels = self._identify_key_levels(candles, highs, lows)
            
            # Confidence baseado na clareza da estrutura
            confidence = self._calculate_structure_confidence(trend, structure, key_levels)
            
            result = {
                'trend': trend,
                'structure': structure,
                'key_levels': key_levels,
                'confidence': confidence,
                'timeframe': timeframe
            }
            
            logger.debug(f"[TECHNICAL ANALYSIS] {timeframe} Structure: {trend} {structure} conf={confidence:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"[TECHNICAL ANALYSIS] Erro ao analisar estrutura: {e}")
            return self._empty_structure()
    
    def detect_patterns(self, candles: List[Dict[str, Any]]) -> List[str]:
        """
        Detecta padrões de price action
        
        Returns:
            Lista de padrões detectados: ['engulfing', 'doji', 'pin_bar', etc]
        """
        # Normaliza candles PRIMEIRO
        candles = self.normalize_candles(candles)
        
        if not candles or len(candles) < 3:
            return []
        
        patterns = []
        
        try:
            # Últimas 3 velas
            recent = candles[-3:]
            last = candles[-1]
            prev = candles[-2]
            
            # === ENGULFING ===
            if self._is_bullish_engulfing(prev, last):
                patterns.append('bullish_engulfing')
            
            if self._is_bearish_engulfing(prev, last):
                patterns.append('bearish_engulfing')
            
            # === PIN BAR ===
            if self._is_pin_bar(last):
                patterns.append('pin_bar')
            
            # === DOJI ===
            if self._is_doji(last):
                patterns.append('doji')
            
            # === INSIDE BAR ===
            if self._is_inside_bar(prev, last):
                patterns.append('inside_bar')
            
            # === HAMMER / SHOOTING STAR ===
            if self._is_hammer(last):
                patterns.append('hammer')
            
            if self._is_shooting_star(last):
                patterns.append('shooting_star')
            
            if patterns:
                logger.debug(f"[TECHNICAL ANALYSIS] Padrões detectados: {', '.join(patterns)}")
            
            return patterns
            
        except Exception as e:
            logger.error(f"[TECHNICAL ANALYSIS] Erro ao detectar padrões: {e}")
            return []
    
    def check_ema_confluence(self,
                            candles: List[Dict[str, Any]],
                            ema_short: int = 9,
                            ema_long: int = 26) -> Dict[str, Any]:
        """
        Verifica confluência de EMAs (OPCIONAL)
        
        Args:
            candles: Lista de candles
            ema_short: Período EMA curta (default 9)
            ema_long: Período EMA longa (default 26)
            
        Returns:
            {
                'cross': 'bullish' | 'bearish' | 'none',
                'alignment': 'bullish' | 'bearish' | 'neutral',
                'price_above_ema': bool,
                'distance_pct': float,
                'strength': 0.0-1.0
            }
        """
        # Normaliza candles PRIMEIRO
        candles = self.normalize_candles(candles)
        
        if not candles or len(candles) < max(ema_short, ema_long) + 5:
            return {'cross': 'none', 'alignment': 'neutral', 'strength': 0.0}
        
        try:
            # Calcula EMAs
            ema_s = self._calculate_ema(candles, ema_short)
            ema_l = self._calculate_ema(candles, ema_long)
            
            if not ema_s or not ema_l:
                return {'cross': 'none', 'alignment': 'neutral', 'strength': 0.0}
            
            current_price = candles[-1]['close']
            
            # Detecta cruzamento recente (últimas 5 velas)
            cross = self._detect_ema_cross(ema_s[-5:], ema_l[-5:])
            
            # Alinhamento atual
            if ema_s[-1] > ema_l[-1]:
                alignment = 'bullish'
            elif ema_s[-1] < ema_l[-1]:
                alignment = 'bearish'
            else:
                alignment = 'neutral'
            
            # Preço vs EMA
            price_above_ema = current_price > ema_s[-1]
            
            # Distância do preço até EMA curta (%)
            distance_pct = ((current_price - ema_s[-1]) / ema_s[-1]) * 100
            
            # Força do sinal EMA (baseado em alinhamento e distância)
            strength = self._calculate_ema_strength(alignment, distance_pct, cross)
            
            result = {
                'cross': cross,
                'alignment': alignment,
                'price_above_ema': price_above_ema,
                'distance_pct': round(distance_pct, 2),
                'strength': round(strength, 2)
            }
            
            logger.debug(f"[TECHNICAL ANALYSIS] EMA: {alignment} | cross={cross} | strength={strength:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"[TECHNICAL ANALYSIS] Erro ao checar EMAs: {e}")
            return {'cross': 'none', 'alignment': 'neutral', 'strength': 0.0}
    
    def identify_liquidity_zones(self, candles: List[Dict[str, Any]]) -> Dict[str, List[float]]:
        """
        Identifica zonas de liquidez (topos/fundos óbvios)
        
        Returns:
            {
                'buy_side': [prices...],  # Liquidez de compra (acima)
                'sell_side': [prices...]  # Liquidez de venda (abaixo)
            }
        """
        # Normaliza candles PRIMEIRO
        candles = self.normalize_candles(candles)
        
        if not candles or len(candles) < 20:
            return {'buy_side': [], 'sell_side': []}
        
        try:
            highs, lows = self._find_swing_points(candles)
            
            # Liquidez buy-side = topos recentes (stop losses de shorts)
            buy_side = sorted(highs[-5:], reverse=True)[:3]
            
            # Liquidez sell-side = fundos recentes (stop losses de longs)
            sell_side = sorted(lows[-5:])[:3]
            
            return {
                'buy_side': buy_side,
                'sell_side': sell_side
            }
            
        except Exception as e:
            logger.error(f"[TECHNICAL ANALYSIS] Erro ao identificar liquidez: {e}")
            return {'buy_side': [], 'sell_side': []}
    
    # ========== MÉTODOS AUXILIARES ==========
    
    def _empty_structure(self) -> Dict[str, Any]:
        """Retorna estrutura vazia"""
        return {
            'trend': 'ranging',
            'structure': 'consolidation',
            'key_levels': {'support': [], 'resistance': []},
            'confidence': 0.0,
            'timeframe': 'unknown'
        }
    
    def _find_swing_points(self, candles: List[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
        """Identifica swing highs e lows"""
        highs = []
        lows = []
        
        window = 5  # Janela para identificar swings
        
        for i in range(window, len(candles) - window):
            high = candles[i]['high']
            low = candles[i]['low']
            
            # Swing high
            is_swing_high = all(high >= candles[j]['high'] for j in range(i-window, i+window+1) if j != i)
            if is_swing_high:
                highs.append(high)
            
            # Swing low
            is_swing_low = all(low <= candles[j]['low'] for j in range(i-window, i+window+1) if j != i)
            if is_swing_low:
                lows.append(low)
        
        return highs, lows
    
    def _determine_trend(self, candles: List[Dict[str, Any]], highs: List[float], lows: List[float]) -> str:
        """Determina tendência"""
        if len(highs) < 3 or len(lows) < 3:
            return 'ranging'
        
        # Higher highs + higher lows = bullish
        if highs[-1] > highs[-2] > highs[-3] and lows[-1] > lows[-2]:
            return 'bullish'
        
        # Lower lows + lower highs = bearish
        if highs[-1] < highs[-2] < highs[-3] and lows[-1] < lows[-2]:
            return 'bearish'
        
        return 'ranging'
    
    def _identify_structure(self, candles: List[Dict[str, Any]], highs: List[float], lows: List[float], trend: str) -> str:
        """Identifica BOS/CHoCH"""
        if not highs or not lows:
            return 'consolidation'
        
        current_high = candles[-1]['high']
        current_low = candles[-1]['low']
        
        # BOS (Break of Structure) = rompe estrutura na direção da tendência
        if trend == 'bullish' and current_high > max(highs[-3:]):
            return 'BOS_bullish'
        
        if trend == 'bearish' and current_low < min(lows[-3:]):
            return 'BOS_bearish'
        
        # CHoCH (Change of Character) = rompe estrutura contra a tendência
        if trend == 'bullish' and current_low < min(lows[-2:]):
            return 'CHoCH_bearish'
        
        if trend == 'bearish' and current_high > max(highs[-2:]):
            return 'CHoCH_bullish'
        
        return 'consolidation'
    
    def _identify_key_levels(self, candles: List[Dict[str, Any]], highs: List[float], lows: List[float]) -> Dict[str, List[float]]:
        """Identifica níveis-chave de suporte/resistência"""
        # Últimos 3 swings
        support = sorted(lows[-5:])[:3] if lows else []
        resistance = sorted(highs[-5:], reverse=True)[:3] if highs else []
        
        return {
            'support': support,
            'resistance': resistance
        }
    
    def _calculate_structure_confidence(self, trend: str, structure: str, key_levels: Dict) -> float:
        """Calcula confiança na estrutura"""
        confidence = 0.5  # Base
        
        # Tendência clara
        if trend in ['bullish', 'bearish']:
            confidence += 0.2
        
        # Estrutura definida (BOS/CHoCH)
        if 'BOS' in structure or 'CHoCH' in structure:
            confidence += 0.2
        
        # Níveis-chave bem definidos
        if len(key_levels.get('support', [])) >= 2 and len(key_levels.get('resistance', [])) >= 2:
            confidence += 0.1
        
        return min(1.0, confidence)
    
    # === PADRÕES DE VELAS ===
    
    def _is_bullish_engulfing(self, prev: Dict, current: Dict) -> bool:
        """Detecta engulfing bullish"""
        try:
            prev_body = abs(prev.get('close', 0) - prev.get('open', 0))
            curr_body = abs(current.get('close', 0) - current.get('open', 0))
            
            return (prev.get('close', 0) < prev.get('open', 0) and  # Prev bearish
                    current.get('close', 0) > current.get('open', 0) and  # Current bullish
                    curr_body > prev_body * 1.5 and  # Corpo maior
                    current.get('close', 0) > prev.get('open', 0))  # Engole anterior
        except (TypeError, ValueError):
            return False
    
    def _is_bearish_engulfing(self, prev: Dict, current: Dict) -> bool:
        """Detecta engulfing bearish"""
        try:
            prev_body = abs(prev.get('close', 0) - prev.get('open', 0))
            curr_body = abs(current.get('close', 0) - current.get('open', 0))
            
            return (prev.get('close', 0) > prev.get('open', 0) and  # Prev bullish
                    current.get('close', 0) < current.get('open', 0) and  # Current bearish
                    curr_body > prev_body * 1.5 and  # Corpo maior
                    current.get('close', 0) < prev.get('open', 0))  # Engole anterior
        except (TypeError, ValueError):
            return False
    
    def _is_pin_bar(self, candle: Dict) -> bool:
        """Detecta pin bar"""
        try:
            body = abs(candle.get('close', 0) - candle.get('open', 0))
            total = candle.get('high', 0) - candle.get('low', 0)
            
            if total == 0:
                return False
            
            # Pavio > 2x corpo
            upper_wick = candle.get('high', 0) - max(candle.get('open', 0), candle.get('close', 0))
            lower_wick = min(candle.get('open', 0), candle.get('close', 0)) - candle.get('low', 0)
            
            return (upper_wick > body * 2 or lower_wick > body * 2)
        except (TypeError, ValueError):
            return False
    
    def _is_doji(self, candle: Dict) -> bool:
        """Detecta doji"""
        try:
            body = abs(candle.get('close', 0) - candle.get('open', 0))
            total = candle.get('high', 0) - candle.get('low', 0)
            
            if total == 0:
                return False
            
            # Corpo < 10% do total
            return (body / total) < 0.1
        except (TypeError, ValueError, ZeroDivisionError):
            return False
    
    def _is_inside_bar(self, prev: Dict, current: Dict) -> bool:
        """Detecta inside bar"""
        try:
            return (current.get('high', 0) < prev.get('high', 0) and 
                    current.get('low', 0) > prev.get('low', 0))
        except (TypeError, ValueError):
            return False
    
    def _is_hammer(self, candle: Dict) -> bool:
        """Detecta hammer (bullish)"""
        try:
            body = abs(candle.get('close', 0) - candle.get('open', 0))
            lower_wick = min(candle.get('open', 0), candle.get('close', 0)) - candle.get('low', 0)
            upper_wick = candle.get('high', 0) - max(candle.get('open', 0), candle.get('close', 0))
            
            return (lower_wick > body * 2 and upper_wick < body * 0.5)
        except (TypeError, ValueError):
            return False
    
    def _is_shooting_star(self, candle: Dict) -> bool:
        """Detecta shooting star (bearish)"""
        try:
            body = abs(candle.get('close', 0) - candle.get('open', 0))
            upper_wick = candle.get('high', 0) - max(candle.get('open', 0), candle.get('close', 0))
            lower_wick = min(candle.get('open', 0), candle.get('close', 0)) - candle.get('low', 0)
            
            return (upper_wick > body * 2 and lower_wick < body * 0.5)
        except (TypeError, ValueError):
            return False
    
    # === EMAs ===
    
    def _calculate_ema(self, candles: List[Dict[str, Any]], period: int) -> List[float]:
        """Calcula EMA"""
        if len(candles) < period:
            return []
        
        closes = [c['close'] for c in candles]
        
        # SMA inicial
        sma = sum(closes[:period]) / period
        ema = [sma]
        
        # Multiplier
        multiplier = 2 / (period + 1)
        
        # Calcula EMA
        for i in range(period, len(closes)):
            ema_value = (closes[i] - ema[-1]) * multiplier + ema[-1]
            ema.append(ema_value)
        
        return ema
    
    def _detect_ema_cross(self, ema_short: List[float], ema_long: List[float]) -> str:
        """Detecta cruzamento de EMAs"""
        if len(ema_short) < 2 or len(ema_long) < 2:
            return 'none'
        
        # Bullish cross (short cruza long para cima)
        if ema_short[-2] <= ema_long[-2] and ema_short[-1] > ema_long[-1]:
            return 'bullish'
        
        # Bearish cross (short cruza long para baixo)
        if ema_short[-2] >= ema_long[-2] and ema_short[-1] < ema_long[-1]:
            return 'bearish'
        
        return 'none'
    
    def _calculate_ema_strength(self, alignment: str, distance_pct: float, cross: str) -> float:
        """Calcula força do sinal EMA"""
        strength = 0.3  # Base
        
        # Alinhamento
        if alignment in ['bullish', 'bearish']:
            strength += 0.3
        
        # Cruzamento recente
        if cross != 'none':
            strength += 0.2
        
        # Distância adequada (não muito longe)
        if 0.5 <= abs(distance_pct) <= 2.0:
            strength += 0.2
        
        return min(1.0, strength)
