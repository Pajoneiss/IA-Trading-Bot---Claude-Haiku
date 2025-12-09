"""
Phase 2 - Decision Parser
Parse e validação robusta de decisões de IA
"""
import json
import logging
from typing import Dict, Any, Optional, Union
from bot.phase2.models import OpenDecision, ManageDecision, SkipDecision

logger = logging.getLogger(__name__)


class DecisionParser:
    """Parser robusto para decisões de IA"""
    
    @staticmethod
    def parse_ai_decision(response: Union[str, dict], source: str = "unknown") -> Optional[Dict[str, Any]]:
        """
        Parse e valida decisão de IA
        
        Args:
            response: Resposta da IA (JSON string ou dict)
            source: Origem da decisão (claude_swing, openai_scalp)
            
        Returns:
            Dict validado ou None se inválido
        """
        try:
            # Se for string, tenta parsear JSON
            if isinstance(response, str):
                # Remove markdown se tiver
                response = response.strip()
                if response.startswith('```json'):
                    response = response.replace('```json', '').replace('```', '').strip()
                
                try:
                    decision = json.loads(response)
                except json.JSONDecodeError as e:
                    logger.error(f"[PARSER] Erro ao parsear JSON: {e}")
                    logger.debug(f"[PARSER] Response: {response[:500]}")
                    return None
            else:
                decision = response
            
            # Valida estrutura básica
            if not isinstance(decision, dict):
                logger.error(f"[PARSER] Decisão não é um dict: {type(decision)}")
                return None
            
            # Determina tipo de ação
            action = decision.get('action', '').lower()
            
            if action == 'open':
                return DecisionParser._parse_open_decision(decision, source)
            elif action == 'manage':
                return DecisionParser._parse_manage_decision(decision, source)
            elif action == 'skip':
                return DecisionParser._parse_skip_decision(decision, source)
            else:
                logger.warning(f"[PARSER] Action desconhecida: {action}")
                return None
                
        except Exception as e:
            logger.error(f"[PARSER] Erro ao processar decisão: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _parse_open_decision(decision: dict, source: str) -> Optional[Dict[str, Any]]:
        """Parse decisão de OPEN"""
        try:
            # Campos obrigatórios
            symbol = decision.get('symbol', '').upper()
            if not symbol:
                logger.error("[PARSER] Symbol vazio em open decision")
                return None
            
            side = decision.get('side', 'long').lower()
            if side not in ['long', 'short']:
                logger.warning(f"[PARSER] Side inválido: {side}, usando 'long'")
                side = 'long'
            
            # Confidence
            confidence = float(decision.get('confidence', 0.0))
            confidence = max(0.0, min(1.0, confidence))  # Clamp entre 0 e 1
            
            # Style
            style = decision.get('style', 'swing').lower()
            if style not in ['scalp', 'swing']:
                # Tenta inferir do source
                style = 'scalp' if 'scalp' in source.lower() else 'swing'
            
            # Risk profile
            risk_profile = decision.get('risk_profile', 'BALANCED').upper()
            if risk_profile not in ['AGGRESSIVE', 'BALANCED', 'CONSERVATIVE']:
                risk_profile = 'BALANCED'
            
            # Stop loss
            stop_loss_price = float(decision.get('stop_loss_price', 0.0))
            stop_loss_pct = float(decision.get('stop_loss_pct', 2.0))
            
            # Take profit
            take_profit_price = float(decision.get('take_profit_price', 0.0))
            
            # Risk & Capital
            risk_amount_usd = float(decision.get('risk_amount_usd', 0.0))
            capital_alloc_usd = float(decision.get('capital_alloc_usd', 0.0))
            
            # Cria objeto OpenDecision
            open_dec = OpenDecision(
                action='open',
                symbol=symbol,
                side=side,
                style=style,
                source=source,
                confidence=confidence,
                reason=decision.get('reason', 'Sem razão fornecida'),
                strategy=decision.get('strategy', 'UNKNOWN'),
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                stop_loss_pct=stop_loss_pct,
                risk_profile=risk_profile,
                risk_amount_usd=risk_amount_usd,
                capital_alloc_usd=capital_alloc_usd,
                confluences=decision.get('confluences', []),
                timeframe_analysis=decision.get('timeframe_analysis', {})
            )
            
            result = open_dec.to_dict()
            logger.info(f"[PARSER] ✅ Open decision parsed: {symbol} {side} {style} conf={confidence:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"[PARSER] Erro ao parsear open decision: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _parse_manage_decision(decision: dict, source: str) -> Optional[Dict[str, Any]]:
        """Parse decisão de MANAGE"""
        try:
            symbol = decision.get('symbol', '').upper()
            if not symbol:
                logger.error("[PARSER] Symbol vazio em manage decision")
                return None
            
            style = decision.get('style', 'swing').lower()
            
            # Parse manage_decision interno
            manage = decision.get('manage_decision', {})
            
            close_pct = float(manage.get('close_pct', 0.0))
            close_pct = max(0.0, min(1.0, close_pct))
            
            new_stop_price = manage.get('new_stop_price')
            if new_stop_price:
                new_stop_price = float(new_stop_price)
            
            new_tp_price = manage.get('new_take_profit_price')
            if new_tp_price:
                new_tp_price = float(new_tp_price)
            
            manage_dec = ManageDecision(
                action='manage',
                symbol=symbol,
                style=style,
                source=source,
                close_pct=close_pct,
                new_stop_price=new_stop_price,
                new_take_profit_price=new_tp_price,
                reason=manage.get('reason', 'Gestão de posição'),
                r_multiple=manage.get('r_multiple')
            )
            
            result = manage_dec.to_dict()
            logger.info(f"[PARSER] ✅ Manage decision parsed: {symbol} close={close_pct:.0%}")
            
            return result
            
        except Exception as e:
            logger.error(f"[PARSER] Erro ao parsear manage decision: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _parse_skip_decision(decision: dict, source: str) -> Optional[Dict[str, Any]]:
        """Parse decisão de SKIP"""
        try:
            symbol = decision.get('symbol', 'UNKNOWN').upper()
            style = decision.get('style', 'swing').lower()
            
            skip_dec = SkipDecision(
                action='skip',
                symbol=symbol,
                style=style,
                source=source,
                reason=decision.get('reason', 'Sem setup claro')
            )
            
            result = skip_dec.to_dict()
            logger.debug(f"[PARSER] ⏭️  Skip decision parsed: {symbol}")
            
            return result
            
        except Exception as e:
            logger.error(f"[PARSER] Erro ao parsear skip decision: {e}", exc_info=True)
            return None
    
    @staticmethod
    def validate_decision(decision: dict) -> bool:
        """
        Valida se decisão tem todos campos necessários
        
        Args:
            decision: Dict da decisão
            
        Returns:
            True se válida
        """
        if not decision:
            return False
        
        action = decision.get('action')
        if not action:
            logger.error("[PARSER] Decision sem 'action'")
            return False
        
        if action == 'open':
            required = ['symbol', 'side', 'confidence', 'stop_loss_price']
            for field in required:
                if field not in decision or not decision[field]:
                    logger.error(f"[PARSER] Open decision sem '{field}'")
                    return False
        
        elif action == 'manage':
            if 'symbol' not in decision:
                logger.error("[PARSER] Manage decision sem 'symbol'")
                return False
        
        elif action == 'skip':
            # Skip é sempre válido se tem action e symbol
            pass
        
        return True
    
    @staticmethod
    def sanitize_decision(decision: dict) -> dict:
        """
        Remove valores None/NaN e aplica defaults
        
        Args:
            decision: Dict da decisão
            
        Returns:
            Dict sanitizado
        """
        sanitized = {}
        
        for key, value in decision.items():
            # Skip None
            if value is None:
                continue
            
            # Converte NaN para 0
            if isinstance(value, (int, float)):
                import math
                if math.isnan(value) or math.isinf(value):
                    sanitized[key] = 0.0
                else:
                    sanitized[key] = value
            
            # Recursivo para dicts
            elif isinstance(value, dict):
                sanitized[key] = DecisionParser.sanitize_decision(value)
            
            # Outros valores
            else:
                sanitized[key] = value
        
        return sanitized
