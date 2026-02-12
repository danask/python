
전문가 관점에서 분석했을 때, troubleshoot은 잘 되고 device_info에서만 **"No response returned"**가 발생하는 이유는 에이전트가 사용하는 MCP 도구의 실행 방식과 그에 따른 응답 지연(Time-out) 차이 때문일 가능성이 매우 높습니다.
두 에이전트의 결정적인 차이점 3가지를 짚어드립니다.
1. 롱러닝 툴(Long-running Tool)의 유무
 * Troubleshoot: 주로 지식 기반 검색(RAG)이나 상태 확인 등 비교적 짧은 시간에 끝나는 툴을 사용합니다. 따라서 async with 컨텍스트가 유지되는 동안 결과가 반환됩니다.
 * Device Info: 장비의 상세 상태를 조회하거나 실시간 진단을 수행하는 MCP 롱러닝 툴을 호출하는 경우가 많습니다. 이 과정에서 폴링(Polling) 로직이 길어지면, runner.run_async 루프가 한참 동안 아무런 이벤트를 뱉지 않게 됩니다.
2. 비동기 컨텍스트 만료 (Context Timeout)
RuntimeError: No response returned는 보통 다음 시나리오에서 발생합니다.
 * async with ChatRunner.get_runner(...) 내부에서 device_info 툴이 실행됨.
 * 툴 실행이 예상보다 길어지거나 내부에서 예외가 발생함.
 * FastAPI 미들웨어가 설정한 타임아웃에 먼저 걸리거나, runner 객체가 툴 응답을 기다리다 연결을 끊어버림.
 * 함수가 return문에 도달하기 전에 제어권이 넘어가면서 미들웨어는 "응답 없음"으로 판단함.
3. 스키마 적용 여부의 부작용
코드상에서 agent_name != "device_info" 일 때만 스키마를 사용하도록 되어 있는 부분이 있습니다.
 * troubleshoot은 일반 텍스트 모드로 작동하여 데이터 수집이 유연합니다.
 * device_info는 특정 출력 스키마를 강제하거나, 반대로 스키마가 없는 상태에서 collect_response가 특정 형식을 기대하고 기다리다 꼬이는 경우가 발생합니다.
해결을 위한 핵심 디버깅 포인트
device_info 호출 시에만 터진다면 아래와 같이 최종 응답을 보장하는 구조로 _handle_chat_request 내부를 감싸야 합니다.
# _handle_chat_request 내부 수정 제안
try:
    async with ChatRunner.get_runner(chat_service, agent_name=agent_name, use_output_schema=use_schema) as runner:
        # 이 안에서 발생하는 모든 일은 result에 담아야 함
        result = await collect_response_with_contexts2(runner, user_input, combined_user_id, session_id)
        
        # 만약 result가 None이면 여기서 강제로 기본값 할당
        if not result:
            result = {"response": "에이전트 응답 생성 실패", "retrieved_contexts": []}
            
except Exception as e:
    logger.error(f"Device Info 처리 중 치명적 에러: {e}", exc_info=True)
    result = {"response": f"시스템 에러 발생: {str(e)}", "retrieved_contexts": []}

return result # 어떤 경우에도 여기서 return이 되어야 RuntimeError가 안 납니다.

요약
troubleshoot은 빨리 끝나서 문제가 없었던 것이고, device_info는 내부 툴(MCP) 실행 시간이 길어지면서 return 문에 도달하기 전에 비동기 루프가 깨지는 것이 원인입니다.
우선 device_info 에이전트가 호출하는 MCP 툴의 로그를 확인해 보시겠어요? 툴이 Success를 찍기 전에 서버 로그에서 RuntimeError가 먼저 올라온다면 타임아웃 문제입니다. 이 경우 collect_ 함수 내부에 중간 yield나 하트비트 로직을 추가해야 합니다.
Would you like me to check the specific MCP tool configuration for device_info to see if it has a shorter timeout?


-----

 elif is_eval:
       logger.info(f"================EVAL: agent={agent_name}, session={session_id}")
       use_schema = agent_name == "device_info"  # device_info일 때만 schema 사용
       
       try:
           async with ChatRunner.get_runner(
               chat_service, agent_name=agent_name, use_output_schema=use_schema
           ) as runner:
               logger.info(f"[DEBUG] Runner created for agent: {agent_name}")
               
               # StreamingResponse와 동일한 방식으로 이벤트 수집
               response_parts = []
               event_count = 0
               
               async for event in runner.run_async(
                   new_message=user_input,
                   user_id=combined_user_id,
                   session_id=session_id,
                   run_config=RunConfig(streaming_mode=StreamingMode.NONE),
               ):
                   event_count += 1
                   event_text = get_response_text_from_event(event)
                   if event_text:
                       response_parts.append(event_text)
               
               logger.info(f"[DEBUG] Collected {event_count} events, {len(response_parts)} non-empty parts")
               
               response_text = "\n".join(response_parts) if response_parts else "No response generated"
               result = {"response": response_text, "retrieved_contexts": []}
               
               context_count = len(result.get("retrieved_contexts", []))
               logger.info(f"================EVAL: Response generated with {context_count} contexts")
               
               return result
               
       except Exception as e:
           logger.error(f"Error in eval request for {agent_name}: {str(e)}", exc_info=True)
           return {"error": str(e), "retrieved_contexts": [], "success": False}

-----

## 수정된 부분 2곳:

### 1. **229-252번 라인** (is_eval 분기)

**변경 전:**
```python
elif is_eval:
    logger.info(f"================EVAL: ======================")
    use_schema = agent_name != "device_info"
    async with ChatRunner.get_runner(
        chat_service, agent_name=agent_name, use_output_schema=use_schema
    ) as runner:
        result = await collect_response_with_contexts2(
            runner, user_input, combined_user_id, session_id
        )
        # context_count = len(result.get("retrieved_contexts", []))
        # logger.info(f"================EVAL: Response generated with {context_count} contexts")
        return result  # ← 문제: context manager 안에서 바로 return
```

**변경 후:**
```python
elif is_eval:
    logger.info(f"================EVAL: agent={agent_name}, session={session_id}")
    use_schema = agent_name == "device_info"  # ← != 에서 == 로 변경
    result = None
    try:
        async with ChatRunner.get_runner(
            chat_service, agent_name=agent_name, use_output_schema=use_schema
        ) as runner:
            logger.info(f"[DEBUG] Runner created for agent: {agent_name}")
            result = await collect_response_with_contexts2(
                runner, user_input, combined_user_id, session_id
            )
            logger.info(f"[DEBUG] Response collected successfully")
    except Exception as e:
        logger.error(f"Error in eval request for {agent_name}: {str(e)}", exc_info=True)
        return {"error": str(e), "retrieved_contexts": [], "success": False}
    
    if not result:
        logger.error(f"No result generated for agent: {agent_name}")
        return {"error": "No response generated", "retrieved_contexts": [], "success": False}
    
    context_count = len(result.get("retrieved_contexts", []))
    logger.info(f"================EVAL: Response generated with {context_count} contexts")
    return result  # ← context manager 밖에서 return
```

### 2. **253-279번 라인** (collect_response_with_contexts2 함수)

**변경 전:**
```python
async for event_text in generate_events(runner, content, user_id, session_id):
    response_parts.append(event_text)  # ← 빈 문자열도 추가됨
```

**변경 후:**
```python
async for event_text in generate_events(runner, content, user_id, session_id):
    event_count += 1
    if event_text:  # ← 빈 문자열 필터링 추가
        response_parts.append(event_text)
```

---

**핵심은 1번 수정**: context manager 안에서 바로 return하지 않고 밖에서 return하도록 변경!

-----

여전히 `RuntimeError: No response returned.`가 발생한다면, 이는 코드의 논리적 오류라기보다 **비동기 컨텍스트 매니저(`async with`) 내에서 예외가 발생하여 `return` 문에 도달하지 못하고 함수가 비정상적으로 종료**되기 때문입니다.

특히 `FastAPI` 미들웨어(`logging_context.py`)가 응답을 가로채려는데, 엔드포인트가 예외로 인해 `None`조차 반환하지 못하고 터져버리면 ASGI 서버는 이 에러를 내뱉습니다.

문제를 확실히 해결하기 위해 **가장 바깥쪽에 `try...except`를 배치**하고, 요청하신 두 가지 버전의 최종 수정안을 제안합니다.

---

### 1. 스키마 유지 버전 (구조화된 데이터 중심)

에이전트가 뱉는 순수한 텍스트 조각들을 모아서 마지막에 JSON 파싱을 시도합니다. `generate_events`를 거치지 않으므로 `**author**:` 같은 이름표 오염이 없어 안전합니다.

```python
async def collect_response_with_contexts_schema(
    runner: Any, content: types.Content, user_id: str, session_id: str
) -> dict:
    response_parts = []
    try:
        # runner에서 직접 순수 파트를 수집하여 이름표(author) 오염 방지
        async for event in runner.run_async(
            new_message=content,
            user_id=user_id,
            session_id=session_id,
            run_config=RunConfig(streaming_mode=StreamingMode.NONE),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        response_parts.append(part.text)
        
        full_text = "".join(response_parts).strip()
        if not full_text:
            return {"response": "No content received", "retrieved_contexts": []}

        # JSON 영역만 추출하여 파싱 시도
        try:
            start = full_text.find('{')
            end = full_text.rfind('}') + 1
            if start != -1 and end != 0:
                return {"response": json.loads(full_text[start:end]), "retrieved_contexts": []}
        except json.JSONDecodeError:
            pass # 파싱 실패 시 아래에서 원본 텍스트 반환

        return {"response": full_text, "retrieved_contexts": []}

    except Exception as e:
        logger.error(f"Error in schema collection: {e}")
        return {"response": f"Error: {str(e)}", "retrieved_contexts": []}

```

---

### 2. 스키마 미유지 버전 (텍스트 로그 중심)

`generate_events`에서 나오는 포맷팅된 문자열을 그대로 합칩니다. 에러 방지를 위해 빈 결과가 나오더라도 반드시 기본 응답을 보장합니다.

```python
async def collect_response_with_contexts_text(
    runner: Any, content: types.Content, user_id: str, session_id: str
) -> dict:
    response_parts = []
    try:
        # 기존 generate_events를 소모하여 포맷팅된 텍스트 수집
        async for event_text in generate_events(runner, content, user_id, session_id):
            if event_text:
                response_parts.append(event_text.strip())
        
        final_text = "\n\n".join(response_parts) if response_parts else "No response generated"
        return {"response": final_text, "retrieved_contexts": []}

    except Exception as e:
        logger.error(f"Error in text collection: {e}")
        return {"response": f"Error: {str(e)}", "retrieved_contexts": []}

```

---

### 3. [핵심] `_handle_chat_request` 구조 수정 (에러 방지용)

`RuntimeError: No response returned`를 잡으려면 `async with` 블록 밖으로 리턴값을 확실히 빼내야 합니다.

```python
async def _handle_chat_request(...):
    # ... (기존 초기화 로직) ...
    
    result = None # 결과를 담을 변수 초기화
    try:
        if stream_response:
            async with ChatRunner.get_runner(chat_service, agent_name=agent_name) as runner:
                return StreamingResponse(...) # 이 부분은 정상 작동 확인됨
        
        else:
            # Eval 또는 일반 단답형 요청 처리
            use_schema = (agent_name == "device_info")
            async with ChatRunner.get_runner(chat_service, agent_name=agent_name, use_output_schema=use_schema) as runner:
                # 사용자가 선택한 버전의 함수 호출
                result = await collect_response_with_contexts_schema(runner, user_input, combined_user_id, session_id)
                
    except Exception as e:
        logger.error(f"Critical error in _handle_chat_request: {e}")
        result = {"response": f"Internal Server Error: {str(e)}", "retrieved_contexts": []}

    # 블록 밖에서 최종적으로 결과가 있는지 검증 후 반환
    if result is None:
        return {"response": "System failed to produce a response.", "retrieved_contexts": []}
    
    return result

```

### 왜 이렇게 해야 하나요?

현재 사용자님의 코드는 `async with` 안에서 모든 처리를 하려다 보니, 내부에서 작은 예외만 발생해도 **함수가 중간에 튕겨져 나가버립니다.** 위와 같이 `result` 변수를 미리 선언하고 마지막에 명시적으로 `return result`를 해주면, 어떤 에러가 나더라도 최소한 에러 메시지가 담긴 JSON 응답이라도 FE에 전달되어 `RuntimeError`를 막을 수 있습니다.

**버전 1(스키마 유지)**을 적용하여 `device_info`를 다시 테스트해 보시겠어요? 이번에는 에러가 나더라도 최소한 로그에 원인이 찍히고 화면에는 에러 메시지가 나올 것입니다. 다음 단계로 무엇을 도와드릴까요?

-----

트레이스백을 보니 문제의 핵심은 `RuntimeError: No response returned.`입니다. 이 에러는 FastAPI(Starlette) 미들웨어 스택에서 **엔드포인트 함수가 아무런 응답(Response) 객체를 반환하지 않았을 때** 발생합니다.

`eval-device-info` 요청 시 이 에러가 발생하는 이유는 `_handle_chat_request` 함수 내부의 `is_eval` 조건문 블록에서 **결과값을 제대로 `return`하지 못하거나, 그 안에서 호출하는 함수가 예기치 않게 종료**되었기 때문일 확률이 매우 높습니다.

---

### 1. 원인 분석: 왜 `No response returned`인가?

`controller3.py` 코드의 `_handle_chat_request` 로직을 보면 다음과 같은 위험 요소가 있습니다.

* **`collect_response_with_contexts2`의 반환 실패**: 이 함수 내부에서 예외가 발생하여 `try...except` 블록에 걸렸을 때, 리턴하는 `dict` 객체가 `_handle_chat_request`까지는 전달되지만, 만약 그 과정에서 비동기 컨텍스트 매니저(`async with ChatRunner.get_runner`)가 비정상 종료되면서 최종 `return`문에 도달하지 못할 수 있습니다.
* **미들웨어와의 충돌**: `logging_context.py` 미들웨어가 응답을 기다리고 있는데, 엔드포인트가 `None`을 반환하거나 예외로 인해 실행 흐름이 끊기면 ASGI 서버는 "응답 없음"으로 간주합니다.

### 2. 해결 코드: 두 가지 버전 업데이트

요청하신 대로 **스키마 유지 버전**과 **텍스트 전용 버전**으로 나누어, 에러 없이 안전하게 응답을 반환하도록 수정한 코드입니다.

#### 버전 A: 스키마 유지 버전 (구조화된 데이터 보존)

에이전트가 뱉는 순수 텍스트만 모아서 마지막에 JSON으로 파싱합니다. 파싱 실패 시에도 빈 응답이 아닌 원본 텍스트를 반환하여 `RuntimeError`를 방지합니다.

```python
async def collect_response_with_contexts_schema(
    runner: Any, content: types.Content, user_id: str, session_id: str
) -> dict:
    """순수 텍스트 파트만 수집하여 최종적으로 JSON 스키마로 파싱합니다."""
    response_parts = []
    try:
        # generate_events 대신 runner를 직접 구독하여 이름표(**author**) 없는 순수 데이터 수집
        async for event in runner.run_async(
            new_message=content,
            user_id=user_id,
            session_id=session_id,
            run_config=RunConfig(streaming_mode=StreamingMode.NONE),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        response_parts.append(part.text)
    except Exception as e:
        logger.error(f"Error gathering stream: {e}")
        return {"response": f"Stream Error: {str(e)}", "retrieved_contexts": []}

    full_text = "".join(response_parts).strip()
    if not full_text:
        return {"response": "No content from agent", "retrieved_contexts": []}

    try:
        # JSON 경계 탐색 및 추출
        start = full_text.find('{')
        end = full_text.rfind('}') + 1
        if start != -1 and end != 0:
            json_str = full_text[start:end]
            return {"response": json.loads(json_str), "retrieved_contexts": []}
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON schema, returning raw text.")
    
    return {"response": full_text, "retrieved_contexts": []}

```

#### 버전 B: 스키마 유지 안 함 (텍스트 로그 중심)

`generate_events`를 사용하여 포맷팅된 문자열을 수집하되, `RuntimeError`가 나지 않도록 반드시 문자열을 결과에 담아 리턴합니다.

```python
async def collect_response_with_contexts_text(
    runner: Any, content: types.Content, user_id: str, session_id: str
) -> dict:
    """포맷팅된 모든 이벤트를 텍스트로 합쳐서 반환합니다."""
    response_parts = []
    try:
        # 기존 generate_events 제너레이터를 소모
        async for event_text in generate_events(runner, content, user_id, session_id):
            if event_text:
                response_parts.append(event_text.strip())
    except Exception as e:
        logger.error(f"Error in text collection: {e}")
        return {"response": f"Collection Error: {str(e)}", "retrieved_contexts": []}

    # 리스트가 비어있어도 최소한의 응답 객체를 보장하여 'No response returned' 방지
    final_text = "\n\n".join(response_parts) if response_parts else "Agent provided no text response."
    return {"response": final_text, "retrieved_contexts": []}

```

---

### 3. `_handle_chat_request` 적용 시 주의사항

함수를 호출할 때 반드시 `await` 결과를 변수에 담아 **함수의 가장 바깥쪽에서 리턴**해야 합니다.

```python
    elif is_eval:
        logger.info(f"================EVAL: ======================")
        use_schema = (agent_name == "device_info") # 스키마 사용 여부 결정
        async with ChatRunner.get_runner(chat_service, agent_name=agent_name, use_output_schema=use_schema) as runner:
            # 선택한 버전의 함수를 호출
            result = await collect_response_with_contexts_schema(runner, user_input, combined_user_id, session_id)
            return result # 여기서 명확하게 return 해야 RuntimeError가 사라집니다.

```

**결론**: 지금 발생하는 `RuntimeError`는 에이전트의 응답이 비어있거나 수집 로직에서 예외가 발생했을 때, FastAPI에게 돌려줄 **"최종 리턴값"**이 유실되었기 때문입니다. 위 수정 코드를 적용하면 어떤 상황에서도 `dict` 응답이 리턴되므로 에러가 해결될 것입니다.

어떤 버전을 먼저 테스트해보시겠어요? 결과가 JSON이어야 한다면 **버전 A**를 추천드립니다.

-----

전문가로서 `eval-device-info`에서 발생하는 에러를 해결하기 위해, 요청하신 **두 가지 버전(스키마 유지 vs 스키마 미유지)**으로 `collect_response_with_contexts2`와 관련 로직을 업데이트해 드립니다.

현재 에러의 핵심은 `generate_events`가 반환하는 `**author**: text` 형태의 문자열이 합쳐지면서 JSON 구조를 파괴하는 것입니다. 이를 방지하는 것이 포인트입니다.

---

### 1. 스키마를 유지하는 버전 (구조화된 데이터 필요 시)

이 버전은 에이전트가 반환하는 순수한 텍스트 파트만 수집하여 최종적으로 JSON으로 파싱합니다. `author` 이름표를 제거하여 JSON 형식을 보존합니다.

```python
async def collect_response_with_contexts_schema_version(
   runner: Any, content: types.Content, user_id: str, session_id: str
) -> dict:
   response_parts = []
   try:
       # generate_events 대신 runner를 직접 구독하여 이름표(**author**)가 붙기 전 데이터를 수집
       async for event in runner.run_async(
           new_message=content,
           user_id=user_id,
           session_id=session_id,
           run_config=RunConfig(streaming_mode=StreamingMode.NONE),
       ):
           if event.content and event.content.parts:
               for part in event.content.parts:
                   # 텍스트 파트만 순수하게 수집 (JSON 조각들)
                   if hasattr(part, "text") and part.text:
                       response_parts.append(part.text)
   except Exception as e:
       logger.error(f"Error in collect_response_with_contexts: {e}", exc_info=True)
       return {"response": None, "error": str(e)}

   full_text = "".join(response_parts).strip()
   
   try:
       # JSON 부분만 추출하여 파싱 (앞뒤 마크다운 등 제거)
       start = full_text.find('{')
       end = full_text.rfind('}') + 1
       if start != -1 and end != 0:
           json_str = full_text[start:end]
           parsed_data = json.loads(json_str)
           # Pydantic 모델로 한 번 더 검증 (선택 사항)
           # return {"response": DeviceInfoWithStatus(**parsed_data).model_dump(), "retrieved_contexts": []}
           return {"response": parsed_data, "retrieved_contexts": []}
   except (json.JSONDecodeError, Exception) as e:
       logger.warning(f"Failed to parse schema, returning raw text: {e}")
       
   return {"response": full_text, "retrieved_contexts": []}

```

---

### 2. 스키마를 유지하지 않는 버전 (단순 텍스트 응답 시)

이 버전은 현재 `generate_events` 로직을 그대로 활용하되, 빈 값을 걸러내고 사람이 읽기 좋은 형태의 전체 대화 로그를 반환합니다.

```python
async def collect_response_with_contexts_text_version(
   runner: Any, content: types.Content, user_id: str, session_id: str
) -> dict:
   response_parts = []
   try:
       # 기존에 정의된 generate_events를 그대로 사용하여 포맷팅된 텍스트 수집
       async for event_text in generate_events(runner, content, user_id, session_id):
           if event_text and event_text.strip():
               # **author**: text\n\n\n 형태의 문자열들이 리스트에 담김
               response_parts.append(event_text.strip())       
   except Exception as e:
       logger.error(f"Error in collect_response_with_contexts: {e}", exc_info=True)
       return {"response": f"Error: {str(e)}", "retrieved_contexts": []}

   # 사람이 읽기 좋게 줄바꿈으로 합침
   response_text = "\n".join(response_parts) if response_parts else "No response generated"
   
   return {"response": response_text, "retrieved_contexts": []}

```

---

### 🏗️ 두 방식의 차이점 비교

| 항목 | 스키마 유지 버전 | 스키마 미유지 버전 |
| --- | --- | --- |
| **응답 데이터 타입** | `dict` (JSON 객체) | `str` (일반 문자열) |
| **주요 용도** | 자동화 테스트, 후처리 API 연동 | 단순 답변 확인, 에이전트 대화 로깅 |
| **추천 에이전트** | `device_info` (구조적 데이터 필요 시) | `orchestrator`, `troubleshoot` |
| **에러 위험** | JSON 형식이 깨질 경우 파싱 에러 발생 가능 | 에러 위험 거의 없음 |

### 적용 가이드

1. **스키마 버전**을 사용하신다면 에이전트의 `instruction`에 "반드시 JSON 형식을 지켜라"라는 내용을 유지하세요.
2. **텍스트 버전**을 사용하신다면 `device_info_app(use_output_schema=False)`로 설정하여 에이전트가 자유롭게 말하도록 하는 것이 좋습니다.

어떤 버전을 메인으로 채택하시겠어요? 결정하시면 해당 코드를 `controller3.py`에 바로 이식할 수 있도록 전체 함수를 정리해 드릴 수 있습니다.
