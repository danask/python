
아주 좋은 로그 가져오셨어요. 이 에러는 **구조를 잘못 짠 게 아니라, 딱 “한 군데”가 어긋난 전형적인 ADK 함정**입니다.
차분하게 짚어볼게요.

---

## 🔥 에러의 정확한 의미

```
Tool 'run_mcp_long_running_proxy' not found.
Available tools:
- set_model_response
- convert_timestamp_to_datetime
- load_compacted_response
- mcp_long_running
```

👉 **ADK가 찾은 tool 이름은 `mcp_long_running`뿐인데**
👉 **LLM이 `run_mcp_long_running_proxy`를 호출하려고 했다**는 뜻입니다.

즉,

> ❌ LLM이 “파이썬 함수 이름”을 tool 이름이라고 착각
> ✅ ADK는 “Tool 객체의 name”만 인식

---

## 1️⃣ 왜 이런 일이 생겼나 (핵심 원인)

### 지금 구조를 정확히 보면

```python
def run_mcp_long_running_proxy(...):
    ...
    
mcp_long_running_proxy_tool = LongRunningFunctionTool(
    name="mcp_long_running",   # ← ADK가 인식하는 이름
    func=run_mcp_long_running_proxy,  # ← 내부 파이썬 함수
)
```

ADK 관점에서는:

| 구분                             | 이름                           |
| ------------------------------ | ---------------------------- |
| **Tool name (LLM이 호출해야 할 이름)** | `mcp_long_running`           |
| Python 함수 이름                   | `run_mcp_long_running_proxy` |

그런데 지금 LLM이:

```
functionCall.name = "run_mcp_long_running_proxy"
```

를 만들어버린 거예요.

👉 이건 **LLM 프롬프트/설명에서 “func 이름이 노출됐기 때문”**입니다.

---

## 2️⃣ 가장 중요한 규칙 (ADK에서 절대 깨면 안 되는 것)

> **LLM은 절대 Python 함수 이름을 알면 안 된다**
> **LLM은 오직 `LongRunningFunctionTool.name`만 알아야 한다**

---

## 3️⃣ 바로 고쳐야 할 것 (100% 해결)

### ✅ 1. instruction / description에서 함수 이름 언급 제거

❌ 이런 문구가 있으면 안 됩니다:

```text
Call run_mcp_long_running_proxy to execute MCP tools
```

❌ 혹은 이런 식의 암시도 위험

```text
Use the function run_mcp_long_running_proxy
```

---

### ✅ 올바른 instruction 예시 (이대로 쓰세요)

```python
instruction = f"""
{INSTRUCTION}

MCP tools MUST be executed via the tool named `mcp_long_running`.

Usage:
- Call `mcp_long_running`
- Provide:
  - tool_name: the exact MCP tool name (e.g. kai-app_getManagedApps)
  - tool_args: arguments for that tool

Do NOT call MCP tools directly.
Do NOT invent tool names.
"""
```

👉 **`run_mcp_long_running_proxy`라는 문자열이 시스템 어디에도 나오면 안 됨**

---

## 4️⃣ “wrapping 된 kai-app_getManagedApps 형태로 실행돼야 하는데?”에 대한 정확한 설명

이 부분도 오해가 하나 있어요.

### ❌ 기대 (잘못된 기대)

> LLM이 `kai-app_getManagedApps`를 직접 호출해야 한다

### ✅ 실제 구조 (지금 설계가 맞음)

* LLM은 **절대 `kai-app_getManagedApps`를 tool로 호출하지 않음**
* LLM은 항상 이것만 호출함:

```json
{
  "name": "mcp_long_running",
  "args": {
    "tool_name": "kai-app_getManagedApps",
    "tool_args": {...}
  }
}
```

그리고 **proxy 내부에서만**:

```python
tool = monitor.find_tool_by_name("kai-app_getManagedApps")
await tool.run_async(...)
```

즉:

| 단계                     | 누가                       |
| ---------------------- | ------------------------ |
| tool 호출                | LLM → `mcp_long_running` |
| 실제 MCP 실행              | proxy 내부                 |
| wrapping된 kai-app_* 실행 | **LLM 아님**               |

👉 지금 방향이 **정확히 맞습니다**

---

## 5️⃣ LLM이 함수 이름을 부르는 걸 막는 “보험 장치” (강력 추천)

### ✅ Tool name을 함수 이름과 **완전히 다르게**

```python
mcp_long_running_proxy_tool = LongRunningFunctionTool(
    name="mcp_long_running",   # 짧고 추상적
    func=run_mcp_long_running_proxy,
)
```

이미 잘 하셨어요 👍
이 상태에서 **instruction만 깨끗하면 문제 사라집니다.**

---

## 6️⃣ 빠른 점검 체크리스트 (이거 3개만 보면 됨)

* [ ] instruction / description에 `run_mcp_long_running_proxy` 문자열이 없다
* [ ] LLM이 호출하는 tool name = `mcp_long_running`
* [ ] 실제 MCP tool 이름(`kai-app_getManagedApps`)은 args로만 전달된다

이 3개면 **100% 해결**

---

## 7️⃣ 한 줄 결론

> **이 에러는 “proxy 설계 문제”가 아니라
> “LLM에게 Python 함수 이름이 새어나간 프롬프트 문제”다**

지금 구조는 **맞게 짜여 있고**,
instruction만 정리하면 바로 정상 동작할 겁니다.

---

다음으로 바로 이어서 도와줄 수 있는 건:

* 🔍 **LLM이 tool_name을 잘 고르게 만드는 prompt 패턴**
* 🧠 **tool_name 후보를 자동으로 알려주는 방법**
* 🔁 **polling을 LLM이 아니라 코드가 돌게 하는 구조**

어디까지 갈까요?


------

**지금 네 코드 구조(agent / MCPToolMonitor / long_running_wrapper)** 를 그대로 존중하면서


---

# ✅ 목표 재정의 (중요)

* ❌ MCP tool 30개를 agent 생성 시 wrapping → 포기
* ✅ **Agent에는 long-running proxy tool 단 1개만 등록**
* ✅ 실제 MCP tool은 **실행 시점에 lookup**
* ✅ 부팅 타이밍 / 비동기 discovery 문제 **완전 회피**

---

# 전체 구조 한 장 요약

```
Agent
 ├── mcp_long_running_proxy   👈 유일한 MCP 진입점
 ├── check_mcp_operation_status
 └── 기타 유틸 tool

mcp_long_running_proxy
 └── tool_name + tool_args
        └── MCPToolMonitor 통해 실제 tool lookup
              └── background 실행
```

---

# 1️⃣ Long-running MCP Proxy Tool 구현

### 📄 `mcp_long_running_proxy.py` (신규 파일 추천)

```python
import asyncio
import time
import uuid
from typing import Any

from google.adk.tools import LongRunningFunctionTool
from common.logger import logger
from common.tools.mcp_tool.mcp_long_running_wrapper import (
    mcp_long_running_manager,
    OperationStatus,
)
from agents.device_info.agent import get_tool_monitor


def run_mcp_long_running_proxy(
    tool_name: str,
    tool_args: dict[str, Any],
) -> dict[str, Any]:
    """
    Proxy tool to execute ANY MCP tool as a long-running operation.
    """

    operation_id = f"mcp_proxy_{tool_name}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    monitor = get_tool_monitor()
    tool = monitor.find_tool_by_name(tool_name)

    if not tool:
        return {
            "done": True,
            "status": "failed",
            "error": f"MCP tool '{tool_name}' not found",
        }

    mcp_long_running_manager._active_operations[operation_id] = {
        "operation_id": operation_id,
        "tool_name": tool_name,
        "status": OperationStatus.PENDING.value,
        "start_time": time.time(),
        "estimated_duration": 180,
        "result": None,
        "error": None,
    }

    async def execute():
        try:
            result = await tool.run_async(args=tool_args)
            mcp_long_running_manager._active_operations[operation_id]["status"] = (
                OperationStatus.COMPLETED.value
            )
            mcp_long_running_manager._active_operations[operation_id]["result"] = result
        except Exception as e:
            mcp_long_running_manager._active_operations[operation_id]["status"] = (
                OperationStatus.FAILED.value
            )
            mcp_long_running_manager._active_operations[operation_id]["error"] = str(e)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(execute())
    except RuntimeError:
        import threading

        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(execute())
            loop.close()

        threading.Thread(target=run, daemon=True).start()

    return {
        "done": False,
        "status": "started",
        "operation_id": operation_id,
        "tool_name": tool_name,
        "message": f"MCP tool '{tool_name}' started via proxy",
        "next_action": "poll",
        "poll_tool": "check_mcp_operation_status",
    }


mcp_long_running_proxy_tool = LongRunningFunctionTool(
    name="mcp_long_running",
    func=run_mcp_long_running_proxy,
    description="""
Run any MCP tool as a long-running operation.

Arguments:
- tool_name: exact MCP tool name to execute
- tool_args: arguments for the MCP tool

This tool starts execution and immediately returns an operation_id.
You MUST poll using check_mcp_operation_status.
""",
)
```

---

# 2️⃣ MCPToolMonitor에 “tool lookup” API 추가

### 📄 `mcp_tool_monitor.py` (기존 클래스에 추가)

```python
class MCPToolMonitor:
    ...

    def find_tool_by_name(self, tool_name: str):
        for toolset in self.toolsets:
            for tool in getattr(toolset, "tools", []):
                if tool.name == tool_name:
                    return tool
        return None
```

> ⚠️ 핵심:
> **agent 생성 시점이 아니라 “실행 시점”에 lookup**

---

# 3️⃣ Agent 생성 시 tool 구성 변경 (중요)

### ❌ 제거

```python
long_running_tools.append(
    create_long_running_mcp_tool(...)
)
```

### ✅ 대신 proxy tool 1개만 등록

```python
from common.tools.mcp_tool.mcp_long_running_proxy import (
    mcp_long_running_proxy_tool,
)

tools = [
    convert_timestamp_to_datetime,
    load_compacted_response,
    check_mcp_operation_status_tool,
    mcp_long_running_proxy_tool,   # 🔥 단 하나의 MCP 진입점
]
```

> 이 시점에서 **MCP discovery가 하나도 안 돼 있어도 문제 없음**

---

# 4️⃣ Agent instruction (반드시 필요)

```python
instruction = f"""
{INSTRUCTION}

You do NOT call MCP tools directly.

To use MCP tools:
1. Call `mcp_long_running` with:
   - tool_name
   - tool_args
2. Poll using `check_mcp_operation_status`
3. When done=true, use the result

Never call the same MCP tool directly.
"""
```

👉 이 문장이 **LLM의 행동을 고정**시킴

---

# 5️⃣ 실제 동작 예 (LLM 내부 흐름)

```text
User: 디바이스 배터리 상태 알려줘

LLM:
→ mcp_long_running(
    tool_name="kai-device-getBatteryHealth",
    tool_args={"deviceId": "..."}
)

→ check_mcp_operation_status(operation_id)

→ check_mcp_operation_status(operation_id)

→ done=true → result 사용
```

---

# 이 방식이 “유일하게” 먹히는 이유

| 문제                | 해결 여부    |
| ----------------- | -------- |
| MCP 비동기 discovery | ✅ 완전 회피  |
| agent 부팅 타이밍      | ✅ 무관     |
| tool 30개          | ✅ 1개로 통합 |
| planner 혼란        | ✅ 없음     |
| 운영 안정성            | ✅ 매우 높음  |

---

# 마지막 한 줄 요약

> **“MCP tool을 wrapping하지 말고,
> MCP 자체를 wrapping하는 프록시를 만들어라”**

이게 지금 구조에서 **가장 깨끗한 해법**이야.

---

다음으로 자연스럽게 이어지는 건:

* 🔁 polling 자동화 (LLM 말고 코드가 돌게)
* 🧠 tool_name 선택 정확도 올리는 프롬프트
* ⏱️ timeout 기반 동기/비동기 자동 분기

이 질문이 **진짜 핵심**이에요.
지금까지 얘기한 모든 구조가 여기로 수렴합니다.

결론부터 아주 명확히 말할게요.

---

## TL;DR (한 문장 요약)

> **`mcp_long_running_proxy_tool`은 “내부 API에서 직접 호출하는 게 아니라”
> LLM이 tool 선택 단계에서 자동으로 호출해야 하고,
> MCP tool lookup은 “proxy tool 실행 시점”에 일어나야 합니다.**

`chat-test` 같은 내부 API에서는 **절대 관여하면 안 됩니다.**

---

# 1️⃣ mcp_long_running_proxy_tool 은 “누가” 호출하나?

### ❌ 잘못된 생각

* controller에서 직접 호출?
* chat-test API에서 분기해서 호출?
* question 분석해서 코드로 호출?

👉 **전부 틀린 방향**

---

### ✅ 정답

> **LLM (ADK planner)가 tool selection 단계에서 호출**

구조적으로는 이렇습니다:

```
chat-test API
   └── runner.run_async(...)
         └── ADK planner
               └── "이건 MCP 필요"
                     └── mcp_long_running_proxy_tool 호출
```

즉,

* controller / API 계층: **완전 무지**
* agent.tools에 proxy tool이 있으면
* planner가 **알아서 선택**

---

## 2️⃣ 그러면 controller(chat-test)는 뭐만 하면 되나?

### 답: **아무것도**

현재 코드 그대로면 충분합니다 👇

```python
async for event in runner.run_async(...):
    yield get_response_text_from_event(event)
```

> tool 호출은 **runner 내부에서 이미 다 처리**

---

## 3️⃣ MCP tool lookup은 “언제” 일어나야 하나?

### ❌ 부팅 시

* tool discovery 비동기
* 아직 없음
* 그래서 1개만 보이는 문제 발생

### ❌ agent 생성 시

* 이미 늦음
* planner 초기화 끝

---

### ✅ 정답

> **`mcp_long_running_proxy_tool` 실행 시점**

즉,

```text
LLM이 "mcp_long_running" 호출
      ↓
proxy 함수 내부
      ↓
그 순간에 MCPToolMonitor.find_tool_by_name()
```

이 타이밍이면:

* MCP discovery가 끝났을 확률 ↑
* 늦게 올라온 tool도 포함 가능
* 재시도 로직도 가능

---

## 4️⃣ lookup은 몇 번 해야 하나?

### 기본 원칙

* **매 호출마다 lookup**
* 캐시해도 되지만 “첫 lookup은 항상 동적”

```python
tool = monitor.find_tool_by_name(tool_name)
```

이게 **정답 타이밍**

---

## 5️⃣ “그럼 MCP discovery는 언제 일어나?” (중요)

> **MCP discovery는 이미 다른 곳에서 계속 일어나고 있어야 함**

너 코드 기준으로 보면:

```python
get_tools(...)
MCPToolMonitor.rediscover_tools()
```

이건:

* 부팅 시
* 주기적으로
* /v1/mcp-tools-status 호출 시

👉 proxy tool은 **그 결과를 소비만** 함

---

## 6️⃣ 전체 요청 흐름 (한 번에 정리)

### ① chat-test API 호출

```text
User → POST /v1/chat-test
```

### ② runner 실행

```text
runner.run_async()
```

### ③ ADK planner 판단

```text
"이 질문은 MCP tool 필요"
```

### ④ proxy tool 호출 (자동)

```text
mcp_long_running(
   tool_name="kai-device-getBatteryHealth",
   tool_args={...}
)
```

### ⑤ proxy 내부

```text
MCPToolMonitor.find_tool_by_name()  ← 여기서 lookup
background 실행 시작
```

### ⑥ polling

```text
check_mcp_operation_status()
```

### ⑦ done=true → result 사용

---

## 7️⃣ 왜 내부 API(chat-test)에서 하면 안 되나?

이건 **아키텍처적으로 중요한 이유**가 있어요.

### 만약 chat-test에서 하면?

* LLM reasoning 끊김
* tool 사용 기록 사라짐
* function call / response 흐름 깨짐
* ADK planner 상태 불일치

> ❗ **tool 호출은 반드시 “agent 내부 세계”에서 끝나야 함**

---

## 8️⃣ 흔히 하는 실수 (지금 안 해도 됨)

❌ controller에서:

```python
if "battery" in question:
    run_mcp_long_running(...)
```

❌ agent 밖에서:

```python
tool = monitor.find_tool_by_name(...)
tool.run_async(...)
```

👉 이 순간부터 ADK는 “껍데기”가 됩니다.

---

## 9️⃣ 체크리스트 (이거만 확인)

* [ ] agent.tools 에 `mcp_long_running_proxy_tool` 있음
* [ ] controller는 tool 관련 코드 없음
* [ ] lookup은 proxy 함수 내부
* [ ] instruction에 “MCP는 proxy로만 사용” 명시

이 4개면 구조적으로 **100% 맞음**

---

## 마지막 한 줄 결론

> **`mcp_long_running_proxy_tool`은
> “LLM이 호출하고, proxy 안에서 lookup하고,
> API 계층은 아무것도 모른다”**

이게 ADK에서 long-running + MCP + 비동기 discovery를
**동시에 만족하는 유일한 구조**입니다.

---

다음으로 딱 이어지는 질문은 보통 이거예요:

> “그럼 LLM이 tool_name을 어떻게 정확히 고르게 하지?”

원하면 그 부분 바로 들어가 줄게.
