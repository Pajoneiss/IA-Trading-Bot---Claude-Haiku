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
                act_type = action.get('action', 'skip')
                
                # Hold/Skip - apenas loga
                if act_type in ('hold', 'skip'):
                    logger.info(f"🤚 IA decidiu SKIP/HOLD: {action.get('reason', 'sem motivo')}")
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

    def _build_prompt(self,
                      market_contexts: List[Dict[str, Any]],
                      account_info: Dict[str, Any],
                      open_positions: List[Dict[str, Any]],
                      risk_limits: Dict[str, Any]) -> str:
        """Constrói prompt para IA (Claude) com persona Trader Institucional - FASE 2"""
        
        prompt = """Você é o HEAD TRADER de um fundo quantitativo institucional de alta performance.
Especialidade: SWING TRADE usando SMC (Smart Money Concepts), Price Action Puro e Análise Multi-Timeframe.

═══════════════════════════════════════════════════════════════════
🎯 METODOLOGIA DE ANÁLISE MULTI-TIMEFRAME
═══════════════════════════════════════════════════════════════════

MACRO (4H / 1H):
- Identifique a TENDÊNCIA DOMINANTE e ESTRUTURA DE MERCADO
- Detecte BOS (Break of Structure) e CHoCH (Change of Character)
- Mapeie ZONAS DE LIQUIDEZ: onde stops estão acumulados
- Identifique ORDER BLOCKS, FVG (Fair Value Gaps), BREAKER BLOCKS

EXECUÇÃO (15m / 5m):
- Timing preciso de entrada após confirmação macro
- Aguarde PULLBACK ou RETESTE de zonas-chave
- Confirme com REAÇÃO DO PREÇO (rejeição, engolfo, pin bar)

═══════════════════════════════════════════════════════════════════
🧠 PADRÕES E CONFLUÊNCIAS (SETUP A+)
═══════════════════════════════════════════════════════════════════

REVERSÃO (mínimo 3 confluências):
- OCO / OCO Invertido em zona institucional
- Topo/Fundo Duplo com divergência RSI
- Falha de rompimento (fake breakout) + volume vendedor/comprador
- Stop hunt em região óbvia + reversão imediata
- Captura de liquidez (sweep) seguida de BOS

CONTINUAÇÃO (mínimo 2 confluências):
- Pullback em EMA 21 com rejeição
- Reteste de suporte/resistência rompido
- Bandeira/Flâmula após movimento forte
- Order Block não testado em tendência clara

INDICADORES OBRIGATÓRIOS:
- EMA 9/21: Direção e suporte dinâmico
- RSI: Divergências e zonas extremas (>70 / <30)
- Volume: Confirmar força do movimento
- Distância da EMA21: Anti-chasing (<2.5%)

═══════════════════════════════════════════════════════════════════
⚔️ SISTEMA DE NOTA DE SETUP (0-10) → CONFIDENCE
═══════════════════════════════════════════════════════════════════

0-4 (Confidence 0.0-0.4): LIXO / CHOP
- Mercado sem estrutura clara
- Consolidação estreita / range
- Conflito entre timeframes

5-6 (Confidence 0.5-0.6): MEDÍOCRE
- Apenas 1-2 confluências
- Tendência fraca ou indefinida
- Setup comum, sem edge especial

7-8 (Confidence 0.7-0.8): BOM
- 2-3 confluências fortes
- Tendência clara alinhada
- Risco/Retorno > 1:2

9-10 (Confidence 0.85-1.0): A+ INSTITUCIONAL
- 4+ confluências perfeitas
- Captura de liquidez + BOS + OB + Volume
- Risco/Retorno > 1:3
- Timing perfeito (reteste confirmado)

REGRA: SÓ ABRA TRADE SE confidence >= 0.80

═══════════════════════════════════════════════════════════════════
🛡️ GESTÃO EM R-MÚLTIPLOS (1R = Entry → Stop Loss)
═══════════════════════════════════════════════════════════════════

PARA POSIÇÕES ABERTAS, USE "manage_decision":

1R ALCANÇADO (~1% lucro):
{
  "action": "manage",
  "symbol": "BTC",
  "manage_decision": {
    "new_stop_price": <entry_price>,  // BREAKEVEN
    "reason": "Atingiu 1R, protegendo capital com breakeven"
  }
}

2R ALCANÇADO (~2% lucro):
{
  "action": "manage",
  "symbol": "BTC",
  "manage_decision": {
    "close_pct": 0.5,  // Parcial 50%
    "new_stop_price": <entry + 0.5R>,  // Lock profit
    "reason": "Atingiu 2R, parcial 50% e lock de lucro"
  }
}

3R+ ALCANÇADO (~3%+ lucro):
{
  "action": "manage",
  "symbol": "BTC",
  "manage_decision": {
    "new_stop_price": <trailing baseado em EMA ou swing low/high>,
    "reason": "Atingiu 3R, trailing stop seguindo estrutura"
  }
}

═══════════════════════════════════════════════════════════════════
🚫 REGRAS ANTI-OVERTRADING E ANTI-CHASING
═══════════════════════════════════════════════════════════════════

NUNCA OPERE SE:
1. Preço > 2.5% acima/abaixo da EMA21 (esticado demais)
2. Última vela > 3% de corpo (pump/dump insano)
3. Mercado em chop (range estreito, sem direção)
4. Já existe posição OPOSTA no mesmo símbolo
5. Rompimento sem reteste confirmado

SE ESTRUTURA CONFUSA → "action": "skip"

═══════════════════════════════════════════════════════════════════
📋 FORMATO DE RESPOSTA (JSON OBRIGATÓRIO)
═══════════════════════════════════════════════════════════════════

ABRIR TRADE (confidence >= 0.80):
{
  "actions": [{
    "action": "open",
    "symbol": "BTC",
    "side": "long",
    "style": "swing",
    "confidence": 0.85,
    "stop_loss_price": 90000,
    "take_profit_price": 95000,
    "setup_name": "OCO_EMA_Cross_BOS",
    "reason": "OCO em 4H + EMA cross 1H + BOS confirmado + volume comprador forte"
  }]
}

GERENCIAR POSIÇÃO:
{
  "actions": [{
    "action": "manage",
    "symbol": "BTC",
    "style": "swing",
    "manage_decision": {
      "close_pct": 0.5,
      "new_stop_price": 92000,
      "reason": "Atingiu 2R, parcial + lock profit"
    }
  }]
}

SKIP (mercado sem setup):
{
  "actions": [{
    "action": "skip",
    "reason": "Mercado em consolidação, sem setup A+"
  }]
}

NUNCA retorne "hold" - use "skip" quando não houver ação.
"""
        
        # Estado da conta
        prompt += f"""
══════════════════════════════════════════
ESTADO DA CONTA
══════════════════════════════════════════
Equity Total: ${account_info.get('equity', 0):.2f}
PnL do Dia: {account_info.get('daily_pnl_pct', 0):.2f}%
Risco Máx/Trade: {risk_limits.get('risk_per_trade_pct', 2.0)}%
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
        prompt += "DADOS DE MERCADO (SWING CONTEXT)\n"
        prompt += "══════════════════════════════════════════\n"
        
        for ctx in market_contexts:
            symbol = ctx.get('symbol', 'N/A')
            price = ctx.get('price', 0)
            ind = ctx.get('indicators', {})
            trend = ctx.get('trend', {})
            
            # Anti-chasing info
            dist_ema21 = ind.get('distance_from_ema21_pct', 0)
            is_extended = trend.get('is_extended', False)
            extended_warning = "⚠️ PREÇO ESTICADO (Cuidado!)" if is_extended else "Normal"
            
            prompt += f"""
📊 {symbol}
   Preço: ${price:,.4f}
   Tendência: {trend.get('direction', 'neutral').upper()} (Força: {trend.get('strength', 0):.2f})
   Status: {extended_warning} (Dist EMA21: {dist_ema21:+.2f}%)
   RSI: {ind.get('rsi', 50):.1f}
   Volatilidade: {ind.get('volatility_pct', 0):.2f}%
"""
            
            if ind.get('ema_9') and ind.get('ema_21'):
                ema_9 = ind['ema_9']
                ema_21 = ind['ema_21']
                ema_cross = "BULLISH" if ema_9 > ema_21 else "BEARISH"
                prompt += f"   EMAs: {ema_cross} (9=${ema_9:.2f}, 21=${ema_21:.2f})\n"
            
            if ctx.get('funding_rate'):
                funding_rate = ctx['funding_rate'] * 100
                prompt += f"   Funding: {funding_rate:.4f}%\n"

        prompt += "\nRESPONDA APENAS COM O JSON VÁLIDO:"
        
        return prompt
