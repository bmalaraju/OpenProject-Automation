from __future__ import annotations

"""
Configuration helpers with backward-compatible env handling.

Canonical variable names (preferred):
- Influx: INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET
- OpenProject: OPENPROJECT_BASE_URL, OPENPROJECT_API_TOKEN (or USERNAME/PASSWORD), OAuth via OPENPROJECT_OAUTH_*
- Langfuse: LANGFUSE_ENABLED, LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

Fallbacks: current codebase uses INFLUX_URL/TOKEN/ORG/BUCKET and existing OP env keys; these remain supported.
"""

from dataclasses import dataclass
import os
from typing import Optional


@dataclass
class InfluxConfig:
    url: str
    token: str
    org: str
    bucket: str

    @classmethod
    def load(cls) -> "InfluxConfig":
        url = (
            os.getenv("INFLUXDB_URL")
            or os.getenv("INFLUX_URL")
            or ""
        ).strip()
        token = (
            os.getenv("INFLUXDB_TOKEN")
            or os.getenv("INFLUX_TOKEN")
            or ""
        ).strip()
        org = (
            os.getenv("INFLUXDB_ORG")
            or os.getenv("INFLUX_ORG")
            or ""
        ).strip()
        bucket = (
            os.getenv("INFLUXDB_BUCKET")
            or os.getenv("INFLUX_BUCKET")
            or ""
        ).strip()
        if not (url and token and org and bucket):
            raise RuntimeError("Influx configuration requires url/token/org/bucket (INFLUXDB_* or INFLUX_*)")
        return cls(url=url, token=token, org=org, bucket=bucket)


@dataclass
class OpenProjectConfig:
    base_url: str
    username: Optional[str]
    password: Optional[str]
    api_token: Optional[str]
    client_id: Optional[str]
    client_secret: Optional[str]
    auth_url: Optional[str]
    token_url: Optional[str]
    scopes: Optional[str]

    @classmethod
    def load(cls) -> "OpenProjectConfig":
        base_url = (os.getenv("OPENPROJECT_BASE_URL") or "").strip().rstrip("/")
        if not base_url:
            raise RuntimeError("OPENPROJECT_BASE_URL is required")
        username = (os.getenv("OPENPROJECT_USERNAME") or os.getenv("OPENPROJECT_BASIC_USER") or "").strip() or None
        password = (os.getenv("OPENPROJECT_PASSWORD") or "").strip() or None
        api_token = (os.getenv("OPENPROJECT_API_TOKEN") or os.getenv("OPENPROJECT_API_KEY") or "").strip() or None
        client_id = (os.getenv("OPENPROJECT_OAUTH_CLIENT_ID") or "").strip() or None
        client_secret = (os.getenv("OPENPROJECT_OAUTH_CLIENT_SECRET") or "").strip() or None
        auth_url = (os.getenv("OPENPROJECT_OAUTH_AUTH_URL") or "").strip() or None
        token_url = (os.getenv("OPENPROJECT_OAUTH_TOKEN_URL") or "").strip() or None
        scopes = (os.getenv("OPENPROJECT_OAUTH_SCOPES") or "api_v3").strip() or None
        return cls(
            base_url=base_url,
            username=username,
            password=password,
            api_token=api_token,
            client_id=client_id,
            client_secret=client_secret,
            auth_url=auth_url,
            token_url=token_url,
            scopes=scopes,
        )


@dataclass
class TracingConfig:
    enabled: bool
    host: Optional[str]
    public_key: Optional[str]
    secret_key: Optional[str]

    @classmethod
    def load(cls) -> "TracingConfig":
        enabled = str(os.getenv("LANGFUSE_ENABLED", "0")).strip() == "1"
        host = (os.getenv("LANGFUSE_HOST") or "").strip() or None
        pub = (os.getenv("LANGFUSE_PUBLIC_KEY") or "").strip() or None
        sec = (os.getenv("LANGFUSE_SECRET_KEY") or "").strip() or None
        return cls(enabled=enabled, host=host, public_key=pub, secret_key=sec)
