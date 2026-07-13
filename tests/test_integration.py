"""Tests for SystemIntegration — full-stack wiring verification."""
import asyncio

import pytest

from jarvis.core.integration import SystemIntegration


# ── Lifecycle ───────────────────────────────────────────────────────────────

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_shutdown(self):
        """Full startup → shutdown cycle completes without error."""
        integration = SystemIntegration()
        assert not integration.running

        await integration.start()
        assert integration.running
        assert integration.bus is not None
        assert integration.codex is not None
        assert integration.vscode is not None
        assert integration.orchestrator is not None

        await integration.shutdown()
        assert not integration.running

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self):
        """Calling start() twice should not crash."""
        integration = SystemIntegration()
        await integration.start()
        await integration.start()  # should log warning, not crash
        await integration.shutdown()

    @pytest.mark.asyncio
    async def test_double_shutdown_is_safe(self):
        """Calling shutdown() twice should not crash."""
        integration = SystemIntegration()
        await integration.start()
        await integration.shutdown()
        await integration.shutdown()  # should be a no-op

    @pytest.mark.asyncio
    async def test_access_before_start_raises(self):
        """Accessing bus/orchestrator before start() raises RuntimeError."""
        integration = SystemIntegration()
        with pytest.raises(RuntimeError):
            _ = integration.bus
        with pytest.raises(RuntimeError):
            _ = integration.orchestrator


# ── Status & Health Check ───────────────────────────────────────────────────

class TestStatus:
    @pytest.mark.asyncio
    async def test_status_after_start(self):
        integration = SystemIntegration()
        await integration.start()

        status = integration.status()
        assert status["running"] is True
        assert status["bus"]["subscribers"] > 0
        assert status["codex"] is True
        assert status["vscode"] is True
        assert status["hermes_server"] is True
        assert status["hermes_client"] is True
        assert status["orchestrator"]["loaded"] is True
        assert status["orchestrator"]["domains"] >= 8

        await integration.shutdown()

    @pytest.mark.asyncio
    async def test_status_after_shutdown(self):
        integration = SystemIntegration()
        await integration.start()
        await integration.shutdown()

        status = integration.status()
        assert status["running"] is False

    @pytest.mark.asyncio
    async def test_topic_summary(self):
        integration = SystemIntegration()
        await integration.start()

        topics = integration.topic_summary()
        # Should have codex and vscode registrations
        topic_names = list(topics.keys())
        assert any("codex" in t for t in topic_names), f"Missing codex topics in {topic_names}"
        assert any("vscode" in t for t in topic_names), f"Missing vscode topics in {topic_names}"

        await integration.shutdown()


# ── Bus Routing ─────────────────────────────────────────────────────────────

class TestBusRouting:
    """Verify that messages on bus topics reach the correct engines."""

    @pytest.mark.asyncio
    async def test_codex_analyze_via_bus(self):
        """Publish to codex.analyze.python → CodexEngine responds."""
        integration = SystemIntegration()
        await integration.start()

        from jarvis.hermes.bus import Message, MessageType, Topic

        # Send a codex analyze request
        reply = await integration.bus.request(
            Topic("codex.analyze.python"),
            payload={"code": "def hello():\n    print('world')", "language": "python"},
            sender="test",
            timeout=5.0,
        )
        assert reply is not None
        assert reply.payload is not None
        # CodexEngine should return analysis data
        assert isinstance(reply.payload, dict)

        await integration.shutdown()

    @pytest.mark.asyncio
    async def test_vscode_open_file_via_bus(self):
        """Publish to vscode.file.open → VSCodeBridge responds."""
        integration = SystemIntegration()
        await integration.start()

        from jarvis.hermes.bus import Message, MessageType, Topic

        reply = await integration.bus.request(
            Topic("vscode.file.open"),
            payload={"path": "C:/test/main.py", "line": 42},
            sender="test",
            timeout=5.0,
        )
        assert reply is not None
        assert isinstance(reply.payload, dict)

        await integration.shutdown()

    @pytest.mark.asyncio
    async def test_topic_isolation(self):
        """Codex topics only reach Codex, VSCode topics only VSCode."""
        integration = SystemIntegration()
        await integration.start()

        topics = integration.topic_summary()
        codex_topics = [t for t in topics if "codex" in t]
        vscode_topics = [t for t in topics if "vscode" in t]

        # Should be separate subscriptions
        assert len(codex_topics) > 0
        assert len(vscode_topics) > 0
        # No topic should appear in both
        assert set(codex_topics).isdisjoint(set(vscode_topics))

        await integration.shutdown()


# ── Orchestrator Integration ────────────────────────────────────────────────

class TestOrchestratorIntegration:
    @pytest.mark.asyncio
    async def test_execute_via_integration(self):
        """Simple non-coding intent goes through orchestrator."""
        integration = SystemIntegration()
        await integration.start()

        result = await integration.execute("帮我查一下今天的天气")
        assert "success" in result
        # Should route to some domain (likely RESEARCH or PERSONAL based on keywords)

        await integration.shutdown()

    @pytest.mark.asyncio
    async def test_execute_code_intent(self):
        """Coding intent is recognized by orchestrator."""
        integration = SystemIntegration()
        await integration.start()

        result = await integration.execute("写一段 Python 代码实现快速排序")
        assert "success" in result
        assert result["domain"] in ("ENGINEERING", "CREATOR")

        await integration.shutdown()

    @pytest.mark.asyncio
    async def test_orchestrator_has_bus(self):
        """Orchestrator should have bus injected after integration start."""
        integration = SystemIntegration()
        await integration.start()

        assert hasattr(integration.orchestrator, "bus")
        assert integration.orchestrator.bus is integration.bus

        await integration.shutdown()


# ── Error Handling ──────────────────────────────────────────────────────────

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_execute_before_start_raises(self):
        """execute() before start() should raise RuntimeError."""
        integration = SystemIntegration()
        with pytest.raises(RuntimeError):
            await integration.execute("hello")

    @pytest.mark.asyncio
    async def test_shutdown_handles_missing_components(self):
        """shutdown() should be safe even if some components are None."""
        integration = SystemIntegration()

        # Manually set some components to None to simulate partial init
        integration._running = True
        integration._bus = None  # simulate message bus failure
        integration._codex_engine = None
        integration._vscode_bridge = None

        # Should not crash
        await integration.shutdown()
        assert not integration.running


# ── Concurrent Access ───────────────────────────────────────────────────────

class TestConcurrent:
    @pytest.mark.asyncio
    async def test_concurrent_bus_requests(self):
        """Multiple concurrent codex requests should not interfere."""
        integration = SystemIntegration()
        await integration.start()

        from jarvis.hermes.bus import Topic

        async def request_codex(i: int) -> dict:
            try:
                reply = await integration.bus.request(
                    Topic("codex.analyze.python"),
                    payload={"code": f"def func{i}(): pass", "language": "python"},
                    sender=f"test-concurrent-{i}",
                    timeout=5.0,
                )
                return {"success": True, "i": i, "payload": reply.payload}
            except Exception as e:
                return {"success": False, "i": i, "error": str(e)}

        results = await asyncio.gather(*[request_codex(i) for i in range(5)])
        succeeded = [r for r in results if r["success"]]
        assert len(succeeded) >= 3  # At least most should succeed

        await integration.shutdown()

    @pytest.mark.asyncio
    async def test_start_shutdown_multiple_cycles(self):
        """Can start and shutdown multiple times (resilience)."""
        integration = SystemIntegration()

        for cycle in range(2):
            await integration.start()
            assert integration.running
            status = integration.status()
            assert status["running"] is True
            await integration.shutdown()
            assert not integration.running
