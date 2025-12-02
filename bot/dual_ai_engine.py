"""
Dual AI Decision Engine
Orquestrador que gerencia Claude (Swing) e OpenAI (Scalp) simultaneamente.
"""
import logging
from typing import Dict, List, Any, Optional
from bot.ai_decision import AiDecisionEngine
from bot.openai_scalp_engine import OpenAiScalpEngine

logger = logging.getLogger(__name__)

class DualAiDecisionEngine:
    """
    Orquestrador que consulta dois motores de IA:
    1. Claude (Swing) - Motor principal existente
    2. OpenAI (Scalp) - Novo motor de alta frequência
    """
    
    def __init__(self, 
                 anthropic_key: Optional[str], 
                 openai_key: Optional[str],
                 anthropic_model: str = "claude-3-5-haiku-20241022",
                 openai_model: str = "gpt-4o-mini"):
        
        # Inicializa motores
        self.swing_engine = AiDecisionEngine(api_key=anthropic_key, model=anthropic_model)
        self.scalp_engine = OpenAiScalpEngine(api_key=openai_key, model=openai_model)
        
        logger.info("🚀 Dual AI Engine Inicializado")
        logger.info(f"  → Swing: {'✅' if self.swing_engine.use_ai else '⚠️ (Fallback)'}")
        logger.info(f"  → Scalp: {'✅' if self.scalp_engine.enabled else '❌ (Desativado)'}")

    def decide(self, 
               market_contexts: List[Dict[str, Any]],
               account_info: Dict[str, Any],
               open_positions: List[Dict[str, Any]],
               risk_limits: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Coleta decisões de ambos os motores e as combina.
        """
        all_decisions = []
        
        # 1. Consulta Swing Engine (Claude)
        try:
            swing_decisions = self.swing_engine.decide(
                market_contexts, account_info, open_positions, risk_limits
            )
            # Garante tags
            for dec in swing_decisions:
                if 'source' not in dec:
                    dec['source'] = 'claude_swing'
                if 'style' not in dec:
                    dec['style'] = 'swing'
            
            all_decisions.extend(swing_decisions)
            
        except Exception as e:
            logger.error(f"Erro no Swing Engine: {e}")
            
        # 2. Consulta Scalp Engine (OpenAI) - se ativado
        if self.scalp_engine.enabled:
            try:
                scalp_decisions = self.scalp_engine.get_scalp_decision(
                    market_contexts, account_info, open_positions, risk_limits
                )
                all_decisions.extend(scalp_decisions)
            except Exception as e:
                logger.error(f"Erro no Scalp Engine: {e}")
        
        # 3. Resolução de Conflitos Básica
        # Se houver decisões conflitantes para o mesmo símbolo, prioriza SWING
        final_decisions = self._resolve_conflicts(all_decisions)
        
        return final_decisions

    def _resolve_conflicts(self, decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove conflitos diretos (ex: Swing Long vs Scalp Short no mesmo símbolo).
        Prioridade: Swing > Scalp.
        """
        if not decisions:
            return []
            
        # Mapa de decisões por símbolo
        swing_map = {}
        scalp_map = {}
        others = []
        
        for dec in decisions:
            symbol = dec.get('symbol')
            source = dec.get('source', 'unknown')
            action = dec.get('action')
            
            if action == 'hold':
                continue
                
            if 'claude_swing' in source:
                swing_map[symbol] = dec
            elif 'openai_scalp' in source:
                scalp_map[symbol] = dec
            else:
                others.append(dec)
        
        final_list = []
        
        # Adiciona todas as decisões de swing
        for symbol, dec in swing_map.items():
            final_list.append(dec)
            
        # Adiciona scalp se não houver conflito
        for symbol, dec in scalp_map.items():
            if symbol in swing_map:
                # Conflito!
                swing_side = swing_map[symbol].get('side')
                scalp_side = dec.get('side')
                
                if swing_side != scalp_side:
                    logger.warning(
                        f"⚔️ CONFLITO em {symbol}: Swing ({swing_side}) vs Scalp ({scalp_side}). "
                        "Priorizando SWING."
                    )
                    continue
                else:
                    # Mesmo lado, permite (reforço de posição?)
                    # Por segurança, vamos permitir, mas o RiskManager vai barrar se estourar limites
                    logger.info(f"🤝 Convergência em {symbol}: Swing e Scalp ambos {swing_side}.")
                    final_list.append(dec)
            else:
                # Sem conflito
                final_list.append(dec)
                
        final_list.extend(others)
        return final_list
