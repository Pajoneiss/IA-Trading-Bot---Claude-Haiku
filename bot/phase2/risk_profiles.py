"""
Phase 2 - Risk Profiles
Define comportamento AGGRESSIVE, BALANCED, CONSERVATIVE
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class RiskProfiles:
    """
    Risk Profiles configuráveis
    
    Profiles:
    - AGGRESSIVE: Mira 3R+, stops mais largos, mais trades
    - BALANCED: Meio termo, setups A+ normais
    - CONSERVATIVE: Só setups cristalinos, stops curtos
    """
    
    PROFILES = {
        'AGGRESSIVE': {
            'min_confidence': 0.75,
            'target_r_multiple': 3.0,
            'max_stop_pct': 3.0,
            'min_rr_ratio': 2.0,
            'max_trades_per_day': 8,
            'partial_pct': 0.33,  # 33% em parcial
            'description': 'Alto risco, alto retorno. Mira 3R+.'
        },
        'BALANCED': {
            'min_confidence': 0.80,
            'target_r_multiple': 2.5,
            'max_stop_pct': 2.5,
            'min_rr_ratio': 2.5,
            'max_trades_per_day': 5,
            'partial_pct': 0.50,  # 50% em parcial
            'description': 'Equilíbrio entre risco e retorno.'
        },
        'CONSERVATIVE': {
            'min_confidence': 0.85,
            'target_r_multiple': 2.0,
            'max_stop_pct': 2.0,
            'min_rr_ratio': 3.0,
            'max_trades_per_day': 3,
            'partial_pct': 0.60,  # 60% em parcial
            'description': 'Baixo risco, apenas setups cristalinos.'
        }
    }
    
    @classmethod
    def get_profile(cls, profile_name: str) -> Dict[str, Any]:
        """
        Retorna configuração do perfil
        
        Args:
            profile_name: 'AGGRESSIVE', 'BALANCED', 'CONSERVATIVE'
            
        Returns:
            Dict com configurações do perfil
        """
        profile = cls.PROFILES.get(profile_name.upper(), cls.PROFILES['BALANCED'])
        
        logger.debug(f"[RISK PROFILES] Profile: {profile_name} | "
                    f"min_conf={profile['min_confidence']} | "
                    f"target={profile['target_r_multiple']}R")
        
        return profile
    
    @classmethod
    def adjust_decision_by_profile(cls,
                                   decision: Dict[str, Any],
                                   market_conditions: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Ajusta decisão baseado no risk profile
        
        Args:
            decision: Decisão original
            market_conditions: Condições de mercado (Fear & Greed, etc)
            
        Returns:
            Decisão ajustada
        """
        profile_name = decision.get('risk_profile', 'BALANCED')
        profile = cls.get_profile(profile_name)
        
        # Valida confidence mínima
        confidence = decision.get('confidence', 0.0)
        min_conf = profile['min_confidence']
        
        if confidence < min_conf:
            # Converte para skip se não atender mínimo do perfil
            logger.warning(f"[RISK PROFILES] {decision.get('symbol')}: "
                          f"confidence {confidence:.2f} < {min_conf} para {profile_name}")
            
            decision['action'] = 'skip'
            decision['reason'] = f"Confidence insuficiente para perfil {profile_name}"
        
        # Valida stop loss
        stop_pct = decision.get('stop_loss_pct', 0.0)
        max_stop = profile['max_stop_pct']
        
        if stop_pct > max_stop:
            logger.warning(f"[RISK PROFILES] {decision.get('symbol')}: "
                          f"stop {stop_pct:.1f}% > {max_stop:.1f}% para {profile_name}")
            
            # Ajusta stop para o máximo permitido
            decision['stop_loss_pct'] = max_stop
            decision['reason'] += f" | Stop ajustado para {max_stop}%"
        
        # Ajusta parcial baseado no perfil
        if 'manage_decision' in decision:
            decision['manage_decision']['close_pct'] = profile['partial_pct']
        
        return decision
    
    @classmethod
    def recommend_profile(cls, market_intelligence: Dict[str, Any]) -> str:
        """
        Recomenda perfil baseado em Market Intelligence
        
        Args:
            market_intelligence: Dados de MI (Fear & Greed, etc)
            
        Returns:
            'AGGRESSIVE', 'BALANCED', 'CONSERVATIVE'
        """
        try:
            fear_greed = market_intelligence.get('fear_greed', {})
            fg_value = fear_greed.get('value', 50)
            fg_class = fear_greed.get('classification', 'Neutral')
            
            # Extreme Fear → CONSERVATIVE
            if fg_class == 'Extreme Fear' or fg_value < 20:
                return 'CONSERVATIVE'
            
            # Extreme Greed → CONSERVATIVE (topo?)
            if fg_class == 'Extreme Greed' or fg_value > 80:
                return 'CONSERVATIVE'
            
            # Fear → BALANCED
            if fg_class == 'Fear' or fg_value < 40:
                return 'BALANCED'
            
            # Greed → BALANCED
            if fg_class == 'Greed' or fg_value > 60:
                return 'BALANCED'
            
            # Neutral → pode ser AGGRESSIVE
            return 'BALANCED'
            
        except Exception as e:
            logger.error(f"[RISK PROFILES] Erro ao recomendar perfil: {e}")
            return 'BALANCED'
