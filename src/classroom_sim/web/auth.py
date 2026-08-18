"""Supabase Auth 연동 — 로그인한 교사만 수업을 만들고 자기 수업만 볼 수 있게 한다.

지금까지는 URL을 아는 누구나 세션을 만들 수 있었다(출시 전 최대 리스크).
브라우저가 Supabase Auth로 로그인해 받은 JWT를 `Authorization: Bearer`로
보내면, 서버가 검증해 사용자를 식별하고 세션 소유권을 확인한다.

토큰 검증은 두 갈래다.

    SUPABASE_JWT_SECRET 있음  → HS256 서명을 로컬에서 직접 검증 (네트워크 불필요)
    없음                      → Supabase `/auth/v1/user`에 물어보고 짧게 캐시

로컬 검증이 빠르지만, 비대칭 키(ES256/RS256)를 쓰는 프로젝트는 시크릿이 없다.
그래서 원격 확인을 폴백으로 둔다. 원격 확인은 토큰 폐기(로그아웃)도 반영된다.

브라우저는 **인증에만** Supabase를 직접 호출한다. 학급·세션·전사 데이터는 전부
우리 서버를 거치므로, 브라우저에 나가는 것은 공개해도 되는 anon 키뿐이다.

환경변수:
    SUPABASE_URL            https://<project>.supabase.co
    SUPABASE_ANON_KEY       브라우저에 내려보내는 공개 키 (로그인 화면용)
    SUPABASE_JWT_SECRET     (선택) HS256 시크릿 — 있으면 로컬 검증
    AUTH_REQUIRED           1/0 강제 지정. 미지정이면 위 설정이 갖춰졌을 때 자동 활성
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from dataclasses import dataclass

log = logging.getLogger("classroom_sim.web")

VERIFY_TIMEOUT = 5.0
CACHE_TTL = 60.0          # 원격 확인 결과 캐시 — 로그아웃 반영이 1분 이상 늦지 않게
CACHE_MAX = 512
LEEWAY = 30.0             # 시계 오차 허용


@dataclass(frozen=True)
class User:
    id: str
    email: str = ""

    @property
    def short(self) -> str:
        return self.id[:8]


class AuthError(Exception):
    """검증 실패 — 호출부가 401로 바꾼다."""


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthConfig:
    url: str
    anon_key: str
    jwt_secret: str
    required: bool

    @property
    def can_verify(self) -> bool:
        return bool(self.url and (self.jwt_secret or self.anon_key))


def load_config() -> AuthConfig:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    anon = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    secret = (os.environ.get("SUPABASE_JWT_SECRET") or "").strip()
    if url and not url.startswith(("http://", "https://")):
        url = ""
    configured = bool(url and (anon or secret))

    forced = (os.environ.get("AUTH_REQUIRED") or "").strip().lower()
    if forced in ("1", "true", "yes", "on"):
        required = True
    elif forced in ("0", "false", "no", "off"):
        required = False
    else:
        required = configured   # 설정을 갖췄다면 켜는 것이 안전한 기본값

    if required and not configured:
        # 로그인을 요구하는데 검증할 수단이 없으면 아무도 못 들어온다. 조용히 넘기면
        # "왜 다 401이지?"로 헤매므로 크게 남긴다.
        log.error("AUTH_REQUIRED=1 이지만 SUPABASE_URL/ANON_KEY(또는 JWT_SECRET)가 없습니다 "
                  "— 모든 요청이 401이 됩니다. docs/supabase_setup.md 참조")
    return AuthConfig(url=url, anon_key=anon, jwt_secret=secret, required=required)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def _b64url(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def decode_unverified(token: str) -> tuple[dict, dict, bytes, bytes]:
    """(header, payload, signature, signing_input). 서명은 확인하지 않는다."""
    try:
        h_b64, p_b64, s_b64 = token.split(".")
        header = json.loads(_b64url(h_b64))
        payload = json.loads(_b64url(p_b64))
        sig = _b64url(s_b64)
    except Exception as exc:
        raise AuthError("토큰 형식이 올바르지 않습니다.") from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise AuthError("토큰 형식이 올바르지 않습니다.")
    return header, payload, sig, f"{h_b64}.{p_b64}".encode()


def _check_claims(payload: dict) -> User:
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        raise AuthError("토큰에 만료 정보가 없습니다.")
    if time.time() > float(exp) + LEEWAY:
        raise AuthError("로그인이 만료되었습니다. 다시 로그인해 주세요.")
    if payload.get("aud") not in (None, "authenticated"):
        raise AuthError("토큰 대상이 올바르지 않습니다.")
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise AuthError("토큰에 사용자 정보가 없습니다.")
    email = payload.get("email")
    return User(id=sub, email=email if isinstance(email, str) else "")


def verify_hs256(token: str, secret: str) -> User:
    header, payload, sig, signing_input = decode_unverified(token)
    if header.get("alg") != "HS256":
        # 비대칭 키 프로젝트 — 시크릿으로는 검증할 수 없다. 호출부가 원격으로 넘긴다.
        raise NotImplementedError(header.get("alg"))
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sig):
        raise AuthError("토큰 서명이 올바르지 않습니다.")
    return _check_claims(payload)


# ---------------------------------------------------------------------------
# 검증기
# ---------------------------------------------------------------------------


class Verifier:
    """토큰 → User. 원격 확인 결과는 짧게 캐시한다."""

    def __init__(self, config: AuthConfig) -> None:
        self.config = config
        self._cache: dict[str, tuple[float, User]] = {}
        self._guard = threading.Lock()

    # -- 캐시 -------------------------------------------------------------
    @staticmethod
    def _key(token: str) -> str:
        # 토큰 원문을 메모리에 그대로 들고 있지 않는다
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _cached(self, key: str) -> User | None:
        with self._guard:
            hit = self._cache.get(key)
            if hit and hit[0] > time.time():
                return hit[1]
            if hit:
                self._cache.pop(key, None)
        return None

    def _store(self, key: str, user: User) -> None:
        with self._guard:
            if len(self._cache) >= CACHE_MAX:
                self._cache.clear()   # 단순 방출 — 재확인 한 번이면 되돌아온다
            self._cache[key] = (time.time() + CACHE_TTL, user)

    # -- 원격 -------------------------------------------------------------
    def _verify_remote(self, token: str) -> User:
        import httpx

        try:
            r = httpx.get(
                f"{self.config.url}/auth/v1/user",
                headers={"apikey": self.config.anon_key, "Authorization": f"Bearer {token}"},
                timeout=VERIFY_TIMEOUT,
            )
        except Exception as exc:
            log.warning("토큰 원격 확인 실패(네트워크): %s", exc)
            raise AuthError("로그인 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc
        if r.status_code == 401:
            raise AuthError("로그인이 만료되었습니다. 다시 로그인해 주세요.")
        if r.status_code >= 400:
            log.warning("토큰 원격 확인 실패(%s): %s", r.status_code, r.text[:200])
            raise AuthError("로그인 확인에 실패했습니다.")
        try:
            data = r.json()
            uid = data["id"]
        except Exception as exc:
            raise AuthError("로그인 확인 응답을 이해하지 못했습니다.") from exc
        return User(id=uid, email=data.get("email") or "")

    # -- 공개 -------------------------------------------------------------
    def verify(self, token: str) -> User:
        token = (token or "").strip()
        if not token:
            raise AuthError("로그인이 필요합니다.")
        key = self._key(token)
        hit = self._cached(key)
        if hit is not None:
            return hit

        if self.config.jwt_secret:
            try:
                user = verify_hs256(token, self.config.jwt_secret)
                self._store(key, user)
                return user
            except NotImplementedError:
                pass    # 비대칭 서명 → 원격으로
        # 원격 확인 전에 만료·형식은 먼저 걸러 낸다 (불필요한 왕복 방지)
        _check_claims(decode_unverified(token)[1])
        if not self.config.anon_key:
            raise AuthError("서버에 로그인 검증 수단이 없습니다. 관리자에게 문의해 주세요.")
        user = self._verify_remote(token)
        self._store(key, user)
        return user

    def invalidate(self, token: str) -> None:
        with self._guard:
            self._cache.pop(self._key(token), None)


def bearer_token(header_value: str | None) -> str:
    """`Authorization: Bearer <token>` 에서 토큰만 꺼낸다."""
    if not header_value:
        return ""
    parts = header_value.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()
