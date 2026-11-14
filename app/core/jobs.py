"""Bounded local jobs; durable stage artifacts survive reloads and later failures."""

import asyncio
import logging
import time
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.core.database import analyses, jobs, utc_now
from app.core.ingestion import canonical_id


class JobRunner:
    def __init__(self, database, handlers):
        self.database, self.handlers = database, handlers
        self.tasks = {}
        self.slots = asyncio.Semaphore(2)
        with database.begin() as connection:
            connection.execute(
                jobs.update()
                .where(jobs.c.status.in_(["queued", "running"]))
                .values(
                    status="interrupted",
                    updated_at=utc_now(),
                    error={"category": "restart", "message": "Server restarted; retry explicitly."},
                )
            )

    def get(self, job_id):
        with self.database.connect() as connection:
            row = connection.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
        if row is None:
            raise HTTPException(404, "Unknown job")
        return dict(row)

    def update(self, job_id, **values):
        with self.database.begin() as connection:
            connection.execute(
                jobs.update().where(jobs.c.id == job_id).values(updated_at=utc_now(), **values)
            )

    def submit(self, kind, target_id, payload, configuration):
        fingerprint = canonical_id(kind, target_id, payload, configuration)
        with self.database.begin() as connection:
            existing = (
                connection.execute(
                    select(jobs).where(
                        jobs.c.fingerprint == fingerprint, jobs.c.status.in_(["queued", "running"])
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                return dict(existing)
            record = {
                "id": str(uuid4()),
                "kind": kind,
                "target_id": target_id,
                "fingerprint": fingerprint,
                "payload": payload,
                "status": "queued",
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "trace": [],
                "result": None,
                "error": None,
            }
            connection.execute(jobs.insert(), record)
        task = asyncio.create_task(self.run(record))
        self.tasks[record["id"]] = task
        task.add_done_callback(lambda _: self.tasks.pop(record["id"], None))
        return record

    async def run(self, job):
        job_id, trace = job["id"], []

        async def stage(name, operation, inputs=None, provider="local"):
            entry = {
                "module": name,
                "status": "running",
                "started_at": utc_now(),
                "inputs": inputs or {},
                "provider": provider,
                "artifact": None,
                "elapsed_seconds": 0,
            }
            trace.append(entry)
            self.update(job_id, trace=trace)
            started = time.monotonic()
            try:
                value = await operation()
                entry.update(status="completed", artifact=jsonable_encoder(value))
                return value
            except BaseException:
                entry["status"] = "interrupted"
                raise
            finally:
                entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
                self.update(job_id, trace=trace)

        try:
            async with self.slots:
                self.update(job_id, status="running")
                async with asyncio.timeout(600):
                    result = await self.handlers[job["kind"]](job, stage)
                analysis_id = str(uuid4())
                with self.database.begin() as connection:
                    connection.execute(
                        analyses.insert().values(
                            id=analysis_id,
                            job_id=job_id,
                            target_id=job["target_id"],
                            kind=job["kind"],
                            created_at=utc_now(),
                            result=result,
                        )
                    )
                    connection.execute(
                        jobs.update()
                        .where(jobs.c.id == job_id)
                        .values(
                            status="completed",
                            result={"analysis_id": analysis_id, **result},
                            updated_at=utc_now(),
                        )
                    )
        except asyncio.CancelledError:
            if self.get(job_id)["status"] != "interrupted":
                self.update(job_id, status="cancelled")
        except Exception as exc:
            logging.getLogger(__name__).exception("Job %s failed", job_id)
            category = (
                "timeout"
                if isinstance(exc, TimeoutError)
                else "provider"
                if isinstance(exc, HTTPException)
                else "internal"
            )
            message = (
                str(exc.detail)
                if isinstance(exc, HTTPException)
                else "Analysis exceeded ten minutes."
                if isinstance(exc, TimeoutError)
                else "Analysis failed; completed stage artifacts are retained. Retry explicitly."
            )
            self.update(job_id, status="failed", error={"category": category, "message": message})

    async def cancel(self, job_id):
        record = self.get(job_id)
        if record["status"] in ("queued", "running"):
            self.update(job_id, status="cancelled")
            task = self.tasks.get(job_id)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        return self.get(job_id)

    async def close(self):
        pending = list(self.tasks.items())
        for job_id, task in pending:
            self.update(
                job_id,
                status="interrupted",
                error={"category": "shutdown", "message": "Server stopped; retry explicitly."},
            )
            task.cancel()
        await asyncio.gather(*(task for _, task in pending), return_exceptions=True)
