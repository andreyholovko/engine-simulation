"""dyno_cli.py had zero automated coverage -- it's a thin wrapper, but it's
also the fastest way to actually drive the sim (README calls it out as
such), and its command parsing/dispatch is real behavior worth locking in
independent of the engine_sim core it wraps.
"""

import dyno_cli
from engine_sim import DynoSession


def _run_cli(monkeypatch, commands):
    inputs = iter(commands)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    dyno_cli.main()


def test_status_line_formats_all_fields_and_flags_rev_limit():
    session = DynoSession()
    snapshot = session.tick(dt=0.01, throttle_percent=0.0)
    line = dyno_cli.status_line(snapshot)
    assert "rpm=" in line and "torque=" in line and "power=" in line
    assert "iat=" in line
    assert "[REV LIMIT]" not in line

    snapshot.rev_limiter_active = True  # DynoSnapshot is a plain dataclass, not frozen
    assert "[REV LIMIT]" in dyno_cli.status_line(snapshot)


def test_engines_command_lists_all_choices(monkeypatch, capsys):
    _run_cli(monkeypatch, ["engines", "quit"])
    out = capsys.readouterr().out
    for key, name in DynoSession.list_engine_choices():
        assert key in out
        assert name in out


def test_engine_command_switches_engine(monkeypatch, capsys):
    _run_cli(monkeypatch, ["engine b58_340i", "status", "quit"])
    out = capsys.readouterr().out
    assert "BMW B58B30" in out


def test_engine_command_rejects_unknown_key_without_crashing(monkeypatch, capsys):
    _run_cli(monkeypatch, ["engine not_a_real_engine", "status", "quit"])
    out = capsys.readouterr().out
    assert "unknown engine choice" in out
    # Still alive and on the default engine afterward.
    assert "EA888" in out


def test_turbos_command_lists_current_engines_choices(monkeypatch, capsys):
    _run_cli(monkeypatch, ["turbos", "quit"])
    out = capsys.readouterr().out
    session = DynoSession()
    for key, name in session.list_turbo_choices():
        assert key in out
        assert name in out


def test_turbo_command_switches_turbo_on_same_engine(monkeypatch, capsys):
    _run_cli(monkeypatch, ["turbo is38", "status", "quit"])
    out = capsys.readouterr().out
    assert "turbo: IHI IS38" in out
    assert "EA888" in out  # still the same engine


def test_turbo_command_rejects_unknown_key_without_crashing(monkeypatch, capsys):
    _run_cli(monkeypatch, ["turbo not_a_real_turbo", "status", "quit"])
    out = capsys.readouterr().out
    assert "unknown turbo choice" in out
    assert "EA888" in out  # still alive, still on the default engine


def test_throttle_and_step_advance_the_session(monkeypatch, capsys):
    _run_cli(monkeypatch, ["throttle 100", "step 2", "quit"])
    out = capsys.readouterr().out
    assert "throttle set to 100%" in out
    # step prints at least one snapshot line.
    assert "rpm=" in out


def test_boost_command_auto_and_numeric(monkeypatch, capsys):
    _run_cli(monkeypatch, ["boost 50", "boost auto", "quit"])
    out = capsys.readouterr().out
    assert "boost target: 50%" in out
    assert "boost target: auto" in out


def test_afr_command_auto_and_numeric(monkeypatch, capsys):
    _run_cli(monkeypatch, ["afr 11.5", "afr auto", "quit"])
    out = capsys.readouterr().out
    assert "AFR override: 11.50" in out
    assert "AFR: auto" in out


def test_octane_command_auto_and_numeric(monkeypatch, capsys):
    _run_cli(monkeypatch, ["octane 85", "octane auto", "quit"])
    out = capsys.readouterr().out
    assert "octane set to 85" in out
    assert "octane: auto" in out


def test_sweep_prints_peak_torque_and_power(monkeypatch, capsys):
    _run_cli(monkeypatch, ["sweep", "quit"])
    out = capsys.readouterr().out
    assert "peak torque:" in out
    assert "peak power:" in out


def test_unknown_command_shows_hint_not_a_crash(monkeypatch, capsys):
    _run_cli(monkeypatch, ["not_a_real_command", "quit"])
    out = capsys.readouterr().out
    assert "unknown command" in out


def test_quit_and_exit_both_end_the_session(monkeypatch, capsys):
    _run_cli(monkeypatch, ["exit"])
    out = capsys.readouterr().out
    assert "Ready." in out  # got past startup before exiting cleanly


def test_blank_line_is_ignored_not_treated_as_a_command(monkeypatch, capsys):
    _run_cli(monkeypatch, ["", "  ", "quit"])
    out = capsys.readouterr().out
    assert "unknown command" not in out


def test_eof_ends_the_session_cleanly(monkeypatch, capsys):
    """A real terminal sends EOFError on Ctrl+D -- must exit cleanly, same
    as an explicit quit, not crash."""
    def raise_eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    dyno_cli.main()  # must return, not raise
    assert "Ready." in capsys.readouterr().out
