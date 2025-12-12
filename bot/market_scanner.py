"""
Market Scanner - Detecção de Oportunidades sem IA

PATCH v3.0:
- Varre mercado e gera triggers de atenção para SWING e SCALP
- NÃO usa IA - apenas dados locais (EMAs, regime, preços)
- Triggers passam pelo AI Budget antes de chamar IA
- Integra com EMA Cross Analyzer e Market Regime
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScanTrigger:
    """Trigger de oportunidade detectado pelo scanner"""
    symbol: str
    timeframe: str
    direction_hint: Optional[Literal["long", "short"]]  # Direção sugerida ou None
    trigger_type: str  # "DAILY_EMA_SHIFT", "REGIME_CHANGE", "STRONG_MOVE", etc.
    details: str  # Texto curto para log
    priority: int = 1  # 1 = alta, 2 = média, 3 = baixa
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class MarketScanner:
    """
    Scanner de Mercado - Camada 1 (sem IA)
    
    Detecta condições interessantes que merecem análise de IA:
    - SWING: Mudanças de tendência no diário, mudanças de regime, movimentos fortes
    - SCALP: Pullbacks em tendência, rompimentos, movimentos explosivos
    
    NÃO toma decisões - apenas gera triggers para avaliação posterior.
    """
    
    CONFIG_FILE = "data/ai_budget_config.json"
    
    def __init__(self, 
                 ema_analyzer=None, 
                 regime_analyzer=None,
                 market_client=None,
                 logger_instance=None):
        """
        Inicializa o scanner
        
        Args:
            ema_analyzer: Instância do EMACrossAnalyzer
            regime_analyzer: Instância do MarketRegimeAnalyzer
            market_client: Cliente para buscar dados (candles, preços)
            logger_instance: Logger opcional
        """
        self.log = logger_instance or logger
        self.ema_analyzer = ema_analyzer
        self.regime_analyzer = regime_analyzer
        self.client = market_client
        
        # Carrega config
        self.config = self._load_config()
        
        # Símbolos a monitorar
        self.swing_symbols = self.config.get("swing", {}).get("symbols", ["BTC", "ETH"])
        self.scalp_symbols = self.config.get("scalp", {}).get("symbols", ["BTC", "ETH", "SOL"])
        
        # Timeframes
        self.swing_timeframes = self.config.get("swing", {}).get("timeframes", ["1d", "4h", "1h"])
        self.scalp_timeframes = self.config.get("scalp", {}).get("timeframes", ["4h", "1h", "30m"])
        
        # [PATCH] Flag para habilitar DAILY_EMA_SHIFT como trigger (default: DESATIVADO)
        # O 1D deve ser FILTRO macro, não gatilho direto para IA
        self.enable_daily_ema_shift = self.config.get("swing", {}).get("enable_daily_ema_shift", False)
        
        # Parâmetros do scanner
        scanner_cfg = self.config.get("scanner", {})
        self.strong_move_atr_mult = scanner_cfg.get("strong_move_atr_multiplier", 1.5)
        self.pullback_ema_dist_pct = scanner_cfg.get("pullback_ema_distance_pct", 1.5)
        self.range_lookback = scanner_cfg.get("range_lookback_bars", 20)
        
        max_triggers = scanner_cfg.get("max_triggers_per_iteration", {})
        self.max_swing_triggers = max_triggers.get("swing", 3)
        self.max_scalp_triggers = max_triggers.get("scalp", 5)
        
        # Cache de estados anteriores para detectar mudanças
        self._last_daily_shifts: Dict[str, Optional[str]] = {}
        self._last_regimes: Dict[str, str] = {}
        
        self.log.info(f"[SCANNER] Inicializado: swing={self.swing_symbols}, scalp={self.scalp_symbols}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Carrega configuração"""
        try:
            config_path = Path(self.CONFIG_FILE)
            if config_path.exists():
                with open(config_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.log.error(f"[SCANNER] Erro ao carregar config: {e}")
        return {}
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normaliza símbolo removendo sufixos"""
        return symbol.replace("USDC", "").replace("USDT", "").replace("USD", "")
    
    def _get_full_symbol(self, symbol: str, trading_pairs: List[str]) -> Optional[str]:
        """Encontra símbolo completo na lista de pares"""
        for pair in trading_pairs:
            if pair.startswith(symbol):
                return pair
        return None
    
    # ==================== SWING SCANNER ====================
    
    def scan_swing_opportunities(self, 
                                  market_contexts: List[Dict],
                                  ema_contexts: Dict[str, Any] = None,
                                  regime_info: Dict[str, Dict] = None) -> List[ScanTrigger]:
        """
        Varre mercado buscando oportunidades de SWING
        
        Args:
            market_contexts: Lista de contextos de mercado por símbolo
            ema_contexts: Dict {symbol: EMAContext} do EMA Analyzer
            regime_info: Dict {symbol: regime_dict} do Market Regime
            
        Returns:
            Lista de ScanTrigger ordenada por prioridade
        """
        triggers = []
        ema_contexts = ema_contexts or {}
        regime_info = regime_info or {}
        
        for ctx in market_contexts:
            symbol = ctx.get('symbol', '')
            symbol_clean = self._normalize_symbol(symbol)
            
            # Filtra apenas símbolos de swing
            if symbol_clean not in self.swing_symbols:
                continue
            
            try:
                # 1. DAILY EMA SHIFT (desativado por default - 1D é filtro, não gatilho)
                # Só dispara se enable_daily_ema_shift=true na config
                if self.enable_daily_ema_shift:
                    trigger = self._check_daily_ema_shift(symbol, ema_contexts.get(symbol))
                    if trigger:
                        triggers.append(trigger)
                
                # 2. REGIME CHANGE (prioridade alta)
                trigger = self._check_regime_change(symbol, regime_info.get(symbol))
                if trigger:
                    triggers.append(trigger)
                
                # 3. STRONG MOVE (prioridade média)
                trigger = self._check_strong_move(symbol, ctx, "swing")
                if trigger:
                    triggers.append(trigger)
                
                # 4. KEY LEVEL TOUCH (prioridade média)
                trigger = self._check_key_level(symbol, ctx)
                if trigger:
                    triggers.append(trigger)
                
            except Exception as e:
                self.log.error(f"[SCANNER][SWING] Erro ao analisar {symbol}: {e}")
        
        # Ordena por prioridade e limita
        triggers.sort(key=lambda t: t.priority)
        triggers = triggers[:self.max_swing_triggers]
        
        # Log triggers encontrados
        for t in triggers:
            self.log.info(
                f"[SCANNER][SWING] {t.symbol} {t.timeframe} {t.trigger_type} "
                f"dir={t.direction_hint} | {t.details}"
            )
        
        return triggers
    
    def _check_daily_ema_shift(self, symbol: str, ema_ctx) -> Optional[ScanTrigger]:
        """
        Verifica se houve mudança de tendência no diário (EMA 9/26 cross)
        
        NOTA: Esta função NÃO é mais usada por default (enable_daily_ema_shift=false).
        O 1D deve ser usado como FILTRO macro (clima), não como gatilho direto para IA.
        Triggers prioritários são: REGIME_CHANGE, STRONG_MOVE, KEY_LEVEL_TOUCH.
        
        Para reativar, setar "enable_daily_ema_shift": true em data/ai_budget_config.json
        """
        if not ema_ctx:
            return None
        
        # Pega daily_trend_shift do EMAContext (patch v2.0)
        daily_shift = getattr(ema_ctx, 'daily_trend_shift', None)
        
        if not daily_shift:
            return None
        
        # Verifica se é NOVO (não o mesmo do último scan)
        last_shift = self._last_daily_shifts.get(symbol)
        if daily_shift == last_shift:
            return None  # Já vimos esse shift
        
        # Atualiza cache
        self._last_daily_shifts[symbol] = daily_shift
        
        direction = "long" if daily_shift == "bull" else "short"
        alignment = getattr(ema_ctx, 'alignment_score', 0)
        
        return ScanTrigger(
            symbol=symbol,
            timeframe="1d",
            direction_hint=direction,
            trigger_type="DAILY_EMA_SHIFT",
            details=f"EMA 9/26 cross {daily_shift} no diário (score={alignment:.2f})",
            priority=1  # Alta prioridade
        )
    
    def _check_regime_change(self, symbol: str, regime_data: Dict) -> Optional[ScanTrigger]:
        """
        Verifica se houve mudança de regime de mercado
        """
        if not regime_data:
            return None
        
        current_regime = regime_data.get('regime', 'UNKNOWN')
        last_regime = self._last_regimes.get(symbol, 'UNKNOWN')
        
        # Mudanças relevantes
        significant_changes = [
            ('RANGE_CHOP', 'TREND_BULL'),
            ('RANGE_CHOP', 'TREND_BEAR'),
            ('LOW_VOL_DRIFT', 'TREND_BULL'),
            ('LOW_VOL_DRIFT', 'TREND_BEAR'),
            ('LOW_VOL_DRIFT', 'PANIC_HIGH_VOL'),
            ('TREND_BULL', 'PANIC_HIGH_VOL'),
            ('TREND_BEAR', 'PANIC_HIGH_VOL'),
        ]
        
        # Verifica se é mudança significativa
        is_significant = (last_regime, current_regime) in significant_changes
        
        if not is_significant:
            # Atualiza cache mesmo se não significativo
            self._last_regimes[symbol] = current_regime
            return None
        
        # Atualiza cache
        self._last_regimes[symbol] = current_regime
        
        # Determina direção baseada no novo regime
        direction = None
        if current_regime == 'TREND_BULL':
            direction = 'long'
        elif current_regime == 'TREND_BEAR':
            direction = 'short'
        
        return ScanTrigger(
            symbol=symbol,
            timeframe="4h",
            direction_hint=direction,
            trigger_type="REGIME_CHANGE",
            details=f"Regime mudou: {last_regime} → {current_regime}",
            priority=1
        )
    
    def _check_strong_move(self, symbol: str, ctx: Dict, style: str) -> Optional[ScanTrigger]:
        """
        Verifica se houve movimento forte (candle muito maior que média)
        """
        candles = ctx.get('candles', [])
        if not candles or len(candles) < 10:
            return None
        
        try:
            # Calcula range médio dos últimos N candles
            ranges = []
            for c in candles[-20:]:
                high = float(c.get('h') or c.get('high', 0))
                low = float(c.get('l') or c.get('low', 0))
                if high > 0 and low > 0:
                    ranges.append(high - low)
            
            if not ranges:
                return None
            
            avg_range = sum(ranges) / len(ranges)
            
            # Range do último candle
            last = candles[-1]
            last_high = float(last.get('h') or last.get('high', 0))
            last_low = float(last.get('l') or last.get('low', 0))
            last_range = last_high - last_low
            
            # Verifica se é movimento forte
            if last_range < avg_range * self.strong_move_atr_mult:
                return None
            
            # Determina direção pelo corpo da vela
            last_open = float(last.get('o') or last.get('open', 0))
            last_close = float(last.get('c') or last.get('close', 0))
            
            direction = "long" if last_close > last_open else "short"
            timeframe = "1d" if style == "swing" else "1h"
            
            return ScanTrigger(
                symbol=symbol,
                timeframe=timeframe,
                direction_hint=direction,
                trigger_type="STRONG_MOVE",
                details=f"Range {last_range:.2f} = {last_range/avg_range:.1f}x média",
                priority=2
            )
            
        except Exception as e:
            self.log.debug(f"[SCANNER] Erro em strong_move {symbol}: {e}")
            return None
    
    def _check_key_level(self, symbol: str, ctx: Dict) -> Optional[ScanTrigger]:
        """
        Verifica se preço está em nível importante (suporte/resistência)
        """
        # Usa dados de phase2 se disponível
        phase2 = ctx.get('phase2', {})
        liquidity = phase2.get('liquidity', {})
        
        if not liquidity:
            return None
        
        current_price = ctx.get('current_price', 0)
        if not current_price:
            return None
        
        # Verifica proximidade de níveis
        support = liquidity.get('support')
        resistance = liquidity.get('resistance')
        
        proximity_pct = 0.5  # 0.5% de distância
        
        if support:
            dist_pct = abs(current_price - support) / current_price * 100
            if dist_pct <= proximity_pct:
                return ScanTrigger(
                    symbol=symbol,
                    timeframe="4h",
                    direction_hint="long",
                    trigger_type="KEY_LEVEL_TOUCH",
                    details=f"Preço próximo ao suporte ${support:.2f} ({dist_pct:.2f}%)",
                    priority=2
                )
        
        if resistance:
            dist_pct = abs(current_price - resistance) / current_price * 100
            if dist_pct <= proximity_pct:
                return ScanTrigger(
                    symbol=symbol,
                    timeframe="4h",
                    direction_hint="short",
                    trigger_type="KEY_LEVEL_TOUCH",
                    details=f"Preço próximo à resistência ${resistance:.2f} ({dist_pct:.2f}%)",
                    priority=2
                )
        
        return None
    
    # ==================== SCALP SCANNER ====================
    
    def scan_scalp_opportunities(self,
                                  market_contexts: List[Dict],
                                  ema_contexts: Dict[str, Any] = None) -> List[ScanTrigger]:
        """
        Varre mercado buscando oportunidades de SCALP
        
        Args:
            market_contexts: Lista de contextos de mercado
            ema_contexts: Dict {symbol: EMAContext}
            
        Returns:
            Lista de ScanTrigger ordenada por prioridade
        """
        triggers = []
        ema_contexts = ema_contexts or {}
        
        for ctx in market_contexts:
            symbol = ctx.get('symbol', '')
            symbol_clean = self._normalize_symbol(symbol)
            
            # Filtra apenas símbolos de scalp
            if symbol_clean not in self.scalp_symbols:
                continue
            
            try:
                # 1. PULLBACK EM TENDÊNCIA (prioridade alta)
                trigger = self._check_pullback_ema(symbol, ctx, ema_contexts.get(symbol))
                if trigger:
                    triggers.append(trigger)
                
                # 2. RANGE BREAKOUT (prioridade alta)
                trigger = self._check_range_breakout(symbol, ctx)
                if trigger:
                    triggers.append(trigger)
                
                # 3. STRONG MOVE SCALP (prioridade média)
                trigger = self._check_strong_move(symbol, ctx, "scalp")
                if trigger:
                    triggers.append(trigger)
                
            except Exception as e:
                self.log.error(f"[SCANNER][SCALP] Erro ao analisar {symbol}: {e}")
        
        # Ordena e limita
        triggers.sort(key=lambda t: t.priority)
        triggers = triggers[:self.max_scalp_triggers]
        
        # Log
        for t in triggers:
            self.log.info(
                f"[SCANNER][SCALP] {t.symbol} {t.timeframe} {t.trigger_type} "
                f"dir={t.direction_hint} | {t.details}"
            )
        
        return triggers
    
    def _check_pullback_ema(self, symbol: str, ctx: Dict, ema_ctx) -> Optional[ScanTrigger]:
        """
        Verifica pullback em tendência forte (preço voltando às EMAs)
        """
        if not ema_ctx:
            return None
        
        # Verifica se está em tendência forte (alinhamento alto)
        alignment = getattr(ema_ctx, 'alignment_score', 0)
        best_dir = getattr(ema_ctx, 'best_direction', None)
        
        if alignment < 0.6 or not best_dir:
            return None  # Não está em tendência clara
        
        # Verifica distância do preço às EMAs
        states = getattr(ema_ctx, 'states', {})
        s1h = states.get('1h')
        
        if not s1h:
            return None
        
        current_price = ctx.get('current_price', 0)
        ema_slow = getattr(s1h, 'ema_slow', 0)
        
        if not current_price or not ema_slow:
            return None
        
        # Calcula distância percentual
        dist_pct = ((current_price - ema_slow) / ema_slow) * 100
        
        # Pullback: preço perto da EMA na direção da tendência
        # Long: preço caiu até perto da EMA (dist pequeno ou levemente negativo)
        # Short: preço subiu até perto da EMA (dist pequeno ou levemente positivo)
        
        is_pullback = False
        if best_dir == 'long' and -self.pullback_ema_dist_pct <= dist_pct <= self.pullback_ema_dist_pct:
            is_pullback = True
        elif best_dir == 'short' and -self.pullback_ema_dist_pct <= dist_pct <= self.pullback_ema_dist_pct:
            is_pullback = True
        
        if not is_pullback:
            return None
        
        return ScanTrigger(
            symbol=symbol,
            timeframe="1h",
            direction_hint=best_dir,
            trigger_type="PULLBACK_EMA",
            details=f"Pullback {best_dir} com dist={dist_pct:.2f}% da EMA26 (align={alignment:.2f})",
            priority=1
        )
    
    def _check_range_breakout(self, symbol: str, ctx: Dict) -> Optional[ScanTrigger]:
        """
        Verifica rompimento de range/consolidação
        """
        candles = ctx.get('candles', [])
        if not candles or len(candles) < self.range_lookback + 1:
            return None
        
        try:
            # Calcula high/low do range (excluindo último candle)
            lookback = candles[-(self.range_lookback + 1):-1]
            
            range_high = max(float(c.get('h') or c.get('high', 0)) for c in lookback)
            range_low = min(float(c.get('l') or c.get('low', 0)) for c in lookback)
            
            # Verifica se é range apertado (menos de 3% de amplitude)
            range_pct = ((range_high - range_low) / range_low) * 100
            if range_pct > 5:  # Range muito largo, não é consolidação
                return None
            
            # Preço atual
            current_price = ctx.get('current_price', 0)
            if not current_price:
                return None
            
            # Verifica breakout
            breakout_margin = 0.001  # 0.1% de margem
            
            if current_price > range_high * (1 + breakout_margin):
                return ScanTrigger(
                    symbol=symbol,
                    timeframe="1h",
                    direction_hint="long",
                    trigger_type="RANGE_BREAKOUT",
                    details=f"Rompeu resistência ${range_high:.2f} (range {range_pct:.1f}%)",
                    priority=1
                )
            elif current_price < range_low * (1 - breakout_margin):
                return ScanTrigger(
                    symbol=symbol,
                    timeframe="1h",
                    direction_hint="short",
                    trigger_type="RANGE_BREAKOUT",
                    details=f"Rompeu suporte ${range_low:.2f} (range {range_pct:.1f}%)",
                    priority=1
                )
            
            return None
            
        except Exception as e:
            self.log.debug(f"[SCANNER] Erro em range_breakout {symbol}: {e}")
            return None
    
    # ==================== UTILITÁRIOS ====================
    
    def get_scanner_status(self) -> Dict[str, Any]:
        """Retorna status do scanner"""
        return {
            "swing_symbols": self.swing_symbols,
            "scalp_symbols": self.scalp_symbols,
            "cached_daily_shifts": dict(self._last_daily_shifts),
            "cached_regimes": dict(self._last_regimes),
            "config": {
                "strong_move_mult": self.strong_move_atr_mult,
                "pullback_dist_pct": self.pullback_ema_dist_pct,
                "range_lookback": self.range_lookback
            }
        }
