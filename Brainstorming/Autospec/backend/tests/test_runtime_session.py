"""Supervisor session origin/identity/persistence; product probes only in Docker."""
import json
import os
import socket
import subprocess
import time
import urllib.request
from types import SimpleNamespace

import pytest

from autospec.orchestrator import isolated_validation as runtime_module
from autospec.orchestrator.isolated_validation import RuntimeSession
from autospec.orchestrator.validation_environment import LinuxEnvironmentManager, snapshot_product


class FakeDocker:
    def __init__(self):
        self.containers = {}
        self.volume = None
        self.calls = []
        self.counter = 0

    def tracked(self, argv, stdin, cwd, timeout):
        self.calls.append((argv, stdin, cwd, timeout))
        if argv[1:3] == ['volume', 'create']:
            owner = next(value.split('=', 1)[1] for value in argv if value.startswith('autospec.run_id='))
            self.volume = {'Name': argv[-1], 'Driver': 'local', 'CreatedAt': '2026-10-12T01:00:00Z',
                           'Labels': {'autospec.run_id': owner, 'autospec.kind': 'validation-state'}}
            return 0, argv[-1] + '\n', ''
        if argv[1] == 'run' and '-d' in argv:
            self.counter += 1
            identifier = f'{self.counter:064x}'
            name = argv[argv.index('--name') + 1]
            owner = next(value.split('=', 1)[1] for value in argv if value.startswith('autospec.run_id='))
            self.containers[identifier] = {'Id': identifier, 'Name': name,
                'Config': {'Labels': {'autospec.run_id': owner, 'autospec.kind': 'sandbox'}}}
            return 0, identifier + '\n', ''
        return 0, 'owned-output', ''

    def call(self, argv, **kwargs):
        self.calls.append((argv, None, None, None))
        if argv[1:3] == ['volume', 'inspect']:
            return SimpleNamespace(returncode=0 if self.volume else 1,
                stdout=json.dumps(self.volume) if self.volume else '', stderr='' if self.volume else 'no such volume')
        if argv[1:3] == ['volume', 'rm']:
            self.volume = None
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if argv[1:3] == ['container', 'inspect']:
            found = next((data for identifier, data in self.containers.items() if argv[3] in {identifier, data['Name']}), None)
            if found and argv[-1] == '{{json .State}}':
                return SimpleNamespace(returncode=0, stdout=json.dumps({'Running': True}), stderr='')
            return SimpleNamespace(returncode=0 if found else 1, stdout=json.dumps(found) if found else '',
                                   stderr='' if found else 'no such container')
        if argv[1:3] == ['container', 'rm']:
            self.containers.pop(argv[-1], None)
        return SimpleNamespace(returncode=0, stdout='', stderr='')


@pytest.fixture
def docker_fake(monkeypatch):
    from autospec.orchestrator import sandbox
    fake = FakeDocker()
    monkeypatch.setattr(runtime_module, '_run_tracked', fake.tracked)
    monkeypatch.setattr(runtime_module, '_docker_call', fake.call)
    monkeypatch.setattr(sandbox, '_docker_call', fake.call)
    monkeypatch.setattr(runtime_module, 'require_sandbox', lambda *a, **kw: None)
    return fake


def test_origin_reserved_before_launch_and_restart_owns_same_db(tmp_path, docker_fake):
    session = RuntimeSession(tmp_path, 'attested', ['python', 'main.py'], application_origin=True,
                             local_cookie_mode=True, persistent_database=True)
    origin = session.origin
    assert origin.startswith('http://127.0.0.1:') and not docker_fake.calls
    assert session.env['APP_ORIGIN'] == origin and session.env['SESSION_COOKIE_SECURE'] == 'false'
    assert session.database_path == '/var/lib/autospec-validation/support.sqlite'
    with session:
        first = session.identifier
        assert session.is_running()
        volume = session.volume_name
        assert session.exec(['python', '-c', 'print(1)'], stdin='data', timeout=2) == (0, 'owned-output', '')
        command, stdin, cwd, timeout = docker_fake.calls[-1]
        assert command[:4] == ['docker', 'exec', '-i', first] and stdin == 'data' and cwd is None
        session.restart()
        assert session.origin == origin and session.volume_name == volume and session.identifier != first
        assert first not in docker_fake.containers
        launches = [call[0] for call in docker_fake.calls if call[0][1] == 'run' and '-d' in call[0]]
        assert all('none' == command[command.index('--network') + 1] for command in launches)
        assert all(command[command.index('-v') + 1].endswith('/app:ro') for command in launches)
        assert all(f'APP_ORIGIN={origin}' in command for command in launches)
    assert not docker_fake.containers and docker_fake.volume is None
    assert not session.is_running()
    with socket.socket() as probe:
        assert probe.connect_ex(('127.0.0.1', session.host_port)) != 0


def test_close_unstarted_session_does_not_deadlock_or_touch_resources(tmp_path, docker_fake):
    session = RuntimeSession(tmp_path, 'attested', ['python'])
    start = time.monotonic()
    session.close()
    session.close()
    assert time.monotonic() - start < 1
    assert not any(call[0][1:3] == ['container', 'rm'] for call in docker_fake.calls)
    with pytest.raises(RuntimeError, match='not active'):
        session.exec(['python'])


def test_exec_and_volume_cleanup_refuse_replaced_identities(tmp_path, docker_fake):
    session = RuntimeSession(tmp_path, 'attested', ['python'], persistent_database=True)
    session.__enter__()
    try:
        docker_fake.containers[session.identifier]['Config']['Labels']['autospec.run_id'] = 'foreign'
        before = len(docker_fake.calls)
        with pytest.raises(RuntimeError, match='ownership identity'):
            session.exec(['python'])
        assert not any(call[0][1] == 'exec' for call in docker_fake.calls[before:])
        docker_fake.containers[session.identifier]['Config']['Labels']['autospec.run_id'] = session.owner
        docker_fake.volume['CreatedAt'] = 'replacement'
        before = len(docker_fake.calls)
        with pytest.raises(RuntimeError, match='volume identity changed'):
            session.close()
        assert not any(call[0][1:3] == ['volume', 'rm'] for call in docker_fake.calls[before:])
    finally:
        docker_fake.volume['CreatedAt'] = '2026-10-12T01:00:00Z'
        session.close()


def test_failed_exec_stops_daemon_container_not_just_client(tmp_path, docker_fake, monkeypatch):
    session = RuntimeSession(tmp_path, 'attested', ['python'], persistent_database=True)
    with session:
        original = docker_fake.tracked
        def timeout(argv, *args):
            if argv[1] == 'exec':
                raise subprocess.TimeoutExpired(argv, 1)
            return original(argv, *args)
        monkeypatch.setattr(runtime_module, '_run_tracked', timeout)
        with pytest.raises(subprocess.TimeoutExpired):
            session.exec(['python'], timeout=1)
        assert session.closed and not docker_fake.containers and docker_fake.volume is None


def test_interrupted_volume_creation_cleans_daemon_resource(tmp_path, docker_fake, monkeypatch):
    session = RuntimeSession(tmp_path, 'attested', ['python'], persistent_database=True)
    original = docker_fake.tracked
    def interrupted(argv, *args):
        result = original(argv, *args)
        if argv[1:3] == ['volume', 'create']:
            raise subprocess.TimeoutExpired(argv, 1)
        return result
    monkeypatch.setattr(runtime_module, '_run_tracked', interrupted)
    with pytest.raises(subprocess.TimeoutExpired):
        session.__enter__()
    assert session.closed and docker_fake.volume is None


@pytest.mark.parametrize('options', [
    {'env': {'APP_ORIGIN': 'http://evil'}},
    {'env': {'SESSION_COOKIE_SECURE': 'false'}},
    {'local_cookie_mode': True},
    {'env': {'DATABASE_URL': 'sqlite:////tmp/../../private.db'}},
    {'env': {'PYTHONPATH': '/etc'}},
    {'connection_timeout': float('inf')},
])
def test_arbitrary_origin_cookie_db_or_python_env_is_not_an_escape(tmp_path, options):
    with pytest.raises(RuntimeError, match='ISOLATION_UNAVAILABLE'):
        RuntimeSession(tmp_path, 'attested', ['python'], **options)


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION') != '1', reason='Opt-in real owned SQLite restart and strict-origin HTTP')
def test_real_stable_origin_owned_sqlite_restart_and_exact_cleanup(tmp_path):
    root = tmp_path / 'product'
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nname="runtime-persistence-proof"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
    # This source is NEVER run by the host. It is copied into the filtered stage
    # then executed only as UID65532 in the owned net-none Linux container.
    (root / 'main.py').write_text('''import os,sqlite3,json
from http.server import BaseHTTPRequestHandler,HTTPServer
path=os.environ['DATABASE_URL'].removeprefix('sqlite:///')
with sqlite3.connect(path) as db:
 db.execute('create table if not exists counter(value integer)')
 if not db.execute('select count(*) from counter').fetchone()[0]: db.execute('insert into counter values(0)')
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  with sqlite3.connect(path) as db: value=db.execute('select value from counter').fetchone()[0]
  body=json.dumps({'value':value,'origin':os.environ['APP_ORIGIN'],'cookie':os.environ['SESSION_COOKIE_SECURE'],'uid':os.getuid()}).encode()
  self.send_response(200);self.end_headers();self.wfile.write(body)
 def do_POST(self):
  if self.headers.get('Origin')!=os.environ['APP_ORIGIN']:
   self.send_response(403);self.end_headers();return
  with sqlite3.connect(path) as db: db.execute('update counter set value=value+1')
  self.send_response(204);self.end_headers()
HTTPServer(('0.0.0.0',8000),Handler).serve_forever()
''')
    manager = LinuxEnvironmentManager(tmp_path / 'cache')
    manager.ensure_lock(root, 'python')
    environment = manager.prepare(root, 'python', 'runtime')
    stage = snapshot_product(root, tmp_path / 'stage')
    session = RuntimeSession(stage, environment.image, ['/opt/venv/bin/python', 'main.py'],
                             application_origin=True, local_cookie_mode=True, persistent_database=True)
    origin = session.origin
    from autospec.orchestrator.sandbox import _docker_call

    def ready():
        deadline = time.monotonic() + 20
        while True:
            try:
                with urllib.request.urlopen(origin, timeout=10) as response:
                    return json.load(response)
            except OSError:
                if time.monotonic() > deadline:
                    raise AssertionError(session.logs())
                time.sleep(.1)

    with socket.socket() as unrelated:
        unrelated.bind(('127.0.0.1', 0)); unrelated.listen()
        unrelated_port = unrelated.getsockname()[1]
        with session:
            assert session.is_running()
            assert ready() == {'value': 0, 'origin': origin, 'cookie': 'false', 'uid': 65532}
            request = urllib.request.Request(origin, method='POST', headers={'Origin': origin})
            with urllib.request.urlopen(request, timeout=10) as response:
                assert response.status == 204
            from urllib.error import HTTPError
            wrong = urllib.request.Request(origin, method='POST', headers={'Origin': 'http://foreign.invalid'})
            with pytest.raises(HTTPError) as refused:
                urllib.request.urlopen(wrong, timeout=10)
            assert refused.value.code == 403
            first = session.identifier
            volume = session.volume_name
            inspect = _docker_call(['docker', 'container', 'inspect', first], capture_output=True, text=True, timeout=10)
            data = json.loads(inspect.stdout)[0]
            assert data['HostConfig']['NetworkMode'] == 'none'
            assert data['HostConfig']['ReadonlyRootfs'] and data['HostConfig']['CapDrop'] == ['ALL']
            assert all(mount['Type'] == 'volume' or not mount['RW'] for mount in data['Mounts'])
            probe = '''import os,socket,json
assert 'ANTHROPIC_API_KEY' not in os.environ
assert not os.path.exists('/var/run/docker.sock')
try: open('/app/escape','w')
except OSError: pass
else: raise AssertionError('runtime source write')
s=socket.socket();s.settimeout(.2)
try:s.connect(('1.1.1.1',443))
except OSError:pass
else:raise AssertionError('network escaped')
print('safe')
'''
            rc, out, err = session.exec(['/opt/venv/bin/python', '-c', probe], timeout=5)
            assert rc == 0 and out.strip() == 'safe', err
            session.restart()
            assert session.identifier != first and session.origin == origin and session.volume_name == volume
            assert ready()['value'] == 1
            observer = "import sqlite3,json; print(json.dumps(sqlite3.connect('/var/lib/autospec-validation/support.sqlite').execute('select value from counter').fetchone()))"
            rc, out, err = session.exec(['/opt/venv/bin/python', '-c', observer], timeout=5)
            assert rc == 0 and json.loads(out) == [1], err
            final = session.identifier
        assert unrelated.fileno() >= 0 and unrelated.getsockname()[1] == unrelated_port
        with socket.socket() as sentinel:
            assert sentinel.connect_ex(('127.0.0.1', unrelated_port)) == 0
    for kind, identifier in [('container', first), ('container', final), ('volume', volume)]:
        result = _docker_call(['docker', kind, 'inspect', identifier], capture_output=True, text=True, timeout=10)
        assert result.returncode != 0
    with socket.socket() as probe:
        assert probe.connect_ex(('127.0.0.1', session.host_port)) != 0
    # An exec timeout must also stop daemon-side work, not only the Windows
    # docker client Job. This sleep executes in Docker, never on the host.
    timed = RuntimeSession(stage, environment.image, ['/opt/venv/bin/python', 'main.py'],
                           application_origin=True, local_cookie_mode=True, persistent_database=True)
    with timed:
        timed_id, timed_volume = timed.identifier, timed.volume_name
        with pytest.raises(subprocess.TimeoutExpired):
            timed.exec(['/opt/venv/bin/python', '-c', 'import time; time.sleep(60)'], timeout=3)
        assert timed.closed and not timed.is_running()
    for kind, identifier in [('container', timed_id), ('volume', timed_volume)]:
        result = _docker_call(['docker', kind, 'inspect', identifier], capture_output=True, text=True, timeout=10)
        assert result.returncode != 0
