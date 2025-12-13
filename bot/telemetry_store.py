"""
TELEMETRY STORE - DATA ENGINE PREMIUM
=====================================

Sistema de persistência completo para o bot de trading.
Armazena histórico de equity, trades, métricas e baselines.

Tabelas:
- equity_snapshots: Time-series de equity (gráfico all-time)
- fills: Histórico de trades/fills da exchange
- performance_baselines: Baselines para PnL dia/semana/mês/all-time
- errors: Log de erros para observabilidade

Uso:
    from bot.telemetry_store import get_telemetry_store
    
    store = get_telemetry_store()
    store.record_equity_snapshot(equity, unrealized, positions_count)
    store.record_fill(fill_data)
    store.get_pnl_summary()
    store.get_equity_series(range_hours=168)

Autor: Claude
Data: 2024-12-13
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ============================================================
# SQLAlchemy Setup
# ============================================================

try:
    from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, JSON, Index
    from sqlalchemy import func, desc, asc
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import QueuePool
    from sqlalchemy.dialects.postgresql import insert
    
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    logger.warning("[TELEMETRY] SQLAlchemy não disponível - pip install sqlalchemy psycopg2-binary")

Base = declarative_base() if SQLALCHEMY_AVAILABLE else None


# ============================================================
# MODELS
# ============================================================

if SQLALCHEMY_AVAILABLE:
    
    class EquitySnapshot(Base):
        """Time-series de equity para gráfico all-time"""
        __tablename__ = 'equity_snapshots'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        ts_utc = Column(DateTime(timezone=True), nullable=False, index=True)
        
        equity_usd = Column(Float, nullable=False)
        unrealized_usd = Column(Float, default=0)
        realized_day_usd = Column(Float, default=0)
        positions_count = Column(Integer, default=0)
        
        execution_mode = Column(String(50))
        ai_mode = Column(String(50))
        
        # Multi-tenant
        user_id = Column(String(100), default='default', index=True)
        account_id = Column(String(100), default='default')
        
        __table_args__ = (
            Index('ix_equity_ts_user', 'ts_utc', 'user_id'),
        )
    
    
    class Fill(Base):
        """Histórico de trades/fills da exchange"""
        __tablename__ = 'fills'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        trade_id = Column(String(100), unique=True, index=True)  # ID único da exchange
        
        ts_utc = Column(DateTime(timezone=True), nullable=False, index=True)
        symbol = Column(String(20), nullable=False, index=True)
        side = Column(String(10), nullable=False)  # buy/sell ou long/short
        
        qty = Column(Float, nullable=False)
        price = Column(Float, nullable=False)
        fee = Column(Float, default=0)
        realized_pnl = Column(Float, default=0)
        
        order_id = Column(String(100))
        order_type = Column(String(20))  # market/limit
        is_close = Column(Boolean, default=False)  # True se fechou posição
        
        # Contexto
        leverage = Column(Integer)
        execution_mode = Column(String(50))
        ai_reason = Column(Text)
        
        # Multi-tenant
        user_id = Column(String(100), default='default', index=True)
        account_id = Column(String(100), default='default')
        
        __table_args__ = (
            Index('ix_fills_ts_symbol', 'ts_utc', 'symbol'),
            Index('ix_fills_user_ts', 'user_id', 'ts_utc'),
        )
    
    
    class PerformanceBaseline(Base):
        """Baselines para cálculo de PnL por período"""
        __tablename__ = 'performance_baselines'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        
        period_key = Column(String(20), nullable=False, index=True)  # day/week/month/all_time
        start_ts = Column(DateTime(timezone=True), nullable=False)
        start_equity = Column(Float, nullable=False)
        
        # Multi-tenant
        user_id = Column(String(100), default='default', index=True)
        account_id = Column(String(100), default='default')
        
        __table_args__ = (
            Index('ix_baseline_user_period', 'user_id', 'period_key'),
        )
    
    
    class ErrorRecord(Base):
        """Log de erros para observabilidade"""
        __tablename__ = 'errors'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        ts_utc = Column(DateTime(timezone=True), nullable=False, index=True)
        
        scope = Column(String(50))
        symbol = Column(String(20))
        message = Column(Text)
        stacktrace = Column(Text)
        meta_json = Column(JSON)
        
        user_id = Column(String(100), default='default')
        account_id = Column(String(100), default='default')


# ============================================================
# TELEMETRY STORE CLASS
# ============================================================

class TelemetryStore:
    """
    Data Engine Premium para persistência de telemetria.
    
    Features:
    - Equity curve all-time
    - Histórico de fills/trades
    - Baselines para PnL dia/semana/mês
    - Métricas de performance
    """
    
    def __init__(self, database_url: str = None):
        self.enabled = False
        self.engine = None
        self.Session = None
        self._last_sync_ts = None
        
        if not SQLALCHEMY_AVAILABLE:
            logger.warning("[TELEMETRY] SQLAlchemy não disponível - telemetria desabilitada")
            return
        
        database_url = database_url or os.getenv("DATABASE_URL")
        
        if not database_url:
            logger.warning("[TELEMETRY] DATABASE_URL não configurada - telemetria desabilitada")
            return
        
        try:
            # Cria engine com pool de conexões
            self.engine = create_engine(
                database_url,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=1800,
                echo=False
            )
            
            # Cria tabelas se não existirem
            Base.metadata.create_all(self.engine)
            
            # Session factory
            self.Session = sessionmaker(bind=self.engine)
            
            self.enabled = True
            logger.info("[TELEMETRY] ✅ Data Engine inicializado com sucesso")
            
            # Inicializa baselines se necessário
            self._init_baselines()
            
        except Exception as e:
            logger.error(f"[TELEMETRY] ❌ Erro ao conectar: {e}")
            self.enabled = False
    
    @contextmanager
    def get_session(self):
        """Context manager para sessões"""
        if not self.enabled or not self.Session:
            yield None
            return
        
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"[TELEMETRY] Erro na sessão: {e}")
            raise
        finally:
            session.close()
    
    # ============================================================
    # BASELINES
    # ============================================================
    
    def _init_baselines(self):
        """Inicializa baselines se não existirem"""
        try:
            with self.get_session() as session:
                if session is None:
                    return
                
                # Verifica se all_time existe
                existing = session.query(PerformanceBaseline).filter_by(
                    period_key='all_time',
                    user_id='default'
                ).first()
                
                if not existing:
                    logger.info("[TELEMETRY] Baselines serão criados no primeiro snapshot")
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao verificar baselines: {e}")
    
    def _update_baselines(self, equity: float, session):
        """Atualiza baselines conforme necessário"""
        now = datetime.now(timezone.utc)
        
        try:
            # ALL_TIME - criar se não existe
            all_time = session.query(PerformanceBaseline).filter_by(
                period_key='all_time', user_id='default'
            ).first()
            
            if not all_time:
                all_time = PerformanceBaseline(
                    period_key='all_time',
                    start_ts=now,
                    start_equity=equity
                )
                session.add(all_time)
                logger.info(f"[TELEMETRY] 📊 Baseline ALL_TIME criado: ${equity:.2f}")
            
            # DAY - reset se mudou o dia
            day_baseline = session.query(PerformanceBaseline).filter_by(
                period_key='day', user_id='default'
            ).first()
            
            if not day_baseline or day_baseline.start_ts.date() < now.date():
                if day_baseline:
                    day_baseline.start_ts = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    day_baseline.start_equity = equity
                else:
                    session.add(PerformanceBaseline(
                        period_key='day',
                        start_ts=now.replace(hour=0, minute=0, second=0, microsecond=0),
                        start_equity=equity
                    ))
            
            # WEEK - reset se mudou a semana (segunda-feira)
            week_baseline = session.query(PerformanceBaseline).filter_by(
                period_key='week', user_id='default'
            ).first()
            
            week_start = now - timedelta(days=now.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            
            if not week_baseline or week_baseline.start_ts < week_start:
                if week_baseline:
                    week_baseline.start_ts = week_start
                    week_baseline.start_equity = equity
                else:
                    session.add(PerformanceBaseline(
                        period_key='week',
                        start_ts=week_start,
                        start_equity=equity
                    ))
            
            # MONTH - reset se mudou o mês
            month_baseline = session.query(PerformanceBaseline).filter_by(
                period_key='month', user_id='default'
            ).first()
            
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            if not month_baseline or month_baseline.start_ts < month_start:
                if month_baseline:
                    month_baseline.start_ts = month_start
                    month_baseline.start_equity = equity
                else:
                    session.add(PerformanceBaseline(
                        period_key='month',
                        start_ts=month_start,
                        start_equity=equity
                    ))
                    
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao atualizar baselines: {e}")
    
    def set_initial_equity(self, initial_equity: float, start_date: str = None) -> bool:
        """
        Define o equity inicial para cálculo de PnL ALL TIME.
        
        Útil quando o bot começou depois da conta já existir na exchange.
        
        Args:
            initial_equity: Equity inicial em USD
            start_date: Data de início (ISO format: "2024-11-01")
            
        Returns:
            True se sucesso
        """
        if not self.enabled:
            return False
        
        try:
            from datetime import datetime
            
            # Parse start_date se fornecido
            if start_date:
                start_ts = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if start_ts.tzinfo is None:
                    start_ts = start_ts.replace(tzinfo=timezone.utc)
            else:
                start_ts = datetime.now(timezone.utc)
            
            with self.get_session() as session:
                if session is None:
                    return False
                
                # Busca ou cria baseline ALL_TIME
                all_time = session.query(PerformanceBaseline).filter_by(
                    period_key='all_time', user_id='default'
                ).first()
                
                if all_time:
                    old_equity = all_time.start_equity
                    all_time.start_equity = initial_equity
                    all_time.start_ts = start_ts
                    logger.info(
                        f"[TELEMETRY] 📊 Baseline ALL_TIME ATUALIZADO: "
                        f"${old_equity:.2f} → ${initial_equity:.2f} (desde {start_date})"
                    )
                else:
                    session.add(PerformanceBaseline(
                        period_key='all_time',
                        start_ts=start_ts,
                        start_equity=initial_equity
                    ))
                    logger.info(
                        f"[TELEMETRY] 📊 Baseline ALL_TIME CRIADO: "
                        f"${initial_equity:.2f} (desde {start_date})"
                    )
                
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao setar initial equity: {e}")
            return False
    
    # ============================================================
    # EQUITY SNAPSHOTS
    # ============================================================
    
    def record_equity_snapshot(self, 
                               equity: float, 
                               unrealized: float = 0,
                               positions_count: int = 0,
                               execution_mode: str = None,
                               ai_mode: str = None) -> bool:
        """
        Registra snapshot de equity.
        
        Chamado a cada 30-60s pelo bot.
        """
        if not self.enabled:
            return False
        
        try:
            with self.get_session() as session:
                if session is None:
                    return False
                
                now = datetime.now(timezone.utc)
                
                # Evita duplicatas muito próximas (30s)
                last = session.query(EquitySnapshot).order_by(
                    desc(EquitySnapshot.ts_utc)
                ).first()
                
                if last and (now - last.ts_utc).total_seconds() < 25:
                    return True  # Skip, muito recente
                
                # Atualiza baselines
                self._update_baselines(equity, session)
                
                # Insere snapshot
                snapshot = EquitySnapshot(
                    ts_utc=now,
                    equity_usd=equity,
                    unrealized_usd=unrealized,
                    positions_count=positions_count,
                    execution_mode=execution_mode,
                    ai_mode=ai_mode
                )
                session.add(snapshot)
                
                logger.debug(f"[TELEMETRY] Equity snapshot: ${equity:.2f}")
                return True
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao gravar equity snapshot: {e}")
            return False
    
    def get_equity_series(self, range_hours: int = 24, limit: int = 2000) -> List[Dict]:
        """Retorna série de equity para gráfico"""
        if not self.enabled:
            return []
        
        try:
            with self.get_session() as session:
                if session is None:
                    return []
                
                if range_hours == -1:  # ALL TIME
                    cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
                else:
                    cutoff = datetime.now(timezone.utc) - timedelta(hours=range_hours)
                
                records = session.query(EquitySnapshot)\
                    .filter(EquitySnapshot.ts_utc >= cutoff)\
                    .order_by(asc(EquitySnapshot.ts_utc))\
                    .limit(limit)\
                    .all()
                
                return [
                    {
                        'ts': r.ts_utc.isoformat(),
                        'equity_usd': r.equity_usd,
                        'unrealized_usd': r.unrealized_usd,
                        'positions_count': r.positions_count
                    }
                    for r in records
                ]
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao buscar série equity: {e}")
            return []
    
    # ============================================================
    # FILLS / TRADES
    # ============================================================
    
    def record_fill(self, fill_data: Dict[str, Any]) -> bool:
        """
        Registra fill/trade da exchange.
        
        fill_data deve conter:
        - trade_id (unique)
        - ts_utc ou timestamp
        - symbol
        - side
        - qty
        - price
        - fee (opcional)
        - realized_pnl (opcional)
        """
        if not self.enabled:
            return False
        
        try:
            with self.get_session() as session:
                if session is None:
                    return False
                
                trade_id = fill_data.get('trade_id') or fill_data.get('tid') or \
                          f"{fill_data.get('symbol')}_{fill_data.get('ts_utc', datetime.now().isoformat())}"
                
                # Verifica se já existe
                existing = session.query(Fill).filter_by(trade_id=str(trade_id)).first()
                if existing:
                    return True  # Já existe, skip
                
                # Parse timestamp
                ts = fill_data.get('ts_utc') or fill_data.get('timestamp')
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                elif isinstance(ts, (int, float)):
                    ts = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)
                else:
                    ts = datetime.now(timezone.utc)
                
                fill = Fill(
                    trade_id=str(trade_id),
                    ts_utc=ts,
                    symbol=fill_data.get('symbol', ''),
                    side=fill_data.get('side', ''),
                    qty=float(fill_data.get('qty', 0) or fill_data.get('sz', 0)),
                    price=float(fill_data.get('price', 0) or fill_data.get('px', 0)),
                    fee=float(fill_data.get('fee', 0)),
                    realized_pnl=float(fill_data.get('realized_pnl', 0) or fill_data.get('closedPnl', 0)),
                    order_id=fill_data.get('order_id') or fill_data.get('oid'),
                    order_type=fill_data.get('order_type'),
                    is_close=fill_data.get('is_close', False),
                    leverage=fill_data.get('leverage'),
                    execution_mode=fill_data.get('execution_mode'),
                    ai_reason=fill_data.get('ai_reason')
                )
                session.add(fill)
                
                logger.debug(f"[TELEMETRY] Fill recorded: {fill_data.get('symbol')} {fill_data.get('side')}")
                return True
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao gravar fill: {e}")
            return False
    
    def record_fills_batch(self, fills: List[Dict]) -> int:
        """Registra múltiplos fills de uma vez (para backfill)"""
        if not self.enabled:
            return 0
        
        count = 0
        for fill in fills:
            if self.record_fill(fill):
                count += 1
        
        logger.info(f"[TELEMETRY] Batch recorded: {count}/{len(fills)} fills")
        return count
    
    def get_fills(self, 
                  range_hours: int = 168, 
                  symbol: str = None,
                  side: str = None,
                  only_profitable: bool = None,
                  limit: int = 500) -> List[Dict]:
        """Retorna histórico de fills"""
        if not self.enabled:
            return []
        
        try:
            with self.get_session() as session:
                if session is None:
                    return []
                
                if range_hours == -1:
                    cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
                else:
                    cutoff = datetime.now(timezone.utc) - timedelta(hours=range_hours)
                
                query = session.query(Fill).filter(Fill.ts_utc >= cutoff)
                
                if symbol:
                    query = query.filter(Fill.symbol == symbol)
                if side:
                    query = query.filter(Fill.side == side)
                if only_profitable is True:
                    query = query.filter(Fill.realized_pnl > 0)
                elif only_profitable is False:
                    query = query.filter(Fill.realized_pnl < 0)
                
                records = query.order_by(desc(Fill.ts_utc)).limit(limit).all()
                
                return [
                    {
                        'id': r.id,
                        'trade_id': r.trade_id,
                        'ts': r.ts_utc.isoformat(),
                        'symbol': r.symbol,
                        'side': r.side,
                        'qty': r.qty,
                        'price': r.price,
                        'fee': r.fee,
                        'realized_pnl': r.realized_pnl,
                        'is_close': r.is_close,
                        'ai_reason': r.ai_reason
                    }
                    for r in records
                ]
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao buscar fills: {e}")
            return []
    
    def get_fills_paginated(self, 
                            range_hours: int = 168, 
                            symbol: str = None,
                            side: str = None,
                            only_profitable: bool = None,
                            limit: int = 200,
                            cursor: int = None,
                            offset: int = None) -> Dict[str, Any]:
        """
        Retorna histórico de fills com paginação cursor-based.
        
        Args:
            range_hours: Janela de tempo (-1 para ALL)
            symbol: Filtro por símbolo
            side: Filtro por lado
            only_profitable: True=wins, False=losses, None=all
            limit: Máximo de registros por página
            cursor: ID do último fill da página anterior
            offset: Alternativa ao cursor (menos eficiente)
            
        Returns:
            {
                'items': [...],
                'nextCursor': int or None,
                'hasMore': bool,
                'total': int
            }
        """
        if not self.enabled:
            return {'items': [], 'hasMore': False, 'total': 0, 'nextCursor': None}
        
        try:
            with self.get_session() as session:
                if session is None:
                    return {'items': [], 'hasMore': False, 'total': 0, 'nextCursor': None}
                
                # Build base query
                if range_hours == -1:
                    cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
                else:
                    cutoff = datetime.now(timezone.utc) - timedelta(hours=range_hours)
                
                query = session.query(Fill).filter(Fill.ts_utc >= cutoff)
                
                # Apply filters
                if symbol:
                    query = query.filter(Fill.symbol == symbol)
                if side:
                    query = query.filter(Fill.side == side)
                if only_profitable is True:
                    query = query.filter(Fill.realized_pnl > 0)
                elif only_profitable is False:
                    query = query.filter(Fill.realized_pnl < 0)
                
                # Get total count (before pagination)
                total = query.count()
                
                # Apply cursor/offset pagination
                if cursor:
                    # Cursor-based: more efficient for large datasets
                    query = query.filter(Fill.id < cursor)
                elif offset:
                    # Offset-based: fallback
                    query = query.offset(offset)
                
                # Order by timestamp DESC, then by ID DESC for stable sorting
                query = query.order_by(desc(Fill.ts_utc), desc(Fill.id))
                
                # Fetch limit + 1 to check if there are more results
                records = query.limit(limit + 1).all()
                
                # Check if there are more results
                hasMore = len(records) > limit
                items = records[:limit]  # Remove the extra item
                
                # Next cursor is the ID of the last item
                nextCursor = items[-1].id if items and hasMore else None
                
                return {
                    'items': [
                        {
                            'id': r.id,
                            'trade_id': r.trade_id,
                            'ts': r.ts_utc.isoformat(),
                            'symbol': r.symbol,
                            'side': r.side,
                            'qty': r.qty,
                            'price': r.price,
                            'fee': r.fee,
                            'realized_pnl': r.realized_pnl,
                            'is_close': r.is_close,
                            'ai_reason': r.ai_reason
                        }
                        for r in items
                    ],
                    'nextCursor': nextCursor,
                    'hasMore': hasMore,
                    'total': total
                }
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao buscar fills paginados: {e}")
            return {'items': [], 'hasMore': False, 'total': 0, 'nextCursor': None}
    
    # ============================================================
    # PNL SUMMARY
    # ============================================================
    
    def get_pnl_summary(self, current_equity: float = None) -> Dict[str, Any]:
        """
        Retorna resumo de PnL para todos os períodos.
        
        Retorna:
        - pnl_all_time_pct, pnl_all_time_usd
        - pnl_day_pct, pnl_day_usd
        - pnl_week_pct, pnl_week_usd
        - pnl_month_pct, pnl_month_usd
        """
        if not self.enabled:
            return {}
        
        try:
            with self.get_session() as session:
                if session is None:
                    return {}
                
                # Busca equity atual se não fornecido
                if current_equity is None:
                    last_snapshot = session.query(EquitySnapshot)\
                        .order_by(desc(EquitySnapshot.ts_utc)).first()
                    current_equity = last_snapshot.equity_usd if last_snapshot else 0
                
                if current_equity <= 0:
                    return {}
                
                result = {
                    'current_equity': current_equity,
                    'pnl_all_time_pct': 0,
                    'pnl_all_time_usd': 0,
                    'pnl_day_pct': 0,
                    'pnl_day_usd': 0,
                    'pnl_week_pct': 0,
                    'pnl_week_usd': 0,
                    'pnl_month_pct': 0,
                    'pnl_month_usd': 0,
                }
                
                # Busca baselines
                baselines = session.query(PerformanceBaseline).filter_by(user_id='default').all()
                
                for b in baselines:
                    if b.start_equity > 0:
                        pnl_usd = current_equity - b.start_equity
                        pnl_pct = (pnl_usd / b.start_equity) * 100
                        
                        if b.period_key == 'all_time':
                            result['pnl_all_time_pct'] = round(pnl_pct, 2)
                            result['pnl_all_time_usd'] = round(pnl_usd, 2)
                            result['all_time_start_equity'] = b.start_equity
                            result['all_time_start_date'] = b.start_ts.isoformat()
                        elif b.period_key == 'day':
                            result['pnl_day_pct'] = round(pnl_pct, 2)
                            result['pnl_day_usd'] = round(pnl_usd, 2)
                        elif b.period_key == 'week':
                            result['pnl_week_pct'] = round(pnl_pct, 2)
                            result['pnl_week_usd'] = round(pnl_usd, 2)
                        elif b.period_key == 'month':
                            result['pnl_month_pct'] = round(pnl_pct, 2)
                            result['pnl_month_usd'] = round(pnl_usd, 2)
                
                return result
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao calcular PnL summary: {e}")
            return {}
    
    # ============================================================
    # METRICS
    # ============================================================
    
    def get_performance_metrics(self, range_hours: int = -1) -> Dict[str, Any]:
        """
        Calcula métricas de performance baseadas nos fills.
        
        Retorna:
        - winrate, profit_factor, avg_win, avg_loss
        - expectancy, max_drawdown
        - trades_count, trades_today, trades_week, trades_month
        """
        if not self.enabled:
            return {}
        
        try:
            with self.get_session() as session:
                if session is None:
                    return {}
                
                now = datetime.now(timezone.utc)
                
                # Busca fills com PnL realizado
                if range_hours == -1:
                    fills_query = session.query(Fill).filter(Fill.realized_pnl != 0)
                else:
                    cutoff = now - timedelta(hours=range_hours)
                    fills_query = session.query(Fill).filter(
                        Fill.ts_utc >= cutoff,
                        Fill.realized_pnl != 0
                    )
                
                fills = fills_query.all()
                
                if not fills:
                    return {
                        'trades_count': 0,
                        'winrate': 0,
                        'profit_factor': 0,
                        'avg_win': 0,
                        'avg_loss': 0,
                        'expectancy': 0,
                        'total_pnl': 0
                    }
                
                wins = [f for f in fills if f.realized_pnl > 0]
                losses = [f for f in fills if f.realized_pnl < 0]
                
                total_profit = sum(f.realized_pnl for f in wins)
                total_loss = abs(sum(f.realized_pnl for f in losses))
                
                winrate = (len(wins) / len(fills) * 100) if fills else 0
                profit_factor = (total_profit / total_loss) if total_loss > 0 else 0
                avg_win = (total_profit / len(wins)) if wins else 0
                avg_loss = (total_loss / len(losses)) if losses else 0
                
                # Expectancy = (Win% * AvgWin) - (Loss% * AvgLoss)
                win_pct = len(wins) / len(fills) if fills else 0
                loss_pct = len(losses) / len(fills) if fills else 0
                expectancy = (win_pct * avg_win) - (loss_pct * avg_loss)
                
                # Max Drawdown da equity curve
                max_dd = self._calculate_max_drawdown(session, range_hours)
                
                # Contagem por período
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                week_start = now - timedelta(days=now.weekday())
                week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                
                trades_today = session.query(Fill).filter(
                    Fill.ts_utc >= today_start,
                    Fill.realized_pnl != 0
                ).count()
                
                trades_week = session.query(Fill).filter(
                    Fill.ts_utc >= week_start,
                    Fill.realized_pnl != 0
                ).count()
                
                trades_month = session.query(Fill).filter(
                    Fill.ts_utc >= month_start,
                    Fill.realized_pnl != 0
                ).count()
                
                # Total de fees
                total_fees = sum(f.fee for f in fills if f.fee)
                
                return {
                    'trades_count': len(fills),
                    'trades_today': trades_today,
                    'trades_week': trades_week,
                    'trades_month': trades_month,
                    'wins': len(wins),
                    'losses': len(losses),
                    'winrate': round(winrate, 1),
                    'profit_factor': round(profit_factor, 2),
                    'avg_win': round(avg_win, 2),
                    'avg_loss': round(avg_loss, 2),
                    'expectancy': round(expectancy, 2),
                    'total_profit': round(total_profit, 2),
                    'total_loss': round(total_loss, 2),
                    'total_pnl': round(total_profit - total_loss, 2),
                    'total_fees': round(total_fees, 2),
                    'max_drawdown_pct': round(max_dd, 2)
                }
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao calcular métricas: {e}")
            return {}
    
    def _calculate_max_drawdown(self, session, range_hours: int = -1) -> float:
        """Calcula max drawdown da equity curve"""
        try:
            if range_hours == -1:
                snapshots = session.query(EquitySnapshot.equity_usd)\
                    .order_by(asc(EquitySnapshot.ts_utc)).all()
            else:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=range_hours)
                snapshots = session.query(EquitySnapshot.equity_usd)\
                    .filter(EquitySnapshot.ts_utc >= cutoff)\
                    .order_by(asc(EquitySnapshot.ts_utc)).all()
            
            if not snapshots:
                return 0
            
            peak = snapshots[0].equity_usd
            max_dd = 0
            
            for s in snapshots:
                if s.equity_usd > peak:
                    peak = s.equity_usd
                
                dd = ((peak - s.equity_usd) / peak) * 100 if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd
            
            return max_dd
            
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao calcular max DD: {e}")
            return 0
    
    # ============================================================
    # ERRORS
    # ============================================================
    
    def store_error(self, error_dict: Dict[str, Any]) -> bool:
        """Armazena erro para observabilidade"""
        if not self.enabled:
            return False
        
        try:
            with self.get_session() as session:
                if session is None:
                    return False
                
                record = ErrorRecord(
                    ts_utc=datetime.now(timezone.utc),
                    scope=error_dict.get('scope', 'UNKNOWN'),
                    symbol=error_dict.get('symbol'),
                    message=error_dict.get('message'),
                    stacktrace=error_dict.get('stacktrace'),
                    meta_json=error_dict.get('meta')
                )
                session.add(record)
                return True
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao gravar error: {e}")
            return False
    
    # ============================================================
    # BACKFILL (para importar histórico)
    # ============================================================
    
    def backfill_from_exchange(self, client, days: int = 30) -> int:
        """
        Faz backfill de fills da exchange Hyperliquid.
        
        Args:
            client: Client da Hyperliquid (HyperliquidBotClient)
            days: Quantos dias para trás (não usado, busca todos disponíveis)
            
        Returns:
            Número de fills importados
        """
        if not self.enabled:
            return 0
        
        try:
            fills = []
            
            # Método 1: get_user_fills (implementado no client)
            if hasattr(client, 'get_user_fills'):
                raw_fills = client.get_user_fills(limit=2000)
                if raw_fills:
                    fills = raw_fills
                    logger.info(f"[TELEMETRY] Backfill via get_user_fills: {len(fills)} fills")
            
            # Método 2: get_user_fills_by_time
            if not fills and hasattr(client, 'get_user_fills_by_time'):
                raw_fills = client.get_user_fills_by_time()
                if raw_fills:
                    fills = raw_fills
                    logger.info(f"[TELEMETRY] Backfill via get_user_fills_by_time: {len(fills)} fills")
            
            if not fills:
                logger.warning("[TELEMETRY] Nenhum fill encontrado para backfill")
                return 0
            
            # Grava fills
            count = 0
            for fill in fills:
                # Normaliza side (Hyperliquid usa 'A'/'B' ou 'Open Long'/'Close Short')
                side = fill.get('side', '')
                if side == 'A':
                    side = 'sell'
                elif side == 'B':
                    side = 'buy'
                elif 'Long' in str(fill.get('dir', '')):
                    side = 'long'
                elif 'Short' in str(fill.get('dir', '')):
                    side = 'short'
                
                normalized = {
                    'trade_id': fill.get('trade_id'),
                    'ts_utc': fill.get('ts_utc'),
                    'symbol': fill.get('symbol'),
                    'side': side,
                    'qty': fill.get('qty'),
                    'price': fill.get('price'),
                    'fee': fill.get('fee', 0),
                    'realized_pnl': fill.get('realized_pnl', 0),
                    'order_id': fill.get('order_id'),
                    'is_close': fill.get('is_close', False)
                }
                
                if self.record_fill(normalized):
                    count += 1
            
            logger.info(f"[TELEMETRY] ✅ Backfill completo: {count} fills importados")
            return count
            
        except Exception as e:
            logger.error(f"[TELEMETRY] ❌ Erro no backfill: {e}")
            return 0
    
    def sync_fills_incremental(self, client) -> int:
        """
        Sync incremental de fills desde o último sync.
        
        Deve ser chamado periodicamente (ex: a cada 2-5 min).
        
        Returns:
            Número de novos fills
        """
        if not self.enabled:
            return 0
        
        try:
            # Busca último fill registrado
            with self.get_session() as session:
                if session is None:
                    return 0
                
                last_fill = session.query(Fill).order_by(desc(Fill.ts_utc)).first()
                
                if last_fill:
                    # Busca fills após o último
                    last_ts = int(last_fill.ts_utc.timestamp() * 1000)
                    
                    if hasattr(client, 'get_user_fills_by_time'):
                        new_fills = client.get_user_fills_by_time(start_time=last_ts + 1)
                    else:
                        new_fills = client.get_user_fills(limit=100)
                else:
                    # Primeiro sync - faz backfill completo
                    return self.backfill_from_exchange(client)
            
            if not new_fills:
                return 0
            
            count = 0
            for fill in new_fills:
                side = fill.get('side', '')
                if side == 'A':
                    side = 'sell'
                elif side == 'B':
                    side = 'buy'
                
                normalized = {
                    'trade_id': fill.get('trade_id'),
                    'ts_utc': fill.get('ts_utc'),
                    'symbol': fill.get('symbol'),
                    'side': side,
                    'qty': fill.get('qty'),
                    'price': fill.get('price'),
                    'fee': fill.get('fee', 0),
                    'realized_pnl': fill.get('realized_pnl', 0),
                    'order_id': fill.get('order_id'),
                    'is_close': fill.get('is_close', False)
                }
                
                if self.record_fill(normalized):
                    count += 1
            
            if count > 0:
                logger.info(f"[TELEMETRY] Sync incremental: {count} novos fills")
            
            return count
            
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro no sync incremental: {e}")
            return 0
    
    # ============================================================
    # LEGACY COMPATIBILITY (snapshot antigo)
    # ============================================================
    
    def store_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """Compatibilidade com formato antigo de snapshot"""
        if not self.enabled:
            return False
        
        try:
            account = snapshot.get('account', {})
            positions = snapshot.get('positions', {})
            execution = snapshot.get('execution', {})
            
            return self.record_equity_snapshot(
                equity=account.get('equity', 0),
                unrealized=positions.get('total_pnl_usd', 0),
                positions_count=positions.get('count', 0),
                execution_mode=execution.get('mode'),
                ai_mode=execution.get('trading_mode')
            )
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao converter snapshot: {e}")
            return False
    
    def store_trade_event(self, trade_event: Dict[str, Any]) -> bool:
        """Compatibilidade com formato antigo de trade event"""
        return self.record_fill(trade_event)


# ============================================================
# SINGLETON
# ============================================================

_telemetry_store: Optional[TelemetryStore] = None


def get_telemetry_store() -> TelemetryStore:
    """Retorna instância singleton do TelemetryStore"""
    global _telemetry_store
    if _telemetry_store is None:
        _telemetry_store = TelemetryStore()
    return _telemetry_store


def init_telemetry(database_url: str = None) -> TelemetryStore:
    """Inicializa e retorna TelemetryStore"""
    global _telemetry_store
    _telemetry_store = TelemetryStore(database_url)
    return _telemetry_store

