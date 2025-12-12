"""
MODO CLAUDE GLOBAL (GLOBAL_IA)
==============================

Neste modo, a IA é 100% responsável por todas as decisões de trading.
O bot atua apenas como executor técnico e fornecedor de dados.

Fluxo:
1. build_global_state() → Monta JSON com estado completo da conta
2. call_claude_global() → Envia para Claude e recebe ações
3. parse_global_actions() → Parseia JSON de resposta
4. execute_global_actions() → Executa ações sem filtros tradicionais

Autor: Claude (Global IA Mode)
Data: 2024-12-12
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict

import anthropic

logger = logging.getLogger(__name__)


# ============================================================
# PROMPT DO TRADER GLOBAL - 100% AUTÔNOMO + DADOS RICOS
# ============================================================

GLOBAL_TRADER_SYSTEM_PROMPT = """Você é o TRADER GLOBAL AUTÔNOMO desta conta na Hyperliquid.

Você não segue estilo fixo.
Você pensa como um trader institucional que opera diversos regimes:
- tendência
- range
- reversão
- momentos de consolidação
- alta volatilidade
- baixa liquidez
- eventos assimétricos
- micro oportunidades

Seu trabalho é FAZER O CAPITAL TRABALHAR.

Você decide:
- entradas e saídas
- reversões
- parciais
- aumentos de posição
- reduções
- breakeven
- alvos e stops
- alavancagem
- sizing
- reentradas

Você deve operar quando houver qualquer vantagem razoável — não exija setup perfeito.

## DADOS DISPONÍVEIS NO STATE

O STATE contém dados RICOS para cada símbolo:
- price: preço atual
- change_1h_pct, change_4h_pct, change_24h_pct: mudanças percentuais
- volatility: low/medium/high/very_high
- atr_pct: ATR como % do preço
- trend_1h, trend_4h, trend_1d: bullish/bearish/neutral/recovering/weakening
- momentum: strong_bullish/bullish/flat/bearish/strong_bearish
- rsi_14: RSI de 14 períodos (0-100)
- volume: low/normal/high
- range_position: near_low/middle/near_high
- funding: neutral/longs_pay/shorts_pay
- ema_position: above/below

Use TODOS esses dados para tomar decisões inteligentes.

## EVITE CHURN (REENTRADAS BURRAS)

Se você acabou de fechar uma posição em um símbolo com pequeno prejuízo (entre -0.1% e -2%):
- EVITE reentrar imediatamente na mesma direção no mesmo símbolo
- Considere reentrar apenas se:
  - O preço melhorou significativamente (caiu pelo menos 1% para nova entrada long)
  - Houve mudança clara de contexto (novo candle forte, mudança de regime, volume)
- Evite o padrão: stop curto → nova entrada quase no mesmo preço
- Isso aumenta custos de taxa sem melhorar o edge

## FORMATO DE RESPOSTA

Retorne APENAS JSON válido:

{
  "analysis": "Breve análise do mercado e seu raciocínio",
  "actions": [
    {
      "symbol": "BTC",
      "intent": "open_long | open_short | close | increase | decrease | adjust_sl | adjust_tp | breakeven",
      "size_usd": 150.0,
      "leverage": 5,
      "stop_loss_pct": 0.02,
      "take_profit_pct": 0.04,
      "new_sl_price": null,
      "new_tp_price": null,
      "partial_close_pct": 0.0,
      "reason": "explique brevemente seu raciocínio"
    }
  ]
}

Se não houver oportunidade clara:
{
  "analysis": "Mercado sem setups claros / aguardando confirmação",
  "actions": []
}

NUNCA responda fora de JSON.
NUNCA inclua texto antes ou depois do JSON.
"""

CHAT_TRADER_SYSTEM_PROMPT = """Você é o TRADER GLOBAL AUTÔNOMO que está operando esta conta na Hyperliquid em tempo real.

Você está vendo o STATE atual da conta (equity, margens, posições abertas, volatilidade, tendências, preços, pnl do dia).

Responda como um TRADER PROFISSIONAL que está vendo o mercado AGORA, analisando:

- as posições abertas (se houver)
- contexto de mercado atual
- oportunidades que você enxerga
- riscos no radar
- possíveis próximos passos
- como você está pensando este exato momento
- por que tomou ou não tomou certas decisões

Fale em linguagem clara, direta e profissional.
Seja honesto sobre incertezas.
Explique seu raciocínio.

NÃO use JSON.
Responda em texto livre, como um trader humano conversando.
"""


@dataclass
class GlobalAction:
    """Ação decidida pela IA Global"""
    symbol: str
    intent: str  # open_long, open_short, close, increase, decrease, adjust_sl, adjust_tp, breakeven
    size_usd: float = 0.0
    leverage: int = 5
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.04
    new_sl_price: Optional[float] = None
    new_tp_price: Optional[float] = None
    partial_close_pct: float = 0.0
    reason: str = ""


class GlobalIAMode:
    """
    Modo GLOBAL_IA - IA é 100% responsável
    
    Bypass de filtros tradicionais:
    - Ignora CooldownManager
    - Ignora TrendGuard
    - Ignora QualityGate (além de sanity checks)
    - Ignora ScalpFilters
    
    Apenas bloqueia quando:
    - size_usd <= 0
    - Símbolo inválido
    - Notional abaixo do mínimo
    - Erro duro da API
    """
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 model: str = "claude-sonnet-4-20250514",
                 logger_instance=None):
        self.logger = logger_instance or logger
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.client = None
        
        if self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
            self.logger.info(f"[GLOBAL_IA] 🧠 Inicializado com modelo {model}")
        else:
            self.logger.warning("[GLOBAL_IA] ⚠️ Sem API key - modo desabilitado")
    
    def build_global_state(self,
                           equity: float,
                           free_margin: float,
                           day_pnl_pct: float,
                           positions: List[Dict],
                           market_snapshot: List[Dict],
                           recent_trades: List[Dict] = None) -> Dict:
        """
        Monta o STATE JSON para enviar à IA
        
        Args:
            equity: Equity total da conta
            free_margin: Margem livre disponível
            day_pnl_pct: PnL do dia em %
            positions: Lista de posições abertas
            market_snapshot: Dados de mercado por símbolo
            recent_trades: Trades recentes (últimas 24h)
            
        Returns:
            Dict com state completo
        """
        state = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "account": {
                "equity": round(equity, 2),
                "free_margin": round(free_margin, 2),
                "day_pnl_pct": round(day_pnl_pct, 2),
                "margin_used_pct": round((1 - free_margin/equity) * 100, 1) if equity > 0 else 0
            },
            "positions": self._format_positions(positions),
            "market": self._format_market_snapshot(market_snapshot),
            "recent_trades": recent_trades or [],
            "mode": "GLOBAL_IA",
            "execution_mode": os.getenv("EXECUTION_MODE", "PAPER_ONLY")
        }
        
        return state
    
    def _format_positions(self, positions: List[Dict]) -> List[Dict]:
        """Formata posições para o state"""
        formatted = []
        for pos in positions:
            formatted.append({
                "symbol": pos.get('symbol', ''),
                "side": pos.get('side', ''),
                "size": pos.get('size', 0),
                "entry_price": pos.get('entry_price', 0),
                "current_price": pos.get('current_price', pos.get('mark_price', 0)),
                "pnl_usd": round(pos.get('unrealized_pnl', 0), 2),
                "pnl_pct": round(pos.get('pnl_pct', pos.get('unrealized_pnl_pct', 0)), 2),
                "leverage": pos.get('leverage', 5),
                "stop_loss": pos.get('stop_loss', pos.get('stop_loss_price')),
                "take_profit": pos.get('take_profit', pos.get('take_profit_price')),
                "duration_hours": pos.get('duration_hours', 0)
            })
        return formatted
    
    def _format_market_snapshot(self, market_data: List[Dict]) -> List[Dict]:
        """Formata dados de mercado para o state"""
        formatted = []
        for data in market_data[:10]:  # Limita a 10 símbolos para não estourar tokens
            formatted.append({
                "symbol": data.get('symbol', ''),
                "price": data.get('price', data.get('current_price', 0)),
                "change_24h_pct": data.get('change_24h_pct', 0),
                "volume_24h": data.get('volume_24h', 0),
                "trend_bias": data.get('trend_bias', data.get('regime_info', {}).get('trend_bias', 'neutral')),
                "regime": data.get('regime', data.get('regime_info', {}).get('regime', 'unknown')),
                "volatility": data.get('volatility', 'normal'),
                "ema_cross": data.get('ema_cross', 'none'),
                "core_setup": data.get('core_analysis', {}).get('has_valid_setup', False),
                "setup_type": data.get('core_analysis', {}).get('setup_type', 'none')
            })
        return formatted
    
    def call_claude_global(self, state: Dict) -> Tuple[str, List[GlobalAction]]:
        """
        Chama Claude com o STATE e recebe ações
        
        Args:
            state: State JSON completo
            
        Returns:
            (analysis, list of GlobalAction)
        """
        if not self.client:
            self.logger.error("[GLOBAL_IA] Cliente não inicializado")
            return "Erro: Cliente não inicializado", []
        
        try:
            # Monta o prompt
            user_message = f"""Aqui está o STATE atual da conta:

```json
{json.dumps(state, indent=2, ensure_ascii=False)}
```

Analise e decida as ações a tomar. Responda em JSON conforme o formato especificado."""

            self.logger.info("[GLOBAL_IA] 🧠 Chamando Claude para decisão global...")
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=GLOBAL_TRADER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}]
            )
            
            response_text = response.content[0].text
            self.logger.debug(f"[GLOBAL_IA] Resposta bruta: {response_text[:500]}...")
            
            # Parseia a resposta
            analysis, actions = self._parse_global_response(response_text)
            
            self.logger.info(f"[GLOBAL_IA] ✅ Análise: {analysis[:100]}...")
            self.logger.info(f"[GLOBAL_IA] ✅ {len(actions)} ações decididas")
            
            return analysis, actions
            
        except Exception as e:
            self.logger.error(f"[GLOBAL_IA] ❌ Erro ao chamar Claude: {e}")
            return f"Erro: {str(e)}", []
    
    def _parse_global_response(self, response_text: str) -> Tuple[str, List[GlobalAction]]:
        """Parseia resposta JSON da IA"""
        try:
            # Tenta extrair JSON da resposta
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                return response_text, []
            
            json_str = response_text[json_start:json_end]
            data = json.loads(json_str)
            
            analysis = data.get('analysis', '')
            actions_raw = data.get('actions', [])
            
            actions = []
            for action_data in actions_raw:
                try:
                    action = GlobalAction(
                        symbol=action_data.get('symbol', ''),
                        intent=action_data.get('intent', 'hold'),
                        size_usd=float(action_data.get('size_usd', 0)),
                        leverage=int(action_data.get('leverage', 5)),
                        stop_loss_pct=float(action_data.get('stop_loss_pct', 0.02)),
                        take_profit_pct=float(action_data.get('take_profit_pct', 0.04)),
                        new_sl_price=action_data.get('new_sl_price'),
                        new_tp_price=action_data.get('new_tp_price'),
                        partial_close_pct=float(action_data.get('partial_close_pct', 0)),
                        reason=action_data.get('reason', '')
                    )
                    actions.append(action)
                except Exception as e:
                    self.logger.warning(f"[GLOBAL_IA] Erro ao parsear ação: {e}")
            
            return analysis, actions
            
        except json.JSONDecodeError as e:
            self.logger.error(f"[GLOBAL_IA] Erro ao parsear JSON: {e}")
            return response_text, []
    
    def validate_action(self, action: GlobalAction, equity: float, free_margin: float) -> Tuple[bool, str]:
        """
        Valida ação antes de executar (sanity checks apenas)
        
        BYPASS de filtros tradicionais - apenas bloqueia erros técnicos
        
        Returns:
            (is_valid, reason)
        """
        # 1. Símbolo válido
        if not action.symbol or len(action.symbol) < 2:
            return False, "Símbolo inválido"
        
        # 2. Intent válido
        valid_intents = ['open_long', 'open_short', 'close', 'increase', 'decrease', 
                        'adjust_sl', 'adjust_tp', 'breakeven', 'hold']
        if action.intent not in valid_intents:
            return False, f"Intent inválido: {action.intent}"
        
        # 3. Para abertura: size > 0
        if action.intent in ['open_long', 'open_short', 'increase']:
            if action.size_usd <= 0:
                return False, "size_usd deve ser > 0"
            
            # Notional mínimo (Hyperliquid = $10)
            if action.size_usd < 10:
                return False, f"size_usd={action.size_usd} abaixo do mínimo ($10)"
            
            # Margem disponível
            required_margin = action.size_usd / action.leverage
            if required_margin > free_margin * 0.9:  # 90% da margem livre
                return False, f"Margem insuficiente: precisa ${required_margin:.2f}, tem ${free_margin:.2f}"
        
        # 4. Leverage válida
        if action.leverage < 1 or action.leverage > 50:
            return False, f"Leverage {action.leverage} fora do range (1-50)"
        
        # 5. Stop loss válido
        if action.stop_loss_pct > 0.10:  # Máximo 10%
            return False, f"Stop loss {action.stop_loss_pct*100}% muito alto (max 10%)"
        
        return True, "OK"
    
    def chat_with_trader(self, state: Dict, user_question: str) -> str:
        """
        Chat conversacional com a IA Trader
        
        Args:
            state: State atual da conta
            user_question: Pergunta do usuário
            
        Returns:
            Resposta em texto natural
        """
        if not self.client:
            return "❌ Erro: Cliente IA não inicializado"
        
        try:
            user_message = f"""Aqui está o STATE atual da conta que você está operando:

```json
{json.dumps(state, indent=2, ensure_ascii=False)}
```

O usuário perguntou:
"{user_question}"

Responda como trader profissional."""

            self.logger.info(f"[GLOBAL_IA] 💬 Chat: {user_question[:50]}...")
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=CHAT_TRADER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}]
            )
            
            return response.content[0].text
            
        except Exception as e:
            self.logger.error(f"[GLOBAL_IA] ❌ Erro no chat: {e}")
            return f"❌ Erro ao processar pergunta: {str(e)}"


# Singleton
_global_ia_mode: Optional[GlobalIAMode] = None

def get_global_ia_mode(api_key: str = None, logger_instance=None) -> GlobalIAMode:
    """Retorna instância singleton do GlobalIAMode"""
    global _global_ia_mode
    if _global_ia_mode is None:
        _global_ia_mode = GlobalIAMode(api_key=api_key, logger_instance=logger_instance)
    return _global_ia_mode
