"""Canonical production authority for the public-only Forward Shadow service.

The public REST and websocket clients are constructed here.  Test doubles are
kept in the private helpers below and cannot be selected from the CLI.
"""
from __future__ import annotations

import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .binance_public import PUBLIC_FAPI
from .checkpoint import checkpoint_payload, load_checkpoint, write_checkpoint
from .core import ForwardResearchError, assert_shadow_only
from .frozen_declarations import load_forward_declaration_manifest, load_n5_plan
from .path_tracker import ShadowPathTracker
from .persistence import ForwardPersistence
from .pipeline import ForwardPipeline
from .runtime import ForwardRuntime
from .orchestrator import ForwardOrchestrator
from .service_runtime import build_service
from .universe import refresh_universe
from .bootstrap import fetch_completed_1h_candles, frozen_warmup_bars
from .daily_manifest import seal_daily_manifest, verify_daily_manifest


def current_git_commit(repo_root: str | Path = ".") -> str:
    value = subprocess.check_output(["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True).strip()
    if len(value) != 40:
        raise ForwardResearchError("forward_git_commit_invalid")
    return value


def _initialize_registry() -> None:
    """Use the same candidate registry population as formal research, once."""
    from quantbot.research.model_registry import _REGISTRY, register_existing_models, validate_registry
    from quantbot.strategies.model_pool import register_model_pool
    if not _REGISTRY:
        register_existing_models()
        register_model_pool()
    validate_registry()
    if len(_REGISTRY) != 36:
        raise ForwardResearchError("forward_canonical_registry_count_invalid")


def _public_json(url: str, session):
    if not url.startswith(PUBLIC_FAPI + "/fapi/v1/"):
        raise ForwardResearchError("forward_nonpublic_rest_endpoint_rejected")
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


class ForwardServiceAuthority:
    """One authority object binds all service lifecycle provenance."""
    def __init__(self, *, config_path, plan_path, declaration_path, data_root, checkpoint_path, repo_root=".", _session=None):
        assert_shadow_only()
        from .config import validate_config
        self.config_path, self.plan_path, self.declaration_path = config_path, plan_path, declaration_path
        self.config = validate_config(config_path)
        self.plan = load_n5_plan(plan_path)
        self.manifest = load_forward_declaration_manifest(declaration_path, self.plan)
        self.git_commit = current_git_commit(repo_root)
        if _session is None:
            import requests
            _session = requests.Session()
        self.data_root, self.checkpoint_path, self.session = Path(data_root), Path(checkpoint_path), _session
        _initialize_registry()
        self.runtime = ForwardRuntime()
        self.universe = None
        self.orchestrator = None
        self.pipeline = None
        self._active_date = None
        self._last_transitions = {'added': [], 'removed': [], 'surviving': []}
        self._transport = None
        self._shutdown = threading.Event()

    def refresh_universe(self, timestamp: str | None = None):
        assert_shadow_only()
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        exchange = _public_json(PUBLIC_FAPI + "/fapi/v1/exchangeInfo", self.session)
        tickers = _public_json(PUBLIC_FAPI + "/fapi/v1/ticker/24hr", self.session)
        date = timestamp[:10]
        # A snapshot is provenance, not a state-generation key.  Its identity
        # changes with timestamp/volume; its membership identity does not.
        snapshot = refresh_universe(exchange, tickers, timestamp)
        self._seal_prior_day(date)
        if self.orchestrator is None:
            persistence = ForwardPersistence(self.data_root, self.git_commit, self.config["config_identity"], snapshot["universe_identity"])
            self.orchestrator = ForwardOrchestrator(persistence, self.runtime, self.config["config_identity"], self.git_commit, snapshot["universe_identity"], ShadowPathTracker())
            self.pipeline = ForwardPipeline(orchestrator=self.orchestrator, plan=self.plan, declarations=self.manifest["declarations"])
            transitions={'added':sorted(row['symbol'] for row in snapshot['symbols']),'removed':[],'surviving':[]}
            self.orchestrator.persistence.bind_snapshot(snapshot)
        else:
            transitions=self.orchestrator.reconcile_membership(self.universe,snapshot)
        refresh_universe(exchange, tickers, timestamp, self.orchestrator.persistence, date)
        for symbol in transitions['added']:
            self._bootstrap_symbol(symbol,timestamp,date)
        self._last_transitions=transitions
        self.universe = snapshot
        return snapshot

    def _bootstrap_symbol(self, symbol, decision_time, date):
        count=frozen_warmup_bars(self.plan['models'])
        rows, provenance=fetch_completed_1h_candles(self.session,symbol=symbol,decision_time=decision_time,count=count)
        self.orchestrator.candles.seed_completed(symbol,'1h',rows)
        self.orchestrator.persistence.append('bootstrap',date,{**provenance,'interval':'1h','bootstrap_only':True})
        return provenance

    def _seal_prior_day(self, date):
        if self._active_date is not None and date != self._active_date:
            target=self.data_root/'manifests'/f'{self._active_date}.json'
            if target.exists():
                verify_daily_manifest(target)
            else:
                seal_daily_manifest(root=self.data_root,date=self._active_date,git_commit=self.git_commit,config_identity=self.config['config_identity'],research_plan_identity=self.plan['research_plan_identity'],declaration_manifest_identity=self.manifest['manifest_identity'])
        self._active_date=date

    def diagnostics(self):
        """Read-only service health; it never ranks, selects, or mutates models."""
        health=self.runtime.health();symbols=tuple(row['symbol'] for row in (self.universe or {}).get('symbols',()))
        counters=self.orchestrator.persistence.daily_counts(self._active_date) if self.orchestrator and self._active_date else {}
        health.update({'eligible_universe_size':len(symbols),'active_membership':symbols,'membership_transitions':self._last_transitions,'raw_event_candle_health':{'intrabar_records':counters.get('intrabar',0),'completed_candle_records':counters.get('candles',0)},'signal_counts':{'long_short_unclassified_records':counters.get('signals',0)},'open_path_observations':self.orchestrator.path_tracker.status()['open_observations'] if self.orchestrator else 0,'completed_path_observations':counters.get('paths',0),'opportunities':counters.get('opportunities',0),'shadow_portfolio_evidence':counters.get('portfolio',0),'diagnostics':counters.get('diagnostics',0),'daily_manifest_identity':None,'oos_allowed':False,'order_placement_allowed':False})
        if self._active_date:
            target=self.data_root/'manifests'/f'{self._active_date}.json'
            if target.exists():health['daily_manifest_identity']=verify_daily_manifest(target)['daily_manifest_identity']
        return health

    def resume(self):
        if not self.checkpoint_path.exists():
            return None
        return load_checkpoint(self.checkpoint_path, config_identity=self.config["config_identity"], git_commit=self.git_commit,
                               research_plan_identity=self.plan["research_plan_identity"], declaration_manifest_identity=self.manifest["manifest_identity"])

    def checkpoint(self):
        if self._transport is not None:
            self.runtime.transport_metrics = self._transport.health()
        payload = checkpoint_payload(self.runtime, self.config["config_identity"], self.git_commit,
                                     research_plan_identity=self.plan["research_plan_identity"], declaration_manifest_identity=self.manifest["manifest_identity"])
        write_checkpoint(self.checkpoint_path, payload)
        return payload

    def build_service(self):
        if self.universe is None:
            self.refresh_universe()
        service=build_service(config_path=self.config_path, symbols=[row["symbol"] for row in self.universe["symbols"]],
                             orchestrator=self.orchestrator, pipeline=self.pipeline, date_provider=lambda value: str(value)[:10])
        self._transport=service['transport'];return service

    def request_shutdown(self, *_):
        self._shutdown.set()

    def serve(self):
        """Explicit production mode.  Uses public websocket-client only."""
        self.resume()
        service = self.build_service()
        try:
            import websocket
        except ImportError as exc:
            raise ForwardResearchError("forward_websocket_dependency_missing") from exc
        signal.signal(signal.SIGINT, self.request_shutdown)
        signal.signal(signal.SIGTERM, self.request_shutdown)
        def connect(url):
            if not url.startswith("wss://fstream.binance.com/"):
                raise ForwardResearchError("forward_nonpublic_websocket_endpoint_rejected")
            return websocket.create_connection(url, timeout=30)
        # Transport owns reconnect/backoff.  Each shard runs independently;
        # only this supervisor owns checkpointing and universe membership.
        generation_stop = threading.Event()
        def should_stop(): return self._shutdown.is_set() or generation_stop.is_set()
        def stream_connection(url):
            ws = websocket.create_connection(url, timeout=30)
            def messages():
                try:
                    while not should_stop():
                        yield ws.recv()
                finally:
                    ws.close()
            return messages()
        workers = [threading.Thread(target=service["transport"].run_shard,
                                    args=(url, stream_connection, lambda: datetime.now(timezone.utc).isoformat(), should_stop),
                                    daemon=True, name=f"forward-public-{index}")
                   for index, url in enumerate(service["transport"].shard_urls())]
        for worker in workers: worker.start()
        refresh_seconds = max(1, int(self.config.get("universe_refresh_seconds", 300)))
        checkpoint_seconds = max(1, int(self.config.get("snapshot_seconds", 60)))
        last_refresh = last_checkpoint = time.monotonic()
        while not self._shutdown.wait(1):
            now = time.monotonic()
            if now - last_checkpoint >= checkpoint_seconds:
                self.checkpoint(); last_checkpoint = now
            if now - last_refresh >= refresh_seconds:
                previous = self.universe["membership_identity"]
                self.refresh_universe()
                last_refresh = now
                if self.universe["membership_identity"] != previous:
                    generation_stop.set()
                    break
        generation_stop.set()
        for worker in workers: worker.join(timeout=35)
        if not service['transport'].close(timeout=30):
            raise ForwardResearchError('forward_transport_drain_timeout')
        self.checkpoint()
        # A changed membership gets a fresh transport generation, while the
        # coordinator retains surviving-symbol state and preserves evidence.
        if not self._shutdown.is_set():
            return self.serve()


def build_production_authority(*, config_path, plan_path, declaration_path, data_root, checkpoint_path, repo_root="."):
    """Public constructor used only by the explicit --serve CLI authority mode."""
    return ForwardServiceAuthority(config_path=config_path, plan_path=plan_path, declaration_path=declaration_path,
                                   data_root=data_root, checkpoint_path=checkpoint_path, repo_root=repo_root)


def _build_authority_for_test(**kwargs):
    """Private synthetic-test seam; the CLI never exposes this dependency."""
    return ForwardServiceAuthority(**kwargs)
