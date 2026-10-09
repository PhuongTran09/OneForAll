# OneForAll - FastAPI Backend Service & Multi-Format Media Processing

Kiến trúc backend hiện đại, mở rộng được (clean layered architecture) dựa trên **FastAPI**, **Supabase Auth & Supabase PostgreSQL (PostgREST)**, **Pydantic v2**, **Celery + Redis**, **Cloudflare R2 Storage**, hệ thống xử lý Media (**yt-dlp**, **FFmpeg**), và tách nền AI **BiRefNet**.

---

## 📁 Cấu Trúc Dự Án (Project Structure)

```text
OneForAll/
├── app/
│   ├── api/
│   │   ├── deps.py                 # Dependencies (Supabase JWT auth ES256/HS256, CurrentUser)
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── convert_file.py # Chuyển đổi tài liệu & file (/api/v1/convert-file, /convert)
│   │       │   ├── files.py        # Quản lý R2, presigned URLs, streaming download & /consumed
│   │       │   ├── health.py       # Health check API & GPU/Model status (/health, /api/v1/health)
│   │       │   ├── image.py        # Xử lý hình ảnh (resize, compress, crop, remove_bg)
│   │       │   ├── jobs.py         # Tra cứu tiến độ Job (/api/v1/jobs/{id})
│   │       │   ├── media.py        # Xử lý media/video/audio & URL YouTube/TikTok (/api/v1/media/process)
│   │       │   ├── payments.py     # Thanh toán PayOS & Webhook (/api/v1/payments/*)
│   │       │   └── users.py        # User & Profile CRUD API routes (/api/v1/users)
│   │       ├── router.py           # V1 main router aggregator
│   │       └── __init__.py
│   ├── core/
│   │   ├── config.py               # Pydantic Settings & Supabase/R2/Redis configuration
│   │   ├── exceptions.py           # Custom HTTP & App exceptions
│   │   ├── security.py             # Supabase JWT token verification (hỗ trợ ES256 JWKS & HS256)
│   │   ├── supabase.py             # Async & Sync Supabase PostgREST clients
│   │   └── __init__.py
│   ├── models/
│   │   ├── base.py                 # Pydantic base models & TimestampMixin
│   │   ├── job.py                  # Job & JobStatus domain models
│   │   ├── user.py                 # User & Profile domain models (Supabase auth.users UUID)
│   │   └── __init__.py
│   ├── repositories/
│   │   ├── base.py                 # Generic BaseRepository PostgREST operations
│   │   ├── job_repository.py       # JobRepository (hỗ trợ get, create, update, delete)
│   │   ├── user_repository.py      # UserRepository (PostgREST profiles)
│   │   └── __init__.py
│   ├── schemas/
│   │   ├── common.py               # Standard response & pagination schemas
│   │   ├── file.py                 # Presigned URL schemas
│   │   ├── job.py                  # Job request/response DTOs
│   │   ├── payment.py              # PayOS payment schemas
│   │   ├── user.py                 # User request/response DTOs
│   │   └── __init__.py
│   ├── services/
│   │   ├── file_converter_service.py # Core CPU document & vector conversions
│   │   ├── format_detector.py      # Nhận diện tự động MIME type, extension, file signature
│   │   ├── job_service.py          # Background Job management & enqueue service
│   │   ├── payment_service.py      # PayOS payment service
│   │   ├── storage_service.py      # Cloudflare R2 / S3 storage service (stream, delete, presigned)
│   │   ├── subscription_service.py # Kiểm tra hạn mức người dùng
│   │   ├── task_queue_service.py   # Celery queue dispatching
│   │   ├── user_service.py         # User profile management service
│   │   └── __init__.py
│   ├── worker/                     # Celery background workers
│   │   ├── celery_app.py           # Celery queues, routing & Beat scheduler
│   │   ├── lifecycle.py            # Quản lý persistent worker event loop
│   │   ├── processors/             # Core workload processors
│   │   │   ├── base.py
│   │   │   ├── document.py         # Document & vector processor
│   │   │   ├── gpu.py              # BiRefNet GPU processor
│   │   │   ├── image.py            # Pillow image processor
│   │   │   └── video.py            # FFmpeg & yt-dlp media processor (impersonation)
│   │   └── tasks/
│   │       ├── cleanup.py          # Định kỳ dọn dẹp R2 output & DELETE job hết hạn (1 phút/lần)
│   │       ├── convert.py          # Document convert worker task
│   │       ├── gpu.py              # AI GPU background removal task
│   │       ├── image.py            # Image processing task
│   │       └── video.py            # Video & URL download task (YouTube, TikTok)
│   ├── utils/
│   │   ├── logger.py               # Centralized logging configuration
│   │   └── __init__.py
│   ├── main.py                     # FastAPI entry point, lifespan, CORS & routers
│   └── __init__.py
├── supabase/                       # Supabase database schemas & triggers
│   └── schema.sql                  # DDL for public.profiles, public.jobs, RLS & triggers
├── tests/                          # Automated tests with pytest (69+ tests passed)
│   ├── api/
│   │   ├── test_auth.py            # Test Supabase JWT verification
│   │   ├── test_bg_removal.py      # Test validation cho endpoint remove-bg
│   │   ├── test_convert_autodetect.py # Test tự động nhận diện định dạng nguồn
│   │   ├── test_converter.py       # Test API chuyển đổi định dạng
│   │   ├── test_health.py          # Test kiểm tra endpoint health
│   │   ├── test_image_video_multipart.py # Test multipart upload cho image và media
│   │   ├── test_storage_optimization.py # Test tối ưu storage: stream download, abort retry, TTL
│   │   └── test_users.py           # Test CRUD users với Supabase profiles & UUID
│   ├── conftest.py                 # In-memory Supabase PostgREST/Auth mock fixtures
│   ├── test_convert_worker.py      # Test Celery conversion & cleanup task
│   ├── test_processors.py          # Test các processors (vtracer, yt-dlp, ffmpeg, birefnet)
│   ├── test_storage_service.py     # Test Cloudflare R2 storage service
│   ├── test_worker_lifecycle.py    # Test persistent event loop lifecycle
│   └── test_workers_queues.py      # Test Celery queues routing
├── API_TEST_CASES.txt              # Danh sách cURL test cases mẫu toàn bộ API
├── .env.example                    # Sample environment variables
├── pyproject.toml                  # Project metadata & dependencies
├── requirements.txt                # Production dependencies
└── README.md                       # Tài liệu dự án
```

---

## 🏗️ Kiến Trúc Hệ Thống (Architecture & Workflows)

Hệ thống tuân thủ kiến trúc **R2 → Worker SSD → Processor → SSD → R2**, loại bỏ hoàn toàn việc nạp file lớn vào RAM:

```text
Client
  ↓
Presigned Upload URL / Stream Upload
  ↓
Cloudflare R2 (uploads/{job_id}/original.{ext})
  ↓
FastAPI (chỉ nhận input_key / stream fileobj trực tiếp, không buffer toàn bộ vào RAM)
  ↓
Create Job → Celery / Redis
  ↓
Worker: Download streaming từ R2 về SSD cục bộ
  /tmp/oneforall/{job_id}/input.{ext}
  ↓
Processor: Nhận file path trực tiếp trên SSD
  FFmpeg / Pillow / Document / BiRefNet GPU
  ↓
Kết quả ghi trực tiếp ra SSD:
  /tmp/oneforall/{job_id}/output.{ext}
  ↓
Upload multipart / stream từ SSD lên Cloudflare R2:
  outputs/{job_id}/result.{ext}
  ↓
Xóa file input gốc trên R2 (nếu có)
  ↓
Dọn dẹp triệt để thư mục tạm trên SSD (/tmp/oneforall/{job_id}/) qua block `finally`
```

### ⚙️ Quy Tắc Quản Lý Tài Nguyên & Concurrency

- **Isolated Job Workspace**: Mỗi job sở hữu một thư mục SSD riêng biệt:
  ```text
  /tmp/oneforall/{job_id}/
  ├── input.{ext}
  ├── output.{ext}
  └── work/
  ```
- **SSD Cleanup**: Luôn được dọn dẹp bằng `try ... finally: cleanup_job_temp_dir(job_id)` bất kể job thành công hay thất bại.
- **Disk Free Space Check**: Tự động kiểm tra dung lượng ổ đĩa khả dụng trước khi xử lý file lớn để tránh tràn SSD.
- **Zero Full-File Memory Loading**:
  - Không dùng `await file.read()` nạp cả file vào RAM (chỉ đọc 4KB header để nhận diện định dạng, sau đó stream trực tiếp bằng `upload_fileobj`).
  - Không dùng `with open(...) as f: f.read()` đối với processor outputs.
  - Processors nhận và trả file path (`process_file(input_path, output_path)`).
- **Hàng đợi & Concurrency Celery**:
  - `convert`: Document & vector conversion (`vtracer`, `docx`, `openpyxl`).
  - `image`: Xử lý ảnh Pillow (resize, compress, format convert).
  - `video`: Xử lý video/audio FFmpeg & tải/trích xuất từ URL bằng `yt-dlp` + `curl-cffi` (giả lập Chrome).
  - `gpu`: Tách nền AI `BiRefNet` trên GPU CUDA (mặc định worker concurrency = 1 tránh OOM VRAM).

---

## 💾 Chính Sách Tối Ưu Storage (R2 & Database TTL)

Nhằm tối ưu chi phí lưu trữ Cloudflare R2, băng thông và dung lượng đĩa:

```text
Temporary & Intermediate files
    → Chỉ lưu cục bộ trong /tmp/oneforall/{job_id}/ của worker SSD
    → Xóa sạch ngay lập tức qua block `finally` (không bao giờ đẩy lên R2)

Final Output
    → Lưu tại: outputs/{job_id}/result.{ext}
    → Thời hạn tối đa: 3 phút (expires_at)
    → User tải trực tiếp qua stream thành công (100%):
          ↳ Xóa ngay output trên R2
          ↳ DELETE job khỏi Database
    → User ngắt kết nối / tải dở giữa chừng (disconnect, abort):
          ↳ Giữ nguyên file trên R2 và job trong DB để user retry trong 3 phút
    → User không tải:
          ↳ Celery Beat quét định kỳ mỗi 1 phút:
          ↳ Xóa output trên R2 và DELETE job khỏi Database

Failed Jobs (status = 'failed')
    → Giữ lại 5 phút để client/user tra cứu thông tin lỗi qua GET /api/v1/jobs/{job_id}
    → Sau 5 phút (expires_at = completed_at + 5m):
          ↳ Celery Beat quét định kỳ mỗi 1 phút:
          ↳ Dọn dẹp file R2 tồn đọng (nếu có)
          ↳ DELETE bản ghi job khỏi Database

Presigned URL Download:
    → Client có thể gọi POST /api/v1/files/{job_id}/consumed sau khi tải xong để dọn dẹp ngay.
```

---

## 🔄 Các Tính Năng Chuyển Đổi Hỗ Trợ

1. **Media Processing (`/api/v1/media/process`)**:
   - **YouTube sang MP3**: Trích xuất âm thanh từ link YouTube bằng `yt-dlp`.
   - **YouTube sang MP4**: Tải video chất lượng cao từ YouTube.
   - **TikTok sang MP3 / MP4**: Vượt qua bot-detection của TikTok qua `curl-cffi` browser impersonation (`chrome`).
   - **Video Transcode**: Chuyển mã MP4, MKV, AVI, WEBM qua FFmpeg (libx264, aac, tuỳ chỉnh CRF).
   - **Extract Audio**: Tách audio từ file video sang MP3, WAV, AAC.
   - **Thumbnail Extraction**: Cắt ảnh đại diện từ video tại timestamp bất kỳ.

2. **File & Document Conversion (`/api/v1/convert-file`, `/convert`)**:
   - Tự động nhận diện định dạng nguồn (không cần gửi tham số `from`).
   - `PNG ➔ SVG`: Vector hóa bằng thuật toán `vtracer`.
   - `DOC/DOCX ➔ PDF`: Chuyển đổi DOCX sang PDF chuẩn khổ A4.
   - `TXT ➔ PDF`: Xuất PDF hỗ trợ font Unicode tiếng Việt.
   - `TXT ➔ DOC/DOCX`: Xuất tài liệu Microsoft Word (.docx).
   - `XLSX ➔ CSV`: UTF-8 with BOM tương thích Excel tiếng Việt.
   - `XLSX ➔ JSON`: Trích xuất dữ liệu bảng tính sang JSON array.

3. **Image Processing (`/api/v1/image/process`)**:
   - Nén ảnh (compress chất lượng tuỳ chọn).
   - Thay đổi kích thước (resize giữ tỉ lệ aspect ratio).
   - Cắt ảnh (crop) và đổi định dạng (PNG, JPG, WEBP).
   - Tách nền ảnh tự động bằng AI BiRefNet.

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
pip install -U yt-dlp curl-cffi
```

*(Lưu ý: Đảm bảo máy tính đã cài đặt `ffmpeg` và có trong biến môi trường `PATH`).*

### 3. Cấu hình biến môi trường (.env)

```bash
cp .env.example .env
```
Điền các giá trị:
- `SUPABASE_URL`: `https://<project-ref>.supabase.co`
- `SUPABASE_KEY`: Anon/public API key
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key bí mật
- `SUPABASE_JWT_SECRET`: (Tuỳ chọn) Secret HS256 nếu có
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`: Cấu hình Cloudflare R2
- `CELERY_BROKER_URL`: `redis://localhost:6379/0`
- `CELERY_RESULT_BACKEND`: `redis://localhost:6379/1`

### 4. Khởi chạy ứng dụng

#### Chạy toàn bộ bằng lệnh độc lập (Khuyên dùng khi test local):
```powershell
# 1. Khởi chạy Redis Broker (nếu dùng Docker):
docker run -d -p 6379:6379 redis:alpine

# 2. Khởi chạy Celery Worker (trên Windows dùng solo pool):
celery -A app.worker.celery_app worker -Q convert,image,video,gpu -l info -P solo

# 3. Khởi chạy Celery Beat (Scheduler dọn dẹp file 1 phút/lần):
celery -A app.worker.celery_app beat -l info

# 4. Khởi chạy FastAPI Backend:
uvicorn app.main:app --reload --port 8000
```

---

## 🧪 Kiểm Thử Tự Động & Thủ Công

### 1. Chạy Automated Tests (Pytest)
```powershell
pytest -v
```
Toàn bộ **69 test cases** bao gồm unit test, component test, multipart endpoint test, mock YouTube/TikTok URL processing, stream retry & storage optimization đều chạy tự động.

### 2. Danh Sách Lệnh cURL Test Thủ Công
Xem chi tiết file [**`API_TEST_CASES.txt`**](API_TEST_CASES.txt) để copy-paste các lệnh cURL test cho từng chức năng:
- Health check & Profile
- YouTube sang MP3 / MP4
- TikTok sang MP3 / MP4
- Upload Video, Extract Audio, Thumbnail
- Chuyển đổi DOCX, PNG sang SVG, XLSX
- Nén ảnh, Resize ảnh, Tách nền AI
- Tải file Stream (`?direct=true`) & Xác nhận consumed

---

## 📚 Tài Liệu API Trực Quan (Interactive Docs)

Sau khi server khởi động:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
