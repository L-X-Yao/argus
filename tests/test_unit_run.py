"""Tests for the launchers: .env loading and how host and port reach the backend.

Each case runs in a fresh interpreter because backend modules read the
environment at import time.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PROBE = """
import json
import sys
from pathlib import Path
from unittest import mock

origins = json.loads(sys.argv[1])
launcher = sys.argv[2]
sys.argv = [launcher, *sys.argv[3:]]

with mock.patch("uvicorn.run") as serve, mock.patch("webbrowser.open") as browser:
    if launcher == "run":
        import run

        run.main()
    else:
        import backend.server

        backend.server.main()

import backend.app as app
import backend.auth as auth
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

auth.TOKEN_FILE = Path("no-such-token-file")


def websocket(client, origin):
    try:
        with client.websocket_connect("/ws", headers={"origin": origin}) as ws:
            ws.send_json({"type": "disconnect"})
    except WebSocketDisconnect as exc:
        return exc.code
    return "open"


with TestClient(app.app) as client:
    sockets = {origin: websocket(client, origin) for origin in origins}

print(json.dumps({
    "host": serve.call_args.kwargs["host"],
    "port": serve.call_args.kwargs["port"],
    "browser": [call.args[0] for call in browser.call_args_list],
    "origins": app._cors_origins,
    "sockets": sockets,
    "token_required": auth.auth_required(),
    "dotenv_token_accepted": auth.verify_token("from-dotenv"),
}))
"""


def probe(tmp_path, launcher="run", dotenv=None, env=None, argv=(), origins=(), dist=False):
    """Start a launcher with uvicorn and the browser mocked, and report what reached them.

    run.py is copied so that its own folder, and the .env in it, is under tmp_path.
    The working directory holds a decoy .env that must never be read.
    """
    app_dir = tmp_path / "app"
    work_dir = tmp_path / "work"
    app_dir.mkdir(exist_ok=True)
    work_dir.mkdir(exist_ok=True)
    shutil.copy2(REPO / "run.py", app_dir / "run.py")
    (app_dir / ".env").unlink(missing_ok=True)
    if dotenv is not None:
        (app_dir / ".env").write_text(dotenv)
    if dist:
        (app_dir / "dist").mkdir(exist_ok=True)
        (app_dir / "dist" / "index.html").write_text("")
    (work_dir / ".env").write_text("ARGUS_HOST=10.0.0.9\nARGUS_PORT=1111\nGCS_AUTH_TOKEN=decoy\n")

    child_env = {k: v for k, v in os.environ.items() if not k.startswith("ARGUS_") and k != "GCS_AUTH_TOKEN"}
    child_env["PYTHONPATH"] = os.pathsep.join([str(app_dir), str(REPO)])
    child_env.update(env or {})
    result = subprocess.run(
        [sys.executable, "-c", PROBE, json.dumps(list(origins)), launcher, *argv],
        cwd=work_dir,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_defaults_without_any_configuration(tmp_path):
    got = probe(tmp_path)
    assert (got["host"], got["port"], got["token_required"]) == ("127.0.0.1", 8100, False)
    assert got["origins"] == [
        "http://localhost:5173",
        "http://localhost:8100",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8100",
    ]


def test_dotenv_reaches_the_launcher_and_the_backend(tmp_path):
    got = probe(
        tmp_path,
        dotenv="ARGUS_HOST=0.0.0.0\nARGUS_PORT=8123\nGCS_AUTH_TOKEN=from-dotenv\n",
        origins=["http://localhost:8123"],
    )
    assert (got["host"], got["port"]) == ("0.0.0.0", 8123)
    assert got["token_required"] is True
    assert got["dotenv_token_accepted"] is True
    assert got["sockets"] == {"http://localhost:8123": 4001}


def test_shell_environment_wins_over_dotenv(tmp_path):
    got = probe(
        tmp_path,
        dotenv="ARGUS_PORT=8123\nGCS_AUTH_TOKEN=from-dotenv\n",
        env={"ARGUS_PORT": "8124", "GCS_AUTH_TOKEN": "from-shell"},
    )
    assert got["port"] == 8124
    assert got["dotenv_token_accepted"] is False


def test_command_line_wins_over_environment(tmp_path):
    got = probe(
        tmp_path,
        dotenv="ARGUS_HOST=0.0.0.0\n",
        env={"ARGUS_PORT": "8124"},
        argv=("--host", "127.0.0.2", "--port", "8125"),
    )
    assert (got["host"], got["port"]) == ("127.0.0.2", 8125)


def test_unusable_values_fall_back_to_the_defaults(tmp_path):
    got = probe(tmp_path, dotenv="ARGUS_HOST=\nARGUS_PORT=abc\n")
    assert (got["host"], got["port"]) == ("127.0.0.1", 8100)
    assert probe(tmp_path, dotenv="ARGUS_PORT=99999\n")["port"] == 8100


def test_browser_opens_unless_disabled_in_dotenv(tmp_path):
    assert probe(tmp_path, dist=True)["browser"] == ["http://localhost:8100"]
    assert probe(tmp_path, dotenv="ARGUS_NO_BROWSER=1\n", dist=True)["browser"] == []


def test_page_on_a_custom_port_can_open_its_own_websocket(tmp_path):
    origins = ["http://localhost:8123", "http://127.0.0.1:8123", "http://localhost:8100"]
    expected = dict(zip(origins, ["open", "open", 4003], strict=True))
    assert probe(tmp_path, env={"ARGUS_PORT": "8123"}, origins=origins)["sockets"] == expected
    assert probe(tmp_path, argv=("--port", "8123"), origins=origins)["sockets"] == expected


def test_explicit_origin_list_is_used_as_given(tmp_path):
    origins = ["http://192.168.1.5:8123", "http://localhost:8123"]
    got = probe(tmp_path, env={"ARGUS_CORS_ORIGINS": origins[0]}, argv=("--port", "8123"), origins=origins)
    assert got["sockets"] == {origins[0]: "open", origins[1]: 4003}


def test_server_launcher_allows_the_port_it_was_given(tmp_path):
    # The Windows package runs `backend/server.py --port 8100` and ignores ARGUS_PORT.
    fixed = probe(
        tmp_path,
        launcher="server",
        env={"ARGUS_PORT": "9000"},
        argv=("--no-browser", "--port", "8100"),
        origins=["http://localhost:8100"],
    )
    assert fixed["port"] == 8100
    assert fixed["sockets"] == {"http://localhost:8100": "open"}

    moved = probe(
        tmp_path,
        launcher="server",
        argv=("--no-browser", "--port", "9000"),
        origins=["http://localhost:9000"],
    )
    assert moved["sockets"] == {"http://localhost:9000": "open"}
