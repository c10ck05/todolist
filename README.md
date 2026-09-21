# Todo✓ — 풀스택 투두리스트 앱

> FastAPI 백엔드 + Vanilla JS 프론트엔드로 만든 개인 투두리스트 서비스

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/Python-3.11+-yellow)
![FastAPI](https://img.shields.io/badge/FastAPI-0.138-green)

---

## 📌 목차

- [소개](#-소개)
- [주요 기능](#-주요-기능)
- [기술 스택](#-기술-스택)
- [프로젝트 구조](#-프로젝트-구조)
- [시작하기](#-시작하기)
- [환경 변수](#-환경-변수)
- [API 명세](#-api-명세)
- [화면 구성](#-화면-구성)

---

## 🗒 소개

회원가입 / 로그인부터 마감기한 관리, 이메일 리마인더까지 지원하는  
**1인 풀스택 투두리스트 웹 앱**입니다.

- 백엔드: **FastAPI** (Python) — Render 배포
- 프론트엔드: **Vanilla HTML/CSS/JS** (단일 파일)
- DB: **PostgreSQL** (SQLAlchemy ORM)
- 이메일: **Resend API**

---

## ✨ 주요 기능

### 👤 인증
| 기능 | 설명 |
|------|------|
| 회원가입 | 이메일 인증번호(6자리) 확인 후 가입 |
| 로그인 | JWT 토큰 발급 (HS256) |
| 비밀번호 재설정 | 이메일 인증번호로 재설정 |
| 비밀번호 암호화 | bcrypt 해싱 적용 |

### ✅ 투두
| 기능 | 설명 |
|------|------|
| 투두 추가 / 삭제 | 본인 투두만 수정·삭제 가능 |
| 내용 수정 | 텍스트 더블클릭으로 인라인 편집 |
| 완료 토글 | 체크박스 클릭으로 완료 처리 |
| 마감기한 설정 / 제거 | datetime-local picker, D-day 뱃지 표시 |
| 마감 초과 강조 | 기한 지난 투두는 주황색 배경으로 표시 |
| 우선순위 | 높음 / 보통 / 낮음 + 색상 뱃지·정렬 |
| 카테고리 | 유저가 만든 카테고리로 분류·필터 |
| 반복 | 매일 / 매주 / 매월, 완료 시 다음 회차 자동 생성 |
| 메모 | 항목별 상세 메모 |
| 서브태스크 | 항목 안에 체크리스트(진행도 표시) |
| 검색 / 정렬 | 제목 검색, 등록·마감·우선순위·가나다순 정렬 |
| 드래그 정렬 | 등록순 모드에서 순서 직접 변경 |
| 일괄 처리 | 전체 완료 / 완료 항목 삭제 |

### 🔔 알림
| 기능 | 설명 |
|------|------|
| 이메일 리마인더 | 마감 24시간 전 자동 이메일 발송 |
| 스케줄러 | APScheduler — 30분마다 마감 체크 |
| Keep-alive | 10분마다 서버 핑 (Render 슬립 방지) |

### 🖥 UI/UX
| 기능 | 설명 |
|------|------|
| 다크모드 | 라이트 / 다크 토글 (localStorage 저장) |
| 필터 탭 | 전체 / 할 일 / 완료 / 마감초과 |
| 타임라인 뷰 | 마감기한 기준 날짜별 그룹 시각화 |
| 캘린더 뷰 | 월간 그리드에 마감일 표시, 날짜 클릭 시 목록 |
| 통계바 | 완료율·진행바·남은 개수 |
| 데이터 백업 | JSON 내보내기 / 가져오기 |
| 계정 관리 | 비밀번호 변경 / 계정 삭제 |
| PWA | 홈 화면 설치·오프라인(앱 셸 캐시) *HTTPS 호스팅 시 |
| 반응형 | 모바일 / 데스크탑 대응 |
| 엔터키 지원 | 모든 입력 폼에서 엔터로 제출 |

---

## 🛠 기술 스택

### Backend
- **FastAPI** 0.138
- **SQLAlchemy** 2.0 (ORM)
- **PostgreSQL** (psycopg2-binary)
- **bcrypt** — 비밀번호 해싱
- **PyJWT** — JWT 토큰
- **Resend** — 이메일 발송
- **APScheduler** — 백그라운드 스케줄러
- **python-dotenv** — 환경변수

### Frontend
- HTML5 / CSS3 / Vanilla JavaScript (단일 파일, 프레임워크 없음)
- CSS Variables 기반 다크모드
- Fetch API 기반 REST 통신

---

## 📂 프로젝트 구조

```
todo-app/
├── main.py          # ASGI 진입점 (uvicorn main:app 호환 유지)
├── database.py      # 기존 외부 스크립트용 호환 import
├── backend/
│   ├── app.py       # FastAPI 조립, CORS, 라우터, 수명주기
│   ├── config.py    # 환경 변수 설정
│   ├── database.py  # SQLAlchemy 엔진 / 세션
│   ├── models.py    # SQLAlchemy 테이블 모델
│   ├── dependencies.py # DB / 인증 의존성
│   ├── routers/     # 인증, 투두, 서브태스크, 계정, 헬스체크 API
│   ├── services/    # Resend 이메일, 마감 리마인더 스케줄러
│   └── utils/       # 투두 직렬화, 반복 기한 계산
├── requirements.txt # Python 패키지 목록
└── index.html       # 프론트엔드 (단일 HTML 파일)
```

### DB 테이블

인증 요청 제한은 `auth_rate_limits` 테이블에 저장하며 서버 시작 시 자동 생성됩니다.
계정별 15분 동안 인증번호 확인 5회, 로그인 10회, 이메일 발송 3회로 제한하며,
발송 사이에는 60초 대기시간이 있습니다. 각 동작의 IP별 제한은 15분당 30회입니다.
성공 요청도 횟수에 포함되고 인증번호 재발송으로 확인 횟수가 초기화되지 않습니다.
프록시 뒤에서는 ASGI 서버가 신뢰하는 프록시만 클라이언트 IP를 전달하도록 설정해야 합니다.

로그인 토큰은 현재 비밀번호 해시에 연결되므로 비밀번호 변경·재설정 후 즉시 무효화됩니다.
이 보안 변경 이전에 발급된 토큰도 거부되므로 배포 후 사용자는 다시 로그인해야 합니다.

반복 일정 중복 방지 기록은 `todo_recurrences` 테이블에 저장합니다.
서버 시작 시 기존 `create_all()`에서 새 테이블을 생성하므로 기존 테이블의 컬럼 변경은 필요 없습니다.
배포 전에 이미 생성된 반복 일정은 연결 기록이 없으며, 기존 중복 데이터는 자동으로 삭제하지 않습니다.

회귀 테스트는 실제 DB 대신 임시 SQLite DB로 실행합니다:

```bash
python -m unittest discover -s tests -v
```

```
users
├── id            (PK, Integer)
├── user_id       (String, unique)
├── password      (String, bcrypt 해시)
└── email         (String, unique)

todolist
├── id            (PK, Integer)
├── todo          (Text)
├── owner_id      (String, FK → users.user_id)
├── completed     (Boolean)
├── deadline      (DateTime, nullable)
├── reminder_sent (Boolean)
├── category      (String, nullable)
├── repeat_cycle  (String, none/daily/weekly/monthly)
├── priority      (Integer, 0=낮음/1=보통/2=높음)
├── detail        (Text, nullable, 메모)
└── sort_order    (Integer, nullable, 수동 정렬)

subtasks
├── id            (PK, Integer)
├── todo_id       (Integer, FK → todolist.id)
├── content       (Text)
└── completed     (Boolean)

email_verifications_scoped
├── email         (PK, String)
├── purpose       (PK, String, signup/reset)
├── code          (String, 6자리)
└── expires_at    (DateTime, 3분 유효)
```

---

## 🚀 시작하기

### 1. 저장소 클론

```bash
git clone https://github.com/your-username/todo-app.git
cd todo-app
```

### 2. 가상환경 & 패키지 설치

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 환경변수 설정

프로젝트 루트에 `.env` 파일 생성 후 아래 내용 입력 ([환경 변수](#-환경-변수) 참고)

### 4. 서버 실행

```bash
uvicorn main:app --reload
```

`main.py`는 호환용 진입점으로 유지했으므로, Render의 기존 Start Command가
`uvicorn main:app ...` 형태라면 변경할 필요가 없습니다. 코드 변경을 서비스에
반영하려면 기존 Render 서비스는 다시 배포해야 합니다. GitHub 자동 배포를 켜둔
경우에는 기본 브랜치에 푸시하면 자동으로 배포됩니다.

### 5. 프론트엔드 접속

인증 검증 업데이트 배포 시 `email_verifications_scoped` 테이블이 자동 생성됩니다.
기존 계정과 할 일은 유지되며, 기존 `email_verifications`의 인증번호는 더 이상
사용하지 않습니다. 배포 전에 인증번호를 받은 사용자는 다시 요청해야 합니다.
구 테이블은 자동 삭제하지 않습니다. 신규 테이블을 만들 수 있는 DB 권한이 필요합니다.

회원가입·비밀번호 변경·재설정에는 공통으로 8자 이상, UTF-8 기준 72바이트 이하의
비밀번호가 필요합니다. 공백만으로 된 비밀번호는 허용하지 않으며, 기존 짧은
비밀번호로의 로그인은 유지됩니다. 잘못된 입력은 422와 문자열 `detail`로 반환합니다.
할 일 삭제 시 하위 항목도 같은 트랜잭션에서 삭제합니다. 기존에 남은 고아 데이터는
이번 배포에서 자동 삭제하지 않습니다.

비밀번호 변경과 계정 삭제의 비밀번호 재확인은 같은 제한을 공유합니다.
계정당 15분에 10회, IP당 15분에 30회까지 허용하며 초과 시 429를 반환합니다.
반복 간격은 1~3650일이며 다음 날짜가 계산 가능한 범위인지 저장 시 검사합니다.

JSON 가져오기는 `POST /todos/import`로 최대 1,000개 항목을 한 번에 복원합니다.
완료 상태·체크리스트·메모·반복 설정과 상대 순서를 유지하고 기존 목록 뒤에 추가합니다.
ID는 새로 발급되며, 형식 오류나 저장 오류가 나면 전체 가져오기를 취소합니다.
브라우저에서는 최대 10MB 파일을 허용합니다. 응답을 받지 못한 경우에는 중복 복원을
피하도록 목록을 먼저 새로고침해 확인하세요.

`index.html`을 브라우저로 열거나,  
VS Code Live Server 등으로 `http://127.0.0.1:5500` 에서 실행

---

## 🔐 환경 변수

`.env` 파일에 아래 항목을 설정하세요.

```env
# 데이터베이스
DATABASE_URL=postgresql://유저:비밀번호@호스트:포트/DB명

# JWT
JWT_SECRET_KEY=your_secret_key_here

# Resend 이메일
RESEND_API_KEY=re_xxxxxxxxxxxx
MAIL_FROM=noreply@yourdomain.com
```

---

## 📡 API 명세

### 인증

| Method | Endpoint | 설명 | 인증 필요 |
|--------|----------|------|-----------|
| `POST` | `/request-code` | 회원가입 인증번호 발송 | ❌ |
| `POST` | `/signup` | 회원가입 | ❌ |
| `POST` | `/login` | 로그인 → JWT 반환 | ❌ |
| `POST` | `/request-reset-code` | 비밀번호 재설정 인증번호 발송 | ❌ |
| `POST` | `/reset-password` | 비밀번호 재설정 | ❌ |

### 투두

| Method | Endpoint | 설명 | 인증 필요 |
|--------|----------|------|-----------|
| `GET` | `/todos` | 내 투두 목록 조회 (서브태스크 포함) | ✅ |
| `POST` | `/todos` | 투두 추가 | ✅ |
| `PATCH` | `/todos/{id}` | 내용·카테고리·우선순위·반복·메모 수정 | ✅ |
| `DELETE` | `/todos/{id}` | 투두 삭제 | ✅ |
| `PATCH` | `/todos/{id}/toggle` | 완료 토글 (반복 시 다음 회차 생성) | ✅ |
| `PATCH` | `/todos/{id}/deadline` | 마감기한 설정 / 제거 | ✅ |
| `POST` | `/todos/reorder` | 순서 저장 (드래그 정렬) | ✅ |

### 서브태스크 / 계정

| Method | Endpoint | 설명 | 인증 필요 |
|--------|----------|------|-----------|
| `POST` | `/todos/{id}/subtasks` | 서브태스크 추가 | ✅ |
| `PATCH` | `/subtasks/{sid}` | 서브태스크 토글 / 수정 | ✅ |
| `DELETE` | `/subtasks/{sid}` | 서브태스크 삭제 | ✅ |
| `POST` | `/change-password` | 비밀번호 변경 | ✅ |
| `DELETE` | `/account` | 계정 삭제 | ✅ |

> ✅ 인증 필요 엔드포인트는 `Authorization: Bearer <token>` 헤더 필요

### 요청 / 응답 예시

**로그인**
```json
// POST /login
{ "username": "hong", "password": "1234" }

// 200 OK
{ "access_token": "eyJhbG..." }
```

**투두 추가**
```json
// POST /todos
{ "content": "알고리즘 공부하기", "deadline": "2025-01-10T18:00" }

// 200 OK
{ "id": 1, "content": "알고리즘 공부하기", "deadline": "2025-01-10T18:00:00" }
```

**마감기한 설정**
```json
// PATCH /todos/1/deadline
{ "deadline": "2025-01-10T18:00" }   // 설정
{ "deadline": null }                  // 제거
```

---

## 🖼 화면 구성

```
┌─────────────────────┐
│  🔑 로그인           │  ← 초기 화면
│  📝 회원가입         │  ← 이메일 인증 포함
│  🔒 비밀번호 재설정  │  ← 이메일 인증 포함
└─────────────────────┘
         ↓ 로그인 성공
┌─────────────────────────────────┐
│  ✓ 나의 투두리스트    [로그아웃] │
│  [ 할 일 입력... ] [+ 등록]      │
│  전체 | 할 일 | 완료 | 마감초과  │
│  타임라인                        │
│  ─────────────────────────────  │
│  ☐ 알고리즘 공부  📅  [삭제]    │
│  ☑ 운동하기       📅  [삭제]    │
│  ⚠️ 보고서 제출   📅  [삭제]    │ ← 마감 초과 (주황)
└─────────────────────────────────┘
```

---

## 📜 라이선스

MIT License © 2025
