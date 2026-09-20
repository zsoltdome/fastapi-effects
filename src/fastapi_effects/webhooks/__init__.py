"""Tenant-safe webhook persistence and optional delivery integration.

Persistence models deliberately use base dependencies.  Modules that perform
encryption or network delivery validate the ``webhooks`` extra at their own
import boundary.
"""
