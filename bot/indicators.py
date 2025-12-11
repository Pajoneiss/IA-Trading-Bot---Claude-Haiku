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
    
    # ========================================================================
    # [Core Strategy] ADX - Average Directional Index
    # ========================================================================
    @staticmethod
    def calculate_adx(highs: List[float], lows: List[float], closes: List[float], 
                     period: int = 14) -> Optional[Dict[str, float]]:
        """
        Calcula ADX (Average Directional Index) para medir força da tendência.
        ADX varia de 0 a 100:
        - < 20: Tendência fraca ou range
        - 20-40: Tendência moderada
        - 40-60: Tendência forte
        - > 60: Tendência muito forte
        
        Args:
            highs: Lista de preços máximos
            lows: Lista de preços mínimos
            closes: Lista de preços de fechamento
            period: Período do ADX (padrão 14)
            
        Returns:
            Dict com adx, plus_di, minus_di ou None
        """
        n = len(closes)
        if n < period * 2:  # Precisa de dados suficientes
            return None
        
        highs_arr = np.array(highs, dtype=float)
        lows_arr = np.array(lows, dtype=float)
        closes_arr = np.array(closes, dtype=float)
        
        # Calcula True Range e Directional Movement
        tr = np.zeros(n)
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)
        
        for i in range(1, n):
            # True Range
            hl = highs_arr[i] - lows_arr[i]
            hc = abs(highs_arr[i] - closes_arr[i-1])
            lc = abs(lows_arr[i] - closes_arr[i-1])
            tr[i] = max(hl, hc, lc)
            
            # Directional Movement
            up_move = highs_arr[i] - highs_arr[i-1]
            down_move = lows_arr[i-1] - lows_arr[i]
            
            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move
        
        # Wilder's Smoothing (EMA-like)
        def wilder_smooth(arr, period):
            result = np.zeros(len(arr))
            result[period] = np.sum(arr[1:period+1])
            for i in range(period + 1, len(arr)):
                result[i] = result[i-1] - (result[i-1] / period) + arr[i]
            return result
        
        atr = wilder_smooth(tr, period)
        plus_dm_smooth = wilder_smooth(plus_dm, period)
        minus_dm_smooth = wilder_smooth(minus_dm, period)
        
        # +DI e -DI
        plus_di = np.zeros(n)
        minus_di = np.zeros(n)
        for i in range(period, n):
            if atr[i] > 0:
                plus_di[i] = 100 * plus_dm_smooth[i] / atr[i]
                minus_di[i] = 100 * minus_dm_smooth[i] / atr[i]
        
        # DX
        dx = np.zeros(n)
        for i in range(period, n):
            di_sum = plus_di[i] + minus_di[i]
            if di_sum > 0:
                dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum
        
        # ADX = Smoothed DX
        adx_arr = np.zeros(n)
        # Primeiro ADX é média simples dos DX
        if n > period * 2:
            adx_arr[period * 2 - 1] = np.mean(dx[period:period*2])
            for i in range(period * 2, n):
                adx_arr[i] = (adx_arr[i-1] * (period - 1) + dx[i]) / period
        
        # Retorna valores finais (clamped 0-100)
        final_adx = min(100, max(0, adx_arr[-1]))
        final_plus_di = min(100, max(0, plus_di[-1]))
        final_minus_di = min(100, max(0, minus_di[-1]))
        
        return {
            'adx': float(final_adx),
            'plus_di': float(final_plus_di),
            'minus_di': float(final_minus_di)
        }
    
    # ========================================================================
    # [Core Strategy] MACD - Moving Average Convergence Divergence
    # ========================================================================
    @staticmethod
    def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, 
                      signal: int = 9) -> Optional[Dict[str, float]]:
        """
        Calcula MACD (Moving Average Convergence Divergence).
        
        Args:
            prices: Lista de preços de fechamento
            fast: Período da EMA rápida (padrão 12)
            slow: Período da EMA lenta (padrão 26)
            signal: Período da linha de sinal (padrão 9)
            
        Returns:
            Dict com macd_line, signal_line, histogram ou None
        """
        if len(prices) < slow + signal:
            return None
        
        # Calcula EMAs
        ema_fast = TechnicalIndicators.calculate_ema(prices, fast)
        ema_slow = TechnicalIndicators.calculate_ema(prices, slow)
        
        if ema_fast is None or ema_slow is None:
            return None
        
        # MACD Line = EMA fast - EMA slow
        # Para calcular o signal line, precisamos do histórico do MACD
        macd_history = []
        for i in range(slow, len(prices) + 1):
            subset = prices[:i]
            ef = TechnicalIndicators.calculate_ema(subset, fast)
            es = TechnicalIndicators.calculate_ema(subset, slow)
            if ef and es:
                macd_history.append(ef - es)
        
        if len(macd_history) < signal:
            return None
        
        macd_line = macd_history[-1]
        
        # Signal Line = EMA do MACD
        signal_line = TechnicalIndicators.calculate_ema(macd_history, signal)
        
        if signal_line is None:
            return None
        
        histogram = macd_line - signal_line
        
        return {
            'macd_line': float(macd_line),
            'signal_line': float(signal_line),
            'histogram': float(histogram)
        }
    
    # ========================================================================
    # [Core Strategy] Stochastic RSI
    # ========================================================================
    @staticmethod
    def calculate_stoch_rsi(prices: List[float], rsi_period: int = 14, 
                           stoch_period: int = 14, k_period: int = 3, 
                           d_period: int = 3) -> Optional[Dict[str, float]]:
        """
        Calcula Stochastic RSI.
        
        Args:
            prices: Lista de preços de fechamento
            rsi_period: Período do RSI
            stoch_period: Período do Stochastic
            k_period: Período de suavização %K
            d_period: Período de suavização %D
            
        Returns:
            Dict com k, d ou None
        """
        if len(prices) < rsi_period + stoch_period + k_period:
            return None
        
        # Calcula série de RSI
        rsi_history = []
        for i in range(rsi_period + 1, len(prices) + 1):
            rsi = TechnicalIndicators.calculate_rsi(prices[:i], rsi_period)
            if rsi is not None:
                rsi_history.append(rsi)
        
        if len(rsi_history) < stoch_period:
            return None
        
        # Stochastic do RSI
        stoch_k_raw = []
        for i in range(stoch_period, len(rsi_history) + 1):
            window = rsi_history[i-stoch_period:i]
            min_rsi = min(window)
            max_rsi = max(window)
            if max_rsi - min_rsi > 0:
                k = 100 * (window[-1] - min_rsi) / (max_rsi - min_rsi)
            else:
                k = 50
            stoch_k_raw.append(k)
        
        if len(stoch_k_raw) < k_period:
            return None
        
        # Suavização %K
        k = np.mean(stoch_k_raw[-k_period:])
        
        # %D = SMA do %K
        if len(stoch_k_raw) >= d_period:
            d = np.mean(stoch_k_raw[-d_period:])
        else:
            d = k
        
        return {
            'k': float(k),
            'd': float(d)
        }
