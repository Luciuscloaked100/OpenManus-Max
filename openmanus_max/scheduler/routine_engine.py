"""
OpenManus-Max Routine Engine
后台守护进程引擎 —— 支持 Cron 调度、事件触发、Heartbeat 心跳

参考 IronClaw 的 Routine 系统设计:
  - Cron Routines:  基于 cron 表达式定时执行
  - Event Routines: 基于文件变更、webhook 等事件触发
  - Heartbeat:      周期性检查清单，有事才通知

Routine 定义格式 (YAML):
  name: daily-report
  trigger:
    type: cron
    expression: "0 0 9 * * *"
  action:
    prompt: "Generate a daily summary report..."
  notify:
    channel: cli
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# 1. 数据模型
# ============================================================

class TriggerType(str, Enum):
    CRON = "cron"
    INTERVAL = "interval"
    FILE_WATCH = "file_watch"
    EVENT = "event"
    HEARTBEAT = "heartbeat"


class RoutineStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    RUNNING = "running"
    ERROR = "error"


class RoutineTrigger(BaseModel):
    """触发器配置"""
    type: TriggerType
    expression: str = ""         # cron 表达式 或 interval 秒数
    watch_paths: List[str] = Field(default_factory=list)  # file_watch 路径
    event_name: str = ""         # event 名称
    interval_seconds: int = 1800  # heartbeat / interval 默认 30 分钟


class RoutineAction(BaseModel):
    """执行动作"""
    prompt: str                  # 发送给 Agent 的 prompt
    max_steps: int = 10          # 最大执行步数
    timeout: int = 300           # 超时秒数


class RoutineNotify(BaseModel):
    """通知配置"""
    channel: str = "cli"         # cli / webhook / file
    webhook_url: str = ""
    file_path: str = ""


class Routine(BaseModel):
    """完整的 Routine 定义"""
    id: str = ""
    name: str
    description: str = ""
    trigger: RoutineTrigger
    action: RoutineAction
    notify: RoutineNotify = Field(default_factory=RoutineNotify)
    status: RoutineStatus = RoutineStatus.ACTIVE
    created_at: str = ""
    last_run: str = ""
    run_count: int = 0
    last_error: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


# ============================================================
# 2. Routine 持久化存储
# ============================================================

class RoutineStore:
    """SQLite 持久化存储"""

    def __init__(self, db_path: str = "~/.openmanus-max/routines.db"):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS routines (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    data TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_at TEXT,
                    last_run TEXT,
                    run_count INTEGER DEFAULT 0,
                    last_error TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS routine_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    routine_id TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    success INTEGER,
                    output TEXT,
                    error TEXT
                )
            """)

    def save(self, routine: Routine):
        data = routine.model_dump_json()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO routines
                   (id, name, data, status, created_at, last_run, run_count, last_error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (routine.id, routine.name, data, routine.status.value,
                 routine.created_at, routine.last_run, routine.run_count, routine.last_error),
            )

    def load_all(self) -> List[Routine]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT data FROM routines").fetchall()
        return [Routine.model_validate_json(row[0]) for row in rows]

    def delete(self, routine_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM routines WHERE id = ?", (routine_id,))
            return cursor.rowcount > 0

    def log_run(self, routine_id: str, success: bool, output: str = "", error: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO routine_runs (routine_id, started_at, finished_at, success, output, error)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (routine_id, datetime.now().isoformat(), datetime.now().isoformat(),
                 1 if success else 0, output[:4096], error[:2048]),
            )

    def get_history(self, routine_id: str, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT started_at, finished_at, success, output, error
                   FROM routine_runs WHERE routine_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (routine_id, limit),
            ).fetchall()
        return [
            {"started_at": r[0], "finished_at": r[1], "success": bool(r[2]),
             "output": r[3], "error": r[4]}
            for r in rows
        ]


# ============================================================
# 3. Cron 解析器（简化版 6 字段）
# ============================================================

def cron_matches(expression: str, dt: Optional[datetime] = None) -> bool:
    """
    检查 cron 表达式是否匹配给定时间。
    格式: 秒 分 时 日 月 星期 (6字段)
    支持: *, */N, N, N-M, N,M
    """
    dt = dt or datetime.now()
    parts = expression.strip().split()
    if len(parts) != 6:
        return False

    fields = [dt.second, dt.minute, dt.hour, dt.day, dt.month, dt.weekday()]
    # weekday: Python 0=Monday, cron 0=Sunday → 转换
    fields[5] = (fields[5] + 1) % 7

    for i, (part, value) in enumerate(zip(parts, fields)):
        if not _cron_field_matches(part, value, _cron_max(i)):
            return False
    return True


def _cron_max(field_idx: int) -> int:
    return [59, 59, 23, 31, 12, 6][field_idx]


def _cron_field_matches(field: str, value: int, max_val: int) -> bool:
    for item in field.split(","):
        item = item.strip()
        if item == "*":
            return True
        if "/" in item:
            base, step_str = item.split("/", 1)
            step = int(step_str)
            if base == "*":
                if value % step == 0:
                    return True
            else:
                start = int(base)
                if value >= start and (value - start) % step == 0:
                    return True
        elif "-" in item:
            lo, hi = item.split("-", 1)
            if int(lo) <= value <= int(hi):
                return True
        else:
            if int(item) == value:
                return True
    return False


# ============================================================
# 4. Routine Engine
# ============================================================

# Agent 执行器类型: 接收 prompt, 返回结果字符串
AgentExecutor = Callable[[str, int], Coroutine[Any, Any, str]]


class RoutineEngine:
    """
    Routine 守护进程引擎

    启动后在后台持续运行:
    - 每秒检查 cron/interval 触发器
    - 监听文件变更事件
    - 执行 heartbeat 检查
    """

    def __init__(
        self,
        store: Optional[RoutineStore] = None,
        executor: Optional[AgentExecutor] = None,
        poll_interval: float = 1.0,
    ):
        self.store = store or RoutineStore()
        self.executor = executor
        self.poll_interval = poll_interval
        self._routines: Dict[str, Routine] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_check: Dict[str, float] = {}
        self._file_mtimes: Dict[str, float] = {}

    def load_routines(self):
        """从存储加载所有 routine"""
        for r in self.store.load_all():
            self._routines[r.id] = r

    def add_routine(self, routine: Routine) -> Routine:
        """添加新 routine"""
        self._routines[routine.id] = routine
        self.store.save(routine)
        return routine

    def remove_routine(self, routine_id: str) -> bool:
        """移除 routine"""
        self._routines.pop(routine_id, None)
        return self.store.delete(routine_id)

    def list_routines(self) -> List[Routine]:
        return list(self._routines.values())

    def get_routine(self, routine_id: str) -> Optional[Routine]:
        return self._routines.get(routine_id)

    def pause_routine(self, routine_id: str) -> bool:
        r = self._routines.get(routine_id)
        if r:
            r.status = RoutineStatus.PAUSED
            self.store.save(r)
            return True
        return False

    def resume_routine(self, routine_id: str) -> bool:
        r = self._routines.get(routine_id)
        if r:
            r.status = RoutineStatus.ACTIVE
            self.store.save(r)
            return True
        return False

    async def start(self, executor: Optional[AgentExecutor] = None):
        """启动守护进程循环"""
        if executor:
            self.executor = executor
        self.load_routines()
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """停止守护进程"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self):
        """主循环"""
        while self._running:
            now = datetime.now()
            for routine in list(self._routines.values()):
                if routine.status != RoutineStatus.ACTIVE:
                    continue
                if self._should_trigger(routine, now):
                    asyncio.create_task(self._execute_routine(routine))
            await asyncio.sleep(self.poll_interval)

    def _should_trigger(self, routine: Routine, now: datetime) -> bool:
        """检查 routine 是否应该触发"""
        trigger = routine.trigger
        last = self._last_check.get(routine.id, 0)

        if trigger.type == TriggerType.CRON:
            if time.time() - last < 60:  # cron 最小粒度 1 分钟
                return False
            if cron_matches(trigger.expression, now):
                self._last_check[routine.id] = time.time()
                return True

        elif trigger.type == TriggerType.INTERVAL:
            interval = trigger.interval_seconds
            if time.time() - last >= interval:
                self._last_check[routine.id] = time.time()
                return True

        elif trigger.type == TriggerType.HEARTBEAT:
            interval = trigger.interval_seconds
            if time.time() - last >= interval:
                self._last_check[routine.id] = time.time()
                return True

        elif trigger.type == TriggerType.FILE_WATCH:
            for path in trigger.watch_paths:
                path = os.path.expanduser(path)
                if os.path.exists(path):
                    mtime = os.path.getmtime(path)
                    key = f"{routine.id}:{path}"
                    if key not in self._file_mtimes:
                        self._file_mtimes[key] = mtime
                    elif mtime > self._file_mtimes[key]:
                        self._file_mtimes[key] = mtime
                        self._last_check[routine.id] = time.time()
                        return True

        return False

    async def _execute_routine(self, routine: Routine):
        """执行单个 routine"""
        if not self.executor:
            return

        routine.status = RoutineStatus.RUNNING
        self.store.save(routine)

        try:
            result = await asyncio.wait_for(
                self.executor(routine.action.prompt, routine.action.max_steps),
                timeout=routine.action.timeout,
            )

            # Heartbeat 特殊处理: 如果回复 HEARTBEAT_OK 则不通知
            if routine.trigger.type == TriggerType.HEARTBEAT:
                if "HEARTBEAT_OK" in (result or ""):
                    routine.status = RoutineStatus.ACTIVE
                    routine.last_run = datetime.now().isoformat()
                    routine.run_count += 1
                    self.store.save(routine)
                    self.store.log_run(routine.id, True, "HEARTBEAT_OK")
                    return

            # 通知
            await self._notify(routine, result or "")

            routine.status = RoutineStatus.ACTIVE
            routine.last_run = datetime.now().isoformat()
            routine.run_count += 1
            routine.last_error = ""
            self.store.save(routine)
            self.store.log_run(routine.id, True, (result or "")[:4096])

        except asyncio.TimeoutError:
            routine.status = RoutineStatus.ERROR
            routine.last_error = f"Timeout after {routine.action.timeout}s"
            self.store.save(routine)
            self.store.log_run(routine.id, False, error=routine.last_error)
        except Exception as e:
            routine.status = RoutineStatus.ERROR
            routine.last_error = str(e)
            self.store.save(routine)
            self.store.log_run(routine.id, False, error=str(e))

    async def _notify(self, routine: Routine, message: str):
        """发送通知"""
        notify = routine.notify
        if notify.channel == "cli":
            print(f"\n[Routine: {routine.name}] {message[:500]}")
        elif notify.channel == "file" and notify.file_path:
            path = os.path.expanduser(notify.file_path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] {routine.name}: {message}\n")
        elif notify.channel == "webhook" and notify.webhook_url:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        notify.webhook_url,
                        json={"routine": routine.name, "message": message[:4096]},
                        timeout=aiohttp.ClientTimeout(total=10),
                    )
            except Exception:
                pass

    # ============================================================
    # 事件触发接口
    # ============================================================

    async def emit_event(self, event_name: str, data: Optional[Dict] = None):
        """触发一个命名事件，匹配的 event routine 会被执行"""
        for routine in self._routines.values():
            if (routine.status == RoutineStatus.ACTIVE
                    and routine.trigger.type == TriggerType.EVENT
                    and routine.trigger.event_name == event_name):
                asyncio.create_task(self._execute_routine(routine))
