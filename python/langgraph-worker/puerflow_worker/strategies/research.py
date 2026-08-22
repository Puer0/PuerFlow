from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient, LLMResponse
from puerflow_worker.runtime import TaskState
from puerflow_worker.budget import raise_if_cancelled, raise_if_over_budget
from puerflow_worker.tools import complete_turn
from puerflow_worker.tools.registry import ToolRegistry

try:
    from langgraph.graph import END, StateGraph
except Exception:  # noqa: BLE001
    END = None
    StateGraph = None

EmitFn = Callable[[ShannonEvent], Awaitable[None]]
_TOKEN = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")


def tokenize(text: str) -> set[str]:
    return {item.lower() for item in _TOKEN.findall(text or "")}


def claim_support_score(claim: str, evidence: str) -> float:
    claim_tokens = tokenize(claim)
    evidence_tokens = tokenize(evidence)
    if not claim_tokens or not evidence_tokens:
        return 0.0
    overlap = len(claim_tokens & evidence_tokens)
    return overlap / max(len(claim_tokens), 1)


def weakest_claims(claims: list[str], evidence: str, limit: int = 2) -> list[str]:
    ranked = sorted(((claim_support_score(claim, evidence), claim) for claim in claims), key=lambda item: item[0])
    return [claim for score, claim in ranked[:limit] if score < 0.35]


class ResearchStrategy:
    """Plan, gather evidence, verify claims, fill gaps, then write a cited draft."""

    name = "research"

    def __init__(self, llm: CompletionClient, tools: ToolRegistry | None = None):
        self.llm = llm
        self.tools = tools
        self._graph = self._build_graph()

    async def run(self, state: TaskState, emit: EmitFn) -> LLMResponse:
        if self.tools is not None:
            allowed = [tool.metadata.name for tool in self.tools.list_tools() if tool.metadata.name != "python_executor"]
            if state.tools:
                allowed = [name for name in state.tools if name != "python_executor"]
            state.tools = allowed
        graph_state: dict[str, Any] = {
            "task": state,
            "emit": emit,
            "plan": "",
            "evidence": "",
            "claims": [],
            "gaps": [],
            "response": None,
        }
        if self._graph is not None:
            graph_state = await self._graph.ainvoke(graph_state)
        else:
            for node in (self.start, self.investigate, self.verify, self.fill_gaps, self.synthesize):
                graph_state = await node(graph_state)
        return graph_state["response"]

    async def start(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="WORKFLOW_STARTED",
                agent_id="research",
                message="Research workflow started",
            )
        )
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        from puerflow_worker.strategies.memory import memory_messages

        messages = [
            {"role": "system", "content": "Outline 3-5 search questions for this research task. Return one question per line."},
        ]
        messages.extend(memory_messages(task))
        messages.append({"role": "user", "content": task.query})
        plan = await complete_turn(self.llm, None, task, emit, messages)
        state["plan"] = plan.content
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="RESEARCH_PLAN_READY",
                agent_id="research",
                message=plan.content[:500],
            )
        )
        return state

    async def investigate(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        evidence = await complete_turn(
            self.llm,
            self.tools,
            task,
            state["emit"],
            [
                {"role": "system", "content": "Collect structured evidence with source hints. Prefer facts over opinions."},
                {"role": "user", "content": f"Query: {task.query}\nPlan:\n{state['plan']}"},
            ],
        )
        state["evidence"] = evidence.content
        await state["emit"](
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="AGENT_COMPLETED",
                agent_id="research-agent",
                message=evidence.content[:500],
            )
        )
        return state

    async def verify(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        extracted = await complete_turn(
            self.llm,
            None,
            task,
            state["emit"],
            [
                {"role": "system", "content": "Extract 3-6 atomic claims from the evidence. One claim per line."},
                {"role": "user", "content": state["evidence"]},
            ],
        )
        claims = [line.strip("- ").strip() for line in extracted.content.splitlines() if line.strip()]
        state["claims"] = claims
        state["gaps"] = weakest_claims(claims, state["evidence"])
        return state

    async def fill_gaps(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        gaps = state.get("gaps") or []
        if not gaps:
            return state
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        extra = await complete_turn(
            self.llm,
            self.tools,
            task,
            state["emit"],
            [
                {"role": "system", "content": "Fill unsupported claims with additional evidence or mark them uncertain."},
                {"role": "user", "content": "Weak claims:\n" + "\n".join(gaps)},
            ],
        )
        state["evidence"] = f"{state['evidence']}\n\nGap fill:\n{extra.content}"
        return state

    async def synthesize(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        response = await complete_turn(
            self.llm,
            self.tools,
            task,
            emit,
            [
                {
                    "role": "system",
                    "content": "Write a careful research answer with caveats and inline source hints from the evidence.",
                },
                {
                    "role": "user",
                    "content": f"Query: {task.query}\nPlan:\n{state['plan']}\nEvidence:\n{state['evidence']}\nClaims:\n"
                    + "\n".join(state.get("claims") or []),
                },
            ],
        )
        raise_if_cancelled(task)
        state["response"] = response
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="LLM_OUTPUT",
                agent_id="final_output",
                message=response.content,
                payload={"text": response.content, "usage": response.usage.as_dict()},
            )
        )
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="WORKFLOW_COMPLETED",
                agent_id="research",
                message="Research workflow completed",
            )
        )
        return state

    def _build_graph(self):
        if StateGraph is None:
            return None
        graph = StateGraph(dict)
        graph.add_node("start", self.start)
        graph.add_node("investigate", self.investigate)
        graph.add_node("verify", self.verify)
        graph.add_node("fill_gaps", self.fill_gaps)
        graph.add_node("synthesize", self.synthesize)
        graph.set_entry_point("start")
        graph.add_edge("start", "investigate")
        graph.add_edge("investigate", "verify")
        graph.add_edge("verify", "fill_gaps")
        graph.add_edge("fill_gaps", "synthesize")
        graph.add_edge("synthesize", END)
        return graph.compile()
