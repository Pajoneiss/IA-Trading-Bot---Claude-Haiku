"""
Phase 7 - IA Coach
Gera insights em linguagem humana baseado em performance
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class IACoach:
    """Coach inteligente que analisa performance e dá insights"""
    
    def __init__(self, performance_engine, logger_instance=None):
        self.perf_engine = performance_engine
        self.logger = logger_instance or logger
    
    def generate_insights(self) -> Optional[str]:
        """
        Gera insights em português baseado em métricas reais
        
        Returns:
            Texto com insights ou None se sem dados
        """
        try:
            # Pega estatísticas
            weekly = self.perf_engine.get_weekly_summary()
            best_worst = self.perf_engine.get_best_worst_pairs(limit=2)
            
            if 'error' in weekly and not best_worst.get('best'):
                return None
            
            msg = "🧠 IA COACH - INSIGHTS\n"
            msg += "=" * 30 + "\n\n"
            
            # Análise geral
            if 'error' not in weekly:
                wr = weekly.get('win_rate', 0)
                trades = weekly.get('trades', 0)
                
                msg += f"📊 Última Semana:\n"
                msg += f"   {trades} trades | Win Rate {wr:.1f}%\n\n"
                
                # Avaliação de performance
                if wr >= 60:
                    msg += "✅ Excelente desempenho! Continue focando nas estratégias que estão funcionando.\n\n"
                elif wr >= 50:
                    msg += "⚖️ Performance equilibrada. Há espaço para melhorar a seletividade.\n\n"
                else:
                    msg += "⚠️ Performance abaixo do ideal. Considere:\n"
                    msg += "   • Ser mais seletivo nos setups\n"
                    msg += "   • Revisar stop loss e take profit\n"
                    msg += "   • Focar nos pares que estão funcionando\n\n"
            
            # Melhores pares
            if best_worst.get('best'):
                msg += "🏆 SEUS PONTOS FORTES:\n"
                for sym, stats in best_worst['best'][:2]:
                    wr = stats.get('win_rate', 0)
                    exp = stats.get('expectancy', 0)
                    msg += f"   • {sym}: WR {wr:.1f}% | Exp {exp:+.2f}%\n"
                    
                    if exp > 1.0:
                        msg += f"     → Continue priorizando setups em {sym}\n"
                
                msg += "\n"
            
            # Piores pares
            if best_worst.get('worst'):
                msg += "⚠️ ÁREAS PARA MELHORAR:\n"
                for sym, stats in best_worst['worst'][:2]:
                    wr = stats.get('win_rate', 0)
                    exp = stats.get('expectancy', 0)
                    msg += f"   • {sym}: WR {wr:.1f}% | Exp {exp:+.2f}%\n"
                    
                    if exp < -0.5:
                        msg += f"     → Reduza exposição em {sym} ou aguarde melhor contexto\n"
                
                msg += "\n"
            
            # Recomendações gerais
            msg += "💡 RECOMENDAÇÕES:\n"
            msg += "   • Mantenha o foco nos ativos com melhor performance\n"
            msg += "   • Seja paciente e aguarde setups de alta qualidade\n"
            msg += "   • Respeite sempre seus stop loss\n"
            msg += "   • Revise este relatório semanalmente\n"
            
            return msg
            
        except Exception as e:
            self.logger.error(f"[COACH] Erro ao gerar insights: {e}")
            return None
