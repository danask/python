소프트웨어 전문가로서 정확한 진단을 내리셨습니다. MCP 서버는 별도의 프로세스로 구동되기 때문에, 에이전트가 실행되는 시점(Import 또는 구동 직후)에 `get_tools`를 호출하면 서버와의 핸드쉐이크가 완료되지 않아 도구 목록이 비어 있는 경우가 많습니다.

이를 해결하기 위해 에이전트 생성 후 도구를 나중에 채워넣는 **포스트 프로세싱(Post-processing)** 또는 **지연 초기화(Lazy Initialization)** 방식이 실무에서 훨씬 안정적입니다.

사용자님의 환경에 맞춰 **"부팅 시에는 대기하고, 첫 요청이나 특정 시점에 도구를 동적으로 변환하여 주입"**하는 코드를 제안합니다.

---

### 1. `long_running_wrapper.py` (이름 식별 기능 포함)

에이전트 로그에 `LR_` 접두어가 찍히도록 명시적으로 이름을 받는 로직을 추가한 버전입니다.

```python
# long_running_wrapper.py

def create_long_running_tool(
    self,
    mcp_toolset,
    tool_name,
    agent_tool_name=None, # 에이전트 인식용 이름 추가
    estimated_duration=DEFAULT_ESTIMATED_DURATION,
    tool_timeout=DEFAULT_TOOL_TIMEOUT,
):
    async def long_running_mcp_function(**kwargs):
        # 실행 시점에 어떤 이름으로 들어왔는지 로그 확인
        display_name = agent_tool_name or tool_name
        logger.info(f"🧩 [LR-WRAPPER-HIT] Executing: {display_name} (Mapped to original: {tool_name})")
        
        # ... (중략: 기존 operation 생성 및 백그라운드 태스크 실행 로직) ...
        return {
            "status": "started",
            "operation_id": f"op_{int(time.time())}",
            "message": f"{display_name} 작업이 백그라운드에서 시작되었습니다."
        }

    # [중요] 에이전트가 이 name을 보고 로그에 남깁니다.
    tool = LongRunningFunctionTool(func=long_running_mcp_function)
    tool.name = agent_tool_name if agent_tool_name else tool_name
    return tool

```

---

### 2. `agent.py` (포스트 프로세싱/지연 초기화 방식)

부팅 시 도구가 없더라도 에이전트를 먼저 만들고, 도구가 준비되었을 때 `LR_` 접두어를 붙여 동적으로 업데이트하는 구조입니다.

```python
# agent.py

# 전역 변수로 관리하여 나중에 업데이트 가능하게 설정
_device_info_agent = None

def create_agent():
    # 1. 기본 도구들만 먼저 정의
    base_tools = [
        convert_timestamp_to_datetime,
        load_compacted_response,
        check_mcp_operation_status_tool,
    ]

    # 2. 에이전트 초기 생성 (이때는 MCP 도구가 없을 수 있음)
    agent = Agent(
        model=BEDROCK_AI_MODEL,
        name="device_info",
        description=DESCRIPTION,
        tools=base_tools, # 우선 기본 도구만 주입
        instruction=INSTRUCTION,
        planner=BuiltInPlanner(thinking_config=types.ThinkingConfig(include_thoughts=True)),
        # ... 나머지 설정 ...
    )
    return agent

def refresh_agent_tools():
    """포스트 프로세싱: MCP 서버에서 도구를 다시 읽어와 LR 접두어를 붙여 에이전트 도구함 갱신"""
    global root_agent
    
    allow_list = ["get", "get_", "list_", "read_", "check_", "usp_", "kai-"]
    long_running_patterns = ["get_", "list_", "usage", "report", "kai-"]

    # MCP 도구 가져오기
    mcp_toolsets = get_tools(
        server_list_env_vars=["KCS_MCP_SERVER_LIST"],
        allow_list=allow_list,
        require_confirmation=False,
    )

    new_tools = [convert_timestamp_to_datetime, load_compacted_response, check_mcp_operation_status_tool]
    
    found_any = False
    for toolset in mcp_toolsets:
        actual_tools = getattr(toolset, "tools", [])
        for tool in actual_tools:
            found_any = True
            # 롱러닝 패턴이면 LR_ 접두어 추가하여 변환
            if any(p in tool.name.lower() for p in long_running_patterns):
                lr_display_name = f"LR_{tool.name}"
                wrapped_tool = create_long_running_mcp_tool(
                    toolset, 
                    tool.name, 
                    agent_tool_name=lr_display_name
                )
                new_tools.append(wrapped_tool)
                logger.info(f"✅ [POST-PROCESS] Wrapped: {lr_display_name}")
            else:
                new_tools.append(tool)

    if found_any:
        # 에이전트의 도구 리스트를 통째로 교체
        root_agent.tools = new_tools
        logger.info(f"🚀 [POST-PROCESS] Agent tools updated. Total: {len(new_tools)}")
    
    return found_any

# 서버 시작 시 혹은 첫 요청 전 호출
root_agent = create_agent()

```

---

### 3. 컨트롤러에서 적용 (Controller.py)

사용자가 요청을 보낼 때, 도구가 아직 없다면 `refresh_agent_tools()`를 한 번 실행해 주는 방식이 가장 안전합니다.

```python
# controller.py 

@router.post("/v1/chat-device-info")
async def chat_device_info(...):
    # 포스트 프로세싱 실행: 도구가 아직 안 불려왔을 경우를 대비
    # (이미 불려왔다면 내부 로직에서 체크하여 빠르게 넘어가게 설계 가능)
    refresh_agent_tools() 
    
    return await _handle_chat_request(
        agent_name="device_info",
        # ... 나머지 인자 ...
    )

```

---

### 4. 이 방식의 장점

1. **부팅 속도 개선:** MCP 서버가 뜰 때까지 `create_agent`가 블록되지 않습니다.
2. **로그 가독성:** `agent.py`에서 접두어를 붙였기 때문에, 터미널 로그에 `Agent is calling tool: LR_kai-app_getAppUsageList`라고 찍혀서 래퍼 작동 여부를 즉시 알 수 있습니다.
3. **유연성:** MCP 서버가 나중에 추가되거나 재구동되어도 `refresh_agent_tools`만 호출하면 에이전트를 새로 만들 필요 없이 도구만 갈아끼울 수 있습니다.

**전문가의 조언:** 만약 포스트 프로세싱으로도 도구가 안 나타난다면, 그것은 타이밍 문제가 아니라 `allow_list`나 `long_running_patterns` 매칭 문제입니다. 위 코드를 적용한 후 터미널에 `✅ [POST-PROCESS] Wrapped: LR_...` 로그가 찍히는지 꼭 확인해 보세요! 찍힌다면 그때부터는 100% 롱러닝 래퍼를 사용하게 됩니다.


-----

소프트웨어 전문가로서, 에이전트가 호출하는 도구가 **일반 MCP 도구인지 아니면 롱러닝 래퍼(Wrapper)인지 로그상에서 이름만 보고도 100% 확신할 수 있도록** 접두어(`LR_`)를 추가하고, 이를 에이전트에게 등록하는 개선 코드를 작성해 드립니다.

이 코드를 적용하면 에이전트 로그에 `Calling tool: LR_kai-app_getAppUsageList`와 같이 찍히게 됩니다.

---

### 1. `long_running_wrapper.py` (이름 설정 기능 추가)

래퍼 내부에서 생성되는 도구 객체에 에이전트용 이름을 명시적으로 부여할 수 있도록 수정합니다.

```python
# long_running_wrapper.py 수정본

def create_long_running_tool(
    self,
    mcp_toolset: McpToolset,
    tool_name: str,
    agent_tool_name: str = None, # 에이전트에게 보여줄 이름 인자 추가
    estimated_duration: int = DEFAULT_ESTIMATED_DURATION,
    tool_timeout: int = DEFAULT_TOOL_TIMEOUT,
) -> LongRunningFunctionTool:
    
    async def long_running_mcp_function(**kwargs) -> dict[str, Any]:
        # 실행 시점에 어떤 이름을 통해 들어왔는지 로그를 남김
        current_name = agent_tool_name or tool_name
        logger.info(f"🧩 [LR-WRAPPER-HIT] Executing: {current_name} (Mapped to: {tool_name})")
        
        # ... 기존 로직 (operation_id 생성 및 background task 실행) ...
        # (생략: 이전 답변에서 드린 필터링 및 비동기 실행 로직 포함)
        return {
            "status": "started",
            "operation_id": f"op_{int(time.time())}",
            "message": f"작업 {current_name}이 백그라운드에서 시작되었습니다."
        }

    tool = LongRunningFunctionTool(func=long_running_mcp_function)
    
    # [중요] 에이전트가 이 이름으로 도구를 인식하고 로그에 남깁니다.
    tool.name = agent_tool_name if agent_tool_name else tool_name
    return tool

# 편의 함수 수정
def create_long_running_mcp_tool(mcp_toolset, tool_name, agent_tool_name=None, **kwargs):
    return mcp_long_running_manager.create_long_running_tool(
        mcp_toolset, tool_name, agent_tool_name=agent_tool_name, **kwargs
    )

```

---

### 2. `agent.py` (접두어 부여 및 도구 필터링 로직)

에이전트에 도구를 등록할 때 **롱러닝 대상은 접두어를 붙이고, 원본은 제외**하여 에이전트가 헷갈리지 않게 합니다.

```python
# agent.py 수정본

def create_agent():
    allow_list = ["get", "get_", "list_", "read_", "check_", "usp_", "kai-"]
    long_running_patterns = ["get_", "list_", "usage", "report", "kai-"] # 롱러닝 대상 패턴

    mcp_toolsets = get_tools(...) # 기존 로드 로직

    final_tools = [
        convert_timestamp_to_datetime,
        load_compacted_response,
        check_mcp_operation_status_tool,
    ]

    logger.info("🛠️ [BOOT] Starting tool registration...")

    for toolset in mcp_toolsets:
        actual_tools = getattr(toolset, "tools", [])
        for tool in actual_tools:
            tool_name = tool.name
            
            # 롱러닝 대상인지 확인
            is_lr = any(p in tool_name.lower() for p in long_running_patterns)
            
            if is_lr:
                # [개선 핵심] 이름 앞에 LR_ 을 붙여서 등록
                lr_display_name = f"LR_{tool_name}"
                logger.info(f"   - Registering Wrapped Tool: {lr_display_name}")
                
                lr_tool = create_long_running_mcp_tool(
                    toolset, 
                    tool_name,           # 실제 호출할 원본 이름
                    agent_tool_name=lr_display_name # 에이전트가 인식할 이름
                )
                final_tools.append(lr_tool)
            else:
                # 롱러닝 대상이 아닌 일반 도구는 그대로 추가
                logger.info(f"   - Registering Simple Tool: {tool_name}")
                final_tools.append(tool)

    # 이제 final_tools에는 'LR_...' 이름의 도구와 일반 도구만 섞여있고, 
    # 롱러닝 대상의 '원본 이름' 도구는 제거된 상태입니다.

    return Agent(
        # ... 나머지 설정 동일 ...
        tools=final_tools,
        instruction=f"{INSTRUCTION}\n참고: 이름이 'LR_'로 시작하는 도구는 실행 시 즉시 결과가 나오지 않고 operation_id를 반환합니다."
    )

```

---

### 3. 이렇게 하면 로그가 어떻게 바뀌나요?

이제 에이전트 실행 시 터미널 로그를 보시면 다음과 같이 명확히 구분됩니다.

* **성공적으로 래퍼를 탈 때:**
`[INFO] Agent is calling tool: 'LR_kai-app_getAppUsageList'`
`[INFO] 🧩 [LR-WRAPPER-HIT] Executing: LR_kai-app_getAppUsageList (Mapped to: kai-app_getAppUsageList)`
`[INFO] Response from tool: {'status': 'started', 'operation_id': 'op_12345'}`
* **만약 래퍼를 안 탔다면 (이전 방식):**
`[INFO] Agent is calling tool: 'kai-app_getAppUsageList'` (앞에 LR_이 없음)
`[INFO] Response from tool: [{"app": "YouTube", ...}]` (데이터가 바로 나옴)

### 4. 추가 팁: 부팅 시 도구 목록 확인

서버 실행 시 로그에 `Registering Wrapped Tool: LR_...` 가 20개 이상 출력되는지 확인하세요. 만약 이 로그가 안 찍힌다면 `long_running_patterns`와 `tool_name`이 매칭되지 않는 것이므로 패턴을 조정해야 합니다.

이제 이 코드를 적용하시면 에이전트가 어떤 경로로 쿼리를 날리는지 눈으로 즉시 확인하실 수 있습니다! 바로 적용해 보시겠어요?

----

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
