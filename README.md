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
| 완료 토글 | 체크박스 클릭으로 완료 처리 |
| 마감기한 설정 | datetime-local picker로 기한 지정 |
| 마감기한 제거 | 기한 제거 버튼 제공 |
| 마감 초과 강조 | 기한 지난 투두는 주황색 배경으로 표시 |

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
├── main.py          # FastAPI 앱 / API 라우터
├── database.py      # SQLAlchemy 모델 / DB 연결
├── requirements.txt # Python 패키지 목록
└── index.html       # 프론트엔드 (단일 HTML 파일)
```

### DB 테이블

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
└── reminder_sent (Boolean)

email_verifications
├── email         (PK, String)
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

### 5. 프론트엔드 접속

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
| `GET` | `/todos` | 내 투두 목록 조회 | ✅ |
| `POST` | `/todos` | 투두 추가 | ✅ |
| `DELETE` | `/todos/{id}` | 투두 삭제 | ✅ |
| `PATCH` | `/todos/{id}/toggle` | 완료 상태 토글 | ✅ |
| `PATCH` | `/todos/{id}/deadline` | 마감기한 설정 / 제거 | ✅ |

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