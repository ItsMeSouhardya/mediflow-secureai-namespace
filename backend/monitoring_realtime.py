"""Redis-backed monitoring pub/sub with an in-process development fallback."""

from __future__ import annotations

import json
import queue
import threading
from collections import defaultdict

try:
    import redis
except ImportError:  # Optional in old/local environments; production installs it.
    redis = None


class MonitoringBroker:
    def __init__(self):
        self._client = None
        self._url = None
        self._subscribers = defaultdict(list)
        self._lock = threading.Lock()

    def configure(self, url: str | None):
        if url == self._url:
            return
        self._url = url
        self._client = None
        if url and redis is not None:
            try:
                client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1)
                client.ping()
                self._client = client
            except Exception:
                self._client = None

    def publish(self, channel: str, event: dict) -> None:
        encoded = json.dumps(event, separators=(",", ":"), default=str)
        if self._client is not None:
            try:
                self._client.publish(channel, encoded)
            except Exception:
                pass
        with self._lock:
            for subscriber in list(self._subscribers[channel]):
                subscriber.put_nowait(encoded)

    def stream(self, channel: str):
        if self._client is not None:
            pubsub = self._client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(channel)
            try:
                for message in pubsub.listen():
                    if message and message.get("type") == "message":
                        yield message["data"]
            finally:
                pubsub.close()
            return

        subscriber = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers[channel].append(subscriber)
        try:
            while True:
                try:
                    yield subscriber.get(timeout=15)
                except queue.Empty:
                    yield None
        finally:
            with self._lock:
                self._subscribers[channel].remove(subscriber)


broker = MonitoringBroker()


def patient_channel(patient_profile_id: int) -> str:
    return f"monitoring:patient:{patient_profile_id}"


def hospital_channel(hospital_id: int) -> str:
    return f"monitoring:hospital:{hospital_id}"


def doctor_channel(doctor_profile_id: int) -> str:
    return f"monitoring:doctor:{doctor_profile_id}"
