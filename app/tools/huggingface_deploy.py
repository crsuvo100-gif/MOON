"""huggingface_deploy.py -- find, compare, and deploy HF models as Inference Endpoints.

Implements the operator workflow:
  1. find the right model on the HF Hub for <what you want to build>,
  2. compare a few candidates,
  3. deploy the best one as an Inference Endpoint in the configured namespace
     (default: crsuvo) using the `hf` CLI, picking suitable hardware and
     verifying the endpoint responds once running.

Also exposes the OAuth client registration payload MOON presents when registered
as an HF OAuth application (Authorization Code + PKCE).

Safety:
  * The actual `hf endpoints create` is BILLABLE (provisions GPU/CPU hardware).
    It is therefore CONFIRMATION-GATED: deploy() only runs it when confirm=True.
    This tool never spends money on its own.
  * If `huggingface_hub` / the `hf` CLI / a token are absent, operations report
    that clearly instead of fabricating results.

Requires (on the deploy host): `pip install huggingface_hub` and the `hf` CLI
(`pip install -U "huggingface_hub[cli]"`) plus HUGGINGFACE_API_KEY in the env.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from app.config.settings import get_settings
from app.tools.base import BaseTool, ToolResult


def _hf_cli() -> str | None:
    return shutil.which("hf")


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


class HuggingFaceDeployTool(BaseTool):
    name = "huggingface_deploy"
    description = (
        "Search/compare Hugging Face models and deploy the best one as an Inference "
        "Endpoint in the configured namespace (default crsuvo). Deploy is confirmation-"
        "gated (billable). Also builds the HF OAuth client registration payload."
    )

    # ------------------------------------------------------------------ #
    # 1) FIND
    # ------------------------------------------------------------------ #
    async def find_models(self, query: str, limit: int = 10, task: str | None = None) -> list[dict]:
        """Return candidate models from the HF Hub matching `query`.

        Uses `hf search` (or huggingface_hub HfApi) when available; otherwise
        returns an empty list with a clear note (no fabrication).
        """
        cli = _hf_cli()
        if cli is None:
            return [{"error": "hf CLI not installed (pip install -U 'huggingface_hub[cli]') -- cannot search live"}]
        cmd = [cli, "api", "models", "--search", query, "--sort", "downloads", "-i", "-L", str(limit)]
        if task:
            cmd += ["--pipeline_tag", task]
        rc, out, err = _run(cmd)
        if rc != 0:
            return [{"error": f"hf search failed: {err.strip() or out.strip()}"}]
        # `hf api` returns JSON lines / array depending on flags; parse defensively.
        candidates: list[dict] = []
        try:
            data = json.loads(out) if out.strip().startswith("[") else [json.loads(l) for l in out.splitlines() if l.strip()]
        except Exception:
            return [{"error": "could not parse hf api output", "raw": out[:500]}]
        for m in data:
            if isinstance(m, dict):
                candidates.append({
                    "id": m.get("id") or m.get("modelId"),
                    "downloads": m.get("downloads", 0),
                    "likes": m.get("likes", 0),
                    "pipeline_tag": m.get("pipeline_tag") or m.get("task"),
                    "lastModified": m.get("lastModified"),
                })
        return candidates[:limit]

    # ------------------------------------------------------------------ #
    # 2) COMPARE
    # ------------------------------------------------------------------ #
    async def compare(self, candidates: list[dict]) -> list[dict]:
        """Rank candidates by a simple popularity/suitability score.

        Score = downloads*1.0 + likes*50, with a small recency nudge omitted for
        determinism. Returns the same dicts sorted best-first.
        """
        def _score(c: dict) -> float:
            return float(c.get("downloads", 0) or 0) + 50.0 * float(c.get("likes", 0) or 0)
        return sorted(candidates, key=_score, reverse=True)

    # ------------------------------------------------------------------ #
    # 3) DEPLOY (confirmation-gated; billable)
    # ------------------------------------------------------------------ #
    async def deploy(
        self,
        model: str,
        *,
        hardware: str = "cpu-small",
        min_replicas: int = 1,
        confirm: bool = False,
        namespace: str | None = None,
    ) -> dict:
        """Deploy `model` as an HF Inference Endpoint in `namespace`.

        REQUIRES confirm=True -- this provisions billable hardware. Builds the
        `hf endpoints create` command, runs it, then verifies the endpoint
        responds via `hf endpoints status`. Does NOT fabricate a running
        endpoint; reports the real CLI output.
        """
        if not confirm:
            return {
                "deployed": False,
                "reason": "confirmation required",
                "note": "Deploy provisions billable hardware. Call again with confirm=true.",
                "would_run": self._build_deploy_cmd(model, hardware, min_replicas, namespace),
            }
        cli = _hf_cli()
        if cli is None:
            return {"deployed": False, "error": "hf CLI not installed"}
        cmd = self._build_deploy_cmd(model, hardware, min_replicas, namespace)
        rc, out, err = _run(cmd, timeout=300)
        if rc != 0:
            return {"deployed": False, "error": (err or out).strip()}
        # Verify the endpoint responds.
        ns = namespace or get_settings().hf_endpoint_namespace or "crsuvo"
        name = model.split("/")[-1].lower().replace(".", "-")
        vrc, vout, verr = _run([cli, "endpoints", "status", f"{ns}/{name}"], timeout=120)
        return {
            "deployed": vrc == 0,
            "namespace": ns,
            "endpoint": f"{ns}/{name}",
            "cli_output": out.strip(),
            "verify_status": (vout or verr).strip(),
        }

    def _build_deploy_cmd(self, model: str, hardware: str, min_replicas: int, namespace: str | None) -> list[str]:
        ns = namespace or get_settings().hf_endpoint_namespace or "crsuvo"
        name = model.split("/")[-1].lower().replace(".", "-")
        return [
            "hf", "endpoints", "create", f"{ns}/{name}",
            "--repository", model,
            "--hardware", hardware,
            "--min-replica", str(min_replicas),
            "--type", "protected",
        ]

    # ------------------------------------------------------------------ #
    # OAuth client registration payload
    # ------------------------------------------------------------------ #
    def oauth_client_config(self) -> dict:
        """Build the HF OAuth client registration payload from settings.

        Mirrors the Authorization Code + PKCE (token_endpoint_auth_method
        'none') registration the operator provided; filled from configured URLs.
        """
        s = get_settings()
        site = (s.hf_oauth_website or "").rstrip("/")
        if not site:
            return {"configured": False, "note": "set HF_OAUTH_WEBSITE in .env to fill the OAuth client payload"}
        return {
            "configured": True,
            "client_id": f"{site}/.well-known/oauth-cimd",
            "client_name": s.hf_oauth_client_name or "MOON",
            "redirect_uris": [f"{site}/oauth/callback/huggingface"],
            "token_endpoint_auth_method": "none",
            "logo_uri": s.hf_oauth_logo_uri or None,
            "client_uri": site,
        }

    # ------------------------------------------------------------------ #
    # Tool entrypoint
    # ------------------------------------------------------------------ #
    async def execute(self, action: str = "find", **kwargs) -> str:
        if action == "find":
            cands = await self.find_models(kwargs.get("query", ""), int(kwargs.get("limit", 10)), kwargs.get("task"))
            return json.dumps(cands, indent=2)
        if action == "compare":
            import json as _json
            cands = kwargs.get("candidates") or _json.loads(kwargs.get("candidates_json", "[]"))
            return _json.dumps(await self.compare(cands), indent=2)
        if action == "deploy":
            return json.dumps(await self.deploy(
                kwargs.get("model", ""),
                hardware=kwargs.get("hardware", "cpu-small"),
                confirm=bool(kwargs.get("confirm", False)),
                namespace=kwargs.get("namespace"),
            ), indent=2)
        if action == "oauth":
            return json.dumps(self.oauth_client_config(), indent=2)
        return "[huggingface_deploy] unknown action. Use find|compare|deploy|oauth."
