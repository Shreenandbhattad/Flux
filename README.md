# Flux - Universal File Converter

A web-based file conversion tool built with FastAPI. Upload any supported file, pick a target format, and download the result.

## Supported Conversions

| Category     | Input                      | Output                        |
|--------------|----------------------------|-------------------------------|
| Image        | jpg, png, webp, tiff, bmp  | jpg, png, webp, pdf, tiff, bmp|
| Audio        | mp3, wav, ogg, flac, aac   | mp3, wav, ogg, flac, aac      |
| Video        | mp4, webm, avi, mov, mkv   | mp4, webm, gif, avi, mov, mkv |
| Spreadsheet  | csv, xlsx                  | csv, xlsx, pdf                |
| Document     | docx, doc, odt, txt        | pdf, txt, odt, docx           |
| Presentation | pptx, ppt, odp             | pdf, odp, pptx                |
| PDF          | pdf                        | png, jpg, txt                 |

## Quick Start (Docker)

```bash
docker-compose up --build
```

Then open: http://localhost:8000

## Manual Setup

### Prerequisites

- Python 3.9+
- ffmpeg
- LibreOffice
- poppler-utils (`pdftoppm`, `pdftotext`)

### Install

```bash
pip install -r requirements.txt
```

### Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000

## Deploy Frontend on GitHub Pages

This project includes a static frontend in `docs/` for GitHub Pages.

1. Push repo to GitHub.
2. In GitHub repo settings: `Pages -> Build and deployment -> Deploy from a branch`.
3. Select branch: `main` and folder: `/docs`.
4. Edit `docs/config.js` and set:

```js
window.FLUX_API_BASE = "https://your-backend-url";
```

5. Commit and push.

## Deploy Backend (Free Option)

GitHub Pages cannot run FastAPI/Python backend code. You must host backend separately.

Recommended free option: deploy backend on Render.

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Optional environment variables:

- `ALLOWED_ORIGINS`:
  `http://localhost:8000,http://127.0.0.1:8000`
- `ALLOWED_ORIGIN_REGEX`:
  `https://<your-github-username>\\.github\\.io$`

## API

### POST /upload

Upload a file for detection.

**Request:** `multipart/form-data` with `file` field

**Response:**
```json
{
  "file_id": "uuid",
  "filename": "example.png",
  "category": "image",
  "mime_type": "image/png",
  "suggestions": ["jpg", "webp", "pdf", "tiff", "bmp"]
}
```

### POST /convert

Convert an uploaded file.

**Request:**
```json
{
  "file_id": "uuid",
  "filename": "example.png",
  "target_format": "jpg"
}
```

**Response:** Binary file download

## Architecture

```
universal-converter/
├── main.py              # FastAPI backend
├── static/
│   └── index.html       # Single-page frontend
├── uploads/             # Temporary upload storage
├── outputs/             # Temporary output storage
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

### Conversion Engines

| Category     | Tool                    |
|--------------|-------------------------|
| Images       | Pillow                  |
| Audio/Video  | ffmpeg                  |
| Spreadsheets | pandas + openpyxl       |
| Documents    | LibreOffice (headless)  |
| PDF → image  | poppler (pdftoppm)      |
| PDF → text   | poppler (pdftotext)     |

## Production Deployment

```bash
# With nginx reverse proxy
nginx -c /etc/nginx/nginx.conf
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 4
```

Future additions: rate limiting, auth, antivirus scanning, cloud storage, batch conversion.
