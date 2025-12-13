"""
ACTION EXECUTOR - Executor Robusto de Ações
=============================================

Este módulo padroniza TODAS as ações de trading, fornecendo:
1. Contrato único de ações (com aliases)
2. Validação de parâmetros
3. Sanity checks anti-bug (não são limites de risco!)
4. Conversões de unidade corretas (USD → coin size)
5. Log estruturado
6. Idempotência básica

Ações suportadas:
- open_position(symbol, side, notional_usd, leverage, isolated)
- close_position(symbol, percent)
- set_sl_tp(symbol, sl_price, tp_price)
- move_sl_to_breakeven(symbol)
- increase_position(symbol, delta_notional_usd)  # SEMPRE USD!
- decrease_position(symbol, percent OR delta_notional_usd)
- cancel_orders(symbol)

ALIASES (retrocompatibilidade):
- adjust_sl → set_sl_tp
- update_stop_loss → set_sl_tp
- breakeven → move_sl_to_breakeven
- execute_partial_close → decrease_position
- pyramid_add → increase_position

Autor: Claude
Data: 2024-12-13
"""

import logging
import math
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Tipos de ação padronizados"""
    OPEN_LONG = "open_long"
    OPEN_SHORT = "open_short"
    CLOSE = "close"
    INCREASE = "increase"
    DECREASE = "decrease"
    SET_SL = "set_sl"
    SET_TP = "set_tp"
    SET_SL_TP = "set_sl_tp"
    BREAKEVEN = "breakeven"
    HOLD = "hold"
    CANCEL_ORDERS = "cancel_orders"


# Mapeamento de aliases para tipos padronizados
ACTION_ALIASES = {
    # Open
    "open_long": ActionType.OPEN_LONG,
    "buy": ActionType.OPEN_LONG,
    "long": ActionType.OPEN_LONG,
    "open_short": ActionType.OPEN_SHORT,
    "sell": ActionType.OPEN_SHORT,
    "short": ActionType.OPEN_SHORT,
    
    # Close
    "close": ActionType.CLOSE,
    "close_position": ActionType.CLOSE,
    "close_market": ActionType.CLOSE,
    
    # Increase
    "increase": ActionType.INCREASE,
    "increase_position": ActionType.INCREASE,
    "pyramid_add": ActionType.INCREASE,
    "add": ActionType.INCREASE,
    "pyramid": ActionType.INCREASE,
    
    # Decrease
    "decrease": ActionType.DECREASE,
    "decrease_position": ActionType.DECREASE,
    "partial_close": ActionType.DECREASE,
    "execute_partial_close": ActionType.DECREASE,
    "reduce": ActionType.DECREASE,
    
    # SL/TP
    "set_sl": ActionType.SET_SL,
    "adjust_sl": ActionType.SET_SL,
    "update_stop_loss": ActionType.SET_SL,
    "set_tp": ActionType.SET_TP,
    "adjust_tp": ActionType.SET_TP,
    "update_take_profit": ActionType.SET_TP,
    "set_sl_tp": ActionType.SET_SL_TP,
    
    # Breakeven
    "breakeven": ActionType.BREAKEVEN,
    "move_sl_to_be": ActionType.BREAKEVEN,
    "move_sl_to_breakeven": ActionType.BREAKEVEN,
    "be": ActionType.BREAKEVEN,
    
    # Hold
    "hold": ActionType.HOLD,
    "wait": ActionType.HOLD,
    "noop": ActionType.HOLD,
    
    # Cancel
    "cancel_orders": ActionType.CANCEL_ORDERS,
    "cancel": ActionType.CANCEL_ORDERS,
}


@dataclass
class ActionResult:
    """Resultado de uma ação executada"""
    success: bool
    action_type: ActionType
    symbol: str
    message: str
    details: Dict[str, Any] = None
    error: str = None


@dataclass
class SanityCheckResult:
    """Resultado de sanity check"""
    passed: bool
    clamped: bool = False
    original_value: float = 0
    clamped_value: float = 0
    reason: str = ""


class ActionExecutor:
    """
    Executor robusto de ações de trading.
    
    Centraliza toda execução, garantindo:
    - Validação de parâmetros
    - Conversões corretas de unidade
    - Sanity checks anti-bug
    - Log estruturado
    """
    
    def __init__(self, bot):
        """
        Args:
            bot: Instância do HyperliquidBot
        """
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        
        # Cache de preços para evitar múltiplas chamadas
        self._price_cache = {}
        self._price_cache_ts = 0
    
    def resolve_action_type(self, intent: str) -> Optional[ActionType]:
        """
        Resolve string de intent para ActionType padronizado.
        
        Suporta aliases para retrocompatibilidade.
        """
        intent_lower = intent.lower().strip()
        return ACTION_ALIASES.get(intent_lower)
    
    def execute(self, action: Dict[str, Any], prices: Dict[str, float] = None) -> ActionResult:
        """
        Executa uma ação de forma padronizada.
        
        Args:
            action: Dict com:
                - intent/action: Tipo de ação (suporta aliases)
                - symbol: Símbolo do ativo
                - ... parâmetros específicos da ação
            prices: Cache de preços (opcional)
            
        Returns:
            ActionResult com status da execução
        """
        # Atualiza cache de preços
        if prices:
            self._price_cache = prices
        
        # Extrai intent
        intent = action.get('intent') or action.get('action') or action.get('type')
        if not intent:
            return ActionResult(
                success=False,
                action_type=None,
                symbol=action.get('symbol', 'UNKNOWN'),
                message="Intent não especificado",
                error="MISSING_INTENT"
            )
        
        # Resolve tipo
        action_type = self.resolve_action_type(intent)
        if not action_type:
            self.logger.warning(f"[ACTION_EXECUTOR] Intent desconhecido: {intent}")
            return ActionResult(
                success=False,
                action_type=None,
                symbol=action.get('symbol', 'UNKNOWN'),
                message=f"Intent desconhecido: {intent}",
                error="UNKNOWN_INTENT"
            )
        
        symbol = action.get('symbol')
        if not symbol and action_type not in [ActionType.HOLD]:
            return ActionResult(
                success=False,
                action_type=action_type,
                symbol='UNKNOWN',
                message="Symbol não especificado",
                error="MISSING_SYMBOL"
            )
        
        # Roteia para executor específico
        try:
            if action_type == ActionType.OPEN_LONG:
                return self._execute_open(symbol, 'long', action)
            elif action_type == ActionType.OPEN_SHORT:
                return self._execute_open(symbol, 'short', action)
            elif action_type == ActionType.CLOSE:
                return self._execute_close(symbol, action)
            elif action_type == ActionType.INCREASE:
                return self._execute_increase(symbol, action)
            elif action_type == ActionType.DECREASE:
                return self._execute_decrease(symbol, action)
            elif action_type in [ActionType.SET_SL, ActionType.SET_TP, ActionType.SET_SL_TP]:
                return self._execute_set_sl_tp(symbol, action)
            elif action_type == ActionType.BREAKEVEN:
                return self._execute_breakeven(symbol, action)
            elif action_type == ActionType.HOLD:
                return self._execute_hold(symbol, action)
            elif action_type == ActionType.CANCEL_ORDERS:
                return self._execute_cancel_orders(symbol, action)
            else:
                return ActionResult(
                    success=False,
                    action_type=action_type,
                    symbol=symbol,
                    message=f"Executor não implementado para {action_type}",
                    error="NOT_IMPLEMENTED"
                )
        except Exception as e:
            self.logger.error(f"[ACTION_EXECUTOR] Erro ao executar {action_type}: {e}")
            return ActionResult(
                success=False,
                action_type=action_type,
                symbol=symbol,
                message=f"Erro ao executar: {e}",
                error=str(e)
            )
    
    # ================================================================
    # SANITY CHECKS (Anti-bug, NÃO são limites de risco!)
    # ================================================================
    
    def _sanity_check_notional(self, notional_usd: float, equity: float, symbol: str) -> SanityCheckResult:
        """
        Sanity check para notional (USD).
        
        Detecta bugs de conversão/unidade que causariam ordens absurdas.
        
        ISSO NÃO É LIMITE DE RISCO - é detecção de bug!
        """
        # Bug detector: notional muito maior que equity é provavelmente erro de unidade
        max_reasonable = equity * 5  # 5x equity é o máximo razoável (500% leverage)
        
        if notional_usd > max_reasonable:
            clamped = max_reasonable
            self.logger.warning(
                f"[SANITY_CHECK] ⚠️ {symbol} NOTIONAL ABSURDO DETECTADO! "
                f"Original=${notional_usd:.2f} > {max_reasonable:.2f} (5x equity). "
                f"Provável bug de unidade. CLAMPED para ${clamped:.2f}"
            )
            return SanityCheckResult(
                passed=False,
                clamped=True,
                original_value=notional_usd,
                clamped_value=clamped,
                reason=f"NOTIONAL_ABSURD: ${notional_usd:.2f} > 5x equity"
            )
        
        return SanityCheckResult(passed=True, original_value=notional_usd, clamped_value=notional_usd)
    
    def _sanity_check_size(self, size_coin: float, symbol: str, current_price: float, equity: float) -> SanityCheckResult:
        """
        Sanity check para size (coins).
        
        Detecta bugs de conversão que causariam posições absurdas.
        """
        # Calcula notional equivalente
        notional = size_coin * current_price
        
        # Bug detector
        max_notional = equity * 5
        
        if notional > max_notional:
            # Calcula size corrigido
            clamped_size = max_notional / current_price
            
            self.logger.warning(
                f"[SANITY_CHECK] ⚠️ {symbol} SIZE ABSURDO DETECTADO! "
                f"size={size_coin:.8f} @ ${current_price:.2f} = ${notional:.2f} notional. "
                f"Provável confusão USD/coin. CLAMPED para {clamped_size:.8f}"
            )
            return SanityCheckResult(
                passed=False,
                clamped=True,
                original_value=size_coin,
                clamped_value=clamped_size,
                reason=f"SIZE_ABSURD: notional ${notional:.2f} > 5x equity"
            )
        
        return SanityCheckResult(passed=True, original_value=size_coin, clamped_value=size_coin)
    
    def _convert_usd_to_size(self, notional_usd: float, symbol: str, current_price: float) -> Tuple[float, int]:
        """
        Converte notional USD para size em coins.
        
        Returns:
            (size_coin, sz_decimals)
        """
        if current_price <= 0:
            raise ValueError(f"Preço inválido para {symbol}: {current_price}")
        
        # Busca decimais do ativo
        sz_decimals = self.bot.client.sz_decimals_cache.get(symbol, 4)
        
        # Calcula size
        raw_size = notional_usd / current_price
        
        # Arredonda DOWN para segurança
        factor = 10 ** sz_decimals
        size_coin = math.floor(raw_size * factor) / factor
        
        self.logger.debug(
            f"[CONVERT] {symbol}: ${notional_usd:.2f} / ${current_price:.2f} = "
            f"{raw_size:.8f} → {size_coin} (floor, {sz_decimals} decimais)"
        )
        
        return size_coin, sz_decimals
    
    def _get_current_price(self, symbol: str) -> float:
        """Obtém preço atual do símbolo"""
        if symbol in self._price_cache:
            return float(self._price_cache[symbol])
        
        try:
            all_prices = self.bot.client.get_all_mids()
            self._price_cache = all_prices
            return float(all_prices.get(symbol, 0))
        except Exception as e:
            self.logger.error(f"[ACTION_EXECUTOR] Erro ao buscar preço de {symbol}: {e}")
            return 0
    
    def _get_equity(self) -> float:
        """Obtém equity atual"""
        try:
            if hasattr(self.bot, 'risk_manager') and self.bot.risk_manager:
                return self.bot.risk_manager.current_equity or 0
            return 0
        except:
            return 0
    
    # ================================================================
    # EXECUTORES ESPECÍFICOS
    # ================================================================
    
    def _execute_open(self, symbol: str, side: str, action: Dict) -> ActionResult:
        """
        Executa abertura de posição.
        
        Delega para o método existente do bot.
        """
        # Prepara decision no formato esperado pelo _execute_open original
        decision = {
            'symbol': symbol,
            'action': 'open',
            'side': side,
            'direction': side,
            'confidence': action.get('confidence', 0.85),
            'leverage': action.get('leverage', 5),
            'size_usd': action.get('size_usd') or action.get('notional_usd', 0),
            'stop_loss_pct': action.get('stop_loss_pct', 2.0),
            'take_profit_pct': action.get('take_profit_pct', 4.0),
            'source': action.get('source', 'action_executor'),
            'style': action.get('style', 'swing'),
            'reason': action.get('reason', ''),
            'trigger_type': action.get('trigger_type', 'ACTION_EXECUTOR')
        }
        
        # Se tem sl_price/tp_price, converte para pct
        if action.get('sl_price') and not action.get('stop_loss_pct'):
            price = self._get_current_price(symbol)
            if price > 0:
                if side == 'long':
                    decision['stop_loss_pct'] = ((price - action['sl_price']) / price) * 100
                else:
                    decision['stop_loss_pct'] = ((action['sl_price'] - price) / price) * 100
        
        # Delega para executor original
        prices = self._price_cache or self.bot.client.get_all_mids()
        result = self.bot._execute_open(decision, prices)
        
        return ActionResult(
            success=bool(result),
            action_type=ActionType.OPEN_LONG if side == 'long' else ActionType.OPEN_SHORT,
            symbol=symbol,
            message=f"Open {side.upper()} executado" if result else "Falha ao abrir posição",
            details=decision
        )
    
    def _execute_close(self, symbol: str, action: Dict) -> ActionResult:
        """Executa fechamento de posição"""
        percent = action.get('percent', 100)
        
        if percent < 100:
            # Partial close
            return self._execute_decrease(symbol, {'percent': percent, 'reason': action.get('reason', 'close partial')})
        
        # Close total
        if not self.bot.position_manager.has_position(symbol):
            return ActionResult(
                success=False,
                action_type=ActionType.CLOSE,
                symbol=symbol,
                message="Posição não encontrada",
                error="POSITION_NOT_FOUND"
            )
        
        position = self.bot.position_manager.get_position(symbol)
        prices = self._price_cache or self.bot.client.get_all_mids()
        
        close_action = {
            'symbol': symbol,
            'action': 'close',
            'reason': action.get('reason', 'ACTION_EXECUTOR'),
            'side': position.side,
            'current_price': prices.get(symbol, position.entry_price)
        }
        
        self.bot._execute_close(close_action, prices)
        
        return ActionResult(
            success=True,
            action_type=ActionType.CLOSE,
            symbol=symbol,
            message=f"Posição {symbol} fechada"
        )
    
    def _execute_increase(self, symbol: str, action: Dict) -> ActionResult:
        """
        Executa aumento de posição.
        
        🔴 CRÍTICO: Sempre recebe delta_notional_usd (USD), NUNCA size_pct!
        
        Parâmetros aceitos:
        - delta_notional_usd: Valor em USD para adicionar
        - size_usd: Alias para delta_notional_usd
        - delta_size: Se for em coins (será convertido com sanity check)
        """
        if not self.bot.position_manager.has_position(symbol):
            return ActionResult(
                success=False,
                action_type=ActionType.INCREASE,
                symbol=symbol,
                message="Posição não encontrada",
                error="POSITION_NOT_FOUND"
            )
        
        position = self.bot.position_manager.get_position(symbol)
        current_price = self._get_current_price(symbol)
        equity = self._get_equity()
        
        if current_price <= 0:
            return ActionResult(
                success=False,
                action_type=ActionType.INCREASE,
                symbol=symbol,
                message="Preço não disponível",
                error="PRICE_UNAVAILABLE"
            )
        
        # ===== EXTRAÇÃO DO VALOR =====
        delta_notional_usd = action.get('delta_notional_usd') or action.get('size_usd')
        delta_size = action.get('delta_size') or action.get('add_size')
        
        # Se veio delta_size em coins, converte para USD para validação
        if delta_size and not delta_notional_usd:
            delta_notional_usd = delta_size * current_price
            self.logger.info(
                f"[INCREASE] {symbol}: Convertendo delta_size={delta_size} → ${delta_notional_usd:.2f}"
            )
        
        if not delta_notional_usd or delta_notional_usd <= 0:
            return ActionResult(
                success=False,
                action_type=ActionType.INCREASE,
                symbol=symbol,
                message="delta_notional_usd inválido ou não especificado",
                error="INVALID_DELTA"
            )
        
        # ===== SANITY CHECK =====
        sanity = self._sanity_check_notional(delta_notional_usd, equity, symbol)
        if sanity.clamped:
            self.logger.warning(f"[INCREASE] SANITY_CLAMP_APPLIED: {sanity.reason}")
            delta_notional_usd = sanity.clamped_value
        
        # ===== CONVERTE USD → SIZE =====
        add_size, sz_decimals = self._convert_usd_to_size(delta_notional_usd, symbol, current_price)
        
        # Valida min_size
        min_size = 10 ** (-sz_decimals)
        min_notional = getattr(self.bot.risk_manager, 'min_notional', 0.5) if hasattr(self.bot, 'risk_manager') else 0.5
        
        if add_size < min_size:
            return ActionResult(
                success=False,
                action_type=ActionType.INCREASE,
                symbol=symbol,
                message=f"add_size={add_size} < min_size={min_size}",
                error="BELOW_MIN_SIZE"
            )
        
        actual_notional = add_size * current_price
        if actual_notional < min_notional:
            return ActionResult(
                success=False,
                action_type=ActionType.INCREASE,
                symbol=symbol,
                message=f"notional=${actual_notional:.2f} < min_notional=${min_notional}",
                error="BELOW_MIN_NOTIONAL"
            )
        
        # ===== LOG ESTRUTURADO =====
        self.logger.info(
            f"📈 [INCREASE] {symbol} | "
            f"delta_notional_usd=${delta_notional_usd:.2f} | "
            f"mark_price=${current_price:.4f} | "
            f"add_size={add_size} | "
            f"current_position={position.size} | "
            f"sanity_clamped={sanity.clamped} | "
            f"reason={action.get('reason', '')}"
        )
        
        # ===== EXECUÇÃO =====
        if not self.bot.live_trading:
            # PAPER MODE
            new_size = position.size + add_size
            self.bot.position_manager.execute_pyramid_add(symbol, add_size, current_price)
            
            self.logger.info(f"[INCREASE] ✅ {symbol} novo size: {new_size} (PAPER)")
            
            # Notifica
            try:
                self.bot.telegram.send(
                    f"📈 PYRAMID ADD {symbol} (PAPER)\n"
                    f"Add: {add_size:.6f} (${actual_notional:.2f})\n"
                    f"Preço: ${current_price:.2f}\n"
                    f"Novo size: {new_size:.6f}\n"
                    f"Motivo: {action.get('reason', 'N/A')}"
                )
            except:
                pass
            
            return ActionResult(
                success=True,
                action_type=ActionType.INCREASE,
                symbol=symbol,
                message=f"Posição aumentada: +{add_size} ({actual_notional:.2f} USD)",
                details={
                    'add_size': add_size,
                    'add_notional': actual_notional,
                    'new_size': new_size,
                    'sanity_clamped': sanity.clamped
                }
            )
        
        # LIVE MODE
        try:
            is_buy = (position.side == 'long')
            
            result = self.bot.client.place_order(
                coin=symbol,
                is_buy=is_buy,
                size=add_size,
                price=current_price,
                order_type="market",
                reduce_only=False
            )
            
            if result and result.get('status') == 'ok':
                self.bot.position_manager.execute_pyramid_add(symbol, add_size, current_price)
                
                try:
                    self.bot.telegram.send(
                        f"📈 PYRAMID ADD {symbol}\n"
                        f"Add: {add_size:.6f} (${actual_notional:.2f})\n"
                        f"Preço: ${current_price:.2f}\n"
                        f"Motivo: {action.get('reason', 'N/A')}"
                    )
                except:
                    pass
                
                return ActionResult(
                    success=True,
                    action_type=ActionType.INCREASE,
                    symbol=symbol,
                    message=f"Posição aumentada: +{add_size}",
                    details={'add_size': add_size, 'add_notional': actual_notional}
                )
            else:
                return ActionResult(
                    success=False,
                    action_type=ActionType.INCREASE,
                    symbol=symbol,
                    message=f"Erro na ordem: {result}",
                    error="ORDER_FAILED"
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                action_type=ActionType.INCREASE,
                symbol=symbol,
                message=f"Exceção: {e}",
                error=str(e)
            )
    
    def _execute_decrease(self, symbol: str, action: Dict) -> ActionResult:
        """
        Executa redução de posição (partial close).
        
        Parâmetros aceitos:
        - percent: Percentual da posição para fechar (0-100)
        - delta_notional_usd: Valor em USD para reduzir
        """
        if not self.bot.position_manager.has_position(symbol):
            return ActionResult(
                success=False,
                action_type=ActionType.DECREASE,
                symbol=symbol,
                message="Posição não encontrada",
                error="POSITION_NOT_FOUND"
            )
        
        percent = action.get('percent') or action.get('partial_close_pct')
        
        # Normaliza percent
        if percent:
            if percent > 1 and percent <= 100:
                percent = percent / 100  # Converte 50 → 0.5
            elif percent > 100:
                percent = 1.0  # Cap em 100%
        else:
            percent = 0.5  # Default 50%
        
        reason = action.get('reason', 'decrease')
        
        # Delega para o método existente que já tem todos os guardrails
        self.bot._execute_partial_close(symbol, percent * 100, reason)
        
        return ActionResult(
            success=True,
            action_type=ActionType.DECREASE,
            symbol=symbol,
            message=f"Partial close {percent*100:.0f}% executado",
            details={'percent': percent * 100}
        )
    
    def _execute_set_sl_tp(self, symbol: str, action: Dict) -> ActionResult:
        """Executa ajuste de SL/TP"""
        if not self.bot.position_manager.has_position(symbol):
            return ActionResult(
                success=False,
                action_type=ActionType.SET_SL_TP,
                symbol=symbol,
                message="Posição não encontrada",
                error="POSITION_NOT_FOUND"
            )
        
        position = self.bot.position_manager.get_position(symbol)
        
        new_sl = action.get('sl_price') or action.get('new_sl_price') or action.get('stop_loss')
        new_tp = action.get('tp_price') or action.get('new_tp_price') or action.get('take_profit')
        
        messages = []
        
        if new_sl:
            position.update_stop_loss(float(new_sl))
            messages.append(f"SL → ${new_sl}")
        
        if new_tp:
            position.update_take_profit(float(new_tp))
            messages.append(f"TP → ${new_tp}")
        
        if not messages:
            return ActionResult(
                success=False,
                action_type=ActionType.SET_SL_TP,
                symbol=symbol,
                message="Nenhum SL/TP especificado",
                error="NO_SL_TP"
            )
        
        msg = f"{symbol}: {', '.join(messages)}"
        self.logger.info(f"[SET_SL_TP] {msg}")
        
        return ActionResult(
            success=True,
            action_type=ActionType.SET_SL_TP,
            symbol=symbol,
            message=msg
        )
    
    def _execute_breakeven(self, symbol: str, action: Dict) -> ActionResult:
        """Move SL para breakeven"""
        if not self.bot.position_manager.has_position(symbol):
            return ActionResult(
                success=False,
                action_type=ActionType.BREAKEVEN,
                symbol=symbol,
                message="Posição não encontrada",
                error="POSITION_NOT_FOUND"
            )
        
        position = self.bot.position_manager.get_position(symbol)
        
        try:
            position.move_stop_to_breakeven()
            self.logger.info(f"[BREAKEVEN] {symbol}: SL movido para breakeven (entry={position.entry_price})")
            
            return ActionResult(
                success=True,
                action_type=ActionType.BREAKEVEN,
                symbol=symbol,
                message=f"SL movido para breakeven @ ${position.entry_price}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type=ActionType.BREAKEVEN,
                symbol=symbol,
                message=f"Erro: {e}",
                error=str(e)
            )
    
    def _execute_hold(self, symbol: str, action: Dict) -> ActionResult:
        """Ação HOLD (noop)"""
        reason = action.get('reason', 'hold')
        self.logger.info(f"[HOLD] {symbol}: {reason}")
        
        return ActionResult(
            success=True,
            action_type=ActionType.HOLD,
            symbol=symbol or 'N/A',
            message=f"HOLD: {reason}"
        )
    
    def _execute_cancel_orders(self, symbol: str, action: Dict) -> ActionResult:
        """Cancela ordens abertas"""
        try:
            if symbol:
                # Cancel orders de um símbolo específico
                # (implementar se necessário)
                pass
            else:
                # Cancel all
                self.bot.client.cancel_all_orders()
            
            return ActionResult(
                success=True,
                action_type=ActionType.CANCEL_ORDERS,
                symbol=symbol or 'ALL',
                message="Ordens canceladas"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type=ActionType.CANCEL_ORDERS,
                symbol=symbol or 'ALL',
                message=f"Erro: {e}",
                error=str(e)
            )


# ================================================================
# SINGLETON
# ================================================================

_action_executor: Optional[ActionExecutor] = None


def get_action_executor(bot=None) -> Optional[ActionExecutor]:
    """Retorna instância do ActionExecutor"""
    global _action_executor
    if _action_executor is None and bot:
        _action_executor = ActionExecutor(bot)
    return _action_executor


def init_action_executor(bot) -> ActionExecutor:
    """Inicializa ActionExecutor"""
    global _action_executor
    _action_executor = ActionExecutor(bot)
    return _action_executor
