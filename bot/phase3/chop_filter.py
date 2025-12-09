"""
Phase 3 - Anti-Chop Filter
Detecta quando mercado está "sujo" (muito pavio, sem direção)
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ChopFilter:
    """
    Detecta mercados choppy (sujos) analisando:
    - Relação wick/body (pavios grandes vs corpo pequeno)
    - Alternância de direção (indecisão)
    - Lack of expansion (range estreito)
    """
    
    # Thresholds configuráveis
    WICK_BODY_RATIO_THRESHOLD = 2.0    # Wick > 2x body = choppy
    DIRECTIONAL_CHANGE_THRESHOLD = 0.7  # >70% alternando = choppy
    MIN_CANDLES = 10                    # Mínimo para análise
    
    def __init__(self, logger_instance=None):
        """Inicializa Chop Filter"""
        self.logger = logger_instance or logger
        self.logger.info("[CHOP FILTER] Inicializado")
    
    def detect_chop(self, candles_m15: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detecta se mercado está choppy
        
        Args:
            candles_m15: Candles 15m normalizados
            
        Returns:
            {
                'is_choppy': bool,
                'chop_score': float,  # 0.0 a 1.0
                'reason': str
            }
        """
        try:
            if not candles_m15 or len(candles_m15) < self.MIN_CANDLES:
                return {
                    'is_choppy': False,
                    'chop_score': 0.0,
                    'reason': 'Poucos candles para análise'
                }
            
            # Analisa últimos N candles
            recent_candles = candles_m15[-self.MIN_CANDLES:]
            
            # 1. Calcula wick/body ratio
            wick_body_score = self._analyze_wick_body_ratio(recent_candles)
            
            # 2. Calcula alternância de direção
            directional_score = self._analyze_directional_changes(recent_candles)
            
            # 3. Calcula expansion (ou falta dela)
            expansion_score = self._analyze_range_expansion(recent_candles)
            
            # Chop score = média ponderada
            chop_score = (
                wick_body_score * 0.4 +      # 40% peso
                directional_score * 0.4 +    # 40% peso
                expansion_score * 0.2        # 20% peso
            )
            
            # Classifica
            is_choppy = chop_score > 0.65  # Mais sensível
            
            # Monta razão
            reasons = []
            if wick_body_score > 0.7:
                reasons.append("pavios grandes")
            if directional_score > 0.7:
                reasons.append("indecisão")
            if expansion_score > 0.7:
                reasons.append("range estreito")
            
            reason = ', '.join(reasons) if reasons else "mercado limpo"
            
            # Log
            if is_choppy:
                self.logger.debug(
                    f"[CHOP FILTER] Choppy detectado: score={chop_score:.2f}, "
                    f"reason={reason}"
                )
            
            return {
                'is_choppy': is_choppy,
                'chop_score': round(chop_score, 2),
                'reason': reason,
                'components': {
                    'wick_body': round(wick_body_score, 2),
                    'directional': round(directional_score, 2),
                    'expansion': round(expansion_score, 2)
                }
            }
            
        except Exception as e:
            self.logger.error(f"[CHOP FILTER] Erro ao detectar chop: {e}", exc_info=True)
            return {
                'is_choppy': False,
                'chop_score': 0.0,
                'reason': f'Erro: {e}'
            }
    
    def _analyze_wick_body_ratio(self, candles: List[Dict[str, Any]]) -> float:
        """
        Analisa relação wick/body
        
        Returns:
            Score 0.0-1.0 (1.0 = muito choppy)
        """
        high_ratio_count = 0
        
        for candle in candles:
            try:
                o = candle.get('open', 0)
                h = candle.get('high', 0)
                l = candle.get('low', 0)
                c = candle.get('close', 0)
                
                # Corpo
                body = abs(c - o)
                
                # Wick total
                total_wick = h - l
                
                # Se corpo muito pequeno, conta como choppy
                if body < total_wick * 0.2:  # Corpo < 20% do range total
                    high_ratio_count += 1
                
            except (TypeError, ValueError, ZeroDivisionError):
                continue
        
        # Score = % de candles com wick alto
        score = high_ratio_count / len(candles) if candles else 0
        return min(1.0, score)
    
    def _analyze_directional_changes(self, candles: List[Dict[str, Any]]) -> float:
        """
        Analisa alternância de direção
        
        Returns:
            Score 0.0-1.0 (1.0 = muita alternância)
        """
        if len(candles) < 2:
            return 0.0
        
        changes = 0
        prev_direction = None
        
        for i in range(len(candles)):
            try:
                o = candles[i].get('open', 0)
                c = candles[i].get('close', 0)
                
                # Direção da vela
                if c > o:
                    direction = 'up'
                elif c < o:
                    direction = 'down'
                else:
                    direction = 'neutral'
                
                # Conta mudança de direção
                if prev_direction and prev_direction != direction and direction != 'neutral':
                    changes += 1
                
                prev_direction = direction
                
            except (TypeError, ValueError):
                continue
        
        # Score = % de mudanças vs possível
        max_changes = len(candles) - 1
        score = changes / max_changes if max_changes > 0 else 0
        
        return min(1.0, score)
    
    def _analyze_range_expansion(self, candles: List[Dict[str, Any]]) -> float:
        """
        Analisa se range está expandindo ou preso
        
        Returns:
            Score 0.0-1.0 (1.0 = range muito estreito)
        """
        if len(candles) < 5:
            return 0.0
        
        try:
            # Calcula range dos últimos 5 vs primeiros 5
            recent_highs = [c.get('high', 0) for c in candles[-5:]]
            recent_lows = [c.get('low', 0) for c in candles[-5:]]
            
            early_highs = [c.get('high', 0) for c in candles[:5]]
            early_lows = [c.get('low', 0) for c in candles[:5]]
            
            recent_range = max(recent_highs) - min(recent_lows)
            early_range = max(early_highs) - min(early_lows)
            
            # Se range recente menor que early = contracting
            if early_range > 0:
                contraction_ratio = recent_range / early_range
                
                # Score alto se contracting
                if contraction_ratio < 0.5:  # Range caiu >50%
                    return 0.8
                elif contraction_ratio < 0.7:
                    return 0.5
                else:
                    return 0.2
            else:
                return 0.5
            
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0


def detect_chop(candles_m15: List[Dict[str, Any]], logger_instance=None) -> Dict[str, Any]:
    """
    Função standalone para detectar chop
    
    Args:
        candles_m15: Candles 15m normalizados
        logger_instance: Logger opcional
        
    Returns:
        {'is_choppy': bool, 'chop_score': float, 'reason': str}
    """
    chop_filter = ChopFilter(logger_instance=logger_instance)
    return chop_filter.detect_chop(candles_m15)
