"""
Phase 4 - Trade Logger
Sistema de logging persistente de todos os eventos de trading
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TradeLogger:
    """
    Trade Logger - Sistema persistente de logging
    
    Loga todos eventos:
    - entry: Abertura de trade
    - close: Fechamento completo
    - partial: Fechamento parcial
    - stop_move: Stop loss movido
    - tp_move: Take profit movido
    - rejection: Rejeitado pelo Quality Gate
    - cancel: Cancelado por conflito
    - skip: Ignorado por regime
    """
    
    def __init__(self, log_file: str = "data/trade_log.jsonl"):
        """
        Inicializa Trade Logger
        
        Args:
            log_file: Caminho do arquivo JSONL
        """
        self.log_file = Path(log_file)
        
        # Garante que diretório existe
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Cria arquivo se não existir
        if not self.log_file.exists():
            self.log_file.touch()
        
        logger.info(f"[TRADE LOGGER] Inicializado: {self.log_file}")
    
    def log_entry(self,
                 symbol: str,
                 side: str,
                 entry_price: float,
                 size: float,
                 stop_price: float,
                 tp_price: float,
                 ai_type: str,
                 strategy: str,
                 confidence: float,
                 regime: Optional[Dict[str, Any]] = None,
                 quality_gate: Optional[Dict[str, Any]] = None,
                 **kwargs) -> None:
        """
        Loga abertura de trade
        
        Args:
            symbol: Símbolo
            side: long ou short
            entry_price: Preço de entrada
            size: Tamanho da posição
            stop_price: Stop loss
            tp_price: Take profit
            ai_type: swing ou scalp
            strategy: Nome da estratégia
            confidence: Confiança (0-1)
            regime: Info de regime de mercado
            quality_gate: Info do quality gate
        """
        try:
            event = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'type': 'entry',
                'symbol': symbol,
                'side': side,
                'entry': entry_price,
                'size': size,
                'stop_loss': stop_price,
                'take_profit': tp_price,
                'ai': ai_type,
                'strategy': strategy,
                'confidence': round(confidence, 3),
                'regime': regime or {},
                'quality_gate': quality_gate or {},
                **kwargs
            }
            
            self._write_event(event)
            logger.debug(f"[TRADE LOGGER] Entry logged: {symbol} {side}")
            
        except Exception as e:
            logger.error(f"[TRADE LOGGER] Erro ao logar entry: {e}", exc_info=True)
    
    def log_close(self,
                 symbol: str,
                 side: str,
                 entry_price: float,
                 exit_price: float,
                 size: float,
                 pnl_value: float,
                 pnl_percent: float,
                 rr: Optional[float],
                 duration_seconds: float,
                 reason: str,
                 ai_type: str,
                 strategy: str,
                 **kwargs) -> None:
        """
        Loga fechamento de trade
        
        Args:
            symbol: Símbolo
            side: long ou short
            entry_price: Preço de entrada
            exit_price: Preço de saída
            size: Tamanho
            pnl_value: PnL em USD
            pnl_percent: PnL em %
            rr: R-múltiplo (se disponível)
            duration_seconds: Duração em segundos
            reason: TP_hit, SL_hit, breakeven, manual_close
            ai_type: swing ou scalp
            strategy: Nome da estratégia
        """
        try:
            event = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'type': 'close',
                'symbol': symbol,
                'side': side,
                'entry': entry_price,
                'exit': exit_price,
                'size': size,
                'pnl_value': round(pnl_value, 2),
                'pnl_percent': round(pnl_percent, 2),
                'rr': round(rr, 2) if rr is not None else None,
                'duration': self._format_duration(duration_seconds),
                'duration_seconds': duration_seconds,
                'reason': reason,
                'ai': ai_type,
                'strategy': strategy,
                **kwargs
            }
            
            self._write_event(event)
            logger.info(f"[TRADE LOGGER] Close logged: {symbol} PnL={pnl_percent:.2f}% ({reason})")
            
        except Exception as e:
            logger.error(f"[TRADE LOGGER] Erro ao logar close: {e}", exc_info=True)
    
    def log_partial(self,
                   symbol: str,
                   side: str,
                   entry_price: float,
                   partial_price: float,
                   size_closed: float,
                   size_remaining: float,
                   pnl_value: float,
                   pnl_percent: float,
                   rr: Optional[float],
                   reason: str,
                   **kwargs) -> None:
        """
        Loga fechamento parcial
        
        Args:
            symbol: Símbolo
            side: long ou short
            entry_price: Preço de entrada original
            partial_price: Preço do parcial
            size_closed: Tamanho fechado
            size_remaining: Tamanho restante
            pnl_value: PnL do parcial
            pnl_percent: PnL % do parcial
            rr: R-múltiplo
            reason: Motivo (ex: 2R_partial)
        """
        try:
            event = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'type': 'partial',
                'symbol': symbol,
                'side': side,
                'entry': entry_price,
                'exit': partial_price,
                'size_closed': size_closed,
                'size_remaining': size_remaining,
                'pnl_value': round(pnl_value, 2),
                'pnl_percent': round(pnl_percent, 2),
                'rr': round(rr, 2) if rr is not None else None,
                'reason': reason,
                **kwargs
            }
            
            self._write_event(event)
            logger.info(f"[TRADE LOGGER] Partial logged: {symbol} {pnl_percent:.2f}% ({reason})")
            
        except Exception as e:
            logger.error(f"[TRADE LOGGER] Erro ao logar partial: {e}", exc_info=True)
    
    def log_stop_move(self,
                     symbol: str,
                     old_stop: float,
                     new_stop: float,
                     reason: str,
                     rr: Optional[float] = None,
                     **kwargs) -> None:
        """
        Loga movimento de stop loss
        
        Args:
            symbol: Símbolo
            old_stop: Stop antigo
            new_stop: Stop novo
            reason: breakeven, trailing, manual
            rr: R-múltiplo atual
        """
        try:
            event = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'type': 'stop_move',
                'symbol': symbol,
                'old_stop': old_stop,
                'new_stop': new_stop,
                'reason': reason,
                'rr': round(rr, 2) if rr is not None else None,
                **kwargs
            }
            
            self._write_event(event)
            logger.debug(f"[TRADE LOGGER] Stop move logged: {symbol} {old_stop} → {new_stop}")
            
        except Exception as e:
            logger.error(f"[TRADE LOGGER] Erro ao logar stop_move: {e}", exc_info=True)
    
    def log_tp_move(self,
                   symbol: str,
                   old_tp: float,
                   new_tp: float,
                   reason: str,
                   **kwargs) -> None:
        """
        Loga movimento de take profit
        
        Args:
            symbol: Símbolo
            old_tp: TP antigo
            new_tp: TP novo
            reason: Motivo
        """
        try:
            event = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'type': 'tp_move',
                'symbol': symbol,
                'old_tp': old_tp,
                'new_tp': new_tp,
                'reason': reason,
                **kwargs
            }
            
            self._write_event(event)
            logger.debug(f"[TRADE LOGGER] TP move logged: {symbol} {old_tp} → {new_tp}")
            
        except Exception as e:
            logger.error(f"[TRADE LOGGER] Erro ao logar tp_move: {e}", exc_info=True)
    
    def log_rejection(self,
                     symbol: str,
                     side: str,
                     confidence: float,
                     ai_type: str,
                     strategy: str,
                     reasons: list,
                     regime: Optional[Dict[str, Any]] = None,
                     quality_gate: Optional[Dict[str, Any]] = None,
                     **kwargs) -> None:
        """
        Loga trade rejeitado pelo Quality Gate
        
        Args:
            symbol: Símbolo
            side: long ou short
            confidence: Confiança original
            ai_type: swing ou scalp
            strategy: Estratégia
            reasons: Razões da rejeição
            regime: Info de regime
            quality_gate: Info do quality gate
        """
        try:
            event = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'type': 'rejection',
                'symbol': symbol,
                'side': side,
                'confidence': round(confidence, 3),
                'ai': ai_type,
                'strategy': strategy,
                'reasons': reasons,
                'regime': regime or {},
                'quality_gate': quality_gate or {},
                **kwargs
            }
            
            self._write_event(event)
            logger.debug(f"[TRADE LOGGER] Rejection logged: {symbol} ({', '.join(reasons)})")
            
        except Exception as e:
            logger.error(f"[TRADE LOGGER] Erro ao logar rejection: {e}", exc_info=True)
    
    def log_skip(self,
                symbol: str,
                reason: str,
                regime: Optional[Dict[str, Any]] = None,
                **kwargs) -> None:
        """
        Loga trade ignorado (por regime, chop, etc)
        
        Args:
            symbol: Símbolo
            reason: Motivo
            regime: Info de regime
        """
        try:
            event = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'type': 'skip',
                'symbol': symbol,
                'reason': reason,
                'regime': regime or {},
                **kwargs
            }
            
            self._write_event(event)
            logger.debug(f"[TRADE LOGGER] Skip logged: {symbol} ({reason})")
            
        except Exception as e:
            logger.error(f"[TRADE LOGGER] Erro ao logar skip: {e}", exc_info=True)
    
    def _write_event(self, event: Dict[str, Any]) -> None:
        """
        Escreve evento no arquivo JSONL
        
        Args:
            event: Dicionário do evento
        """
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                json.dump(event, f, ensure_ascii=False)
                f.write('\n')
        except Exception as e:
            logger.error(f"[TRADE LOGGER] Erro ao escrever evento: {e}", exc_info=True)
    
    def _format_duration(self, seconds: float) -> str:
        """
        Formata duração em formato legível
        
        Args:
            seconds: Duração em segundos
            
        Returns:
            String formatada (ex: "2h 15m")
        """
        try:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            
            if hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
        except:
            return "N/A"
