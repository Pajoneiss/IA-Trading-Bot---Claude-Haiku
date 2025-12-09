"""
AI Decision Engine - VERSÃO AUTÔNOMA
A IA decide TUDO: leverage, stop loss, take profit, tamanho, etc.
"""
import json
import logging
import os
from typing import Dict, List, Optional, Any
import anthropic
from bot.ai_decision_logger import get_decision_logger

logger = logging.getLogger(__name__)


class AiDecisionEngine:
    """Motor de decisão IA 100% autônomo usando Claude API"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-haiku-20241022"):
        self.api_key = api_key
        self.model = model
        self.client = None
        self.use_ai = False
        
        if api_key:
            try:
                self.client = anthropic.Anthropic(api_key=api_key)
                self.use_ai = True
                logger.info(f"✅ AI Engine ativada com modelo: {model}")
            except Exception as e:
                logger.error(f"Erro ao inicializar Anthropic client: {e}")
                logger.warning("Usando fallback simples")
        else:
            logger.warning("⚠️  ANTHROPIC_API_KEY não configurada - usando lógica simples")
    
    def decide(self, 
               market_contexts: List[Dict[str, Any]],
               account_info: Dict[str, Any],
               open_positions: List[Dict[str, Any]],
               risk_limits: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        IA analisa TUDO e retorna decisões COMPLETAS.
        A IA decide: ação, lado, tamanho, leverage, stop loss, take profit.
        """
        if self.use_ai and self.client:
            return self._decide_with_ai(market_contexts, account_info, open_positions, risk_limits)
        else:
            return self._decide_fallback(market_contexts, account_info, open_positions)
    
    def _decide_with_ai(self,
                        market_contexts: List[Dict[str, Any]],
                        account_info: Dict[str, Any],
                        open_positions: List[Dict[str, Any]],
                        risk_limits: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Decisão usando Claude API - IA decide TUDO"""
        
        prompt = self._build_prompt(market_contexts, account_info, open_positions, risk_limits)
        
        try:
            logger.debug("Consultando Claude API...")
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=3000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = response.content[0].text
            logger.debug(f"Resposta IA (raw): {response_text[:300]}...")
            
            decisions = self._parse_ai_response(response_text)
            
            # Log todas as decisões para diagnóstico
            decision_logger = get_decision_logger()
            
            if decisions:
                logger.info(f"✅ IA retornou {len(decisions)} decisões")
                for dec in decisions:
                    if dec.get('action') == 'hold':
                        logger.info(f"  → HOLD: {dec.get('reason', 'sem motivo')}")
                        decision_logger.log_swing_decision(
                            symbol=dec.get('symbol'),
                            decision_data=dec,
                            rejected=False
                        )
                    else:
                        logger.info(
                            f"  → {dec.get('symbol')} {dec.get('action')} {dec.get('side', '')} "
                            f"| ${dec.get('size_usd', 0):.0f} @ {dec.get('leverage', 1)}x"
                        )
                        decision_logger.log_swing_decision(
                            symbol=dec.get('symbol'),
                            decision_data=dec,
                            rejected=False
                        )
            else:
                logger.info("ℹ️  IA não recomendou nenhuma ação")
                decision_logger.log_decision(
                    decision_type="SWING",
                    symbol=None,
                    action="no_decision",
                    raw_reason="IA não retornou decisões válidas"
                )
            
            return decisions
            
        except Exception as e:
            logger.error(f"Erro ao consultar Claude API: {e}")
            return self._decide_fallback(market_contexts, account_info, open_positions)


    def _parse_ai_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse da resposta da IA (suporta formato antigo e novo)"""
        try:
            # Limpa markdown
            text = response_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            data = json.loads(text)
            
            # Normaliza para lista de ações
            actions = []
            if isinstance(data, list):
                actions = data
            elif isinstance(data, dict):
                if 'actions' in data:
                    actions = data['actions']
                else:
                    # Formato novo: objeto único
                    actions = [data]
            
            valid_actions = []
            for action in actions:
                act_type = action.get('action', 'hold')
                
                # Hold - apenas loga
                if act_type == 'hold':
                    logger.info(f"🤚 IA decidiu HOLD: {action.get('reason', 'sem motivo')}")
                    continue
                
                # Open - valida campos obrigatórios
                if act_type in ('open', 'open_long', 'open_short'):
                    # Normaliza action para 'open' e define side se vier no action
                    if act_type == 'open_long':
                        action['action'] = 'open'
                        action['side'] = 'long'
                    elif act_type == 'open_short':
                        action['action'] = 'open'
                        action['side'] = 'short'
                        
                    # Mapeia structural_stop_price para stop_loss_price se necessário
                    if not action.get('stop_loss_price') and action.get('structural_stop_price'):
                        action['stop_loss_price'] = action['structural_stop_price']

                    if not all([
                        action.get('symbol'),
                        action.get('side'),
                        # action.get('size_usd'), # Removido: Prompt diz que é calculado pelo Risk Manager
                    ]):
                        logger.warning(f"Ação 'open' incompleta, ignorando: {action}")
                        continue
                    
                    # Defaults para campos opcionais
                    if not action.get('leverage'):
                        action['leverage'] = 5
                    
                    # Garante limites
                    action['leverage'] = max(1, min(50, int(float(action['leverage']))))
                    
                    valid_actions.append(action)
                
                # Close
                elif act_type == 'close':
                    if not action.get('symbol'):
                        continue
                    valid_actions.append(action)
                
                # Increase/Decrease/Manage
                elif act_type in ('increase', 'decrease', 'manage'):
                    if not action.get('symbol'):
                        continue
                    if act_type != 'manage' and not action.get('size_usd'):
                        action['size_usd'] = 20  # Default
                    valid_actions.append(action)
            
            return valid_actions
            
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao fazer parse do JSON da IA: {e}")
            logger.debug(f"Resposta problemática: {response_text[:500]}")
            return []
        except Exception as e:
            logger.error(f"Erro inesperado ao processar resposta IA: {e}")
            return []
    
    def _build_prompt(self,
                      market_contexts: List[Dict[str, Any]],
                      account_info: Dict[str, Any],
                      open_positions: List[Dict[str, Any]],
                      risk_limits: Dict[str, Any]) -> str:
        """Constrói prompt para IA (Claude) com persona Trader Institucional Agressivo/Inteligente"""
        
        prompt = """Você é o HEAD TRADER de um fundo quantitativo institucional.
Especialidade: SWING TRADE usando SMC (Smart Money Concepts), Price Action Puro e Análise Multi-Timeframe.

═══════════════════════════════════════════════════════
🎯 FILOSOFIA DE TRADING & AGRESSIVIDADE
═══════════════════════════════════════════════════════

SEU OBJETIVO: Maximizar retorno ajustado ao risco.
- NÃO SEJA TIMÍDO. Se o setup existe, OPERE.
- RSI ALTO/BAIXO NÃO É PROIBIÇÃO DE TRADE. Em tendências fortes, o RSI fica extremo por muito tempo.
- Posição aberta em um ativo (ex: ZEC) NÃO IMPEDE abertura em outros (ex: BTC, ETH), desde que haja margem.
- DIVERSIFIQUE: Se já está em ZEC, procure oportunidades em BTC ou ETH para não concentrar risco.

═══════════════════════════════════════════════════════
📊 EMAs + VWAP = TIMING DE ENTRADA (MUITO IMPORTANTE)
═══════════════════════════════════════════════════════

PRIORIDADE DE ANÁLISE:
1. ESTRUTURA (Topo/Fundo, BOS, CHoCH) = Define a direção.
2. TIMING (EMAs 9/26 + VWAP) = Define O MOMENTO EXATO.
3. ADICIONAL (RSI, Volume) = Confirmação ou alerta de exaustão.

SETUP DE REVERSÃO "SNIPER":
1. Tendência prévia exausta (velas menores, pavios).
2. Preço cruza EMA 9 e testa EMA 26 (ou cruza ambas).
3. EMA 9 cruza EMA 26 a favor da nova direção.
4. Preço recupera/perde VWAP.
5. GATILHO: Rompimento do candle de confirmação ou reteste (pullback) nas médias.

MODO AGRESSIVO/BALANCEADO:
- PODE entrar no cruzamento ou no primeiro candle de força pós-cruzamento.
- PODE operar continuação de tendência mesmo com RSI > 70 (Long) ou < 30 (Short), se o momentum for forte.

MODO CONSERVADOR:
- Exige Pullback claro e toque na EMA/VWAP antes de entrar.

═══════════════════════════════════════════════════════
⚔️ REGRAS DE GESTÃO DE POSIÇÃO
═══════════════════════════════════════════════════════

STOP LOSS (OBRIGATÓRIO):
- O Stop DEVE ser ESTRUTURAL (último fundo/topo válido, Order Block).
- NUNCA abra trade sem Stop Loss definido.
- Distância do stop define o tamanho da mão (calculado externamente, foque no PREÇO do stop).

GESTÃO DINÂMICA (Trailing/Parciais):
- Se tendência forte: DEIXE CORRER (Trailing no Swing Low anterior ou EMA 21).
- Se lateral/perigoso: Realize parciais (Trim) rápido.
- Breakeven: Mova para BE quando preço atingir 1R ou romper estrutura a favor.

═══════════════════════════════════════════════════════
"""

        # Informações da conta
        prompt += f"\n📊 ESTADO DA CONTA:\n"
        prompt += f"- Equity: ${account_info.get('equity', 0):.2f}\n"
        prompt += f"- Posições Abertas: {len(open_positions)} (Max Global: {risk_limits.get('max_open_trades', 3)})\n"
        
        # Limites de risco
        prompt += f"\n⚠️ LIMITES DE RISCO (Risk Manager vai validar):\n"
        prompt += f"- Risco Base Swing: {risk_limits.get('risk_per_trade_pct', 1.0)}% da banca\n"
        prompt += f"- Max Leverage: {risk_limits.get('max_leverage', 20)}x\n"
        
        # Posições abertas
        open_symbols = []
        if open_positions:
            prompt += f"\n📈 POSIÇÕES ABERTAS (Não abra contra. Pode abrir outros pares):\n"
            for pos in open_positions:
                sym = pos.get('symbol')
                open_symbols.append(sym)
                prompt += f"- {sym}: {pos.get('side')} | PnL: {pos.get('pnl_pct', 0):.2f}% | Size: ${pos.get('size', 0):.2f}\n"
        else:
            prompt += "\n📈 POSIÇÕES ABERTAS: NENHUMA. Carteira Livre.\n"
        
        # Contexto de mercado
        prompt += f"\n🔍 ANÁLISE DE MERCADO (Analise TODOS para diversificar):\n"
        for ctx in market_contexts:
            symbol = ctx.get('symbol', 'UNKNOWN')
            
            # Pula análise profunda se já posicionado no mesmo ativo (para evitar duplicação simples)
            # Mas permite GESTÃO se for o caso. O prompt deve decidir.
            
            price = ctx.get('price', 0)
            
            prompt += f"\n=== {symbol} (Preço: ${price:.4f}) ===\n"
            
            # Indicadores
            indicators = ctx.get('indicators', {})
            ema9 = indicators.get('ema_9') or 0
            ema21 = indicators.get('ema_21') or 0
            rsi = indicators.get('rsi') or 50
            volatility = indicators.get('volatility_pct') or 0
            
            prompt += f"Indicadores: EMA9=${ema9:.4f} | EMA21=${ema21:.4f} | RSI={rsi:.1f} | Vol={volatility:.2f}%\n"
            
            # Trend
            trend = ctx.get('trend', {})
            direction = trend.get('direction', 'neutral')
            strength = trend.get('strength', 0)
            prompt += f"Tendência Macro: {direction.upper()} (Força: {strength:.2f})\n"
            
            # Phase2 Structure
            phase2 = ctx.get('phase2', {})
            if phase2 and isinstance(phase2, dict):
                structure = phase2.get('structure')
                patterns = phase2.get('patterns', [])
                regime = phase2.get('regime_kv', {})
                
                if structure:
                    prompt += f"Estrutura: {structure.get('trend', 'N/A')}\n"
                
                if regime:
                    prompt += f"Regime: {regime.get('name', 'UNKNOWN')} (Chop: {regime.get('chop_score', 0):.1f})\n"

        # Formato de resposta
        prompt += """
═══════════════════════════════════════════════════════
📝 DECISÃO (JSON OBRIGATÓRIO)
═══════════════════════════════════════════════════════

Responda APENAS com um JSON. Se não houver oportunidade, use action: hold.

PARA ABRIR TRADE (SWING):
{
  "action": "open",
  "symbol": "SÍMBOLO",
  "side": "long" ou "short",
  "style": "swing",
  "entry_price": preço_atual,
  "structural_stop_price": PREÇO_EXATO_DO_STOP (fundo/topo anterior),
  "invalid_level": preço que invalida a tese antes do stop,
  "management_plan": {
    "style": "TREND_FOLLOW",
    "trail_logic": "EMA21_CLOSE"
  },
  "confidence": 0.0 a 1.0 (Seja honesto. Agressivo aceita >0.65),
  "reason": "Explique o setup: Estrutura + Timing (EMA/VWAP) + Contexto"
}

Observação: O tamanho da posição (size_usd) será calculado automaticamente pelo Risk Manager com base na distância do STOP ESTRUTURAL e o % de risco do modo atual. Você foca na qualidade do Stop.

Se houver posição aberta e quiser gerenciar:
{"action": "close", "symbol": "...", "reason": "..."}
{"action": "hold", "reason": "..."}
"""
        
        return prompt
    
    def _decide_fallback(self,

                        market_contexts: List[Dict[str, Any]],
                        account_info: Dict[str, Any],
                        open_positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Lógica simples de fallback quando IA não está disponível
        Estratégia: Cruzamento EMA + RSI
        """
        logger.info("🔧 Usando lógica FALLBACK simples (EMA cross + RSI)")
        
        actions = []
        open_symbols = {pos.get('symbol') for pos in open_positions}
        equity = account_info.get('equity', 100)
        
        for ctx in market_contexts:
            symbol = ctx['symbol']
            price = ctx.get('price', 0)
            
            if symbol in open_symbols:
                continue
            
            ind = ctx.get('indicators', {})
            ema9 = ind.get('ema_9')
            ema21 = ind.get('ema_21')
            rsi = ind.get('rsi')
            
            if ema9 is None or ema21 is None or rsi is None:
                continue
            
            # Sinal de LONG
            if ema9 > ema21 and rsi < 70 and rsi > 30:
                stop_loss = price * 0.97
                take_profit = price * 1.06
                
                actions.append({
                    'symbol': symbol,
                    'action': 'open',
                    'side': 'long',
                    'size_usd': equity * 0.05,
                    'leverage': 5,
                    'stop_loss_price': stop_loss,
                    'take_profit_price': take_profit,
                    'reason': f'Fallback: EMA9 > EMA21, RSI={rsi:.1f}'
                })
            
            # Sinal de SHORT
            elif ema9 < ema21 and rsi > 30 and rsi < 70:
                stop_loss = price * 1.03
                take_profit = price * 0.94
                
                actions.append({
                    'symbol': symbol,
                    'action': 'open',
                    'side': 'short',
                    'size_usd': equity * 0.05,
                    'leverage': 5,
                    'stop_loss_price': stop_loss,
                    'take_profit_price': take_profit,
                    'reason': f'Fallback: EMA9 < EMA21, RSI={rsi:.1f}'
                })
        
        return actions
