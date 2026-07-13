"""
JARVIS CLI — Command-line entry point with subcommands.

Usage:
    jarvis run         Start full system (Hermes + Codex + VSCode + MCP + Orchestrator)
    jarvis serve       Start the API server
    jarvis chat        Quick chat (Orchestrator-only, no Hermes)
    jarvis status      Display system status
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path when running as module
sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.core.config import JARVISConfig, load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("jarvis.cli")


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------

def _build_subsystems(config: JARVISConfig):
    """Create MemoryEngine, SandboxManager, EvolutionController.

    Returns a dict ready for SystemIntegration.start(**kwargs).
    """
    from jarvis.core.llm import init_llm
    from jarvis.memory.engine import MemoryEngine
    from jarvis.sandbox import SandboxManager
    from jarvis.evolution.controller import EvolutionController

    init_llm(config)

    memory = MemoryEngine(
        persist_dir=str(Path(config.data_dir) / "memory"),
        compression_threshold=getattr(config.memory, "auto_compress_threshold", 5000),
    )

    sandbox = SandboxManager(
        engine=getattr(config.sandbox, "engine", "direct"),
        memory_limit=getattr(config.sandbox, "memory_limit", 512),
        cpu_limit=getattr(config.sandbox, "cpu_limit", 1.0),
        timeout_seconds=getattr(config.sandbox, "timeout_seconds", 30),
        network_enabled=getattr(config.sandbox, "network_enabled", False),
    )

    evolution = EvolutionController(data_dir=Path(config.data_dir), config=config)

    return {
        "memory_engine": memory,
        "sandbox_manager": sandbox,
        "evolution_controller": evolution,
    }, (memory, sandbox, evolution)


async def _start_integration(config: JARVISConfig) -> "SystemIntegration":
    """Build subsystems and start SystemIntegration."""
    from jarvis.core.integration import SystemIntegration

    subsystems, (memory, sandbox, evolution) = _build_subsystems(config)

    integration = SystemIntegration()
    await integration.start(**subsystems)

    loaded = integration.orchestrator.registry.list_domains()
    logger.info("Loaded %d domains: %s", len(loaded), [d.name for d in loaded])

    return integration, (memory, sandbox, evolution)


# ---------------------------------------------------------------------------
# jarvis run — Full system startup
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> None:
    """Start the full JARVIS system (Hermes + Codex + VSCode + MCP + Orchestrator)."""

    async def _run() -> None:
        config = load_config()
        integration, subsystems = await _start_integration(config)
        _, (_, _, evolution) = subsystems

        banner = f"""
╔══════════════════════════════════════════════════════════════╗
║     JARVIS v{config.version:<47}║
║     Full System — Hermes + Codex + VSCode + MCP              ║
║     "At your service, sir."                                  ║
╚══════════════════════════════════════════════════════════════╝
"""
        print(banner)
        print(f"Bus subscribers: {integration.bus.subscriber_count}")
        status = integration.status()
        print(f"Domains loaded:  {status['orchestrator']['domains']}")
        print(f"Codex:           {'✓' if status['codex'] else '✗'}")
        print(f"VSCode:          {'✓' if status['vscode'] else '✗'}")
        print(f"MCP Server:      {'✓' if status['hermes_server'] else '✗'}")
        print(f"MCP Client:      {'✓' if status['hermes_client'] else '✗'}")
        print("\nType 'exit' or 'quit' to stop.\n")

        # Interactive loop
        while True:
            try:
                user_input = input("You > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nShutting down...")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                print("Goodbye, sir.")
                break

            result = await integration.execute(user_input)
            if result["success"]:
                output = result.get("output", "")
                domain = result.get("domain", "core")
                print(f"JARVIS [{domain}] > {output}")
            else:
                error = result.get("error", "Unknown error")
                print(f"JARVIS > [ERROR] {error}")

        await integration.shutdown()
        evolution.save_state()
        subsystems[1][1].cleanup()  # sandbox.cleanup()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# jarvis serve — API server
# ---------------------------------------------------------------------------

def cmd_serve(args: argparse.Namespace) -> None:
    """Start the JARVIS API server with full SystemIntegration."""

    async def _serve() -> None:
        config = load_config()
        integration, _ = await _start_integration(config)

        import jarvis.api.server as api_server
        api_server.orchestrator_ref = integration.orchestrator
        api_server.config_ref = config
        api_server._start_time = __import__("time").time()

        import uvicorn
        uvicorn_config = uvicorn.Config(
            app="jarvis.api.server:app",
            host=args.host,
            port=args.port,
            log_level="info",
            reload=args.reload,
        )
        server = uvicorn.Server(uvicorn_config)
        await server.serve()

    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        print("\nServer stopped.")


# ---------------------------------------------------------------------------
# jarvis chat — Quick chat (Orchestrator-only)
# ---------------------------------------------------------------------------

def cmd_chat(args: argparse.Namespace) -> None:
    """Run JARVIS in quick-chat mode (Orchestrator-only, no Hermes wiring)."""
    config = load_config()

    from jarvis.core.llm import init_llm
    from jarvis.memory.engine import MemoryEngine
    from jarvis.sandbox import SandboxManager
    from jarvis.evolution.controller import EvolutionController
    from jarvis.core.orchestrator import Orchestrator

    init_llm(config)

    memory = MemoryEngine(
        persist_dir=str(Path(config.data_dir) / "memory"),
        compression_threshold=getattr(config.memory, "auto_compress_threshold", 5000),
    )
    sandbox = SandboxManager(
        engine=getattr(config.sandbox, "engine", "direct"),
        memory_limit=getattr(config.sandbox, "memory_limit", 512),
        cpu_limit=getattr(config.sandbox, "cpu_limit", 1.0),
        timeout_seconds=getattr(config.sandbox, "timeout_seconds", 30),
        network_enabled=getattr(config.sandbox, "network_enabled", False),
    )
    evolution = EvolutionController(data_dir=Path(config.data_dir), config=config)

    orchestrator = Orchestrator(
        memory_engine=memory,
        evolution_controller=evolution,
        sandbox_manager=sandbox,
    )
    orchestrator.load_all_domains()
    loaded = orchestrator.registry.list_domains()
    logger.info("Loaded %d domains: %s", len(loaded), [d.name for d in loaded])

    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║     JARVIS v{config.version:<47}║
║     Quick Chat — Orchestrator-only                           ║
║     "At your service, sir."                                  ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)
    print("Type 'exit' or 'quit' to stop.\n")

    async def _chat() -> None:
        while True:
            try:
                user_input = input("You > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nShutting down...")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                print("Goodbye, sir.")
                break

            result = await orchestrator.execute(user_input)
            if result.success:
                print(f"JARVIS > {result.output}")
            else:
                print(f"JARVIS > [ERROR] {result.error}")

    try:
        asyncio.run(_chat())
    except KeyboardInterrupt:
        print("\nGoodbye.")


# ---------------------------------------------------------------------------
# jarvis status — System status
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> None:
    """Display JARVIS system status via SystemIntegration."""

    async def _status() -> None:
        config = load_config()
        integration, (memory, sandbox, evolution) = await _start_integration(config)

        status = integration.status()
        mem_stats = await integration.orchestrator.memory.get_stats()
        domains = integration.orchestrator.registry.list_domains()
        topics = integration.topic_summary()

        print(f"JARVIS Core v{config.version}")
        print(f"  Running         : {'yes' if status['running'] else 'no'}")
        print(f"  Domains loaded  : {len(domains)} ({', '.join(d.name for d in domains)})")
        print(f"  Memory entries  : {mem_stats['episodic_count']} episodic + {mem_stats['semantic_count']} semantic")
        print(f"  ChromaDB        : {'enabled' if mem_stats['chromadb_enabled'] else 'disabled'}")
        print(f"  Evolution       : {evolution.total_cycles} cycles, {evolution.average_score:.1%} success rate")
        print(f"  Sandbox engine  : {config.sandbox.engine}")
        print(f"  Bus subscribers : {status['bus']['subscribers']}")
        print(f"  Bus messages    : {status['bus']['messages']}")
        print(f"  Codex           : {'✓' if status['codex'] else '✗'}")
        print(f"  VSCode          : {'✓' if status['vscode'] else '✗'}")
        print(f"  MCP Server      : {'✓' if status['hermes_server'] else '✗'}")
        print(f"  MCP Client      : {'✓' if status['hermes_client'] else '✗'}")
        print(f"  Hermes topics   : {len(topics)} ({', '.join(topics.keys())})")

        await integration.shutdown()
        evolution.save_state()
        sandbox.cleanup()

    asyncio.run(_status())


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point — registered in pyproject.toml [project.scripts]."""
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="JARVIS — Just A Rather Very Intelligent System",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # jarvis run
    run_parser = subparsers.add_parser("run", help="Start full JARVIS system (Hermes + Codex + VSCode + MCP)")
    run_parser.set_defaults(func=cmd_run)

    # jarvis serve
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    serve_parser.set_defaults(func=cmd_serve)

    # jarvis chat
    chat_parser = subparsers.add_parser("chat", help="Quick chat mode (Orchestrator-only)")
    chat_parser.set_defaults(func=cmd_chat)

    # jarvis status
    status_parser = subparsers.add_parser("status", help="Display system status")
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
