"""
THOUGHT FEED - Pensamentos Relevantes da IA
=============================================

Este módulo armazena e gerencia os "pensamentos" da IA:
- Análises de mercado
- Decisões de trading
- Avaliações de risco
- Execuções realizadas

O objetivo é fornecer uma timeline de raciocínio limpa,
SEM log cru, SEM stack traces, apenas insights relevantes.

Uso:
    from bot.thought_feed import get_thought_feed, ThoughtType
    
    feed = get_thought_feed()
    feed.add_thought(
        type=ThoughtType.ANALYSIS,
        summary="BTC mostrando força acima de EMA200",
        symbols=["BTC"],
        details={"ema_200": 95000, "current": 100000}
    )
    
    thoughts = feed.get_thoughts(limit=50)

Autor: Claude
Data: 2024-12-13
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, asdict
import threading

logger = logging.getLogger(__name__)


class ThoughtType(Enum):
    """Tipos de pensamento da IA"""
    ANALYSIS = "analysis"      # Análise de mercado
    DECISION = "decision"      # Decisão de trading
    RISK = "risk"              # Avaliação de risco
    EXECUTION = "execution"    # Execução realizada
    ADJUSTMENT = "adjustment"  # Ajuste de posição (SL/TP/BE)
    ERROR = "error"            # Erro relevante (não stack trace!)
    INSIGHT = "insight"        # Insight/observação
    STRATEGY = "strategy"      # Mudança de estratégia


@dataclass
class Thought:
    """Representa um pensamento/insight da IA"""
    id: str
    timestamp: str
    type: str
    summary: str  # Resumo curto e humano
    symbols: List[str] = None
    actions: List[str] = None  # Ações tomadas/sugeridas
    details: Dict[str, Any] = None  # Detalhes relevantes (opcional)
    confidence: float = None
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'type': self.type,
            'summary': self.summary,
            'symbols': self.symbols or [],
            'actions': self.actions or [],
            'details': self.details or {},
            'confidence': self.confidence
        }


class ThoughtFeed:
    """
    Gerenciador de pensamentos da IA.
    
    Armazena em memória + arquivo para persistência básica.
    """
    
    def __init__(self, max_thoughts: int = 500, persist_file: str = None):
        self.max_thoughts = max_thoughts
        self.thoughts: List[Thought] = []
        self._lock = threading.Lock()
        self._counter = 0
        
        # Arquivo de persistência
        self.persist_file = persist_file or os.path.join(
            os.path.dirname(__file__), '..', 'data', 'thought_feed.jsonl'
        )
        
        # Carrega histórico se existir
        self._load_history()
    
    def _load_history(self):
        """Carrega histórico do arquivo"""
        try:
            if os.path.exists(self.persist_file):
                with open(self.persist_file, 'r') as f:
                    lines = f.readlines()[-self.max_thoughts:]  # Últimos N
                    for line in lines:
                        try:
                            data = json.loads(line.strip())
                            thought = Thought(**data)
                            self.thoughts.append(thought)
                            self._counter = max(self._counter, int(data.get('id', '0').split('_')[-1] or 0))
                        except:
                            pass
                logger.info(f"[THOUGHT_FEED] Carregados {len(self.thoughts)} pensamentos do histórico")
        except Exception as e:
            logger.debug(f"[THOUGHT_FEED] Erro ao carregar histórico: {e}")
    
    def _persist_thought(self, thought: Thought):
        """Persiste pensamento no arquivo"""
        try:
            os.makedirs(os.path.dirname(self.persist_file), exist_ok=True)
            with open(self.persist_file, 'a') as f:
                f.write(json.dumps(thought.to_dict()) + '\n')
        except Exception as e:
            logger.debug(f"[THOUGHT_FEED] Erro ao persistir: {e}")
    
    def add_thought(self,
                    type: ThoughtType,
                    summary: str,
                    symbols: List[str] = None,
                    actions: List[str] = None,
                    details: Dict[str, Any] = None,
                    confidence: float = None) -> Thought:
        """
        Adiciona um novo pensamento.
        
        Args:
            type: Tipo do pensamento
            summary: Resumo CURTO e HUMANO (max ~200 chars)
            symbols: Símbolos envolvidos
            actions: Ações tomadas/sugeridas
            details: Detalhes relevantes (opcional)
            confidence: Confiança da IA (0-1)
            
        Returns:
            Thought criado
        """
        with self._lock:
            self._counter += 1
            
            thought = Thought(
                id=f"thought_{self._counter}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                type=type.value if isinstance(type, ThoughtType) else type,
                summary=summary[:500],  # Limita tamanho
                symbols=symbols or [],
                actions=actions or [],
                details=details or {},
                confidence=confidence
            )
            
            self.thoughts.append(thought)
            
            # Limita tamanho
            if len(self.thoughts) > self.max_thoughts:
                self.thoughts = self.thoughts[-self.max_thoughts:]
            
            # Persiste
            self._persist_thought(thought)
            
            logger.debug(f"[THOUGHT_FEED] +{thought.type}: {thought.summary[:50]}...")
            
            return thought
    
    def get_thoughts(self,
                     limit: int = 50,
                     type_filter: str = None,
                     symbol_filter: str = None,
                     since: str = None) -> List[Dict]:
        """
        Retorna lista de pensamentos.
        
        Args:
            limit: Máximo de pensamentos
            type_filter: Filtrar por tipo
            symbol_filter: Filtrar por símbolo
            since: Timestamp ISO para filtrar (só mais recentes)
            
        Returns:
            Lista de pensamentos como dicts
        """
        with self._lock:
            result = list(reversed(self.thoughts))  # Mais recentes primeiro
            
            if type_filter:
                result = [t for t in result if t.type == type_filter]
            
            if symbol_filter:
                result = [t for t in result if symbol_filter in (t.symbols or [])]
            
            if since:
                result = [t for t in result if t.timestamp > since]
            
            return [t.to_dict() for t in result[:limit]]
    
    def get_last_thought(self, type_filter: str = None) -> Optional[Dict]:
        """Retorna último pensamento"""
        thoughts = self.get_thoughts(limit=1, type_filter=type_filter)
        return thoughts[0] if thoughts else None
    
    # ================================================================
    # HELPERS para adicionar pensamentos comuns
    # ================================================================
    
    def analysis(self, summary: str, symbols: List[str] = None, details: Dict = None):
        """Adiciona análise de mercado"""
        return self.add_thought(ThoughtType.ANALYSIS, summary, symbols=symbols, details=details)
    
    def decision(self, summary: str, symbols: List[str] = None, actions: List[str] = None, confidence: float = None):
        """Adiciona decisão de trading"""
        return self.add_thought(ThoughtType.DECISION, summary, symbols=symbols, actions=actions, confidence=confidence)
    
    def execution(self, summary: str, symbols: List[str] = None, details: Dict = None):
        """Adiciona execução realizada"""
        return self.add_thought(ThoughtType.EXECUTION, summary, symbols=symbols, details=details)
    
    def risk(self, summary: str, symbols: List[str] = None, details: Dict = None):
        """Adiciona avaliação de risco"""
        return self.add_thought(ThoughtType.RISK, summary, symbols=symbols, details=details)
    
    def adjustment(self, summary: str, symbols: List[str] = None, details: Dict = None):
        """Adiciona ajuste de posição"""
        return self.add_thought(ThoughtType.ADJUSTMENT, summary, symbols=symbols, details=details)
    
    def insight(self, summary: str, symbols: List[str] = None):
        """Adiciona insight/observação"""
        return self.add_thought(ThoughtType.INSIGHT, summary, symbols=symbols)
    
    def error(self, summary: str, symbols: List[str] = None):
        """Adiciona erro relevante (sem stack trace!)"""
        return self.add_thought(ThoughtType.ERROR, summary, symbols=symbols)


# ================================================================
# AI CHAT RESPONDER
# ================================================================

class AIChatResponder:
    """
    Responde perguntas do usuário como "Trader IA".
    
    Usa o snapshot atual para contextualizar respostas.
    Pode chamar a IA real se houver budget, ou usar fallback.
    """
    
    def __init__(self, bot=None, thought_feed: ThoughtFeed = None):
        self.bot = bot
        self.thought_feed = thought_feed or get_thought_feed()
    
    def respond(self, user_message: str) -> Dict[str, Any]:
        """
        Responde uma mensagem do usuário.
        
        Se não houver budget de IA, usa fallback baseado no snapshot.
        
        Returns:
            {
                'reply': 'resposta da IA',
                'context': {...},
                'used_ai': bool
            }
        """
        try:
            # Tenta usar IA real se houver budget
            if self._has_ai_budget():
                return self._respond_with_ai(user_message)
            else:
                return self._respond_fallback(user_message)
        except Exception as e:
            logger.error(f"[AI_CHAT] Erro ao responder: {e}")
            return {
                'reply': f"Desculpe, ocorreu um erro ao processar sua pergunta. Tente novamente.",
                'context': {},
                'used_ai': False,
                'error': str(e)
            }
    
    def _has_ai_budget(self) -> bool:
        """Verifica se há budget de IA disponível"""
        if not self.bot:
            return False
        
        try:
            budget_manager = getattr(self.bot, 'ai_budget_manager', None)
            if budget_manager:
                # Verifica se pode fazer pelo menos 1 chamada
                return budget_manager.can_call_claude() or budget_manager.can_call_openai()
        except:
            pass
        
        return False
    
    def _respond_with_ai(self, user_message: str) -> Dict[str, Any]:
        """Responde usando a IA real"""
        # TODO: Implementar chamada real à IA com prompt curto
        # Por agora, usa fallback
        return self._respond_fallback(user_message)
    
    def _respond_fallback(self, user_message: str) -> Dict[str, Any]:
        """
        Responde sem chamar IA, baseado no snapshot atual.
        """
        context = self._build_context()
        
        # Analisa pergunta e gera resposta baseada no contexto
        msg_lower = user_message.lower()
        
        reply = self._generate_contextual_reply(msg_lower, context)
        
        return {
            'reply': reply,
            'context': context,
            'used_ai': False,
            'note': 'Resposta baseada no snapshot atual (budget IA limitado)'
        }
    
    def _build_context(self) -> Dict[str, Any]:
        """Constrói contexto atual para resposta"""
        context = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'positions': [],
            'equity': 0,
            'mode': 'unknown',
            'recent_thoughts': []
        }
        
        try:
            if self.bot:
                # Posições
                positions = self.bot.position_manager.get_all_positions()
                for pos in positions:
                    context['positions'].append({
                        'symbol': pos.symbol,
                        'side': pos.side,
                        'size': pos.size,
                        'entry': pos.entry_price,
                        'pnl_pct': pos.get_unrealized_pnl_pct(pos.current_price) if hasattr(pos, 'current_price') else 0
                    })
                
                # Equity
                if hasattr(self.bot, 'risk_manager') and self.bot.risk_manager:
                    context['equity'] = self.bot.risk_manager.current_equity or 0
                
                # Mode
                if hasattr(self.bot, 'mode_manager') and self.bot.mode_manager:
                    context['mode'] = str(self.bot.mode_manager.current_mode.value)
            
            # Últimos pensamentos
            context['recent_thoughts'] = self.thought_feed.get_thoughts(limit=5)
            
        except Exception as e:
            logger.debug(f"[AI_CHAT] Erro ao construir contexto: {e}")
        
        return context
    
    def _generate_contextual_reply(self, msg_lower: str, context: Dict) -> str:
        """Gera resposta baseada no contexto"""
        positions = context.get('positions', [])
        equity = context.get('equity', 0)
        thoughts = context.get('recent_thoughts', [])
        
        # Perguntas sobre posições
        if any(w in msg_lower for w in ['posição', 'posições', 'position', 'positions', 'aberta', 'abertas']):
            if not positions:
                return "📊 Não temos posições abertas no momento. Estou monitorando o mercado em busca de oportunidades."
            
            pos_text = '\n'.join([
                f"• {p['symbol']}: {p['side'].upper()} ({p['pnl_pct']:.2f}%)" 
                for p in positions
            ])
            return f"📊 Posições atuais ({len(positions)}):\n{pos_text}"
        
        # Perguntas sobre o que a IA está pensando
        if any(w in msg_lower for w in ['pensando', 'thinking', 'análise', 'analysis', 'visão', 'view']):
            if thoughts:
                last = thoughts[0]
                return f"🧠 Último pensamento ({last['type']}):\n{last['summary']}"
            return "🧠 Ainda coletando dados para formar uma tese. Aguarde..."
        
        # Perguntas sobre equity/saldo
        if any(w in msg_lower for w in ['equity', 'saldo', 'balance', 'dinheiro', 'capital']):
            return f"💰 Equity atual: ${equity:.2f}"
        
        # Perguntas sobre estratégia
        if any(w in msg_lower for w in ['estratégia', 'strategy', 'plano', 'plan']):
            mode = context.get('mode', 'unknown')
            return f"📈 Modo atual: {mode}. Focando em trades de alta probabilidade com gestão de risco rigorosa."
        
        # Default
        return (
            f"👋 Sou o Trader IA do InspetorPro.\n\n"
            f"📊 Status: {'Tenho ' + str(len(positions)) + ' posição(ões) aberta(s)' if positions else 'Sem posições abertas'}\n"
            f"💰 Equity: ${equity:.2f}\n\n"
            f"Pergunte sobre: posições, análise, estratégia, ou qualquer dúvida sobre o mercado!"
        )


# ================================================================
# SINGLETON
# ================================================================

_thought_feed: Optional[ThoughtFeed] = None
_chat_responder: Optional[AIChatResponder] = None


def get_thought_feed() -> ThoughtFeed:
    """Retorna instância singleton do ThoughtFeed"""
    global _thought_feed
    if _thought_feed is None:
        _thought_feed = ThoughtFeed()
    return _thought_feed


def get_chat_responder(bot=None) -> AIChatResponder:
    """Retorna instância do AIChatResponder"""
    global _chat_responder
    if _chat_responder is None or bot:
        _chat_responder = AIChatResponder(bot, get_thought_feed())
    return _chat_responder


def init_thought_feed(bot=None) -> ThoughtFeed:
    """Inicializa ThoughtFeed"""
    global _thought_feed, _chat_responder
    _thought_feed = ThoughtFeed()
    if bot:
        _chat_responder = AIChatResponder(bot, _thought_feed)
    return _thought_feed
