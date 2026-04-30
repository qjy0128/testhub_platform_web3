# -*- coding: utf-8 -*-
from pathlib import Path, PurePosixPath, PureWindowsPath
import re


ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
MAX_IMAGE_UPLOAD_SIZE = 5 * 1024 * 1024
CATEGORY_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\u4e00-\u9fa5]{1,80}$')
FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.\u4e00-\u9fa5 ]{1,180}$')


class UnsafeTemplatePath(ValueError):
    pass


def sanitize_category(value):
    category = str(value or 'common').strip()
    if not CATEGORY_PATTERN.fullmatch(category):
        raise UnsafeTemplatePath('分类名称只能包含字母、数字、下划线、中划线和中文')
    return category


def sanitize_image_filename(value):
    filename = str(value or '').strip()
    if not filename:
        raise UnsafeTemplatePath('文件名不能为空')
    if filename != PureWindowsPath(filename).name or filename != PurePosixPath(filename).name:
        raise UnsafeTemplatePath('文件名不能包含路径')
    if filename.startswith('.'):
        raise UnsafeTemplatePath('文件名不能以点开头')
    if not FILENAME_PATTERN.fullmatch(filename):
        raise UnsafeTemplatePath('文件名包含非法字符')
    if Path(filename).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise UnsafeTemplatePath('仅支持 png、jpg、jpeg、gif、webp 图片')
    return filename


def validate_image_upload(uploaded_file):
    if getattr(uploaded_file, 'size', 0) > MAX_IMAGE_UPLOAD_SIZE:
        raise UnsafeTemplatePath('Image file cannot exceed 5MB')
    return sanitize_image_filename(uploaded_file.name)


def sanitize_file_stem(value, default='captured_element'):
    stem = str(value or default).strip()
    stem = re.sub(r'[^a-zA-Z0-9_\-\u4e00-\u9fa5]+', '_', stem).strip('_')
    return stem[:80] or default


def normalize_template_relative_path(value):
    raw_path = str(value or '').strip().replace('\\', '/')
    if not raw_path:
        raise UnsafeTemplatePath('图片路径不能为空')

    posix_path = PurePosixPath(raw_path)
    if posix_path.is_absolute() or PureWindowsPath(raw_path).is_absolute():
        raise UnsafeTemplatePath('图片路径不能是绝对路径')

    parts = posix_path.parts
    if any(part in ('', '.', '..') for part in parts):
        raise UnsafeTemplatePath('图片路径不能包含相对目录')
    if len(parts) != 2:
        raise UnsafeTemplatePath('图片路径必须是 分类/文件名 格式')

    category = sanitize_category(parts[0])
    filename = sanitize_image_filename(parts[1])
    return f'{category}/{filename}'


def safe_template_join(template_base, relative_path):
    normalized_path = normalize_template_relative_path(relative_path)
    base = Path(template_base).resolve(strict=False)
    target = (base / normalized_path).resolve(strict=False)
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise UnsafeTemplatePath('图片路径超出模板目录') from exc
    return target, normalized_path
