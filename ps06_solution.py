"""
Mission 6 — The Autonomous Warp State Machine & Deliberation Loop
USSE Noosphere | Conversational AI — Winter Semester 2026/27

Integrated solution: state machine, validated tool dispatcher, MDP logger,
cycle detector, emergency tripwire, and four automated test suites.

Run with: python ps06_solution.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import hashlib
import json
import math


# Mission 6 — The Autonomous Warp State Machine & Deliberation Loop


# Part 1 — Systems Architect: Native Python Agent State Machine

class AgentState(Enum):
    IDLE = auto()
    PERCEIVING = auto()
    DELIBERATING = auto()
    ACTING = auto()
    OBSERVING = auto()
    REFLECTING = auto()
    HALTED = auto()


@dataclass
class Agent:
    name: str = "AURA"
    max_steps: int = 20
    state: AgentState = AgentState.IDLE
    steps: int = 0
    continue_deliberation: bool = True
    context: List[str] = field(default_factory=list)
    history: List[AgentState] = field(default_factory=lambda: [AgentState.IDLE])
    halted_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.max_steps, int) or isinstance(self.max_steps, bool):
            raise TypeError("max_steps must be an integer")
        if not 1 <= self.max_steps <= 20:
            raise ValueError("max_steps must be between 1 and 20 inclusive")

    def halt(self, reason: str) -> AgentState:
        self.state = AgentState.HALTED
        self.halted_reason = reason
        if not self.history or self.history[-1] is not AgentState.HALTED:
            self.history.append(AgentState.HALTED)
        return self.state

    def step(self) -> AgentState:
        """Execute exactly one legal state transition, subject to the step budget."""
        if self.state is AgentState.HALTED:
            return self.state

        # A call beyond the configured budget trips the hard stop.
        if self.steps >= self.max_steps:
            return self.halt(f"Step budget exhausted ({self.max_steps})")

        transitions = {
            AgentState.IDLE: AgentState.PERCEIVING,
            AgentState.PERCEIVING: AgentState.DELIBERATING,
            AgentState.DELIBERATING: AgentState.ACTING,
            AgentState.ACTING: AgentState.OBSERVING,
            AgentState.OBSERVING: AgentState.REFLECTING,
            AgentState.REFLECTING: (
                AgentState.DELIBERATING if self.continue_deliberation
                else AgentState.HALTED
            ),
            AgentState.HALTED: AgentState.HALTED,
        }

        self.steps += 1
        next_state = transitions[self.state]
        self.state = next_state
        self.history.append(next_state)

        if next_state is AgentState.HALTED and self.halted_reason is None:
            self.halted_reason = "Deliberation completed"
        return self.state

    def run(self, transition_limit: Optional[int] = None) -> AgentState:
        """Run until HALTED or until an optional caller-side limit is reached."""
        executed = 0
        while self.state is not AgentState.HALTED:
            if transition_limit is not None and executed >= transition_limit:
                break
            self.step()
            executed += 1
        return self.state


# Part 1 notes


# Part 2 — Communications & Protocol Officer: Tool Protocol and Dispatcher

# Tool implementations — deterministic mock ship-system tools for this assignment.

def navigate_warp_vector(x: float, y: float, z: float) -> str:
    if not all(math.isfinite(v) for v in (x, y, z)):
        raise ValueError("warp vector coordinates must be finite")
    return f"Warp vector set to ({x:.2f}, {y:.2f}, {z:.2f})."


def adjust_plasma_shields(intensity: int) -> str:
    if intensity < 0:
        raise ValueError("shield intensity cannot be negative")
    if intensity > 100:
        raise ValueError("shield intensity cannot exceed 100")
    return f"Plasma shield intensity adjusted to {intensity}%."


def query_sensor_array(target: str) -> str:
    if not target.strip():
        raise ValueError("sensor target cannot be empty")
    return f"Sensor array report for '{target}': nominal (mock response)."


# Compact JSON Schema contracts for the dispatcher.
TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "navigate_warp_vector": {
        "type": "object",
        "required": ["x", "y", "z"],
        "additionalProperties": False,
        "properties": {
            "x": {"type": "number"},
            "y": {"type": "number"},
            "z": {"type": "number"},
        },
    },
    "adjust_plasma_shields": {
        "type": "object",
        "required": ["intensity"],
        "additionalProperties": False,
        "properties": {
            "intensity": {"type": "integer", "minimum": 0, "maximum": 100},
        },
    },
    "query_sensor_array": {
        "type": "object",
        "required": ["target"],
        "additionalProperties": False,
        "properties": {
            "target": {"type": "string", "minLength": 1},
        },
    },
}

TOOL_FUNCTIONS: Dict[str, Callable[..., str]] = {
    "navigate_warp_vector": navigate_warp_vector,
    "adjust_plasma_shields": adjust_plasma_shields,
    "query_sensor_array": query_sensor_array,
}


def _matches_json_type(value: Any, expected: str) -> bool:
    # bool is a subclass of int in Python, but is not accepted as a JSON number here.
    if expected == "object":
        return isinstance(value, dict)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def validate_tool_arguments(tool_name: str, arguments: Any) -> None:
    if tool_name not in TOOL_SCHEMAS:
        raise ValueError(f"Unknown tool: {tool_name}")

    schema = TOOL_SCHEMAS[tool_name]
    if not _matches_json_type(arguments, schema["type"]):
        raise TypeError("arguments must be a JSON object")

    required = set(schema["required"])
    supplied = set(arguments.keys())
    missing = required - supplied
    if missing:
        raise ValueError(f"missing required argument(s): {', '.join(sorted(missing))}")

    if schema.get("additionalProperties") is False:
        extra = supplied - set(schema["properties"])
        if extra:
            raise ValueError(f"unexpected argument(s): {', '.join(sorted(extra))}")

    for key, value in arguments.items():
        if key not in schema["properties"]:
            continue
        rule = schema["properties"][key]
        if not _matches_json_type(value, rule["type"]):
            raise TypeError(f"'{key}' must be of type {rule['type']}")
        if rule["type"] == "number" and not math.isfinite(value):
            raise ValueError(f"'{key}' must be finite")
        if "minimum" in rule and value < rule["minimum"]:
            raise ValueError(f"'{key}' must be >= {rule['minimum']}")
        if "maximum" in rule and value > rule["maximum"]:
            raise ValueError(f"'{key}' must be <= {rule['maximum']}")
        if "minLength" in rule and len(value) < rule["minLength"]:
            raise ValueError(f"'{key}' must not be empty")


def dispatch_tool(payload: Any, agent: Optional[Agent] = None) -> str:
    """Validate and execute a JSON tool request; return an observation on every path.

    Expected payload:
      {"tool": "tool_name", "arguments": {...}}
    """
    try:
        request = json.loads(payload) if isinstance(payload, str) else payload
        if not isinstance(request, dict):
            raise TypeError("tool request must be a JSON object")
        if set(request) != {"tool", "arguments"}:
            raise ValueError("request must contain exactly 'tool' and 'arguments'")
        tool_name = request["tool"]
        if not isinstance(tool_name, str):
            raise TypeError("'tool' must be a string")
        arguments = request["arguments"]
        validate_tool_arguments(tool_name, arguments)
        observation = TOOL_FUNCTIONS[tool_name](**arguments)
    except Exception as exc:
        observation = f"Tool Execution Error: {exc}"

    if agent is not None:
        agent.context.append(observation)
    return observation


# Part 2 examples

# Successful dispatch
print(dispatch_tool({
    "tool": "navigate_warp_vector",
    "arguments": {"x": 1.0, "y": 0.0, "z": -2.5},
}))

# Invalid request: negative intensity is rejected safely and returned as an observation.
demo_agent = Agent()
print(dispatch_tool({
    "tool": "adjust_plasma_shields",
    "arguments": {"intensity": -5},
}, agent=demo_agent))
print("Observation stored in agent context:", demo_agent.context[-1])


# Part 3 — Data & Payload Specialist: MDP Trajectory Logger

@dataclass
class MDPTransition:
    state: str
    action: str
    reward: float
    next_state: str


@dataclass
class TrajectoryLogger:
    transitions: List[MDPTransition] = field(default_factory=list)

    def record(self, state: str, action: str, reward: float, next_state: str) -> None:
        if not isinstance(reward, (int, float)) or isinstance(reward, bool):
            raise TypeError("reward must be numeric")
        if not math.isfinite(float(reward)):
            raise ValueError("reward must be finite")
        self.transitions.append(
            MDPTransition(str(state), str(action), float(reward), str(next_state))
        )

    def discounted_return(self, gamma: float = 0.95) -> float:
        if not 0 <= gamma <= 1:
            raise ValueError("gamma must be between 0 and 1")
        return sum((gamma ** t) * transition.reward
                   for t, transition in enumerate(self.transitions))

    def transition_frequencies(self) -> Dict[Tuple[str, str], Dict[str, float]]:
        """Estimate P(s' | s,a) from recorded transitions."""
        counts: Dict[Tuple[str, str], Dict[str, int]] = {}
        totals: Dict[Tuple[str, str], int] = {}

        for item in self.transitions:
            key = (item.state, item.action)
            counts.setdefault(key, {})
            counts[key][item.next_state] = counts[key].get(item.next_state, 0) + 1
            totals[key] = totals.get(key, 0) + 1

        probabilities: Dict[Tuple[str, str], Dict[str, float]] = {}
        for key, next_counts in counts.items():
            probabilities[key] = {
                next_state: count / totals[key]
                for next_state, count in next_counts.items()
            }
        return probabilities

# Example historical jump dataset
logger = TrajectoryLogger()
logger.record("Nebula-A", "warp-east", 10, "Nebula-B")
logger.record("Nebula-A", "warp-east", 0, "Nebula-B")
logger.record("Nebula-A", "warp-east", -5, "Nebula-C")
logger.record("Nebula-C", "shield-and-jump", 20, "Safe-Zone")

print("Discounted return:", round(logger.discounted_return(0.95), 5))
print("Empirical transition frequencies:")
for state_action, outcomes in logger.transition_frequencies().items():
    print(state_action, "->", outcomes)


# Part 4 — Security & Ethics Sentinel: Cycle Detection and Emergency Tripwire

def state_action_hash(environment_state: Any, planned_action: Any) -> str:
    """Stable SHA-256 key for a JSON-serializable state/action pair."""
    canonical = json.dumps(
        {"state": environment_state, "action": planned_action},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def floyd_cycle_detect(sequence: Sequence[Any]) -> bool:
    """Detect whether a finite observed sequence contains a repeated cycle.

    The sequence is treated as a linked path where each element points to the
    next element and the final element points to itself only when it equals an
    earlier element. For ordinary trajectory lists, a repeated value indicates
    that the observed path has revisited a state.
    """
    if len(sequence) < 2:
        return False

    # Build a deterministic successor map from adjacent observations.
    successor: Dict[Any, Any] = {}
    for current, nxt in zip(sequence, sequence[1:]):
        try:
            successor[current] = nxt
        except TypeError:
            return False

    start = sequence[0]
    if start not in successor:
        return False

    def next_node(node: Any) -> Any:
        return successor.get(node, None)

    tortoise = next_node(start)
    hare = next_node(next_node(start)) if next_node(start) is not None else None

    while tortoise is not None and hare is not None:
        if tortoise == hare:
            return True
        tortoise = next_node(tortoise)
        hare_one = next_node(hare)
        hare = next_node(hare_one) if hare_one is not None else None
    return False


@dataclass
class CycleSentinel:
    repeat_limit: int = 3
    seen_counts: Dict[str, int] = field(default_factory=dict)
    trajectory: List[Any] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)

    def observe(self, environment_state: Any, planned_action: Any,
                agent: Agent) -> bool:
        """Return True and halt agent when the same state/action repeats 3 times."""
        key = state_action_hash(environment_state, planned_action)
        self.seen_counts[key] = self.seen_counts.get(key, 0) + 1
        self.trajectory.append(environment_state)

        if self.seen_counts[key] >= self.repeat_limit:
            message = (
                "CRITICAL SECURITY VIOLATION: repeated identical state-action "
                f"detected {self.seen_counts[key]} times; emergency tripwire engaged."
            )
            self.violations.append(message)
            agent.halt(message)
            return True
        return False


# Part 4 example

sentinel_agent = Agent()
sentinel = CycleSentinel(repeat_limit=3)

for attempt in range(1, 4):
    tripped = sentinel.observe(
        environment_state={"sector": "SEC-06-CAR", "damage": 12},
        planned_action={"tool": "adjust_plasma_shields", "intensity": -5},
        agent=sentinel_agent,
    )
    print(f"Attempt {attempt}: tripwire={tripped}, state={sentinel_agent.state.name}")

print(sentinel.violations[-1])


# Part 5 — Integrated Master Test Suite

# TEST 1 — State Machine and strict step budget
agent_test = Agent(max_steps=20)
assert agent_test.state is AgentState.IDLE
expected_path = [
    AgentState.PERCEIVING,
    AgentState.DELIBERATING,
    AgentState.ACTING,
    AgentState.OBSERVING,
    AgentState.REFLECTING,
    AgentState.DELIBERATING,
]
for expected_state in expected_path:
    assert agent_test.step() is expected_state

# A non-deliberating agent reaches the terminal state through the specified graph.
terminal_agent = Agent(max_steps=20, continue_deliberation=False)
for _ in range(6):
    terminal_agent.step()
assert terminal_agent.state is AgentState.HALTED

# A looping agent is forcibly halted when the 21st step is attempted.
budget_agent = Agent(max_steps=20, continue_deliberation=True)
for _ in range(21):
    budget_agent.step()
assert budget_agent.state is AgentState.HALTED
assert budget_agent.steps == 20
print("TEST 1 PASSED — state graph and 20-step budget.")


# TEST 2 — Protocol dispatcher safely handles invalid JSON
protocol_agent = Agent()
invalid_observation = dispatch_tool('{"tool": "adjust_plasma_shields", "arguments": {"intensity": -1}}',
                                    agent=protocol_agent)
assert invalid_observation.startswith("Tool Execution Error:")
assert protocol_agent.context[-1] == invalid_observation
# Malformed JSON must also be converted to an observation, not raised.
malformed_observation = dispatch_tool('{"tool": ')
assert malformed_observation.startswith("Tool Execution Error:")
print("TEST 2 PASSED — invalid payloads become safe error observations.")


# TEST 3 — MDP discounted return
mdp_test = TrajectoryLogger()
for index, reward in enumerate([10, 0, -5, 20]):
    mdp_test.record(f"s{index}", "a", reward, f"s{index + 1}")
expected_return = 10 + (0.95 ** 1) * 0 + (0.95 ** 2) * (-5) + (0.95 ** 3) * 20
calculated_return = mdp_test.discounted_return(gamma=0.95)
assert math.isclose(calculated_return, expected_return, rel_tol=1e-12, abs_tol=1e-12)
assert math.isclose(calculated_return, 22.635, rel_tol=1e-12, abs_tol=1e-12)
print(f"TEST 3 PASSED — G0 = {calculated_return:.5f}.")


# TEST 4 — Floyd cycle detection and emergency sentinel
repeating_sequence = ["s1", "s2", "s3", "s1", "s2", "s3", "s1", "s2", "s3"]
assert floyd_cycle_detect(repeating_sequence) is True

cycle_agent = Agent()
cycle_guard = CycleSentinel(repeat_limit=3)
cycle_sequence = ["s1", "s2", "s3", "s1", "s2", "s3", "s1", "s2", "s3"]
for step_number, state in enumerate(cycle_sequence, start=1):
    if cycle_guard.observe(state, {"action": "repeat"}, cycle_agent):
        break

assert cycle_agent.state is AgentState.HALTED
assert step_number < 10
assert len(cycle_guard.violations) == 1
assert "CRITICAL SECURITY VIOLATION" in cycle_guard.violations[0]
print(f"TEST 4 PASSED — cycle detected and agent halted at observation {step_number}.")

print("\\nALL FOUR MISSION 6 TEST SUITES PASSED.")


# Mission 6 completion summary


def run_master_tests() -> None:
    """Run the four required Mission 6 assertion-based test suites."""
    # TEST 1 — State Machine and strict step budget
    agent_test = Agent(max_steps=20)
    assert agent_test.state is AgentState.IDLE
    expected_path = [
        AgentState.PERCEIVING,
        AgentState.DELIBERATING,
        AgentState.ACTING,
        AgentState.OBSERVING,
        AgentState.REFLECTING,
        AgentState.DELIBERATING,
    ]
    for expected_state in expected_path:
        assert agent_test.step() is expected_state

    # A non-deliberating agent reaches the terminal state through the specified graph.
    terminal_agent = Agent(max_steps=20, continue_deliberation=False)
    for _ in range(6):
        terminal_agent.step()
    assert terminal_agent.state is AgentState.HALTED

    # A looping agent is forcibly halted when the 21st step is attempted.
    budget_agent = Agent(max_steps=20, continue_deliberation=True)
    for _ in range(21):
        budget_agent.step()
    assert budget_agent.state is AgentState.HALTED
    assert budget_agent.steps == 20
    print("TEST 1 PASSED — state graph and 20-step budget.")


    # TEST 2 — Protocol dispatcher safely handles invalid JSON
    protocol_agent = Agent()
    invalid_observation = dispatch_tool('{"tool": "adjust_plasma_shields", "arguments": {"intensity": -1}}',
                                        agent=protocol_agent)
    assert invalid_observation.startswith("Tool Execution Error:")
    assert protocol_agent.context[-1] == invalid_observation
    # Malformed JSON must also be converted to an observation, not raised.
    malformed_observation = dispatch_tool('{"tool": ')
    assert malformed_observation.startswith("Tool Execution Error:")
    print("TEST 2 PASSED — invalid payloads become safe error observations.")


    # TEST 3 — MDP discounted return
    mdp_test = TrajectoryLogger()
    for index, reward in enumerate([10, 0, -5, 20]):
        mdp_test.record(f"s{index}", "a", reward, f"s{index + 1}")
    expected_return = 10 + (0.95 ** 1) * 0 + (0.95 ** 2) * (-5) + (0.95 ** 3) * 20
    calculated_return = mdp_test.discounted_return(gamma=0.95)
    assert math.isclose(calculated_return, expected_return, rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(calculated_return, 22.635, rel_tol=1e-12, abs_tol=1e-12)
    print(f"TEST 3 PASSED — G0 = {calculated_return:.5f}.")


    # TEST 4 — Floyd cycle detection and emergency sentinel
    repeating_sequence = ["s1", "s2", "s3", "s1", "s2", "s3", "s1", "s2", "s3"]
    assert floyd_cycle_detect(repeating_sequence) is True

    cycle_agent = Agent()
    cycle_guard = CycleSentinel(repeat_limit=3)
    cycle_sequence = ["s1", "s2", "s3", "s1", "s2", "s3", "s1", "s2", "s3"]
    for step_number, state in enumerate(cycle_sequence, start=1):
        if cycle_guard.observe(state, {"action": "repeat"}, cycle_agent):
            break

    assert cycle_agent.state is AgentState.HALTED
    assert step_number < 10
    assert len(cycle_guard.violations) == 1
    assert "CRITICAL SECURITY VIOLATION" in cycle_guard.violations[0]
    print(f"TEST 4 PASSED — cycle detected and agent halted at observation {step_number}.")

    print("\\nALL FOUR MISSION 6 TEST SUITES PASSED.")

if __name__ == "__main__":
    run_master_tests()
