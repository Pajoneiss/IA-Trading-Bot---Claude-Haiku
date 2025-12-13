"""
TELEMETRY STORE
===============

Módulo de persistência para telemetria do bot.
Armazena snapshots, trades, e erros no Postgres.

Tabelas:
- snapshots: Time-series do estado do bot
- trades: Journal de todas as operações
- errors: Log de erros para observabilidade

Uso:
    from bot.telemetry_store import TelemetryStore
    
    store = TelemetryStore()
    store.store_snapshot(snapshot_dict)
    store.store_trade_event(trade_event)
    store.store_error(error_dict)

Autor: Claude
Data: 2024-12-13
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ============================================================
# SQLAlchemy Setup
# ============================================================

try:
    from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, JSON
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import QueuePool
    
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    logger.warning("[TELEMETRY] SQLAlchemy não disponível - pip install sqlalchemy psycopg2-binary")

Base = declarative_base() if SQLALCHEMY_AVAILABLE else None


# ============================================================
# MODELS
# ============================================================

if SQLALCHEMY_AVAILABLE:
    class SnapshotRecord(Base):
        """Time-series de snapshots do bot"""
        __tablename__ = 'snapshots'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        ts_utc = Column(DateTime(timezone=True), nullable=False, index=True)
        
        # Execution
        mode_execution = Column(String(50))  # PAPER/LIVE/SHADOW
        ai_mode = Column(String(50))  # GLOBAL_IA/BALANCEADO/etc
        is_paused = Column(Boolean, default=False)
        
        # Account
        equity = Column(Float)
        free_margin = Column(Float)
        day_pnl_pct = Column(Float)
        week_pnl_pct = Column(Float)
        daily_drawdown_pct = Column(Float)
        
        # Positions
        open_positions_count = Column(Integer, default=0)
        total_positions_pnl_usd = Column(Float, default=0)
        
        # AI Budget
        claude_calls_today = Column(Integer, default=0)
        claude_limit_per_day = Column(Integer, default=12)
        openai_calls_today = Column(Integer, default=0)
        openai_limit_per_day = Column(Integer, default=40)
        
        # GLOBAL_IA
        global_ia_active = Column(Boolean, default=False)
        global_ia_last_call_ts = Column(DateTime(timezone=True))
        
        # Market
        symbols_monitored = Column(Integer, default=0)
        
        # Raw JSON (backup completo)
        raw_json = Column(JSON)
        
        # Multi-tenant (futuro)
        user_id = Column(String(100), default='default')
        account_id = Column(String(100), default='default')


    class TradeRecord(Base):
        """Journal de trades"""
        __tablename__ = 'trades'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        ts_utc = Column(DateTime(timezone=True), nullable=False, index=True)
        
        # Trade info
        symbol = Column(String(20), nullable=False, index=True)
        side = Column(String(10))  # long/short
        action_type = Column(String(20))  # OPEN/CLOSE/INCREASE/DECREASE/SL/TP/BREAKEVEN
        
        # Execution
        size = Column(Float)
        price = Column(Float)
        leverage = Column(Integer)
        
        # PnL
        pnl_usd = Column(Float)
        pnl_pct = Column(Float)
        fees_est_usd = Column(Float)
        
        # Context
        mode_execution = Column(String(50))
        strategy_tag = Column(String(50))
        
        # AI Decision
        ai_reason = Column(Text)
        ai_confidence = Column(Float)
        
        # Raw data
        state_hash = Column(String(64))
        raw_ai_decision_json = Column(JSON)
        raw_exchange_response = Column(JSON)
        
        # Multi-tenant
        user_id = Column(String(100), default='default')
        account_id = Column(String(100), default='default')


    class ErrorRecord(Base):
        """Log de erros para observabilidade"""
        __tablename__ = 'errors'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        ts_utc = Column(DateTime(timezone=True), nullable=False, index=True)
        
        # Error info
        scope = Column(String(50))  # GLOBAL_IA/EXECUTION/TELEGRAM/API
        symbol = Column(String(20))
        message = Column(Text)
        stacktrace = Column(Text)
        
        # Extra
        meta_json = Column(JSON)
        
        # Multi-tenant
        user_id = Column(String(100), default='default')
        account_id = Column(String(100), default='default')


# ============================================================
# TELEMETRY STORE CLASS
# ============================================================

class TelemetryStore:
    """
    Classe principal para persistência de telemetria.
    
    Conecta ao Postgres via DATABASE_URL e oferece métodos
    para armazenar snapshots, trades e erros.
    """
    
    def __init__(self, database_url: str = None):
        """
        Inicializa conexão com banco.
        
        Args:
            database_url: URL do Postgres (default: env DATABASE_URL)
        """
        self.enabled = False
        self.engine = None
        self.Session = None
        
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
            logger.info("[TELEMETRY] ✅ Store inicializado com sucesso")
            
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
    
    def store_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """
        Armazena snapshot do bot.
        
        Args:
            snapshot: Dict com estado do bot (de build_runtime_snapshot)
            
        Returns:
            True se gravou com sucesso
        """
        if not self.enabled:
            return False
        
        try:
            with self.get_session() as session:
                if session is None:
                    return False
                
                # Extrai campos
                execution = snapshot.get('execution', {})
                account = snapshot.get('account', {})
                positions = snapshot.get('positions', {})
                ai_budget = snapshot.get('ai_budget', {})
                global_ia = snapshot.get('global_ia', {})
                market = snapshot.get('market', {})
                
                # Parse timestamps
                global_ia_last_call = None
                if global_ia.get('last_call_time'):
                    try:
                        global_ia_last_call = datetime.fromisoformat(
                            global_ia['last_call_time'].replace('Z', '+00:00')
                        )
                    except:
                        pass
                
                record = SnapshotRecord(
                    ts_utc=datetime.now(timezone.utc),
                    
                    mode_execution=execution.get('mode'),
                    ai_mode=execution.get('trading_mode'),
                    is_paused=execution.get('is_paused', False),
                    
                    equity=account.get('equity'),
                    free_margin=account.get('free_margin'),
                    day_pnl_pct=account.get('day_pnl_pct'),
                    week_pnl_pct=account.get('week_pnl_pct'),
                    daily_drawdown_pct=account.get('daily_drawdown_pct'),
                    
                    open_positions_count=positions.get('count', 0),
                    total_positions_pnl_usd=positions.get('total_pnl_usd', 0),
                    
                    claude_calls_today=ai_budget.get('claude_calls_today', 0),
                    claude_limit_per_day=ai_budget.get('claude_limit_per_day', 12),
                    openai_calls_today=ai_budget.get('openai_calls_today', 0),
                    openai_limit_per_day=ai_budget.get('openai_limit_per_day', 40),
                    
                    global_ia_active=global_ia.get('enabled', False),
                    global_ia_last_call_ts=global_ia_last_call,
                    
                    symbols_monitored=market.get('symbols_monitored', 0),
                    
                    raw_json=snapshot
                )
                
                session.add(record)
                logger.debug("[TELEMETRY] Snapshot armazenado")
                return True
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao gravar snapshot: {e}")
            return False
    
    def store_trade_event(self, trade_event: Dict[str, Any]) -> bool:
        """
        Armazena evento de trade (open/close/adjust/etc).
        
        Args:
            trade_event: Dict com:
                - symbol, side, action_type
                - size, price, leverage
                - pnl_usd, pnl_pct, fees_est_usd
                - ai_reason, ai_confidence
                - raw_ai_decision, raw_exchange_response
                - state_snapshot (opcional)
                
        Returns:
            True se gravou com sucesso
        """
        if not self.enabled:
            return False
        
        try:
            with self.get_session() as session:
                if session is None:
                    return False
                
                # Gera hash do state se fornecido
                state_hash = None
                if trade_event.get('state_snapshot'):
                    state_str = json.dumps(trade_event['state_snapshot'], sort_keys=True)
                    state_hash = hashlib.sha256(state_str.encode()).hexdigest()[:64]
                
                record = TradeRecord(
                    ts_utc=datetime.now(timezone.utc),
                    
                    symbol=trade_event.get('symbol'),
                    side=trade_event.get('side'),
                    action_type=trade_event.get('action_type'),
                    
                    size=trade_event.get('size'),
                    price=trade_event.get('price'),
                    leverage=trade_event.get('leverage'),
                    
                    pnl_usd=trade_event.get('pnl_usd'),
                    pnl_pct=trade_event.get('pnl_pct'),
                    fees_est_usd=trade_event.get('fees_est_usd'),
                    
                    mode_execution=trade_event.get('mode_execution'),
                    strategy_tag=trade_event.get('strategy_tag'),
                    
                    ai_reason=trade_event.get('ai_reason'),
                    ai_confidence=trade_event.get('ai_confidence'),
                    
                    state_hash=state_hash,
                    raw_ai_decision_json=trade_event.get('raw_ai_decision'),
                    raw_exchange_response=trade_event.get('raw_exchange_response')
                )
                
                session.add(record)
                logger.info(f"[TELEMETRY] Trade registrado: {trade_event.get('symbol')} {trade_event.get('action_type')}")
                return True
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao gravar trade: {e}")
            return False
    
    def store_error(self, error_dict: Dict[str, Any]) -> bool:
        """
        Armazena erro para observabilidade.
        
        Args:
            error_dict: Dict com:
                - scope: GLOBAL_IA/EXECUTION/TELEGRAM/API
                - symbol (opcional)
                - message
                - stacktrace (opcional)
                - meta (opcional)
                
        Returns:
            True se gravou com sucesso
        """
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
                logger.debug(f"[TELEMETRY] Erro registrado: {error_dict.get('scope')}")
                return True
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao gravar error: {e}")
            return False
    
    # ============================================================
    # QUERY METHODS (para API)
    # ============================================================
    
    def get_snapshots_series(self, 
                             range_hours: int = 24, 
                             limit: int = 1000) -> List[Dict]:
        """
        Retorna série de snapshots para gráfico.
        
        Args:
            range_hours: Quantas horas para trás
            limit: Máximo de registros
            
        Returns:
            Lista de dicts com ts, equity, day_pnl_pct, etc.
        """
        if not self.enabled:
            return []
        
        try:
            with self.get_session() as session:
                if session is None:
                    return []
                
                from sqlalchemy import desc
                from datetime import timedelta
                
                cutoff = datetime.now(timezone.utc) - timedelta(hours=range_hours)
                
                records = session.query(SnapshotRecord)\
                    .filter(SnapshotRecord.ts_utc >= cutoff)\
                    .order_by(desc(SnapshotRecord.ts_utc))\
                    .limit(limit)\
                    .all()
                
                return [
                    {
                        'ts': r.ts_utc.isoformat() if r.ts_utc else None,
                        'equity': r.equity,
                        'day_pnl_pct': r.day_pnl_pct,
                        'open_positions': r.open_positions_count,
                        'total_pnl_usd': r.total_positions_pnl_usd
                    }
                    for r in reversed(records)
                ]
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao buscar série: {e}")
            return []
    
    def get_trades(self, 
                   limit: int = 200, 
                   symbol: str = None,
                   range_hours: int = 24) -> List[Dict]:
        """
        Retorna trades do journal.
        
        Args:
            limit: Máximo de registros
            symbol: Filtro por símbolo (opcional)
            range_hours: Quantas horas para trás
            
        Returns:
            Lista de trades
        """
        if not self.enabled:
            return []
        
        try:
            with self.get_session() as session:
                if session is None:
                    return []
                
                from sqlalchemy import desc
                from datetime import timedelta
                
                cutoff = datetime.now(timezone.utc) - timedelta(hours=range_hours)
                
                query = session.query(TradeRecord)\
                    .filter(TradeRecord.ts_utc >= cutoff)
                
                if symbol:
                    query = query.filter(TradeRecord.symbol == symbol)
                
                records = query.order_by(desc(TradeRecord.ts_utc))\
                    .limit(limit)\
                    .all()
                
                return [
                    {
                        'id': r.id,
                        'ts': r.ts_utc.isoformat() if r.ts_utc else None,
                        'symbol': r.symbol,
                        'side': r.side,
                        'action_type': r.action_type,
                        'size': r.size,
                        'price': r.price,
                        'leverage': r.leverage,
                        'pnl_usd': r.pnl_usd,
                        'pnl_pct': r.pnl_pct,
                        'ai_reason': r.ai_reason,
                        'strategy_tag': r.strategy_tag
                    }
                    for r in records
                ]
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao buscar trades: {e}")
            return []
    
    def get_metrics(self, range_hours: int = 24) -> Dict[str, Any]:
        """
        Calcula métricas agregadas.
        
        Args:
            range_hours: Período de análise
            
        Returns:
            Dict com win_rate, profit_factor, avg_win, avg_loss, etc.
        """
        if not self.enabled:
            return {}
        
        try:
            trades = self.get_trades(limit=1000, range_hours=range_hours)
            
            if not trades:
                return {}
            
            # Filtra apenas trades de fechamento (CLOSE, SL, TP)
            closed_trades = [t for t in trades if t.get('action_type') in ['CLOSE', 'SL', 'TP', 'close']]
            
            if not closed_trades:
                return {}
            
            wins = [t for t in closed_trades if (t.get('pnl_usd') or 0) > 0]
            losses = [t for t in closed_trades if (t.get('pnl_usd') or 0) < 0]
            
            total_profit = sum(t.get('pnl_usd', 0) for t in wins)
            total_loss = abs(sum(t.get('pnl_usd', 0) for t in losses))
            
            win_rate = len(wins) / len(closed_trades) * 100 if closed_trades else 0
            profit_factor = total_profit / total_loss if total_loss > 0 else 0
            avg_win = total_profit / len(wins) if wins else 0
            avg_loss = total_loss / len(losses) if losses else 0
            
            # Expectancy = (Win% * AvgWin) - (Loss% * AvgLoss)
            win_pct = len(wins) / len(closed_trades) if closed_trades else 0
            loss_pct = len(losses) / len(closed_trades) if closed_trades else 0
            expectancy = (win_pct * avg_win) - (loss_pct * avg_loss)
            
            return {
                'total_trades': len(closed_trades),
                'wins': len(wins),
                'losses': len(losses),
                'win_rate': round(win_rate, 1),
                'profit_factor': round(profit_factor, 2),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'expectancy': round(expectancy, 2),
                'total_profit': round(total_profit, 2),
                'total_loss': round(total_loss, 2),
                'net_pnl': round(total_profit - total_loss, 2)
            }
            
        except Exception as e:
            logger.error(f"[TELEMETRY] Erro ao calcular métricas: {e}")
            return {}


# ============================================================
# SINGLETON INSTANCE
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
