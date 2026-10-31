"""Safety tests for the explicit PostgreSQL backup-before-migration gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_DATA_DIR = Path(__file__).resolve().parents[2] / "scripts" / "home-server" / "data"
if str(_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(_DATA_DIR))

import pg_deploy_gate as gate  # noqa: E402


def _args(tmp_path: Path, *, execute: bool = True, confirmed: bool = True):
    return SimpleNamespace(
        project="gasflow-test",
        compose_files=["docker-compose.prod.yml"],
        env_file=".env.test",
        backup_dir=str(tmp_path / "offhost"),
        database_name="gasflow_test",
        confirm_off_host=confirmed,
        execute=execute,
    )


def test_dry_run_never_invokes_commands(tmp_path):
    calls = []
    result = gate._execute_gate(
        _args(tmp_path, execute=False),
        repository_root=tmp_path / "repo",
        runner=lambda *args, **kwargs: calls.append(args),
    )
    assert result["status"] == "dry-run"
    assert result["migration_executed"] is False
    assert calls == []


def test_offhost_confirmation_is_required_before_any_command(tmp_path):
    calls = []
    with pytest.raises(gate.GateRefusal, match="confirmação humana"):
        gate._execute_gate(
            _args(tmp_path, confirmed=False),
            repository_root=tmp_path / "repo",
            runner=lambda *args, **kwargs: calls.append(args),
            destination_validator=lambda *_: tmp_path / "offhost",
        )
    assert calls == []


def test_same_filesystem_backup_destination_is_refused(tmp_path):
    repo = tmp_path / "repo"
    destination = tmp_path / "offhost"
    repo.mkdir()
    destination.mkdir()
    with pytest.raises(gate.GateRefusal, match="mesmo filesystem"):
        gate._validate_backup_destination(destination, repo)


def test_verified_backup_precedes_migration(tmp_path):
    backup_root = tmp_path / "offhost"
    backup_root.mkdir()
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        if any("pg_dump" in part for part in command):
            kwargs["stdout"].write(gate.PG_MAGIC + b"synthetic custom archive")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    result = gate._execute_gate(
        _args(tmp_path),
        repository_root=tmp_path / "repo",
        runner=fake_runner,
        destination_validator=lambda *_: backup_root,
        timestamp="20261030T120000Z",
    )

    dump_index = next(i for i, command in enumerate(calls) if any("pg_dump" in part for part in command))
    list_index = next(i for i, command in enumerate(calls) if "--list" in command)
    migration_index = next(i for i, command in enumerate(calls) if "upgrade" in command)
    verify_index = next(
        i for i, command in enumerate(calls) if any("_assert_postgres_schema_current" in part for part in command)
    )
    assert dump_index < list_index < migration_index < verify_index
    assert not any("up" in command for command in calls)
    assert result["status"] == "migration-completed"
    assert result["dump"]["magic_ok"] is True
    manifest_path = Path(result["destination"]) / "database.dump.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "migration-completed"
    assert manifest["dump"]["pg_restore_list_verified"] is True


def test_migration_failure_keeps_backup_and_marks_partial(tmp_path):
    backup_root = tmp_path / "offhost"
    backup_root.mkdir()
    calls = []

    def fail_migration(command, **kwargs):
        calls.append(command)
        if any("pg_dump" in part for part in command):
            kwargs["stdout"].write(gate.PG_MAGIC + b"synthetic custom archive")
        if "upgrade" in command:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"redacted")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    with pytest.raises(gate.GateRefusal, match="migration pode estar parcial"):
        gate._execute_gate(
            _args(tmp_path),
            repository_root=tmp_path / "repo",
            runner=fail_migration,
            destination_validator=lambda *_: backup_root,
            timestamp="20261030T120002Z",
        )

    manifests = list(backup_root.glob("*/database.dump.manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "migration-failed-or-partial"
    assert (manifests[0].parent / "database.dump").is_file()
    assert not any("_assert_postgres_schema_current" in part for command in calls for part in command)


def test_dump_failure_never_runs_migration(tmp_path):
    backup_root = tmp_path / "offhost"
    backup_root.mkdir()
    calls = []

    def failing_dump(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"redacted")

    with pytest.raises(gate.GateRefusal, match="Alembic não foi executado"):
        gate._execute_gate(
            _args(tmp_path),
            repository_root=tmp_path / "repo",
            runner=failing_dump,
            destination_validator=lambda *_: backup_root,
            timestamp="20261030T120001Z",
        )
    assert not any("upgrade" in command for command in calls)
