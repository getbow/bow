
from bow.core.resources import (
    Resources, 
    Probe
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def full_image(values: dict) -> str:

    registry = values.get("registry", "")
    repo = values.get("repository", "")
    tag = values.get("tag", "latest")

    if registry:
        return f"{registry}/{repo}:{tag}"
    
    return f"{repo}:{tag}"


def apply_resources(res: dict | None) -> None:    
    if not res:
        return
    req = res.get("requests", {})
    lim = res.get("limits", {})
    if req or lim:
        Resources(
            cpu=req.get("cpu"),
            memory=req.get("memory"),
            limits_cpu=lim.get("cpu"),
            limits_memory=lim.get("memory"),
        )


def apply_probe(probe_type: str, exec_command: list[str], cfg: dict) -> None:
    if not cfg.get("enabled", True):
        return
    Probe(
        probe_type,
        exec_command=exec_command,
        initial_delay=cfg.get("initialDelaySeconds", 20),
        period=cfg.get("periodSeconds", 5),
        timeout=cfg.get("timeoutSeconds", 5),
        failure_threshold=cfg.get("failureThreshold", 5),
    )
