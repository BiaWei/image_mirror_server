from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from PIL import Image, ImageOps, ImageSequence
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


def process_static_image(image: Image.Image, crop_percent: int, selected_side: str) -> Image.Image:
    print(f"Processing static image with crop_percent={crop_percent}, selected_side={selected_side}")
    image = correct_image_orientation(image)
    width, height = image.size
    crop_width = int(width * crop_percent / 100)

    if selected_side == "left":
        cropped = image.crop((0, 0, crop_width, height))
        mirrored = ImageOps.mirror(cropped)
        result = Image.new('RGBA', (crop_width * 2, height))
        result.paste(cropped, (0, 0))
        result.paste(mirrored, (crop_width, 0))
    else:
        cropped = image.crop((width - crop_width, 0, width, height))
        mirrored = ImageOps.mirror(cropped)
        result = Image.new('RGBA', (crop_width * 2, height))
        result.paste(mirrored, (0, 0))
        result.paste(cropped, (crop_width, 0))

    return result


def correct_image_orientation(image):
    try:
        exif = image._getexif()
        if exif:
            orientation_key = next(
                (key for key, val in ExifTags.TAGS.items() if val == 'Orientation'), None)
            if orientation_key and orientation_key in exif:
                orientation = exif[orientation_key]

                # 根据 Orientation 值旋转图片
                if orientation == 3:  # 上下颠倒
                    image = image.rotate(180, expand=True)
                elif orientation == 6:  # 顺时针 90 度
                    image = image.rotate(270, expand=True)
                elif orientation == 8:  # 逆时针 90 度
                    image = image.rotate(90, expand=True)
        return image
    except Exception as e:
        print(f"Error correcting orientation: {e}")
        return image


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    if rate_limiter.is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    rate_limiter.add_request(client_ip)
    response = await call_next(request)
    return response


# another method
def process_animated_image_spare(image: Image.Image, crop_percent: int, selected_side: str) -> tuple:
    """
    修复透明背景和残影问题的 GIF 图片处理函数
    增加了更严格的颜色处理逻辑，防止白色区域变为透明
    """
    frames = []
    durations = []
    disposal_methods = []

    width, height = image.size
    crop_width = int(width * crop_percent / 100)

    print("Original size:", width, height)
    print("Crop width:", crop_width)

    try:
        previous_frame = None
        palette = None

        for frame_index, frame in enumerate(ImageSequence.Iterator(image)):
            duration = frame.info.get('duration', 100)
            durations.append(duration)
            disposal_method = getattr(frame, 'disposal_method', 2)
            disposal_methods.append(disposal_method)

            # 转换为 RGBA 模式，保持原始颜色
            current = frame.convert('RGBA')

            print(f"Frame {frame_index} original mode:", current.mode)

            # 创建新的透明画布
            new_frame = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))

            # 裁剪和镜像处理
            if selected_side == "left":
                cropped = current.crop((0, 0, crop_width, height))
                mirrored = ImageOps.mirror(cropped)
                new_frame.paste(cropped, (0, 0), cropped)
                new_frame.paste(mirrored, (crop_width, 0), mirrored)
            else:
                cropped = current.crop((width - crop_width, 0, width, height))
                mirrored = ImageOps.mirror(cropped)
                new_frame.paste(mirrored, (0, 0), mirrored)
                new_frame.paste(cropped, (crop_width, 0), cropped)

            # 根据 disposal_method 处理残影
            if (disposal_method == 0 or disposal_method == 1) and previous_frame:
                new_frame = Image.alpha_composite(previous_frame, new_frame)
            elif disposal_method == 3 and previous_frame:
                new_frame = Image.alpha_composite(previous_frame, new_frame)

            # 创建 RGB 图像并处理透明度
            rgb_frame = Image.new('RGB', new_frame.size, (255, 255, 255))  # 使用白色背景
            rgb_frame.paste(new_frame, mask=new_frame.split()[3])

            if palette is None:
                # 第一帧：创建调色板，保留256个颜色位置
                converted_frame = rgb_frame.convert('P', palette=Image.ADAPTIVE, colors=255)
                palette = converted_frame.getpalette()
                # 确保透明色位置的颜色为黑色
                palette[:3] = [0, 0, 0]
            else:
                # 后续帧：使用相同的调色板
                converted_frame = rgb_frame.convert('P', palette=Image.ADAPTIVE, colors=255)
                converted_frame.putpalette(palette)

            # 更严格的透明度处理
            alpha = new_frame.split()[3]
            # 只有完全透明的像素（alpha=0）才会被标记为透明
            mask = alpha.point(lambda x: 0 if x == 0 else 255)

            # 仅对完全透明的区域应用透明色
            converted_frame.paste(0, mask=ImageOps.invert(mask))

            # 保存关键信息
            converted_frame.info['transparency'] = 0
            converted_frame.info['duration'] = duration

            print(f"Frame {frame_index} final mode:", converted_frame.mode)
            print(f"Frame {frame_index} has transparency:", 'transparency' in converted_frame.info)

            frames.append(converted_frame)
            previous_frame = new_frame

    except EOFError:
        pass

    return frames, durations, disposal_methods


def process_animated_image(image: Image.Image, crop_percent: int, selected_side: str) -> tuple:
    """
    修复透明背景和残影问题的 GIF 图片处理函数
    """
    frames = []
    durations = []
    disposal_methods = []

    width, height = image.size
    crop_width = int(width * crop_percent / 100)

    # 检查透明索引（如果存在）
    transparency_index = image.info.get('transparency', None)

    try:
        previous_frame = None
        for frame in ImageSequence.Iterator(image):
            # 获取当前帧的 duration 和 disposal_method
            durations.append(frame.info.get('duration', 100))
            disposal_method = getattr(frame, 'disposal_method', 2)
            disposal_methods.append(disposal_method)

            # 转换为 RGBA 模式，确保透明处理
            current = frame.convert('RGBA')

            # 创建新的透明画布
            new_frame = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))

            # 根据选择的边进行裁剪和镜像
            if selected_side == "left":
                cropped = current.crop((0, 0, crop_width, height))
                mirrored = ImageOps.mirror(cropped)
                new_frame.paste(cropped, (0, 0), cropped)
                new_frame.paste(mirrored, (crop_width, 0), mirrored)
            else:
                cropped = current.crop((width - crop_width, 0, width, height))
                mirrored = ImageOps.mirror(cropped)
                new_frame.paste(mirrored, (0, 0), mirrored)
                new_frame.paste(cropped, (crop_width, 0), cropped)

            # 根据 disposal_method 处理残影
            if disposal_method == 0 or disposal_method == 1:
                if previous_frame:
                    new_frame = Image.alpha_composite(previous_frame, new_frame)
            elif disposal_method == 2:
                pass  # 恢复到背景（透明）
            elif disposal_method == 3 and previous_frame:
                new_frame = Image.alpha_composite(previous_frame, new_frame)

            # 转换为调色板模式
            reduced_frame = new_frame.convert('P', palette=Image.ADAPTIVE, colors=255)

            # 如果存在透明索引，则添加到调色板
            if transparency_index is not None:
                palette = reduced_frame.getpalette()
                transparent_color = (0, 0, 0)  # 假定透明色为黑色
                transparent_index = len(palette) // 3
                if transparent_index < 256:
                    palette[transparent_index * 3:transparent_index * 3 + 3] = transparent_color
                    reduced_frame.putpalette(palette)

                    # 应用透明掩码
                    mask = new_frame.split()[-1].point(lambda p: 255 if p < 128 else 0)
                    reduced_frame.paste(transparent_index, mask=mask)
                    reduced_frame.info['transparency'] = transparent_index

            frames.append(reduced_frame)
            previous_frame = new_frame

    except EOFError:
        pass  # 到达最后一帧

    return frames, durations, disposal_methods


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

    uvicorn.run("main:app", host="0.0.0.0", port=1998, reload=True)