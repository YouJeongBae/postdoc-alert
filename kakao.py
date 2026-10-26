import json
import requests

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


class KakaoClient:
    """카카오톡 '나에게 보내기' 클라이언트."""

    def __init__(self, rest_key, refresh_token, client_secret=None):
        self.rest_key = rest_key
        self.refresh_token = refresh_token
        self.client_secret = client_secret or None
        self.access_token = None
        self.new_refresh_token = None  # 카카오가 새 refresh token을 주면 여기에 저장

    def refresh(self):
        data = {
            "grant_type": "refresh_token",
            "client_id": self.rest_key,
            "refresh_token": self.refresh_token,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        r = requests.post(TOKEN_URL, data=data, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"카카오 토큰 갱신 실패: {r.status_code} {r.text}")
        j = r.json()
        self.access_token = j["access_token"]
        # refresh token 만료가 1개월 미만 남았을 때만 새 값이 내려옴
        if j.get("refresh_token"):
            self.new_refresh_token = j["refresh_token"]

    def send_text(self, text, url, button_title="자세히 보기"):
        if not self.access_token:
            self.refresh()
        template = {
            "object_type": "text",
            "text": text[:200],  # 텍스트 템플릿 최대 200자
            "link": {"web_url": url, "mobile_web_url": url},
            "button_title": button_title,
        }
        r = requests.post(
            SEND_URL,
            headers={"Authorization": f"Bearer {self.access_token}"},
            data={"template_object": json.dumps(template, ensure_ascii=False)},
            timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(f"카카오 전송 실패: {r.status_code} {r.text}")
