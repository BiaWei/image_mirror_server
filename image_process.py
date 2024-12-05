from PIL import Image, ImageOps, ImageSequence
from PIL import Image, ExifTags
import io
import os


def crop_mirror_image(image: Image.Image, new_canvas: Image.Image,
                      crop_width: int, crop_height: int, width: int, height: int,
                      side: str):
    result = new_canvas
    print(f"crop_width: {crop_width}, crop_height: {crop_height}, width: {width}, height: {height}, side: {side}")
    if side == "left":
        cropped = image.crop((0, 0, crop_width, height))
        mirrored = ImageOps.mirror(cropped)
        result.paste(cropped, (0, 0))
        result.paste(mirrored, (crop_width, 0))
    elif side == "right":
        cropped = image.crop((width - crop_width, 0, width, height))
        mirrored = ImageOps.mirror(cropped)
        result.paste(mirrored, (0, 0))
        result.paste(cropped, (crop_width, 0))
    elif side == "up":
        cropped = image.crop((0, 0, width, crop_height))
        mirrored = ImageOps.flip(cropped)
        result.paste(cropped, (0, 0))
        result.paste(mirrored, (0, crop_height))
    elif side == "down":
        cropped = image.crop((0, height - crop_height, width, height))
        mirrored = ImageOps.flip(cropped)
        result.paste(mirrored, (0, 0))
        result.paste(cropped, (0, crop_height))
    else:
        raise ValueError(f"Invalid selected_side: {selected_side}")

    return result


def process_static_image(image: Image.Image, horizontal_crop_percent: int, vertical_crop_percent: int, selected_side: str) -> Image.Image:
    print(f"Processing static image with horizontal_crop_percent={horizontal_crop_percent},"
          f" vertical_crop_percent={vertical_crop_percent}, selected_side={selected_side}")
    width, height = image.size
    crop_width = int(width * horizontal_crop_percent / 100)
    crop_height = int(height * vertical_crop_percent / 100)

    if selected_side == "left" or selected_side == "right":
        new_canvas = Image.new('RGBA', (crop_width * 2, height))
        new_image = crop_mirror_image(image, new_canvas, crop_width, crop_height, width, height, selected_side)

    elif selected_side == "up" or selected_side == "down":
        new_canvas = Image.new('RGBA', (width, crop_height * 2))
        new_image = crop_mirror_image(image, new_canvas, crop_width, crop_height, width, height, selected_side)

    elif selected_side == "q1":
        new_canvas = Image.new('RGBA', (crop_width * 2, height))
        new_image = crop_mirror_image(image, new_canvas, crop_width, crop_height, width, height, "left")
        width, height = new_image.size
        new_canvas = Image.new('RGBA', (width, crop_height * 2))
        new_image = crop_mirror_image(new_image, new_canvas, crop_width, crop_height, width, height, "up")

    elif selected_side == "q2":
        new_canvas = Image.new('RGBA', (crop_width * 2, height))
        new_image = crop_mirror_image(image, new_canvas, crop_width, crop_height, width, height, "right")
        width, height = new_image.size
        new_canvas = Image.new('RGBA', (width, crop_height * 2))
        new_image = crop_mirror_image(new_image, new_canvas, crop_width, crop_height, width, height, "up")

    elif selected_side == "q3":
        new_canvas = Image.new('RGBA', (crop_width * 2, height))
        new_image = crop_mirror_image(image, new_canvas, crop_width, crop_height, width, height, "right")
        width, height = new_image.size
        new_canvas = Image.new('RGBA', (width, crop_height * 2))
        new_image = crop_mirror_image(new_image, new_canvas, crop_width, crop_height, width, height, "down")

    elif selected_side == "q4":
        new_canvas = Image.new('RGBA', (crop_width * 2, height))
        new_image = crop_mirror_image(image, new_canvas, crop_width, crop_height, width, height, "left")
        width, height = new_image.size
        new_canvas = Image.new('RGBA', (width, crop_height * 2))
        new_image = crop_mirror_image(new_image, new_canvas, crop_width, crop_height, width, height, "down")

    else:
        raise ValueError(f"Invalid selected_side: {selected_side}")


    return new_image


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


# another method
def process_animated_image_spare(image: Image.Image, horizontal_crop_percent: int, vertical_crop_percent: int, selected_side: str) -> tuple:
    """
    修复透明背景和残影问题的 GIF 图片处理函数
    增加了更严格的颜色处理逻辑，防止白色区域变为透明
    """
    frames = []
    durations = []
    disposal_methods = []

    width, height = image.size
    crop_width = int(width * horizontal_crop_percent / 100)
    crop_height = int(height * vertical_crop_percent / 100)

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
            if selected_side == "left" or selected_side == "right":
                new_frame = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_frame, crop_width, crop_height, width, height, selected_side)

            elif selected_side == "up" or selected_side == "down":
                new_frame = Image.new('RGBA', (width, crop_height * 2), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_frame, crop_width, crop_height, width, height, selected_side)

            elif selected_side == "q1":
                new_canvas = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_canvas, crop_width, crop_height, width, height, "left")
                new_canvas = Image.new('RGBA', (crop_width * 2, crop_height * 2), (0, 0, 0, 0))
                new_frame = crop_mirror_image(new_frame, new_canvas, crop_width, crop_height, crop_width * 2, height,
                                              "up")

            elif selected_side == "q2":
                new_frame = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_frame, crop_width, crop_height, width, height, "right")
                new_canvas = Image.new('RGBA', (crop_width * 2, crop_height * 2), (0, 0, 0, 0))
                new_frame = crop_mirror_image(new_frame, new_canvas, crop_width, crop_height, crop_width * 2, height,
                                              "up")

            elif selected_side == "q3":
                new_canvas = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_canvas, crop_width, crop_height, width, height, "right")
                new_canvas = Image.new('RGBA', (crop_width * 2, crop_height * 2), (0, 0, 0, 0))
                new_frame = crop_mirror_image(new_frame, new_canvas, crop_width, crop_height, crop_width * 2, height,
                                              "down")

            elif selected_side == "q4":
                new_canvas = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_canvas, crop_width, crop_height, width, height, "left")
                width, height = new_frame.size
                new_canvas = Image.new('RGBA', (crop_width * 2, crop_height * 2), (0, 0, 0, 0))
                new_frame = crop_mirror_image(new_frame, new_canvas, crop_width, crop_height, crop_width * 2, height,
                                              "down")
            else:
                raise ValueError(f"Invalid selected_side: {selected_side}")

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


def process_animated_image(image: Image.Image, horizontal_crop_percent: int, vertical_crop_percent: int, selected_side: str) -> tuple:
    """
    修复透明背景和残影问题的 GIF 图片处理函数
    """
    frames = []
    durations = []
    disposal_methods = []

    width, height = image.size
    crop_width = int(width * horizontal_crop_percent / 100)
    crop_height = int(height * vertical_crop_percent / 100)

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
            if selected_side == "left" or selected_side == "right":
                new_frame = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_frame, crop_width, crop_height, width, height, selected_side)

            elif selected_side == "up" or selected_side == "down":
                new_frame = Image.new('RGBA', (width, crop_height * 2), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_frame, crop_width, crop_height, width, height, selected_side)

            elif selected_side == "q1":
                new_canvas = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_canvas, crop_width, crop_height, width, height, "left")
                new_canvas = Image.new('RGBA', (crop_width * 2, crop_height * 2), (0, 0, 0, 0))
                new_frame = crop_mirror_image(new_frame, new_canvas, crop_width, crop_height, crop_width * 2, height, "up")

            elif selected_side == "q2":
                new_frame = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_frame, crop_width, crop_height, width, height, "right")
                new_canvas = Image.new('RGBA', (crop_width * 2, crop_height * 2), (0, 0, 0, 0))
                new_frame = crop_mirror_image(new_frame, new_canvas, crop_width, crop_height, crop_width * 2, height, "up")

            elif selected_side == "q3":
                new_canvas = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_canvas, crop_width, crop_height, width, height, "right")
                new_canvas = Image.new('RGBA', (crop_width * 2, crop_height * 2), (0, 0, 0, 0))
                new_frame = crop_mirror_image(new_frame, new_canvas, crop_width, crop_height, crop_width * 2, height, "down")

            elif selected_side == "q4":
                new_canvas = Image.new('RGBA', (crop_width * 2, height), (0, 0, 0, 0))
                new_frame = crop_mirror_image(current, new_canvas, crop_width, crop_height, width, height, "left")
                width, height = new_frame.size
                new_canvas = Image.new('RGBA', (crop_width * 2, crop_height * 2), (0, 0, 0, 0))
                new_frame = crop_mirror_image(new_frame, new_canvas, crop_width, crop_height, crop_width * 2, height, "down")
            else:
                raise ValueError(f"Invalid selected_side: {selected_side}")

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


def process_animated_image_combined(image: Image.Image, horizontal_crop_percent: int, vertical_crop_percent: int, selected_side: str) -> tuple:
    try:
        frames, durations, disposal_methods = process_animated_image(image, horizontal_crop_percent, vertical_crop_percent, selected_side)

    except Exception as e:
        frames, durations, disposal_methods = process_animated_image_spare(image, horizontal_crop_percent, vertical_crop_percent, selected_side)

    return frames, durations, disposal_methods

###################


def process_image_locally(file_path, horizontal_crop_percent, vertical_crop_percent, selected_side, output_dir):
    """
    本地处理图像，支持静态和动态（GIF）图像。

    参数：
    - file_path (str): 输入文件的路径。
    - crop_percent (int): 裁剪百分比。
    - selected_side (str): 裁剪的边，'left' 或 'right'。
    - output_dir (str): 输出目录。

    返回：
    - str: 输出文件路径。
    """
    # 根据选择的边调整裁剪比例
    if selected_side == "right" or selected_side == "q2" or selected_side == "q3":
        horizontal_crop_percent = 100 - horizontal_crop_percent
    if selected_side == "down" or selected_side == "q3" or selected_side == "q4":
        vertical_crop_percent = 100 - vertical_crop_percent

    try:
        original_filename = file_path[file_path.rfind('\\') + 1:]
        print(f"Processing {original_filename}")
        output_path = os.path.join(output_dir, f"{selected_side}_{horizontal_crop_percent}_{original_filename}")

        # 打开图像
        with open(file_path, "rb") as f:
            content = f.read()
        image = Image.open(io.BytesIO(content))
        is_animated = getattr(image, "is_animated", False)
        print(f"Processing image. Is animated: {is_animated}")

        if is_animated:
            # 处理 GIF 动画
            frames, durations, _ = process_animated_image_combined(image, horizontal_crop_percent, vertical_crop_percent,  selected_side)
            frames[0].save(
                output_path,
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                disposal=2,
                loop=0
            )
        else:
            # 处理静态图像
            image = correct_image_orientation(image)
            result = process_static_image(image, horizontal_crop_percent, vertical_crop_percent, selected_side)
            # 确保 JPEG 兼容性
            if file_path.lower().endswith(('.jpg', '.jpeg')) and result.mode != "RGB":
                result = result.convert("RGB")
            result.save(output_path)

        print(f"Image processed successfully. Saved to {output_path}")
        return output_path
    except Exception as e:
        print(f"Error processing image: {e}")
        raise


if __name__ == '__main__':
    file_path = os.path.join("examples", "test", "img.gif")
    output_dir = os.path.join("examples", "test", "output")

    horizontal_crop_percent = 29
    vertical_crop_percent = 100

    selected_side = "q1"
    file_path = process_image_locally(file_path, horizontal_crop_percent, vertical_crop_percent, selected_side, output_dir)

