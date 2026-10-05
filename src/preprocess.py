# -*- coding: utf-8 -*-
"""
电池包表面裂纹 — 图像预处理（训推共用）

几何不变：不裁剪、不缩放、不旋转。输出与输入同尺寸，标签坐标可直接复用。
训练 / 验证 / 正式推理必须调用本模块同一函数与同一组参数。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional, Tuple, Union

import cv2
import numpy as np

# =============================================================================
# 参数配置区（只改这里；训推保持一致）
# =============================================================================

# ---------- 总开关 ----------
# 是否启用预处理；False 时原样返回，便于做「原图 baseline」对照
ENABLE_PREPROCESS: bool = True

# ---------- LAB-CLAHE（主配方，建议默认开启）----------
# 只在 L（亮度）通道做自适应直方图均衡，抬局部对比、压光照不均
ENABLE_CLAHE: bool = True
CLAHE_CLIP_LIMIT: float = 2.0          # 对比度限制；越大裂纹越“黑”，过大易放大涂层噪声
CLAHE_TILE_SIZE: int = 8               # 分块边长（像素）；常用 8

# ---------- 反锐化 Unsharp（主配方，建议默认开启）----------
# 弥补 JPEG 发糊，让细裂纹边缘更清晰
ENABLE_UNSHARP: bool = True
UNSHARP_AMOUNT: float = 1.35           # 锐化强度，建议 1.2～1.5；>1.6 易出假纹
UNSHARP_SIGMA: float = 3.0             # 高斯模糊 sigma；核大小用 (0,0) 由 sigma 自动决定

# ---------- 黑帽 Black-hat（可选加强；主配方 Recall 不够再开）----------
# 形态学闭运算减原图，突出比邻域更暗的细缝；假阳也会升，务必做 val 对照
ENABLE_BLACKHAT: bool = False
BLACKHAT_KERNEL_SIZE: int = 17         # 椭圆核边长，奇数，建议 15～21
BLACKHAT_ALPHA: float = 1.0            # 叠回权重 α，建议 0.8～1.5

# ---------- 批量离线烘焙默认路径（可被命令行覆盖）----------
DEFAULT_INPUT_DIR: str = r"data/测试集"
DEFAULT_OUTPUT_DIR: str = r"data/yolo/images_enhanced"
IMAGE_SUFFIXES: Tuple[str, ...] = (".jpg", ".jpeg", ".png", ".bmp")

# =============================================================================
# 实现
# =============================================================================

PathLike = Union[str, Path]


def get_preprocess_config() -> dict:
    """返回当前生效的预处理参数快照（写日志 / 方案用）。"""
    return {
        "ENABLE_PREPROCESS": ENABLE_PREPROCESS,
        "ENABLE_CLAHE": ENABLE_CLAHE,
        "CLAHE_CLIP_LIMIT": CLAHE_CLIP_LIMIT,
        "CLAHE_TILE_SIZE": CLAHE_TILE_SIZE,
        "ENABLE_UNSHARP": ENABLE_UNSHARP,
        "UNSHARP_AMOUNT": UNSHARP_AMOUNT,
        "UNSHARP_SIGMA": UNSHARP_SIGMA,
        "ENABLE_BLACKHAT": ENABLE_BLACKHAT,
        "BLACKHAT_KERNEL_SIZE": BLACKHAT_KERNEL_SIZE,
        "BLACKHAT_ALPHA": BLACKHAT_ALPHA,
    }


def _apply_clahe_lab(bgr: np.ndarray, clip_limit: float, tile: int) -> np.ndarray:
    """在 LAB 颜色空间仅增强 L 通道，避免把色度通道拉花。"""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=float(clip_limit), tileGridSize=(int(tile), int(tile)))
    l_ch = clahe.apply(l_ch)
    return cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)


def _apply_unsharp(bgr: np.ndarray, amount: float, sigma: float) -> np.ndarray:
    """反锐化：原图加权减去高斯模糊图，突出边缘。"""
    blur = cv2.GaussianBlur(bgr, (0, 0), float(sigma))
    # amount * 原图 + (1 - amount) * 模糊图
    return cv2.addWeighted(bgr, float(amount), blur, 1.0 - float(amount), 0)


def _apply_blackhat(bgr: np.ndarray, kernel_size: int, alpha: float) -> np.ndarray:
    """
    黑帽：close(gray) - gray，再按权重从彩色图中减去，使暗裂纹更黑。
    几何不变，仅改变像素值。
    """
    k = int(kernel_size)
    if k % 2 == 0:
        k += 1  # 形态学核必须为奇数
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    # 扩展为三通道后按 α 从各通道减去
    bh = cv2.cvtColor(blackhat, cv2.COLOR_GRAY2BGR).astype(np.float32)
    out = bgr.astype(np.float32) - float(alpha) * bh
    return np.clip(out, 0, 255).astype(np.uint8)


def enhance_crack(
    bgr: np.ndarray,
    *,
    enable: Optional[bool] = None,
    enable_clahe: Optional[bool] = None,
    clip_limit: Optional[float] = None,
    tile: Optional[int] = None,
    enable_unsharp: Optional[bool] = None,
    sharp: Optional[float] = None,
    sigma: Optional[float] = None,
    enable_blackhat: Optional[bool] = None,
    blackhat_kernel: Optional[int] = None,
    blackhat_alpha: Optional[float] = None,
) -> np.ndarray:
    """
    裂纹可见性增强（主入口）。

    默认流水线：BGR → LAB-CLAHE → BGR → 反锐化 →（可选）黑帽融合。
    未传入的关键字参数一律使用文件顶部配置区的默认值。

    参数
    ----
    bgr : HxWx3 uint8，OpenCV BGR 图像
    其余关键字 : 覆盖顶部配置；一般调用方不要改，保证训推一致

    返回
    ----
    与输入同 shape、同 dtype 的 uint8 BGR 图
    """
    if bgr is None or not isinstance(bgr, np.ndarray) or bgr.ndim != 3 or bgr.shape[2] != 3:
        raise ValueError("enhance_crack 需要 HxWx3 的 BGR uint8 图像")

    use = ENABLE_PREPROCESS if enable is None else enable
    if not use:
        return bgr.copy()

    do_clahe = ENABLE_CLAHE if enable_clahe is None else enable_clahe
    do_unsharp = ENABLE_UNSHARP if enable_unsharp is None else enable_unsharp
    do_bh = ENABLE_BLACKHAT if enable_blackhat is None else enable_blackhat

    out = bgr
    if do_clahe:
        out = _apply_clahe_lab(
            out,
            clip_limit if clip_limit is not None else CLAHE_CLIP_LIMIT,
            tile if tile is not None else CLAHE_TILE_SIZE,
        )
    if do_unsharp:
        out = _apply_unsharp(
            out,
            sharp if sharp is not None else UNSHARP_AMOUNT,
            sigma if sigma is not None else UNSHARP_SIGMA,
        )
    if do_bh:
        out = _apply_blackhat(
            out,
            blackhat_kernel if blackhat_kernel is not None else BLACKHAT_KERNEL_SIZE,
            blackhat_alpha if blackhat_alpha is not None else BLACKHAT_ALPHA,
        )

    # 尺寸必须与原图一致，否则标签 / CSV 坐标会错位
    if out.shape != bgr.shape:
        raise RuntimeError(f"预处理改变了尺寸: {bgr.shape} -> {out.shape}")
    return out


def enhance_crack_file(src: PathLike, dst: Optional[PathLike] = None) -> np.ndarray:
    """
    读单张图 → 增强 → 可选写盘。

    返回增强后的 BGR 数组。读失败抛 FileNotFoundError / RuntimeError。
    """
    src_path = Path(src)
    # Windows 下中文路径用 imdecode，避免 cv2.imread 失败
    data = np.fromfile(str(src_path), dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError(f"无法读取图像: {src_path}")

    enhanced = enhance_crack(bgr)

    if dst is not None:
        dst_path = Path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        ext = dst_path.suffix.lower() or ".jpg"
        ok, buf = cv2.imencode(ext, enhanced)
        if not ok:
            raise RuntimeError(f"编码失败: {dst_path}")
        buf.tofile(str(dst_path))

    return enhanced


def list_images(directory: PathLike) -> list[Path]:
    """列出目录下常见图像文件（不递归），按文件名排序。"""
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"目录不存在: {root}")
    files = [
        p
        for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(files, key=lambda p: p.name.lower())


def bake_directory(
    input_dir: PathLike,
    output_dir: PathLike,
    *,
    names: Optional[Iterable[str]] = None,
) -> int:
    """
    离线烘焙：对目录内图像逐张增强并写到 output_dir（文件名不变）。

    names 不为空时只处理给定文件名集合。返回成功写出的张数。
    """
    in_root = Path(input_dir)
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    images = list_images(in_root)
    if names is not None:
        allow = set(names)
        images = [p for p in images if p.name in allow]

    count = 0
    for src in images:
        enhance_crack_file(src, out_root / src.name)
        count += 1
    return count


def make_compare_strip(bgr: np.ndarray, enhanced: Optional[np.ndarray] = None) -> np.ndarray:
    """左右拼接「原图 | 增强图」，方便人工抽检。"""
    enh = enhance_crack(bgr) if enhanced is None else enhanced
    if enh.shape != bgr.shape:
        raise RuntimeError("对比条尺寸不一致")
    return np.hstack([bgr, enh])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="电池包裂纹图像预处理")
    parser.add_argument("--input", "-i", type=str, default=None, help="单张输入图路径")
    parser.add_argument("--output", "-o", type=str, default=None, help="单张输出图路径")
    parser.add_argument("--input-dir", type=str, default=None, help="批量输入目录")
    parser.add_argument("--output-dir", type=str, default=None, help="批量输出目录")
    parser.add_argument(
        "--compare",
        type=str,
        default=None,
        help="将原图|增强图横向拼接保存到该路径（单张模式）",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="打印当前顶部配置并退出",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.show_config:
        for k, v in get_preprocess_config().items():
            print(f"{k}={v}")
        return

    # 单张
    if args.input:
        src = Path(args.input)
        data = np.fromfile(str(src), dtype=np.uint8)
        bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if bgr is None:
            raise SystemExit(f"无法读取: {src}")
        enh = enhance_crack(bgr)

        if args.output:
            enhance_crack_file(src, args.output)
            print(f"已写出增强图: {args.output}")

        if args.compare:
            strip = make_compare_strip(bgr, enh)
            cmp_path = Path(args.compare)
            cmp_path.parent.mkdir(parents=True, exist_ok=True)
            ok, buf = cv2.imencode(cmp_path.suffix or ".jpg", strip)
            if not ok:
                raise SystemExit(f"对比图编码失败: {cmp_path}")
            buf.tofile(str(cmp_path))
            print(f"已写出对比图: {cmp_path}")

        if not args.output and not args.compare:
            print(f"增强完成 shape={enh.shape} dtype={enh.dtype}（未指定 -o / --compare，未写盘）")
        return

    # 批量
    in_dir = args.input_dir or DEFAULT_INPUT_DIR
    out_dir = args.output_dir or DEFAULT_OUTPUT_DIR
    n = bake_directory(in_dir, out_dir)
    print(f"批量增强完成: {n} 张 -> {out_dir}")
    print("当前配置:", get_preprocess_config())


if __name__ == "__main__":
    main()
