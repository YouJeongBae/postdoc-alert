"""최초 1회: 카카오 refresh token 발급 + 테스트 메시지 전송 (내 PC에서 실행).
브라우저에서 동의하면 code를 자동으로 받아오므로 복사/붙여넣기가 필요 없습니다.
Kakao 콘솔의 리다이렉트 URI는 http://localhost:3000 이어야 합니다."""
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from kakao import KakaoClient

REDIRECT = "http://localhost:3000"
result = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        if "code" in qs:
            result["code"] = qs["code"][0]
            msg = "인증 완료! 이 창을 닫고 명령 프롬프트로 돌아가세요."
        elif "error" in qs:
            result["error"] = qs.get("error_description", qs["error"])[0]
            msg = "인증 실패: " + result["error"]
        else:
            msg = "대기 중..."
        body = f"<html><meta charset='utf-8'><body style='font-family:sans-serif;padding:40px'><h2>{msg}</h2></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args):
        pass


rest_key = input("REST API 키: ").strip()
secret = input("Client Secret (사용 안 하면 그냥 엔터): ").strip()

server = HTTPServer(("localhost", 3000), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

auth_url = "https://kauth.kakao.com/oauth/authorize?" + urlencode({
    "client_id": rest_key, "redirect_uri": REDIRECT,
    "response_type": "code", "scope": "talk_message",
})
print("\n브라우저가 열립니다. 카카오 로그인/동의를 해주세요.")
print("(브라우저가 안 열리면 아래 주소를 직접 복사해서 여세요)\n" + auth_url)
webbrowser.open(auth_url)

print("\n브라우저에서 '인증 완료!'가 뜰 때까지 기다리는 중...")
while "code" not in result and "error" not in result:
    threading.Event().wait(0.5)
server.shutdown()

if "error" in result:
    raise SystemExit(f"카카오 인증 실패: {result['error']}")

data = {"grant_type": "authorization_code", "client_id": rest_key,
        "redirect_uri": REDIRECT, "code": result["code"]}
if secret:
    data["client_secret"] = secret
j = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=30).json()
if "refresh_token" not in j:
    raise SystemExit(f"토큰 발급 실패: {j}")

client = KakaoClient(rest_key, j["refresh_token"], secret)
client.access_token = j["access_token"]
client.send_text("✅ 공고 알림 봇 연결 테스트 성공!", "https://www.humboldt-foundation.de/en/", "확인")

print("\n카톡을 확인해 보세요. 아래 값을 GitHub Secret 'KAKAO_REFRESH_TOKEN'에 넣으세요:\n")
print(j["refresh_token"])
