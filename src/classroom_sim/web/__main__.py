"""uvicorn 실행 래퍼.

    PYTHONPATH=src python -m classroom_sim.web --port 8000
    PYTHONPATH=src CLASSROOM_SIM_FAKE=1 python -m classroom_sim.web  # 엔진 없이 개발
"""

from __future__ import annotations

import argparse
import logging
import os
import socket


def _lan_ip() -> str | None:
    """이 컴퓨터가 같은 Wi-Fi(LAN)에서 보이는 IP를 찾는다.

    UDP 소켓을 connect 하면 실제 패킷을 보내지 않고도 커널이 고를 출발지 주소를
    알 수 있다. 오프라인이면 호스트 이름으로 한 번 더 시도하고, 그래도 안 되면 None.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        sock.close()
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return None


def _print_access_hint(host: str, port: int) -> None:
    """--host 0.0.0.0 처럼 외부 공개로 띄웠을 때 휴대폰 접속 주소를 안내한다."""
    if host not in ("0.0.0.0", "::", "0"):
        return
    ip = _lan_ip()
    print("")
    print("  ┌─ 보이는 교실 ─────────────────────────────")
    print(f"  │  이 컴퓨터  : http://127.0.0.1:{port}")
    if ip:
        print(f"  │  휴대폰     : http://{ip}:{port}")
        print("  │  (같은 Wi-Fi 에 연결한 뒤 위 주소를 브라우저 주소창에 입력하세요)")
    else:
        print("  │  휴대폰     : LAN IP를 찾지 못했습니다.")
        print("  │  (터미널에서 ipconfig / ifconfig 로 IP를 확인해 http://<IP>:%d 로 접속)" % port)
    print("  │  ※ 같은 네트워크의 다른 기기에도 열려 있으니 사용 후 서버를 꺼주세요.")
    print("  └───────────────────────────────────────────")
    print("")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m classroom_sim.web", description="보이는 교실 웹 서버")
    ap.add_argument(
        "--host",
        default="127.0.0.1",
        help="바인드 주소 (기본 127.0.0.1). 휴대폰에서 접속하려면 --host 0.0.0.0",
    )
    ap.add_argument("--port", type=int, default=8000, help="포트 (기본 8000)")
    ap.add_argument("--reload", action="store_true", help="코드 변경 시 자동 재시작")
    ap.add_argument(
        "--fake",
        action="store_true",
        help="무대 엔진 대신 개발용 FakeSession 사용 (CLASSROOM_SIM_FAKE=1 과 동일)",
    )
    args = ap.parse_args()

    if args.fake:
        os.environ["CLASSROOM_SIM_FAKE"] = "1"

    import uvicorn

    # 앱 로그(classroom_sim.web)가 시간과 함께 터미널에 남게 한다.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    _print_access_hint(args.host, args.port)

    uvicorn.run(
        "classroom_sim.web.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
