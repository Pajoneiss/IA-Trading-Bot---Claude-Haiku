"""
Market Context Builder
Coleta e organiza dados de mercado da Hyperliquid
"""
import logging
from typing import Dict, List, Optional, Any
from .indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class MarketContext:
    """Constrói contexto de mercado completo para decisão"""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
    
    def build_context_for_pair(self, 
                               symbol: str,
                               current_price: float,
                               candles: List[Dict[str, Any]],
                               funding_rate: Optional[float] = None,
                               volume_24h: Optional[float] = None,
                               open_interest: Optional[float] = None) -> Dict[str, Any]:
        """
        Constrói contexto completo para um par
        
        Args:
            symbol: Par de trading (ex: BTCUSDC)
            current_price: Preço atual
            candles: Lista de candles OHLCV (dicts com t, o, h, l, c, v)
            funding_rate: Taxa de funding atual
            volume_24h: Volume 24h
            open_interest: Open Interest
            
        Returns:
            Dict com contexto completo do par
        """
        if not candles or len(candles) < 2:
            logger.warning(f"{symbol}: Dados insuficientes de candles")
            return self._empty_context(symbol, current_price)
        
        # Extrai dados dos candles
        closes = [float(c.get('c', 0)) for c in candles]
        highs = [float(c.get('h', 0)) for c in candles]
        lows = [float(c.get('l', 0)) for c in candles]
        volumes = [float(c.get('v', 0)) for c in candles]
        
        # Calcula variação 24h
        if len(closes) >= 2:
            price_24h_ago = closes[0]
            price_change_24h = ((current_price - price_24h_ago) / price_24h_ago) * 100
        else:
            price_change_24h = 0.0
        
        # Calcula indicadores
        ema_9 = self.indicators.calculate_ema(closes, 9)
        ema_21 = self.indicators.calculate_ema(closes, 21)
        rsi = self.indicators.calculate_rsi(closes, 14)
        atr = self.indicators.calculate_atr(highs, lows, closes, 14)
        bb_bands = self.indicators.calculate_bb_bands(closes, 20, 2.0)
        trend_info = self.indicators.detect_trend(closes, 9, 21)
        volatility = self.indicators.calculate_volatility(closes, 20)
        
        # Volume médio
        avg_volume = sum(volumes[-20:]) / min(20, len(volumes)) if volumes else 0
        
        # Monta contexto
        context = {
            'symbol': symbol,
            'price': current_price,
            'price_change_24h_pct': round(price_change_24h, 2),
            'funding_rate': funding_rate,
            'volume_24h': volume_24h,
            'avg_volume_20': round(avg_volume, 2),
            'open_interest': open_interest,
            'indicators': {
                'ema_9': round(ema_9, 2) if ema_9 else None,
                'ema_21': round(ema_21, 2) if ema_21 else None,
                'rsi': round(rsi, 1) if rsi else None,
                'atr': round(atr, 4) if atr else None,
                'bb_upper': round(bb_bands['upper'], 2) if bb_bands else None,
                'bb_middle': round(bb_bands['middle'], 2) if bb_bands else None,
                'bb_lower': round(bb_bands['lower'], 2) if bb_bands else None,
                'volatility_pct': round(volatility, 2) if volatility else None,
                'distance_from_ema21_pct': round(((current_price - ema_21) / ema_21) * 100, 2) if ema_21 else 0.0
            },
            'trend': {
                'direction': trend_info['trend'],
                'strength': round(trend_info['strength'], 2),
                'is_extended': abs(((current_price - ema_21) / ema_21) * 100) > 2.5 if ema_21 else False
            },
            'candles_count': len(candles)
        }
        
        return context
    
    def _empty_context(self, symbol: str, price: float) -> Dict[str, Any]:
        """Retorna contexto vazio quando dados são insuficientes"""
        return {
            'symbol': symbol,
            'price': price,
            'price_change_24h_pct': 0.0,
            'funding_rate': None,
            'volume_24h': None,
            'avg_volume_20': 0.0,
            'open_interest': None,
            'indicators': {
                'ema_9': None,
                'ema_21': None,
                'rsi': None,
                'atr': None,
                'bb_upper': None,
                'bb_middle': None,
                'bb_lower': None,
                'volatility_pct': None
            },
            'trend': {
                'direction': 'neutral',
                'strength': 0.0
            },
            'candles_count': 0
        }
    
    def summarize_for_ai(self, contexts: List[Dict[str, Any]]) -> str:
        """
        Cria resumo textual dos contextos para enviar à IA
        
        Args:
            contexts: Lista de contextos de pares
            
        Returns:
            String formatada com resumo
        """
        summary_lines = ["=== CONTEXTO DE MERCADO ===\n"]
        
        for ctx in contexts:
            symbol = ctx['symbol']
            price = ctx['price']
            change = ctx['price_change_24h_pct']
            trend = ctx['trend']['direction']
            strength = ctx['trend']['strength']
            
            ind = ctx['indicators']
            rsi = ind.get('rsi')
            ema9 = ind.get('ema_9')
            ema21 = ind.get('ema_21')
            vol = ind.get('volatility_pct')
            
            summary_lines.append(f"\n{symbol}:")
            summary_lines.append(f"  Preço: ${price:,.2f} ({change:+.2f}% 24h)")
            summary_lines.append(f"  Tendência: {trend.upper()} (força: {strength:.2f})")
            
            if rsi:
                rsi_status = "sobrecomprado" if rsi > 70 else "sobrevendido" if rsi < 30 else "neutro"
                summary_lines.append(f"  RSI: {rsi:.1f} ({rsi_status})")
            
            if ema9 and ema21:
                ema_cross = "acima" if ema9 > ema21 else "abaixo"
                summary_lines.append(f"  EMAs: 9={ema9:.2f} está {ema_cross} de 21={ema21:.2f}")
            
            if vol:
                vol_status = "alta" if vol > 3 else "média" if vol > 1.5 else "baixa"
                summary_lines.append(f"  Volatilidade: {vol:.2f}% ({vol_status})")
            
            if ctx.get('funding_rate'):
                summary_lines.append(f"  Funding: {ctx['funding_rate']:.4f}%")
            
            # Anti-Chasing Warning
            dist_ema21 = ind.get('distance_from_ema21_pct', 0)
            if abs(dist_ema21) > 2.5:
                summary_lines.append(f"  ⚠️ PREÇO ESTICADO: {dist_ema21:+.2f}% da EMA21 (Cuidado com Chasing!)")
        
        return "\n".join(summary_lines)
