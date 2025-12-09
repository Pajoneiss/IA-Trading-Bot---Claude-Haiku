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
                        
                    if not all([
                        action.get('symbol'),
                        action.get('side'),
                        action.get('size_usd'),
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
        """Constrói prompt para IA (Claude) com persona Trader Institucional"""
        
        prompt = """Você é o HEAD TRADER de um fundo quantitativo institucional.
Especialidade: SWING TRADE usando SMC (Smart Money Concepts), Price Action Puro e Análise Multi-Timeframe.

═══════════════════════════════════════════════════════
🎯 METODOLOGIA DE ANÁLISE
═══════════════════════════════════════════════════════

MACRO (4H / 1H):
- Identifique a TENDÊNCIA DOMINANTE e ESTRUTURA DE MERCADO
- Detecte BOS (Break of Structure) e CHoCH (Change of Character)
- Mapeie ZONAS DE LIQUIDEZ: onde stops estão acumulados
- Identifique ORDER BLOCKS, FVG (Fair Value Gaps), BREAKER BLOCKS

EXECUÇÃO (15m / 5m):
- Timing preciso de entrada após confirmação macro
- Aguarde PULLBACK ou RETESTE de zonas-chave
- Confirme com REAÇÃO DO PREÇO (rejeição, engolfo, pin bar)

═══════════════════════════════════════════════════════
🧠 PADRÕES E CONFLUÊNCIAS (SETUP A+)
═══════════════════════════════════════════════════════

REVERSÃO (mínimo 3 confluências):
- OCO / OCO Invertido em zona institucional
- Topo/Fundo Duplo com divergência RSI
- Falha de rompimento (fake breakout) + volume
- Stop hunt em região óbvia + reversão imediata

CONTINUAÇÃO (mínimo 2 confluências):
- Pullback em EMA 21 com rejeição
- Reteste de suporte/resistência rompido
- Bandeira/Flâmula após movimento forte

═══════════════════════════════════════════════════════
⚔️ REGRAS DE ENTRADA E SAÍDA
═══════════════════════════════════════════════════════

ANTES DE ABRIR TRADE:
- Confirme tendência macro (4H/1H)
- Aguarde pullback/reteste
- Verifique confluências
- Stop em zona estrutural clara (swing high/low)

TAKE PROFIT:
- RR mínimo 2:1 para primeiro alvo
- Parciais em zonas de liquidez
- Trailing após 1.5R de lucro

═══════════════════════════════════════════════════════

"""

        # Informações da conta
        prompt += f"\n📊 ESTADO DA CONTA:\n"
        prompt += f"- Equity: ${account_info.get('equity', 0):.2f}\n"
        prompt += f"- Drawdown Hoje: {account_info.get('daily_drawdown', 0):.2f}%\n"
        prompt += f"- Posições Abertas: {len(open_positions)}\n"
        
        # Limites de risco
        prompt += f"\n⚠️ LIMITES DE RISCO:\n"
        prompt += f"- Max Posições: {risk_limits.get('max_open_trades', 3)}\n"
        prompt += f"- Max Leverage: {risk_limits.get('max_leverage', 20)}x\n"
        prompt += f"- Risco por Trade: {risk_limits.get('risk_per_trade_pct', 1.0)}%\n"
        
        # Posições abertas
        if open_positions:
            prompt += f"\n📈 POSIÇÕES ABERTAS:\n"
            for pos in open_positions:
                prompt += f"- {pos.get('symbol')}: {pos.get('side')} ${pos.get('size', 0):.2f} | PnL: {pos.get('pnl_pct', 0):.2f}%\n"
        
        # Contexto de mercado
        prompt += f"\n🔍 ANÁLISE DE MERCADO:\n"
        for ctx in market_contexts:
            symbol = ctx.get('symbol', 'UNKNOWN')
            price = ctx.get('current_price', 0)
            
            prompt += f"\n=== {symbol} (Preço: ${price:.4f}) ===\n"
            
            # EMAs e RSI
            ema9 = ctx.get('ema_9', 0)
            ema21 = ctx.get('ema_21', 0)
            rsi = ctx.get('rsi', 50)
            
            prompt += f"EMA9: ${ema9:.4f} | EMA21: ${ema21:.4f} | RSI: {rsi:.1f}\n"
            
            # Regime
            regime = ctx.get('regime', 'UNKNOWN')
            prompt += f"Regime: {regime}\n"
            
            # Sinais técnicos se disponíveis
            signals = ctx.get('signals', {})
            if signals:
                prompt += f"Sinais: {signals}\n"
        
        # Formato de resposta
        prompt += """

═══════════════════════════════════════════════════════
📝 FORMATO DE RESPOSTA (JSON OBRIGATÓRIO)
═══════════════════════════════════════════════════════

Responda APENAS com um JSON válido. NADA de texto antes ou depois.

Se NÃO houver oportunidade clara:
{"action": "hold", "reason": "Motivo claro e específico"}

Se houver oportunidade de ABERTURA:
{
  "action": "open",
  "symbol": "SÍMBOLO",
  "side": "long" ou "short",
  "size_usd": valor entre 20-100,
  "leverage": entre 1-20,
  "stop_loss_price": preço exato do stop,
  "take_profit_price": preço exato do alvo,
  "confidence": 0.0 a 1.0,
  "reason": "Setup: padrão encontrado + confluências"
}

Se houver ação em posição aberta:
{"action": "close", "symbol": "SÍMBOLO", "reason": "motivo"}
{"action": "increase", "symbol": "SÍMBOLO", "size_usd": 20, "reason": "motivo"}
{"action": "decrease", "symbol": "SÍMBOLO", "size_usd": 20, "reason": "motivo"}
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
