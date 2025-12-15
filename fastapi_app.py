from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from py_utils import generate_lotto, generate_password, count_word

app = FastAPI(title="WS_Python API", version="0.1")


@app.get("/")
def read_root():
    return {"message": "FastAPI service running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/lotto")
def lotto(count: int = 6):
    if count < 1 or count > 10:
        raise HTTPException(status_code=400, detail="count must be between 1 and 10")
    return {"numbers": generate_lotto(count)}


class PasswordReq(BaseModel):
    website: str


@app.post("/password")
def password(req: PasswordReq):
    try:
        pw = generate_password(req.website)
        return {"password": pw}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class CountReq(BaseModel):
    text: str
    word: str


@app.post("/count")
def count(req: CountReq):
    return {"count": count_word(req.text, req.word)}
