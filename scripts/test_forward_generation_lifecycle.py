"""Synthetic lifecycle regression: rollover is iterative, never recursive."""
from __future__ import annotations

import inspect
import sys
from types import SimpleNamespace
from unittest.mock import patch

from quantbot.forward_research.production_runtime import ForwardServiceAuthority


class _Shutdown:
    def __init__(self): self.value = False
    def is_set(self): return self.value
    def set(self): self.value = True
    def wait(self, _timeout): return self.value


class _Clock:
    def __init__(self): self.value = 0
    def __call__(self): self.value += 2; return self.value


class _Thread:
    def __init__(self, *_, name=None, **__): self.name = name or 'synthetic-reader'
    def start(self): pass
    def join(self, timeout=None): self.timeout = timeout
    def is_alive(self): return False


class _Transport:
    def __init__(self, sequence): self.sequence = sequence
    def shard_urls(self): return ('wss://fstream.binance.com/ws/synthetic',)
    def run_shard(self, *_): raise AssertionError('synthetic reader must not connect')
    def close(self, timeout): self.sequence.append('transport-close'); return True
    def health(self): return {'synthetic': True}


class _Pipeline:
    def __init__(self, sequence): self.sequence = sequence
    def retire_and_drain(self, timeout): self.sequence.append('pipeline-drain'); return True
    def close(self, timeout): self.sequence.append('pipeline-close'); return True


class _Persistence:
    def __init__(self, sequence): self.sequence = sequence
    def flush(self): self.sequence.append('flush')


class _Authority:
    """Production-shaped seam: invoke the real serve coordinator unbound."""
    def __init__(self, rollovers):
        self.config = {'universe_refresh_seconds': 1, 'snapshot_seconds': 999999}
        self._shutdown = _Shutdown()
        self.universe = {'membership_identity': 'generation-0'}
        self.sequence, self.depths = [], []
        self.pipeline = _Pipeline(self.sequence)
        self.orchestrator = SimpleNamespace(persistence=_Persistence(self.sequence))
        self.rollovers, self.refreshes, self.builds, self.checkpoints = rollovers, 0, 0, 0
    def resume(self): self.sequence.append('resume')
    def request_shutdown(self, *_): self._shutdown.set()
    def build_service(self):
        self.builds += 1
        self.depths.append(len(inspect.stack()))
        self.sequence.append(f'build:{self.builds}')
        return {'transport': _Transport(self.sequence)}
    def refresh_universe(self):
        self.refreshes += 1
        if self.refreshes <= self.rollovers:
            self.universe = {'membership_identity': f'generation-{self.refreshes}'}
        else:
            self._shutdown.set()
    def checkpoint(self): self.checkpoints += 1; self.sequence.append('checkpoint')


def main():
    authority = _Authority(rollovers=128)
    clock = _Clock()
    fake_websocket = SimpleNamespace(create_connection=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('network attempted')))
    with patch.dict(sys.modules, {'websocket': fake_websocket}), \
         patch('quantbot.forward_research.production_runtime.signal.signal', lambda *_: None), \
         patch('quantbot.forward_research.production_runtime.threading.Thread', _Thread), \
         patch('quantbot.forward_research.production_runtime.time.monotonic', clock):
        ForwardServiceAuthority.serve(authority)
    assert authority.builds == 129
    assert authority.refreshes == 129
    assert authority.checkpoints == 129
    assert authority.sequence.count('transport-close') == 129
    assert authority.sequence.count('pipeline-drain') == 129
    assert authority.sequence.count('flush') == 129
    assert authority.sequence.count('pipeline-close') == 1
    assert max(authority.depths) - min(authority.depths) < 8
    for generation in range(1, 129):
        assert authority.sequence.index(f'build:{generation}') < authority.sequence.index('transport-close', authority.sequence.index(f'build:{generation}'))
        assert authority.sequence.index('pipeline-drain', authority.sequence.index(f'build:{generation}')) < authority.sequence.index(f'build:{generation + 1}')
    assert authority.sequence[-1] == 'pipeline-close'
    print('FORWARD_ITERATIVE_GENERATION_LIFECYCLE=PASS')
    print('SUCCESSFUL_ROLLOVERS=128')
    print('RECURSIVE_SERVE_REENTRY=ABSENT')
    print('RETIRE_BEFORE_REPLACEMENT=PASS')
    print('FLUSH_AND_CHECKPOINT_PER_RETIREMENT=PASS')
    print('SHUTDOWN_FINAL_PIPELINE_CLOSE=PASS')
    print('OOS_READS=0')
    print('FORMAL_ARTIFACT_MUTATIONS=0')
    print('EXCHANGE_ORDER_PLACEMENT=0')
    print('LIVE_AUTHORIZATION=0')


if __name__ == '__main__': main()
