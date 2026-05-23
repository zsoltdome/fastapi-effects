"""Shared test configuration.

Mutable process-global state is forbidden. Each asynchronous test receives its own
loop scope through pytest-asyncio configuration.
"""
