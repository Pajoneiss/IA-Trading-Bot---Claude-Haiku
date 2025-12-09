"""
Phase 8 - Execution Manager
Controla execução: LIVE, PAPER, SHADOW
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from bot.phase8.execution_config import ExecutionMode, get_active_shadow_configs
from bot.phase8.paper_portfolio import PaperPortfolio

logger = logging.getLogger(__name__)


class ExecutionManager:
    """Gerencia execução de trades (LIVE/PAPER/SHADOW)"""
    
    STATE_FILE = "data/execution_state.json"
    
    def __init__(self, trade_journal=None, logger_instance=None):
        self.logger = logger_instance or logger
        self.trade_journal = trade_journal
        
        # Estado de execução
        self.execution_mode = ExecutionMode.LIVE
        self.paper_portfolio = PaperPortfolio(logger_instance=self.logger)
        
        self._load_state()
        self.logger.info(f"[EXECUTION] Modo: {self.execution_mode.value}")
    
    def set_mode(self, mode: ExecutionMode, source: str = "manual") -> bool:
        """
        Altera modo de execução
        
        Args:
            mode: Novo modo
            source: Origem da mudança
            
        Returns:
            True se sucesso
        """
        try:
            old_mode = self.execution_mode
            self.execution_mode = mode
            
            self.logger.info(
                f"[EXECUTION] Modo alterado: {old_mode.value} -> {mode.value} "
                f"(fonte: {source})"
            )
            
            self._save_state()
            return True
            
        except Exception as e:
            self.logger.error(f"[EXECUTION] Erro ao alterar modo: {e}")
            return False
    
    def should_execute_live(self) -> bool:
        """Retorna se deve executar ordens reais"""
        return self.execution_mode in [ExecutionMode.LIVE, ExecutionMode.SHADOW]
    
    def should_execute_paper(self) -> bool:
        """Retorna se deve executar ordens paper"""
        return self.execution_mode in [ExecutionMode.PAPER_ONLY, ExecutionMode.SHADOW]
    
    def execute_paper_trade(self, decision: Dict[str, Any], current_price: float,
                           paper_profile: str = "GLOBAL_PAPER") -> Optional[str]:
        """
        Executa trade paper
        
        Args:
            decision: Decisão de trade
            current_price: Preço atual
            paper_profile: Perfil do paper
            
        Returns:
            Position ID ou None
        """
        try:
            if not self.should_execute_paper():
                return None
            
            return self.paper_portfolio.open_position(decision, current_price, paper_profile)
            
        except Exception as e:
            self.logger.error(f"[PAPER] Erro ao executar paper trade: {e}")
            return None
    
    def process_shadow_experiments(self, decision: Dict[str, Any], 
                                   current_price: float) -> List[str]:
        """
        Processa experimentos shadow
        
        Args:
            decision: Decisão original (que vai ser executada no LIVE)
            current_price: Preço atual
            
        Returns:
            Lista de position IDs dos shadows criados
        """
        shadow_positions = []
        
        try:
            if self.execution_mode != ExecutionMode.SHADOW:
                return []
            
            symbol = decision.get('symbol')
            style = decision.get('style')
            
            # Para cada shadow config ativo
            for name, config in get_active_shadow_configs().items():
                # Verifica se se aplica
                if config.get('style') and config['style'] != style:
                    continue
                
                if config.get('symbols'):
                    if symbol not in config['symbols']:
                        continue
                
                # Cria decisão shadow modificada
                shadow_decision = decision.copy()
                
                # Aplica multiplicadores
                risk_mult = config.get('risk_multiplier', 1.0)
                tp_mult = config.get('take_profit_multiplier', 1.0)
                sl_mult = config.get('stop_loss_multiplier', 1.0)
                
                shadow_decision['risk_pct'] = decision.get('risk_pct', 0.5) * risk_mult
                
                # Ajusta stops e targets
                if 'take_profit' in decision:
                    entry = decision.get('entry_price', current_price)
                    side = decision.get('side')
                    tp_distance = abs(decision['take_profit'] - entry)
                    
                    if side == 'LONG':
                        shadow_decision['take_profit'] = entry + (tp_distance * tp_mult)
                    else:
                        shadow_decision['take_profit'] = entry - (tp_distance * tp_mult)
                
                if 'stop_loss' in decision:
                    entry = decision.get('entry_price', current_price)
                    side = decision.get('side')
                    sl_distance = abs(entry - decision['stop_loss'])
                    
                    if side == 'LONG':
                        shadow_decision['stop_loss'] = entry - (sl_distance * sl_mult)
                    else:
                        shadow_decision['stop_loss'] = entry + (sl_distance * sl_mult)
                
                # Executa shadow
                paper_profile = f"SHADOW:{name}"
                pos_id = self.execute_paper_trade(shadow_decision, current_price, paper_profile)
                
                if pos_id:
                    shadow_positions.append(pos_id)
                    self.logger.info(f"[SHADOW] Experimento '{name}' criado para {symbol}")
            
        except Exception as e:
            self.logger.error(f"[SHADOW] Erro ao processar experiments: {e}")
        
        return shadow_positions
    
    def update_paper_positions(self, current_prices: Dict[str, float]):
        """
        Atualiza posições paper (verifica stops/targets)
        
        Args:
            current_prices: Preços atuais por símbolo
        """
        try:
            closed_trades = self.paper_portfolio.check_stops_and_targets(current_prices)
            
            # Registra no journal
            if self.trade_journal and closed_trades:
                for trade_data in closed_trades:
                    self.trade_journal.log_trade(trade_data)
            
        except Exception as e:
            self.logger.error(f"[PAPER] Erro ao atualizar posições: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status de execução"""
        return {
            'mode': self.execution_mode.value,
            'paper_portfolio': self.paper_portfolio.get_status(),
            'shadow_configs': get_active_shadow_configs()
        }
    
    def _load_state(self):
        """Carrega estado do disco"""
        try:
            state_file = Path(self.STATE_FILE)
            
            if not state_file.exists():
                return
            
            with open(state_file, 'r') as f:
                data = json.load(f)
            
            mode_str = data.get('execution_mode', 'LIVE')
            self.execution_mode = ExecutionMode[mode_str]
            
            self.logger.info(f"[EXECUTION] Estado carregado: {self.execution_mode.value}")
            
        except Exception as e:
            self.logger.warning(f"[EXECUTION] Erro ao carregar estado: {e}")
            self.execution_mode = ExecutionMode.LIVE
    
    def _save_state(self):
        """Salva estado no disco"""
        try:
            state_file = Path(self.STATE_FILE)
            state_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'execution_mode': self.execution_mode.value
            }
            
            with open(state_file, 'w') as f:
                json.dump(data, f, indent=2)
            
        except Exception as e:
            self.logger.error(f"[EXECUTION] Erro ao salvar estado: {e}")
