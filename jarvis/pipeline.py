"""
服务流水线引擎 — 将能力串联成端到端的自动化服务链
实现"服务规模化"：专家级、个性化、持续、普惠
"""
from __future__ import annotations

import json as _json
import time
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Any, Optional
from enum import Enum


class StageStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class StageResult:
    """流水线阶段结果"""
    stage_name: str
    status: StageStatus
    started_at: float = 0
    finished_at: float = 0
    result: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class PipelineResult:
    """流水线执行结果"""
    pipeline_name: str
    pipeline_id: str
    status: PipelineStatus = PipelineStatus.IDLE
    stages: List[StageResult] = field(default_factory=list)
    started_at: float = 0
    finished_at: float = 0
    final_output: Dict[str, Any] = field(default_factory=dict)


class ServicePipeline:
    """
    服务流水线：将多个能力阶段串联执行

    Stage handler 约定：
      handler(ctx: dict) -> dict
      其中 ctx 是当前流水线上下文（包含所有前置阶段的输出），
      handler 内部负责调用实际的 capability handler（签名 prompt + **kwargs）。

    使用方式：
        pipeline = ServicePipeline("每日简报", [
            Stage("gather", lambda ctx: _news_handler("科技新闻")),
            Stage("analyze", lambda ctx: _handle_text(ctx["gather"]["result"])),
        ])
        result = pipeline.execute()
    """

    def __init__(self, name: str, stages: List['Stage'] = None,
                 auto_retry: bool = True, max_retries: int = 1,
                 on_stage_complete: Callable = None,
                 on_pipeline_complete: Callable = None):
        self.name = name
        self.stages = stages or []
        self.auto_retry = auto_retry
        self.max_retries = max_retries
        self.on_stage_complete = on_stage_complete
        self.on_pipeline_complete = on_pipeline_complete
        self._status = PipelineStatus.IDLE
        self._current_stage_index = 0
        self._lock = threading.Lock()
        self._context: Dict[str, Any] = {}  # 阶段间上下文传递

    @property
    def status(self) -> PipelineStatus:
        return self._status

    @property
    def progress(self) -> Dict[str, Any]:
        """流水线进度"""
        total = len(self.stages)
        completed = sum(
            1 for s in self.stages
            if s._result and s._result.status in (StageStatus.SUCCESS, StageStatus.SKIPPED)
        )
        return {
            "pipeline": self.name,
            "status": self._status.value,
            "total_stages": total,
            "completed_stages": completed,
            "current_stage": (
                self.stages[self._current_stage_index].name
                if self._current_stage_index < total else None
            ),
            "percentage": (completed / total * 100) if total > 0 else 0,
        }

    def add_stage(self, stage: 'Stage') -> 'ServicePipeline':
        self.stages.append(stage)
        return self

    def execute(self, initial_context: Dict[str, Any] = None) -> PipelineResult:
        """执行流水线"""
        import uuid

        pipeline_id = str(uuid.uuid4())[:8]
        result = PipelineResult(
            pipeline_name=self.name,
            pipeline_id=pipeline_id,
            status=PipelineStatus.RUNNING,
            started_at=time.time(),
        )

        self._status = PipelineStatus.RUNNING
        self._context = initial_context or {}

        for i, stage in enumerate(self.stages):
            self._current_stage_index = i

            # 检查条件
            if stage.condition and not stage.condition(self._context):
                stage_result = StageResult(
                    stage_name=stage.name,
                    status=StageStatus.SKIPPED,
                )
                result.stages.append(stage_result)
                continue

            # 执行阶段（含重试）
            stage_result = self._execute_stage(stage)
            result.stages.append(stage_result)

            # 更新上下文
            if stage.output_key and stage_result.status == StageStatus.SUCCESS:
                self._context[stage.output_key] = stage_result.result

            # 回调
            if self.on_stage_complete:
                self.on_stage_complete(stage.name, stage_result)

            # 失败处理
            if stage_result.status == StageStatus.FAILED:
                if stage.fail_strategy == "stop":
                    result.status = PipelineStatus.FAILED
                    break
                elif stage.fail_strategy == "skip":
                    continue

        else:
            result.status = PipelineStatus.COMPLETED

        result.finished_at = time.time()
        result.final_output = self._context
        self._status = result.status

        if self.on_pipeline_complete:
            self.on_pipeline_complete(result)

        return result

    def _execute_stage(self, stage: 'Stage') -> StageResult:
        """执行单个阶段（含重试）"""
        max_attempts = self.max_retries + 1 if self.auto_retry else 1

        for attempt in range(max_attempts):
            stage_result = StageResult(
                stage_name=stage.name,
                status=StageStatus.RUNNING,
                started_at=time.time(),
            )

            try:
                # 准备输入：合并上下文和阶段输入映射
                stage_input = dict(self._context)
                if stage.input_mapping:
                    stage_input.update(stage.input_mapping(self._context))

                # 执行处理函数 — handler 接收 ctx dict，内部自行调用实际能力函数
                output = stage.handler(stage_input)

                stage_result.status = StageStatus.SUCCESS
                stage_result.result = output if isinstance(output, dict) else {"raw": str(output)}
                stage_result.finished_at = time.time()

                stage._result = stage_result
                return stage_result

            except Exception as e:
                if attempt < max_attempts - 1:
                    time.sleep(0.5 * (attempt + 1))  # 指数退避
                    continue

                stage_result.status = StageStatus.FAILED
                stage_result.error = str(e)
                stage_result.finished_at = time.time()
                stage._result = stage_result
                return stage_result

        return stage_result  # unreachable, but keep type checker happy


class Stage:
    """流水线阶段

    handler 约定：`handler(ctx: dict) -> dict`
    其中 ctx 是合并后的上下文字典，handler 内部负责调用实际的能力函数。
    """

    def __init__(self, name: str, handler: Callable[[Dict], Any],
                 input_mapping: Callable[[Dict], Dict] = None,
                 output_key: str = None,
                 condition: Callable[[Dict], bool] = None,
                 fail_strategy: str = "stop"):  # stop | skip | continue
        self.name = name
        self.handler = handler
        self.input_mapping = input_mapping  # 从上下文提取输入
        self.output_key = output_key  # 输出写入上下文的 key
        self.condition = condition  # 前置条件
        self.fail_strategy = fail_strategy
        self._result: Optional[StageResult] = None


class PipelineRegistry:
    """流水线注册中心 — 管理和调度所有服务流水线"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pipelines: Dict[str, ServicePipeline] = {}
            cls._instance._templates: Dict[str, callable] = {}
            cls._instance._history: List[PipelineResult] = []
            cls._instance._lock = threading.Lock()
        return cls._instance

    def register_template(self, name: str, factory: callable):
        """注册流水线模板（工厂函数）"""
        self._templates[name] = factory

    def create_pipeline(self, template_name: str, **kwargs) -> ServicePipeline:
        """从模板创建流水线实例"""
        if template_name not in self._templates:
            raise ValueError(f"Unknown pipeline template: {template_name}")

        pipeline = self._templates[template_name](**kwargs)
        pipeline_id = f"{template_name}_{len(self._history)}"
        self._pipelines[pipeline_id] = pipeline
        return pipeline

    def execute_template(self, template_name: str, context: Dict = None, **kwargs) -> PipelineResult:
        """创建并执行流水线"""
        pipeline = self.create_pipeline(template_name, **kwargs)
        result = pipeline.execute(context)

        with self._lock:
            self._history.append(result)
            # 只保留最近 100 条
            if len(self._history) > 100:
                self._history = self._history[-100:]

        return result

    def get_history(self, limit: int = 20) -> List[Dict]:
        """获取执行历史"""
        return [
            {
                "pipeline_name": r.pipeline_name,
                "pipeline_id": r.pipeline_id,
                "status": r.status.value,
                "stages": [{"name": s.stage_name, "status": s.status.value} for s in r.stages],
                "duration": round(r.finished_at - r.started_at, 2) if r.finished_at else 0,
            }
            for r in self._history[-limit:]
        ]

    def get_active_pipelines(self) -> List[Dict]:
        """获取正在运行的流水线"""
        return [
            p.progress for p in self._pipelines.values()
            if p.status == PipelineStatus.RUNNING
        ]


# 全局单例
pipeline_registry = PipelineRegistry()


# === 预定义流水线模板 ===
# 注意：各 Stage handler 以 ctx dict 为入参，内部自行将 ctx["key"] 中的
# 数据转换为实际 handler 的 (prompt, **kwargs) 调用格式。


def _create_daily_brief_pipeline():
    """每日简报流水线：新闻采集 → 文本统计 → 摘要格式化"""
    from jarvis.capability import _news_handler, _handle_text

    return (ServicePipeline("每日简报", auto_retry=True, max_retries=1)
        .add_stage(Stage(
            name="采集新闻",
            handler=lambda ctx: _news_handler("科技新闻"),
            output_key="news_raw",
        ))
        .add_stage(Stage(
            name="文本统计",
            handler=lambda ctx: {
                "summary": _handle_text(
                    ctx.get("news_raw", {}).get("result", "(无内容)")
                )["result"]
            },
            input_mapping=lambda ctx: {
                "news_text": ctx.get("news_raw", {}).get("result", ""),
            },
            output_key="analysis",
            fail_strategy="skip",
        ))
        .add_stage(Stage(
            name="格式化输出",
            handler=lambda ctx: {
                "report": (
                    "=== 每日简报 ===\n\n"
                    + str(ctx.get("news_raw", {}).get("result", "(无新闻数据)"))
                    + "\n\n--- 文本分析 ---\n"
                    + str(ctx.get("analysis", {}).get("summary", ""))
                )
            },
            output_key="final_report",
            fail_strategy="skip",
        ))
    )


def _create_health_check_pipeline():
    """健康检查流水线：系统健康 → 天气 → 综合摘要"""
    from jarvis.capability import _weather_handler

    return (ServicePipeline("健康检查", auto_retry=False)
        .add_stage(Stage(
            name="系统健康",
            handler=lambda ctx: (
                __import__('jarvis.health', fromlist=['get_system_health'])
                .get_system_health()
            ),
            output_key="system_health",
        ))
        .add_stage(Stage(
            name="天气查询",
            handler=lambda ctx: _weather_handler("北京天气"),
            output_key="weather",
            fail_strategy="skip",
        ))
    )


def _create_search_analyze_pipeline(query: str = ""):
    """搜索分析流水线：搜索 → 抓取 → 文本分析"""
    from jarvis.capability import (
        _web_search_handler, _web_fetch_handler, _handle_text,
    )

    q = query or ""

    return (ServicePipeline(f"搜索分析: {q[:20]}" if q else "搜索分析", auto_retry=True)
        .add_stage(Stage(
            name="搜索",
            handler=lambda ctx: _web_search_handler(
                ctx.get("query", q)
            ),
            input_mapping=lambda ctx: {"query": q},
            output_key="search_results",
        ))
        .add_stage(Stage(
            name="抓取详情",
            handler=lambda ctx: _web_fetch_handler(
                ctx.get("search_results", {}).get("result", "")
            ),
            output_key="fetched_content",
            fail_strategy="skip",
        ))
        .add_stage(Stage(
            name="分析总结",
            handler=lambda ctx: {
                "analysis": _handle_text(
                    ctx.get("fetched_content", {}).get("result", "(无抓取内容)")
                )["result"]
            },
            output_key="analysis",
            fail_strategy="skip",
        ))
    )


# 注册默认模板
pipeline_registry.register_template("daily_brief", _create_daily_brief_pipeline)
pipeline_registry.register_template("health_check", _create_health_check_pipeline)
pipeline_registry.register_template("search_analyze", _create_search_analyze_pipeline)
