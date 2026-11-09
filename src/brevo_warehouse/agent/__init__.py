"""Question assistant over the warehouse (programme block 6), rules only, read-only.

    from brevo_warehouse.agent import ask
    print(ask("Combien de campagnes locales ?").answer)
"""
from .agent import AgentResult, ask
from .guard import GuardError, check_sql
from .parser import NotUnderstood, parse

__all__ = ["ask", "AgentResult", "check_sql", "GuardError", "parse", "NotUnderstood"]
