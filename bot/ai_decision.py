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
📊 EMAs + VWAP = FERRAMENTA DE TIMING (NÃO REGRA ABSOLUTA)
═══════════════════════════════════════════════════════

PRIORIDADE DE LEITURA:
1. ESTRUTURA E LIQUIDEZ VÊM PRIMEIRO (BOS, CHoCH, topos/fundos, OB, FVG)
2. Depois, confirme direção com EMAs/VWAP:
   - Posição do preço em relação às EMAs e VWAP
   - Inclinação das EMAs (abrindo a favor ou flat em range)
3. EMAs/VWAP só geram trades se contexto estrutural fizer sentido!

PADRÃO DE REVERSÃO TÍPICO OPERÁVEL:
- Tendência anterior forte (alta ou baixa)
- Perda de força: candles menores, pavios, possíveis divergências
- EMA curta cruza a longa (ou preço respeita as duas alinhadas)
- VWAP é recuperado (reversão de baixa) ou perdido (reversão de alta)
- Estrutura confirma com HL (Higher Low) ou LH (Lower High)

O QUE EVITAR:
- NÃO operar TODO cruzamento de EMA
- EMAs "emboladas" (flat) no meio de range estreito = HOLD
- Chop score alto + range sujo = HOLD
- Sem justificativa estrutural = HOLD

═══════════════════════════════════════════════════════
🎚️ REGRAS DE EMA/VWAP POR MODO
═══════════════════════════════════════════════════════

MODO CONSERVADOR:
- EMA cross + VWAP a favor + estrutura clara de reversão (HL/HH ou LH/LL)
- OBRIGATÓRIO: confluência com suporte/resistência forte
- PRIORIZE ENTRAR NO PULLBACK (reteste das EMAs/VWAP)
- EMAs aqui são FILTRO DE CONFIRMAÇÃO, não gatilho

MODO BALANCEADO:
- EMA cross + VWAP pode ser GATILHO principal se:
  - Contexto estrutural razoável
  - Regime não for RANGE_CHOP extremo
- Preferir primeiro pullback após barra de cruzamento
- Stop abaixo do fundo que precedeu o cross (longs) ou acima do topo (shorts)
- Aceita setups "B" se RR e risco forem aceitáveis

MODO AGRESSIVO:
- Pode antecipar: entrar na própria barra de cruzamento
- Desde que exista:
  - Confirmação de volume/momentum
  - Contexto estrutural que faça sentido
- Ainda assim: respeitar Risk Manager, evitar EMA cross em RANGE_CHOP alto

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
            price = ctx.get('price', 0)  # Corrigido de 'current_price' para 'price'
            
            prompt += f"\n=== {symbol} (Preço: ${price:.4f}) ===\n"
            
            # Indicadores estão em um dict aninhado
            indicators = ctx.get('indicators', {})
            ema9 = indicators.get('ema_9') or 0
            ema21 = indicators.get('ema_21') or 0
            rsi = indicators.get('rsi') or 50
            volatility = indicators.get('volatility_pct') or 0
            
            prompt += f"EMA9: ${ema9:.4f} | EMA21: ${ema21:.4f} | RSI: {rsi:.1f} | Vol: {volatility:.2f}%\n"
            
            # Trend está em dict aninhado
            trend = ctx.get('trend', {})
            direction = trend.get('direction', 'neutral')
            strength = trend.get('strength', 0)
            prompt += f"Tendência: {direction.upper()} (força: {strength:.2f})\n"
            
            # Variação 24h
            change_24h = ctx.get('price_change_24h_pct', 0)
            prompt += f"Variação 24h: {change_24h:+.2f}%\n"
            
            # Phase2 data se disponível
            phase2 = ctx.get('phase2', {})
            if phase2 and isinstance(phase2, dict):
                structure = phase2.get('structure')
                patterns = phase2.get('patterns', [])
                if structure and isinstance(structure, dict):
                    prompt += f"Estrutura: {structure.get('trend', 'N/A')} | Último Swing: {structure.get('last_swing', 'N/A')}\n"
                if patterns and isinstance(patterns, list):
                    pattern_names = []
                    for p in patterns[:3]:
                        if isinstance(p, dict):
                            pattern_names.append(p.get('name', ''))
                        elif isinstance(p, str):
                            pattern_names.append(p)
                    if pattern_names:
                        prompt += f"Padrões: {', '.join(pattern_names)}\n"


        
        # Formato de resposta
        prompt += """

═══════════════════════════════════════════════════════
📝 FORMATO DE RESPOSTA (JSON OBRIGATÓRIO)
═══════════════════════════════════════════════════════

Você é um TREND FOLLOWER ESTRUTURAL. Seu papel:
1. Identificar tendências e entrar na direção delas
2. Posicionar STOP em NÍVEL ESTRUTURAL (não % arbitrário)
3. SEGURAR a posição enquanto estrutura estiver intacta
4. SAIR quando houver reversão clara de estrutura (CHoCH/BOS contra)

Responda APENAS com um JSON válido. NADA de texto antes ou depois.

Se NÃO houver oportunidade clara:
{"action": "hold", "reason": "Motivo claro e específico"}

Se houver oportunidade de ABERTURA (SWING):
{
  "action": "open",
  "symbol": "SÍMBOLO",
  "side": "long" ou "short",
  "style": "swing",
  "entry_price": preço sugerido de entrada,
  "entry_zone": [preço_min, preço_max],
  "structural_stop_price": preço do stop baseado em estrutura (swing high/low, OB, FVG),
  "invalid_level": preço onde ideia de trade fica inválida,
  "size_usd": valor entre 20-100 (calculado pelo risco),
  "leverage": entre 3-15,
  "confidence": 0.0 a 1.0,
  "management_plan": {
    "style": "TREND_FOLLOW",
    "min_rr_before_trim": 1.5,
    "trail_logic": "SWING_HIGHS_LOWS" ou "EMA21" ou "ATR_TRAILING"
  },
  "regime_context": "descrição breve do regime",
  "reason": "Setup: padrão + confluências + por que esse stop faz sentido"
}

IMPORTANTE SOBRE O STOP:
- O stop DEVE estar em um nível estrutural claro (último swing high/low, order block, FVG)
- NÃO use % arbitrário (ex: -2%)
- Se não houver estrutura clara para o stop, prefira HOLD
- A distância do stop define o tamanho da posição (risco fixo)

Se houver ação em posição aberta:
{"action": "close", "symbol": "SÍMBOLO", "reason": "motivo - CHoCH/reversão estrutural"}
{"action": "increase", "symbol": "SÍMBOLO", "size_usd": 20, "reason": "piramidação em pullback"}
{"action": "decrease", "symbol": "SÍMBOLO", "size_usd": 20, "reason": "parcial em target/exaustão"}
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
