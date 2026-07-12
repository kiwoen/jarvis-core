"""
JARVIS Orchestrator — the master controller.

This is the brain of JARVIS. It receives natural language intents,
routes them to the correct domain module(s), orchestrates multi-domain
workflows, and manages the self-evolution loop.

Unlike traditional "tool" frameworks, this orchestrator treats every
domain as a first-class citizen — not a plugin, but a limb.

Architecture:
    ┌─────────────────────────────────────────┐
    │            ORCHESTRATOR                  │
    │  ┌───────┐  ┌───────┐  ┌──────────┐    │
    │  │Intent │  │Domain │  │Evolution  │    │
    │  │Parser │→│Router │→│Controller │    │
    │  └───────┘  └───────┘  └─────┬────┘    │
    │                              │          │
    │  ┌───────┐  ┌───────┐       │          │
    │  │Memory │  │Sandbox│       │          │
    │  │Engine │  │Engine │       │          │
    │  └───────┘  └───────┘       ▼          │
    │                        Capability Tree  │
    └─────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger("jarvis.orchestrator")


class Domain(Enum):
    """All domains JARVIS operates in."""

    PERSONAL = auto()
    RESEARCH = auto()
    ENGINEERING = auto()
    CREATOR = auto()
    SECURITY = auto()
    HEALTH = auto()
    FINANCE = auto()
    HOME = auto()
    CORE = auto()  # meta-domain for system operations


@dataclass
class Intent:
    """Parsed user intent with context."""

    raw_text: str
    primary_domain: Domain
    secondary_domains: list[Domain] = field(default_factory=list)
    action: str = ""
    entities: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    context_ids: list[str] = field(default_factory=list)


@dataclass
class TaskResult:
    """Standardized result from any domain module."""

    domain: Domain
    success: bool
    output: Any = None
    error: Optional[str] = None
    artifacts: list[Path] = field(default_factory=list)
    memory_keys: list[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    tokens_consumed: int = 0


class DomainRegistry:
    """Registry of all loaded domain modules.

    Domains are hot-pluggable — they can be loaded/unloaded
    at runtime without restarting JARVIS.
    """

    def __init__(self) -> None:
        self._modules: dict[Domain, Any] = {}
        self._capabilities: dict[Domain, list[str]] = {}

    def register(self, domain: Domain, module: Any) -> None:
        self._modules[domain] = module
        if hasattr(module, "CAPABILITIES"):
            self._capabilities[domain] = module.CAPABILITIES
        logger.info("Domain registered: %s", domain.name)

    def get(self, domain: Domain) -> Any | None:
        return self._modules.get(domain)

    def list_domains(self) -> list[Domain]:
        return list(self._modules.keys())

    def list_capabilities(self) -> dict[Domain, list[str]]:
        return dict(self._capabilities)


class IntentParser:
    """Parses natural language into structured Intent objects.

    Uses a cascade strategy:
    1. Keyword matching for fast routing
    2. Semantic embedding for ambiguous intents
    3. Context-aware disambiguation via conversation memory
    """

    DOMAIN_KEYWORDS: dict[Domain, list[str]] = {
        Domain.PERSONAL: [
            "remind", "schedule", "calendar", "email", "message", "call",
            "contact", "todo", "task", "meeting", "appointment", "note",
            "日记", "提醒", "日程", "邮件", "消息", "联系人", "待办", "会议",
        ],
        Domain.RESEARCH: [
            "research", "search", "analyze", "compare", "paper", "study",
            "文献", "论文", "研究", "调查", "分析", "对比", "搜索", "查找",
        ],
        Domain.ENGINEERING: [
            "code", "build", "deploy", "debug", "refactor", "test", "api",
            "database", "docker", "kubernetes", "git", "compile",
            "编程", "构建", "部署", "调试", "重构", "测试", "接口",
        ],
        Domain.CREATOR: [
            "write", "design", "draw", "compose", "video", "music", "image",
            "photo", "edit", "render", "animate", "story", "novel", "fiction",
            "写作", "设计", "绘画", "作曲", "视频", "音乐", "图片", "渲染",
            "写", "小说", "故事", "创作", "写一", "写个", "画", "画一",
        ],
        Domain.SECURITY: [
            "monitor", "scan", "alert", "threat", "firewall", "encrypt",
            "auth", "audit", "log", "intrusion",
            "监控", "扫描", "警告", "威胁", "防火墙", "加密", "审计",
        ],
        Domain.HEALTH: [
            "health", "fitness", "sleep", "diet", "exercise", "meditation",
            "heart rate", "calorie", "workout", "weight",
            "健康", "健身", "睡眠", "饮食", "运动", "冥想", "心率", "卡路里",
        ],
        Domain.FINANCE: [
            "budget", "invest", "stock", "crypto", "tax", "expense", "income",
            "trade", "portfolio", "market", "bank", "fund", "asset",
            "预算", "投资", "股票", "加密货币", "税务", "支出", "收入", "交易",
            "投资组合", "理财", "基金", "资产", "收益率", "持仓", "盈亏",
        ],
        Domain.HOME: [
            "light", "temperature", "lock", "camera", "thermostat", "door",
            "window", "curtain", "ac", "tv", "speaker",
            "灯光", "温度", "门锁", "摄像头", "恒温器", "窗帘", "空调", "电视",
        ],
    }

    def parse(self, text: str, context: list[str] | None = None) -> Intent:
        text_lower = text.lower()
        scores: dict[Domain, int] = {}

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            # Boost score if context mentions this domain
            if context:
                ctx_text = " ".join(context).lower()
                score += sum(1 for kw in keywords if kw in ctx_text) * 2
            if score > 0:
                scores[domain] = score

        if not scores:
            # Default to PERSONAL for ambiguous intents
            primary = Domain.PERSONAL
            secondary = []
        else:
            sorted_domains = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            primary = sorted_domains[0][0]
            secondary = [d for d, s in sorted_domains[1:3] if s > 1]

        return Intent(
            raw_text=text,
            primary_domain=primary,
            secondary_domains=secondary,
            action=self._extract_action(text),
            entities=self._extract_entities(text),
        )

    def _extract_action(self, text: str) -> str:
        actions = [
            "create", "delete", "update", "search", "analyze",
            "compare", "summarize", "translate", "convert", "generate",
            "monitor", "optimize", "deploy", "build", "install",
            "创建", "删除", "更新", "搜索", "分析", "对比", "总结", "翻译",
            "转换", "生成", "监控", "优化", "部署", "构建", "安装",
        ]
        for action in actions:
            if action in text.lower():
                return action
        return "query"

    def _extract_entities(self, text: str) -> dict[str, Any]:
        # Simplified entity extraction — production would use NER models
        entities: dict[str, Any] = {}
        words = text.split()
        for i, word in enumerate(words):
            if word.startswith("@") or word.startswith("#"):
                entities["tag"] = word[1:]
            if ":" in word and not word.startswith("http"):
                key, _, val = word.partition(":")
                entities[key] = val
        return entities


class Orchestrator:
    """The master controller of JARVIS.

    Responsibilities:
    1. Parse user intents
    2. Route to appropriate domain modules
    3. Coordinate multi-domain workflows
    4. Feed results into the evolution engine
    5. Maintain conversation memory and context
    """

    def __init__(
        self,
        memory_engine: Any = None,
        evolution_controller: Any = None,
        sandbox_manager: Any = None,
    ) -> None:
        self.registry = DomainRegistry()
        self.intent_parser = IntentParser()
        self.memory = memory_engine
        self.evolution = evolution_controller
        self.sandbox = sandbox_manager
        self.context: list[str] = []

    async def execute(self, user_input: str) -> TaskResult:
        """Main entry point — parse, route, execute, learn."""

        # Step 1: Parse intent
        intent = self.intent_parser.parse(user_input, self.context)
        logger.info("Parsed intent: domain=%s, action=%s", intent.primary_domain.name, intent.action)

        # Step 2: Route to domain module
        module = self.registry.get(intent.primary_domain)
        if not module:
            return TaskResult(
                domain=intent.primary_domain,
                success=False,
                error=f"Domain {intent.primary_domain.name} not loaded",
            )

        # Step 3: Execute
        start_time = asyncio.get_event_loop().time()
        try:
            if hasattr(module, "handle"):
                result = await module.handle(intent)
            else:
                result = await self._default_handle(module, intent)
        except Exception as e:
            logger.exception("Execution failed in domain %s", intent.primary_domain.name)
            result = TaskResult(
                domain=intent.primary_domain,
                success=False,
                error=str(e),
            )

        result.execution_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000

        # Step 4: Store in memory
        if self.memory:
            await self.memory.store(
                key=f"task_{id(result)}",
                value={
                    "intent": intent.raw_text,
                    "domain": intent.primary_domain.name,
                    "success": result.success,
                    "output": str(result.output)[:2000],
                },
            )

        # Step 5: Feed to evolution engine
        if self.evolution and result.success:
            await self.evolution.record_success(intent, result)

        # Step 6: Update context
        self.context.append(user_input)
        if len(self.context) > 50:
            self.context = self.context[-50:]

        return result

    async def _default_handle(self, module: Any, intent: Intent) -> TaskResult:
        """Fallback handler when domain lacks a handle() method."""
        return TaskResult(
            domain=intent.primary_domain,
            success=False,
            error=f"Domain {intent.primary_domain.name} has no handler",
        )

    def load_all_domains(self) -> None:
        """Auto-discover and load all domain modules."""
        domain_module_names = [
            "jarvis.domains.personal",
            "jarvis.domains.research",
            "jarvis.domains.engineering",
            "jarvis.domains.creator",
            "jarvis.domains.security",
            "jarvis.domains.health",
            "jarvis.domains.finance",
            "jarvis.domains.home",
        ]
        for name in domain_module_names:
            try:
                mod = importlib.import_module(name)
                if hasattr(mod, "DomainModule"):
                    module_instance = mod.DomainModule(self)
                    domain_field = getattr(mod, "DOMAIN", None) or Domain.CORE
                    self.registry.register(domain_field, module_instance)
            except ImportError:
                logger.warning("Domain %s not available — skipping", name)
