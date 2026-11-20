from dataclasses import dataclass, field


@dataclass
class Settings:
    api_prefix: str = "quartz"
    restrict_register: bool = True
    lenient_ui: bool = True
    record_missing: bool = True
    strict_layout: bool = False
    invoke_in_background: bool = False
    sweep_mode: bool = False
    trust_scripts: bool = False
    undo_steps: int = 32


settings: Settings = Settings()


def reset() -> None:
    defaults = Settings()
    for k, v in defaults.__dict__.items():
        setattr(settings, k, v)


def snapshot() -> dict:
    return dict(settings.__dict__)


def restore(snap: dict) -> None:
    for k, v in snap.items():
        setattr(settings, k, v)
