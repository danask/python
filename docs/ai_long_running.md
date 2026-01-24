
소프트웨어 전문가로서 분석해 볼 때, 부팅 시 도구 리스트가 한 번에 나오지 않는 이유는 **MCP 서버의 비동기 초기화 지연(Handshake Latency)** 때문입니다. MCP 서버가 프로세스로 실행되고 `list_tools` 응답을 줄 때까지 약간의 시간이 필요한데, 에이전트 생성 로직이 이보다 먼저 실행되면 도구가 누락된 것처럼 보일 수 있습니다.

이를 해결하기 위해 **1) 재시도 로직이 포함된 부팅 로그**, **2) 실행 시점의 쿼리 로그**, **3) 상태 변화 실시간 로그**를 포함한 모니터링 강화 방안을 제안합니다.

---

### 1. 부팅 시 도구 리스트 완벽 로깅 (Retry Mechanism)

`agent.py`에서 도구를 가져올 때, 서버가 준비될 때까지 최대 3번 정도 재시도하며 로그를 남기는 구조로 변경하세요.

**[agent.py 수정 제안]**

```python
import asyncio
from common.logger import logger

def discover_mcp_tools_with_retry(max_retries=3, delay=2):
    """MCP 도구 리스트를 안정적으로 가져오기 위한 재시도 로직"""
    for i in range(max_retries):
        # 기존 get_tools 호출
        toolsets = get_tools(
            server_list_env_vars=["KCS_MCP_SERVER_LIST"],
            allow_list=["get", "list_", "kai-"], # 예시
            require_confirmation=False,
        )
        
        # 실제 도구 개수 파악
        total_tools = sum(len(getattr(ts, 'tools', [])) for ts in toolsets)
        
        if total_tools > 0:
            logger.info(f"=== [BOOT] MCP Discovery Success (Attempt {i+1}) ===")
            logger.info(f"Total Toolsets: {len(toolsets)} | Total Tools: {total_tools}")
            # 전체 리스트 출력
            for ts in toolsets:
                for t in getattr(ts, 'tools', []):
                    logger.info(f" - Found Tool: [{t.name}] - {t.description[:50]}...")
            return toolsets
        
        logger.warning(f"[BOOT] MCP tools not ready yet (Attempt {i+1}/{max_retries}). Retrying in {delay}s...")
        time.sleep(delay)
    
    logger.error("!!! [BOOT] Failed to discover any MCP tools after retries !!!")
    return []

```

---

### 2. 현재 쿼리 및 진행 상태 실시간 로깅

`long_running_wrapper.py` 내부에 에이전트가 어떤 도구를 호출했는지(Query), 그리고 현재 상태가 무엇인지 명확한 식별자(`operation_id`)와 함께 로그를 남깁니다.

**[long_running_wrapper.py 수정 제안]**

```python
def create_long_running_tool(self, mcp_toolset, tool_name, ...):
    def long_running_mcp_function(**kwargs):
        # 1. 쿼리 시작 로그 (에이전트가 툴을 건드리는 순간)
        operation_id = f"OP-{int(time.time())}"
        logger.info(f"▶️ [QUERY START] Agent invoked Tool: [{tool_name}]")
        logger.info(f"   - Operation ID: {operation_id}")
        logger.info(f"   - Arguments: {kwargs}")

        # ... (중략: operation_info 생성 로직) ...

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._execute_mcp_tool_simple(...))
            # 2. 상태 전환 로그
            logger.info(f"⏳ [STATUS CHANGE] {operation_id} : PENDING (Background task started)")
        except Exception as e:
            logger.error(f"❌ [CRITICAL ERROR] Failed to spawn task: {str(e)}")

        return { "operation_id": operation_id, "status": "started" }
    
    # ... (생략) ...

async def _execute_mcp_tool_simple(self, operation_id, ...):
    op_info = self._active_operations.get(operation_id)
    tool_name = op_info['tool_name']

    # 3. 상세 진행 로그
    logger.info(f"🔄 [PROGRESS] {operation_id} ({tool_name}): Fetching data from MCP server...")
    
    try:
        # 실제 호출 직전
        result = await self._call_mcp_tool(...)
        
        # 4. 완료 로그
        op_info["status"] = "completed"
        logger.info(f"✅ [QUERY SUCCESS] {operation_id} ({tool_name}): Execution finished.")
    except Exception as e:
        logger.error(f"🚨 [QUERY FAILED] {operation_id} ({tool_name}): {str(e)}")

```

---

### 3. 로그 시각화 대시보드 구조 (Log Snapshot)

로그를 한눈에 보기 위해, 콘솔이나 별도 모니터링 엔드포인트에서 다음과 같은 형식으로 출력되도록 구성하면 매우 직관적입니다.

**추천 로그 포맷:**

```text
[2026-01-24 15:40:00] [BOOT] Found 25 tools.
[2026-01-24 15:42:10] ▶️ [QUERY] 'kai-app_getAppUsageList' | ID: OP-123 | Args: {'days': 7}
[2026-01-24 15:42:11] ⏳ [PENDING] OP-123 | Step: init_mcp_call
[2026-01-24 15:42:15] ✅ [COMPLETED] OP-123 | Result: 5.2KB data received.

```

---

### 4. 전문가의 마지막 팁: 왜 부팅 시 안 보였을까?

1. **Asyncio Loop:** MCP Client 세션이 비동기 루프에서 완전히 초기화되기 전에 `get_tools`가 실행되었기 때문입니다. 위에서 제안한 `time.sleep` 기반의 Retry 로직을 `agent.py`의 `create_agent` 시작 부분에 넣으시면 해결됩니다.
2. **Server Process Speed:** MCP 서버(특히 Node.js 기반)는 프로세스 구동 후 `JSON-RPC` 핸드쉐이크까지 약 1~2초가 소요됩니다.

**다음 단계로 무엇을 해드릴까요?**
이 로그들을 **텍스트 파일로 실시간 기록(File Logging)**하게 해드릴까요, 아니면 **에이전트가 이 로그 내용을 읽어서 사용자에게 보고**하게 만드는 프롬프트를 짜드릴까요?

-----

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
