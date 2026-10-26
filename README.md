# 📬 포닥·장학금·산업체 공고 카톡 알림

매일 아침 8시(KST)에 공고 사이트를 확인해서 **새로 올라온 공고만** 카카오톡 "나에게 보내기"로 알려줍니다.
GitHub Actions에서 돌아가므로 PC를 켜둘 필요가 없습니다.

| 구분 | 소스 | 방식 |
|---|---|---|
| 학계 (유럽) | AcademicPositions, ScholarshipDB, EURAXESS, jobs.ac.uk | 사이트 검색 결과 페이지 수집 |
| 산업체 (미국·유럽) + 미국 포닥/국립연구소 | Adzuna 공식 API | 키워드 검색 |
| 장학금 | 훔볼트 연구 펠로십 | 모집 열림/마감 상태 변화 + 오픈 7일 전 리마인더 |
| 기업 연구소 | Bosch (SmartRecruiters 공식 API) | 열관리·히트펌프 키워드, 유럽·미국 국가만 |
| 현대차 | HATCI(미국) 채용 사이트, HMETC(독일)는 Adzuna 독일 검색 | thermal 키워드 / 회사명 검색 |
| 산학 포닥 | EURAXESS·AcademicPositions "industrial postdoc" + Adzuna | 제목에 열·차량·배터리 관련 단어가 있는 것만 |
| MSCA 호스트 | EURAXESS "MSCA postdoctoral fellowship" | MSCA 지원자를 찾는 대학·기업 공고 |
| 펠로십 일정 | MSCA 포닥 펠로십 2027 | 오픈 30일 전·당일, 마감 30일 전 리마인더 (`deadline_reminders`) |

매일 오는 메시지: ① 요약(새 공고 수, 훔볼트 상태, 수집 문제) ② 공고별 메시지(최대 8개, 산업체 → 국립연구소 → 학계 순) ③ 나머지는 요약 페이지 링크.
공고마다 [현대차 HATCI], [Bosch], [산학 포닥], [MSCA 호스트] 같은 경로 태그가 붙고, `priority_companies`에 있는 완성차·부품사 공고와 제목에 "industrial postdoc" 등이 들어간 공고는 ★와 함께 맨 앞에 옵니다.
미국 공고에는 비자 제한 문구(시민권, security clearance 등)를 찾아 ⛔ 또는 ⚠️ 표시를 붙입니다.

---

## 설정 순서 (약 30분)

### 1. Kakao Developers
(2025년 콘솔 개편 이후 메뉴 기준)
1. https://developers.kakao.com → 내 애플리케이션 → 애플리케이션 추가하기
2. **[앱] > [플랫폼 키] > [REST API 키]** 에서 키 복사 → 키를 클릭해 상세 화면으로 들어가서
   - 카카오 로그인 **리다이렉트 URI**에 `http://localhost:3000` 등록
   - **클라이언트 시크릿**이 켜져 있으면 그 값도 복사 (꺼져 있으면 그대로 둬도 됨)
3. **[카카오 로그인] > [일반]** 에서 사용 설정 ON
4. **[카카오 로그인] > [동의항목]** 에서 "카카오톡 메시지 전송(talk_message)" 사용 설정
5. **[앱] > [제품 링크 관리] > 웹 도메인** 에 카톡 버튼이 열 도메인 등록
   `https://YOUR_GITHUB_ID.github.io`, `https://academicpositions.com`, `https://scholarshipdb.net`,
   `https://euraxess.ec.europa.eu`, `https://www.jobs.ac.uk`, `https://www.humboldt-foundation.de`, `https://ec.europa.eu`,
   `https://careers-americas.hyundai.com`, `https://jobs.smartrecruiters.com`
   (개수 제한에 걸리면 덜 중요한 것을 빼세요. 빠진 도메인의 공고는 요약 페이지로 연결됩니다.)

### 2. 토큰 발급 (내 PC에서 1회)
```bash
pip install -r requirements.txt
python get_token.py
```
카톡에 "연결 테스트 성공" 메시지가 오면 성공. 출력된 refresh token을 복사해 둡니다.

### 3. Adzuna API 키 (산업체 공고용, 무료)
https://developer.adzuna.com 가입 → App ID / App Key 발급

### 4. GitHub 저장소
1. 새 저장소 `postdoc-alert` 생성 후 이 폴더 전체 업로드
2. `config.yaml`의 `digest_url`을 `https://본인ID.github.io/postdoc-alert/`로 수정
3. **Settings → Pages** → Source: *Deploy from a branch*, Branch: `main` / `/docs`
   (무료 계정은 Pages를 쓰려면 저장소가 Public이어야 합니다. 키는 Secret에 들어가므로 노출되지 않습니다.)
4. **Settings → Secrets and variables → Actions**에 등록

| 이름 | 값 |
|---|---|
| `KAKAO_REST_KEY` | REST API 키 |
| `KAKAO_REFRESH_TOKEN` | 2단계에서 받은 refresh token |
| `KAKAO_CLIENT_SECRET` | (Client Secret 켰을 때만) |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna 키 |
| `GH_PAT` | GitHub Personal Access Token (fine-grained, 이 저장소에 **Secrets: Read and write** 권한) |

`GH_PAT`는 카카오 refresh token(약 2개월 유효)이 갱신될 때 Secret을 자동으로 바꾸는 데 씁니다.

### 5. 첫 실행
**Actions 탭 → daily-alert → Run workflow**.
첫 실행은 현재 공고를 "이미 본 것"으로 기록만 하고 시작 메시지를 보냅니다. 다음 날부터 새 공고만 옵니다.

---

## 처음 1~2주는 조정 기간

- 요약 메시지에 `⚠️ 확인 필요: ScholarshipDB` 같은 문구가 보이면, 그 사이트에서 공고 링크를 하나도 못 찾은 경우(페이지 구조 변경이나 자동 접속 차단)입니다. 관련 단어 필터로 0건이 된 경우는 정상이라 경고하지 않습니다. 상세 내용은 요약 페이지 맨 위에 나옵니다. `config.yaml`의 `link_pattern`을 고치거나 해당 소스를 지우면 됩니다.
  로컬에서 `python main.py --dry-run`으로 사이트별 수집 건수와 보낼 메시지를 미리 볼 수 있습니다(전송·저장 안 함).
- 알림이 너무 많거나 적으면 `config.yaml`의 검색 URL 키워드, `queries`, `exclude_title_keywords`를 조정하세요.
- AcademicPositions·ScholarshipDB 자체 이메일 알림도 함께 걸어두면 이 봇이 놓치는 경우의 안전망이 됩니다.

## 사이트 추가
- SmartRecruiters를 쓰는 다른 회사: `smartrecruiters_sources`에 `company_id`만 바꿔 추가 (jobs.smartrecruiters.com/<company_id> 주소에서 확인)
- 학계·장학금 검색 페이지: `html_sources`에 항목 추가 (`url` = 검색 결과 주소, `link_pattern` = 공고 상세 링크 정규식)
- 상태 감시형(훔볼트처럼 열림/닫힘): `check_humboldt`를 참고해 같은 방식으로 추가
- 날짜가 정해진 펠로십: `deadline_reminders`에 이름·URL·날짜·며칠 전 알림(offsets)만 추가. MSCA 2028 공고가 확정되면 같은 형식으로 한 블록 더 넣으면 됩니다.
