import os
import uuid
import shutil
import subprocess
import mimetypes
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    import filetype
    HAS_FILETYPE = True
except ImportError:
    HAS_FILETYPE = False

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import pypdfium2 as pdfium
    HAS_PDFIUM = True
except ImportError:
    HAS_PDFIUM = False

app = FastAPI(title="Universal File Converter")

allowed_origins_raw = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173",
)
allowed_origins = [origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()]
allowed_origin_regex = os.getenv("ALLOWED_ORIGIN_REGEX", r"https://.*\.github\.io$")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Conversion format suggestions per category
FORMAT_MAP = {
    "image": ["png", "jpg", "jpeg", "webp", "pdf", "tiff", "tif", "bmp", "gif", "ico"],
    "audio": ["mp3", "wav", "ogg", "flac", "aac", "m4a"],
    "video": ["mp4", "webm", "gif", "avi", "mov", "mkv"],
    "spreadsheet": ["csv", "xlsx", "xls", "pdf"],
    "document": ["pdf", "txt", "odt", "docx", "html", "rtf"],
    "presentation": ["pdf", "pptx", "odp"],
    "pdf": ["png", "jpg", "jpeg", "webp", "txt"],
}

MIME_TO_CATEGORY = {
    "image": "image",
    "audio": "audio",
    "video": "video",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "spreadsheet",
    "application/vnd.ms-excel": "spreadsheet",
    "text/csv": "spreadsheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "application/msword": "document",
    "text/plain": "document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "presentation",
    "application/vnd.ms-powerpoint": "presentation",
}

EXT_TO_CATEGORY = {
    "jpg": "image", "jpeg": "image", "png": "image", "gif": "image",
    "webp": "image", "tiff": "image", "tif": "image", "bmp": "image",
    "mp3": "audio", "wav": "audio", "ogg": "audio", "flac": "audio",
    "aac": "audio", "m4a": "audio", "wma": "audio",
    "mp4": "video", "webm": "video", "avi": "video", "mov": "video",
    "mkv": "video", "wmv": "video", "flv": "video",
    "csv": "spreadsheet", "xlsx": "spreadsheet", "xls": "spreadsheet",
    "docx": "document", "doc": "document", "txt": "document", "odt": "document",
    "pptx": "presentation", "ppt": "presentation", "odp": "presentation",
    "pdf": "pdf",
}

EXT_ALIASES = {
    "jpeg": "jpg",
    "tif": "tiff",
}


def normalize_ext(ext: str) -> str:
    clean = ext.lower().lstrip(".")
    return EXT_ALIASES.get(clean, clean)


def detect_category(filename: str, mime: Optional[str]) -> str:
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext in EXT_TO_CATEGORY:
        return EXT_TO_CATEGORY[ext]
    if mime:
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("audio/"):
            return "audio"
        if mime.startswith("video/"):
            return "video"
        if mime in MIME_TO_CATEGORY:
            return MIME_TO_CATEGORY[mime]
    return "unknown"


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    category: str
    mime_type: str
    suggestions: List[str]


class ConvertRequest(BaseModel):
    file_id: str
    filename: str
    target_format: str


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix
    save_path = UPLOAD_DIR / f"{file_id}{ext}"

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Detect MIME
    mime = file.content_type or ""
    if HAS_FILETYPE:
        kind = filetype.guess(str(save_path))
        if kind:
            mime = kind.mime

    if not mime or mime == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(file.filename)
        if guessed:
            mime = guessed

    category = detect_category(file.filename, mime)
    suggestions = FORMAT_MAP.get(category, [])

    # Remove same format as input
    input_ext = normalize_ext(Path(file.filename).suffix.lstrip("."))
    suggestions = [s for s in suggestions if normalize_ext(s) != input_ext]

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        category=category,
        mime_type=mime,
        suggestions=suggestions,
    )


@app.post("/convert")
async def convert_file(req: ConvertRequest):
    # Find uploaded file
    input_ext = Path(req.filename).suffix
    input_path = UPLOAD_DIR / f"{req.file_id}{input_ext}"

    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Upload not found")

    category = detect_category(req.filename, None)
    target_raw = req.target_format.lower().lstrip(".")
    target = normalize_ext(target_raw)
    output_ext = target_raw
    output_filename = Path(req.filename).stem + f".{output_ext}"
    output_path = OUTPUT_DIR / f"{req.file_id}_{output_filename}"

    allowed_targets = {normalize_ext(fmt) for fmt in FORMAT_MAP.get(category, [])}
    if target not in allowed_targets:
        raise HTTPException(
            status_code=400,
            detail=f"Target .{target_raw} is not supported for {category}",
        )

    try:
        if category == "image":
            convert_image(input_path, output_path, target)
        elif category in ("audio", "video"):
            convert_media(input_path, output_path, target)
        elif category == "spreadsheet":
            convert_spreadsheet(input_path, output_path, target)
        elif category in ("document", "presentation"):
            convert_office(input_path, output_path, target)
        elif category == "pdf":
            convert_pdf(input_path, output_path, target)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported category: {category}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")

    if not output_path.exists():
        raise HTTPException(status_code=500, detail="Conversion produced no output file")

    return FileResponse(
        path=str(output_path),
        filename=output_filename,
        media_type="application/octet-stream",
    )


def convert_image(src: Path, dst: Path, target: str):
    if not HAS_PILLOW:
        raise RuntimeError("Pillow not installed")
    img = Image.open(src)
    if target == "jpg":
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        img.save(dst, "JPEG", quality=95)
    elif target == "pdf":
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        img.save(dst, "PDF")
    else:
        fmt_map = {"webp": "WEBP", "png": "PNG", "tiff": "TIFF", "bmp": "BMP", "gif": "GIF", "ico": "ICO"}
        fmt = fmt_map.get(target, target.upper())
        img.save(dst, fmt)


def convert_media(src: Path, dst: Path, target: str):
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), str(dst)],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr[-500:]}")


def convert_spreadsheet(src: Path, dst: Path, target: str):
    if not HAS_PANDAS:
        raise RuntimeError("pandas not installed")
    ext = src.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(src)
    else:
        df = pd.read_excel(src)

    if target == "csv":
        df.to_csv(dst, index=False)
    elif target == "xlsx":
        df.to_excel(dst, index=False)
    elif target == "pdf":
        convert_office(src, dst, "pdf")
    else:
        raise RuntimeError(f"Unsupported spreadsheet target: {target}")


def convert_office(src: Path, dst: Path, target: str):
    fmt_map = {
        "pdf": "pdf", "txt": "txt", "odt": "odt",
        "docx": "docx", "html": "html", "odp": "odp",
        "pptx": "pptx", "csv": "csv", "xlsx": "xlsx",
    }
    lo_format = fmt_map.get(target, target)
    result = subprocess.run(
        ["libreoffice", "--headless", "--convert-to", lo_format,
         "--outdir", str(dst.parent), str(src)],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice error: {result.stderr[-500:]}")

    # LibreOffice names output based on input stem
    expected = dst.parent / (src.stem + f".{lo_format}")
    if expected.exists() and expected != dst:
        expected.rename(dst)


def convert_pdf(src: Path, dst: Path, target: str):
    if target in ("png", "jpg"):
        if convert_pdf_with_poppler(src, dst, target):
            return
        if convert_pdf_with_pdfium(src, dst, target):
            return
        raise RuntimeError(
            "No PDF-to-image backend available. Install poppler (pdftoppm) or pypdfium2."
        )
    elif target == "webp":
        if convert_pdf_with_pdfium(src, dst, target):
            return
        raise RuntimeError("PDF to WEBP requires pypdfium2.")
    elif target == "txt":
        result = subprocess.run(
            ["pdftotext", str(src), str(dst)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise RuntimeError(f"pdftotext error: {result.stderr}")
    else:
        raise RuntimeError(f"Unsupported PDF target: {target}")


def convert_pdf_with_poppler(src: Path, dst: Path, target: str) -> bool:
    try:
        poppler_target = "jpeg" if target == "jpg" else target
        prefix = dst.parent / dst.stem
        result = subprocess.run(
            ["pdftoppm", "-r", "150", "-singlefile", f"-{poppler_target}", str(src), str(prefix)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return False
        candidates = [dst.parent / f"{dst.stem}.{target}"]
        if target == "jpg":
            candidates.append(dst.parent / f"{dst.stem}.jpeg")
        for candidate in candidates:
            if candidate.exists():
                if candidate != dst:
                    candidate.replace(dst)
                return True
    except FileNotFoundError:
        return False
    return False


def convert_pdf_with_pdfium(src: Path, dst: Path, target: str) -> bool:
    if not HAS_PDFIUM:
        return False
    pdf = None
    try:
        pdf = pdfium.PdfDocument(str(src))
        if len(pdf) == 0:
            raise RuntimeError("PDF has no pages")
        page = pdf[0]
        pil_image = page.render(scale=2).to_pil()
        if target == "jpg":
            if pil_image.mode in ("RGBA", "LA", "P"):
                pil_image = pil_image.convert("RGB")
            pil_image.save(dst, "JPEG", quality=92)
        elif target == "png":
            pil_image.save(dst, "PNG")
        elif target == "webp":
            pil_image.save(dst, "WEBP", quality=90)
        else:
            return False
        return True
    except Exception:
        return False
    finally:
        if pdf is not None:
            pdf.close()


app.mount("/static", StaticFiles(directory="static"), name="static")
