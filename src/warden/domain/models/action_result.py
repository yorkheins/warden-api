from dataclasses import dataclass, field


@dataclass
class ActionResult:
    success: bool
    message: str
    details: dict = field(default_factory=dict)
