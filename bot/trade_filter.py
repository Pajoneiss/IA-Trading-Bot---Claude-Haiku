"""
Trade Action Filter / Execution Guard
Camada de proteção contra overtrading e micro-ajustes

Este módulo filtra as decisões da IA antes da execução, garantindo que:
- Não haja ajustes muito frequentes no mesmo ativo
- Haja variação mínima de preço desde o último ajuste
- A mudança de posição seja significativa o suficiente
- Não haja ping-pong de increase/decrease
"""
import time
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SymbolAdjustmentState:
    """Estado de ajustes para um símbolo específico"""
    last_adjustment_time: float = 0.0
    last_adjustment_price: float = 0.0
    last_adjustment_action: str = ""  # "increase" ou "decrease"
    last_position_size: float = 0.0
    adjustment_count_today: int = 0
    last_reset_date: str = ""


class TradeActionFilter:
    """
    Filtro de ações de trading para evitar overtrading.
    
    Recebe lista de ações da IA e estado atual, devolve lista filtrada
    removendo ajustes inúteis ou prejudiciais.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Inicializa o filtro com configurações.
        
        Args:
            config: Dicionário de configuração (opcional)
        """
        config = config or {}
        
        # ========== CONFIGURAÇÕES DE FILTRO ==========
        
        # Tempo mínimo entre ajustes no mesmo símbolo (segundos)
        self.min_seconds_between_adjustments = config.get(
            'min_seconds_between_adjustments', 300  # 5 minutos
        )
        
        # Movimento mínimo de preço para justificar ajuste (%)
        self.min_price_move_pct = config.get(
            'min_price_move_pct', 0.5  # 0.5%
        )
        
        # Mudança mínima de posição (ratio do tamanho atual)
        self.min_position_change_ratio = config.get(
            'min_position_change_ratio', 0.25  # 25% da posição
        )
        
        # Notional mínimo para ajuste valer a pena (USD)
        self.min_notional_adjust = config.get(
            'min_notional_adjust', 10.0  # $10
        )
        
        # Máximo de ajustes por símbolo por dia
        self.max_adjustments_per_symbol_per_day = config.get(
            'max_adjustments_per_symbol_per_day', 4
        )
        
        # Confiança mínima para diferentes ações
        self.min_confidence_open = config.get('min_confidence_open', 0.72)
        self.min_confidence_adjust = config.get('min_confidence_adjust', 0.80)
        self.min_confidence_close = config.get('min_confidence_close', 0.65)
        
        # Proteção contra ping-pong: tempo mínimo para inverter direção
        self.min_seconds_to_reverse = config.get(
            'min_seconds_to_reverse', 600  # 10 minutos
        )
        
        # PnL mínimo (negativo) para permitir reversão rápida
        self.emergency_pnl_threshold = config.get(
            'emergency_pnl_threshold', -2.0  # -2%
        )
        
        # ========== ESTADO INTERNO ==========
        self.symbol_states: Dict[str, SymbolAdjustmentState] = {}
        
        logger.info(f"🛡️ TradeActionFilter inicializado:")
        logger.info(f"   - Min tempo entre ajustes: {self.min_seconds_between_adjustments}s")
        logger.info(f"   - Min movimento preço: {self.min_price_move_pct}%")
        logger.info(f"   - Min mudança posição: {self.min_position_change_ratio*100}%")
        logger.info(f"   - Min notional ajuste: ${self.min_notional_adjust}")
        logger.info(f"   - Max ajustes/dia/símbolo: {self.max_adjustments_per_symbol_per_day}")
    
    def _get_symbol_state(self, symbol: str) -> SymbolAdjustmentState:
        """Obtém ou cria estado para um símbolo"""
        if symbol not in self.symbol_states:
            self.symbol_states[symbol] = SymbolAdjustmentState()
        
        state = self.symbol_states[symbol]
        
        # Reset diário do contador
        today = datetime.now().strftime("%Y-%m-%d")
        if state.last_reset_date != today:
            state.adjustment_count_today = 0
            state.last_reset_date = today
        
        return state
    
    def _update_symbol_state(self, symbol: str, action: str, price: float, size: float):
        """Atualiza estado após uma ação ser aceita"""
        state = self._get_symbol_state(symbol)
        state.last_adjustment_time = time.time()
        state.last_adjustment_price = price
        state.last_adjustment_action = action
        state.last_position_size = size
        state.adjustment_count_today += 1
    
    def filter_actions(
        self,
        actions: List[Dict[str, Any]],
        positions: Dict[str, Dict[str, Any]],
        prices: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """
        Filtra lista de ações, removendo ajustes inúteis.
        
        Args:
            actions: Lista de ações da IA
            positions: Dict de posições abertas {symbol: position_data}
            prices: Dict de preços atuais {symbol: price}
            
        Returns:
            Lista de ações filtradas (aprovadas)
        """
        filtered = []
        now = time.time()
        
        for action in actions:
            symbol = action.get('symbol', '')
            action_type = action.get('action', '')
            confidence = action.get('confidence', 0.5)
            quantity_pct = action.get('quantity_pct', 0.5)
            
            # Obtém info da posição e preço
            position = positions.get(symbol, {})
            current_price = prices.get(symbol, 0)
            current_size = position.get('size', 0) if position else 0
            entry_price = position.get('entry_price', current_price) if position else current_price
            
            # Calcula PnL se houver posição
            pnl_pct = 0
            if position and entry_price > 0 and current_price > 0:
                side = position.get('side', 'long')
                if side == 'long':
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100
            
            # ========== FILTROS POR TIPO DE AÇÃO ==========
            
            # OPEN e CLOSE passam com menos restrições
            if action_type == 'open':
                result = self._filter_open(action, position, confidence)
            elif action_type == 'close':
                result = self._filter_close(action, position, confidence, pnl_pct)
            elif action_type in ('increase', 'decrease'):
                result = self._filter_adjustment(
                    action, position, current_price, current_size, 
                    confidence, quantity_pct, pnl_pct, now
                )
            elif action_type == 'hold':
                # Hold sempre passa (não faz nada mesmo)
                result = (True, "hold aceito")
            else:
                result = (True, "tipo desconhecido, deixando passar")
            
            approved, reason = result
            
            if approved:
                filtered.append(action)
                
                # Atualiza estado se for adjustment
                if action_type in ('increase', 'decrease'):
                    self._update_symbol_state(symbol, action_type, current_price, current_size)
                    
                logger.debug(f"✅ FILTRO APROVOU: {symbol} {action_type} - {reason}")
            else:
                logger.info(f"🚫 FILTRO BLOQUEOU: {symbol} {action_type} - {reason}")
        
        return filtered
    
    def _filter_open(
        self, 
        action: Dict, 
        position: Dict, 
        confidence: float
    ) -> tuple[bool, str]:
        """Filtra ação de abertura de posição"""
        symbol = action.get('symbol', '')
        
        # Já tem posição aberta?
        if position and position.get('size', 0) > 0:
            return False, "já existe posição aberta"
        
        # Confiança mínima
        if confidence < self.min_confidence_open:
            return False, f"confiança {confidence:.2f} < {self.min_confidence_open} (mín para open)"
        
        return True, "aprovado"
    
    def _filter_close(
        self,
        action: Dict,
        position: Dict,
        confidence: float,
        pnl_pct: float
    ) -> tuple[bool, str]:
        """Filtra ação de fechamento"""
        symbol = action.get('symbol', '')
        
        # Não tem posição para fechar?
        if not position or position.get('size', 0) <= 0:
            return False, "não há posição para fechar"
        
        # Close é mais permissivo - especialmente se PnL negativo
        if pnl_pct < self.emergency_pnl_threshold:
            return True, f"emergência: PnL {pnl_pct:.2f}% muito negativo"
        
        if confidence < self.min_confidence_close:
            return False, f"confiança {confidence:.2f} < {self.min_confidence_close} (mín para close)"
        
        return True, "aprovado"
    
    def _filter_adjustment(
        self,
        action: Dict,
        position: Dict,
        current_price: float,
        current_size: float,
        confidence: float,
        quantity_pct: float,
        pnl_pct: float,
        now: float
    ) -> tuple[bool, str]:
        """Filtra ações de increase/decrease"""
        symbol = action.get('symbol', '')
        action_type = action.get('action', '')
        state = self._get_symbol_state(symbol)
        
        # ===== VERIFICAÇÃO 1: Posição existe? =====
        if not position or current_size <= 0:
            if action_type == 'decrease':
                return False, "não há posição para reduzir"
            # Para increase sem posição, deixa passar (pode ser DCA em posição pequena)
        
        # ===== VERIFICAÇÃO 2: Confiança mínima =====
        if confidence < self.min_confidence_adjust:
            return False, f"confiança {confidence:.2f} < {self.min_confidence_adjust} (mín para ajuste)"
        
        # ===== VERIFICAÇÃO 3: Limite diário de ajustes =====
        if state.adjustment_count_today >= self.max_adjustments_per_symbol_per_day:
            return False, f"limite de {self.max_adjustments_per_symbol_per_day} ajustes/dia atingido"
        
        # ===== VERIFICAÇÃO 4: Tempo desde último ajuste =====
        if state.last_adjustment_time > 0:
            elapsed = now - state.last_adjustment_time
            
            # Verificação de ping-pong (inversão de direção)
            is_reversal = (
                (state.last_adjustment_action == 'increase' and action_type == 'decrease') or
                (state.last_adjustment_action == 'decrease' and action_type == 'increase')
            )
            
            if is_reversal:
                # Reversão só permitida se:
                # 1. Passou tempo suficiente OU
                # 2. PnL muito negativo (emergência)
                if elapsed < self.min_seconds_to_reverse:
                    if pnl_pct > self.emergency_pnl_threshold:
                        return False, f"ping-pong bloqueado: só {elapsed:.0f}s desde {state.last_adjustment_action}"
                    else:
                        logger.warning(f"⚠️ {symbol}: Permitindo reversão emergencial (PnL: {pnl_pct:.2f}%)")
            
            # Tempo mínimo entre ajustes (mesmo tipo)
            if elapsed < self.min_seconds_between_adjustments:
                return False, f"cooldown: apenas {elapsed:.0f}s desde último ajuste (mín: {self.min_seconds_between_adjustments}s)"
        
        # ===== VERIFICAÇÃO 5: Movimento de preço =====
        if state.last_adjustment_price > 0 and current_price > 0:
            price_move_pct = abs(current_price - state.last_adjustment_price) / state.last_adjustment_price * 100
            
            if price_move_pct < self.min_price_move_pct:
                return False, f"preço moveu apenas {price_move_pct:.2f}% (mín: {self.min_price_move_pct}%)"
        
        # ===== VERIFICAÇÃO 6: Tamanho da mudança =====
        if current_size > 0:
            change_size = current_size * quantity_pct
            change_ratio = change_size / current_size
            
            if change_ratio < self.min_position_change_ratio:
                return False, f"mudança de {change_ratio*100:.1f}% muito pequena (mín: {self.min_position_change_ratio*100}%)"
            
            # Notional mínimo
            notional_change = change_size * current_price
            if notional_change < self.min_notional_adjust:
                return False, f"notional ${notional_change:.2f} < ${self.min_notional_adjust} (não vale a taxa)"
        
        return True, "aprovado após todas verificações"
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do filtro"""
        stats = {
            'symbols_tracked': len(self.symbol_states),
            'symbol_details': {}
        }
        
        for symbol, state in self.symbol_states.items():
            stats['symbol_details'][symbol] = {
                'adjustments_today': state.adjustment_count_today,
                'last_action': state.last_adjustment_action,
                'last_price': state.last_adjustment_price,
                'seconds_since_last': time.time() - state.last_adjustment_time if state.last_adjustment_time > 0 else None
            }
        
        return stats
    
    def reset_symbol(self, symbol: str):
        """Reseta estado de um símbolo específico"""
        if symbol in self.symbol_states:
            del self.symbol_states[symbol]
            logger.info(f"🔄 Estado resetado para {symbol}")
    
    def reset_all(self):
        """Reseta todo o estado do filtro"""
        self.symbol_states.clear()
        logger.info("🔄 Todo estado do filtro resetado")
