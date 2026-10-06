# OneForAll - FastAPI Backend Service & BiRefNet AI Background Removal

Kiến trúc backend hiện đại, mở rộng được (clean layered architecture) dựa trên **FastAPI**, **SQLAlchemy 2.0 (Async)**, **Alembic**, **Pydantic v2**, và hệ thống tách nền AI **BiRefNet-Lite**.

---

## 📁 Cấu Trúc Dự Án (Project Structure)

```text
OneForAll/
├── app/
│   ├── api/
│   │   ├── deps.py                 # Dependencies (DB session, Auth token, Current User)
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── bg_removal.py   # AI Remove Background endpoint (/api/v1/remove-bg)
│   │       │   ├── health.py       # Health check API & GPU/Model status (/health, /api/v1/health)
│   │       │   └── users.py        # User CRUD API routes
│   │       ├── router.py           # V1 main router aggregator
│   │       └── __init__.py
│   ├── core/
│   │   ├── config.py               # Pydantic Settings & environment variables
│   │   ├── database.py             # SQLAlchemy Async Engine, Base & Session
│   │   ├── exceptions.py           # Custom HTTP & App exceptions
│   │   ├── security.py             # Password hashing (bcrypt) & JWT helpers
│   │   └── __init__.py
│   ├── models/
│   │   ├── base.py                 # TimestampMixin & base model classes
│   │   ├── user.py                 # User ORM model
│   │   └── __init__.py
│   ├── repositories/
│   │   ├── base.py                 # Generic BaseRepository CRUD operations
│   │   ├── user_repository.py      # UserRepository
│   │   └── __init__.py
│   ├── schemas/
│   │   ├── common.py               # Standard response & pagination schemas
│   │   ├── user.py                 # User request/response DTOs & token schemas
│   │   └── __init__.py
│   ├── services/
│   │   ├── bg_removal_service.py   # AI Service: BiRefNet-Lite inference & Image processing
│   │   ├── user_service.py         # Business logic layer
│   │   └── __init__.py
│   ├── utils/
│   │   ├── logger.py               # Centralized logging configuration
│   │   └── __init__.py
│   ├── main.py                     # FastAPI application entry point, lifespan & CORS
│   └── __init__.py
├── migrations/                     # Alembic database migrations
│   ├── versions/
│   │   └── .gitkeep
│   ├── env.py                      # Async migration runner
│   └── script.py.mako              # Migration file template
├── tests/                          # Automated tests with pytest
│   ├── api/
│   │   ├── test_bg_removal.py      # Test validation cho endpoint remove-bg
│   │   ├── test_health.py          # Test kiểm tra endpoint health
│   │   └── test_users.py           # Test tích hợp CRUD users
│   ├── conftest.py                 # In-memory SQLite & AsyncClient fixtures
│   └── __init__.py
├── .env.example                    # Sample environment variables
├── .env                            # Local environment variables
├── .gitignore                      # Git ignore file
├── alembic.ini                     # Alembic migration configuration
├── docker-compose.yml              # Docker Compose (API + PostgreSQL)
├── Dockerfile                      # Production Docker container
├── pyproject.toml                  # Project metadata & pytest configuration
├── requirements.txt                # Production & development dependencies
└── README.md                       # Project documentation
```

---

## 🎨 Tính Năng Tách Nền AI (BiRefNet-Lite)

- **Mô hình**: `ZhengPeng7/BiRefNet_lite`
- **Tự động nhận diện phần cứng**: Tự động sử dụng `CUDA` (GPU) nếu khả dụng, ngược lại dùng `CPU`.
- **Hỗ trợ ảnh EXIF**: Tự động xoay ảnh đúng chiều theo metadata EXIF từ điện thoại.
- **Nén PNG tối ưu**: Sử dụng `compress_level=1` giúp xuất ảnh nhanh gấp 3-5 lần.
- **Worker Threadpool**: Endpoint tách nền chạy trên worker threadpool của FastAPI tránh nghẽn luồng asyncio.

### Endpoint:
- `POST /api/v1/remove-bg`: Tải lên file ảnh (`multipart/form-data` với key `file`), trả về ảnh PNG có nền trong suốt (`image/png`).

---

## 🔄 Dịch Vụ Chuyển Đổi Định Dạng (File & Document Converter)

Hỗ trợ chuyển đổi đa định dạng hình ảnh và tài liệu:

| Chuyển đổi | Endpoint | Phương thức | Output Media-Type | Ghi chú |
|---|---|---|---|---|
| **PNG ➔ SVG** | `/api/v1/convert/png-to-svg` | `POST` | `image/svg+xml` | Vector hóa ảnh qua `vtracer`, hỗ trợ color/binary, spline/polygon |
| **DOC/DOCX ➔ PDF** | `/api/v1/convert/doc-to-pdf` | `POST` | `application/pdf` | Chuyển đổi DOCX chuẩn A4, hỗ trợ bảng biểu, hình ảnh |
| **TXT ➔ PDF** | `/api/v1/convert/txt-to-pdf` | `POST` | `application/pdf` | Hỗ trợ đầy đủ font Tiếng Việt có dấu, phân trang chuẩn |
| **TXT ➔ DOC/DOCX** | `/api/v1/convert/txt-to-doc` | `POST` | `application/vnd.openxmlformats-officedocument...` | Xuất file Microsoft Word (.docx) |
| **XLSX ➔ CSV** | `/api/v1/convert/xlsx-to-csv` | `POST` | `text/csv` | Mã hóa UTF-8 with BOM tương thích 100% tiếng Việt trên Excel |
| **XLSX ➔ JSON** | `/api/v1/convert/xlsx-to-json` | `POST` | `application/json` | Trích xuất dạng JSON Array hoặc tải file đính kèm |
| **PNG ➔ JPG/JPEG** | `/api/v1/convert/png-to-jpg` | `POST` | `image/jpeg` | Xử lý vùng trong suốt (alpha) bằng nền màu tùy chọn |
| **JPG ➔ WEBP** | `/api/v1/convert/jpg-to-webp` | `POST` | `image/webp` | Nén WEBP thế hệ mới với tùy chọn chất lượng & lossless |


---

## 🚀 Hướng Dẫn Cài Đặt & Chạy

### 1. Kích hoạt môi trường ảo (Virtualenv)

Trên Windows (PowerShell):
```powershell
.venv\Scripts\Activate.ps1
```

Trên Linux / macOS:
```bash
source .venv/bin/activate
```

### 2. Cài đặt thư viện dependencies

```bash
pip install -r requirements.txt
```

*(Lưu ý: Nếu dùng GPU NVIDIA, cài đặt PyTorch hỗ trợ CUDA phù hợp từ [pytorch.org](https://pytorch.org))*

### 3. Cấu hình biến môi trường

```bash
cp .env.example .env
```

### 4. Chạy ứng dụng nhanh (Quick Start)

Dự án đã tích hợp sẵn lệnh chạy trọn gói (FastAPI + Celery Worker + Celery Beat dọn dẹp file tự động):

#### Cách 1: Chạy bằng 1 lệnh duy nhất (Khuyên dùng trên Windows)
```cmd
start.bat
```
hoặc bằng PowerShell:
```powershell
.\start.ps1
```
hoặc bằng Python CLI trực tiếp:
```bash
python run.py
```
*(Script sẽ tự động khởi chạy FastAPI, Celery Worker và Celery Beat. Khi muốn dừng, chỉ cần nhấn `Ctrl + C` để dừng toàn bộ an toàn).*

#### Cách 2: Chạy từng service riêng biệt
```bash
python run.py api        # Chỉ chạy FastAPI Web Server (Uvicorn)
python run.py worker     # Chỉ chạy Celery Worker (tự động cấu hình solo pool trên Windows)
python run.py beat       # Chỉ chạy Celery Beat (scheduler dọn dẹp file R2 hết hạn)
python run.py test       # Chạy nhanh bộ test tự động (pytest)
```

#### Cách 3: Chạy toàn bộ hệ thống bằng Docker Compose
```bash
docker compose up --build
# Hoặc: python run.py docker
```

---

### 5. Tài liệu API (Interactive Docs)

Truy cập tài liệu API tự động:
- **Swagger UI**: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- **ReDoc**: [http://localhost:8000/api/v1/redoc](http://localhost:8000/api/v1/redoc)
- **Health check**: [http://localhost:8000/health](http://localhost:8000/health)