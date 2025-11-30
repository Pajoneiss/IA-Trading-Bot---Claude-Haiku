"""
AI Decision Engine - VERSÃO AUTÔNOMA
A IA decide TUDO: leverage, stop loss, take profit, tamanho, etc.
"""
import json
import logging
import os
from typing import Dict, List, Optional, Any
import anthropic

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
            
            if decisions:
                logger.info(f"✅ IA retornou {len(decisions)} decisões")
                for dec in decisions:
                    if dec.get('action') == 'hold':
                        logger.info(f"  → HOLD: {dec.get('reason', 'sem motivo')}")
                    else:
                        logger.info(
                            f"  → {dec.get('symbol')} {dec.get('action')} {dec.get('side', '')} "
                            f"| ${dec.get('size_usd', 0):.0f} @ {dec.get('leverage', 1)}x"
                        )
            else:
                logger.info("ℹ️  IA não recomendou nenhuma ação")
            
            return decisions
            
        except Exception as e:
            logger.error(f"Erro ao consultar Claude API: {e}")
            return self._decide_fallback(market_contexts, account_info, open_positions)
    
    def _build_prompt(self,
                      market_contexts: List[Dict[str, Any]],
                      account_info: Dict[str, Any],
                      open_positions: List[Dict[str, Any]],
                      risk_limits: Dict[str, Any]) -> str:
        """Constrói prompt para IA 100% autônoma"""
        
        prompt = """Você é um TRADER AUTÔNOMO de criptomoedas operando perpetuals na Hyperliquid.

Você tem TOTAL AUTONOMIA para decidir TUDO:
- Se vai operar ou não
- Qual moeda operar
- Long ou Short  
- Quanto dinheiro arriscar (em USD)
- Qual alavancagem usar (1x até 50x)
- Onde colocar Stop Loss (preço exato)
- Onde colocar Take Profit (preço exato)
- Se vai aumentar, diminuir ou fechar posições

REGRAS DE SOBREVIVÊNCIA (únicas regras fixas):
1. Nunca use mais de 30% do equity em uma única operação
2. Leverage alto (>20x) = stop loss OBRIGATORIAMENTE mais apertado
3. Se não tiver certeza, retorne "hold" - não operar é uma decisão válida
4. Considere o funding rate antes de abrir posição
5. Se uma posição está perdendo muito (>5%), considere fechar

CÁLCULO DE CONFIANÇA (confidence):
Você DEVE incluir um campo "confidence" (0.0 a 1.0) em todas as decisões.
Use esta lógica para calcular:

• Base inicial: 0.3 (30%)

• EMAs (tendência):
  - Todas alinhadas a favor: +0.2
  - Parcialmente favoráveis: +0.1
  - Mistas/Neutras: +0.0

• RSI:
  - Favorável (ex: 35-45 em suporte para LONG): +0.15
  - Neutro: +0.0
  - Contra: -0.1 a -0.2

• Volatilidade/Contexto:
  - Saudável com liquidez: +0.1
  - Muito baixa (parado): -0.1
  - Caos/Wicks enormes: -0.05

• Qualidade do Setup:
  - Confluência clara: Ajustar até 0.8-0.9
  - Especulativo/Contra-tendência: Máximo 0.5-0.6

LIMITES:
- Mínimo 0.1 para trades (OPEN)
- Máximo 0.95
- Para HOLD: 0.4 (neutro/perigoso) a 0.8 (hold convicto)

"""
        
        # Estado da conta
        prompt += f"""
══════════════════════════════════════════
ESTADO DA CONTA
══════════════════════════════════════════
Equity Total: ${account_info.get('equity', 0):.2f}
PnL do Dia: {account_info.get('daily_pnl_pct', 0):.2f}%

"""
        
        # Posições abertas
        prompt += "══════════════════════════════════════════\n"
        prompt += "POSIÇÕES ABERTAS\n"
        prompt += "══════════════════════════════════════════\n"
        
        if open_positions:
            for pos in open_positions:
                symbol = pos.get('symbol', 'N/A')
                side = pos.get('side', 'N/A')
                entry = pos.get('entry_price', 0)
                size = pos.get('size', 0)
                pnl_pct = pos.get('unrealized_pnl_pct', 0)
                leverage = pos.get('leverage', 1)
                
                prompt += f"""
{symbol} - {side.upper()}
  Entry: ${entry:.4f}
  Size: {size:.4f}
  PnL: {pnl_pct:+.2f}%
  Leverage: {leverage}x
"""
        else:
            prompt += "\nNenhuma posição aberta.\n"
        
        # Dados de mercado
        prompt += "\n══════════════════════════════════════════\n"
        prompt += "DADOS DE MERCADO\n"
        prompt += "══════════════════════════════════════════\n"
        
        for ctx in market_contexts:
            symbol = ctx.get('symbol', 'N/A')
            price = ctx.get('price', 0)
            change_24h = ctx.get('change_24h', 0)
            ind = ctx.get('indicators', {})
            
            trend = ind.get('trend', 'neutral')
            strength = ind.get('trend_strength', 0)
            rsi = ind.get('rsi', 50)
            volatility = ind.get('volatility_pct', 0)
            funding = ctx.get('funding_rate', 0)
            
            prompt += f"""
📊 {symbol}
   Preço: ${price:,.4f} ({change_24h:+.2f}% 24h)
   Tendência: {trend.upper()} (força: {strength:.2f})
   RSI: {rsi:.1f}
   Volatilidade: {volatility:.2f}%
   Funding: {funding*100:.4f}%
"""
            
            # Adiciona info de candles se disponível
            if ind.get('ema_9') and ind.get('ema_21'):
                ema_cross = "BULLISH" if ind['ema_9'] > ind['ema_21'] else "BEARISH"
                prompt += f"   EMAs: {ema_cross} (EMA9 vs EMA21)\n"
        
        # Instruções de resposta
        prompt += """

══════════════════════════════════════════
SUA DECISÃO
══════════════════════════════════════════

Analise TUDO e decida o que fazer. Você decide TODOS os parâmetros.

Retorne APENAS um JSON válido (sem texto antes ou depois):

{
  "actions": [
    {
      "action": "open",
      "symbol": "BTC",
      "side": "long",
      "size_usd": 50.0,
      "leverage": 10,
      "stop_loss_price": 94500.0,
      "take_profit_price": 98000.0,
      "reason": "Tendência alta, RSI saudável, bom R:R",
      "confidence": 0.85
    }
  ]
}

AÇÕES POSSÍVEIS:
- "open": Abrir nova posição (precisa de side, size_usd, leverage, stop_loss_price, take_profit_price)
- "close": Fechar posição existente (precisa de symbol e reason)
- "increase": Aumentar posição (precisa de symbol, size_usd e reason)
- "decrease": Diminuir posição (precisa de symbol, size_usd e reason)  
- "hold": Não fazer nada (só precisa de reason)

Se não quiser operar:
{
  "actions": [
    {
      "action": "hold",
      "reason": "Mercado indefinido, aguardando melhor setup",
      "confidence": 0.4
    }
  ]
}

RESPONDA APENAS COM O JSON:"""
        
        return prompt
    
    def _parse_ai_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse da resposta da IA"""
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
            actions = data.get('actions', [])
            
            valid_actions = []
            for action in actions:
                act_type = action.get('action', 'hold')
                
                # Hold - apenas loga
                if act_type == 'hold':
                    logger.info(f"🤚 IA decidiu HOLD: {action.get('reason', 'sem motivo')}")
                    continue
                
                # Open - valida campos obrigatórios
                if act_type == 'open':
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
                    if action['leverage'] > 50:
                        action['leverage'] = 50
                    if action['leverage'] < 1:
                        action['leverage'] = 1
                    
                    valid_actions.append(action)
                
                # Close
                elif act_type == 'close':
                    if not action.get('symbol'):
                        continue
                    valid_actions.append(action)
                
                # Increase/Decrease
                elif act_type in ('increase', 'decrease'):
                    if not action.get('symbol'):
                        continue
                    if not action.get('size_usd'):
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
