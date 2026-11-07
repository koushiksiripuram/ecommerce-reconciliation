"""Backend reconciliation engine.

Matches orders against marketplace settlements and COD remittances, compares
expected against received amounts with exact decimal arithmetic, and records the
outcome (plus any detected problems) as :class:`~app.models.ReconciliationResult`
rows. Nothing here talks HTTP; the API layer wraps :mod:`app.reconciliation.service`.
"""
