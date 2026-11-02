"""Read-only local environment self-check route (qc doctor over the local API).

The server is a research/simulation workbench: this route only inspects local files,
dependencies and the C++ engine. It never touches the network or mutates state.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from ..doctor import run_doctor
from .schemas import DoctorView
from .workspace import Workspace


def register_doctor_routes(app: FastAPI, ctx: Workspace) -> None:
    @app.get("/api/doctor", response_model=DoctorView)
    def doctor(include_optional: bool = True) -> DoctorView:
        # The API server is already listening, so probing its own port would always
        # report a false "busy" warning; the HTTP view skips the CLI port check.
        report = run_doctor(
            Path.cwd(),
            check_port=None,
            include_optional=include_optional,
            data_root=ctx.settings.data_root,
            snapshots_root=ctx.settings.snapshots_root,
        )
        return DoctorView.model_validate(report.to_dict())
