"""Import pipeline.

The package is deliberately split so each concern can be understood and tested
on its own:

``errors``
    Failures raised by the pipeline, each mapping to one HTTP status.
``fields``
    The canonical-field registry: which fields exist and which are required for
    each source type. Knows nothing about files or HTTP.
``parser``
    Turns the bytes of a CSV/XLSX file into headers plus string rows. Knows
    nothing about canonical fields.
``mapping``
    Suggests and validates the translation from a partner's headers to
    canonical fields. Works on header names only, never on file bytes.
``normalizer``
    Converts and validates a single row's values (amounts, dates, text).
``service``
    Orchestrates the above against the database: storage, de-duplication,
    preview, mapping and processing.

Submodules are intentionally *not* re-exported here: callers import the module
they need, which keeps the dependency direction obvious.
"""
