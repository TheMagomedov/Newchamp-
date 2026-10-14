"""Фрагмент 1: HTTP, сеанс и безопасные повторы; никаких SQL и глобальных токенов."""
import hashlib
import json
import uuid
from urllib.parse import urlsplit

import httpx


class ApiError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.message = message
        self.status = status


class ApiClient:
    def __init__(self, base_url="http://127.0.0.1:8000", transport=None):
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._session = {}
        self._attempts = {}

    @property
    def authenticated(self):
        return bool(self._session.get("access_token"))

    @property
    def user(self):
        return self._session.get("user", {})

    def login(self, email, password):
        data = self.call("auth/login", method="POST", payload={
            "email": email.strip(), "password": password
        })
        self._session = self._auth_data(data)
        self._attempts.clear()
        return self.user

    def logout(self):
        try:
            if self._session.get("refresh_token"):
                self.call("auth/logout", method="POST", payload={
                    "refresh_token": self._session["refresh_token"]
                })
        finally:
            self._session.clear()
            self._attempts.clear()

    def _key(self, action, method, path, payload, params, raw):
        identity = json.dumps([method, path, payload, params], sort_keys=True,
                              ensure_ascii=False, default=str).encode("utf-8")
        signature = hashlib.sha256(identity + (raw or b"")).hexdigest()
        slot = action or f"{method}:{path}"
        saved = self._attempts.get(slot)
        if not saved or saved[0] != signature:
            self._attempts[slot] = (signature, str(uuid.uuid4()))
        return slot, self._attempts[slot][1]

    def _send(self, path, method, payload, params, raw, headers):
        if path.startswith(("/", "http:" , "https:")) or ".." in path.split("/"):
            raise ApiError("Недопустимый адрес запроса.")
        options = {"params": params, "headers": headers}
        if raw is not None:
            options["content"] = raw
        elif payload is not None:
            options["json"] = payload
        try:
            with httpx.Client(timeout=15, transport=self._transport,
                              follow_redirects=False, trust_env=False) as connection:
                return connection.request(method, self.base_url + "/api/" + path, **options)
        except httpx.RequestError as exc:
            raise ApiError("API недоступен. Проверьте сервер и повторите действие.") from exc

    @staticmethod
    def _auth_data(data):
        if not isinstance(data, dict) or not isinstance(data.get("user"), dict):
            raise ApiError("Сервер вернул некорректный сеанс входа.", 502)
        if any(not isinstance(data.get(key), str) or not data[key]
               for key in ("access_token", "refresh_token")):
            raise ApiError("Сервер не выдал действительные токены входа.", 502)
        return data

    @staticmethod
    def _data(response):
        try:
            result = response.json()
        except ValueError as exc:
            raise ApiError("Сервер вернул некорректный ответ.", response.status_code) from exc
        if not response.is_success or not isinstance(result, dict) or not result.get("success"):
            message = result.get("message") if isinstance(result, dict) else None
            raise ApiError(message or "Запрос не выполнен.", response.status_code)
        return result.get("data")

    def _refresh(self):
        token = self._session.get("refresh_token")
        if not token:
            self._session.clear()
            raise ApiError("Войдите в систему заново.", 401)
        response = self._send("auth/refresh", "POST", {"refresh_token": token}, None, None, {})
        try:
            self._session = self._auth_data(self._data(response))
        except ApiError as exc:
            if exc.status in (400, 401, 403):
                self._session.clear()
            raise

    def call(self, path, method="GET", payload=None, params=None, raw=None, action=None):
        method = method.upper()
        headers = {}
        slot = None
        if method in ("POST", "PUT", "DELETE") and not path.startswith("auth/"):
            slot, key = self._key(action, method, path, payload, params, raw)
            headers["Idempotency-Key"] = key
        if self.authenticated:
            headers["Authorization"] = "Bearer " + self._session["access_token"]
        response = self._send(path, method, payload, params, raw, headers)
        if response.status_code == 401 and path not in ("auth/login", "auth/refresh"):
            self._refresh()
            headers["Authorization"] = "Bearer " + self._session["access_token"]
            if path == "auth/logout":
                payload = {"refresh_token": self._session["refresh_token"]}
            response = self._send(path, method, payload, params, raw, headers)
        data = self._data(response)
        if slot:
            self._attempts.pop(slot, None)
        return data

    def download(self, url):
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise ApiError("Скачивание разрешено только с текущего API.")
        if not parsed.path.startswith(("/api/download/", "/api/files/")):
            raise ApiError("Недопустимая ссылка скачивания.")
        path = parsed.path.removeprefix("/api/")
        headers = {"Authorization": "Bearer " + self._session.get("access_token", "")}
        response = self._send(path, "GET", None, None, None, headers)
        if response.status_code == 401:
            self._refresh()
            headers["Authorization"] = "Bearer " + self._session["access_token"]
            response = self._send(path, "GET", None, None, None, headers)
        if not response.is_success:
            self._data(response)
        return response.content
