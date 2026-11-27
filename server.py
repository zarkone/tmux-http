"""tmux HTTP server — REST API over tmux."""

from __future__ import annotations

import argparse
from typing import Optional

import libtmux
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


app = FastAPI(title="tmux-http", description="REST API over tmux")
server = libtmux.Server()


def _bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v) == "1"


def _int(v, default: int = 0) -> int:
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def session_dict(s) -> dict:
    return {
        "name": s.session_name,
        "id": s.session_id,
        "created": _int(s.session_created),
        "attached": _bool(s.session_attached),
        "windows": _int(getattr(s, "session_windows", None)),
    }


def window_dict(w) -> dict:
    return {
        "index": _int(w.window_index),
        "id": w.window_id,
        "name": w.window_name,
        "active": _bool(w.window_active),
        "panes": _int(w.window_panes),
    }


def pane_dict(p) -> dict:
    return {
        "index": _int(p.pane_index),
        "id": p.pane_id,
        "active": _bool(p.pane_active),
        "pid": _int(p.pane_pid),
        "command": p.pane_current_command,
        "width": _int(p.pane_width),
        "height": _int(p.pane_height),
    }


def get_session(name: str):
    matches = server.sessions.filter(session_name=name)
    if not matches:
        raise HTTPException(404, f"session {name!r} not found")
    return matches[0]


def get_window(session_name: str, idx: int):
    sess = get_session(session_name)
    wins = sess.windows.filter(window_index=str(idx))
    if not wins:
        raise HTTPException(404, f"window {idx} not found in session {session_name!r}")
    return wins[0]


def resolve_pane(target: str):
    """Resolve `%id` or `session:window.pane` to a libtmux Pane."""
    if target.startswith("%"):
        matches = server.panes.filter(pane_id=target)
        if not matches:
            raise HTTPException(404, f"pane {target!r} not found")
        return matches[0]
    try:
        if "." in target:
            sw, p_idx = target.rsplit(".", 1)
        else:
            sw, p_idx = target, "0"
        s_name, w_idx = sw.split(":", 1)
    except ValueError:
        raise HTTPException(400, f"invalid pane target: {target!r}")
    sess = get_session(s_name)
    wins = sess.windows.filter(window_index=str(w_idx))
    if not wins:
        raise HTTPException(404, f"window {w_idx} not found in session {s_name!r}")
    panes = wins[0].panes.filter(pane_index=str(p_idx))
    if not panes:
        raise HTTPException(404, f"pane {p_idx} not found in {s_name}:{w_idx}")
    return panes[0]


class CreateSession(BaseModel):
    name: str
    command: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class SendInput(BaseModel):
    keys: str
    literal: bool = False
    enter: bool = False


class Rename(BaseModel):
    new_name: str


@app.get("/")
def root():
    return {
        "name": "tmux-http",
        "endpoints": [
            "GET    /sessions",
            "POST   /sessions               {name, command?, width?, height?}",
            "GET    /sessions/{name}",
            "DELETE /sessions/{name}",
            "POST   /sessions/{name}/rename {new_name}",
            "GET    /sessions/{name}/windows",
            "GET    /sessions/{name}/windows/{idx}/panes",
            "POST   /sessions/{name}/windows/{idx}/rename {new_name}",
            "GET    /panes/{target}/output?lines=N",
            "POST   /panes/{target}/input   {keys, literal?, enter?}",
        ],
    }


@app.get("/sessions")
def sessions_list():
    return [session_dict(s) for s in server.sessions]


@app.post("/sessions", status_code=201)
def sessions_create(body: CreateSession):
    if server.sessions.filter(session_name=body.name):
        raise HTTPException(409, f"session {body.name!r} exists")
    kwargs: dict = {"session_name": body.name}
    if body.command:
        kwargs["window_command"] = body.command
    if body.width:
        kwargs["x"] = body.width
    if body.height:
        kwargs["y"] = body.height
    s = server.new_session(**kwargs)
    return session_dict(s)


@app.get("/sessions/{name}")
def session_get(name: str):
    s = get_session(name)
    return {**session_dict(s), "windows": [window_dict(w) for w in s.windows]}


@app.delete("/sessions/{name}")
def session_delete(name: str):
    s = get_session(name)
    s.kill()
    return {"ok": True}


@app.post("/sessions/{name}/rename")
def session_rename(name: str, body: Rename):
    s = get_session(name)
    if server.sessions.filter(session_name=body.new_name):
        raise HTTPException(409, f"session {body.new_name!r} already exists")
    s.rename_session(body.new_name)
    return session_dict(s)


@app.get("/sessions/{name}/windows")
def session_windows(name: str):
    s = get_session(name)
    return [window_dict(w) for w in s.windows]


@app.get("/sessions/{name}/windows/{idx}/panes")
def window_panes(name: str, idx: int):
    w = get_window(name, idx)
    return [pane_dict(p) for p in w.panes]


@app.post("/sessions/{name}/windows/{idx}/rename")
def window_rename(name: str, idx: int, body: Rename):
    w = get_window(name, idx)
    w.rename_window(body.new_name)
    return window_dict(w)


@app.get("/panes/{target}/output")
def pane_output(target: str, lines: int = 100):
    pane = resolve_pane(target)
    out = pane.capture_pane(start=-lines)
    if isinstance(out, list):
        out = "\n".join(out)
    return {"target": target, "output": out}


@app.post("/panes/{target}/input")
def pane_input(target: str, body: SendInput):
    pane = resolve_pane(target)
    pane.send_keys(body.keys, literal=body.literal, enter=body.enter)
    return {"ok": True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
