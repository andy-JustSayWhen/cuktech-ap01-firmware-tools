"""刷前验证 AGENTS 与原厂一级页面组合后的连续交互合同。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from typing import Callable, Mapping, Protocol


EVENTS = ("left", "right", "enter")
ROTATION_EVENTS = ("left", "right")
STOCK_PAGE_NAMES = {
    0: "power",
    1: "c1",
    2: "c2",
    3: "clock",
    4: "calendar",
    5: "weather",
    6: "settings",
    7: "pet",
}
AGENTS_PAGE_NAMES = {
    1: "agents-overview",
    2: "agents-weekly",
    3: "agents-today",
    4: "agents-last-30-days",
}
REQUIRED_LOCAL_HOOKS = frozenset({"萌宠左旋", "萌宠右旋", "萌宠确认"})


class InteractionSimulationError(RuntimeError):
    """交互模拟输入或报告没有通过门禁。"""


class RouteLike(Protocol):
    action: str
    target_dispatch: int | None
    target_state: int | None
    switch_mode: int | None


RouteResolver = Callable[..., RouteLike]


@dataclass(frozen=True)
class PageConfiguration:
    c1_enabled: bool = False
    c2_enabled: bool = False
    pet_enabled: bool = True
    agents_enabled: bool = True

    def stock_dispatches(
        self,
        *,
        power_available: bool = True,
    ) -> tuple[int, ...]:
        pages = [0] if power_available else []
        if self.c1_enabled:
            pages.append(1)
        if self.c2_enabled:
            pages.append(2)
        pages.extend((3, 4, 5, 6))
        if self.pet_enabled or self.agents_enabled:
            pages.append(7)
        return tuple(pages)


@dataclass(frozen=True)
class InteractionContract:
    name: str
    local_hook_labels: tuple[str, ...]
    overview_right_target_dispatch: int | None
    power_left_enters_agents: bool
    stock_entry_filter_enabled: bool
    power_confirm_isolated: bool
    page_registration_unchanged: bool
    global_key_callback_registration_unchanged: bool
    fixed_shared_pages_enabled: bool = False
    power_confirm_guard_enabled: bool = False
    power_confirm_guard_calls_stock_clock: bool = False
    source_manifest_sha256: str | None = None

    @classmethod
    def current_stock_resume(cls) -> "InteractionContract":
        return cls(
            name="FW-AGENTS-008",
            local_hook_labels=("萌宠左旋", "萌宠右旋", "萌宠确认"),
            overview_right_target_dispatch=None,
            power_left_enters_agents=False,
            stock_entry_filter_enabled=False,
            power_confirm_isolated=True,
            page_registration_unchanged=True,
            global_key_callback_registration_unchanged=True,
        )

@dataclass(frozen=True)
class InteractionState:
    dispatch: int
    agents_state: int = 0
    original_owned_context: str | None = None
    base_connected: bool = True
    power_data_available: bool = True

    @property
    def visible_page(self) -> str:
        if self.original_owned_context is not None:
            return self.original_owned_context
        if self.agents_state:
            return AGENTS_PAGE_NAMES.get(
                self.agents_state,
                "invalid-agents-state",
            )
        return STOCK_PAGE_NAMES.get(self.dispatch, "invalid-stock-page")

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "visible_page": self.visible_page,
        }


def _state_with(
    state: InteractionState,
    *,
    dispatch: int,
    agents_state: int = 0,
    original_owned_context: str | None = None,
    base_connected: bool | None = None,
    power_data_available: bool | None = None,
) -> InteractionState:
    return InteractionState(
        dispatch=dispatch,
        agents_state=agents_state,
        original_owned_context=original_owned_context,
        base_connected=(
            state.base_connected
            if base_connected is None
            else base_connected
        ),
        power_data_available=(
            state.power_data_available
            if power_data_available is None
            else power_data_available
        ),
    )


@dataclass(frozen=True)
class TraceStep:
    sequence: int
    event: str
    before: InteractionState
    action: str
    after: InteractionState | None
    continuation_address: str | None = None
    resolved: bool = True
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "event": self.event,
            "before": self.before.to_dict(),
            "action": self.action,
            "after": self.after.to_dict() if self.after is not None else None,
            "continuation_address": self.continuation_address,
            "resolved": self.resolved,
            "message": self.message,
        }


@dataclass(frozen=True)
class SimulationFailure:
    code: str
    scenario: str
    message: str
    event: str | None = None
    state: InteractionState | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "scenario": self.scenario,
            "message": self.message,
            "event": self.event,
            "state": self.state.to_dict() if self.state is not None else None,
        }


def _stock_neighbor(
    state: InteractionState,
    event: str,
    configuration: PageConfiguration,
) -> int:
    power_available = (
        state.base_connected and state.power_data_available
    )
    pages = configuration.stock_dispatches(
        power_available=power_available,
    )
    if state.dispatch == 0 and not power_available:
        return pages[0] if event == "right" else pages[-1]
    if state.dispatch not in pages:
        raise InteractionSimulationError("当前原厂分派序号不在启用页面序列")
    offset = 1 if event == "right" else -1
    return pages[(pages.index(state.dispatch) + offset) % len(pages)]


def _stock_transition(
    state: InteractionState,
    event: str,
    configuration: PageConfiguration,
    contract: InteractionContract,
) -> tuple[InteractionState | None, str, str | None]:
    if event == "enter":
        if (
            state.dispatch == 0
            and contract.power_confirm_guard_enabled
            and (
                not state.base_connected
                or not state.power_data_available
            )
        ):
            if not contract.power_confirm_guard_calls_stock_clock:
                return None, "unresolved-power-confirm-guard", None
            return (
                _state_with(
                    state,
                    dispatch=3,
                    base_connected=False,
                    power_data_available=False,
                ),
                "power-confirm-guard-to-clock",
                "0xa0193862",
            )
        context = f"stock-owned:{state.visible_page}:confirm"
        return (
            _state_with(
                state,
                dispatch=state.dispatch,
                original_owned_context=context,
            ),
            "stock-confirm",
            None,
        )

    target = _stock_neighbor(state, event, configuration)
    if target != 7:
        return _state_with(state, dispatch=target), "stock-rotate", None

    if event == "left" and configuration.agents_enabled:
        if not contract.power_left_enters_agents:
            return None, "unresolved-power-left-agents-entry", None
        return _state_with(
            state,
            dispatch=7,
            agents_state=1,
        ), "show-agents", None

    if configuration.pet_enabled:
        return _state_with(state, dispatch=7), "stock-rotate", None
    if configuration.agents_enabled and contract.stock_entry_filter_enabled:
        return _state_with(
            state,
            dispatch=7,
            agents_state=1,
        ), "show-agents", None
    return None, "unresolved-shared-dispatch-entry", None


def _continuation_for_branch(branch: str) -> str:
    return {
        "pet-left": "0xa00bc464",
        "pet-right": "0xa00bc716",
        "pet-enter": "0xa00bda68",
    }[branch]


def simulate_event(
    state: InteractionState,
    event: str,
    configuration: PageConfiguration,
    contract: InteractionContract,
    route_resolver: RouteResolver,
    *,
    sequence: int = 1,
) -> TraceStep:
    if event not in EVENTS:
        raise InteractionSimulationError("未知交互事件")
    if state.original_owned_context is not None:
        return TraceStep(
            sequence=sequence,
            event=event,
            before=state,
            action="stock-owned-context",
            after=state,
            message="原厂详情后续交互不由本模块重定义",
        )
    if state.dispatch != 7:
        after, action, continuation = _stock_transition(
            state,
            event,
            configuration,
            contract,
        )
        return TraceStep(
            sequence=sequence,
            event=event,
            before=state,
            action=action,
            after=after,
            continuation_address=continuation,
            resolved=after is not None,
            message=(
                None
                if after is not None
                else "最终页面未解析：当前成品没有证明共享分派入口的目标画面"
            ),
        )

    branch = f"pet-{event}"
    route = route_resolver(
        branch,
        state.agents_state,
        pet_enabled=configuration.pet_enabled,
        agents_enabled=configuration.agents_enabled,
    )
    continuation = _continuation_for_branch(branch)

    if route.action == "show-agents" and route.target_state is not None:
        after = _state_with(
            state,
            dispatch=7,
            agents_state=route.target_state,
        )
    elif route.action == "restore-pet":
        after = _state_with(state, dispatch=7)
    elif route.action == "switch-stock" and route.target_dispatch is not None:
        after = _state_with(state, dispatch=route.target_dispatch)
    elif route.action in (
        "stock-resume",
        "restore-then-stock",
        "close-then-stock-resume",
    ):
        restored = _state_with(state, dispatch=7)
        if event == "enter":
            after = _state_with(
                state,
                dispatch=7,
                original_owned_context="stock-owned:pet:confirm",
            )
        else:
            after, _, _ = _stock_transition(
                restored,
                event,
                configuration,
                contract,
            )
    elif route.action == "restore-then-stock-resume":
        if contract.overview_right_target_dispatch is None:
            return TraceStep(
                sequence=sequence,
                event=event,
                before=state,
                action=route.action,
                after=None,
                continuation_address=continuation,
                resolved=False,
                message=(
                    "最终页面未解析：恢复萌宠后只证明返回原厂继续地址，"
                    "没有证明继续执行后的可见页面"
                ),
            )
        after = _state_with(
            state,
            dispatch=contract.overview_right_target_dispatch,
        )
    else:
        return TraceStep(
            sequence=sequence,
            event=event,
            before=state,
            action=route.action,
            after=None,
            continuation_address=continuation,
            resolved=False,
            message="最终页面未解析：局部分支动作没有完整目标合同",
        )

    return TraceStep(
        sequence=sequence,
        event=event,
        before=state,
        action=route.action,
        after=after,
        continuation_address=(
            continuation if "stock" in route.action else None
        ),
    )


def simulate_sequence(
    initial: InteractionState,
    events: tuple[str, ...],
    configuration: PageConfiguration,
    contract: InteractionContract,
    route_resolver: RouteResolver,
) -> tuple[TraceStep, ...]:
    state = initial
    steps: list[TraceStep] = []
    for sequence, event in enumerate(events, 1):
        step = simulate_event(
            state,
            event,
            configuration,
            contract,
            route_resolver,
            sequence=sequence,
        )
        steps.append(step)
        if not step.resolved or step.after is None:
            break
        state = step.after
    return tuple(steps)


def _configuration_name(configuration: PageConfiguration) -> str:
    enabled = [
        name
        for name, value in asdict(configuration).items()
        if value
    ]
    return "+".join(enabled) or "settings-only"


def _append_unresolved_failure(
    failures: list[SimulationFailure],
    scenario: str,
    step: TraceStep,
) -> None:
    if step.resolved:
        return
    failures.append(
        SimulationFailure(
            code="UNRESOLVED_FINAL_PAGE",
            scenario=scenario,
            message=step.message or "最终页面未解析",
            event=step.event,
            state=step.before,
        )
    )


def run_interaction_simulation(
    contract: InteractionContract,
    route_resolver: RouteResolver,
    *,
    exhaustive_depth: int = 5,
) -> dict[str, object]:
    if exhaustive_depth < 1 or exhaustive_depth > 8:
        raise InteractionSimulationError("穷举深度必须在 1～8 之间")

    failures: list[SimulationFailure] = []
    selected_traces: dict[str, list[dict[str, object]]] = {}
    scenario_count = 0
    trace_step_count = 0

    missing_hooks = REQUIRED_LOCAL_HOOKS.difference(contract.local_hook_labels)
    if missing_hooks:
        failures.append(
            SimulationFailure(
                code="MISSING_LOCAL_HOOK",
                scenario="binary-contract",
                message="缺少局部分支挂接：" + "、".join(sorted(missing_hooks)),
            )
        )
    for gate_name, gate_value in (
        (
            "功率确认隔离或连接保护",
            (
                contract.power_confirm_isolated
                or contract.power_confirm_guard_enabled
            ),
        ),
        ("页面注册原字节", contract.page_registration_unchanged),
        (
            "一级总键值回调注册地址",
            contract.global_key_callback_registration_unchanged,
        ),
    ):
        if not gate_value:
            failures.append(
                SimulationFailure(
                    code="BINARY_ISOLATION_GATE_FAILED",
                    scenario="binary-contract",
                    message=f"成品合同没有证明{gate_name}保持不变",
                )
            )
    if (
        contract.power_confirm_guard_enabled
        and not contract.power_confirm_guard_calls_stock_clock
    ):
        failures.append(
            SimulationFailure(
                code="POWER_CONFIRM_GUARD_INCOMPLETE",
                scenario="binary-contract",
                message="功率确认连接保护没有证明复用原厂离线切页入口",
            )
        )

    configurations = (
        tuple(
            PageConfiguration(c1, c2, True, True)
            for c1, c2 in product((False, True), repeat=2)
        )
        if contract.fixed_shared_pages_enabled
        else tuple(
            PageConfiguration(c1, c2, pet, agents)
            for c1, c2, pet, agents in product((False, True), repeat=4)
        )
    )
    for configuration in configurations:
        config_name = _configuration_name(configuration)
        for direction in ROTATION_EVENTS:
            start = InteractionState(0 if direction == "right" else 6)
            length = len(configuration.stock_dispatches()) + 3
            steps = simulate_sequence(
                start,
                (direction,) * length,
                configuration,
                contract,
                route_resolver,
            )
            scenario = f"primary-cycle:{config_name}:{direction}"
            scenario_count += 1
            trace_step_count += len(steps)
            for step in steps:
                _append_unresolved_failure(failures, scenario, step)
            visited = {
                step.after.visible_page
                for step in steps
                if step.resolved and step.after is not None
            }
            required_stock = {
                STOCK_PAGE_NAMES[index]
                for index in configuration.stock_dispatches()
                if index != 7 or configuration.pet_enabled
            }
            if configuration.agents_enabled:
                required_stock.add("agents-overview")
            missing_pages = required_stock.difference(visited)
            if missing_pages:
                failures.append(
                    SimulationFailure(
                        code="PRIMARY_PAGE_UNREACHABLE",
                        scenario=scenario,
                        message="连续旋转未到达：" + "、".join(sorted(missing_pages)),
                    )
                )

    if contract.power_confirm_guard_enabled:
        detached_configuration = PageConfiguration()
        for direction in ROTATION_EVENTS:
            start = InteractionState(
                3,
                base_connected=False,
                power_data_available=False,
            )
            length = len(
                detached_configuration.stock_dispatches(
                    power_available=False,
                )
            ) + 2
            steps = simulate_sequence(
                start,
                (direction,) * length,
                detached_configuration,
                contract,
                route_resolver,
            )
            scenario = f"detached-primary-cycle:{direction}"
            scenario_count += 1
            trace_step_count += len(steps)
            selected_traces[scenario] = [
                step.to_dict() for step in steps
            ]
            for step in steps:
                _append_unresolved_failure(failures, scenario, step)
            if any(
                step.after is not None
                and step.after.visible_page == "power"
                for step in steps
            ):
                failures.append(
                    SimulationFailure(
                        code="DETACHED_POWER_REACHABLE",
                        scenario=scenario,
                        message="基座离线时一级循环仍到达功率页",
                    )
                )

    detail_scenarios = {
        "overview-enter-return": (
            InteractionState(7, 1),
            ("enter", "enter"),
        ),
        "details-right-cycle": (
            InteractionState(7, 2),
            ("right", "right", "right"),
        ),
        "details-left-cycle": (
            InteractionState(7, 2),
            ("left", "left", "left"),
        ),
        "overview-right-exit": (InteractionState(7, 1), ("right",)),
        "power-confirm-connected": (InteractionState(0), ("enter",)),
        "fast-reversal": (
            InteractionState(3),
            ("right", "left", "right", "left"),
        ),
    }
    if contract.power_confirm_guard_enabled:
        detail_scenarios.update(
            {
                "power-confirm-detached-stale": (
                    InteractionState(
                        0,
                        base_connected=False,
                        power_data_available=False,
                    ),
                    ("enter",),
                ),
                "power-confirm-data-missing": (
                    InteractionState(
                        0,
                        base_connected=True,
                        power_data_available=False,
                    ),
                    ("enter",),
                ),
            }
        )
    default_configuration = PageConfiguration()
    for scenario, (initial, events) in detail_scenarios.items():
        steps = simulate_sequence(
            initial,
            events,
            default_configuration,
            contract,
            route_resolver,
        )
        scenario_count += 1
        trace_step_count += len(steps)
        selected_traces[scenario] = [step.to_dict() for step in steps]
        for step in steps:
            _append_unresolved_failure(failures, scenario, step)

    expected_detail_pages = {
        "overview-enter-return": ["agents-weekly", "agents-overview"],
        "details-right-cycle": [
            "agents-today",
            "agents-last-30-days",
            "agents-weekly",
        ],
        "details-left-cycle": [
            "agents-last-30-days",
            "agents-today",
            "agents-weekly",
        ],
    }
    for scenario, expected in expected_detail_pages.items():
        actual = [
            step["after"]["visible_page"]
            for step in selected_traces[scenario]
            if step["after"] is not None
        ]
        if actual != expected:
            failures.append(
                SimulationFailure(
                    code="DETAIL_SEQUENCE_MISMATCH",
                    scenario=scenario,
                    message=f"详情轨迹不匹配：{actual}",
                )
            )

    if contract.power_confirm_guard_enabled:
        for scenario in (
            "power-confirm-detached-stale",
            "power-confirm-data-missing",
        ):
            steps = selected_traces[scenario]
            actual = (
                steps[-1]["after"]["visible_page"]
                if steps and steps[-1]["after"] is not None
                else None
            )
            action = steps[-1]["action"] if steps else None
            if actual != "clock" or action != "power-confirm-guard-to-clock":
                failures.append(
                    SimulationFailure(
                        code="POWER_CONFIRM_GUARD_MISMATCH",
                        scenario=scenario,
                        message="失效功率页确认没有安全回到时钟",
                    )
                )

    exhaustive_sequences = 0
    exhaustive_starts = tuple(
        InteractionState(dispatch)
        for dispatch in (0, 3, 4, 5, 6, 7)
    ) + tuple(InteractionState(7, state) for state in range(1, 5))
    if contract.power_confirm_guard_enabled:
        exhaustive_starts += (
            InteractionState(
                0,
                base_connected=False,
                power_data_available=False,
            ),
            InteractionState(
                0,
                base_connected=True,
                power_data_available=False,
            ),
        )
    for length in range(1, exhaustive_depth + 1):
        for events in product(EVENTS, repeat=length):
            for initial in exhaustive_starts:
                exhaustive_sequences += 1
                scenario = (
                    f"exhaustive:{initial.visible_page}:" + "-".join(events)
                )
                steps = simulate_sequence(
                    initial,
                    events,
                    default_configuration,
                    contract,
                    route_resolver,
                )
                for step in steps:
                    if not step.resolved:
                        _append_unresolved_failure(failures, scenario, step)
                        break
                    if step.after is None:
                        failures.append(
                            SimulationFailure(
                                code="MISSING_AFTER_STATE",
                                scenario=scenario,
                                message="已解析事件缺少目标状态",
                                event=step.event,
                                state=step.before,
                            )
                        )
                        break
                    if step.after.visible_page.startswith("invalid-"):
                        failures.append(
                            SimulationFailure(
                                code="INVALID_VISIBLE_PAGE",
                                scenario=scenario,
                                message="事件进入无效可见页面",
                                event=step.event,
                                state=step.after,
                            )
                        )
                        break

    unique_failures: dict[tuple[object, ...], SimulationFailure] = {}
    for failure in failures:
        scenario_key = (
            "exhaustive"
            if failure.scenario.startswith("exhaustive:")
            else failure.scenario
        )
        key = (
            failure.code,
            scenario_key,
            failure.message,
            failure.event,
            failure.state,
        )
        unique_failures[key] = failure

    failure_list = list(unique_failures.values())
    return {
        "schema_version": 1,
        "report_type": "agents-preflash-interaction-simulation",
        "contract": asdict(contract),
        "scope": {
            "events": list(EVENTS),
            "stock_dispatches": STOCK_PAGE_NAMES,
            "agents_states": AGENTS_PAGE_NAMES,
            "runtime_states": [
                "base_connected",
                "power_data_available",
            ],
            "configuration_cases": len(configurations),
            "exhaustive_depth": exhaustive_depth,
        },
        "capability_boundary": {
            "continuous_page_event_model": True,
            "base_lifecycle_event_model": (
                contract.power_confirm_guard_enabled
            ),
            "instruction_level_execution": False,
            "board_hardware_model": False,
            "physical_acceptance_replaced": False,
        },
        "summary": {
            "passed": not failure_list,
            "build_allowed": not failure_list,
            "scenario_count": scenario_count,
            "trace_step_count": trace_step_count,
            "exhaustive_sequence_count": exhaustive_sequences,
            "failure_count": len(failure_list),
        },
        "failures": [failure.to_dict() for failure in failure_list],
        "selected_traces": selected_traces,
    }


def contract_from_manifest(
    document: Mapping[str, object],
    *,
    source_manifest_sha256: str | None = None,
) -> InteractionContract:
    manifest_type = document.get("manifest_type")
    if manifest_type not in (
        "agents-local-ui-stock-resume-firmware",
        "agents-local-ui-stock-safe-firmware",
        "agents-local-ui-base-safe-firmware",
        "agents-live-data-base-safe-firmware",
    ):
        raise InteractionSimulationError("构建清单类型不是当前局部界面固件")
    validation = document.get("validation")
    callchain = document.get("callchain_gates")
    if not isinstance(validation, Mapping) or not isinstance(callchain, Mapping):
        raise InteractionSimulationError("构建清单缺少验证或调用链合同")
    raw_hooks = callchain.get("local_branch_hooks")
    if not isinstance(raw_hooks, list):
        raise InteractionSimulationError("构建清单缺少局部分支挂接")
    labels = tuple(
        item.get("label")
        for item in raw_hooks
        if isinstance(item, Mapping) and isinstance(item.get("label"), str)
    )
    stock_safe = manifest_type in (
        "agents-local-ui-stock-safe-firmware",
        "agents-local-ui-base-safe-firmware",
        "agents-live-data-base-safe-firmware",
    )
    base_safe = manifest_type in (
        "agents-local-ui-base-safe-firmware",
        "agents-live-data-base-safe-firmware",
    )
    live_data = manifest_type == "agents-live-data-base-safe-firmware"
    return InteractionContract(
        name=(
            "FW-AGENTS-011"
            if live_data
            else "FW-AGENTS-010" if base_safe
            else "FW-AGENTS-009" if stock_safe else "FW-AGENTS-008"
        ),
        local_hook_labels=labels,
        overview_right_target_dispatch=0 if stock_safe else None,
        power_left_enters_agents=(
            stock_safe or any(label == "功率左旋" for label in labels)
        ),
        stock_entry_filter_enabled=bool(
            validation.get("page_filter_switch_call_verified")
        ),
        power_confirm_isolated=bool(
            validation.get("stock_power_confirm_path_unchanged")
        ),
        page_registration_unchanged=bool(
            validation.get("page_registration_unchanged")
        ),
        global_key_callback_registration_unchanged=bool(
            validation.get("global_key_callback_registration_unchanged")
        ),
        fixed_shared_pages_enabled=stock_safe,
        power_confirm_guard_enabled=bool(
            validation.get("stock_power_confirm_entry_guarded")
        ),
        power_confirm_guard_calls_stock_clock=bool(
            callchain.get("power_confirm_guard_calls_stock_clock")
        ),
        source_manifest_sha256=source_manifest_sha256,
    )


def simulate_manifest(
    manifest_path: Path,
    route_resolver: RouteResolver,
    *,
    exhaustive_depth: int = 5,
) -> dict[str, object]:
    selected = manifest_path.expanduser().resolve()
    try:
        encoded = selected.read_bytes()
        document = json.loads(encoded.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InteractionSimulationError("无法读取构建清单") from error
    if not isinstance(document, Mapping):
        raise InteractionSimulationError("构建清单根节点不是对象")
    return run_interaction_simulation(
        contract_from_manifest(
            document,
            source_manifest_sha256=sha256(encoded).hexdigest(),
        ),
        route_resolver,
        exhaustive_depth=exhaustive_depth,
    )


def simulate_current_manifest(
    manifest_path: Path,
    *,
    exhaustive_depth: int = 5,
) -> dict[str, object]:
    from .sync_build import route_stock_local_branch

    return simulate_manifest(
        manifest_path,
        route_stock_local_branch,
        exhaustive_depth=exhaustive_depth,
    )


def write_simulation_report(path: Path, report: Mapping[str, object]) -> Path:
    selected = path.expanduser().resolve()
    if selected.exists():
        raise InteractionSimulationError("模拟报告目标已经存在，拒绝覆盖")
    selected.parent.mkdir(parents=True, exist_ok=True)
    temporary = selected.with_name(f".{selected.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(selected)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return selected
