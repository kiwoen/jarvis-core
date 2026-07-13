"""Tests for JARVIS CLI — argument parsing and command lifecycle."""
from __future__ import annotations

import argparse
import io
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.cli import main as cli_main
from jarvis.core.config import load_config


# ── Argument Parsing ─────────────────────────────────────────────────────────

class TestArgumentParsing:
    def test_no_args_prints_help_and_exits(self):
        """No subcommand → print help, exit code 1."""
        with patch.object(sys, "argv", ["jarvis"]):
            with pytest.raises(SystemExit) as exc_info:
                cli_main()
            assert exc_info.value.code == 1

    def test_run_subcommand_parsed(self):
        """jarvis run → cmd_run is set as handler."""
        with patch.object(sys, "argv", ["jarvis", "run"]):
            with patch("jarvis.cli.cmd_run") as mock_run:
                cli_main()
                mock_run.assert_called_once()

    def test_chat_subcommand_parsed(self):
        """jarvis chat → cmd_chat is set as handler."""
        with patch.object(sys, "argv", ["jarvis", "chat"]):
            with patch("jarvis.cli.cmd_chat") as mock_chat:
                cli_main()
                mock_chat.assert_called_once()

    def test_serve_subcommand_parsed(self):
        """jarvis serve → cmd_serve with defaults."""
        with patch.object(sys, "argv", ["jarvis", "serve"]):
            with patch("jarvis.cli.cmd_serve") as mock_serve:
                cli_main()
                args = mock_serve.call_args[0][0]
                assert args.host == "127.0.0.1"
                assert args.port == 8000
                assert args.reload is False

    def test_serve_subcommand_custom_args(self):
        """jarvis serve --host 0.0.0.0 --port 9000 --reload."""
        with patch.object(sys, "argv", ["jarvis", "serve", "--host", "0.0.0.0", "--port", "9000", "--reload"]):
            with patch("jarvis.cli.cmd_serve") as mock_serve:
                cli_main()
                args = mock_serve.call_args[0][0]
                assert args.host == "0.0.0.0"
                assert args.port == 9000
                assert args.reload is True

    def test_status_subcommand_parsed(self):
        """jarvis status → cmd_status handler."""
        with patch.object(sys, "argv", ["jarvis", "status"]):
            with patch("jarvis.cli.cmd_status") as mock_status:
                cli_main()
                mock_status.assert_called_once()

    def test_unknown_subcommand_help_output(self):
        """Unknown subcommand should trigger argparse error."""
        with patch.object(sys, "argv", ["jarvis", "unknown"]):
            with pytest.raises(SystemExit):
                cli_main()


# ── Helpers ─────────────────────────────────────────────────────────────────

class TestBuildSubsystems:
    def test_build_subsystems_returns_all_three(self):
        """_build_subsystems returns memory, sandbox, evolution + wrapper dict."""
        from jarvis.cli import _build_subsystems

        config = load_config()
        subsystems, (memory, sandbox, evolution) = _build_subsystems(config)

        assert "memory_engine" in subsystems
        assert "sandbox_manager" in subsystems
        assert "evolution_controller" in subsystems
        assert memory is not None
        assert sandbox is not None
        assert evolution is not None


    def test_build_subsystems_with_different_config(self):
        """Different config values propagate to subsystems."""
        from jarvis.cli import _build_subsystems

        config = load_config()
        # Override sandbox config
        config.sandbox.timeout_seconds = 99
        subsystems, (memory, sandbox, evolution) = _build_subsystems(config)

        assert sandbox.timeout_seconds == 99


# ── Integration Smoke Tests ─────────────────────────────────────────────────

class TestCLICommands:
    """Lightweight smoke tests — verify commands don't crash on startup."""

    @pytest.mark.asyncio
    async def test_cmd_status_starts_and_stops(self):
        """cmd_status should start integration, print status, and shutdown."""
        from jarvis.cli import _start_integration
        from jarvis.core.config import load_config

        config = load_config()
        integration, (memory, sandbox, evolution) = await _start_integration(config)

        status = integration.status()
        assert status["running"] is True
        assert status["orchestrator"]["domains"] >= 8
        assert status["bus"]["subscribers"] > 0
        assert status["codex"] is True
        assert status["vscode"] is True

        await integration.shutdown()
        evolution.save_state()
        sandbox.cleanup()

    @pytest.mark.asyncio
    async def test_integration_execute_works(self):
        """execute() through integration returns valid result dict."""
        from jarvis.cli import _start_integration
        from jarvis.core.config import load_config

        config = load_config()
        integration, (memory, sandbox, evolution) = await _start_integration(config)

        result = await integration.execute("你好")
        assert isinstance(result, dict)
        assert "success" in result
        assert "domain" in result
        assert "output" in result

        await integration.shutdown()
        evolution.save_state()
        sandbox.cleanup()

    @pytest.mark.asyncio
    async def test_integration_topic_summary(self):
        """topic_summary includes codex and vscode registrations."""
        from jarvis.cli import _start_integration
        from jarvis.core.config import load_config

        config = load_config()
        integration, (memory, sandbox, evolution) = await _start_integration(config)

        topics = integration.topic_summary()
        topic_names = list(topics.keys())
        assert any("codex" in t for t in topic_names)
        assert any("vscode" in t for t in topic_names)

        await integration.shutdown()
        evolution.save_state()
        sandbox.cleanup()


# ── Edge Cases ──────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_serve_with_all_options(self):
        """Verify serve command handles all CLI options."""
        from jarvis.cli import main as cli_main

        argv = ["jarvis", "serve", "--host", "0.0.0.0", "--port", "8080", "--reload"]
        with patch.object(sys, "argv", argv):
            with patch("jarvis.cli.cmd_serve") as mock:
                cli_main()
                args = mock.call_args[0][0]
                assert args.host == "0.0.0.0"
                assert args.port == 8080
                assert args.reload is True

    def test_run_subcommand_minimal(self):
        """jarvis run with no extra flags."""
        argv = ["jarvis", "run"]
        with patch.object(sys, "argv", argv):
            with patch("jarvis.cli.cmd_run") as mock:
                cli_main()
                mock.assert_called_once()
