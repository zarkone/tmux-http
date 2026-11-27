# tmux-http

A tiny REST API over your running tmux server. List sessions, read pane output,
send keystrokes — all over HTTP. Built on [libtmux] + [FastAPI].

[libtmux]: https://github.com/tmux-python/libtmux
[FastAPI]: https://fastapi.tiangolo.com/

## Why

Tmux has no built-in HTTP interface. If you want to drive tmux from a script,
an agent, a webhook, or just `curl`, you either shell out to `tmux ...` or
wrap the socket. This is the wrapper.

## Install & run

Requires Nix with flakes enabled.

```sh
nix run                              # build and run on 127.0.0.1:8765
nix run . -- --host 0.0.0.0 --port 9000
nix develop -c python3 server.py     # dev shell
```

The server connects to your **default** tmux socket — the same one your
running sessions live on. There is no separate tmux server.

## API

Once running, the OpenAPI spec is auto-generated:

- `GET /openapi.json` — machine-readable spec
- `GET /docs` — Swagger UI
- `GET /redoc` — ReDoc UI

Endpoint summary:

| Method | Path | Description |
|---|---|---|
| GET | `/` | Endpoint index |
| GET | `/sessions` | List all sessions |
| POST | `/sessions` | Create a session — `{name, command?, width?, height?}` |
| GET | `/sessions/{name}` | Session detail with windows |
| DELETE | `/sessions/{name}` | Kill the named session |
| GET | `/sessions/{name}/windows` | List windows in a session |
| POST | `/sessions/{name}/windows` | Create a window — `{name?, command?}` |
| DELETE | `/sessions/{name}/windows/{idx}` | Kill a window |
| POST | `/sessions/{name}/windows/{idx}/select` | Select (focus) a window |
| GET | `/sessions/{name}/windows/{idx}/panes` | List panes in a window |
| GET | `/panes/{target}/output?lines=N` | Capture last N lines from a pane |
| POST | `/panes/{target}/input` | Send keys — `{keys, literal?, enter?}` |

Pane targets accept either `%id` (e.g. `%14`) or `session:window.pane`
(e.g. `main:0.1`).

### Examples

```sh
curl -s localhost:8765/sessions | jq
curl -s -X POST localhost:8765/sessions \
  -H 'content-type: application/json' \
  -d '{"name":"scratch"}'
curl -s 'localhost:8765/panes/scratch:0.0/output?lines=50'
curl -s -X POST localhost:8765/panes/scratch:0.0/input \
  -H 'content-type: application/json' \
  -d '{"keys":"echo hi","enter":true}'
curl -s -X DELETE localhost:8765/sessions/scratch
```

## Safety

`DELETE /sessions/{name}` and `POST /panes/{target}/input` operate on your
real tmux. Be deliberate about which sessions and panes you target — there is
no undo. Bind to `127.0.0.1` (the default) unless you have a reason not to.

## License

MIT — see [LICENSE](LICENSE).
