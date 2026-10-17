"""App wiring: constructs every component once and hands them to the daemon / CLI."""

from __future__ import annotations

from .archive import TranscriptArchive
from .briefing import Briefer
from .config import Config, load_config
from .creative_output import CreativeOutput
from .daily_journal import JournalRouter
from .dream_journal import DreamRouter
from .edits import ActionLedger
from .glossary import Glossary
from .llm import OllamaClient
from .notes import NoteWriter
from .patterns import Patterns
from .vault_ops import Organizer
from .query import QueryEngine
from .relay import Relay
from .settings_sync import VaultSettings
from .stats_generator import StatsGenerator
from .stt import WhisperSTT
from .vault import Vault


class App:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        for d in (cfg.state_dir(), cfg.spool_dir(), cfg.models_dir()):
            d.mkdir(parents=True, exist_ok=True)

        self.vault = Vault(cfg)
        self.llm = OllamaClient(cfg)
        self.stt = WhisperSTT(cfg)
        self.ledger = ActionLedger(cfg, self.vault)
        self.archive = TranscriptArchive(cfg)
        self.glossary = Glossary(cfg, self.vault)

        self.dream = DreamRouter(cfg, self.vault, self.llm, self.ledger)
        self.journal = JournalRouter(cfg, self.vault, self.llm, self.ledger)
        self.notes = NoteWriter(cfg, self.vault, self.llm, self.ledger)
        self.query = QueryEngine(cfg, self.vault, self.llm, self.archive)
        self.organizer = Organizer(cfg, self.vault, self.llm, self.ledger)
        self.creative = CreativeOutput(cfg, self.vault, self.llm)
        self.stats = StatsGenerator(cfg, self.vault, self.llm, self.ledger)
        self.briefer = Briefer(cfg, self.vault, self.llm, self.archive)
        self.relay = Relay(cfg)
        self.settings_sync = VaultSettings(cfg, self.vault)
        self.patterns = Patterns(cfg, self.vault)
        self.patterns.ensure_file()  # never raises; degrades to built-ins if the vault layout fights us


def build_app(cfg: Config | None = None) -> App:
    return App(cfg or load_config())
