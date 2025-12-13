"""
DASHBOARD API SERVER
====================

API HTTP para servir dados do bot para o dashboard.

Endpoints:
- GET /api/snapshot - Runtime snapshot completo
- GET /api/health - Health check
- GET /api/positions - Posições abertas
- GET /api/account - Info da conta

Segurança:
- Requer header X-API-KEY com valor de DASHBOARD_API_KEY

Uso:
    from bot.dashboard_api import create_api_server, start_api_server
    
    # No bot
    api_server = create_api_server(bot)
    start_api_server(api_server, port=8080)

Autor: Claude
Data: 2024-12-13
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from threading import Thread

logger = logging.getLogger(__name__)

# Variável global para referência do bot
_bot_instance = None


def set_bot_instance(bot):
    """Define a instância do bot para a API acessar"""
    global _bot_instance
    _bot_instance = bot
    logger.info("[DASHBOARD API] Bot instance registrada")


def get_bot_instance():
    """Retorna a instância do bot"""
    global _bot_instance
    return _bot_instance


# ============================================================
# FASTAPI SERVER
# ============================================================

try:
    from fastapi import FastAPI, HTTPException, Header, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    import uvicorn
    
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.warning("[DASHBOARD API] FastAPI não disponível - pip install fastapi uvicorn")


def create_api_server(bot=None) -> Optional["FastAPI"]:
    """
    Cria servidor FastAPI para dashboard.
    
    Args:
        bot: Instância do HyperliquidBot (opcional, pode ser setado depois)
        
    Returns:
        FastAPI app ou None se FastAPI não disponível
    """
    if not FASTAPI_AVAILABLE:
        logger.error("[DASHBOARD API] FastAPI não instalado")
        return None
    
    if bot:
        set_bot_instance(bot)
    
    app = FastAPI(
        title="IA Trading Bot Dashboard API",
        description="API para monitoramento do bot de trading",
        version="1.0.0"
    )
    
    # CORS para permitir dashboard de outro domínio
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Em produção, especificar domínios
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # ========== AUTH MIDDLEWARE ==========
    
    def verify_api_key(x_api_key: str = Header(None)) -> bool:
        """Verifica API key"""
        expected_key = os.getenv("DASHBOARD_API_KEY", "")
        
        if not expected_key:
            # Se não configurou key, aceita qualquer request (dev mode)
            logger.warning("[DASHBOARD API] DASHBOARD_API_KEY não configurada - modo dev")
            return True
        
        if not x_api_key or x_api_key != expected_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        
        return True
    
    # ========== ENDPOINTS ==========
    
    @app.get("/")
    async def root():
        """Root endpoint"""
        return {
            "name": "IA Trading Bot Dashboard API",
            "version": "1.0.0",
            "status": "online",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    @app.get("/api/health")
    async def health():
        """Health check"""
        bot = get_bot_instance()
        
        return {
            "status": "healthy",
            "bot_connected": bot is not None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    @app.get("/api/snapshot")
    async def get_snapshot(x_api_key: str = Header(None)):
        """
        Retorna runtime snapshot completo do bot.
        
        Requer header: X-API-KEY
        """
        verify_api_key(x_api_key)
        
        bot = get_bot_instance()
        if not bot:
            raise HTTPException(status_code=503, detail="Bot not connected")
        
        try:
            from bot.runtime_snapshot import build_runtime_snapshot
            snapshot = build_runtime_snapshot(bot)
            return JSONResponse(content=snapshot)
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao gerar snapshot: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/positions")
    async def get_positions(x_api_key: str = Header(None)):
        """Retorna posições abertas"""
        verify_api_key(x_api_key)
        
        bot = get_bot_instance()
        if not bot:
            raise HTTPException(status_code=503, detail="Bot not connected")
        
        try:
            position_manager = getattr(bot, 'position_manager', None)
            if not position_manager:
                return {"positions": [], "count": 0}
            
            # Busca preços
            try:
                all_prices = bot.client.get_all_mids()
            except:
                all_prices = {}
            
            positions = []
            for symbol, pos in position_manager.positions.items():
                current_price = float(all_prices.get(symbol, pos.entry_price))
                pnl_pct = pos.get_unrealized_pnl_pct(current_price)
                
                positions.append({
                    "symbol": symbol,
                    "side": pos.side,
                    "size": pos.size,
                    "entry_price": pos.entry_price,
                    "current_price": current_price,
                    "pnl_pct": round(pnl_pct, 2),
                    "leverage": pos.leverage,
                    "stop_loss": pos.stop_loss_price,
                    "take_profit": pos.take_profit_price
                })
            
            return {"positions": positions, "count": len(positions)}
            
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar positions: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/account")
    async def get_account(x_api_key: str = Header(None)):
        """Retorna info da conta"""
        verify_api_key(x_api_key)
        
        bot = get_bot_instance()
        if not bot:
            raise HTTPException(status_code=503, detail="Bot not connected")
        
        try:
            risk_manager = getattr(bot, 'risk_manager', None)
            
            return {
                "equity": round(getattr(risk_manager, 'current_equity', 0), 2) if risk_manager else 0,
                "free_margin": round(getattr(risk_manager, 'free_margin', 0), 2) if risk_manager else 0,
                "day_pnl_pct": round(getattr(risk_manager, 'daily_pnl_pct', 0), 2) if risk_manager else 0,
                "week_pnl_pct": round(getattr(risk_manager, 'weekly_pnl_pct', 0), 2) if risk_manager else 0
            }
            
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar account: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/ai-status")
    async def get_ai_status(x_api_key: str = Header(None)):
        """Retorna status do GLOBAL_IA"""
        verify_api_key(x_api_key)
        
        bot = get_bot_instance()
        if not bot:
            raise HTTPException(status_code=503, detail="Bot not connected")
        
        try:
            from bot.phase5 import TradingMode
            
            mode_manager = getattr(bot, 'mode_manager', None)
            current_mode = mode_manager.current_mode.value if mode_manager else "UNKNOWN"
            is_global = current_mode == "GLOBAL_IA"
            
            last_call = getattr(bot, 'last_global_ia_call', None)
            last_call_minutes = None
            if last_call:
                delta = datetime.now() - last_call
                last_call_minutes = round(delta.total_seconds() / 60, 1)
            
            # AI Budget
            ai_budget = getattr(bot, 'ai_budget_manager', None)
            budget_info = {}
            if ai_budget:
                budget_info = {
                    "claude_calls": getattr(ai_budget, 'claude_calls_today', 0),
                    "claude_limit": getattr(ai_budget, 'claude_daily_limit', 12),
                    "openai_calls": getattr(ai_budget, 'openai_calls_today', 0),
                    "openai_limit": getattr(ai_budget, 'openai_daily_limit', 40)
                }
            
            has_positions = len(getattr(bot.position_manager, 'positions', {})) > 0
            
            # Calcula próxima chamada
            next_call_eta = None
            if is_global and last_call:
                interval = 15 if has_positions else 30
                elapsed = last_call_minutes or 0
                remaining = interval - elapsed
                next_call_eta = max(0, remaining)
            
            return {
                "mode": current_mode,
                "global_ia_enabled": is_global,
                "last_call_time": last_call.isoformat() if last_call else None,
                "last_call_minutes_ago": last_call_minutes,
                "next_call_eta_minutes": next_call_eta,
                "has_positions": has_positions,
                "ai_budget": budget_info
            }
            
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar ai-status: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # ========== ENDPOINTS DE TELEMETRIA (SÉRIES E MÉTRICAS) ==========
    
    @app.get("/api/metrics/series")
    async def get_metrics_series(
        x_api_key: str = Header(None),
        range: str = "24h"
    ):
        """
        Retorna série temporal para gráficos.
        
        Query params:
            range: 1h, 24h, 7d, 30d
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.telemetry_store import get_telemetry_store
            store = get_telemetry_store()
            
            # Converte range para horas
            range_map = {
                "1h": 1,
                "24h": 24,
                "7d": 168,
                "30d": 720
            }
            range_hours = range_map.get(range, 24)
            
            series = store.get_snapshots_series(range_hours=range_hours)
            
            return {
                "range": range,
                "range_hours": range_hours,
                "points": len(series),
                "data": series
            }
            
        except ImportError:
            return {"error": "Telemetry not available", "data": []}
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar série: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/trades")
    async def get_trades_journal(
        x_api_key: str = Header(None),
        limit: int = 200,
        symbol: str = None,
        range: str = "24h"
    ):
        """
        Retorna journal de trades.
        
        Query params:
            limit: max registros (default 200)
            symbol: filtro por símbolo
            range: 1h, 24h, 7d, 30d
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.telemetry_store import get_telemetry_store
            store = get_telemetry_store()
            
            range_map = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}
            range_hours = range_map.get(range, 24)
            
            trades = store.get_trades(
                limit=limit,
                symbol=symbol,
                range_hours=range_hours
            )
            
            return {
                "range": range,
                "symbol": symbol,
                "count": len(trades),
                "trades": trades
            }
            
        except ImportError:
            return {"error": "Telemetry not available", "trades": []}
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar trades: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/metrics/stats")
    async def get_metrics_stats(
        x_api_key: str = Header(None),
        range: str = "24h"
    ):
        """
        Retorna métricas agregadas (win rate, profit factor, etc).
        
        Query params:
            range: 24h, 7d, 30d
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.telemetry_store import get_telemetry_store
            store = get_telemetry_store()
            
            range_map = {"24h": 24, "7d": 168, "30d": 720}
            range_hours = range_map.get(range, 24)
            
            metrics = store.get_metrics(range_hours=range_hours)
            
            return {
                "range": range,
                "range_hours": range_hours,
                "metrics": metrics
            }
            
        except ImportError:
            return {"error": "Telemetry not available", "metrics": {}}
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar métricas: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/health/details")
    async def get_health_details(x_api_key: str = Header(None)):
        """
        Retorna detalhes de saúde do sistema.
        """
        verify_api_key(x_api_key)
        
        bot = get_bot_instance()
        
        try:
            # Verifica telemetria
            telemetry_ok = False
            try:
                from bot.telemetry_store import get_telemetry_store
                store = get_telemetry_store()
                telemetry_ok = store.enabled
            except:
                pass
            
            # Última atualização de preços
            last_price_update = None
            if bot:
                try:
                    last_price_update = getattr(bot, 'last_price_update', None)
                    if last_price_update:
                        last_price_update = last_price_update.isoformat()
                except:
                    pass
            
            # Último erro
            last_error = None
            if bot:
                last_error = getattr(bot, 'last_error', None)
            
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "bot_connected": bot is not None,
                "telemetry_enabled": telemetry_ok,
                "last_price_update": last_price_update,
                "last_error": last_error,
                "global_ia_last_call": getattr(bot, 'last_global_ia_call', None).isoformat() if bot and getattr(bot, 'last_global_ia_call', None) else None
            }
            
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar health: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # ========== ENDPOINTS PREMIUM (PNL CAMPEÃO) ==========
    
    @app.get("/api/pnl/summary")
    async def get_pnl_summary(x_api_key: str = Header(None)):
        """
        Retorna resumo de PnL para todos os períodos.
        
        Returns:
        - pnl_all_time_pct, pnl_all_time_usd
        - pnl_day_pct, pnl_day_usd
        - pnl_week_pct, pnl_week_usd
        - pnl_month_pct, pnl_month_usd
        - max_drawdown_pct
        - winrate, profit_factor
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.telemetry_store import get_telemetry_store
            store = get_telemetry_store()
            
            # Busca equity atual
            bot = get_bot_instance()
            current_equity = None
            if bot:
                risk_manager = getattr(bot, 'risk_manager', None)
                if risk_manager:
                    current_equity = getattr(risk_manager, 'current_equity', None)
            
            # PnL Summary
            pnl = store.get_pnl_summary(current_equity)
            
            # Métricas de performance (all time)
            metrics = store.get_performance_metrics(range_hours=-1)
            
            return {
                **pnl,
                "winrate": metrics.get('winrate', 0),
                "profit_factor": metrics.get('profit_factor', 0),
                "max_drawdown_pct": metrics.get('max_drawdown_pct', 0),
                "total_trades": metrics.get('trades_count', 0),
                "trades_today": metrics.get('trades_today', 0),
                "trades_week": metrics.get('trades_week', 0),
                "trades_month": metrics.get('trades_month', 0)
            }
            
        except ImportError:
            return {"error": "Telemetry not available"}
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar PnL summary: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/pnl/series")
    async def get_pnl_series(
        x_api_key: str = Header(None),
        range: str = "7d"
    ):
        """
        Retorna série de equity para gráfico ALL TIME.
        
        Query params:
            range: 1d, 7d, 30d, all
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.telemetry_store import get_telemetry_store
            store = get_telemetry_store()
            
            range_map = {
                "1d": 24,
                "7d": 168,
                "30d": 720,
                "all": -1
            }
            range_hours = range_map.get(range, 168)
            
            series = store.get_equity_series(range_hours=range_hours)
            
            return {
                "range": range,
                "points": len(series),
                "data": series
            }
            
        except ImportError:
            return {"error": "Telemetry not available", "data": []}
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar PnL series: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/fills")
    async def get_fills(
        x_api_key: str = Header(None),
        range: str = "7d",
        symbol: str = None,
        side: str = None,
        result: str = None,
        limit: int = 200,
        cursor: int = None,
        offset: int = None
    ):
        """
        Retorna histórico de fills/trades com paginação.
        
        Query params:
            range: 7d, 30d, all
            symbol: filtro por símbolo
            side: filtro por lado (buy/sell ou long/short)
            result: win, loss, all
            limit: máximo de registros por página (default 200)
            cursor: ID do último fill da página anterior (para paginação)
            offset: offset alternativo (menos eficiente que cursor)
        
        Returns:
            {
                "range": "7d",
                "filters": {...},
                "count": 200,
                "fills": [...],
                "nextCursor": 12345,
                "hasMore": true,
                "total": 450
            }
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.telemetry_store import get_telemetry_store
            store = get_telemetry_store()
            
            range_map = {"7d": 168, "30d": 720, "all": -1}
            range_hours = range_map.get(range, 168)
            
            only_profitable = None
            if result == "win":
                only_profitable = True
            elif result == "loss":
                only_profitable = False
            
            # Use new paginated method
            paginated_result = store.get_fills_paginated(
                range_hours=range_hours,
                symbol=symbol,
                side=side,
                only_profitable=only_profitable,
                limit=limit,
                cursor=cursor,
                offset=offset
            )
            
            return {
                "range": range,
                "filters": {"symbol": symbol, "side": side, "result": result},
                "count": len(paginated_result['items']),
                "fills": paginated_result['items'],
                "nextCursor": paginated_result.get('nextCursor'),
                "hasMore": paginated_result.get('hasMore', False),
                "total": paginated_result.get('total', 0)
            }
            
        except ImportError:
            return {"error": "Telemetry not available", "fills": [], "hasMore": False, "total": 0}
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar fills: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    
    @app.get("/api/metrics")
    async def get_full_metrics(
        x_api_key: str = Header(None),
        range: str = "all"
    ):
        """
        Retorna métricas completas de performance.
        
        Returns:
        - winrate, profit_factor, avg_win, avg_loss
        - expectancy, max_drawdown
        - trades_count, trades_today, trades_week, trades_month
        - total_profit, total_loss, total_pnl, total_fees
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.telemetry_store import get_telemetry_store
            store = get_telemetry_store()
            
            range_map = {"24h": 24, "7d": 168, "30d": 720, "all": -1}
            range_hours = range_map.get(range, -1)
            
            metrics = store.get_performance_metrics(range_hours=range_hours)
            
            return {
                "range": range,
                "metrics": metrics
            }
            
        except ImportError:
            return {"error": "Telemetry not available", "metrics": {}}
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar métricas: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/backfill")
    async def trigger_backfill(x_api_key: str = Header(None)):
        """
        Dispara backfill de fills da exchange.
        
        Requer autenticação admin.
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.telemetry_store import get_telemetry_store
            store = get_telemetry_store()
            
            bot = get_bot_instance()
            if not bot or not hasattr(bot, 'client'):
                return {"error": "Bot not connected", "fills_imported": 0}
            
            count = store.backfill_from_exchange(bot.client, days=30)
            
            return {
                "status": "ok",
                "fills_imported": count
            }
            
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro no backfill: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # ========== ENDPOINTS DE THOUGHT FEED ==========
    
    @app.get("/api/thoughts")
    async def get_thoughts(
        x_api_key: str = Header(None),
        limit: int = 50,
        type: str = None,
        symbol: str = None
    ):
        """
        Retorna pensamentos/insights da IA.
        
        Query params:
            limit: Máximo de pensamentos (default 50)
            type: Filtro por tipo (analysis, decision, risk, execution, etc)
            symbol: Filtro por símbolo
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.thought_feed import get_thought_feed
            feed = get_thought_feed()
            
            thoughts = feed.get_thoughts(
                limit=limit,
                type_filter=type,
                symbol_filter=symbol
            )
            
            return {
                "count": len(thoughts),
                "thoughts": thoughts
            }
            
        except ImportError:
            return {"error": "Thought feed not available", "thoughts": []}
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar thoughts: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/ai-chat")
    async def ai_chat(
        request: Request,
        x_api_key: str = Header(None)
    ):
        """
        Chat com a IA Trader.
        
        Body: { "message": "sua pergunta" }
        
        Returns:
            { "reply": "resposta da IA", "context": {...}, "used_ai": bool }
        """
        verify_api_key(x_api_key)
        
        try:
            body = await request.json()
            user_message = body.get('message', '')
            
            if not user_message:
                return {"error": "Message is required", "reply": ""}
            
            from bot.thought_feed import get_chat_responder
            bot = get_bot_instance()
            responder = get_chat_responder(bot)
            
            response = responder.respond(user_message)
            
            return response
            
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro no ai-chat: {e}")
            return {
                "reply": "Desculpe, ocorreu um erro. Tente novamente.",
                "error": str(e),
                "used_ai": False
            }
    
    @app.get("/api/performance")
    async def get_performance(x_api_key: str = Header(None)):
        """
        Retorna performance por janelas de tempo.
        
        Returns:
            {
                "all": {"pnl_usd": X, "pnl_pct": Y},
                "24h": {...},
                "7d": {...},
                "30d": {...},
                "90d": {...},
                "180d": {...},
                "365d": {...}
            }
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.telemetry_store import get_telemetry_store
            store = get_telemetry_store()
            
            # Busca equity atual
            bot = get_bot_instance()
            current_equity = None
            if bot:
                risk_manager = getattr(bot, 'risk_manager', None)
                if risk_manager:
                    current_equity = getattr(risk_manager, 'current_equity', None)
            
            # Busca PnL summary (all time + day + week + month)
            pnl_summary = store.get_pnl_summary(current_equity)
            
            # Mapeia para formato de windows
            result = {
                "current_equity": current_equity or pnl_summary.get('current_equity', 0),
                "all": {
                    "pnl_usd": pnl_summary.get('pnl_all_time_usd', 0),
                    "pnl_pct": pnl_summary.get('pnl_all_time_pct', 0),
                    "start_equity": pnl_summary.get('all_time_start_equity'),
                    "start_date": pnl_summary.get('all_time_start_date')
                },
                "24h": {
                    "pnl_usd": pnl_summary.get('pnl_day_usd', 0),
                    "pnl_pct": pnl_summary.get('pnl_day_pct', 0)
                },
                "7d": {
                    "pnl_usd": pnl_summary.get('pnl_week_usd', 0),
                    "pnl_pct": pnl_summary.get('pnl_week_pct', 0)
                },
                "30d": {
                    "pnl_usd": pnl_summary.get('pnl_month_usd', 0),
                    "pnl_pct": pnl_summary.get('pnl_month_pct', 0)
                },
                # 90d, 180d, 365d - para agora, usamos all time como proxy
                # TODO: Implementar baselines adicionais se necessário
                "90d": {
                    "pnl_usd": pnl_summary.get('pnl_all_time_usd', 0),
                    "pnl_pct": pnl_summary.get('pnl_all_time_pct', 0)
                },
                "180d": {
                    "pnl_usd": pnl_summary.get('pnl_all_time_usd', 0),
                    "pnl_pct": pnl_summary.get('pnl_all_time_pct', 0)
                },
                "365d": {
                    "pnl_usd": pnl_summary.get('pnl_all_time_usd', 0),
                    "pnl_pct": pnl_summary.get('pnl_all_time_pct', 0)
                }
            }
            
            return result
            
        except ImportError:
            return {"error": "Telemetry not available"}
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao buscar performance: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/set-initial-equity")
    async def set_initial_equity(
        request: Request,
        x_api_key: str = Header(None)
    ):
        """
        Define o equity inicial para cálculo de PnL ALL TIME.
        
        Útil quando o bot começou depois da conta já existir.
        
        Body: { "initial_equity": 10.0, "start_date": "2024-11-01" }
        """
        verify_api_key(x_api_key)
        
        try:
            body = await request.json()
            initial_equity = body.get('initial_equity')
            start_date = body.get('start_date')  # ISO format: "2024-11-01"
            
            if not initial_equity:
                return {"error": "initial_equity is required"}
            
            from bot.telemetry_store import get_telemetry_store
            store = get_telemetry_store()
            
            result = store.set_initial_equity(
                initial_equity=float(initial_equity),
                start_date=start_date
            )
            
            return {
                "status": "ok" if result else "error",
                "initial_equity": initial_equity,
                "start_date": start_date
            }
            
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao setar initial equity: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/init-thoughts-table")
    async def init_thoughts_table(x_api_key: str = Header(None)):
        """
        Inicializa a tabela de thoughts no PostgreSQL.
        Chamada uma vez após deploy para criar a estrutura.
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.thought_feed import get_thought_feed, ThoughtFeed, SQLALCHEMY_AVAILABLE
            
            if not SQLALCHEMY_AVAILABLE:
                return {"error": "SQLAlchemy not available"}
            
            feed = get_thought_feed()
            
            if feed._db_enabled:
                return {
                    "status": "ok",
                    "message": "Tabela ai_thoughts já existe e está conectada",
                    "db_enabled": True
                }
            else:
                # Força reinicialização
                feed._init_database()
                return {
                    "status": "ok" if feed._db_enabled else "error",
                    "message": "Tabela criada" if feed._db_enabled else "Falha ao criar tabela",
                    "db_enabled": feed._db_enabled
                }
                
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao criar tabela: {e}")
            return {"error": str(e)}
    
    @app.post("/api/test-thought")
    async def test_thought(x_api_key: str = Header(None)):
        """
        Cria um thought de teste para verificar se está funcionando.
        """
        verify_api_key(x_api_key)
        
        try:
            from bot.thought_feed import get_thought_feed
            feed = get_thought_feed()
            
            thought = feed.add_thought(
                type='analysis',
                summary='Teste de integração - Sistema de thoughts inicializado com sucesso!',
                symbols=['BTC', 'ETH'],
                actions=['test'],
                confidence=1.0
            )
            
            return {
                "status": "ok",
                "thought": thought.to_dict(),
                "db_enabled": feed._db_enabled
            }
            
        except Exception as e:
            logger.error(f"[DASHBOARD API] Erro ao criar thought de teste: {e}")
            return {"error": str(e)}
    
    logger.info("[DASHBOARD API] FastAPI server criado (PREMIUM EDITION + THOUGHTS + CHAT)")
    return app


def start_api_server(app, host: str = "0.0.0.0", port: int = 8080):
    """
    Inicia servidor API em thread separada.
    
    Args:
        app: FastAPI app
        host: Host para bind
        port: Porta
    """
    if not app:
        logger.error("[DASHBOARD API] App não fornecido")
        return
    
    def run():
        uvicorn.run(app, host=host, port=port, log_level="warning")
    
    thread = Thread(target=run, daemon=True)
    thread.start()
    logger.info(f"[DASHBOARD API] Server iniciado em http://{host}:{port}")


def start_api_server_async(app, host: str = "0.0.0.0", port: int = 8080):
    """
    Inicia servidor API de forma assíncrona.
    
    Para uso com asyncio event loop existente.
    """
    if not app:
        return
    
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    
    asyncio.create_task(server.serve())
    logger.info(f"[DASHBOARD API] Server async iniciado em http://{host}:{port}")


# ============================================================
# INTEGRAÇÃO COM BOT
# ============================================================

def integrate_with_bot(bot, port: int = None):
    """
    Integra API com o bot de forma simples.
    
    Args:
        bot: Instância do HyperliquidBot
        port: Porta para API (default: env PORT ou 8080)
    """
    if not FASTAPI_AVAILABLE:
        logger.warning("[DASHBOARD API] FastAPI não disponível, pulando integração")
        return None
    
    # Determina porta
    if port is None:
        port = int(os.getenv("API_PORT", os.getenv("PORT", 8080)))
    
    # Cria e inicia servidor
    app = create_api_server(bot)
    if app:
        start_api_server(app, port=port)
        return app
    
    return None
