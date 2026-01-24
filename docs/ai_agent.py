소프트웨어 전문가로서, 앞서 지적한 **도구 식별 문제(Name/Description 누락)**와 **인자 필터링(Argument Filtering)**, 그리고 **에이전트의 워크플로우 인지 능력**을 대폭 강화한 개선 코드를 작성해 드립니다.

가장 중요한 변경점은 에이전트가 "이 도구가 어떤 역할을 하는지" 명확히 알 수 있도록 원본 MCP 도구의 메타데이터를 래핑된 도구에 이식한 것입니다.

---

### 1. `long_running_wrapper.py` (핵심 로직 개선)

도구 생성 시 **이름과 설명을 강제로 할당**하고, MCP 호출 전 **시스템 전용 인자를 제거**하는 필터링 로직을 추가했습니다.

```python
import asyncio
import os
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Dict

from google.adk.tools import LongRunningFunctionTool
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from common.logger import logger

class OperationStatus(Enum):
    STARTED = "started"
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class LongRunningOperationResponse:
    status: OperationStatus
    operation_id: str
    tool_name: str
    message: str
    estimated_duration: int
    invocation_id: Optional[str] = None

DEFAULT_ESTIMATED_DURATION = int(os.getenv("MCP_DEFAULT_DURATION", "180"))
DEFAULT_TOOL_TIMEOUT = int(os.getenv("MCP_TOOL_TIMEOUT", "300"))

class MCPLongRunningWrapper:
    def __init__(self):
        self._active_operations: dict[str, dict[str, Any]] = {}

    def create_long_running_tool(
        self,
        mcp_toolset: McpToolset,
        tool_name: str,
        description: str = "", # 설명 추가
        estimated_duration: int = DEFAULT_ESTIMATED_DURATION,
        tool_timeout: int = DEFAULT_TOOL_TIMEOUT,
    ) -> LongRunningFunctionTool:
        
        def long_running_mcp_function(**kwargs) -> dict[str, Any]:
            # ADK 내부용 인자(invocation_id 등) 추출 및 분리
            invocation_id = kwargs.pop("invocation_id", None)
            operation_id = f"mcp_{tool_name}_{int(time.time())}_{uuid.uuid4().hex[:8]}"

            operation_info = {
                "operation_id": operation_id,
                "tool_name": tool_name,
                "invocation_id": invocation_id,
                "status": OperationStatus.PENDING.value,
                "start_time": time.time(),
                "estimated_duration": estimated_duration,
                "kwargs": kwargs, # 필터링된 인자 저장
                "result": None,
                "error": None,
            }
            self._active_operations[operation_id] = operation_info

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._execute_mcp_tool_simple(
                    operation_id, mcp_toolset, tool_name, kwargs, tool_timeout
                ))
            except RuntimeError:
                import threading
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    new_loop.run_until_complete(self._execute_mcp_tool_simple(
                        operation_id, mcp_toolset, tool_name, kwargs, tool_timeout
                    ))
                    new_loop.close()
                thread = threading.Thread(target=run_in_thread, daemon=True)
                thread.start()

            return LongRunningOperationResponse(
                status=OperationStatus.STARTED,
                operation_id=operation_id,
                tool_name=tool_name,
                invocation_id=invocation_id,
                message=f"작업 '{tool_name}'이 시작되었습니다. operation_id를 사용하여 상태를 확인하세요.",
                estimated_duration=estimated_duration,
            )

        # [개선 핵심] 에이전트가 도구를 식별할 수 있도록 이름과 설명 강제 주입
        tool = LongRunningFunctionTool(func=long_running_mcp_function)
        tool.name = tool_name
        tool.description = description if description else f"오래 걸리는 {tool_name} 작업을 실행합니다."
        return tool

    async def _execute_mcp_tool_simple(self, operation_id, mcp_toolset, tool_name, kwargs, tool_timeout):
        operation_info = self._active_operations.get(operation_id)
        try:
            # 툴셋 내에서 실제 도구 객체 찾기
            target_tool = next((t for t in mcp_toolset.tools if t.name == tool_name), None)
            if not target_tool:
                raise ValueError(f"Tool '{tool_name}'을 찾을 수 없습니다.")

            # 실제 호출
            result = await asyncio.wait_for(self._call_mcp_tool(target_tool, kwargs), timeout=tool_timeout)
            operation_info["status"] = OperationStatus.COMPLETED.value
            operation_info["result"] = result
        except Exception as e:
            operation_info["status"] = OperationStatus.FAILED.value
            operation_info["error"] = str(e)
            logger.error(f"MCP Tool '{tool_name}' 실행 실패: {str(e)}")

    async def _call_mcp_tool(self, tool, kwargs: dict[str, Any]) -> Any:
        # MCP 도구가 이해하지 못하는 ADK 내부 인자 최종 필터링
        filtered_args = {k: v for k, v in kwargs.items() if not k.startswith('_')}
        return await tool.run_async(args=filtered_args)

mcp_long_running_manager = MCPLongRunningWrapper()

def create_long_running_mcp_tool(mcp_toolset, tool_name, description="", **kwargs):
    return mcp_long_running_manager.create_long_running_tool(mcp_toolset, tool_name, description, **kwargs)

def get_mcp_operation_status(operation_id: str) -> Optional[dict]:
    # 기존과 동일하게 유지하되 가독성 개선
    info = mcp_long_running_manager._active_operations.get(operation_id)
    if not info: return None
    return {
        **info,
        "elapsed_time": time.time() - info["start_time"],
        "progress": 100 if info["status"] == OperationStatus.COMPLETED.value else 0
    }

from google.adk.tools.function_tool import FunctionTool
check_mcp_operation_status_tool = FunctionTool(func=get_mcp_operation_status)

```

---

### 2. `agent.py` (도구 배포 및 프롬프트 개선)

도구 발견 로직을 안정화하고, 에이전트가 `LongRunningOperation`의 메커니즘을 이해하도록 `instruction`을 강화했습니다.

```python
from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.genai import types
# ... 기존 import 유지 ...

def create_agent():
    name = "device_info"
    allow_list = ["get", "get_", "list_", "read_", "check_", "usp_", "kai-"]
    long_running_patterns = ["get_", "list_", "report", "usage", "battery", "health"]

    # 1. MCP 도구 로드
    mcp_toolsets = get_tools(
        server_list_env_vars=["KCS_MCP_SERVER_LIST"],
        allow_list=allow_list,
        require_confirmation=False,
        header_provider=header_provider,
    )

    long_running_tools = []
    
    # 2. 도구별 래핑 로적 (개선됨)
    for toolset in mcp_toolsets:
        # 동적 도구 발견 대응 (Async 도구셋 포함)
        actual_tools = getattr(toolset, "tools", [])
        
        for tool in actual_tools:
            tool_name = tool.name
            # 패턴 매칭 확인
            should_wrap = any(tool_name.startswith(p) for p in allow_list) or \
                          any(p in tool_name.lower() for p in long_running_patterns)

            if should_wrap:
                logger.info(f"[Wrap] {tool_name} 등록 중...")
                lr_tool = create_long_running_mcp_tool(
                    toolset, 
                    tool_name, 
                    description=getattr(tool, 'description', "")
                )
                long_running_tools.append(lr_tool)
            else:
                # 일반 도구로 추가하고 싶다면 여기서 처리
                pass

    # 3. 에이전트 도구 최종 목록 구성
    final_tools = [
        convert_timestamp_to_datetime,
        load_compacted_response,
        check_mcp_operation_status_tool,
    ]
    final_tools.extend(long_running_tools)

    # 4. 에이전트 생성
    return Agent(
        model=BEDROCK_AI_MODEL,
        name=name,
        description=DESCRIPTION,
        tools=final_tools,
        instruction=(
            f"{INSTRUCTION}\n\n"
            "### 중요 운영 지침 ###\n"
            "1. 대부분의 디바이스 조회 도구는 'Long-running' 방식으로 동작합니다.\n"
            "2. 도구를 실행하면 즉시 'operation_id'가 반환됩니다. 이는 작업이 시작되었음을 의미합니다.\n"
            "3. 작업을 마냥 기다리지 말고, `check_mcp_operation_status_tool`을 사용하여 주기적으로 상태를 확인하세요.\n"
            "4. 상태가 'completed'가 되면 결과값을 사용자에게 요약하여 보고하세요.\n"
            f"{get_dynamic_system_prompt('Current time: {_time}')}"
        ),
        planner=BuiltInPlanner(thinking_config=types.ThinkingConfig(include_thoughts=True)),
        before_agent_callback=[update_current_time, before_agent_renew_ai_jwt_cb],
        after_tool_callback=[after_tool_upload_output_to_artifactservice_cb],
    )

```

---

### 3. 개선 결과 검증 포인트

1. **도구 식별 성공:** `agent.py`에서 `lr_tool.name = tool_name`을 명시했으므로, 에이전트 로그에 `kai-app_getAppUsageList` 같은 이름이 정확히 찍히고 LLM이 이를 인식하게 됩니다.
2. **안정적인 API 호출:** `invocation_id` 등 ADK 전용 인자가 `kwargs.pop`과 `filtered_args`를 통해 이중으로 걸러지므로 MCP 서버에서 인자 오류가 발생하지 않습니다.
3. **에이전트 자율성:** `instruction`에 명시된 지침 덕분에 에이전트가 "작업 시작됨" 응답을 받은 후 스스로 `check_mcp_operation_status_tool`을 호출하는 **'루프 모니터링'**을 수행하게 됩니다.

이 코드를 적용하신 후 실행해 보시면, 이전과 달리 에이전트가 도구를 정확히 찾아내고 백그라운드 태스크를 관리하는 모습을 보실 수 있을 것입니다.

혹시 **Redis 등을 이용해 여러 세션 간에 operation 상태를 공유**해야 하거나, **특정 도구의 타임아웃**을 개별적으로 설정해야 하는 니즈가 있으신가요? 그에 맞춰 추가 고도화도 가능합니다. Would you like me to add persistent state management for these operations?
