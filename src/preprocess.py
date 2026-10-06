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

# ---------- 双边滤波去噪（先做，压涂层颗粒 / JPEG 噪点，尽量保住裂纹边）----------
ENABLE_DENOISE: bool = True
DENOISE_DIAMETER: int = 7              # 邻域直径，奇数；5～9
DENOISE_SIGMA_COLOR: float = 80.0      # 颜色空间 sigma；越大越平滑
DENOISE_SIGMA_SPACE: float = 45.0      # 坐标空间 sigma

# ---------- LAB-CLAHE（宜弱，过强会把噪声当对比度抬起来）----------
# 只在 L（亮度）通道做自适应直方图均衡
ENABLE_CLAHE: bool = False
CLAHE_CLIP_LIMIT: float = 1.4          # 对比度限制；1.2～1.6 较稳，>2 易出沙粒感
CLAHE_TILE_SIZE: int = 16              # 分块边长；比 8 大，减少局部噪声被放大

# ---------- 反锐化 Unsharp（默认关：会放大噪点；裂纹靠黑帽拉黑）----------
ENABLE_UNSHARP: bool = False
UNSHARP_AMOUNT: float = 1.12           # 若重开，用很弱的 1.08～1.15
UNSHARP_SIGMA: float = 2.0

# ---------- 黑帽 Black-hat（专门抠暗裂纹，默认开）----------
# close(gray)-gray；只把响应超过阈值的像素叠回去，避免细沙被当裂纹
ENABLE_BLACKHAT: bool = True
BLACKHAT_KERNEL_SIZE: int = 21         # 椭圆核边长，奇数，建议 17～25
BLACKHAT_ALPHA: float = 1.8            # 叠回权重；越大裂纹越黑
BLACKHAT_THRESHOLD: int = 12           # 黑帽响应低于此值不叠（0 表示全叠）
BLACKHAT_OPEN_SIZE: int = 3            # 对掩膜做开运算去孤立点；1 或 0 表示关闭

# ---------- 批量离线烘焙默认路径（可被命令行覆盖）----------
# 相对路径一律相对「项目根目录」，不依赖你从哪个文件夹启动脚本
#
# 注意：本仓库文件夹名与常见习惯相反——
#   data/训练集  = 640 张无实例标签图（默认批量增强这批）
#   data/测试集  = 160 张带多边形标注（做有监督 train/val 时请改成这个目录）
DEFAULT_INPUT_DIR: str = r"data/训练集"
DEFAULT_OUTPUT_DIR: str = r"data/yolo/images_enhanced"
IMAGE_SUFFIXES: Tuple[str, ...] = (".jpg", ".jpeg", ".png", ".bmp")

# =============================================================================
# 实现
# =============================================================================

PathLike = Union[str, Path]

# 本文件在 src/preprocess.py → 项目根 = 上一级目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_path(path: PathLike) -> Path:
    """
    把路径解析为绝对路径。

    - 已是绝对路径：直接返回
    - 相对路径：相对项目根目录解析（不是相对当前工作目录）
    """
    p = Path(path)
    if p.is_absolute():
        return p
    return (_PROJECT_ROOT / p).resolve()


def get_preprocess_config() -> dict:
    """返回当前生效的预处理参数快照（写日志 / 方案用）。"""
    return {
        "ENABLE_PREPROCESS": ENABLE_PREPROCESS,
        "ENABLE_DENOISE": ENABLE_DENOISE,
        "DENOISE_DIAMETER": DENOISE_DIAMETER,
        "DENOISE_SIGMA_COLOR": DENOISE_SIGMA_COLOR,
        "DENOISE_SIGMA_SPACE": DENOISE_SIGMA_SPACE,
        "ENABLE_CLAHE": ENABLE_CLAHE,
        "CLAHE_CLIP_LIMIT": CLAHE_CLIP_LIMIT,
        "CLAHE_TILE_SIZE": CLAHE_TILE_SIZE,
        "ENABLE_UNSHARP": ENABLE_UNSHARP,
        "UNSHARP_AMOUNT": UNSHARP_AMOUNT,
        "UNSHARP_SIGMA": UNSHARP_SIGMA,
        "ENABLE_BLACKHAT": ENABLE_BLACKHAT,
        "BLACKHAT_KERNEL_SIZE": BLACKHAT_KERNEL_SIZE,
        "BLACKHAT_ALPHA": BLACKHAT_ALPHA,
        "BLACKHAT_THRESHOLD": BLACKHAT_THRESHOLD,
        "BLACKHAT_OPEN_SIZE": BLACKHAT_OPEN_SIZE,
    }


def _apply_denoise(
    bgr: np.ndarray,
    diameter: int,
    sigma_color: float,
    sigma_space: float,
) -> np.ndarray:
    """双边滤波：平滑平坦涂层，保留裂纹等强边缘。"""
    d = int(diameter)
    if d % 2 == 0:
        d += 1
    return cv2.bilateralFilter(bgr, d, float(sigma_color), float(sigma_space))


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


def _apply_blackhat(
    bgr: np.ndarray,
    kernel_size: int,
    alpha: float,
    threshold: int,
    open_size: int,
) -> np.ndarray:
    """
    黑帽：close(gray) - gray，再按权重从彩色图中减去，使暗裂纹更黑。
    threshold>0 时只叠响应较强的像素；open_size>=3 时对掩膜开运算，去掉孤立沙粒。
    """
    k = int(kernel_size)
    if k % 2 == 0:
        k += 1  # 形态学核必须为奇数
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    if int(threshold) > 0:
        _, keep = cv2.threshold(blackhat, int(threshold), 255, cv2.THRESH_BINARY)
        osz = int(open_size)
        if osz >= 3:
            if osz % 2 == 0:
                osz += 1
            open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (osz, osz))
            keep = cv2.morphologyEx(keep, cv2.MORPH_OPEN, open_k)
        blackhat = cv2.bitwise_and(blackhat, keep)
    bh = cv2.cvtColor(blackhat, cv2.COLOR_GRAY2BGR).astype(np.float32)
    out = bgr.astype(np.float32) - float(alpha) * bh
    return np.clip(out, 0, 255).astype(np.uint8)


def enhance_crack(
    bgr: np.ndarray,
    *,
    enable: Optional[bool] = None,
    enable_denoise: Optional[bool] = None,
    denoise_d: Optional[int] = None,
    denoise_sigma_color: Optional[float] = None,
    denoise_sigma_space: Optional[float] = None,
    enable_clahe: Optional[bool] = None,
    clip_limit: Optional[float] = None,
    tile: Optional[int] = None,
    enable_unsharp: Optional[bool] = None,
    sharp: Optional[float] = None,
    sigma: Optional[float] = None,
    enable_blackhat: Optional[bool] = None,
    blackhat_kernel: Optional[int] = None,
    blackhat_alpha: Optional[float] = None,
    blackhat_threshold: Optional[int] = None,
    blackhat_open: Optional[int] = None,
) -> np.ndarray:
    """
    裂纹可见性增强（主入口）。

    默认流水线：BGR → 双边去噪 → 弱 CLAHE → 阈值黑帽（反锐化默认关闭）。
    未传入的关键字参数一律使用文件顶部配置区的默认值。
    """
    if bgr is None or not isinstance(bgr, np.ndarray) or bgr.ndim != 3 or bgr.shape[2] != 3:
        raise ValueError("enhance_crack 需要 HxWx3 的 BGR uint8 图像")

    use = ENABLE_PREPROCESS if enable is None else enable
    if not use:
        return bgr.copy()

    do_denoise = ENABLE_DENOISE if enable_denoise is None else enable_denoise
    do_clahe = ENABLE_CLAHE if enable_clahe is None else enable_clahe
    do_unsharp = ENABLE_UNSHARP if enable_unsharp is None else enable_unsharp
    do_bh = ENABLE_BLACKHAT if enable_blackhat is None else enable_blackhat

    out = bgr
    if do_denoise:
        out = _apply_denoise(
            out,
            denoise_d if denoise_d is not None else DENOISE_DIAMETER,
            denoise_sigma_color if denoise_sigma_color is not None else DENOISE_SIGMA_COLOR,
            denoise_sigma_space if denoise_sigma_space is not None else DENOISE_SIGMA_SPACE,
        )
    if do_clahe:
        out = _apply_clahe_lab(
            out,
            clip_limit if clip_limit is not None else CLAHE_CLIP_LIMIT,
            tile if tile is not None else CLAHE_TILE_SIZE,
        )
    if do_bh:
        out = _apply_blackhat(
            out,
            blackhat_kernel if blackhat_kernel is not None else BLACKHAT_KERNEL_SIZE,
            blackhat_alpha if blackhat_alpha is not None else BLACKHAT_ALPHA,
            blackhat_threshold if blackhat_threshold is not None else BLACKHAT_THRESHOLD,
            blackhat_open if blackhat_open is not None else BLACKHAT_OPEN_SIZE,
        )
    if do_unsharp:
        out = _apply_unsharp(
            out,
            sharp if sharp is not None else UNSHARP_AMOUNT,
            sigma if sigma is not None else UNSHARP_SIGMA,
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
    src_path = resolve_path(src)
    # Windows 下中文路径用 imdecode，避免 cv2.imread 失败
    data = np.fromfile(str(src_path), dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError(f"无法读取图像: {src_path}")

    enhanced = enhance_crack(bgr)

    if dst is not None:
        dst_path = resolve_path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        ext = dst_path.suffix.lower() or ".jpg"
        ok, buf = cv2.imencode(ext, enhanced)
        if not ok:
            raise RuntimeError(f"编码失败: {dst_path}")
        buf.tofile(str(dst_path))

    return enhanced


def list_images(directory: PathLike) -> list[Path]:
    """列出目录下常见图像文件（不递归），按文件名排序。"""
    root = resolve_path(directory)
    if not root.is_dir():
        raise FileNotFoundError(
            f"目录不存在: {root}\n"
            f"（相对路径按项目根解析: {_PROJECT_ROOT}；"
            f"当前工作目录: {Path.cwd()}）"
        )
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
    in_root = resolve_path(input_dir)
    out_root = resolve_path(output_dir)
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
        src = resolve_path(args.input)
        data = np.fromfile(str(src), dtype=np.uint8)
        bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if bgr is None:
            raise SystemExit(f"无法读取: {src}")
        enh = enhance_crack(bgr)

        if args.output:
            out_path = resolve_path(args.output)
            enhance_crack_file(src, out_path)
            print(f"已写出增强图: {out_path}")

        if args.compare:
            strip = make_compare_strip(bgr, enh)
            cmp_path = resolve_path(args.compare)
            cmp_path.parent.mkdir(parents=True, exist_ok=True)
            ok, buf = cv2.imencode(cmp_path.suffix or ".jpg", strip)
            if not ok:
                raise SystemExit(f"对比图编码失败: {cmp_path}")
            buf.tofile(str(cmp_path))
            print(f"已写出对比图: {cmp_path}")

        if not args.output and not args.compare:
            print(f"增强完成 shape={enh.shape} dtype={enh.dtype}（未指定 -o / --compare，未写盘）")
        return

    # 批量（未传参数时用顶部默认路径，相对项目根）
    in_dir = resolve_path(args.input_dir or DEFAULT_INPUT_DIR)
    out_dir = resolve_path(args.output_dir or DEFAULT_OUTPUT_DIR)
    n = bake_directory(in_dir, out_dir)
    print(f"批量增强完成: {n} 张 -> {out_dir}")
    print("当前配置:", get_preprocess_config())


if __name__ == "__main__":
    main()
