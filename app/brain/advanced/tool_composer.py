"""Tool composition and chaining for agent cognition.

Enables the agent to compose multiple tools into chains, where the output
of one tool feeds into the input of the next. Supports parallel branches,
conditional routing, and result aggregation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

from app.config.logging import get_logger

logger = get_logger(__name__)


class ChainNodeType(str, Enum):
    TOOL = "tool"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    AGGREGATE = "aggregate"


@dataclass
class ToolChain:
    """A composed chain of tool calls."""
    name: str
    nodes: list[dict[str, Any]]  # Each node: {type, tool, args, condition, branches}
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolChainResult:
    """Result of executing a tool chain."""
    chain_name: str
    success: bool
    results: list[dict[str, Any]]
    final_output: str
    execution_time: float
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolComposer:
    """Composes and executes tool chains.

    Supports sequential chains, parallel branches, conditional routing,
    and result aggregation patterns.
    """

    def __init__(self, *, tool_executor: Callable[[str, dict[str, Any]], Awaitable[str]] | None = None) -> None:
        self._tool_executor = tool_executor
        self._chains: dict[str, ToolChain] = {}

    def register_chain(self, chain: ToolChain) -> None:
        """Register a tool chain for later execution."""
        self._chains[chain.name] = chain

    async def execute_chain(
        self,
        chain: ToolChain | str,
        *,
        initial_args: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ToolChainResult:
        """Execute a tool chain.

        Args:
            chain: A ToolChain object or registered chain name.
            initial_args: Initial arguments for the first tool.
            context: Shared context across all tools in the chain.

        Returns:
            ToolChainResult with all intermediate results.
        """
        if isinstance(chain, str):
            chain = self._chains.get(chain)
            if chain is None:
                return ToolChainResult(
                    chain_name="unknown",
                    success=False,
                    results=[],
                    final_output=f"Chain '{chain}' not found",
                    execution_time=0.0,
                )

        start_time = asyncio.get_event_loop().time()
        results: list[dict[str, Any]] = []
        shared_context = dict(context or {})
        shared_context.update(initial_args or {})
        last_output = ""

        for i, node in enumerate(chain.nodes):
            node_type = ChainNodeType(node.get("type", "tool"))

            if node_type == ChainNodeType.TOOL:
                tool_name = node.get("tool", "")
                tool_args = self._resolve_args(node.get("args", {}), shared_context, last_output)
                try:
                    output = await self._execute_tool(tool_name, tool_args)
                    results.append({
                        "node": i,
                        "type": "tool",
                        "tool": tool_name,
                        "args": tool_args,
                        "output": output,
                        "success": True,
                    })
                    last_output = output
                    shared_context[f"step_{i}"] = output
                except Exception as exc:
                    results.append({
                        "node": i,
                        "type": "tool",
                        "tool": tool_name,
                        "error": str(exc),
                        "success": False,
                    })
                    if not node.get("continue_on_error", False):
                        break

            elif node_type == ChainNodeType.PARALLEL:
                branches = node.get("branches", [])
                branch_results = await asyncio.gather(*[
                    self._execute_branch(branch, shared_context, last_output)
                    for branch in branches
                ])
                results.append({
                    "node": i,
                    "type": "parallel",
                    "branches": branch_results,
                    "success": all(r.get("success", False) for r in branch_results),
                })
                # Merge outputs
                for r in branch_results:
                    if r.get("output"):
                        last_output += f"\n{r['output']}"

            elif node_type == ChainNodeType.CONDITIONAL:
                condition = node.get("condition", "")
                if self._evaluate_condition(condition, shared_context, last_output):
                    branch = node.get("then_branch", {})
                    branch_result = await self._execute_branch(branch, shared_context, last_output)
                else:
                    branch = node.get("else_branch", {})
                    branch_result = await self._execute_branch(branch, shared_context, last_output)
                results.append({
                    "node": i,
                    "type": "conditional",
                    "condition": condition,
                    "result": branch_result,
                    "success": branch_result.get("success", False),
                })

            elif node_type == ChainNodeType.AGGREGATE:
                strategy = node.get("strategy", "concat")
                outputs = [r.get("output", "") for r in results if r.get("output")]
                if strategy == "concat":
                    last_output = "\n".join(outputs)
                elif strategy == "last":
                    last_output = outputs[-1] if outputs else ""
                elif strategy == "summary":
                    last_output = f"Aggregated {len(outputs)} results"
                results.append({
                    "node": i,
                    "type": "aggregate",
                    "strategy": strategy,
                    "output": last_output,
                    "success": True,
                })

        execution_time = asyncio.get_event_loop().time() - start_time
        success = all(r.get("success", True) for r in results)

        return ToolChainResult(
            chain_name=chain.name,
            success=success,
            results=results,
            final_output=last_output,
            execution_time=execution_time,
            metadata={"nodes_executed": len(results)},
        )

    async def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        """Execute a single tool."""
        if self._tool_executor:
            return await self._tool_executor(tool_name, args)
        return f"[no executor for {tool_name}]"

    async def _execute_branch(
        self,
        branch: dict[str, Any],
        context: dict[str, Any],
        last_output: str,
    ) -> dict[str, Any]:
        """Execute a branch (sub-chain or single tool)."""
        if "nodes" in branch:
            # Sub-chain
            sub_chain = ToolChain(name="sub", nodes=branch["nodes"])
            result = await self.execute_chain(sub_chain, context=context)
            return {"success": result.success, "output": result.final_output}
        else:
            # Single tool
            tool_name = branch.get("tool", "")
            args = self._resolve_args(branch.get("args", {}), context, last_output)
            try:
                output = await self._execute_tool(tool_name, args)
                return {"success": True, "output": output, "tool": tool_name}
            except Exception as exc:
                return {"success": False, "error": str(exc), "tool": tool_name}

    def _resolve_args(
        self,
        args: dict[str, Any],
        context: dict[str, Any],
        last_output: str,
    ) -> dict[str, Any]:
        """Resolve argument templates using context and last output."""
        resolved = {}
        for key, value in args.items():
            if isinstance(value, str):
                # Replace {{context.key}} and {{last_output}}
                resolved[key] = value.replace("{{last_output}}", last_output)
                for ctx_key, ctx_val in context.items():
                    resolved[key] = resolved[key].replace(
                        f"{{{{context.{ctx_key}}}}}", str(ctx_val)
                    )
            else:
                resolved[key] = value
        return resolved

    def _evaluate_condition(self, condition: str, context: dict[str, Any], last_output: str) -> bool:
        """Evaluate a simple condition string."""
        # Simple conditions: "output contains X", "context.key == value"
        condition = condition.strip()
        if "contains" in condition:
            parts = condition.split("contains")
            left = parts[0].strip().strip("'\"")
            right = parts[1].strip().strip("'\"")
            left_val = context.get(left, last_output)
            return right in str(left_val)
        if "==" in condition:
            parts = condition.split("==")
            left = parts[0].strip().strip("'\"")
            right = parts[1].strip().strip("'\"")
            return str(context.get(left, "")) == right
        return bool(condition)
