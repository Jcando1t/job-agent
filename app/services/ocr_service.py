"""本地简历图片 OCR。图片和识别过程均留在运行本应用的电脑上。"""

from functools import lru_cache
from io import BytesIO


MAX_IMAGE_PIXELS = 25_000_000


class OcrImageError(ValueError):
    """图片无法安全解码或没有识别到文字。"""


@lru_cache(maxsize=1)
def _get_engine():
    # 延迟加载体积较大的 OCR 模型，避免普通页面和 API 启动受其影响。
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def recognize_resume_image(content: bytes) -> str:
    """读取一张图片并返回识别出的文字，不会保存或上传中间数据。"""
    import numpy as np
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(BytesIO(content)) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise OcrImageError("图片分辨率过大，请先缩小图片后重试。")
            image = ImageOps.exif_transpose(source).convert("RGB")
            pixels = np.asarray(image)
    except OcrImageError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise OcrImageError("图片无法读取，请重新上传 PNG 或 JPG 图片。") from error

    result, _ = _get_engine()(pixels)
    if not result:
        return ""

    lines = []
    for item in result:
        # RapidOCR 的每项通常是 [边框, 文字, 置信度]。
        if len(item) >= 2 and str(item[1]).strip():
            lines.append(str(item[1]).strip())
    return "\n".join(lines)
