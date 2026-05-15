"""``apps.api.backends`` — adapter and shared-contract package marker.

Empty package marker. Submodules to import directly:

    - ``apps.api.backends.chunks``        ChatChunk Pydantic union
    - ``apps.api.backends.protocol``      BackendAdapter Protocol
    - ``apps.api.backends.cost``          CostTracker base class
    - ``apps.api.backends.pricing``       PricingTable
    - ``apps.api.backends.keystore``      KeyStore
    - ``apps.api.backends.logging_filter`` RedactionFilter

Wave 1 plans add ``apps.api.backends.openrouter``,
``apps.api.backends.claude_code``, ``apps.api.backends.computer_use``.
"""
