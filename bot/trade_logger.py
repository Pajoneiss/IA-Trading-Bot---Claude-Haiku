"""
Trade Logger - Logging estruturado para análise
Salva trades em CSV para backtest e métricas.
"""
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TradeLogger:
    """Logger estruturado de trades para análise posterior"""
    
    CSV_FILE = "data/trades_log.csv"
    JSON_FILE = "data/trades_log.json"
    
    CSV_FIELDS = [
        'timestamp',
        'symbol', 
        'action',
        'side',
        'entry_price',
        'size',
        'notional_usd',
        'leverage',
        'stop_loss',
        'take_profit',
        'confidence',
        'regime',
        'trend_bias',
        'ai_type',
        'reason',
        'execution_mode',
        'trade_id'
    ]
    
    def __init__(self, logger_instance=None):
        self.log = logger_instance or logger
        self._ensure_csv_header()
    
    def _ensure_csv_header(self):
        """Garante que o CSV tem header"""
        csv_path = Path(self.CSV_FILE)
        if not csv_path.exists():
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            with open(csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_FIELDS)
                writer.writeheader()
            self.log.info(f"[TRADE LOGGER] Criado arquivo {self.CSV_FILE}")
    
    def log_trade(self, 
                  symbol: str,
                  action: str,
                  side: str,
                  entry_price: float,
                  size: float,
                  confidence: float,
                  regime: str = "UNKNOWN",
                  trend_bias: str = "neutral",
                  ai_type: str = "swing",
                  reason: str = "",
                  stop_loss: float = 0,
                  take_profit: float = 0,
                  leverage: float = 1,
                  execution_mode: str = "PAPER",
                  trade_id: str = None,
                  extra: Dict[str, Any] = None) -> bool:
        """
        Loga um trade no CSV e JSON
        
        Args:
            symbol: Par de trading
            action: open, close, increase, reduce
            side: long, short
            entry_price: Preço de entrada
            size: Tamanho da posição
            confidence: Confiança da IA (0-1)
            regime: Regime de mercado
            trend_bias: Viés de tendência
            ai_type: swing ou scalp
            reason: Razão do trade
            stop_loss: Preço de stop
            take_profit: Preço de TP
            leverage: Alavancagem usada
            execution_mode: LIVE, PAPER, SHADOW
            trade_id: ID único do trade
            extra: Dados extras para JSON
            
        Returns:
            True se sucesso
        """
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            notional = entry_price * size
            
            if not trade_id:
                trade_id = f"{symbol}_{timestamp.replace(':', '-')}"
            
            # Dados para CSV
            row = {
                'timestamp': timestamp,
                'symbol': symbol,
                'action': action,
                'side': side,
                'entry_price': round(entry_price, 6),
                'size': round(size, 8),
                'notional_usd': round(notional, 2),
                'leverage': leverage,
                'stop_loss': round(stop_loss, 6) if stop_loss else 0,
                'take_profit': round(take_profit, 6) if take_profit else 0,
                'confidence': round(confidence, 3),
                'regime': regime,
                'trend_bias': trend_bias,
                'ai_type': ai_type,
                'reason': reason[:200] if reason else "",  # Limita tamanho
                'execution_mode': execution_mode,
                'trade_id': trade_id
            }
            
            # Escreve CSV
            with open(self.CSV_FILE, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_FIELDS)
                writer.writerow(row)
            
            # Escreve JSON (com dados extras)
            json_data = {**row, **(extra or {})}
            self._append_json(json_data)
            
            self.log.info(
                f"[TRADE LOGGER] {action.upper()} {side} {symbol} "
                f"@ {entry_price:.2f} | conf={confidence:.2f} | regime={regime}"
            )
            
            return True
            
        except Exception as e:
            self.log.error(f"[TRADE LOGGER] Erro ao logar trade: {e}")
            return False
    
    def _append_json(self, data: Dict[str, Any]):
        """Adiciona entrada ao JSON"""
        json_path = Path(self.JSON_FILE)
        
        try:
            if json_path.exists():
                with open(json_path, 'r') as f:
                    trades = json.load(f)
            else:
                trades = []
            
            trades.append(data)
            
            # Mantém últimos 1000 trades
            if len(trades) > 1000:
                trades = trades[-1000:]
            
            with open(json_path, 'w') as f:
                json.dump(trades, f, indent=2, default=str)
                
        except Exception as e:
            self.log.debug(f"[TRADE LOGGER] Erro ao escrever JSON: {e}")
    
    def get_recent_trades(self, limit: int = 50) -> list:
        """Retorna trades recentes do JSON"""
        try:
            json_path = Path(self.JSON_FILE)
            if json_path.exists():
                with open(json_path, 'r') as f:
                    trades = json.load(f)
                return trades[-limit:]
        except Exception:
            pass
        return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Calcula estatísticas básicas dos trades logados"""
        trades = self.get_recent_trades(limit=1000)
        
        if not trades:
            return {'total': 0}
        
        opens = [t for t in trades if t.get('action') == 'open']
        
        stats = {
            'total': len(trades),
            'opens': len(opens),
            'by_side': {
                'long': len([t for t in opens if t.get('side') == 'long']),
                'short': len([t for t in opens if t.get('side') == 'short'])
            },
            'by_regime': {},
            'avg_confidence': 0
        }
        
        # Por regime
        for t in opens:
            regime = t.get('regime', 'UNKNOWN')
            stats['by_regime'][regime] = stats['by_regime'].get(regime, 0) + 1
        
        # Confidence média
        confs = [t.get('confidence', 0) for t in opens if t.get('confidence')]
        if confs:
            stats['avg_confidence'] = round(sum(confs) / len(confs), 3)
        
        return stats


# Singleton
_trade_logger: Optional[TradeLogger] = None

def get_trade_logger(logger_instance=None) -> TradeLogger:
    """Retorna instância singleton do TradeLogger"""
    global _trade_logger
    if _trade_logger is None:
        _trade_logger = TradeLogger(logger_instance=logger_instance)
    return _trade_logger
