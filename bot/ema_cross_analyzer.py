"""
EMA Cross Analyzer - Multi-Timeframe Timing Intelligence
Analisa EMAs 9/26 em múltiplos timeframes (4h, 1h, 15m, 5m) para identificar alinhamento e timing.
"""
import logging
import numpy as np
from typing import Dict, List, Optional, Literal
from dataclasses import dataclass
from bot.indicators import TechnicalIndicators

@dataclass
class EMATimeframeState:
    timeframe: str
    trend_direction: Literal["bull", "bear", "flat"]
    last_cross_direction: Optional[Literal["bull", "bear"]]
    bars_since_last_cross: Optional[int]
    is_fresh_cross: bool
    is_overextended: bool
    ema_fast: float
    ema_slow: float
    price: float

@dataclass
class EMAContext:
    symbol: str
    states: Dict[str, EMATimeframeState]
    alignment_score: float
    has_bull_alignment: bool
    has_bear_alignment: bool
    best_direction: Optional[Literal["long", "short"]]

def default_ema_config():
    return {
        "timeframes": ["4h", "1h", "15m", "5m"],
        "ema_fast": 9,
        "ema_slow": 26,
        "max_bars_lookback": 300,
        # Critérios de recência (barras desde o último X para ser "fresh")
        "fresh_cross_bars_4h": 3,
        "fresh_cross_bars_1h": 5,
        "fresh_cross_bars_15m": 8,
        "fresh_cross_bars_5m": 12,
        # Distância máxima do preço em relação às EMAs para não considerar 'overextended'
        "max_price_distance_pct": 3.0
    }

class EMACrossAnalyzer:
    """
    Analisa EMAs 9/26 em múltiplos timeframes para fornecer inteligência de timing.
    """
    
    def __init__(self, market_client, logger_instance=None, config=None):
        self.client = market_client
        self.log = logger_instance or logging.getLogger(__name__)
        self.config = config or default_ema_config()
        self.indicators = TechnicalIndicators()
        # Cache structure: { "symbol_timeframe": { "data": candles, "timestamp": ts } }
        self.cache = {}
        import time
        self._time = time

    def analyze_symbol(self, symbol: str, prefetched_candles: Optional[Dict[str, List]] = None) -> Optional[EMAContext]:
        """
        Analisa o símbolo em todos os timeframes configurados e gera o contexto.
        Args:
            symbol: Símbolo a analisar
            prefetched_candles: Dict opcional {timeframe: data} para economizar requests
        """
        states = {}
        import time
        
        try:
            for tf in self.config["timeframes"]:
                
                # Intra-symbol throttling para suavizar burst
                time.sleep(0.2)
                
                # Check pre-fetched first
                if prefetched_candles and tf in prefetched_candles:
                    candles = prefetched_candles[tf]
                else:
                    # Busca candles (agora com cache)
                    candles = self._fetch_candles(symbol, tf)
                
                if not candles:
                    # Log menos verboso se for erro recorrente
                    # self.log.warning(f"[EMA] Sem candles para {symbol} {tf}")
                    continue
                
                # Calcula estado
                state = self._calculate_state(symbol, tf, candles)
                if state:
                    states[tf] = state
            
            if not states:
                return None
                
            # Gera contexto agregado
            context = self._aggregate_context(symbol, states)
            
            # Log debug do resultado (reduzido para INFO apenas se mudar muito, ou DEBUG)
            # self._log_analysis(context)
            
            return context
            
        except Exception as e:
            self.log.error(f"[EMA] Erro ao analisar {symbol}: {e}")
            return None

    def _fetch_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Busca candles da exchange com cache para evitar 429"""
        limit = self.config["max_bars_lookback"]
        cache_key = f"{symbol}_{timeframe}"
        now = self._time.time()
        
        # TTL por timeframe para reduzir requests
        # 4h -> 5 min cache
        # 1h -> 2 min cache
        # 15m -> 1 min cache
        # 5m -> 30s cache
        ttls = {
            "4h": 300,
            "1h": 120,
            "15m": 60,
            "5m": 30
        }
        ttl = ttls.get(timeframe, 60)
        
        # 1. Verifica Cache
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if now - entry["timestamp"] < ttl:
                # Cache válido
                return entry["data"]
        
        # 2. Busca API
        try:
            # Assume que self.client tem get_candles(symbol, interval, limit)
            candles = self.client.get_candles(symbol, interval=timeframe, limit=limit)
            
            if candles:
                # Atualiza Cache
                self.cache[cache_key] = {
                    "data": candles,
                    "timestamp": now
                }
                return candles
                
            return []
            
        except Exception as e:
            # Em caso de erro (ex: 429), tenta usar cache antigo se existir
            if cache_key in self.cache:
                self.log.warning(f"[EMA] Erro API {e}, usando cache antigo para {symbol} {timeframe}")
                return self.cache[cache_key]["data"]
                
            self.log.debug(f"[EMA] Falha ao buscar candles {symbol} {timeframe}: {e}")
            return []

    def _calculate_state(self, symbol: str, timeframe: str, candles: List[Dict]) -> Optional[EMATimeframeState]:
        """Calcula estado das EMAs para um timeframe"""
        closes = [float(c.get('c') or c.get('close')) for c in candles]
        current_price = closes[-1]
        
        ema_fast_period = self.config["ema_fast"]
        ema_slow_period = self.config["ema_slow"]
        
        # Precisa de dados suficientes
        if len(closes) < ema_slow_period + 5:
            return None
            
        # Calcula series EMA (usando numpy para eficiência se possível, ou loop)
        # TechnicalIndicators.calculate_ema devolve float único atual.
        # Precisamos da série histórica para achar o cruzamento.
        
        ema_fast_series = self._calculate_ema_series(closes, ema_fast_period)
        ema_slow_series = self._calculate_ema_series(closes, ema_slow_period)
        
        current_fast = ema_fast_series[-1]
        current_slow = ema_slow_series[-1]
        
        # Direção
        if current_fast > current_slow:
            trend = "bull"
        elif current_fast < current_slow:
            trend = "bear"
        else:
            trend = "flat"
            
        # Encontrar último cruzamento
        last_cross_dir = None
        bars_since = None
        
        # Itera de trás pra frente
        for i in range(len(ema_fast_series) - 2, 0, -1):
            prev_fast = ema_fast_series[i]
            prev_slow = ema_slow_series[i]
            
            curr_fast_i = ema_fast_series[i+1]
            curr_slow_i = ema_slow_series[i+1]
            
            # Bullish Cross (Fast cruza Slow pra cima)
            if prev_fast <= prev_slow and curr_fast_i > curr_slow_i:
                last_cross_dir = "bull"
                bars_since = (len(ema_fast_series) - 1) - (i + 1)
                break
                
            # Bearish Cross (Fast cruza Slow pra baixo)
            if prev_fast >= prev_slow and curr_fast_i < curr_slow_i:
                last_cross_dir = "bear"
                bars_since = (len(ema_fast_series) - 1) - (i + 1)
                break
        
        # Fresh Cross check
        fresh_limit = self.config.get(f"fresh_cross_bars_{timeframe}", 5)
        is_fresh = False
        if bars_since is not None and bars_since <= fresh_limit:
            # Só é fresh se o cross for na direção da tendência atual
            if last_cross_dir == trend:
                is_fresh = True
                
        # Overextended Check
        # Distância % do preço para EMA21 (slow)
        dist_pct = abs((current_price - current_slow) / current_slow) * 100
        is_extended = dist_pct > self.config["max_price_distance_pct"]
        
        return EMATimeframeState(
            timeframe=timeframe,
            trend_direction=trend,
            last_cross_direction=last_cross_dir,
            bars_since_last_cross=bars_since,
            is_fresh_cross=is_fresh,
            is_overextended=is_extended,
            ema_fast=current_fast,
            ema_slow=current_slow,
            price=current_price
        )

    def _calculate_ema_series(self, prices: List[float], period: int) -> np.ndarray:
        """Calcula série completa de EMA"""
        prices_arr = np.array(prices)
        ema = np.zeros_like(prices_arr)
        multiplier = 2 / (period + 1)
        
        # SMA inicial
        ema[period-1] = np.mean(prices_arr[:period])
        
        # EMA restante
        for i in range(period, len(prices_arr)):
            ema[i] = (prices_arr[i] - ema[i-1]) * multiplier + ema[i-1]
            
        return ema

    def _aggregate_context(self, symbol: str, states: Dict[str, EMATimeframeState]) -> EMAContext:
        """
        Analisa alinhamento entre timeframes e gera score.
        """
        s4h = states.get("4h")
        s1h = states.get("1h")
        s15m = states.get("15m")
        s5m = states.get("5m")
        
        # Defaults
        bull_score = 0.0
        bear_score = 0.0
        
        # Lógica de Pontuação BULL
        if s4h and s4h.trend_direction == "bull":
            bull_score += 0.3
        if s1h and s1h.trend_direction == "bull":
            bull_score += 0.3
        if s15m:
            if s15m.trend_direction == "bull":
                bull_score += 0.2
            if s15m.last_cross_direction == "bull" and s15m.is_fresh_cross:
                bull_score += 0.2  # Bônus por fresh cross
        if s5m and s5m.trend_direction == "bull" and s5m.is_fresh_cross:
                bull_score += 0.1
                
        # Lógica de Pontuação BEAR
        if s4h and s4h.trend_direction == "bear":
            bear_score += 0.3
        if s1h and s1h.trend_direction == "bear":
            bear_score += 0.3
        if s15m:
            if s15m.trend_direction == "bear":
                bear_score += 0.2
            if s15m.last_cross_direction == "bear" and s15m.is_fresh_cross:
                bear_score += 0.2
        if s5m and s5m.trend_direction == "bear" and s5m.is_fresh_cross:
                bear_score += 0.1
                
        # Penaliza Overextension
        for st in [s15m, s1h]:
            if st and st.is_overextended:
                bull_score *= 0.8
                bear_score *= 0.8
                
        # Determina melhor direção
        best_dir = None
        alignment_score = 0.0
        
        if bull_score > bear_score:
            alignment_score = min(1.0, bull_score)
            if alignment_score > 0.4:
                best_dir = "long"
        elif bear_score > bull_score:
            alignment_score = min(1.0, bear_score)
            if alignment_score > 0.4:
                best_dir = "short"
        
        return EMAContext(
            symbol=symbol,
            states=states,
            alignment_score=alignment_score,
            has_bull_alignment=bull_score >= 0.6,
            has_bear_alignment=bear_score >= 0.6,
            best_direction=best_dir
        )

    def _log_analysis(self, ctx: EMAContext):
        """Log compacto para debug"""
        s4h = ctx.states.get("4h")
        s1h = ctx.states.get("1h")
        s15m = ctx.states.get("15m")
        s5m = ctx.states.get("5m")
        
        def fmt(s): 
            if not s: return "N/A"
            cross_info = f"{s.bars_since_last_cross}b" if s.bars_since_last_cross is not None else "Old"
            fresh = "*" if s.is_fresh_cross else ""
            return f"{s.trend_direction.upper()}({cross_info}{fresh})"

        self.log.debug(
            f"[EMA] {ctx.symbol} | Score: {ctx.alignment_score:.2f} ({ctx.best_direction or 'None'}) | "
            f"4h={fmt(s4h)} 1h={fmt(s1h)} 15m={fmt(s15m)} 5m={fmt(s5m)}"
        )

    def ema_timing_filter(self, 
                         mode: str, 
                         ema_context: EMAContext, 
                         proposed_direction: Literal["long", "short"], 
                         style: Literal["swing", "scalp"] = "swing") -> bool:
        """
        Aplica regras de timing baseadas no modo.
        Retorna True se aprovado, False se bloqueado.
        """
        if not ema_context:
            return True # Fail open se não tiver dados (safety fallback) ou False (strict)? 
                        # Vamos usar True mas logar warning, para não travar o bot por falta de dados 4h
        
        # Extrai states
        s4h = ema_context.states.get("4h")
        s1h = ema_context.states.get("1h")
        s15m = ema_context.states.get("15m")
        s5m = ema_context.states.get("5m")
        
        # --- REGRAS CONSERVADOR ---
        if mode == "CONSERVATIVE":
            # Exige alinhamento forte
            if proposed_direction == "long":
                # 4h e 1h devem ser bull
                if not (s4h and s4h.trend_direction == "bull"): return False
                if not (s1h and s1h.trend_direction == "bull"): return False
                # 15m ou 5m deve ter fresh cross ou estar bull forte
                if not (s15m and s15m.trend_direction == "bull"): return False
            else: # short
                if not (s4h and s4h.trend_direction == "bear"): return False
                if not (s1h and s1h.trend_direction == "bear"): return False
                if not (s15m and s15m.trend_direction == "bear"): return False
                
            # Score alto
            if ema_context.alignment_score < 0.7: return False
            
            return True

        # --- REGRAS BALANCEADO ---
        elif mode == "BALANCED":
            # 1h favorável, 4h neutro ou favorável
            if proposed_direction == "long":
                if s1h and s1h.trend_direction == "bear": return False # Contra 1h não
                if s4h and s4h.trend_direction == "bear": return False # Contra 4h não (pode ser flat)
                
                # Gatilho: 15m ou 5m deve estar favorável
                has_trigger = (s15m and s15m.trend_direction == "bull") or \
                              (s5m and s5m.trend_direction == "bull")
                if not has_trigger: return False
                
            else: # short
                if s1h and s1h.trend_direction == "bull": return False
                if s4h and s4h.trend_direction == "bull": return False
                has_trigger = (s15m and s15m.trend_direction == "bear") or \
                              (s5m and s5m.trend_direction == "bear")
                if not has_trigger: return False

            if ema_context.alignment_score < 0.5: return False
            return True

        # --- REGRAS AGRESSIVO ---
        elif mode == "AGGRESSIVE":
            # Permite operar contra 4h se tiver setup claro em LTF (reversão/scalp)
            if proposed_direction == "long":
                # Apenas exige que não esteja em queda livre no 15m sem sinal de reversão
                if s15m and s15m.trend_direction == "bear" and not s15m.is_fresh_cross:
                    # Se 15m é bear e não acabou de cruzar pra cima, precisamos do 5m bull strong
                    if not (s5m and s5m.trend_direction == "bull" and s5m.is_fresh_cross):
                        return False
            else:
                 if s15m and s15m.trend_direction == "bull" and not s15m.is_fresh_cross:
                    if not (s5m and s5m.trend_direction == "bear" and s5m.is_fresh_cross):
                        return False
            
            # Score mínimo baixo
            if ema_context.alignment_score < 0.3: return False
            return True
            
        return True
