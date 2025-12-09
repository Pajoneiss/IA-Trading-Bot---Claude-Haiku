"""
Phase 8 - Paper Portfolio Manager
Gerencia posições simuladas (paper e shadow)
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class PaperPortfolio:
    """Gerenciador de portfolio paper"""
    
    STATE_FILE = "data/paper_state.json"
    
    def __init__(self, initial_equity: float = 10000.0, logger_instance=None):
        self.logger = logger_instance or logger
        self.paper_equity_start = initial_equity
        self.paper_equity_current = initial_equity
        self.paper_positions = {}  # symbol -> position dict
        self.closed_trades_count = 0
        
        self._load_state()
        self.logger.info(f"[PAPER] Portfolio inicializado: ${self.paper_equity_current:.2f}")
    
    def open_position(self, decision: Dict[str, Any], current_price: float, 
                     paper_profile: str = "GLOBAL_PAPER") -> Optional[str]:
        """
        Abre posição paper
        
        Args:
            decision: Decisão de trade
            current_price: Preço atual
            paper_profile: Perfil (GLOBAL_PAPER ou SHADOW:xxx)
            
        Returns:
            Position ID ou None se falhou
        """
        try:
            symbol = decision.get('symbol')
            side = decision.get('side')
            
            if not symbol or not side:
                return None
            
            # Gera ID único
            pos_id = f"{symbol}_{side}_{paper_profile}_{datetime.utcnow().timestamp()}"
            
            # Calcula tamanho
            risk_pct = decision.get('risk_pct', 0.5)
            size_usd = self.paper_equity_current * (risk_pct / 100)
            
            # Cria posição
            position = {
                'id': pos_id,
                'symbol': symbol,
                'side': side,
                'style': decision.get('style', 'SWING'),
                'source': decision.get('source', 'unknown'),
                'entry_price': current_price,
                'size_usd': size_usd,
                'stop_loss': decision.get('stop_loss', current_price * 0.98),
                'take_profit': decision.get('take_profit', current_price * 1.02),
                'timestamp_open': datetime.utcnow().isoformat(),
                'paper_profile': paper_profile,
                'strategy_tag': decision.get('strategy_tag', 'UNKNOWN'),
                'reason': decision.get('reason', '')
            }
            
            self.paper_positions[pos_id] = position
            self._save_state()
            
            self.logger.info(
                f"[PAPER] Posição aberta: {symbol} {side} @ ${current_price:.2f} "
                f"({paper_profile})"
            )
            
            return pos_id
            
        except Exception as e:
            self.logger.error(f"[PAPER] Erro ao abrir posição: {e}")
            return None
    
    def close_position(self, pos_id: str, exit_price: float, reason: str = "manual") -> Optional[Dict]:
        """
        Fecha posição paper
        
        Args:
            pos_id: ID da posição
            exit_price: Preço de saída
            reason: Motivo do fechamento
            
        Returns:
            Trade data para journal ou None
        """
        try:
            if pos_id not in self.paper_positions:
                return None
            
            pos = self.paper_positions[pos_id]
            
            # Calcula PnL
            entry = pos['entry_price']
            multiplier = 1 if pos['side'] == 'LONG' else -1
            pnl_pct = ((exit_price - entry) / entry) * 100 * multiplier
            pnl_abs = (pos['size_usd'] * pnl_pct) / 100
            
            # Atualiza equity
            self.paper_equity_current += pnl_abs
            
            # Cria registro para journal
            timestamp_close = datetime.utcnow().isoformat()
            timestamp_open = pos['timestamp_open']
            
            # Calcula duração
            try:
                t_open = datetime.fromisoformat(timestamp_open.replace('Z', '+00:00'))
                t_close = datetime.fromisoformat(timestamp_close.replace('Z', '+00:00'))
                duration_minutes = (t_close - t_open).total_seconds() / 60
            except:
                duration_minutes = 0
            
            trade_data = {
                'timestamp_open': timestamp_open,
                'timestamp_close': timestamp_close,
                'duration_minutes': duration_minutes,
                'symbol': pos['symbol'],
                'side': pos['side'],
                'style': pos['style'],
                'source': pos['source'],
                'entry_price': entry,
                'exit_price': exit_price,
                'stop_loss_price': pos.get('stop_loss'),
                'take_profit_price': pos.get('take_profit'),
                'pnl_abs': pnl_abs,
                'pnl_pct': pnl_pct,
                'reason_summary': pos.get('reason', '')[:200],
                'strategy_tag': pos.get('strategy_tag', 'UNKNOWN'),
                'is_paper': True,
                'paper_profile': pos['paper_profile']
            }
            
            # Remove posição
            del self.paper_positions[pos_id]
            self.closed_trades_count += 1
            self._save_state()
            
            self.logger.info(
                f"[PAPER] Posição fechada: {pos['symbol']} {pos['side']} | "
                f"PnL: {pnl_pct:+.2f}% (${pnl_abs:+.2f}) | Reason: {reason}"
            )
            
            return trade_data
            
        except Exception as e:
            self.logger.error(f"[PAPER] Erro ao fechar posição: {e}")
            return None
    
    def check_stops_and_targets(self, current_prices: Dict[str, float]) -> List[Dict]:
        """
        Verifica stops e targets das posições abertas
        
        Args:
            current_prices: Dict com preços atuais por símbolo
            
        Returns:
            Lista de trades fechados
        """
        closed_trades = []
        positions_to_close = []
        
        try:
            for pos_id, pos in self.paper_positions.items():
                symbol = pos['symbol']
                
                if symbol not in current_prices:
                    continue
                
                current_price = current_prices[symbol]
                side = pos['side']
                
                # Verifica stop loss
                if side == 'LONG' and current_price <= pos.get('stop_loss', 0):
                    positions_to_close.append((pos_id, current_price, 'stop_loss'))
                elif side == 'SHORT' and current_price >= pos.get('stop_loss', float('inf')):
                    positions_to_close.append((pos_id, current_price, 'stop_loss'))
                
                # Verifica take profit
                elif side == 'LONG' and current_price >= pos.get('take_profit', float('inf')):
                    positions_to_close.append((pos_id, current_price, 'take_profit'))
                elif side == 'SHORT' and current_price <= pos.get('take_profit', 0):
                    positions_to_close.append((pos_id, current_price, 'take_profit'))
            
            # Fecha posições
            for pos_id, exit_price, reason in positions_to_close:
                trade_data = self.close_position(pos_id, exit_price, reason)
                if trade_data:
                    closed_trades.append(trade_data)
            
        except Exception as e:
            self.logger.error(f"[PAPER] Erro ao verificar stops: {e}")
        
        return closed_trades
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status do portfolio"""
        return {
            'equity_start': self.paper_equity_start,
            'equity_current': self.paper_equity_current,
            'pnl_total': self.paper_equity_current - self.paper_equity_start,
            'pnl_pct': ((self.paper_equity_current - self.paper_equity_start) / self.paper_equity_start) * 100,
            'open_positions': len(self.paper_positions),
            'closed_trades': self.closed_trades_count
        }
    
    def _load_state(self):
        """Carrega estado do disco"""
        try:
            state_file = Path(self.STATE_FILE)
            
            if not state_file.exists():
                return
            
            with open(state_file, 'r') as f:
                data = json.load(f)
            
            self.paper_equity_start = data.get('equity_start', self.paper_equity_start)
            self.paper_equity_current = data.get('equity_current', self.paper_equity_current)
            self.paper_positions = data.get('positions', {})
            self.closed_trades_count = data.get('closed_trades', 0)
            
            self.logger.info(f"[PAPER] Estado carregado: {len(self.paper_positions)} posições abertas")
            
        except Exception as e:
            self.logger.warning(f"[PAPER] Erro ao carregar estado: {e}")
    
    def _save_state(self):
        """Salva estado no disco"""
        try:
            state_file = Path(self.STATE_FILE)
            state_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'equity_start': self.paper_equity_start,
                'equity_current': self.paper_equity_current,
                'positions': self.paper_positions,
                'closed_trades': self.closed_trades_count
            }
            
            with open(state_file, 'w') as f:
                json.dump(data, f, indent=2)
            
        except Exception as e:
            self.logger.error(f"[PAPER] Erro ao salvar estado: {e}")
