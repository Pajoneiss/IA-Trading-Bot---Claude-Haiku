"""
Indicadores Técnicos para Análise de Mercado
"""
import numpy as np
from typing import List, Dict, Optional


class TechnicalIndicators:
    """Calcula indicadores técnicos a partir de dados OHLCV"""
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> Optional[float]:
        """
        Calcula Exponential Moving Average (EMA)
        
        Args:
            prices: Lista de preços (mais recente no final)
            period: Período da EMA
            
        Returns:
            Valor da EMA atual ou None se dados insuficientes
        """
        if len(prices) < period:
            return None
            
        prices_array = np.array(prices)
        multiplier = 2 / (period + 1)
        
        # Inicia com SMA
        ema = np.mean(prices_array[:period])
        
        # Calcula EMA para o restante
        for price in prices_array[period:]:
            ema = (price - ema) * multiplier + ema
            
        return float(ema)
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """
        Calcula Relative Strength Index (RSI)
        
        Args:
            prices: Lista de preços de fechamento
            period: Período do RSI (padrão 14)
            
        Returns:
            Valor do RSI (0-100) ou None se dados insuficientes
        """
        if len(prices) < period + 1:
            return None
            
        prices_array = np.array(prices)
        deltas = np.diff(prices_array)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], closes: List[float], 
                     period: int = 14) -> Optional[float]:
        """
        Calcula Average True Range (ATR)
        
        Args:
            highs: Lista de preços máximos
            lows: Lista de preços mínimos
            closes: Lista de preços de fechamento
            period: Período do ATR (padrão 14)
            
        Returns:
            Valor do ATR ou None se dados insuficientes
        """
        if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
            return None
            
        highs_array = np.array(highs)
        lows_array = np.array(lows)
        closes_array = np.array(closes)
        
        # True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list = []
        for i in range(1, len(closes_array)):
            hl = highs_array[i] - lows_array[i]
            hc = abs(highs_array[i] - closes_array[i-1])
            lc = abs(lows_array[i] - closes_array[i-1])
            tr = max(hl, hc, lc)
            tr_list.append(tr)
        
        if len(tr_list) < period:
            return None
            
        atr = np.mean(tr_list[-period:])
        return float(atr)
    
    @staticmethod
    def calculate_bb_bands(prices: List[float], period: int = 20, 
                          std_dev: float = 2.0) -> Optional[Dict[str, float]]:
        """
        Calcula Bandas de Bollinger
        
        Args:
            prices: Lista de preços de fechamento
            period: Período da média móvel (padrão 20)
            std_dev: Multiplicador de desvio padrão (padrão 2.0)
            
        Returns:
            Dict com upper, middle, lower ou None
        """
        if len(prices) < period:
            return None
            
        prices_array = np.array(prices[-period:])
        middle = np.mean(prices_array)
        std = np.std(prices_array)
        
        return {
            'upper': float(middle + std_dev * std),
            'middle': float(middle),
            'lower': float(middle - std_dev * std)
        }
    
    @staticmethod
    def detect_trend(prices: List[float], short_period: int = 9, 
                    long_period: int = 21) -> Dict[str, any]:
        """
        Detecta tendência usando cruzamento de EMAs
        
        Args:
            prices: Lista de preços
            short_period: Período da EMA curta
            long_period: Período da EMA longa
            
        Returns:
            Dict com trend, ema_short, ema_long, strength
        """
        if len(prices) < long_period:
            return {
                'trend': 'neutral',
                'ema_short': None,
                'ema_long': None,
                'strength': 0.0
            }
        
        ema_short = TechnicalIndicators.calculate_ema(prices, short_period)
        ema_long = TechnicalIndicators.calculate_ema(prices, long_period)
        
        if ema_short is None or ema_long is None:
            return {
                'trend': 'neutral',
                'ema_short': ema_short,
                'ema_long': ema_long,
                'strength': 0.0
            }
        
        diff_pct = ((ema_short - ema_long) / ema_long) * 100
        
        if diff_pct > 0.5:
            trend = 'bullish'
            strength = min(abs(diff_pct) / 2, 1.0)  # Normaliza força 0-1
        elif diff_pct < -0.5:
            trend = 'bearish'
            strength = min(abs(diff_pct) / 2, 1.0)
        else:
            trend = 'neutral'
            strength = 0.0
        
        return {
            'trend': trend,
            'ema_short': ema_short,
            'ema_long': ema_long,
            'strength': strength
        }
    
    @staticmethod
    def calculate_volatility(prices: List[float], period: int = 20) -> Optional[float]:
        """
        Calcula volatilidade como desvio padrão percentual
        
        Args:
            prices: Lista de preços
            period: Período para cálculo
            
        Returns:
            Volatilidade em % ou None
        """
        if len(prices) < period:
            return None
            
        prices_array = np.array(prices[-period:])
        returns = np.diff(prices_array) / prices_array[:-1]
        volatility = np.std(returns) * 100  # em %
        
        return float(volatility)
