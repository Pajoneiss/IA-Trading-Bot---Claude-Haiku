"""
SCALP Filters - Anti-Overtrading Protection
Filtros inteligentes para evitar overtrading no motor SCALP
"""
import logging
import time
import json
import os
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict, deque
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ScalpFilters:
    """
    Filtros anti-overtrading para o motor SCALP.
    
    Implementa:
    - Filtro de volatilidade mínima
    - Filtro de fee/spread (TP mínimo)
    - Validação de notional mínimo
    - Cooldown por símbolo após overtrading
    - Limite de posições SCALP por símbolo
    - Limite de trades por dia
    - Cooldown após sequência de perdas
    """
    
    def __init__(self,
                 min_volatility_pct: float = 0.4,  # Relaxado de 0.7 para 0.4
                 min_tp_pct: float = 0.5,  # Relaxado de 0.6 para 0.5
                 min_notional: float = 5.0,
                 cooldown_duration_seconds: int = 900,  # Relaxado de 1800 para 900 (15min)
                 max_trades_for_cooldown: int = 3,
                 max_scalp_positions_per_symbol: int = 2,
                 max_scalp_trades_per_day: int = 8,  # NOVO
                 losing_streak_threshold: int = 3,  # NOVO
                 losing_streak_cooldown_minutes: int = 30):  # NOVO
        """
        Inicializa filtros SCALP
        
        Args:
            min_volatility_pct: Volatilidade mínima em % para operar (default: 0.4%)
            min_tp_pct: Take Profit mínimo em % para cobrir fees (default: 0.5%)
            min_notional: Notional mínimo em USDC (default: 5.0)
            cooldown_duration_seconds: Duração do cooldown em segundos (default: 900 = 15min)
            max_trades_for_cooldown: Número de trades para ativar cooldown (default: 3)
            max_scalp_positions_per_symbol: Máximo de posições SCALP por símbolo (default: 2)
            max_scalp_trades_per_day: Máximo de trades SCALP por dia (default: 8)
            losing_streak_threshold: Número de perdas consecutivas para ativar cooldown (default: 3)
            losing_streak_cooldown_minutes: Duração do cooldown após losing streak (default: 30)
        """
        # Tenta carregar config do arquivo
        config = self._load_config()
        
        self.min_volatility_pct = config.get('min_volatility_pct', min_volatility_pct)
        self.min_tp_pct = config.get('min_tp_pct', min_tp_pct)
        self.min_notional = config.get('min_notional', min_notional)
        self.cooldown_duration = config.get('cooldown_seconds', cooldown_duration_seconds)
        self.max_trades_for_cooldown = config.get('max_trades_for_cooldown', max_trades_for_cooldown)
        self.max_scalp_positions_per_symbol = config.get('max_scalp_positions_per_symbol', max_scalp_positions_per_symbol)
        self.max_scalp_trades_per_day = config.get('max_trades_per_day', max_scalp_trades_per_day)
        self.losing_streak_threshold = config.get('losing_streak_threshold', losing_streak_threshold)
        self.losing_streak_cooldown_minutes = config.get('losing_streak_cooldown_minutes', losing_streak_cooldown_minutes)
        
        # Rastreamento de trades por símbolo
        # {symbol: deque([(timestamp, pnl), ...])}
        self.trade_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=20))
        
        # Cooldown ativo por símbolo
        # {symbol: timestamp_fim_cooldown}
        self.cooldowns: Dict[str, float] = {}
        
        # Contagem diária de trades
        self.daily_trade_count = 0
        self.last_trade_date = ""
        
        # Sequência de perdas
        self.losing_streak = 0
        self.losing_streak_cooldown_end = 0.0
        
        logger.info(
            f"ScalpFilters inicializado: min_vol={self.min_volatility_pct}% | "
            f"min_tp={self.min_tp_pct}% | min_notional=${self.min_notional} | "
            f"cooldown={self.cooldown_duration}s | max_pos={self.max_scalp_positions_per_symbol} | "
            f"max_trades_day={self.max_scalp_trades_per_day}"
        )
    
    def _load_config(self) -> Dict[str, Any]:
        """Carrega configuração do arquivo se existir"""
        config_path = os.path.join("data", "ai_trading_config.json")
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    data = json.load(f)
                    return data.get('scalp', {})
        except Exception as e:
            logger.warning(f"Erro ao carregar config: {e}")
        return {}
    
    def _reset_daily_count_if_needed(self):
        """Reseta contagem diária se mudou o dia"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self.last_trade_date:
            self.daily_trade_count = 0
            self.last_trade_date = today
            self.losing_streak = 0
            logger.info(f"📅 Reset contagem diária de SCALP: {today}")
    
    def check_daily_limit(self) -> Tuple[bool, str]:
        """
        Verifica se atingiu o limite diário de trades SCALP
        
        Returns:
            (pode_operar, motivo)
        """
        self._reset_daily_count_if_needed()
        
        if self.daily_trade_count >= self.max_scalp_trades_per_day:
            logger.info(
                f"[RISK] SCALP bloqueado: Limite diário atingido "
                f"({self.daily_trade_count}/{self.max_scalp_trades_per_day})"
            )
            return False, f"Limite diário atingido ({self.daily_trade_count}/{self.max_scalp_trades_per_day})"
        
        return True, "OK"
    
    def check_losing_streak(self) -> Tuple[bool, str]:
        """
        Verifica se está em cooldown por losing streak
        
        Returns:
            (pode_operar, motivo)
        """
        current_time = time.time()
        
        if current_time < self.losing_streak_cooldown_end:
            remaining = int((self.losing_streak_cooldown_end - current_time) / 60)
            logger.info(
                f"[RISK] SCALP bloqueado: Losing streak cooldown "
                f"(restam {remaining}min)"
            )
            return False, f"Losing streak cooldown (restam {remaining}min)"
        
        return True, "OK"
    
    def register_trade_result(self, pnl: float):
        """
        Registra resultado de um trade para controle de losing streak
        
        Args:
            pnl: PnL do trade em USDC
        """
        self._reset_daily_count_if_needed()
        self.daily_trade_count += 1
        
        if pnl < 0:
            self.losing_streak += 1
            logger.info(f"⚠️ Losing streak: {self.losing_streak}/{self.losing_streak_threshold}")
            
            if self.losing_streak >= self.losing_streak_threshold:
                cooldown_seconds = self.losing_streak_cooldown_minutes * 60
                self.losing_streak_cooldown_end = time.time() + cooldown_seconds
                logger.warning(
                    f"🚨 SCALP Losing Streak Cooldown ativado! "
                    f"{self.losing_streak} perdas seguidas. "
                    f"Cooldown de {self.losing_streak_cooldown_minutes}min."
                )
        else:
            if self.losing_streak > 0:
                logger.info(f"✅ Losing streak resetado após lucro")
            self.losing_streak = 0

    def check_volatility(self, candles: List[Dict[str, Any]], symbol: str) -> Tuple[bool, str]:
        """
        Verifica se há volatilidade suficiente para scalp
        
        Args:
            candles: Lista de candles OHLCV
            symbol: Símbolo do par
            
        Returns:
            (pode_operar, motivo)
        """
        if not candles or len(candles) < 20:
            return False, f"Dados insuficientes ({len(candles) if candles else 0} candles)"
        
        # Pega últimos 20 candles
        recent_candles = candles[-20:]
        
        # Calcula range médio (high - low) / close
        ranges = []
        for candle in recent_candles:
            high = float(candle.get('h', 0))
            low = float(candle.get('l', 0))
            close = float(candle.get('c', 1))
            
            if close > 0:

                range_pct = ((high - low) / close) * 100
                ranges.append(range_pct)
        
        if not ranges:
            return False, "Não foi possível calcular volatilidade"
        
        avg_range = sum(ranges) / len(ranges)
        
        if avg_range < self.min_volatility_pct:
            logger.info(
                f"[RISK] SCALP bloqueado em {symbol}: "
                f"Volatilidade muito baixa ({avg_range:.2f}% < {self.min_volatility_pct}%)"
            )
            return False, f"Volatilidade muito baixa ({avg_range:.2f}% < {self.min_volatility_pct}%)"
        
        logger.debug(f"✅ {symbol}: Volatilidade OK ({avg_range:.2f}%)")
        return True, "OK"
    
    def check_fee_viability(self, tp_pct: float, sl_pct: float, symbol: str) -> Tuple[bool, str]:
        """
        Verifica se TP é suficiente para cobrir fees + spread
        
        Hyperliquid fees:
        - Maker: 0.02%
        - Taker: 0.05%
        - Spread estimado: ~0.02-0.05%
        
        Custo total estimado (ida + volta): ~0.15-0.20%
        TP mínimo recomendado: 3x custo = 0.6%
        
        Args:
            tp_pct: Take Profit em %
            sl_pct: Stop Loss em %
            symbol: Símbolo do par
            
        Returns:
            (pode_operar, motivo)
        """
        # Valida que TP > SL (básico)
        if tp_pct <= sl_pct:
            logger.warning(
                f"[RISK] SCALP bloqueado em {symbol}: "
                f"TP ({tp_pct}%) <= SL ({sl_pct}%)"
            )
            return False, f"TP ({tp_pct}%) deve ser maior que SL ({sl_pct}%)"
        
        # Verifica TP mínimo
        if tp_pct < self.min_tp_pct:
            logger.info(
                f"[RISK] SCALP bloqueado em {symbol}: "
                f"TP muito baixo ({tp_pct}% < {self.min_tp_pct}%)"
            )
            return False, f"TP muito baixo ({tp_pct}% < {self.min_tp_pct}%), não cobre fees"
        
        # Calcula risk/reward
        rr_ratio = tp_pct / sl_pct if sl_pct > 0 else 0
        
        if rr_ratio < 1.5:
            logger.warning(
                f"[RISK] SCALP em {symbol}: R/R baixo ({rr_ratio:.2f}), "
                f"mas TP >= mínimo. Permitindo."
            )
        
        logger.debug(f"✅ {symbol}: TP OK ({tp_pct}%), R/R={rr_ratio:.2f}")
        return True, "OK"
    
    def check_min_notional(self, notional: float, symbol: str) -> Tuple[bool, str]:
        """
        Verifica se notional atinge o mínimo
        
        Args:
            notional: Valor notional em USDC
            symbol: Símbolo do par
            
        Returns:
            (pode_operar, motivo)
        """
        if notional < self.min_notional:
            logger.info(
                f"[RISK] SCALP bloqueado em {symbol}: "
                f"Notional muito baixo (${notional:.2f} < ${self.min_notional})"
            )
            return False, f"Notional muito baixo (${notional:.2f} < ${self.min_notional})"
        
        logger.debug(f"✅ {symbol}: Notional OK (${notional:.2f})")
        return True, "OK"
    
    def check_cooldown(self, symbol: str) -> Tuple[bool, str]:
        """
        Verifica se símbolo está em cooldown
        
        Args:
            symbol: Símbolo do par
            
        Returns:
            (pode_operar, motivo)
        """
        current_time = time.time()
        
        if symbol in self.cooldowns:
            cooldown_end = self.cooldowns[symbol]
            
            if current_time < cooldown_end:
                remaining = int((cooldown_end - current_time) / 60)
                logger.info(
                    f"[RISK] SCALP bloqueado em {symbol}: "
                    f"Símbolo em cooldown (restam {remaining}min)"
                )
                return False, f"Símbolo em cooldown (restam {remaining}min)"
            else:
                # Cooldown expirou
                del self.cooldowns[symbol]
                logger.info(f"✅ {symbol}: Cooldown expirado, liberado para operar")
        
        return True, "OK"
    
    def check_position_limit(self, symbol: str, open_positions: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Verifica limite de posições SCALP por símbolo
        
        Args:
            symbol: Símbolo do par
            open_positions: Lista de posições abertas
            
        Returns:
            (pode_operar, motivo)
        """
        # Conta posições SCALP abertas neste símbolo
        scalp_count = 0
        for pos in open_positions:
            if pos.get('symbol') == symbol and pos.get('style') == 'scalp':
                scalp_count += 1
        
        if scalp_count >= self.max_scalp_positions_per_symbol:
            logger.info(
                f"[RISK] SCALP bloqueado em {symbol}: "
                f"Limite de posições atingido ({scalp_count}/{self.max_scalp_positions_per_symbol})"
            )
            return False, f"Limite de posições atingido ({scalp_count}/{self.max_scalp_positions_per_symbol})"
        
        logger.debug(f"✅ {symbol}: Posições OK ({scalp_count}/{self.max_scalp_positions_per_symbol})")
        return True, "OK"
    
    def record_trade(self, symbol: str, pnl: float):
        """
        Registra resultado de um trade e verifica se deve ativar cooldown
        
        Args:
            symbol: Símbolo do par
            pnl: PnL realizado em USDC
        """
        current_time = time.time()
        
        # Adiciona trade ao histórico
        self.trade_history[symbol].append((current_time, pnl))
        
        # Verifica últimos N trades em janela de tempo
        recent_trades = []
        cutoff_time = current_time - self.cooldown_duration
        
        for timestamp, trade_pnl in self.trade_history[symbol]:
            if timestamp >= cutoff_time:
                recent_trades.append((timestamp, trade_pnl))
        
        # Se tiver N ou mais trades recentes
        if len(recent_trades) >= self.max_trades_for_cooldown:
            total_pnl = sum(pnl for _, pnl in recent_trades)
            
            # Se PnL total for negativo ou próximo de zero
            if total_pnl <= 0.5:  # Tolerância de $0.50
                # Ativa cooldown
                self.cooldowns[symbol] = current_time + self.cooldown_duration
                
                logger.warning(
                    f"🚨 [RISK] SCALP cooldown ativado em {symbol}: "
                    f"overtrading detectado ({len(recent_trades)} trades em "
                    f"{self.cooldown_duration/60:.0f}min com PnL total ${total_pnl:.2f})"
                )
            else:
                logger.debug(
                    f"✅ {symbol}: {len(recent_trades)} trades recentes com PnL positivo (${total_pnl:.2f})"
                )
    
    def apply_all_filters(self,
                         decision: Dict[str, Any],
                         candles: List[Dict[str, Any]],
                         open_positions: List[Dict[str, Any]],
                         notional: Optional[float] = None) -> Tuple[bool, str]:
        """
        Aplica todos os filtros em sequência
        
        Args:
            decision: Decisão de trade da IA
            candles: Candles do símbolo
            open_positions: Posições abertas
            notional: Valor notional (opcional, se já calculado)
            
        Returns:
            (aprovado, motivo_se_bloqueado)
        """
        symbol = decision.get('symbol', 'UNKNOWN')
        action = decision.get('action')
        
        # Só aplica filtros para ações de abertura
        if action != 'open':
            return True, "OK"
        
        # 1. Filtro de Cooldown (primeiro, mais rápido)
        can_trade, reason = self.check_cooldown(symbol)
        if not can_trade:
            return False, reason
        
        # 2. Filtro de Limite de Posições
        can_trade, reason = self.check_position_limit(symbol, open_positions)
        if not can_trade:
            return False, reason
        
        # 3. Filtro de Volatilidade
        can_trade, reason = self.check_volatility(candles, symbol)
        if not can_trade:
            return False, reason
        
        # 4. Filtro de Fee/TP
        # Extrai TP e SL da decisão
        # A decisão pode ter stop_loss_price/take_profit_price ou stop_loss_pct/take_profit_pct
        tp_pct = decision.get('take_profit_pct')
        sl_pct = decision.get('stop_loss_pct')
        
        # Se não tiver pct, tenta calcular a partir dos preços
        if tp_pct is None or sl_pct is None:
            # Precisaria do preço atual, mas não temos aqui
            # Vamos assumir que a decisão tem os pcts ou pular esse filtro
            logger.debug(f"{symbol}: Filtro de TP/SL pulado (sem percentuais na decisão)")
        else:
            # Converte para valores absolutos
            tp_pct = abs(float(tp_pct))
            sl_pct = abs(float(sl_pct))
            
            can_trade, reason = self.check_fee_viability(tp_pct, sl_pct, symbol)
            if not can_trade:
                return False, reason
        
        # 5. Filtro de Notional (se fornecido)
        if notional is not None:
            can_trade, reason = self.check_min_notional(notional, symbol)
            if not can_trade:
                return False, reason
        
        logger.info(f"✅ {symbol}: Todos os filtros SCALP aprovados")
        return True, "OK"
    
    def get_cooldown_status(self) -> Dict[str, int]:
        """
        Retorna status de cooldown de todos os símbolos
        
        Returns:
            Dict {symbol: minutos_restantes}
        """
        current_time = time.time()
        status = {}
        
        for symbol, cooldown_end in self.cooldowns.items():
            if current_time < cooldown_end:
                remaining_minutes = int((cooldown_end - current_time) / 60)
                status[symbol] = remaining_minutes
        
        return status
