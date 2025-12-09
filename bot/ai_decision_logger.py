"""
AI Decision Logger
Logs all AI decisions (SWING and SCALP) for diagnosis and debugging.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class AIDecisionLogger:
    """
    Logger dedicado para decisões de IA.
    Salva em /data/ai_decisions.jsonl para diagnóstico.
    """
    
    def __init__(self, log_dir: str = "data"):
        self.log_dir = log_dir
        self.log_file = os.path.join(log_dir, "ai_decisions.jsonl")
        
        # Cria diretório se não existir
        os.makedirs(log_dir, exist_ok=True)
        
        logger.info(f"📊 AIDecisionLogger inicializado: {self.log_file}")
    
    def log_decision(self,
                     decision_type: str,  # "SWING" ou "SCALP"
                     symbol: Optional[str],
                     action: str,  # "open", "hold", "close", etc.
                     direction: Optional[str] = None,  # "long", "short"
                     confidence: float = 0.0,
                     raw_reason: Optional[str] = None,
                     rejection_reason: Optional[str] = None,
                     rejected_by: Optional[str] = None,  # "quality_gate", "risk_manager", "confidence", etc.
                     extra_data: Optional[Dict[str, Any]] = None):
        """
        Loga uma decisão de IA para análise.
        
        Args:
            decision_type: SWING ou SCALP
            symbol: Símbolo do ativo (ex: BTC)
            action: Ação decidida (open, hold, close, etc.)
            direction: long ou short
            confidence: Confiança da decisão (0.0 a 1.0)
            raw_reason: Motivo textual dado pela IA
            rejection_reason: Se rejeitado, o motivo
            rejected_by: Componente que rejeitou (quality_gate, risk_manager, etc.)
            extra_data: Dados extras para diagnóstico
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        entry = {
            "timestamp": timestamp,
            "type": decision_type,
            "symbol": symbol,
            "action": action,
            "direction": direction,
            "confidence": confidence,
            "raw_reason": raw_reason,
            "rejected": rejection_reason is not None,
            "rejection_reason": rejection_reason,
            "rejected_by": rejected_by,
        }
        
        if extra_data:
            entry["extra"] = extra_data
        
        # Log estruturado para console
        if rejection_reason:
            logger.info(
                f"[DEBUG_DECISION] {decision_type} {symbol or 'N/A'} "
                f"action={action} direction={direction or 'N/A'} "
                f"confidence={confidence:.2f} → REJECTED by {rejected_by}: {rejection_reason}"
            )
        else:
            logger.info(
                f"[DEBUG_DECISION] {decision_type} {symbol or 'N/A'} "
                f"action={action} direction={direction or 'N/A'} "
                f"confidence={confidence:.2f} → APPROVED"
            )
        
        # Salva em arquivo JSONL
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.warning(f"Erro ao salvar decisão em arquivo: {e}")
    
    def log_swing_decision(self,
                           symbol: Optional[str],
                           decision_data: Dict[str, Any],
                           rejected: bool = False,
                           rejection_reason: Optional[str] = None,
                           rejected_by: Optional[str] = None):
        """Atalho para logar decisão SWING."""
        self.log_decision(
            decision_type="SWING",
            symbol=symbol,
            action=decision_data.get('action', 'unknown'),
            direction=decision_data.get('side'),
            confidence=decision_data.get('confidence', 0.0),
            raw_reason=decision_data.get('reason') or decision_data.get('rationale'),
            rejection_reason=rejection_reason if rejected else None,
            rejected_by=rejected_by if rejected else None,
            extra_data={
                'leverage': decision_data.get('leverage'),
                'size_usd': decision_data.get('size_usd'),
                'stop_loss_price': decision_data.get('stop_loss_price'),
                'take_profit_price': decision_data.get('take_profit_price'),
                'structural_stop_price': decision_data.get('structural_stop_price'),
            }
        )
    
    def log_scalp_decision(self,
                           symbol: Optional[str],
                           decision_data: Dict[str, Any],
                           rejected: bool = False,
                           rejection_reason: Optional[str] = None,
                           rejected_by: Optional[str] = None):
        """Atalho para logar decisão SCALP."""
        self.log_decision(
            decision_type="SCALP",
            symbol=symbol,
            action=decision_data.get('action', 'unknown'),
            direction=decision_data.get('side'),
            confidence=decision_data.get('confidence', 0.0),
            raw_reason=decision_data.get('reason'),
            rejection_reason=rejection_reason if rejected else None,
            rejected_by=rejected_by if rejected else None,
            extra_data={
                'leverage': decision_data.get('leverage'),
                'size_usd': decision_data.get('size_usd'),
                'stop_loss_pct': decision_data.get('stop_loss_pct'),
                'take_profit_pct': decision_data.get('take_profit_pct'),
            }
        )
    
    def log_risk_rejection(self,
                           decision_type: str,
                           symbol: str,
                           reason: str):
        """Loga rejeição pelo Risk Manager."""
        self.log_decision(
            decision_type=decision_type,
            symbol=symbol,
            action="blocked",
            rejection_reason=reason,
            rejected_by="risk_manager"
        )
    
    def log_confidence_rejection(self,
                                  decision_type: str,
                                  symbol: str,
                                  confidence: float,
                                  min_required: float):
        """Loga rejeição por confiança insuficiente."""
        self.log_decision(
            decision_type=decision_type,
            symbol=symbol,
            action="blocked",
            confidence=confidence,
            rejection_reason=f"confidence {confidence:.2f} < {min_required:.2f} required",
            rejected_by="confidence_filter"
        )


# Instância global para uso em todo o bot
_decision_logger: Optional[AIDecisionLogger] = None

def get_decision_logger() -> AIDecisionLogger:
    """Retorna instância singleton do logger."""
    global _decision_logger
    if _decision_logger is None:
        _decision_logger = AIDecisionLogger()
    return _decision_logger
