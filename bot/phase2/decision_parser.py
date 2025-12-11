"""
Phase 2 - Decision Parser
Parse e validação robusta de decisões de IA

[Claude Trend Refactor] Data: 2024-12-11
- Defaults mais seguros para confidence (0.7 em vez de 0.0)
- Validação extra de trend_bias
- Melhor tratamento de JSON malformado
"""
import json
import logging
import re
from typing import Dict, Any, Optional, Union
from bot.phase2.models import OpenDecision, ManageDecision, SkipDecision

logger = logging.getLogger(__name__)


# Default confidence quando não informado ou inválido
DEFAULT_CONFIDENCE = 0.70


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
                
                # [Claude Trend Refactor] Limpeza mais agressiva
                # Remove ```json e ``` e qualquer texto antes/depois do JSON
                if '```json' in response:
                    response = response.split('```json')[-1]
                if '```' in response:
                    response = response.split('```')[0]
                
                # Tenta encontrar JSON válido na string
                response = response.strip()
                
                # Se começa com texto antes do {, remove
                if not response.startswith('{') and '{' in response:
                    json_start = response.find('{')
                    response = response[json_start:]
                
                # Se tem texto depois do }, remove
                if '}' in response:
                    json_end = response.rfind('}') + 1
                    response = response[:json_end]
                
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
            
            # Normaliza actions alternativas
            if action in ('open_long', 'open_short'):
                if action == 'open_long':
                    decision['side'] = 'long'
                else:
                    decision['side'] = 'short'
                action = 'open'
                decision['action'] = 'open'
            
            if action == 'open':
                return DecisionParser._parse_open_decision(decision, source)
            elif action == 'manage':
                return DecisionParser._parse_manage_decision(decision, source)
            elif action in ('skip', 'hold'):
                return DecisionParser._parse_skip_decision(decision, source)
            else:
                logger.warning(f"[PARSER] Action desconhecida: {action}")
                return None
                
        except Exception as e:
            logger.error(f"[PARSER] Erro ao processar decisão: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _parse_open_decision(decision: dict, source: str) -> Optional[Dict[str, Any]]:
        """
        Parse decisão de OPEN
        
        [Claude Trend Refactor] Melhorias:
        - Default confidence = 0.70 (não 0.0)
        - Extrai trend_bias se presente
        """
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
            
            # [Claude Trend Refactor] Confidence com default mais seguro
            raw_confidence = decision.get('confidence')
            
            # Tenta extrair confidence de várias formas
            if raw_confidence is None:
                confidence = DEFAULT_CONFIDENCE
                logger.warning(f"[PARSER] ⚠️ Confidence não informado, usando default: {DEFAULT_CONFIDENCE}")
            elif isinstance(raw_confidence, str):
                # Pode vir como "0.75" ou "75%"
                try:
                    raw_confidence = raw_confidence.replace('%', '').strip()
                    confidence = float(raw_confidence)
                    if confidence > 1.0:
                        confidence = confidence / 100  # Era porcentagem
                except ValueError:
                    confidence = DEFAULT_CONFIDENCE
                    logger.warning(f"[PARSER] Confidence string inválida: {raw_confidence}, usando default")
            else:
                try:
                    confidence = float(raw_confidence)
                except (ValueError, TypeError):
                    confidence = DEFAULT_CONFIDENCE
                    logger.warning(f"[PARSER] Confidence inválido: {raw_confidence}, usando default")
            
            # Clamp entre 0 e 1
            confidence = max(0.0, min(1.0, confidence))
            
            # Se confidence muito baixo (provavelmente erro), usa default
            if confidence < 0.1 and raw_confidence != 0:
                logger.warning(f"[PARSER] ⚠️ Confidence muito baixo ({confidence}), substituindo por default")
                confidence = DEFAULT_CONFIDENCE
            
            # Style
            style = decision.get('style', 'swing').lower()
            if style not in ['scalp', 'swing']:
                # Tenta inferir do source
                style = 'scalp' if 'scalp' in source.lower() else 'swing'
            
            # Risk profile
            risk_profile = decision.get('risk_profile', 'BALANCED').upper()
            if risk_profile not in ['AGGRESSIVE', 'BALANCED', 'CONSERVATIVE']:
                risk_profile = 'BALANCED'
            
            # [Claude Trend Refactor] Extrai trend_bias
            trend_bias = decision.get('trend_bias', 'neutral').lower()
            if trend_bias not in ['long', 'short', 'neutral']:
                trend_bias = 'neutral'
            
            # Stop loss
            stop_loss_price = float(decision.get('stop_loss_price') or decision.get('structural_stop_price') or 0.0)
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
            
            # [Claude Trend Refactor] Adiciona trend_bias ao resultado
            result['trend_bias'] = trend_bias
            
            logger.info(f"[PARSER] ✅ Open decision parsed: {symbol} {side} {style} conf={confidence:.2f} trend_bias={trend_bias}")
            
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
