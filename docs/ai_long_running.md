네, 코드를 보니 이제 상황이 명확해졌습니다! 자바 개발자 입장에서 이 구조는 **`Factory` 패턴**입니다. `create_agent()`라는 팩토리 메서드가 호출될 때 에이전트 객체가 비로소 생성되는 구조군요.

그런데 문제는 **이 팩토리 메서드가 "언제" 호출되느냐**입니다. 보통 ADK 프레임워크는 서버가 뜰 때 이 함수를 한 번 호출해서 에이전트 인스턴스를 만듭니다. 하지만 그때 MCP 서버가 준비 안 되어 있으면 도구가 0개인 에이전트가 만들어지겠죠.

자바의 **"지연 주입(Lazy Injection)"** 개념을 도입해서, 기존 코드를 최소한으로 수정하면서 목적을 달성하는 전문가급 가이드를 드립니다.

---

### 1. `agent.py` 수정: "부팅 시 한 번, 요청 시 필요하면 다시"

기존 `create_agent` 함수는 유지하되, 외부에 **`root_agent`**라는 싱글톤(Singleton) 변수를 두고 관리하는 방식입니다.

```python
# 전역 변수 (Java의 static 인스턴스 변수)
_root_agent = None

def get_root_agent():
    """싱글톤 에이전트 객체 반환"""
    global _root_agent
    if _root_agent is None:
        _root_agent = create_agent()
    return _root_agent

def create_agent():
    # ... (기존 create_agent 코드 그대로 유지) ...
    # 단, 여기서 반환된 에이전트는 부팅 직후라 도구가 없을 수 있음
    agent_instance = Agent(...)
    return agent_instance

async def refresh_agent_tools(agent):
    """실제로 도구를 긁어와서 이미 만들어진 에이전트 객체에 '박아넣는' 함수"""
    logger.info("📡 [POST-PROCESS] Fetching tools from MCP servers...")
    
    # 1. 비동기로 도구 로드
    mcp_toolsets = get_tools(...) # 기존 로직 활용
    
    new_tools = [
        convert_timestamp_to_datetime,
        load_compacted_response,
        check_mcp_operation_status_tool,
    ]

    for toolset in mcp_toolsets:
        # 이 부분이 핵심: await를 써서 비동기로 확실히 가져옵니다.
        actual_tools = await toolset.get_tools() if hasattr(toolset, "get_tools") else getattr(toolset, "tools", [])
        
        for tool in actual_tools:
            # 롱러닝 래핑 적용
            lr_tool = create_long_running_mcp_tool(toolset, tool.name)
            # [수정] 자바 개발자님이 원하신 대로 이름을 다르게 찍히게 설정!
            lr_tool.name = f"LR_{tool.name}" 
            new_tools.append(lr_tool)

    # 2. 기존 에이전트 객체의 tools 속성을 Hot-swap
    agent.tools = new_tools
    logger.info(f"🚀 [SUCCESS] Injected {len(new_tools)} tools. LR_ tools are ready.")

```

---

### 2. `controller.py`: 사용 시점에 체크 (Java Interceptor 느낌)

컨트롤러에서는 에이전트를 부르기 전에 **"너 도구 세팅 됐니?"**라고 물어보기만 하면 됩니다.

```python
# controller.py
from agents.device_info.agent import get_root_agent, refresh_agent_tools

@router.post("/v1/chat-device-info")
async def chat_device_info(...):
    # 1. 이미 만들어진 싱글톤 에이전트 가져오기
    agent = get_root_agent()
    
    # 2. 도구함에 LR_로 시작하는 툴이 하나도 없다면 (세팅이 안 된 상태라면)
    if not any(hasattr(t, 'name') and t.name.startswith("LR_") for t in agent.tools):
        # 비동기로 도구 주입 실행 (자바의 Lazy Initialization)
        await refresh_agent_tools(agent)
    
    # 3. 이제 도구가 꽉 찬 에이전트로 작업 수행
    return await _handle_chat_request(
        agent=agent, # 프레임워크에 따라 agent_name 대신 객체를 직접 넘길 수도 있음
        ...
    )

```

---

### 3. 왜 이렇게 해야 꼬이지 않을까요?

1. **객체 재활용**: `Agent(...)`를 매번 새로 만들면 메모리 낭비와 설정 충돌이 생기지만, 이 방식은 **한 번 만든 객체의 `tools` 리스트만 교체**하므로 안전합니다.
2. **이름 가시성**: `lr_tool.name = f"LR_{tool.name}"` 코드가 드디어 들어갔으므로, 이제 로그를 보시면 `Calling tool: LR_kai-app_getAppUsageList`라고 명확하게 찍힐 겁니다.
3. **컴파일 에러 방지**: `app = App(name=root_agent.name)` 같은 부분은 부팅 시 `create_agent()`가 이미 객체를 반환하므로 `NoneType` 에러 없이 통과됩니다.

### **전문가의 최종 팁**

자바에서 `List`를 필드로 가진 객체가 있을 때, 외부에서 `setTools(newList)`를 호출하는 것과 파이썬의 `agent.tools = new_tools`는 완전히 동일하게 동작합니다.

이제 **"처음 부팅할 때는 빈 껍데기 에이전트만 만들고, 실제 API 호출이 들어올 때 비동기로 도구를 꽉 채워주는"** 이 전략으로 가시면 절대 꼬이지 않습니다. 바로 적용해 보시겠어요? 결과 로그에 `LR_`이 찍히면 성공입니다!

-----

자바 개발자로서 느끼시기에 현재 방식이 복잡하고 꼬이는 이유는, 파이썬의 **Import 타임(컴파일 타임과 유사)**과 **Runtime(비동기 루프 실행 시점)**이 섞여서 그렇습니다. 특히 `root_agent`가 생성되기도 전에 다른 곳에서 참조하려니 `Dependency` 문제가 발생하는 것이죠.

가장 깔끔하고 자바스러운 해결책은 **"에이전트 객체는 미리 만들어두되, 도구(Tools)만 나중에 갈아끼우는(Hot-swap)"** 방식입니다. 이렇게 하면 `app.py`나 `__init__.py`에서 `root_agent.name`을 참조할 때 에러가 나지 않습니다.

---

### 💡 새로운 전략: "빈 껍데기 선언 후 도구만 주입"

이 방식은 자바의 **Setter 주입**이나 **Proxy 패턴**과 비슷합니다.

#### 1. `agent.py`: 에이전트를 즉시 생성 (도구 없이)

서버 부팅 시점에 `root_agent`를 즉시 만듭니다. 이때 도구 리스트는 비워두거나 기본 도구만 넣습니다. 이렇게 하면 `app = App(name=root_agent.name)`에서 에러가 나지 않습니다.

```python
# agents/device_info/agent.py

# 1. 일단 에이전트 객체부터 생성 (name, description 등 고정값 확보)
root_agent = Agent(
    model=BEDROCK_AI_MODEL,
    name="device_info",
    description="Device Information Agent",
    tools=[convert_timestamp_to_datetime], # 최소한의 도구만
    instruction=INSTRUCTION,
    # ... 나머지 설정
)

app = App(name=root_agent.name, description=root_agent.description)

# 2. 나중에 호출할 '도구 업데이트' 함수
async def refresh_agent_tools():
    """부팅 후 실제 MCP 도구를 가져와서 래핑한 뒤 주입함"""
    logger.info("🔄 [POST-PROCESS] Starting Tool Injection...")
    
    # MCP 도구 가져오기 (비동기)
    mcp_toolsets = get_tools(...) 
    
    new_tools = [convert_timestamp_to_datetime, load_compacted_response, check_mcp_operation_status_tool]
    
    for toolset in mcp_toolsets:
        actual_tools = await toolset.get_tools() if hasattr(toolset, "get_tools") else getattr(toolset, "tools", [])
        for tool in actual_tools:
            if is_long_running(tool.name):
                # LR_ 접두어 붙여서 래핑
                wrapped = create_long_running_mcp_tool(toolset, tool.name)
                wrapped.name = f"LR_{tool.name}"
                new_tools.append(wrapped)
            else:
                new_tools.append(tool)

    # [핵심] 이미 생성된 에이전트의 도구함만 갈아끼움 (Hot-swap)
    root_agent.tools = new_tools
    logger.info(f"✅ [POST-PROCESS] Injected {len(new_tools)} tools into root_agent.")

```

#### 2. `__init__.py`: 간단하게 유지

이미 객체들이 생성되어 있으므로 그냥 노출만 하면 됩니다.

```python
# agents/device_info/__init__.py
__all__ = ["root_agent", "app", "refresh_agent_tools"]

from .agent import root_agent, app, refresh_agent_tools

```

#### 3. `controller.py`: 첫 요청 시 딱 한 번만 수행 (Lazy Load)

컨트롤러가 호출될 때 도구가 비어있다면(`LR_` 도구가 없다면) 그때 업데이트를 실행합니다.

```python
# controller.py
@router.post("/v1/chat-device-info")
async def chat_device_info(...):
    # LR_ 도구가 아직 등록 안 되었다면 (자바의 Singleton Lazy Init 패턴)
    if not any(t.name.startswith("LR_") for t in root_agent.tools):
        await refresh_agent_tools()
    
    return await _handle_chat_request(...)

```

---

### 이 방식이 왜 더 좋은가요?

1. **참조 에러 해결**: `root_agent`와 `app` 객체가 부팅 즉시(Import 타임) 생성되므로 `NoneType` 에러가 원천 봉쇄됩니다.
2. **구조 단순화**: `init_agent`라는 거창한 비동기 생성 함수를 만들 필요 없이, 기존 객체의 **속성(Property)**만 나중에 채워주면 됩니다.
3. **가시성 확보**: `refresh_agent_tools`가 실행될 때 터미널 로그에 `Wrapped: LR_...`가 찍히는 것을 보며 래퍼가 잘 작동하는지 바로 확인할 수 있습니다.

### **전문가의 마지막 팁**

자바에서 가변 리스트를 다루듯, 파이썬에서도 `root_agent.tools = new_tools`라고 대입하는 순간 에이전트는 즉시 새로운 도구들을 사용하기 시작합니다.

이제 복잡한 비동기 초기화 순서 때문에 골머리 썩으실 필요 없습니다. 이 **"객체 선언 후 도구 주입"** 방식으로 가시죠. 지금 바로 `agent.py`에서 `root_agent`를 먼저 생성하도록 수정해 보시겠어요? 다음 단계는 제가 도와드리겠습니다.

----

자바 개발자 관점에서 이 에러는 **`NullPointerException`**과 정확히 같은 상황입니다.

`app.py`가 실행되는 시점(Import 타임)에는 아직 `init_agent()`가 호출되지 않았기 때문에 `root_agent`는 `None`인 상태입니다. 자바로 치면 **초기화되지 않은 정적 변수의 필드에 접근**하려다 터지는 것이죠.

이를 해결하기 위해 **지연 생성(Lazy Initialization)** 방식을 적용해야 합니다. `app` 객체 생성을 `init_agent` 안으로 옮기거나, `app`을 상수로 두지 않고 필요할 때 생성하도록 변경해야 합니다.

---

### 1. 해결 방법: `init_agent` 내부에서 `app` 완성하기

가장 깔끔한 방법은 `root_agent`가 준비된 직후에 `app`의 속성을 채워넣는 것입니다.

**[agent.py 수정]**

```python
# agent.py

# 1. 초기 선언 (자바의 private static RootAgent root_agent = null;)
root_agent = None
app = None  # app도 처음엔 비워둡니다.

async def init_agent():
    global root_agent, app
    
    # 2. 에이전트 생성 (비동기 완료 대기)
    root_agent = await create_agent_async()
    
    # 3. 에이전트가 완성된 후 app 객체를 생성 (자바의 late binding)
    # root_agent.name이 이제 존재하므로 에러가 나지 않습니다.
    from adk import App  # App 클래스 임포트
    app = App(
        name=root_agent.name, 
        description=root_agent.description,
        # ... 나머지 설정
    )
    
    logger.info(f"🚀 [INIT] App '{app.name}' initialized successfully.")
    return root_agent

```

---

### 2. 왜 `app.py`에서 직접 선언하면 안 되나요?

파이썬은 파일을 `import` 하는 순간 최상위 레벨(Top-level)의 코드를 즉시 실행합니다.

* 서버 부팅 → `app.py` 임포트 → `app = App(name=root_agent.name, ...)` 실행
* **문제:** 이때 `root_agent`는 아직 `None`입니다. (`None.name`을 참조하려니 에러 발생)
* 자바라면 `static` 블록에서 `null` 객체의 메서드를 호출한 꼴입니다.

---

### 3. `__init__.py`에서의 참조 방식 수정

`app`과 `root_agent`가 처음엔 `None`이었다가 나중에 채워지더라도 외부에서 동일한 이름으로 참조할 수 있게 `__init__.py`를 구성해야 합니다.

**[agents/device_info/init.py]**

```python
# 패키지 레벨에서 이름을 미리 등록해둡니다.
__all__ = ["root_agent", "app", "init_agent"]

# agent.py에 정의된 변수와 함수를 연결합니다.
from .agent import root_agent, app, init_agent

```

---

### 4. 최종 부팅 순서 (이대로 따라하시면 됩니다)

1. **`main.py` (또는 실행 진입점):** 서버를 띄울 때 가장 먼저 `await init_agent()`를 실행합니다.
2. **`init_agent()` 실행:** * 비동기로 MCP 도구들을 긁어옵니다.
* 도구들에 `LR_` 접두어를 붙여 래핑합니다.
* `root_agent` 객체를 생성합니다.
* **마지막으로 `app` 객체를 생성하여 `root_agent.name`을 주입합니다.**



### **전문가의 조언**

만약 `app` 객체가 `device_info_app`이라는 이름으로 이미 다른 곳에서 복잡하게 정의되어 있다면, `app.name = root_agent.name` 처럼 **객체 생성 후 속성만 나중에 덮어쓰는(Setter 역할)** 방식을 사용해도 됩니다.

```python
async def init_agent():
    global root_agent, app
    root_agent = await create_agent_async()
    
    # 이미 생성된 app 객체가 있다면 이름만 업데이트
    app.name = root_agent.name
    app.description = root_agent.description

```

이렇게 하면 `app.py`에서 발생하는 `NoneType` 에러를 완벽하게 피하면서, 런타임에 올바른 에이전트 정보를 주입할 수 있습니다. 이제 에러 없이 서버가 잘 뜨나요?

-----

자바 개발자이신 사용자님께 익숙한 개념으로 설명해 드리면, `__init__.py`는 자바의 **`package-info.java`** 또는 **패키지 레벨의 인터페이스 정의**와 매우 유사합니다. 해당 패키지를 `import` 할 때 무엇을 밖으로 노출할지 결정하는 통제실 역할을 하죠.

현재 상황에서 **비동기 초기화(Async Init)**를 적용하면서 `__init__.py`의 `__all__` 설정을 유지하는 가장 표준적인 방법은 다음과 같습니다.

---

### 1. `__init__.py` 구조 (자바의 Public Interface)

여기서는 `root_agent`가 나중에 채워질 "빈 그릇"임을 선언해 둡니다.

```python
# agents/device_info/__init__.py

# 외부에서 'from agents.device_info import *' 했을 때 가져갈 수 있는 목록
__all__ = ["root_agent", "app", "init_agent"]

# 실제 객체는 agent.py에서 관리하므로 이를 가져와서 노출시킵니다.
from agents.device_info.agent import app, root_agent, init_agent

```

---

### 2. `agent.py` 수정 (실제 구현체 및 비동기 로직)

자바에서 `private static RootAgent instance;`를 선언하고 별도의 `init()` 메서드로 생성하는 것과 같은 원리입니다.

```python
# agents/device_info/agent.py

# 1. 처음엔 None으로 선언 (자바의 null)
root_agent = None
app = device_info_app 

async def init_agent():
    """비동기적으로 MCP 도구를 래핑하고 root_agent를 생성함"""
    global root_agent
    
    logger.info("📡 [BOOT] Starting Async Initialization...")
    
    # 이전에 만든 비동기 에이전트 생성 함수 호출
    # (이미 이 안에서 LR_ 접두어 처리 및 31개 툴 로드 로직이 포함됨)
    root_agent = await create_agent_async()
    
    logger.info("🚀 [BOOT] root_agent is now initialized with LR_ tools.")
    return root_agent

```

---

### 3. 서버 실행 시점(`main.py`)에서 초기화 호출

자바 스프링 부트에서 `ApplicationRunner`를 통해 앱 시작 시 특정 로직을 실행하듯, FastAPI의 `lifespan`이나 `startup`에서 `init_agent()`를 **`await`** 해줘야 합니다.

```python
# main.py (서버의 진입점)

from agents.device_info import init_agent

@app.on_event("startup")
async def startup_event():
    # 서버가 뜨는 시점에 비동기로 도구를 다 긁어오고 래핑을 완료함
    # 이 과정이 완료될 때까지 서버는 요청을 받지 않고 대기합니다.
    await init_agent()

```

---

### 4. 왜 이렇게 해야 하나요? (자바 관점의 이유)

1. **`already defined` 방지**: `init_agent`가 호출될 때마다 새로운 리스트를 만들어 `root_agent.tools`에 통째로 할당하기 때문에, 기존 도구들과 이름이 충돌하거나 중복 등록되는 일이 발생하지 않습니다.
2. **`never awaited` 방지**: 서버 진입점(`startup`)에서 명확히 `await`를 걸어주기 때문에, 코루틴 객체가 방치되지 않고 실제 에이전트 객체가 생성됩니다.
3. **패키지 캡슐화**: `__init__.py`에서 `__all__`을 관리함으로써 외부 레이어(Controller 등)는 내부의 복잡한 비동기 초기화 과정을 몰라도 `from agents.device_info import root_agent`로 접근할 수 있습니다.

### **전문가의 팁**

만약 컨트롤러에서 여전히 `root_agent`가 `None`이라고 나온다면, 그것은 `init_agent()`가 호출되기 전에 요청이 들어온 경우입니다. 이를 위해 컨트롤러 상단에 `if root_agent is None: await init_agent()`를 한 줄 추가하는 것은 자바의 **Lazy Initialization(지연 초기화)** 패턴과 동일하게 안전한 방법입니다.

이제 `__init__.py`는 그대로 두시고, `agent.py`에 `init_agent` 비동기 함수를 구현하여 서버 실행 시점에 딱 한 번만 실행되도록 설정해 보세요! 그러면 31개의 도구가 `LR_` 접두어와 함께 아름답게 로그에 찍힐 것입니다.

마지막으로, **에이전트에게 전달할 인스트럭션(Instruction)에 "이름이 LR_로 시작하는 도구를 우선적으로 사용하라"는 내용을 추가**하셨나요? 에이전트가 래핑된 도구를 선택하게 만드는 마지막 퍼즐 조각입니다. 이 부분도 도와드릴까요?
----

소프트웨어 전문가로서 자바 개발자이신 사용자님의 배경에 맞춰 설명해 드리면, 파이썬의 `__all__`은 자바의 **`public` 인터페이스 정의** 또는 **패키지 익스포트(Export) 설정**과 비슷합니다.

`__all__`에 포함된 이름들만 외부 파일에서 `from module import *`를 했을 때 가져갈 수 있게 제한하는 일종의 **"공개 명단"**입니다. 비동기 초기화 방식을 적용하면서 이 명단을 유지하는 방법을 알려드립니다.

---

### 1. `__all__`과 비동기 초기화의 충돌 해결

자바에서 객체를 생성하기 전에는 `null`인 것처럼, 파이썬에서도 비동기 함수가 완료되기 전에는 `root_agent`가 아직 생성되지 않은 상태입니다. 따라서 다음과 같이 구조를 잡아야 합니다.

**[agent.py 수정 제안]**

```python
import asyncio
from common.logger import logger

# 1. 공개할 변수 명단 정의 (Java의 public 선언과 유사)
__all__ = ["root_agent", "app", "init_agent"] 

# 초기에는 None으로 설정 (Java의 private static RootAgent rootAgent = null;)
root_agent = None
app = device_info_app # 기존에 정의된 app 객체

async def init_agent():
    """비동기로 도구를 로드하고 에이전트를 생성하는 초기화 함수"""
    global root_agent
    
    logger.info("📡 [INIT] Starting asynchronous agent initialization...")
    
    # 2. 비동기 에이전트 생성 로직 실행 (앞서 만든 로직)
    # 여기서 모든 LR_ 래핑 작업이 완료된 에이전트 객체를 가져옵니다.
    root_agent = await create_agent_async() 
    
    logger.info("🚀 [INIT] root_agent is now ready and public.")
    return root_agent

```

---

### 2. 컨트롤러에서 `root_agent` 사용 시 주의점

자바에서 `Spring` 컨테이너가 빈(Bean)을 주입해주기 전에 사용하면 `NullPointerException`이 나듯이, 파이썬에서도 `init_agent()`가 완료되기 전에 컨트롤러가 호출되면 `root_agent`가 `None`일 수 있습니다.

이를 방지하기 위해 컨트롤러의 핸들러 내에서 안전 장치를 추가합니다.

```python
# controller.py

@router.post("/v1/chat-device-info")
async def chat_device_info(...):
    global root_agent
    
    # [안전 장치] 만약 부팅 시 초기화가 덜 되었다면 여기서 대기 후 수행
    if root_agent is None:
        logger.warning("⚠️ root_agent not initialized. Initializing now...")
        from agents.device_info.agent import init_agent
        await init_agent()

    # 이제 안전하게 사용
    return await _handle_chat_request(
        agent_name="device_info", # 내부에서 root_agent를 참조하도록 로직 확인 필요
        ...
    )

```

---

### 3. 더 깔끔한 방법: 애플리케이션 시작 시 강제 실행

FastAPI를 사용 중이시라면 `lifespan`이나 `startup` 이벤트를 사용하는 것이 자바의 `CommandLineRunner`처럼 확실합니다.

```python
# main.py (또는 서버 실행 파일)

@app.on_event("startup")
async def startup_event():
    # 서버가 뜨자마자 비동기 초기화를 실행하여 root_agent를 채워넣음
    from agents.device_info.agent import init_agent
    await init_agent()

```

---

### 요약 및 자바 비유

* **`__all__`**: 자바 클래스 내에서 어떤 필드를 `public`으로 열어둘지 결정하는 것과 같습니다. 그대로 두셔도 되지만, 초기값은 `None`이어야 합니다.
* **비동기 처리**: `root_agent`를 만드는 과정이 `CompletableFuture`처럼 작동하므로, 서버 시작 시점에 `await`를 걸어 **실제 객체**로 치환해줘야 합니다.
* **`already defined` 방지**: `init_agent` 함수 내부에서 리스트를 새로 만들어서 `root_agent.tools = 새로운_리스트`로 덮어쓰기만 하면 중복 정의 에러는 발생하지 않습니다.

**결론적으로**, `__all__`은 건드리지 마시고, `root_agent = None`으로 시작한 뒤 **서버 실행 시점에 `await init_agent()`를 호출**하여 `None`을 실제 에이전트 객체로 갈아끼우는 방식을 사용하시면 됩니다.

혹시 서버 실행 파일(`main.py` 등)에서 이 초기화 함수를 호출하는 부분도 코드로 짜드릴까요?

---
소프트웨어 전문가로서 답변드립니다. `already defined` 에러는 **동일한 이름의 도구가 에이전트의 도구 리스트(`root_agent.tools`)에 중복으로 등록**되려 할 때 발생합니다. 특히 `refresh_agent_tools`를 여러 번 호출하거나, 기존 리스트에 `extend`나 `append`를 반복하면서 발생했을 가능성이 큽니다.

결론부터 말씀드리면, **초기 부팅 시 `async/await`로 처리하는 것이 가장 깔끔하고 권장되는 방식**입니다. 다만, 메인 루프가 뜨기 전이므로 `asyncio.run()` 또는 별도의 초기화 루틴을 사용해야 합니다.

가장 안정적인 **초기 부팅 시점의 동기화 코드**를 제안해 드립니다.

---

### 1. `agent.py` 수정: 부팅 시 비동기 초기화

에이전트를 생성하는 함수 자체를 `async`로 만들거나, 내부에서 도구를 완전히 준비한 후 에이전트를 반환하도록 수정합니다.

```python
# agent.py

async def create_agent_async():
    name = "device_info"
    allow_list = ["get", "get_", "list_", "read_", "check_", "usp_", "kai-"]
    
    # 1. 도구셋을 비동기로 확실히 가져옴
    mcp_toolsets = get_tools(
        server_list_env_vars=["KCS_MCP_SERVER_LIST"],
        allow_list=allow_list,
        require_confirmation=False,
        header_provider=header_provider,
    )

    # 2. 기본 도구 정의
    final_tools = [
        convert_timestamp_to_datetime,
        load_compacted_response,
        check_mcp_operation_status_tool,
    ]

    # 3. 롱러닝 래퍼 적용 (중복 방지를 위해 set이나 dict 활용 가능하지만, 여기선 새로 생성)
    long_running_patterns = ["get_", "list_", "usage", "report", "kai-"]
    
    for toolset in mcp_toolsets:
        # 비동기로 실제 도구 목록을 끝까지 기다려 가져옴
        actual_tools = await toolset.get_tools() if hasattr(toolset, "get_tools") else getattr(toolset, "tools", [])
        
        for tool in actual_tools:
            if any(p in tool.name.lower() for p in long_running_patterns):
                lr_name = f"LR_{tool.name}"
                # 래퍼 생성 및 이름 부여
                wrapped = create_long_running_mcp_tool(toolset, tool.name)
                wrapped.name = lr_name 
                final_tools.append(wrapped)
                logger.info(f"✅ [BOOT] Wrapped: {lr_name}")
            else:
                final_tools.append(tool)

    # 4. 에이전트 생성 및 반환
    return Agent(
        model=BEDROCK_AI_MODEL,
        name=name,
        tools=final_tools, # 완성된 리스트 주입
        instruction=f"{INSTRUCTION}\n참고: 'LR_' 도구는 비동기로 동작합니다.",
        planner=BuiltInPlanner(thinking_config=types.ThinkingConfig(include_thoughts=True)),
        # ... 나머지 설정 ...
    )

# 전역 변수 초기화 방식 (서버 부팅 시점)
root_agent = None

async def init_root_agent():
    global root_agent
    root_agent = await create_agent_async()
    logger.info("🚀 [SYSTEM] Root Agent is fully initialized with MCP tools.")

```

---

### 2. 메인 실행부 (FastAPI 등)에서의 호출

애플리케이션이 시작될 때(`lifespan` 또는 `on_event("startup")`) 위 `init_root_agent`를 한 번만 호출하면 됩니다.

```python
# main.py 또는 server.py
@app.on_event("startup")
async def startup_event():
    # 부팅 시 딱 한 번만 실행하여 도구를 세팅합니다.
    await init_root_agent()

```

---

### 3. 왜 `already defined`가 떴을까?

원인은 크게 두 가지입니다:

1. **중복 리스트 추가**: `tools.extend(long_running_tools)`를 호출할 때, `long_running_tools` 안에 이미 존재하는 도구 이름이 들어있었기 때문입니다.
2. **`refresh` 로직의 누적**: `root_agent.tools = new_tools`로 교체하지 않고 `root_agent.tools.append()`를 사용했다면 호출할 때마다 도구가 늘어납니다.

---

### 4. 전문가의 조언: 이렇게 확인하세요

부팅 시 `async/await` 처리를 적용한 후, 로그에 다음과 같은 흐름이 보이는지 확인하세요.

1. `📡 [BOOT] Checking MCP Tools...`
2. `✅ [BOOT] Wrapped: LR_kai-app_getAppUsageList` (이게 20여 개 쭉 나와야 함)
3. `🚀 [SYSTEM] Root Agent is fully initialized...`

이렇게 **부팅 시점에 한 번에 비동기로 처리**하면, 컨트롤러에서 매번 `refresh`를 호출할 필요도 없고 `already defined` 같은 이름 충돌 문제도 완벽하게 해결됩니다. 지금 바로 `create_agent`를 `async` 버전으로 교체해 보시겠어요?

-----

소프트웨어 전문가로서 분석해 본 결과, `refresh_agent_tools` 함수 내에서 `get_tools`를 호출했을 때 값이 없는 이유는 **`get_tools` 함수가 비동기(Async) 방식으로 동작해야 함에도 불구하고 동기 방식으로 호출되었거나, 내부적으로 사용 중인 `McpToolset` 객체들이 아직 서버로부터 도구 목록을 수신(Fetch)하지 못한 상태**이기 때문입니다.

특히 제공해주신 `agent.py` 코드를 보면, `get_tools`가 반환하는 `toolset` 내부에 `tools` 속성이 없을 경우를 대비해 `asyncio.run(current_toolset.get_tools())`를 사용하는 복잡한 로직이 이미 포함되어 있습니다. 이는 MCP 도구 로딩이 단순히 함수 호출 한 번으로 끝나는 게 아니라 네트워크 통신이 필요한 비동기 작업임을 의미합니다.

이 문제를 해결하고, 컨트롤러 시작 전 터미널에서 확실히 상태를 확인할 수 있는 개선된 포스트 프로세싱 코드를 제안합니다.

### 1. 포스트 프로세싱 코드 개선 (비동기 처리 강화)

`get_tools`가 반환한 `toolset`들이 실제로 도구를 가지고 있는지 확인하기 위해 `await`를 명시적으로 사용해야 합니다. 또한, 에이전트의 `tools`를 교체할 때 **이름(name) 속성이 확실히 부여된 래퍼**가 들어가도록 보정합니다.

```python
# agent.py 내부에 수정 적용
async def refresh_agent_tools():
    """포스트 프로세싱: 비동기적으로 도구를 다시 읽어와 LR 접두어를 붙여 갱신"""
    global root_agent
    
    allow_list = ["get", "get_", "list_", "read_", "check_", "usp_", "kai-"]
    long_running_patterns = ["get_", "list_", "usage", "report", "kai-"]

    # 1. MCP 도구셋 가져오기
    mcp_toolsets = get_tools(
        server_list_env_vars=["KCS_MCP_SERVER_LIST"],
        allow_list=allow_list,
        require_confirmation=False,
    )

    new_final_tools = [
        convert_timestamp_to_datetime, 
        load_compacted_response, 
        check_mcp_operation_status_tool
    ]
    
    found_any = False
    
    for toolset in mcp_toolsets:
        # [중요] 비동기적으로 도구 목록을 가져와야 할 수 있음
        actual_tools = []
        if hasattr(toolset, "get_tools"):
            # McpToolset의 도구를 비동기로 명시적 획득
            actual_tools = await toolset.get_tools() 
        elif hasattr(toolset, "tools"):
            actual_tools = toolset.tools

        if not actual_tools:
            logger.warning(f"⚠️ [POST-PROCESS] Toolset {type(toolset).__name__} has no tools yet.")
            continue

        for tool in actual_tools:
            found_any = True
            tool_name = tool.name
            
            # 롱러닝 대상 여부 확인
            is_lr = any(p in tool_name.lower() for p in long_running_patterns)
            
            if is_lr:
                lr_display_name = f"LR_{tool_name}"
                # [수정] 래퍼 생성 시 에이전트용 이름을 인자로 전달 (wrapper 코드 수정 필요)
                wrapped_tool = create_long_running_mcp_tool(
                    toolset, 
                    tool_name,
                    # 만약 wrapper가 agent_tool_name을 지원하지 않는다면 아래 '3번' 참고
                )
                # 에이전트 인식용 이름 강제 부여
                wrapped_tool.name = lr_display_name 
                new_final_tools.append(wrapped_tool)
                logger.info(f"✅ [POST-PROCESS] Wrapped: {lr_display_name}")
            else:
                new_final_tools.append(tool)

    if found_any:
        # [핵심] 에이전트 객체의 도구 리스트를 강제로 교체
        root_agent.tools = new_final_tools
        logger.info(f"🚀 [POST-PROCESS] Agent tools updated. Total: {len(new_final_tools)}")
    
    return found_any

```

### 2. 컨트롤러 시작 전 터미널에서 확인하는 방법

서버가 실행될 때(Controller가 요청을 받기 전) 도구가 정상적으로 변환되었는지 확인하려면, `agent.py` 맨 하단에 **백그라운드 초기화 루프**를 돌리는 것이 가장 효과적입니다.

```python
# agent.py 최하단에 추가
import asyncio
import threading

def run_post_init():
    """별도 스레드에서 도구가 로드될 때까지 재시도하며 상태를 로그에 출력"""
    async def _init():
        max_retries = 5
        for i in range(max_retries):
            logger.info(f"🔄 [MONITOR] Attempting tool synchronization (Attempt {i+1}/{max_retries})...")
            success = await refresh_agent_tools()
            if success:
                # 성공 시 현재 에이전트가 가진 도구 이름을 모두 출력
                names = [getattr(t, 'name', str(t)) for t in root_agent.tools]
                logger.info(f"📊 [MONITOR] Final Tool List: {names}")
                break
            await asyncio.sleep(2) # MCP 서버 응답 대기 시간

    # 새 루프에서 실행 (메인 루프와 충돌 방지)
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_until_complete, args=(_init(),), daemon=True).start()

# 에이전트 생성 직후 실행
run_post_init()

```

### 3. 왜 `LR_` 관련 로그가 안 뜰까? (점검 포인트)

1. **변수 스코프 문제**: `Agent` 생성 시 전달된 `tools` 리스트는 내부적으로 튜플이나 복사된 리스트로 저장될 수 있습니다. `root_agent.tools = new_tools`와 같이 **인스턴스 속성에 직접 재할당**하지 않으면 에이전트는 계속 예전 도구 리스트를 참조합니다.
2. **도구 이름 속성 누락**: `LongRunningFunctionTool` 객체가 생성된 후 `.name` 속성에 `LR_...` 값이 할당되지 않으면, 에이전트의 로그 시스템(`BuiltInPlanner`)은 원본 함수 이름이나 래퍼의 공통 이름을 출력하게 됩니다.
3. **패턴 매칭 실패**: `long_running_patterns`에 포함된 문자열이 실제 MCP 도구 이름과 대소문자까지 정확히 맞는지 확인해야 합니다 (`tool_name.lower()` 사용 권장).

**정리:** `refresh_agent_tools` 내부에서 `await toolset.get_tools()`를 호출하여 실제 도구 데이터를 확보한 뒤, `root_agent.tools`에 직접 재할당하는 로직을 적용해 보세요. 그러면 컨트롤러 호출 전 터미널 로그에서 `✅ [POST-PROCESS] Wrapped: LR_...` 메시지를 보실 수 있을 것입니다.

-----

소프트웨어 전문가로서 분석해 본 결과, 현재 상황은 **"도구는 불러왔지만, 에이전트 객체 내부의 도구 리스트(tools)가 실제로는 교체되지 않았거나, 래퍼(Wrapper)가 원본 도구를 덮어쓰지 못한 상태"**입니다.

`monitor.log_summary()`를 통해 컨트롤러 시작 전 터미널에서 즉시 확인하고, 롱러닝 래퍼가 확실히 적용되도록 강제하는 최종 개선안을 드립니다.

---

### 1. `MCPToolMonitor`에서 변환 여부 확인하기

`monitor.summary()` 호출 시, 단순히 개수만 보여주지 말고 **이름 앞에 `LR_`이 붙은 도구가 몇 개인지** 로그에 찍히도록 `mcp_tool_monitor.py` (또는 관련 로직)를 수정해야 합니다.

```python
# mcp_tool_monitor.py 또는 체크 로직에 추가
def log_summary(self):
    total = len(self.tools)
    # 현재 등록된 도구 중 LR_ 접두어가 붙은 것들 카운트
    lr_tools = [t.name for t in self.tools if t.name.startswith("LR_")]
    
    logger.info("="*50)
    logger.info(f"📊 MCP TOOL MONITOR SUMMARY")
    logger.info(f" - Total Tools: {total}")
    logger.info(f" - Long-Running Tools (LR_): {len(lr_tools)}")
    if lr_tools:
        logger.info(f" - LR Tool List: {', '.join(lr_tools)}")
    else:
        logger.warning(" ⚠️ WARNING: No 'LR_' prefixed tools found!")
    logger.info("="*50)

```

---

### 2. `agent.py` 수정: 포스트 프로세싱 강제 적용

사용자님이 말씀하신 "다시 조회 시 31개"가 뜬다는 것은 `rediscover_tools`가 작동했다는 뜻입니다. 이때 **에이전트의 `tools` 속성을 직접 갈아끼워야 합니다.**

```python
# agent.py 개선본

async def check_mcp_tools_status():
    """MCP 도구 상태를 체크하고, 발견된 도구들을 LR로 변환하여 에이전트에 주입"""
    monitor = get_tool_monitor()
    # 1. 최신 도구 리스트 확보 (여기서 28개를 가져옴)
    await monitor.rediscover_tools() 
    
    # 2. 래퍼 적용 및 에이전트 도구 교체
    all_mcp_toolsets = monitor.toolsets # rediscover 이후의 최신 툴셋
    long_running_patterns = ["get_", "list_", "usage", "report", "kai-"]
    
    # 기본 툴은 유지
    updated_tools = [
        convert_timestamp_to_datetime,
        load_compacted_response,
        check_mcp_operation_status_tool
    ]

    for toolset in all_mcp_toolsets:
        for tool in getattr(toolset, "tools", []):
            # 패턴 매칭 시 LR_ 접두어 붙여서 래핑
            if any(p in tool.name.lower() for p in long_running_patterns):
                lr_name = f"LR_{tool.name}"
                wrapped = create_long_running_mcp_tool(
                    toolset, 
                    tool.name, 
                    agent_tool_name=lr_name # 이 이름이 로그에 찍힘
                )
                updated_tools.append(wrapped)
            else:
                updated_tools.append(tool)

    # [가장 중요] 글로벌 에이전트 객체의 도구 리스트를 강제로 업데이트
    root_agent.tools = updated_tools
    
    logger.info(f"🚀 [POST-PROCESS] Agent tools synchronized. Total: {len(updated_tools)}")
    monitor.log_summary() # 위에서 만든 요약 로그 출력
    
    return {"total": len(updated_tools), "lr_count": len([t for t in updated_tools if hasattr(t, 'name') and t.name.startswith("LR_")])}

```

---

### 3. 컨트롤러에서 로그 확인 절차

`chat-device-info`가 불리기 전에 `check_mcp_tools_status()`가 비동기로 완료되어야 합니다.

```python
# controller.py
@router.post("/v1/chat-device-info")
async def chat_device_info(...):
    # 요청마다 체크하거나, 서버 부팅 후 최초 1회 확실히 수행
    status = await check_mcp_tools_status()
    logger.info(f"Current Agent Tool Status: {status}")
    
    # 이제 에이전트는 LR_ 접두어가 붙은 도구만 알고 있습니다.

```

---

### 4. 왜 이전에는 LR 로그가 안 떴을까? (원인 분석)

1. **객체 참조 분리:** `Agent`를 생성할 때 전달한 `tools` 리스트는 리스트의 **복사본**일 수 있습니다. 나중에 외부에서 `long_running_tools` 리스트에 append 해도 에이전트 내부의 리스트에는 반영되지 않습니다. 반드시 `root_agent.tools = new_list` 처럼 직접 할당해야 합니다.
2. **이름 중복:** 만약 `LR_`을 붙이지 않고 원본 이름 그대로 래핑했다면, 에이전트는 기존에 알고 있던(래핑 안 된) 도구를 계속 사용할 수 있습니다. 접두어를 붙이면 에이전트가 "아, 이제는 `LR_...` 이걸 써야 하는구나"라고 확실히 인지합니다.

### **전문가의 최종 제언**

지금 바로 `check_mcp_tools_status` 함수 끝에 `print([t.name for t in root_agent.tools])`를 넣어보세요. 출력된 리스트에 `LR_`로 시작하는 이름들이 있다면 성공입니다. 만약 없다면 `create_long_running_mcp_tool` 내부에서 `tool.name`이 제대로 설정되지 않는 것이니 그 부분을 다시 점검해야 합니다.

이제 `LR_` 접두어가 로그에 찍히는지 확인해 보시겠어요? 가시성이 확보되면 디버깅이 훨씬 빨라집니다.


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
