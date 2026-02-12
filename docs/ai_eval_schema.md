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
