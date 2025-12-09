"""
Phase 5 - Trading Modes
Sistema de personalidade do trader (Conservador, Balanceado, Agressivo)
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """Modos de trading disponíveis"""
    CONSERVADOR = "CONSERVADOR"
    BALANCEADO = "BALANCEADO"
    AGRESSIVO = "AGRESSIVO"


class TradingModeConfig:
    """
    Configuração dos modos de trading
    
    Cada modo ajusta parâmetros DENTRO dos limites já existentes:
    - risk_multiplier: Multiplicador do risco base (0.5 a 1.2)
    - confidence_delta_swing: Ajuste na confiança mínima swing
    - confidence_delta_scalp: Ajuste na confiança mínima scalp
    - max_signals_per_day: Limite de sinais/dia
    - allowed_regimes: Regimes permitidos
    - quality_gate_strictness: Ajuste no Quality Gate
    """
    
    MODES = {
        TradingMode.CONSERVADOR: {
            'risk_multiplier': 0.5,  # 50% do risco base
            'confidence_delta_swing': 0.10,  # +10% na confiança mínima
            'confidence_delta_scalp': 0.10,  # +10% na confiança mínima
            'max_signals_per_day': 10,
            'allowed_regimes': ['TREND_BULL', 'TREND_BEAR'],  # Só trends limpos
            'quality_gate_strictness': 1.2,  # 20% mais rígido
            'description': '👶 Modo mais seletivo com menor risco',
            'emoji': '👶'
        },
        TradingMode.BALANCEADO: {
            'risk_multiplier': 1.0,  # 100% do risco base (padrão atual)
            'confidence_delta_swing': 0.0,  # Sem ajuste
            'confidence_delta_scalp': 0.0,  # Sem ajuste
            'max_signals_per_day': 20,
            'allowed_regimes': ['TREND_BULL', 'TREND_BEAR', 'RANGE_CHOP', 'LOW_VOL_DRIFT'],
            'quality_gate_strictness': 1.0,  # Padrão
            'description': '⚖️ Modo equilibrado (padrão)',
            'emoji': '⚖️'
        },
        TradingMode.AGRESSIVO: {
            'risk_multiplier': 1.2,  # 120% do risco base (NUNCA ultrapassa limite global)
            'confidence_delta_swing': -0.05,  # -5% na confiança mínima
            'confidence_delta_scalp': -0.05,  # -5% na confiança mínima
            'max_signals_per_day': 40,
            'allowed_regimes': ['TREND_BULL', 'TREND_BEAR', 'RANGE_CHOP', 'LOW_VOL_DRIFT'],
            'quality_gate_strictness': 0.9,  # 10% mais permissivo
            'description': '🔥 Mais trades com risco controlado',
            'emoji': '🔥'
        }
    }
    
    @classmethod
    def get_config(cls, mode: TradingMode) -> Dict[str, Any]:
        """
        Retorna configuração de um modo
        
        Args:
            mode: Modo de trading
            
        Returns:
            Dict com configurações do modo
        """
        return cls.MODES.get(mode, cls.MODES[TradingMode.BALANCEADO])
    
    @classmethod
    def get_all_modes(cls) -> Dict[TradingMode, Dict[str, Any]]:
        """Retorna todas as configurações"""
        return cls.MODES.copy()


class TradingModeManager:
    """
    Gerenciador de modos de trading
    
    Responsável por:
    - Carregar/salvar modo atual
    - Aplicar multiplicadores de risco
    - Ajustar thresholds de confiança
    - Validar regimes permitidos
    """
    
    STATE_FILE = "data/trading_mode_state.json"
    
    def __init__(self, logger_instance=None):
        """
        Inicializa Trading Mode Manager
        
        Args:
            logger_instance: Logger opcional
        """
        self.logger = logger_instance or logger
        self.current_mode = TradingMode.BALANCEADO  # Default
        self.signals_today = 0  # Contador de sinais do dia
        
        # Cache de configurações do arquivo mode_config.json
        self.mode_config_cache: Dict[str, Any] = {}
        self._load_mode_config()
        
        # Carrega modo persistido
        self._load_mode()
        
        self.logger.info(f"[MODE] Modo de trading carregado: {self.current_mode.value}")
    
    def get_current_mode(self) -> TradingMode:
        """Retorna modo atual"""
        return self.current_mode
    
    def get_current_config(self) -> Dict[str, Any]:
        """Retorna configuração do modo atual"""
        return TradingModeConfig.get_config(self.current_mode)
    
    def set_mode(self, mode: TradingMode, source: str = "unknown") -> bool:
        """
        Altera modo de trading
        
        Args:
            mode: Novo modo
            source: Origem da mudança (telegram, api, etc)
            
        Returns:
            True se alterado com sucesso
        """
        try:
            old_mode = self.current_mode
            self.current_mode = mode
            
            # Salva estado
            self._save_mode()
            
            # Log da mudança
            self.logger.info(
                f"[MODE] Modo alterado por {source}: "
                f"{old_mode.value} -> {mode.value}"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"[MODE] Erro ao alterar modo: {e}", exc_info=True)
            return False
    
    def apply_risk_multiplier(self, base_risk: float, max_risk: float) -> float:
        """
        Aplica multiplicador de risco do modo atual
        
        Args:
            base_risk: Risco base (ex: 2.0%)
            max_risk: Risco máximo permitido (ex: 5.0%)
            
        Returns:
            Risco efetivo (nunca ultrapassa max_risk)
        """
        try:
            config = self.get_current_config()
            multiplier = config['risk_multiplier']
            
            # Aplica multiplicador
            effective_risk = base_risk * multiplier
            
            # NUNCA ultrapassa limite global
            effective_risk = min(effective_risk, max_risk)
            
            # Log do ajuste
            self.logger.debug(
                f"[MODE] Aplicando risk_multiplier={multiplier} "
                f"({self.current_mode.value}) sobre risco base={base_risk:.2f}% "
                f"-> risco efetivo={effective_risk:.2f}%"
            )
            
            return effective_risk
            
        except Exception as e:
            self.logger.error(f"[MODE] Erro ao aplicar risk multiplier: {e}")
            return base_risk  # Fallback para risco base
    
    def get_min_confidence(self, ai_type: str, base_confidence: float) -> float:
        """
        Calcula confiança mínima ajustada pelo modo
        
        Args:
            ai_type: 'swing' ou 'scalp'
            base_confidence: Confiança base (ex: 0.80)
            
        Returns:
            Confiança mínima ajustada
        """
        try:
            config = self.get_current_config()
            
            # Pega delta apropriado
            if ai_type == 'swing':
                delta = config['confidence_delta_swing']
            else:
                delta = config['confidence_delta_scalp']
            
            # Calcula confiança ajustada
            adjusted = base_confidence + delta
            
            # Limita entre 0.5 e 0.95 (sanity check)
            adjusted = max(0.5, min(0.95, adjusted))
            
            if delta != 0:
                self.logger.debug(
                    f"[MODE] Confiança mínima {ai_type}: {base_confidence:.2f} + "
                    f"{delta:.2f} = {adjusted:.2f} ({self.current_mode.value})"
                )
            
            return adjusted
            
        except Exception as e:
            self.logger.error(f"[MODE] Erro ao calcular confiança: {e}")
            return base_confidence  # Fallback
    
    def is_regime_allowed(self, regime: str) -> bool:
        """
        Verifica se regime é permitido no modo atual
        
        Args:
            regime: Regime de mercado (ex: 'TREND_BULL')
            
        Returns:
            True se permitido
        """
        try:
            config = self.get_current_config()
            allowed = config['allowed_regimes']
            
            is_allowed = regime in allowed
            
            if not is_allowed:
                self.logger.info(
                    f"[MODE] Trade bloqueado: regime '{regime}' não compatível "
                    f"com modo {self.current_mode.value} "
                    f"(permitidos: {', '.join(allowed)})"
                )
            
            return is_allowed
            
        except Exception as e:
            self.logger.error(f"[MODE] Erro ao verificar regime: {e}")
            return True  # Fallback permissivo
    
    def can_accept_signal(self) -> bool:
        """
        Verifica se pode aceitar mais um sinal hoje
        
        Returns:
            True se pode aceitar
        """
        try:
            config = self.get_current_config()
            max_signals = config['max_signals_per_day']
            
            can_accept = self.signals_today < max_signals
            
            if not can_accept:
                self.logger.info(
                    f"[MODE] Limite de sinais diários atingido: "
                    f"{self.signals_today}/{max_signals} ({self.current_mode.value})"
                )
            
            return can_accept
            
        except Exception as e:
            self.logger.error(f"[MODE] Erro ao verificar limite de sinais: {e}")
            return True  # Fallback permissivo
    
    def increment_signal_count(self):
        """Incrementa contador de sinais do dia"""
        self.signals_today += 1
        self.logger.debug(f"[MODE] Sinais hoje: {self.signals_today}")
    
    def reset_daily_counters(self):
        """Reseta contadores diários (chamar a cada novo dia)"""
        self.signals_today = 0
        self.logger.debug("[MODE] Contadores diários resetados")
    
    def get_quality_gate_strictness(self) -> float:
        """
        Retorna multiplicador de strictness do Quality Gate
        
        Returns:
            Multiplicador (1.0 = padrão, >1.0 = mais rígido, <1.0 = mais permissivo)
        """
        try:
            mode_key = self.current_mode.value
            if mode_key in self.mode_config_cache:
                return self.mode_config_cache[mode_key].get('quality_gate_strictness', 1.0)
            config = self.get_current_config()
            return config['quality_gate_strictness']
        except:
            return 1.0
    
    # ========== NOVOS MÉTODOS - CONFIGS DINÂMICAS POR MODO ==========
    
    MODE_CONFIG_FILE = "data/mode_config.json"
    
    def _load_mode_config(self):
        """Carrega configurações do arquivo mode_config.json"""
        try:
            config_file = Path(self.MODE_CONFIG_FILE)
            
            if not config_file.exists():
                self.logger.warning(f"[MODE] Arquivo {self.MODE_CONFIG_FILE} não encontrado. Usando configs padrão.")
                return
            
            with open(config_file, 'r', encoding='utf-8') as f:
                self.mode_config_cache = json.load(f)
            
            self.logger.info(f"[MODE] Configs carregadas de {self.MODE_CONFIG_FILE}: {list(self.mode_config_cache.keys())}")
            
        except Exception as e:
            self.logger.error(f"[MODE] Erro ao carregar {self.MODE_CONFIG_FILE}: {e}")
            self.mode_config_cache = {}
    
    def get_mode_config_value(self, key: str, default: Any = None) -> Any:
        """
        Retorna valor de config para o modo atual
        
        Args:
            key: Nome da config (ex: 'min_conf_swing')
            default: Valor default se não encontrar
        """
        mode_key = self.current_mode.value
        if mode_key in self.mode_config_cache:
            return self.mode_config_cache[mode_key].get(key, default)
        return default
    
    def get_min_conf_swing(self) -> float:
        """Retorna confiança mínima para SWING no modo atual"""
        return self.get_mode_config_value('min_conf_swing', 0.80)
    
    def get_min_conf_scalp(self) -> float:
        """Retorna confiança mínima para SCALP no modo atual"""
        return self.get_mode_config_value('min_conf_scalp', 0.70)
    
    def get_risk_per_trade(self, ai_type: str = 'swing') -> float:
        """
        Retorna % de risco por trade para o tipo de IA
        
        Args:
            ai_type: 'swing' ou 'scalp'
        """
        if ai_type == 'scalp':
            return self.get_mode_config_value('risk_per_trade_scalp_pct', 0.35)
        return self.get_mode_config_value('risk_per_trade_swing_pct', 0.75)
    
    def get_max_trades_scalp(self) -> int:
        """Retorna limite diário de trades SCALP no modo atual"""
        return self.get_mode_config_value('max_trades_per_day_scalp', 7)
    
    def get_allowed_regimes(self, ai_type: str = 'swing') -> list:
        """
        Retorna lista de regimes permitidos para o tipo de IA
        
        Args:
            ai_type: 'swing' ou 'scalp'
        """
        if ai_type == 'scalp':
            key = 'allowed_regimes_scalp'
            default = ['TREND_BULL', 'TREND_BEAR']
        else:
            key = 'allowed_regimes_swing'
            default = ['TREND_BULL', 'TREND_BEAR']
        
        return self.get_mode_config_value(key, default)
    
    def is_regime_allowed_for_type(self, regime: str, ai_type: str = 'swing') -> bool:
        """
        Verifica se regime é permitido para dado tipo de IA no modo atual
        
        Args:
            regime: Regime de mercado (ex: 'TREND_BULL')
            ai_type: 'swing' ou 'scalp'
            
        Returns:
            True se permitido
        """
        allowed = self.get_allowed_regimes(ai_type)
        is_allowed = regime in allowed
        
        if not is_allowed:
            self.logger.info(
                f"[MODE] Trade {ai_type.upper()} bloqueado: regime '{regime}' não compatível "
                f"com modo {self.current_mode.value} "
                f"(permitidos: {', '.join(allowed)})"
            )
        
        return is_allowed
    
    def get_max_open_positions(self) -> int:
        """Retorna máximo de posições abertas simultâneas"""
        return self.get_mode_config_value('max_open_positions', 3)
    
    def get_max_total_risk_open_pct(self) -> float:
        """Retorna risco total máximo aberto em %"""
        return self.get_mode_config_value('max_total_risk_open_pct', 5.0)
    
    def get_max_daily_loss_pct(self) -> float:
        """Retorna perda diária máxima em %"""
        return self.get_mode_config_value('max_daily_loss_pct', 4.0)
    
    def get_max_weekly_loss_pct(self) -> float:
        """Retorna perda semanal máxima em %"""
        return self.get_mode_config_value('max_weekly_loss_pct', 10.0)
    
    def get_management_config(self) -> Dict[str, Any]:
        """Retorna dict com parâmetros de gestão (BE, Trim, etc)"""
        default_mgmt = {
            "be_rr": 1.2,
            "first_trim_rr": 2.0,
            "first_trim_pct": 0.5,
            "trail_start_rr": 2.5
        }
        return self.get_mode_config_value('management', default_mgmt)
    
    def get_mode_summary(self) -> str:
        """Retorna resumo do modo atual para logs/telegram"""
        mode = self.current_mode.value
        conf_swing = self.get_min_conf_swing()
        conf_scalp = self.get_min_conf_scalp()
        risk_swing = self.get_risk_per_trade('swing')
        risk_scalp = self.get_risk_per_trade('scalp')
        max_scalp = self.get_max_trades_scalp()
        
        return (
            f"{mode}: Swing(conf≥{conf_swing:.0%}, risk={risk_swing}%) | "
            f"Scalp(conf≥{conf_scalp:.0%}, risk={risk_scalp}%, max/day={max_scalp})"
        )
    
    # ========== FIM NOVOS MÉTODOS ==========
    
    def _load_mode(self):
        """Carrega modo persistido"""
        try:
            state_file = Path(self.STATE_FILE)
            
            if not state_file.exists():
                # Primeira execução - cria arquivo com modo padrão
                self._save_mode()
                return
            
            # Carrega arquivo
            with open(state_file, 'r') as f:
                data = json.load(f)
            
            # Extrai modo
            mode_str = data.get('mode', 'BALANCEADO')
            self.current_mode = TradingMode[mode_str]
            
            self.logger.debug(f"[MODE] Modo carregado do arquivo: {mode_str}")
            
        except Exception as e:
            self.logger.warning(
                f"[MODE] Erro ao carregar modo do arquivo: {e}. "
                f"Usando padrão (BALANCEADO)"
            )
            self.current_mode = TradingMode.BALANCEADO
    
    def _save_mode(self):
        """Salva modo no arquivo de estado"""
        try:
            state_file = Path(self.STATE_FILE)
            
            # Garante que diretório existe
            state_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Salva estado
            data = {
                'mode': self.current_mode.value
            }
            
            with open(state_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.logger.debug(f"[MODE] Modo salvo: {self.current_mode.value}")
            
        except Exception as e:
            self.logger.error(f"[MODE] Erro ao salvar modo: {e}", exc_info=True)
