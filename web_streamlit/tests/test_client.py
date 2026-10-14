"""Изолированные сценарии HTTP-клиента: каждый запрос проходит через MockTransport."""
import json
from collections import deque

import httpx
import pytest

from api_client import ApiClient, ApiError


def response(data=None, status=200, success=True, message="Ошибка API"):
    return httpx.Response(status, json={"success": success, "data": data, "message": message})


def session(suffix="one"):
    return {"access_token": "access-" + suffix, "refresh_token": "refresh-" + suffix,
            "user": {"Id": suffix, "Name": "Тест", "Role": "master"}}


def scenario(*steps, authenticated=True):
    """Неожиданный повтор запроса сразу падает; сеть и файловая система не нужны."""
    pending = deque(([response(session())] if authenticated else []) + list(steps))
    requests = []

    def send(request):
        requests.append(request)
        assert pending, "Клиент отправил незапланированный HTTP-запрос"
        result = pending.popleft()
        if isinstance(result, Exception):
            raise result
        return result

    client = ApiClient("http://test.local", transport=httpx.MockTransport(send))
    if authenticated:
        client.login("  master@test.local  ", "secret")
        requests.clear()
    return client, requests


def body(request):
    return json.loads(request.content)


def test_login_normalizes_email_and_preserves_password():
    client, sent = scenario(response(session()), authenticated=False)
    assert client.login("  user@test.local  ", " password ")["Id"] == "one"
    assert client.authenticated
    assert body(sent[0]) == {"email": "user@test.local", "password": " password "}
    assert "authorization" not in sent[0].headers


@pytest.mark.parametrize("reply,status", [
    (response(status=401, success=False, message="Неверный пароль"), 401),
    (httpx.ConnectError("offline"), 0),
    (httpx.Response(200, text="not-json"), 200),
    (httpx.Response(200, json=[]), 200),
])
def test_login_wrong_network_and_malformed_reply_are_errors_without_retry(reply, status):
    client, sent = scenario(reply, authenticated=False)
    with pytest.raises(ApiError) as error:
        client.login("user@test.local", "bad")
    assert error.value.status == status
    assert not client.authenticated
    assert len(sent) == 1


@pytest.mark.parametrize("invalid", [None, [], "token", {}, {"access_token": 123},
                                      {"access_token": "a", "refresh_token": "r", "user": []}])
def test_malformed_successful_login_data_is_rejected(invalid):
    client, sent = scenario(response(invalid), authenticated=False)
    with pytest.raises(ApiError):
        client.login("user@test.local", "secret")
    assert not client.authenticated
    assert len(sent) == 1


def test_separate_clients_never_share_tokens_or_identity():
    first, first_sent = scenario(response({"owner": "one"}), response())
    second, second_sent = scenario(response(session("two")), response({"owner": "two"}), authenticated=False)
    second.login("second@test.local", "secret")
    assert first.call("meta")["owner"] == "one"
    assert second.call("meta")["owner"] == "two"
    first.logout()
    assert not first.authenticated and second.user["Id"] == "two"
    assert first_sent[0].headers["authorization"] == "Bearer access-one"
    assert second_sent[1].headers["authorization"] == "Bearer access-two"


def test_401_refresh_retries_once_with_same_idempotency_key_and_body():
    client, sent = scenario(response(status=401, success=False), response(session("new")), response({"Id": 7}))
    assert client.call("equipment", "POST", {"Name": "Станок"}, action="create")["Id"] == 7
    assert [r.url.path for r in sent] == ["/api/equipment", "/api/auth/refresh", "/api/equipment"]
    assert sent[0].headers["idempotency-key"] == sent[2].headers["idempotency-key"]
    assert sent[0].content == sent[2].content
    assert body(sent[1]) == {"refresh_token": "refresh-one"}
    assert sent[2].headers["authorization"] == "Bearer access-new"


def test_logout_after_refresh_revokes_rotated_refresh_token_and_clears_session():
    client, sent = scenario(response(status=401, success=False), response(session("new")), response())
    client.logout()
    assert body(sent[0]) == {"refresh_token": "refresh-one"}
    assert body(sent[2]) == {"refresh_token": "refresh-new"}
    assert sent[2].headers["authorization"] == "Bearer access-new"
    assert not client.authenticated and not client._attempts


@pytest.mark.parametrize("reply", [response(status=401, success=False), httpx.ConnectError("offline")])
def test_failed_logout_always_clears_local_session(reply):
    client, _ = scenario(reply, response(status=401, success=False))
    with pytest.raises(ApiError):
        client.logout()
    assert not client.authenticated


def test_failed_refresh_clears_expired_session_without_retrying_mutation():
    client, sent = scenario(response(status=401, success=False), response(status=401, success=False))
    with pytest.raises(ApiError):
        client.call("equipment", "POST", {"Name": "A"})
    assert len(sent) == 2
    assert not client.authenticated


def test_malformed_refresh_data_is_a_controlled_error():
    client, sent = scenario(response(status=401, success=False), response(None))
    with pytest.raises(ApiError):
        client.call("meta")
    assert len(sent) == 2


@pytest.mark.parametrize("raw", [None, b"\x00\xffphoto\x01"])
def test_explicit_retry_preserves_key_payload_and_bytes_until_success(raw):
    client, sent = scenario(httpx.ReadTimeout("unknown outcome"), response({"Id": 8}), response({"Id": 9}))
    args = {"payload": {"Name": "A"}, "params": {"kind": "photo"}, "raw": raw, "action": "save"}
    with pytest.raises(ApiError):
        client.call("files/upload", "POST", **args)
    assert len(sent) == 1
    client.call("files/upload", "POST", **args)
    assert sent[0].headers["idempotency-key"] == sent[1].headers["idempotency-key"]
    assert sent[0].content == sent[1].content
    if raw is not None:
        assert sent[1].content == raw
    assert not client._attempts
    client.call("files/upload", "POST", **args)
    assert sent[1].headers["idempotency-key"] != sent[2].headers["idempotency-key"]


@pytest.mark.parametrize("change", [{"payload": {"Name": "B"}}, {"params": {"kind": "other"}},
                                     {"raw": b"changed"}])
def test_changed_operation_gets_new_key(change):
    client, sent = scenario(response(status=500, success=False), response(status=500, success=False))
    original = {"payload": {"Name": "A"}, "params": {"kind": "photo"}, "raw": b"original", "action": "save"}
    for options in (original, original | change):
        with pytest.raises(ApiError):
            client.call("files/upload", "POST", **options)
    assert sent[0].headers["idempotency-key"] != sent[1].headers["idempotency-key"]


def test_reordered_json_keys_keep_failed_attempt_key():
    client, sent = scenario(response(status=409, success=False), response({"Id": 1}))
    with pytest.raises(ApiError):
        client.call("equipment", "PUT", {"Name": "A", "Id": 1})
    client.call("equipment", "PUT", {"Id": 1, "Name": "A"})
    assert sent[0].headers["idempotency-key"] == sent[1].headers["idempotency-key"]


@pytest.mark.parametrize("url", ["https://evil.test/api/files/a", "//evil.test/api/files/a",
    "/api/files/a?token=secret", "/api/files/a#fragment", "/api/auth/login", "/api/files/../auth/login"])
def test_download_rejects_foreign_or_unsafe_urls_without_network(url):
    client, sent = scenario()
    with pytest.raises(ApiError):
        client.download(url)
    assert not sent


@pytest.mark.parametrize("path", ["/api/files/photo.jpg", "/api/download/report.xlsx"])
def test_download_refreshes_expired_access_with_current_client_identity(path):
    client, sent = scenario(response(status=401, success=False), response(session("new")), httpx.Response(200, content=b"file"))
    assert client.download(path) == b"file"
    assert sent[0].headers["authorization"] == "Bearer access-one"
    assert sent[2].headers["authorization"] == "Bearer access-new"
    assert sent[2].url.host == "test.local" and sent[2].url.path == path


def test_foreign_user_download_is_forbidden_without_refresh_or_retry():
    client, sent = scenario(response(status=403, success=False, message="Нет доступа"))
    with pytest.raises(ApiError, match="Нет доступа") as error:
        client.download("/api/download/another-users-report.xlsx")
    assert error.value.status == 403 and len(sent) == 1


def test_second_401_does_not_create_refresh_loop():
    client, sent = scenario(response(status=401, success=False), response(session("new")), response(status=401, success=False))
    with pytest.raises(ApiError):
        client.call("meta")
    assert len(sent) == 3


@pytest.mark.parametrize("operation", ["call", "download"])
def test_connection_failure_never_causes_automatic_network_retry(operation):
    client, sent = scenario(httpx.ConnectError("offline"))
    with pytest.raises(ApiError):
        client.call("meta") if operation == "call" else client.download("/api/files/photo.jpg")
    assert len(sent) == 1


@pytest.mark.parametrize("status", [404, 410])
def test_expired_or_missing_download_is_reported_without_retry(status):
    client, sent = scenario(response(status=status, success=False, message="Файл недоступен"))
    with pytest.raises(ApiError, match="Файл недоступен") as error:
        client.download("/api/download/expired.xlsx")
    assert error.value.status == status and len(sent) == 1


def test_new_login_does_not_reuse_previous_users_failed_attempt_key():
    client, sent = scenario(response(status=409, success=False), response(session("two")), response({"Id": 2}))
    with pytest.raises(ApiError):
        client.call("equipment", "POST", {"Name": "A"}, action="create")
    client.login("second@test.local", "secret")
    client.call("equipment", "POST", {"Name": "A"}, action="create")
    assert sent[0].headers["idempotency-key"] != sent[2].headers["idempotency-key"]
    assert sent[2].headers["authorization"] == "Bearer access-two"


def test_upload_after_401_refresh_keeps_exact_binary_body_and_key():
    client, sent = scenario(response(status=401, success=False), response(session("new")), response({"Id": 2}))
    raw = b"\x00\xff\x89PNG\r\n"
    client.call("files/upload", "POST", raw=raw, params={"filename": "a.png"})
    assert sent[0].content == sent[2].content == raw
    assert sent[0].headers["idempotency-key"] == sent[2].headers["idempotency-key"]
