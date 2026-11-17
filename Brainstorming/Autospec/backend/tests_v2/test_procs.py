import sys
import time

from autospec.core.procs import run_capped


def test_captures_output_and_exit_code():
    result = run_capped([sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"],
                        timeout_s=30)
    assert result.returncode == 3
    assert result.stdout.strip() == "out"
    assert "err" in result.stderr
    assert not result.timed_out


def test_stdin_is_fed_then_closed():
    result = run_capped([sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
                        input_text="héllo\nworld", timeout_s=30)
    assert result.stdout.strip() == "HÉLLO\nWORLD"


def test_timeout_kills_the_whole_tree_quickly():
    # The child spawns a grandchild that would outlive a plain kill of its parent.
    code = ("import subprocess, sys, time;"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
            "time.sleep(60)")
    started = time.monotonic()
    result = run_capped([sys.executable, "-c", code], timeout_s=2)
    assert result.timed_out and result.returncode is None
    assert time.monotonic() - started < 20


def test_large_output_does_not_deadlock():
    result = run_capped([sys.executable, "-c", "print('x' * 2_000_000)"], timeout_s=30)
    assert len(result.stdout.strip()) == 2_000_000
