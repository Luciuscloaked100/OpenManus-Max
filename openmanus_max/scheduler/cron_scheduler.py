"""
OpenManus-Max Cron Scheduler
基于 APScheduler 的定时任务调度系统
支持 Cron 表达式和间隔调度
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

from pydantic import BaseModel, Field

from openmanus_max.core.logger import logger


class ScheduledTask(BaseModel):
    """定时任务模型"""
    id: str
    name: str
    prompt: str
    schedule_type: str  # "cron" or "interval"
    schedule_expr: str  # cron expression or interval seconds
    repeat: bool = True
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0


class CronScheduler:
    """定时任务调度器

    功能：
    - 支持 Cron 表达式调度
    - 支持固定间隔调度
    - 任务持久化到 SQLite
    - 支持任务的增删改查
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.expanduser("~/.openmanus-max/scheduler.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running = False
        self._executor: Optional[Callable] = None
        self._background_task: Optional[asyncio.Task] = None
        self._load_tasks()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                schedule_type TEXT NOT NULL,
                schedule_expr TEXT NOT NULL,
                repeat INTEGER DEFAULT 1,
                enabled INTEGER DEFAULT 1,
                created_at TEXT,
                last_run TEXT,
                run_count INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def _load_tasks(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT * FROM tasks WHERE enabled = 1")
        for row in cursor.fetchall():
            task = ScheduledTask(
                id=row[0], name=row[1], prompt=row[2],
                schedule_type=row[3], schedule_expr=row[4],
                repeat=bool(row[5]), enabled=bool(row[6]),
                created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
                last_run=datetime.fromisoformat(row[8]) if row[8] else None,
                run_count=row[9] or 0,
            )
            self._tasks[task.id] = task
        conn.close()
        logger.info(f"Loaded {len(self._tasks)} scheduled tasks")

    def add_task(self, task: ScheduledTask) -> ScheduledTask:
        """添加定时任务"""
        self._tasks[task.id] = task
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)",
            (task.id, task.name, task.prompt, task.schedule_type,
             task.schedule_expr, int(task.repeat), int(task.enabled),
             task.created_at.isoformat(), None, 0),
        )
        conn.commit()
        conn.close()
        logger.info(f"Added task: {task.name} ({task.schedule_type}: {task.schedule_expr})")
        return task

    def remove_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            conn.close()
            return True
        return False

    def list_tasks(self) -> List[ScheduledTask]:
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        return self._tasks.get(task_id)

    async def start(self, executor: Callable[[str], Coroutine[Any, Any, str]]):
        """启动调度器后台循环"""
        self._executor = executor
        self._running = True
        self._background_task = asyncio.create_task(self._run_loop())
        logger.info("Scheduler started")

    async def stop(self):
        """停止调度器"""
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _run_loop(self):
        """后台调度循环"""
        while self._running:
            now = datetime.now()
            for task in list(self._tasks.values()):
                if not task.enabled:
                    continue
                if self._should_run(task, now):
                    asyncio.create_task(self._execute_task(task))
            await asyncio.sleep(30)  # 每 30 秒检查一次

    def _should_run(self, task: ScheduledTask, now: datetime) -> bool:
        """判断任务是否应该执行"""
        if task.schedule_type == "interval":
            interval_seconds = int(task.schedule_expr)
            if task.last_run is None:
                return True
            elapsed = (now - task.last_run).total_seconds()
            return elapsed >= interval_seconds

        elif task.schedule_type == "cron":
            # 简化的 cron 匹配：分钟级精度
            try:
                parts = task.schedule_expr.split()
                if len(parts) < 5:
                    return False
                # sec min hour dom month dow
                if len(parts) == 6:
                    _, minute, hour, dom, month, dow = parts
                else:
                    minute, hour, dom, month, dow = parts

                if not self._cron_match(minute, now.minute):
                    return False
                if not self._cron_match(hour, now.hour):
                    return False
                if not self._cron_match(dom, now.day):
                    return False
                if not self._cron_match(month, now.month):
                    return False
                if not self._cron_match(dow, now.weekday()):
                    return False

                # 避免同一分钟内重复执行
                if task.last_run and (now - task.last_run).total_seconds() < 60:
                    return False
                return True
            except Exception:
                return False
        return False

    @staticmethod
    def _cron_match(expr: str, value: int) -> bool:
        """简化的 cron 字段匹配"""
        if expr == "*":
            return True
        if expr.startswith("*/"):
            step = int(expr[2:])
            return value % step == 0
        if "," in expr:
            return value in [int(x) for x in expr.split(",")]
        if "-" in expr:
            low, high = expr.split("-")
            return int(low) <= value <= int(high)
        return value == int(expr)

    async def _execute_task(self, task: ScheduledTask):
        """执行定时任务"""
        logger.info(f"Executing scheduled task: {task.name}")
        task.last_run = datetime.now()
        task.run_count += 1

        try:
            if self._executor:
                result = await self._executor(task.prompt)
                logger.info(f"Task {task.name} completed: {str(result)[:100]}")
        except Exception as e:
            logger.error(f"Task {task.name} failed: {e}")

        if not task.repeat:
            task.enabled = False

        # 更新数据库
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE tasks SET last_run=?, run_count=?, enabled=? WHERE id=?",
            (task.last_run.isoformat(), task.run_count, int(task.enabled), task.id),
        )
        conn.commit()
        conn.close()
