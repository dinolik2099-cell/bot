"""Versioned forward universe-to-shard reconciliation without historical deletion."""
from __future__ import annotations
from .collector import shard_symbols
from .core import identity
def reconcile_universe(previous,current,max_per_shard=200):
 before={row['symbol'] for row in previous.get('symbols',[])} if previous else set();after={row['symbol'] for row in current['symbols']};data={'schema_version':'quantbot-forward-universe-reconcile-v1','previous_universe_identity':previous.get('universe_identity') if previous else None,'universe_identity':current['universe_identity'],'subscribe':sorted(after-before),'unsubscribe':sorted(before-after),'active_symbols':sorted(after),'shards':[list(row) for row in shard_symbols(after,max_per_shard)],'historical_observations_deleted':False};data['reconcile_identity']=identity(data);return data
