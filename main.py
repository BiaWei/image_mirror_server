from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from image_process import process_animated_image_combined, process_static_image
import io
import os
import time
import uuid
import shutil
from typing import Optional, Dict
from datetime import datetime, timedelta
import asyncio
from collections import defaultdict
from PIL import Image, ExifTags

# Lifespan 上下文管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up...")
    cleanup_task = None
    try:
        if not os.path.exists(TEMP_DIR):
            os.makedirs(TEMP_DIR)

        async def periodic_cleanup():
            while True:
                file_manager.clean_expired_files()
                await asyncio.sleep(FILE_EXPIRY_MINUTES * 60)

        cleanup_task = asyncio.create_task(periodic_cleanup())
        yield
    finally:
        print("Shutting down...")
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)


app = FastAPI(lifespan=lifespan)

HTML_DIR = "html"
INDEX_FILE = "index.html"
TEMP_DIR = "temp"
MAX_REQUESTS_PER_MINUTE = 30
FILE_EXPIRY_MINUTES = 30
MAX_FILE_SIZE_MB = 10

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"]
)


class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)

    def is_rate_limited(self, client_id: str) -> bool:
        current_time = time.time()
        minute_ago = current_time - 60
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if req_time > minute_ago
        ]
        return len(self.requests[client_id]) >= MAX_REQUESTS_PER_MINUTE

    def add_request(self, client_id: str):
        self.requests[client_id].append(time.time())


rate_limiter = RateLimiter()


class FileManager:
    def __init__(self):
        self.base_temp_dir = TEMP_DIR
        self.ensure_base_dir()
        self.user_dirs: Dict[str, datetime] = {}

    def ensure_base_dir(self):
        if not os.path.exists(self.base_temp_dir):
            os.makedirs(self.base_temp_dir)

    def get_user_dir(self, user_id: str) -> str:
        user_dir = os.path.join(self.base_temp_dir, user_id)
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)
        self.user_dirs[user_id] = datetime.now()
        return user_dir

    def clean_expired_files(self):
        current_time = datetime.now()
        expired_users = []
        for user_id, last_access in self.user_dirs.items():
            if current_time - last_access > timedelta(minutes=FILE_EXPIRY_MINUTES):
                user_dir = os.path.join(self.base_temp_dir, user_id)
                if os.path.exists(user_dir):
                    shutil.rmtree(user_dir)
                expired_users.append(user_id)
        for user_id in expired_users:
            del self.user_dirs[user_id]


file_manager = FileManager()


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    if rate_limiter.is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    rate_limiter.add_request(client_ip)
    response = await call_next(request)
    return response


@app.post("/process-image")
async def process_image(
        request: Request,
        file: UploadFile = File(...),
        horizontal_crop_percent: int = Form(...),
        vertical_crop_percent: int = Form(...),
        selected_side: str = Form(...)
):
    if selected_side == "right" or selected_side == "q2" or selected_side == "q3":
        horizontal_crop_percent = 100 - horizontal_crop_percent
    if selected_side == "down" or selected_side == "q3" or selected_side == "q4":
        vertical_crop_percent = 100 - vertical_crop_percent

    try:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"文件大小超过最大限制 {MAX_FILE_SIZE_MB}MB")

        user_id = str(uuid.uuid4())
        user_dir = file_manager.get_user_dir(user_id)

        # 更智能的文件类型检测
        try:
            # 尝试从文件内容判断真正的文件类型
            image = Image.open(io.BytesIO(content))

            # 获取真实的图像格式
            actual_format = image.format.lower()
            print(f"实际图像格式: {actual_format}")

            # 为输出文件选择正确的扩展名
            output_filename = f"processed_image.{actual_format.lower()}"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"无法打开图像: {str(e)}")

        output_path = os.path.join(user_dir, output_filename)

        is_animated = getattr(image, "is_animated", False)
        print(f"Processing image. Is animated: {is_animated}")

        if is_animated or actual_format == 'gif':
            frames, durations, disposal_methods = process_animated_image_combined(image, horizontal_crop_percent,
                                                                                  vertical_crop_percent, selected_side)

            # 保存动画 GIF
            frames[0].save(
                output_path,
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                # transparency=frames[0].info['transparency'],
                disposal=2,
                loop=0
            )

        else:
            result = process_static_image(image, horizontal_crop_percent, vertical_crop_percent, selected_side)

            # 根据原始图像格式保存
            if actual_format in ['jpeg', 'jpg']:
                if result.mode != "RGB":
                    print("转换静态图像模式为 RGB 以兼容 JPEG")
                    result = result.convert("RGB")
                result.save(output_path, format='JPEG')
            elif actual_format == 'png':
                result.save(output_path, format='PNG')
            else:
                # 对于其他格式，使用原始格式保存
                result.save(output_path, format=actual_format.upper())

        print(f"图像处理成功。保存至 {output_path}")
        return FileResponse(
            output_path,
            media_type=f"image/{actual_format}",
            headers={"X-User-ID": user_id}
        )

    except Exception as e:
        print(f"处理图像时发生未处理的错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def serve_index():
    file_path = os.path.join(HTML_DIR, INDEX_FILE)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="text/html")
    else:
        raise HTTPException(status_code=404, detail="Index file not found.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
