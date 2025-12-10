"""
EMA Cross Analyzer - Multi-Timeframe Timing Intelligence
Analisa EMAs 9/26 em múltiplos timeframes (1D, 4h, 1h, 30m) para identificar alinhamento e timing.

PATCH v2.0:
- Removido 5m/15m - apenas 30m para cima
- Adicionado daily_trend_shift para detectar cruzamento no 1D
- Score de alinhamento prioriza 1D + 4h
- Novo campo allow_high_rsi_override para gestão defensiva
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
    # NOVO: Detecta shift de tendência no diário
    daily_trend_shift: Optional[Literal["bull", "bear"]] = None
    # NOVO: Flag para gestão defensiva quando RSI alto mas daily shift favorável
    allow_high_rsi_override: bool = False

def default_ema_config():
    """
    Configuração padrão - SOMENTE 30m para cima (nada de 5m/15m)
    """
    return {
        # SOMENTE 30m para cima – nada de 5m/15m
        "timeframes": ["1d", "4h", "1h", "30m"],
        "ema_fast": 9,
        "ema_slow": 26,
        "max_bars_lookback": 500,

        # Recência do cross por timeframe
        "fresh_cross_bars": {
            "1d": 3,    # cross diário recente ~últimos 3 candles
            "4h": 5,
            "1h": 8,
            "30m": 12,
        },

        # Overextension máxima do preço vs EMAs
        "max_price_distance_pct": {
            "1d": 8.0,   # diário pode tolerar mais distância
            "4h": 5.0,
            "1h": 4.0,
            "30m": 3.0,
        }
    }

class EMACrossAnalyzer:
    """
    Analisa EMAs 9/26 em múltiplos timeframes para fornecer inteligência de timing.
    
    PATCH v2.0:
    - Apenas timeframes 30m, 1h, 4h, 1d
    - Detecta daily_trend_shift para swing trades
    - Score de alinhamento prioriza timeframes maiores
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
        # Cooldown tracking
        self._cooldowns = {}

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
                    continue
                
                # Calcula estado
                state = self._calculate_state(symbol, tf, candles)
                if state:
                    states[tf] = state
            
            if not states:
                return None
                
            # Gera contexto agregado
            context = self._aggregate_context(symbol, states)
            
            # Log compacto
            self._log_analysis(context)
            
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
        ttls = {
            "1d": 600,   # 10 min cache para diário
            "4h": 300,   # 5 min cache
            "1h": 120,   # 2 min cache
            "30m": 60,   # 1 min cache
        }
        ttl = ttls.get(timeframe, 60)
        
        # 1. Verifica Cache
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if now - entry["timestamp"] < ttl:
                return entry["data"]
        
        # 2. Busca API
        try:
            candles = self.client.get_candles(symbol, interval=timeframe, limit=limit)
            
            if candles:
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
            
        # Calcula series EMA
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
        
        # Fresh Cross check - usando config por timeframe
        fresh_cross_bars = self.config.get("fresh_cross_bars", {})
        fresh_limit = fresh_cross_bars.get(timeframe, 5)
        is_fresh = False
        if bars_since is not None and bars_since <= fresh_limit:
            # Só é fresh se o cross for na direção da tendência atual
            if last_cross_dir == trend:
                is_fresh = True
                
        # Overextended Check - usando config por timeframe
        max_distance_pct = self.config.get("max_price_distance_pct", {})
        if isinstance(max_distance_pct, dict):
            max_dist = max_distance_pct.get(timeframe, 3.0)
        else:
            max_dist = max_distance_pct
            
        dist_pct = abs((current_price - current_slow) / current_slow) * 100
        is_extended = dist_pct > max_dist
        
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
        
        PATCH v2.0:
        - Novo scoring focado em 1D + 4h + 1h + 30m
        - Detecta daily_trend_shift
        - Mais peso para timeframes maiores
        """
        s1d = states.get("1d")
        s4h = states.get("4h")
        s1h = states.get("1h")
        s30m = states.get("30m")
        
        # Defaults
        bull_score = 0.0
        bear_score = 0.0
        daily_trend_shift = None
        
        # ===== DETECTAR DAILY TREND SHIFT =====
        if s1d:
            fresh_limit_1d = self.config.get("fresh_cross_bars", {}).get("1d", 3)
            if s1d.last_cross_direction == "bull" and s1d.bars_since_last_cross is not None:
                if s1d.bars_since_last_cross <= fresh_limit_1d:
                    daily_trend_shift = "bull"
            elif s1d.last_cross_direction == "bear" and s1d.bars_since_last_cross is not None:
                if s1d.bars_since_last_cross <= fresh_limit_1d:
                    daily_trend_shift = "bear"
        
        # ===== NOVO SCORING: Prioriza 1D + 4h =====
        
        # 1D e 4h na mesma direção → +0.4
        if s1d and s4h:
            if s1d.trend_direction == s4h.trend_direction and s1d.trend_direction != "flat":
                if s1d.trend_direction == "bull":
                    bull_score += 0.4
                else:
                    bear_score += 0.4
        
        # 4h e 1h na mesma direção → +0.3
        if s4h and s1h:
            if s4h.trend_direction == s1h.trend_direction and s4h.trend_direction != "flat":
                if s4h.trend_direction == "bull":
                    bull_score += 0.3
                else:
                    bear_score += 0.3
        
        # 1h e 30m na mesma direção → +0.2
        if s1h and s30m:
            if s1h.trend_direction == s30m.trend_direction and s1h.trend_direction != "flat":
                if s1h.trend_direction == "bull":
                    bull_score += 0.2
                else:
                    bear_score += 0.2
        
        # Fresh cross recente no maior timeframe relevante → +0.1
        for st in [s1d, s4h, s1h, s30m]:
            if st and st.is_fresh_cross:
                if st.last_cross_direction == "bull":
                    bull_score += 0.1
                elif st.last_cross_direction == "bear":
                    bear_score += 0.1
                break  # Só conta o maior
                
        # Penaliza Overextension (leve)
        for st in [s1h, s30m]:
            if st and st.is_overextended:
                bull_score *= 0.9
                bear_score *= 0.9
                
        # Determina melhor direção
        best_dir = None
        alignment_score = 0.0
        
        # Clamp em [0, 1]
        bull_score = min(1.0, max(0.0, bull_score))
        bear_score = min(1.0, max(0.0, bear_score))
        
        if bull_score > bear_score:
            alignment_score = bull_score
            if alignment_score > 0.3:
                best_dir = "long"
        elif bear_score > bull_score:
            alignment_score = bear_score
            if alignment_score > 0.3:
                best_dir = "short"
        
        # Flag para override de RSI alto quando daily shift favorável
        allow_high_rsi = False
        if daily_trend_shift and alignment_score >= 0.6:
            allow_high_rsi = True
        
        return EMAContext(
            symbol=symbol,
            states=states,
            alignment_score=alignment_score,
            has_bull_alignment=bull_score >= 0.6,
            has_bear_alignment=bear_score >= 0.6,
            best_direction=best_dir,
            daily_trend_shift=daily_trend_shift,
            allow_high_rsi_override=allow_high_rsi
        )

    def _log_analysis(self, ctx: EMAContext):
        """Log compacto para debug - PATCH v2.0"""
        s1d = ctx.states.get("1d")
        s4h = ctx.states.get("4h")
        s1h = ctx.states.get("1h")
        s30m = ctx.states.get("30m")
        
        def fmt(s): 
            if not s: return "N/A"
            cross_info = f"{s.bars_since_last_cross}b" if s.bars_since_last_cross is not None else "Old"
            fresh = "*" if s.is_fresh_cross else ""
            return f"{s.trend_direction.upper()}({cross_info}{fresh})"

        self.log.debug(
            f"[EMA] {ctx.symbol} 1d={fmt(s1d)} 4h={fmt(s4h)} 1h={fmt(s1h)} 30m={fmt(s30m)} "
            f"daily_shift={ctx.daily_trend_shift} score={ctx.alignment_score:.2f}"
        )

    def check_cooldown(self, symbol: str, timeframe: str, direction: str) -> bool:
        """
        Verifica se há cooldown ativo para este gatilho.
        Retorna True se estiver em cooldown (bloqueado), False se livre.
        """
        key = f"{symbol}_{timeframe}_{direction}"
        last_time = self._cooldowns.get(key, 0)
        
        import time
        now = time.time()
        
        # Configuração de cooldown em segundos
        # 30m * 6 barras = 180 min = 3h
        # 1h * 3 barras = 180 min = 3h
        # 4h * 2 barras = 480 min = 8h
        cooldown_duration = 0
        if timeframe == "30m": cooldown_duration = 30 * 60 * 6
        elif timeframe == "1h": cooldown_duration = 60 * 60 * 3
        elif timeframe == "4h": cooldown_duration = 4 * 60 * 60 * 2
        elif timeframe == "1d": cooldown_duration = 24 * 60 * 60  # 1 dia
        
        if now - last_time < cooldown_duration:
            return True
            
        return False

    def register_trigger(self, symbol: str, timeframe: str, direction: str):
        """Registra que um gatilho foi usado"""
        import time
        key = f"{symbol}_{timeframe}_{direction}"
        self._cooldowns[key] = time.time()

    def ema_timing_filter(self, 
                         mode: str, 
                         ema_context: EMAContext, 
                         proposed_direction: Literal["long", "short"], 
                         style: Literal["swing", "scalp"] = "swing") -> bool:
        """
        Aplica regras de timing baseadas no modo.
        Retorna True se aprovado, False se bloqueado.
        
        PATCH v2.0:
        - Não usa mais 5m/15m
        - Para SCALP, EMA é apenas consultivo (não bloqueia)
        - Para SWING, considera daily_trend_shift
        """
        if not ema_context:
            return True 
        
        # Extrai states
        s1d = ema_context.states.get("1d")
        s4h = ema_context.states.get("4h")
        s1h = ema_context.states.get("1h")
        s30m = ema_context.states.get("30m")
        
        # ===== SCALP: EMA apenas consultivo, não bloqueia =====
        if style == "scalp":
            return self._ema_timing_filter_scalp(mode, ema_context, proposed_direction, s4h, s1h, s30m)
        
        # ===== SWING: Regras por modo =====
        return self._ema_timing_filter_swing(mode, ema_context, proposed_direction, s1d, s4h, s1h, s30m)
    
    def _ema_timing_filter_scalp(self, mode: str, ema_context: EMAContext, 
                                  proposed_direction: str, s4h, s1h, s30m) -> bool:
        """
        Filtro EMA para SCALP - apenas consultivo.
        
        PATCH v2.0:
        - NÃO usa 5m/15m
        - Só evita operar TOTALMENTE contra tendência forte de 4h/1h
        - Para Balanceado/Agressivo, EMA é apenas orientação
        """
        # Só bloquear se estiver MUITO contra mesmo
        if ema_context.alignment_score < 0.2:
            # Determinar se está contra a direção proposta
            is_against = False
            if proposed_direction == "long":
                if s4h and s4h.trend_direction == "bear" and s1h and s1h.trend_direction == "bear":
                    is_against = True
            else:
                if s4h and s4h.trend_direction == "bull" and s1h and s1h.trend_direction == "bull":
                    is_against = True
            
            if is_against and mode == "CONSERVATIVE":
                self.log.info(f"[QUALITY GATE][EMA][SCALP] Bloqueando scalp contra alinhamento extremamente fraco.")
                return False
        
        # Para Balanceado/Agressivo, EMA é apenas orientação, não bloqueio duro
        self.log.debug(f"[QUALITY GATE][EMA][SCALP] EMA apenas consultivo (30m+); não bloqueando.")
        return True
    
    def _ema_timing_filter_swing(self, mode: str, ema_context: EMAContext,
                                  proposed_direction: str, s1d, s4h, s1h, s30m) -> bool:
        """
        Filtro EMA para SWING por modo.
        """
        # --- REGRAS CONSERVADOR ---
        if mode == "CONSERVATIVE":
            if ema_context.alignment_score < 0.7: 
                self.log.debug(f"[EMA FILTER] Bloqueado (CONSERVATIVE): Score < 0.7")
                return False
                
            if proposed_direction == "long":
                # 4h e 1h devem ser bull
                if not (s4h and s4h.trend_direction == "bull"): return False
                if not (s1h and s1h.trend_direction == "bull"): return False
                
                # 30m deve estar bull
                if not (s30m and s30m.trend_direction == "bull"): return False
                
                # Check Overextended
                if s1h and s1h.is_overextended: return False
                if s30m and s30m.is_overextended: return False

            else: # short
                if not (s4h and s4h.trend_direction == "bear"): return False
                if not (s1h and s1h.trend_direction == "bear"): return False
                if not (s30m and s30m.trend_direction == "bear"): return False
                
                if s1h and s1h.is_overextended: return False
                if s30m and s30m.is_overextended: return False
            
            return True

        # --- REGRAS BALANCEADO ---
        elif mode == "BALANCED":
            if ema_context.alignment_score < 0.5: return False
            
            if proposed_direction == "long":
                if s1h and s1h.trend_direction == "bear": return False
                if s4h and s4h.trend_direction == "bear": return False
                
                # Gatilho: 30m ou 1h bull
                has_trigger = (s30m and s30m.trend_direction == "bull") or \
                              (s1h and s1h.trend_direction == "bull")
                if not has_trigger: return False
                
            else: # short
                if s1h and s1h.trend_direction == "bull": return False
                if s4h and s4h.trend_direction == "bull": return False
                has_trigger = (s30m and s30m.trend_direction == "bear") or \
                              (s1h and s1h.trend_direction == "bear")
                if not has_trigger: return False

            return True

        # --- REGRAS AGRESSIVO ---
        elif mode == "AGGRESSIVE":
            # Permissivo, mas exige fresh cross se contra trend maior
            if proposed_direction == "long":
                if s1h and s1h.trend_direction == "bear":
                    # Se 1h é contra, precisa fresh cross no 30m
                    has_fresh = (s30m and s30m.is_fresh_cross and s30m.last_cross_direction == "bull")
                    if not has_fresh:
                        return False
            else:
                if s1h and s1h.trend_direction == "bull":
                     has_fresh = (s30m and s30m.is_fresh_cross and s30m.last_cross_direction == "bear")
                     if not has_fresh:
                        return False
            
            if ema_context.alignment_score < 0.3: return False
            return True
            
        return True
