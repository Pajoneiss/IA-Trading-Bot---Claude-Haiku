"""
RUNTIME SNAPSHOT
================

Módulo que centraliza o estado atual do bot em um dicionário estruturado,
pronto para ser consumido por um dashboard (web/app) no futuro.

Uso:
    from bot.runtime_snapshot import build_runtime_snapshot
    snapshot = build_runtime_snapshot(bot)
    
    # snapshot é um dict que pode ser serializado em JSON

Autor: Claude (Preparação Dashboard)
Data: 2024-12-13
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass  # Evita import circular

logger = logging.getLogger(__name__)


# ============================================================
# TRACKING DE ÚLTIMOS TRADES (para anti-churn)
# ============================================================

# Dicionário global para rastrear últimos exits por símbolo
_last_exits_by_symbol: Dict[str, Dict[str, Any]] = {}


def record_exit(symbol: str, side: str, exit_price: float, pnl_pct: float):
    """
    Registra um exit de posição para tracking anti-churn.
    
    Chamado quando uma posição é fechada completamente.
    
    Args:
        symbol: Símbolo (ex: "BTC", "SOL")
        side: Lado da posição ("long" ou "short")
        exit_price: Preço de saída
        pnl_pct: PnL percentual realizado
    """
    global _last_exits_by_symbol
    
    _last_exits_by_symbol[symbol] = {
        "exit_time": datetime.now(timezone.utc),
        "exit_price": exit_price,
        "side": side,
        "pnl_pct": round(pnl_pct, 2)
    }
    
    logger.info(f"[SNAPSHOT] Exit registrado: {symbol} {side} @ ${exit_price:.2f} ({pnl_pct:+.2f}%)")


def get_recent_exits() -> Dict[str, Dict[str, Any]]:
    """
    Retorna dicionário de exits recentes formatado para o STATE da IA.
    
    Returns:
        Dict com info de exits recentes por símbolo
    """
    global _last_exits_by_symbol
    
    now = datetime.now(timezone.utc)
    recent = {}
    
    for symbol, data in _last_exits_by_symbol.items():
        exit_time = data.get("exit_time")
        if exit_time:
            delta = now - exit_time
            minutes_ago = delta.total_seconds() / 60
            
            # Só inclui exits das últimas 2 horas
            if minutes_ago < 120:
                recent[symbol] = {
                    "minutes_ago": round(minutes_ago, 1),
                    "side": data.get("side"),
                    "pnl_pct": data.get("pnl_pct"),
                    "exit_price": data.get("exit_price")
                }
    
    return recent


def clear_old_exits(max_age_hours: int = 24):
    """Remove exits antigos da memória"""
    global _last_exits_by_symbol
    
    now = datetime.now(timezone.utc)
    to_remove = []
    
    for symbol, data in _last_exits_by_symbol.items():
        exit_time = data.get("exit_time")
        if exit_time:
            delta = now - exit_time
            if delta.total_seconds() > max_age_hours * 3600:
                to_remove.append(symbol)
    
    for symbol in to_remove:
        del _last_exits_by_symbol[symbol]


# ============================================================
# BUILD RUNTIME SNAPSHOT
# ============================================================

def build_runtime_snapshot(bot) -> Dict[str, Any]:
    """
    Constrói snapshot completo do estado do bot.
    
    Retorna um dicionário estruturado pronto para:
    - Serialização em JSON
    - Consumo por dashboard web/app
    - Logging detalhado
    - Debugging
    
    Args:
        bot: Instância do HyperliquidBot
        
    Returns:
        Dict com estado completo do bot
    """
    now = datetime.now(timezone.utc)
    
    snapshot = {
        "timestamp_utc": now.isoformat(),
        "version": "1.0.0",
        
        # ===== MODO DE EXECUÇÃO =====
        "execution": {
            "mode": _get_execution_mode(bot),
            "trading_mode": _get_trading_mode(bot),
            "is_paused": getattr(bot, 'paused', False),
            "live_trading": getattr(bot, 'live_trading', False)
        },
        
        # ===== CONTA =====
        "account": _build_account_info(bot),
        
        # ===== POSIÇÕES =====
        "positions": _build_positions_info(bot),
        
        # ===== AI BUDGET =====
        "ai_budget": _build_ai_budget_info(bot),
        
        # ===== GLOBAL_IA STATUS =====
        "global_ia": _build_global_ia_info(bot),
        
        # ===== RISK MANAGER =====
        "risk": _build_risk_info(bot),
        
        # ===== RECENT EXITS (anti-churn) =====
        "recent_exits": get_recent_exits(),
        
        # ===== MERCADO =====
        "market": _build_market_info(bot),
        
        # ===== SISTEMA =====
        "system": {
            "uptime_seconds": _get_uptime(bot),
            "trading_pairs_count": len(getattr(bot, 'trading_pairs', [])),
            "last_iteration": getattr(bot, 'last_iteration_time', None)
        }
    }
    
    return snapshot


def _get_execution_mode(bot) -> str:
    """
    Retorna modo de execução (PAPER_ONLY/SHADOW/LIVE).
    
    FONTE ÚNICA DA VERDADE para execution mode.
    """
    # 1. Tenta via execution_manager
    try:
        exec_manager = getattr(bot, 'execution_manager', None)
        if exec_manager and hasattr(exec_manager, 'current_mode'):
            return exec_manager.current_mode.value
    except Exception:
        pass
    
    # 2. Tenta via env EXECUTION_MODE
    env_mode = os.getenv("EXECUTION_MODE", "")
    if env_mode:
        return env_mode
    
    # 3. Fallback baseado em live_trading
    live = getattr(bot, 'live_trading', False)
    return "LIVE" if live else "PAPER_ONLY"


def _get_trading_mode(bot) -> str:
    """Retorna modo de trading (CONSERVADOR/BALANCEADO/AGRESSIVO/GLOBAL_IA)"""
    try:
        mode_manager = getattr(bot, 'mode_manager', None)
        if mode_manager and hasattr(mode_manager, 'current_mode'):
            return mode_manager.current_mode.value
    except Exception:
        pass
    return "BALANCEADO"


def _build_account_info(bot) -> Dict[str, Any]:
    """
    Constrói info da conta com margem real.
    
    Busca dados diretamente do client quando possível.
    """
    result = {
        "equity": 0,
        "free_margin": 0,
        "used_margin": 0,
        "available_balance": 0,
        "day_pnl_pct": 0,
        "week_pnl_pct": 0,
        "daily_drawdown_pct": 0
    }
    
    # Tenta buscar do user_state (dados frescos da exchange)
    try:
        client = getattr(bot, 'client', None)
        if client:
            user_state = client.get_user_state()
            
            # Campos que Hyperliquid pode retornar
            equity = float(user_state.get('account_value', 0) or user_state.get('accountValue', 0) or 0)
            withdrawable = float(user_state.get('withdrawable', 0) or 0)
            margin_used = float(user_state.get('margin_used', 0) or user_state.get('marginUsed', 0) or 0)
            
            result["equity"] = round(equity, 2)
            result["available_balance"] = round(withdrawable, 2)
            result["used_margin"] = round(margin_used, 2)
            
            # free_margin = equity - margin_used (estimativa)
            # Se withdrawable disponível, usa ele
            if withdrawable > 0:
                result["free_margin"] = round(withdrawable, 2)
            elif equity > 0 and margin_used >= 0:
                result["free_margin"] = round(max(0, equity - margin_used), 2)
            else:
                result["free_margin"] = round(equity * 0.8, 2)  # Estimativa 80%
    except Exception as e:
        logger.debug(f"[SNAPSHOT] Erro ao buscar user_state: {e}")
    
    # Complementa com dados do risk_manager
    risk_manager = getattr(bot, 'risk_manager', None)
    if risk_manager:
        if result["equity"] == 0:
            result["equity"] = round(getattr(risk_manager, 'current_equity', 0), 2)
        result["day_pnl_pct"] = round(getattr(risk_manager, 'daily_drawdown_pct', 0), 2)  # Note: daily_drawdown_pct é o PnL do dia
        result["daily_drawdown_pct"] = round(abs(min(0, getattr(risk_manager, 'daily_drawdown_pct', 0))), 2)
    
    return result


def _build_positions_info(bot) -> Dict[str, Any]:
    """Constrói info das posições"""
    position_manager = getattr(bot, 'position_manager', None)
    
    if not position_manager:
        return {"count": 0, "list": [], "total_pnl_usd": 0}
    
    positions_list = []
    total_pnl = 0
    
    # Busca preços atuais
    try:
        all_prices = bot.client.get_all_mids()
    except:
        all_prices = {}
    
    for symbol, pos in position_manager.positions.items():
        current_price = float(all_prices.get(symbol, pos.entry_price))
        pnl_pct = pos.get_unrealized_pnl_pct(current_price)
        pnl_usd = (pnl_pct / 100) * (pos.size * pos.entry_price)
        
        positions_list.append({
            "symbol": symbol,
            "side": pos.side,
            "size": pos.size,
            "entry_price": round(pos.entry_price, 6),
            "current_price": round(current_price, 6),
            "pnl_pct": round(pnl_pct, 2),
            "pnl_usd": round(pnl_usd, 2),
            "leverage": pos.leverage,
            "stop_loss_price": round(pos.stop_loss_price, 6) if pos.stop_loss_price else None,
            "take_profit_price": round(pos.take_profit_price, 6) if pos.take_profit_price else None,
            "strategy": pos.strategy,
            "trade_state": pos.trade_state.value if hasattr(pos, 'trade_state') else "unknown",
            "opened_at": pos.opened_at.isoformat() if hasattr(pos, 'opened_at') else None
        })
        
        total_pnl += pnl_usd
    
    return {
        "count": len(positions_list),
        "list": positions_list,
        "total_pnl_usd": round(total_pnl, 2)
    }


def _build_ai_budget_info(bot) -> Dict[str, Any]:
    """Constrói info do AI Budget"""
    ai_budget = getattr(bot, 'ai_budget_manager', None)
    
    if not ai_budget:
        return {
            "claude_calls_today": 0,
            "claude_limit_per_day": 12,
            "openai_calls_today": 0,
            "openai_limit_per_day": 40,
            "budget_ok": True
        }
    
    return {
        "claude_calls_today": getattr(ai_budget, 'claude_calls_today', 0),
        "claude_limit_per_day": getattr(ai_budget, 'claude_daily_limit', 12),
        "openai_calls_today": getattr(ai_budget, 'openai_calls_today', 0),
        "openai_limit_per_day": getattr(ai_budget, 'openai_daily_limit', 40),
        "budget_ok": ai_budget.can_call_claude() if hasattr(ai_budget, 'can_call_claude') else True
    }


def _build_global_ia_info(bot) -> Dict[str, Any]:
    """Constrói info do GLOBAL_IA"""
    last_call = getattr(bot, 'last_global_ia_call', None)
    
    info = {
        "enabled": _get_trading_mode(bot) == "GLOBAL_IA",
        "last_call_time": last_call.isoformat() if last_call else None,
        "last_call_minutes_ago": None,
        "last_analysis": getattr(bot, 'last_global_ia_analysis', None),
        "last_actions_count": getattr(bot, 'last_global_ia_actions_count', 0),
        "last_error": getattr(bot, 'last_global_ia_error', None)
    }
    
    if last_call:
        delta = datetime.now() - last_call
        info["last_call_minutes_ago"] = round(delta.total_seconds() / 60, 1)
    
    return info


def _build_risk_info(bot) -> Dict[str, Any]:
    """Constrói info de risco"""
    risk_manager = getattr(bot, 'risk_manager', None)
    
    if not risk_manager:
        return {}
    
    return {
        "max_positions": getattr(risk_manager, 'max_open_trades', 5),
        "open_positions": getattr(risk_manager, 'current_open_positions', 0),
        "risk_per_trade_pct": getattr(risk_manager, 'risk_per_trade_pct', 2.5),
        "max_daily_drawdown_pct": getattr(risk_manager, 'max_daily_drawdown_pct', 5),
        "circuit_breaker_active": getattr(risk_manager, 'circuit_breaker_active', False),
        "cooldown_symbols": list(getattr(bot, 'cooldown_manager', {}).active_cooldowns.keys()) if hasattr(bot, 'cooldown_manager') and hasattr(bot.cooldown_manager, 'active_cooldowns') else []
    }


def _build_market_info(bot) -> Dict[str, Any]:
    """Constrói info resumida do mercado"""
    last_contexts = getattr(bot, 'last_market_contexts', [])
    
    if not last_contexts:
        return {"symbols_monitored": 0, "snapshot": []}
    
    # Resumo compacto para dashboard
    summary = []
    for ctx in last_contexts[:10]:  # Top 10
        summary.append({
            "symbol": ctx.get("symbol", ""),
            "price": ctx.get("price", 0),
            "trend": ctx.get("trend_1h", ctx.get("trend", "neutral")),
            "momentum": ctx.get("momentum", "flat"),
            "rsi": ctx.get("rsi_14", 50)
        })
    
    return {
        "symbols_monitored": len(last_contexts),
        "snapshot": summary
    }


def _get_uptime(bot) -> Optional[float]:
    """Retorna uptime do bot em segundos"""
    start_time = getattr(bot, 'start_time', None)
    if start_time:
        return (datetime.now(timezone.utc) - start_time).total_seconds()
    return None


# ============================================================
# HELPERS
# ============================================================

def save_snapshot_to_file(snapshot: Dict[str, Any], filepath: str = "data/runtime_snapshot.json"):
    """Salva snapshot em arquivo JSON (para debugging ou consumo externo)"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False, default=str)
        logger.debug(f"[SNAPSHOT] Salvo em {filepath}")
    except Exception as e:
        logger.error(f"[SNAPSHOT] Erro ao salvar: {e}")


def format_snapshot_for_telegram(snapshot: Dict[str, Any]) -> str:
    """Formata snapshot para envio via Telegram (texto resumido)"""
    acc = snapshot.get("account", {})
    pos = snapshot.get("positions", {})
    ai = snapshot.get("global_ia", {})
    budget = snapshot.get("ai_budget", {})
    
    lines = [
        "📊 *Runtime Snapshot*",
        "",
        f"💰 Equity: ${acc.get('equity', 0):.2f}",
        f"📈 Day PnL: {acc.get('day_pnl_pct', 0):+.2f}%",
        "",
        f"📊 Posições: {pos.get('count', 0)}",
        f"💵 PnL Total: ${pos.get('total_pnl_usd', 0):+.2f}",
        "",
        f"🧠 GLOBAL_IA: {'✅ ON' if ai.get('enabled') else '❌ OFF'}",
        f"⏱️ Last call: {ai.get('last_call_minutes_ago', '?')} min ago",
        "",
        f"🎯 Budget Claude: {budget.get('claude_calls_today', 0)}/{budget.get('claude_limit_per_day', 12)}",
        f"🎯 Budget OpenAI: {budget.get('openai_calls_today', 0)}/{budget.get('openai_limit_per_day', 40)}"
    ]
    
    return "\n".join(lines)


# ============================================================
# EXEMPLO DE SNAPSHOT RETORNADO
# ============================================================

"""
{
  "timestamp_utc": "2024-12-13T12:00:00.000000+00:00",
  "version": "1.0.0",
  
  "execution": {
    "mode": "PAPER_ONLY",
    "trading_mode": "GLOBAL_IA",
    "is_paused": false,
    "live_trading": false
  },
  
  "account": {
    "equity": 1250.50,
    "free_margin": 875.35,
    "day_pnl_pct": 1.25,
    "week_pnl_pct": 3.50,
    "daily_drawdown_pct": 0.50
  },
  
  "positions": {
    "count": 2,
    "list": [
      {
        "symbol": "BTC",
        "side": "long",
        "size": 0.005,
        "entry_price": 95000.0,
        "current_price": 97000.0,
        "pnl_pct": 2.1,
        "pnl_usd": 10.0,
        "leverage": 5,
        "stop_loss_price": 93000.0,
        "take_profit_price": 100000.0,
        "strategy": "swing",
        "trade_state": "INIT",
        "opened_at": "2024-12-13T10:00:00+00:00"
      }
    ],
    "total_pnl_usd": 10.0
  },
  
  "ai_budget": {
    "claude_calls_today": 5,
    "claude_limit_per_day": 12,
    "openai_calls_today": 15,
    "openai_limit_per_day": 40,
    "budget_ok": true
  },
  
  "global_ia": {
    "enabled": true,
    "last_call_time": "2024-12-13T11:45:00+00:00",
    "last_call_minutes_ago": 15.0,
    "last_analysis": "Mercado em tendência de alta...",
    "last_actions_count": 1,
    "last_error": null
  },
  
  "risk": {
    "max_positions": 5,
    "open_positions": 2,
    "risk_per_trade_pct": 2.5,
    "max_daily_drawdown_pct": 5,
    "circuit_breaker_active": false,
    "cooldown_symbols": []
  },
  
  "recent_exits": {
    "SOL": {
      "minutes_ago": 25.5,
      "side": "long",
      "pnl_pct": -0.35,
      "exit_price": 131.50
    }
  },
  
  "market": {
    "symbols_monitored": 15,
    "snapshot": [
      {"symbol": "BTC", "price": 97000.0, "trend": "bullish", "momentum": "bullish", "rsi": 62.5},
      {"symbol": "ETH", "price": 3650.0, "trend": "bullish", "momentum": "strong_bullish", "rsi": 68.0}
    ]
  },
  
  "system": {
    "uptime_seconds": 3600.0,
    "trading_pairs_count": 15,
    "last_iteration": null
  }
}
"""
