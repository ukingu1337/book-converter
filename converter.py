import os
import zipfile
import rarfile
import subprocess
import tempfile
import shutil
from pathlib import Path

SUPPORTED_FORMATS = {
    '.epub', '.pdf', '.mobi', '.fb2', '.docx',
    '.txt', '.rtf', '.djvu', '.cbz', '.cbr', '.html', '.odt'
}

ARCHIVE_FORMATS = {'.zip', '.rar'}


def is_archive(filepath: str) -> bool:
    ext = Path(filepath).suffix.lower()
    return ext in ARCHIVE_FORMATS


def extract_archive(filepath: str, dest: str) -> list[str]:
    ext = Path(filepath).suffix.lower()
    extracted = []

    if ext == '.zip':
        with zipfile.ZipFile(filepath, 'r') as zf:
            zf.extractall(dest)
            extracted = [os.path.join(dest, name) for name in zf.namelist()
                         if not name.endswith('/')]

    elif ext == '.rar':
        with rarfile.RarFile(filepath, 'r') as rf:
            rf.extractall(dest)
            extracted = [os.path.join(dest, name) for name in rf.namelist()
                         if not name.endswith('/')]

    return extracted


def find_book_files(files: list[str]) -> list[str]:
    return [f for f in files
            if Path(f).suffix.lower() in SUPPORTED_FORMATS
            and os.path.isfile(f)]


def _find_ebook_convert() -> str:
    for path in ["ebook-convert", "/usr/bin/ebook-convert", "/usr/local/bin/ebook-convert"]:
        if shutil.which(path):
            return path
    raise RuntimeError("ebook-convert не найден. Установи Calibre.")


def convert_file(input_path: str, output_format: str) -> str:
    output_dir = os.path.dirname(input_path)
    base = Path(input_path).stem
    output_path = os.path.join(output_dir, f"{base}.{output_format}")

    cmd = [
        _find_ebook_convert(),
        input_path,
        output_path,
    ]

    env = os.environ.copy()
    env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-gpu"
    env["QT_QPA_PLATFORM"] = "offscreen"

    result = subprocess.run(cmd, capture_output=True, timeout=300, env=env)

    stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""

    if result.returncode != 0:
        raise RuntimeError(stderr or stdout or "ebook-convert failed with unknown error")

    if not os.path.exists(output_path):
        raise RuntimeError("Conversion produced no output file")

    return output_path


def convert_book(input_path: str, output_format: str) -> str | list[str]:
    ext = Path(input_path).suffix.lower()

    if ext in ARCHIVE_FORMATS:
        tmpdir = tempfile.mkdtemp(prefix="bookconv_")
        try:
            extracted = extract_archive(input_path, tmpdir)
            books = find_book_files(extracted)

            if not books:
                raise ValueError("Архив не содержит книг в поддерживаемом формате")

            if len(books) == 1:
                result = convert_file(books[0], output_format)
                final = os.path.join(os.path.dirname(input_path),
                                     Path(books[0]).stem + f".{output_format}")
                shutil.move(result, final)
                return final
            else:
                results = []
                for book in books:
                    result = convert_file(book, output_format)
                    final = os.path.join(os.path.dirname(input_path),
                                         Path(book).stem + f".{output_format}")
                    shutil.move(result, final)
                    results.append(final)
                return results
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    else:
        result = convert_file(input_path, output_format)
        final = os.path.join(os.path.dirname(input_path),
                             Path(input_path).stem + f".{output_format}")
        shutil.move(result, final)
        return final
