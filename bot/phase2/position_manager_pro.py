"""
Phase 2 - Position Manager Pro
Gestão avançada: breakeven, parciais, trailing baseado em R-múltiplo
"""
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PositionManagerPro:
    """
    Gestão avançada de posição
    
    Features:
    - Breakeven automático em 1R
    - Parciais em 2R (25-50%)
    - Trailing em 3R+
    - Baseado em R-múltiplo
    """
    
    def __init__(self, position_manager, config: Optional[Dict[str, Any]] = None):
        """
        Inicializa Position Manager Pro
        
        Args:
            position_manager: PositionManager original do bot
            config: Configurações opcionais
        """
        self.position_manager = position_manager
        self.config = config or {}
        
        # Configurações de gestão
        self.breakeven_at_r = self.config.get('breakeven_at_r', 1.0)  # Breakeven em 1R
        self.partial_at_r = self.config.get('partial_at_r', 2.0)      # Parcial em 2R
        self.partial_pct = self.config.get('partial_pct', 0.5)        # 50% de parcial
        self.trailing_at_r = self.config.get('trailing_at_r', 3.0)    # Trailing em 3R
        self.trailing_distance_pct = self.config.get('trailing_distance_pct', 1.0)  # 1% de distância
        
        # Estado interno - rastreia ações já executadas
        self.actions_taken = {}  # {symbol: {'breakeven': True, 'partial': True, 'trailing': True}}
        
        logger.info(f"[POSITION MANAGER PRO] Inicializado:")
        logger.info(f"  Breakeven: {self.breakeven_at_r}R")
        logger.info(f"  Parcial: {self.partial_at_r}R ({self.partial_pct*100:.0f}%)")
        logger.info(f"  Trailing: {self.trailing_at_r}R")
    
    def calculate_r_multiple(self, 
                            entry_price: float,
                            current_price: float,
                            stop_price: float,
                            side: str) -> float:
        """
        Calcula R-múltiplo da posição
        
        Args:
            entry_price: Preço de entrada
            current_price: Preço atual
            stop_price: Preço do stop loss
            side: 'long' ou 'short'
            
        Returns:
            R-múltiplo (ex: 2.5 = 2.5R)
        """
        try:
            if side.lower() == 'long':
                # R inicial = distância do entry até o stop
                r_initial = entry_price - stop_price
                
                # Lucro atual = distância do entry até o preço atual
                profit = current_price - entry_price
                
            else:  # short
                r_initial = stop_price - entry_price
                profit = entry_price - current_price
            
            # Se R inicial for zero ou negativo, retorna 0
            if r_initial <= 0:
                return 0.0
            
            # R-múltiplo = lucro / R inicial
            r_multiple = profit / r_initial
            
            return round(r_multiple, 2)
            
        except Exception as e:
            logger.error(f"[POSITION MANAGER PRO] Erro ao calcular R: {e}")
            return 0.0
    
    def analyze_position(self,
                        symbol: str,
                        current_price: float) -> Optional[Dict[str, Any]]:
        """
        Analisa posição e sugere gestão (breakeven, parcial, trailing)
        
        Args:
            symbol: Símbolo da posição
            current_price: Preço atual
            
        Returns:
            Dict com sugestão de manage_decision ou None
        """
        try:
            # Verifica se tem posição
            if not self.position_manager.has_position(symbol):
                return None
            
            position = self.position_manager.get_position(symbol)
            
            # Calcula R-múltiplo
            r_multiple = self.calculate_r_multiple(
                entry_price=position.entry_price,
                current_price=current_price,
                stop_price=position.stop_loss_price,
                side=position.side
            )
            
            # Inicializa rastreamento se não existir
            if symbol not in self.actions_taken:
                self.actions_taken[symbol] = {
                    'breakeven': False,
                    'partial': False,
                    'trailing': False,
                    'last_trailing_r': 0.0
                }
            
            actions = self.actions_taken[symbol]
            
            logger.debug(f"[POSITION MANAGER PRO] {symbol}: R={r_multiple:.2f} | "
                        f"BE={actions['breakeven']} | Partial={actions['partial']} | "
                        f"Trailing={actions['trailing']}")
            
            # === TRAILING (prioridade 1) ===
            if r_multiple >= self.trailing_at_r:
                trailing_suggestion = self._check_trailing(
                    symbol=symbol,
                    position=position,
                    current_price=current_price,
                    r_multiple=r_multiple
                )
                
                if trailing_suggestion:
                    return trailing_suggestion
            
            # === PARCIAL (prioridade 2) ===
            if r_multiple >= self.partial_at_r and not actions['partial']:
                return self._suggest_partial(
                    symbol=symbol,
                    position=position,
                    r_multiple=r_multiple
                )
            
            # === BREAKEVEN (prioridade 3) ===
            if r_multiple >= self.breakeven_at_r and not actions['breakeven']:
                return self._suggest_breakeven(
                    symbol=symbol,
                    position=position,
                    r_multiple=r_multiple
                )
            
            # Nenhuma ação necessária
            return None
            
        except Exception as e:
            logger.error(f"[POSITION MANAGER PRO] Erro ao analisar {symbol}: {e}", exc_info=True)
            return None
    
    def _suggest_breakeven(self,
                          symbol: str,
                          position: Any,
                          r_multiple: float) -> Dict[str, Any]:
        """Sugere mover stop para breakeven"""
        
        logger.info(f"[POSITION MANAGER PRO] 🎯 {symbol}: {r_multiple:.2f}R atingido - "
                   f"Sugerindo BREAKEVEN")
        
        # Marca como executado
        self.actions_taken[symbol]['breakeven'] = True
        
        return {
            'action': 'manage',
            'symbol': symbol,
            'style': position.strategy,  # scalp ou swing
            'source': 'position_manager_pro',
            'manage_decision': {
                'close_pct': 0.0,  # Não fecha nada
                'new_stop_price': position.entry_price,  # Stop no entry
                'new_take_profit_price': None,
                'reason': f'Breakeven em {r_multiple:.2f}R - proteção de lucro',
                'r_multiple': r_multiple
            }
        }
    
    def _suggest_partial(self,
                        symbol: str,
                        position: Any,
                        r_multiple: float) -> Dict[str, Any]:
        """Sugere parcial (fechar parte da posição)"""
        
        logger.info(f"[POSITION MANAGER PRO] 💰 {symbol}: {r_multiple:.2f}R atingido - "
                   f"Sugerindo PARCIAL {self.partial_pct*100:.0f}%")
        
        # Marca como executado
        self.actions_taken[symbol]['partial'] = True
        
        # Calcula novo stop (no lucro)
        if position.side.lower() == 'long':
            # Stop acima do entry (no lucro)
            new_stop = position.entry_price * 1.005  # 0.5% acima do entry
        else:  # short
            new_stop = position.entry_price * 0.995  # 0.5% abaixo do entry
        
        return {
            'action': 'manage',
            'symbol': symbol,
            'style': position.strategy,
            'source': 'position_manager_pro',
            'manage_decision': {
                'close_pct': self.partial_pct,  # Fecha 50%
                'new_stop_price': new_stop,  # Stop no lucro
                'new_take_profit_price': None,
                'reason': f'Parcial {self.partial_pct*100:.0f}% em {r_multiple:.2f}R + SL no lucro',
                'r_multiple': r_multiple
            }
        }
    
    def _check_trailing(self,
                       symbol: str,
                       position: Any,
                       current_price: float,
                       r_multiple: float) -> Optional[Dict[str, Any]]:
        """
        Verifica e sugere trailing stop
        
        Trailing é atualizado a cada 0.5R de movimento adicional
        """
        
        actions = self.actions_taken[symbol]
        last_trailing_r = actions.get('last_trailing_r', 0.0)
        
        # Só atualiza trailing se subiu pelo menos 0.5R desde a última vez
        if r_multiple < last_trailing_r + 0.5:
            return None
        
        logger.info(f"[POSITION MANAGER PRO] 📈 {symbol}: {r_multiple:.2f}R - "
                   f"Atualizando TRAILING STOP")
        
        # Marca última atualização
        self.actions_taken[symbol]['trailing'] = True
        self.actions_taken[symbol]['last_trailing_r'] = r_multiple
        
        # Calcula trailing stop (distância percentual do preço atual)
        if position.side.lower() == 'long':
            # Trailing abaixo do preço atual
            new_stop = current_price * (1 - self.trailing_distance_pct / 100)
            
            # Garante que está ACIMA do stop atual (nunca move para trás)
            new_stop = max(new_stop, position.stop_loss_price)
            
        else:  # short
            # Trailing acima do preço atual
            new_stop = current_price * (1 + self.trailing_distance_pct / 100)
            
            # Garante que está ABAIXO do stop atual
            new_stop = min(new_stop, position.stop_loss_price)
        
        return {
            'action': 'manage',
            'symbol': symbol,
            'style': position.strategy,
            'source': 'position_manager_pro',
            'manage_decision': {
                'close_pct': 0.0,
                'new_stop_price': new_stop,
                'new_take_profit_price': None,
                'reason': f'Trailing stop em {r_multiple:.2f}R ({self.trailing_distance_pct}% do preço)',
                'r_multiple': r_multiple
            }
        }
    
    def reset_position_tracking(self, symbol: str):
        """Reseta rastreamento quando posição é fechada"""
        if symbol in self.actions_taken:
            del self.actions_taken[symbol]
            logger.debug(f"[POSITION MANAGER PRO] Rastreamento de {symbol} resetado")
    
    def get_position_status(self, symbol: str, current_price: float) -> Dict[str, Any]:
        """
        Retorna status completo da posição
        
        Returns:
            {
                'r_multiple': 2.5,
                'breakeven_done': True,
                'partial_done': False,
                'trailing_active': False,
                'next_action': 'partial',
                'next_action_at_r': 2.0
            }
        """
        if not self.position_manager.has_position(symbol):
            return {'error': 'Position not found'}
        
        position = self.position_manager.get_position(symbol)
        
        r_multiple = self.calculate_r_multiple(
            entry_price=position.entry_price,
            current_price=current_price,
            stop_price=position.stop_loss_price,
            side=position.side
        )
        
        actions = self.actions_taken.get(symbol, {
            'breakeven': False,
            'partial': False,
            'trailing': False
        })
        
        # Determina próxima ação
        next_action = None
        next_action_at_r = None
        
        if not actions.get('breakeven') and r_multiple < self.breakeven_at_r:
            next_action = 'breakeven'
            next_action_at_r = self.breakeven_at_r
        elif not actions.get('partial') and r_multiple < self.partial_at_r:
            next_action = 'partial'
            next_action_at_r = self.partial_at_r
        elif r_multiple < self.trailing_at_r:
            next_action = 'trailing'
            next_action_at_r = self.trailing_at_r
        else:
            next_action = 'trailing_active'
        
        return {
            'r_multiple': r_multiple,
            'breakeven_done': actions.get('breakeven', False),
            'partial_done': actions.get('partial', False),
            'trailing_active': actions.get('trailing', False),
            'next_action': next_action,
            'next_action_at_r': next_action_at_r
        }
