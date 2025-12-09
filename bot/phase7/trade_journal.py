"""
Phase 7 - Trade Journal Estruturado
Sistema de journaling rico para análise de performance
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TradeJournal:
    """
    Journal estruturado de trades para análise avançada
    """
    
    JOURNAL_FILE = "data/trade_journal.jsonl"
    
    def __init__(self, logger_instance=None):
        """Inicializa Trade Journal"""
        self.logger = logger_instance or logger
        self._ensure_file_exists()
        self.logger.info("[JOURNAL] Trade Journal inicializado")
    
    def log_trade(self, trade_data: Dict[str, Any]) -> bool:
        """
        Registra trade completo no journal
        
        Args:
            trade_data: Dict com dados do trade
            
        Returns:
            True se sucesso
        """
        try:
            # Valida dados mínimos
            required = ['symbol', 'side', 'entry_price', 'exit_price', 'pnl_abs', 'pnl_pct']
            for field in required:
                if field not in trade_data:
                    self.logger.warning(f"[JOURNAL] Campo obrigatório ausente: {field}")
                    return False
            
            # Adiciona timestamp se não tiver
            if 'timestamp_close' not in trade_data:
                trade_data['timestamp_close'] = datetime.utcnow().isoformat()
            
            # Escreve no arquivo
            journal_path = Path(self.JOURNAL_FILE)
            
            with open(journal_path, 'a') as f:
                f.write(json.dumps(trade_data) + '\n')
            
            self.logger.debug(f"[JOURNAL] Trade registrado: {trade_data['symbol']} {trade_data['side']}")
            return True
            
        except Exception as e:
            self.logger.error(f"[JOURNAL][ERROR] Falha ao registrar trade: {e}")
            return False
    
    def get_recent_trades(self, limit: int = 10) -> list:
        """Retorna últimos N trades"""
        try:
            journal_path = Path(self.JOURNAL_FILE)
            
            if not journal_path.exists():
                return []
            
            trades = []
            with open(journal_path, 'r') as f:
                for line in f:
                    try:
                        trades.append(json.loads(line.strip()))
                    except:
                        continue
            
            return trades[-limit:]
            
        except Exception as e:
            self.logger.error(f"[JOURNAL] Erro ao ler trades: {e}")
            return []
    
    def get_all_trades(self) -> list:
        """Retorna todos os trades"""
        try:
            journal_path = Path(self.JOURNAL_FILE)
            
            if not journal_path.exists():
                return []
            
            trades = []
            with open(journal_path, 'r') as f:
                for line in f:
                    try:
                        trades.append(json.loads(line.strip()))
                    except:
                        continue
            
            return trades
            
        except Exception as e:
            self.logger.error(f"[JOURNAL] Erro ao ler todos trades: {e}")
            return []
    
    def _ensure_file_exists(self):
        """Garante que arquivo existe"""
        try:
            journal_path = Path(self.JOURNAL_FILE)
            journal_path.parent.mkdir(parents=True, exist_ok=True)
            
            if not journal_path.exists():
                journal_path.touch()
                
        except Exception as e:
            self.logger.error(f"[JOURNAL] Erro ao criar arquivo: {e}")
