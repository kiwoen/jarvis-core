#!/usr/bin/env python3
"""Emperor Core CLI — 多领域 AI Agent 管理系统命令行工具。

Usage:
    jarvis serve                    启动 Dashboard 服务器
    jarvis task <prompt>            提交任务
    jarvis status                   查看系统状态
    jarvis ministers                列出所有大臣
    jarvis evolve                   手动触发进化
    jarvis alerts                   查看活跃告警
    jarvis --version                显示版本号
"""

from __future__ import annotations

import argparse
import sys
import textwrap

VERSION = "0.2.0"

# ANSI colors — only enabled when stdout is a TTY
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_BLUE = "\033[94m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _c(text: str, code: str) -> str:
    """Wrap text in ANSI code if stdout is a TTY."""
    if sys.stdout.isatty():
        return f"{code}{text}{_RESET}"
    return text


def cmd_serve(args: argparse.Namespace) -> None:
    """启动 Dashboard 服务器。"""
    from jarvis.emperor import Emperor, EmperorConfig

    cfg = EmperorConfig()
    if args.port:
        cfg.api_port = args.port
    if args.host:
        cfg.api_host = args.host

    emperor = Emperor(config=cfg)
    emperor.serve(host=args.host or "127.0.0.1", port=args.port or 9020)


def cmd_task(args: argparse.Namespace) -> None:
    """提交任务。"""
    from jarvis.emperor import Emperor

    emperor = Emperor()
    report = emperor.execute_task(args.prompt, domain=args.domain)

    success = report.get("success", False)
    status_label = _c("成功", _GREEN) if success else _c("失败", _RED)

    print()
    print(f"  任务ID: {report.get('task_id', 'N/A')}")
    print(f"  大臣:   {report.get('minister', 'N/A')}")
    print(f"  状态:   {status_label}")
    print(f"  置信度: {report.get('confidence', 0):.2f}")
    print(f"  耗时:   {report.get('execution_time_ms', 0):.0f}ms")
    print(f"  {'=' * 50}")
    response = report.get("response", "")
    if response:
        print(response)
    else:
        err = report.get("error", "")
        if err:
            print(f"  错误: {err}")
    print(f"  {'=' * 50}")


def cmd_status(args: argparse.Namespace) -> None:
    """查看系统状态。"""
    from jarvis.emperor import Emperor

    emperor = Emperor()
    court = emperor.court
    snap = court.inspect.snapshot()
    ranking = court.merit_ranking

    print()
    print(f"  {_c('Emperor Core', _BOLD)} v{VERSION}")
    print(f"  大臣总数:   {snap.total_ministers}")
    print(f"  活跃大臣:   {snap.active_count}")
    print(f"  进化代数:   {court.cycle}")

    if ranking:
        top = ranking[0]
        avg_merit = sum(r.merit_score for r in ranking) / len(ranking)
        print(f"  平均功绩:   {avg_merit:.1f}")
        print(f"  成功率:     {court.success_rate:.1%}")
        print(f"  榜首:       {top.minister} (merit={top.merit_score:.1f})")

    sched = getattr(emperor, "_scheduler", None)
    if sched is not None and hasattr(sched, "state"):
        from jarvis.court.scheduler import SchedulerState
        state = sched.state
        paused = state == SchedulerState.PAUSED
        running = state == SchedulerState.RUNNING
        state_str = (
            _c("运行中", _GREEN) if running
            else _c("已暂停", _YELLOW) if paused
            else state.name
        )
        print(f"  调度状态:   {state_str}")

    domains: set[str] = set()
    for m in snap.ministers:
        domains.add(m.domain)
    print(f"  活跃领域:   {len(domains)} ({', '.join(sorted(domains))})")
    print()


def cmd_ministers(args: argparse.Namespace) -> None:
    """列出所有大臣。"""
    from jarvis.emperor import Emperor

    emperor = Emperor()
    court = emperor.court
    snap = court.inspect.snapshot()

    if not snap.ministers:
        print("\n  暂无大臣\n")
        return

    genomes = court._sm._genomes
    ranking_map = {r.minister: r for r in court.merit_ranking}

    merged = []
    for m in snap.ministers:
        genome = genomes.get(m.name)
        merit_report = ranking_map.get(m.name)
        merit = float(merit_report.merit_score) if merit_report else float(m.merit)
        streak = getattr(genome, "success_streak", 0) if genome else 0
        fail_streak = getattr(genome, "failure_streak", 0) if genome else 0
        total_tasks = getattr(genome, "total_tasks", 0) if genome else 0
        capability_hits = getattr(genome, "capability_hits", 0) if genome else 0

        if streak >= 3:
            status = f"{_c(f'{streak}连胜', _GREEN)}"
        elif fail_streak >= 3:
            status = f"{_c(f'{fail_streak}连败', _RED)}"
        else:
            status = "--"

        merged.append({
            "name": m.name,
            "domain": m.domain,
            "merit": merit,
            "status": status,
            "streak": streak,
            "fail_streak": fail_streak,
            "total_tasks": total_tasks,
            "capability_hits": capability_hits,
        })

    merged.sort(key=lambda x: x["merit"], reverse=True)

    print()
    header = f"  {'排名':<4} {'名称':<16} {'领域':<12} {'功绩':<16} {'任务':<8} {'状态'}"
    print(header)
    print(f"  {'-' * 4} {'-' * 16} {'-' * 12} {'-' * 16} {'-' * 8} {'-' * 12}")

    for i, m in enumerate(merged, 1):
        bar_len = min(int(m["merit"] / 5), 20)
        bar = _c("█" * bar_len + "░" * (20 - bar_len), _BLUE)
        merit_str = f"{bar} {m['merit']:.0f}"

        tasks_str = f"{m['total_tasks']}"
        if m["total_tasks"] > 0:
            hit_rate = m["capability_hits"] * 100 // m["total_tasks"]
            tasks_str += f"({hit_rate}%)"

        print(f"  {i:<4} {m['name']:<16} {m['domain']:<12} {merit_str:<28} {tasks_str:<8} {m['status']}")
    print()


def cmd_evolve(args: argparse.Namespace) -> None:
    """手动触发进化。"""
    from jarvis.emperor import Emperor

    emperor = Emperor()
    court = emperor.court

    if not court.active_ministers:
        print(f"\n  {_c('无活跃大臣，请先注册大臣', _YELLOW)}\n")
        return

    print(f"\n  {_c('正在执行进化...', _BOLD)}")
    try:
        result = court.evolve(args.cycles)
        if isinstance(result, dict):
            active = result.get("active_count", "?")
            eliminated = result.get("eliminated_count", "?")
            spawned = result.get("new_spawns", "?")
            print(f"  {_c('进化完成', _GREEN)}: active={active}, eliminated={eliminated}, spawned={spawned}")
        else:
            print(f"  {_c('进化完成', _GREEN)}")
    except Exception as e:
        print(f"  {_c(f'进化失败: {e}', _RED)}")
    print()


def cmd_alerts(args: argparse.Namespace) -> None:
    """查看活跃告警。"""
    from jarvis.emperor import Emperor

    emperor = Emperor()
    alert_manager = emperor.alerts

    if alert_manager is None:
        print("\n  告警管理器未初始化\n")
        return

    history = alert_manager.history(limit=20)
    if not history:
        print(f"\n  {_c('无活跃告警', _GREEN)}\n")
        return

    level_map = {
        "critical": _c("CRIT", _RED),
        "warning": _c("WARN", _YELLOW),
        "info": _c("INFO", _BLUE),
    }

    print(f"\n  {'级别':<10} {'规则':<30} {'消息'}")
    print(f"  {'-' * 10} {'-' * 30} {'-' * 40}")
    for a in history:
        level_str = level_map.get(a.severity, a.severity.upper())
        rule = a.rule_name[:30]
        msg = (a.message or "")[:60]
        print(f"  {level_str:<16} {rule:<30} {msg}")
    print()


# ══════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Emperor Core — 多领域 AI Agent 管理系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              jarvis serve                       启动 Dashboard
              jarvis serve --port 8080           指定端口
              jarvis task "计算 2+3"             提交任务
              jarvis task --domain math "计算 pi" 指定领域
              jarvis status                      查看状态
              jarvis ministers                   大臣列表
              jarvis evolve                      手动进化
              jarvis alerts                      告警列表
        """),
    )

    parser.add_argument(
        "--version", action="version", version=f"jarvis {VERSION}"
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # ── serve ──
    serve_parser = subparsers.add_parser("serve", help="启动 Dashboard 服务器")
    serve_parser.add_argument(
        "--host", default="127.0.0.1", help="监听地址 (默认: 127.0.0.1)"
    )
    serve_parser.add_argument(
        "--port", type=int, default=0, help="监听端口 (默认: 9020)"
    )
    serve_parser.set_defaults(func=cmd_serve)

    # ── task ──
    task_parser = subparsers.add_parser("task", help="提交任务")
    task_parser.add_argument("prompt", help="任务描述")
    task_parser.add_argument(
        "--domain", "-d", default="general", help="任务领域 (默认: general)"
    )
    task_parser.set_defaults(func=cmd_task)

    # ── status ──
    status_parser = subparsers.add_parser("status", help="系统状态")
    status_parser.set_defaults(func=cmd_status)

    # ── ministers ──
    ministers_parser = subparsers.add_parser("ministers", help="大臣列表")
    ministers_parser.set_defaults(func=cmd_ministers)

    # ── evolve ──
    evolve_parser = subparsers.add_parser("evolve", help="手动进化")
    evolve_parser.add_argument(
        "--cycles", "-c", type=int, default=1, help="进化轮数 (默认: 1)"
    )
    evolve_parser.set_defaults(func=cmd_evolve)

    # ── alerts ──
    alerts_parser = subparsers.add_parser("alerts", help="告警列表")
    alerts_parser.set_defaults(func=cmd_alerts)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
