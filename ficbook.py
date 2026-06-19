import cloudscraper
import re
import html as html_mod
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from xml.dom import minidom

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

FICBOOK_URL_RE = re.compile(
    r"ficbook\.net/readfic/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+)",
    re.IGNORECASE
)


def extract_fic_id(text: str) -> str | None:
    m = FICBOOK_URL_RE.search(text)
    return m.group(1) if m else None


def _make_scraper():
    return cloudscraper.create_scraper()


def _clean_html_to_text(raw_html: str) -> str:
    text = re.sub(r'<br\s*/?>', '\n', raw_html)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = html_mod.unescape(text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _parse_fic_info(scraper, fic_id: str) -> dict:
    url = f"https://ficbook.net/readfic/{fic_id}"
    resp = scraper.get(url, headers=HEADERS)
    if resp.status_code != 200:
        raise ValueError(f"Не удалось загрузить страницу ficbook #{fic_id}")

    html_text = resp.text

    title_m = re.search(r'<h1[^>]*class="heading"[^>]*>\s*<a[^>]*>([^<]+)</a>', html_text)
    if not title_m:
        title_m = re.search(r'itemprop="name">([^<]+)<', html_text)
    title = title_m.group(1).strip() if title_m else f"fic_{fic_id}"

    author_m = re.search(r'itemprop="author">([^<]+)<', html_text)
    author = author_m.group(1).strip() if author_m else "Unknown"

    desc_m = re.search(r'itemprop="description"[^>]*>(.*?)</div>', html_text, re.DOTALL)
    description = ""
    if desc_m:
        description = _clean_html_to_text(desc_m.group(1))

    fic_id_escaped = re.escape(fic_id)
    chapter_links = re.findall(
        rf'href="(/readfic/{fic_id_escaped}/\d+[^"]*)"', html_text
    )
    chapter_links = list(dict.fromkeys(chapter_links))

    if not chapter_links:
        chapter_links = [f"/readfic/{fic_id}"]

    return {
        "title": title,
        "author": author,
        "description": description,
        "chapter_links": chapter_links,
    }


def _parse_chapter(scraper, chapter_url: str) -> tuple[str, str]:
    full_url = f"https://ficbook.net{chapter_url}"
    resp = scraper.get(full_url, headers=HEADERS)
    if resp.status_code != 200:
        return ("", "")

    html_text = resp.text

    title_m = re.search(r'class="part-title[^"]*"[^>]*>(.*?)</(?:h2|div|span)', html_text, re.DOTALL)
    chapter_title = ""
    if title_m:
        chapter_title = _clean_html_to_text(title_m.group(1))

    text_m = re.search(
        r'id="content"\s+class="js-part-text[^"]*"[^>]*>(.*?)</div>\s*(?:<div class="part-comment)',
        html_text, re.DOTALL
    )
    if not text_m:
        text_m = re.search(
            r'class="js-part-text[^"]*"[^>]*itemprop="articleBody"[^>]*>(.*?)</div>',
            html_text, re.DOTALL
        )
    if not text_m:
        text_m = re.search(
            r'itemprop="articleBody"[^>]*>(.*?)</div>',
            html_text, re.DOTALL
        )

    chapter_text = ""
    if text_m:
        chapter_text = _clean_html_to_text(text_m.group(1))

    return (chapter_title, chapter_text)


def _build_fb2(title: str, author: str, description: str, chapters: list[tuple[str, str]]) -> str:
    ns = "http://www.gribuser.ru/xml/fictionbook/2.0"

    fb2 = ET.Element("FictionBook", xmlns=ns)

    styles = ET.SubElement(fb2, "stylesheet")
    styles.text = "p { text-indent: 1.5em; margin: 0; }"

    description_el = ET.SubElement(fb2, "description")
    title_info = ET.SubElement(description_el, "title-info")
    ET.SubElement(title_info, "genre").text = "fanfiction"
    ET.SubElement(title_info, "book-title").text = title

    author_el = ET.SubElement(title_info, "author")
    ET.SubElement(author_el, "first-name").text = author
    ET.SubElement(author_el, "nickname").text = author

    if description:
        annotation = ET.SubElement(title_info, "annotation")
        for para in description.split("\n\n"):
            para = para.strip()
            if para:
                p = ET.SubElement(annotation, "p")
                p.text = para

    ET.SubElement(title_info, "lang").text = "ru"

    document_info = ET.SubElement(description_el, "document-info")
    ET.SubElement(document_info, "program-used").text = "Book Converter Bot"
    doc_author = ET.SubElement(document_info, "author")
    ET.SubElement(doc_author, "nickname").text = "BookConverterBot"
    ET.SubElement(document_info, "id").text = f"ficbook-{title}"
    ET.SubElement(document_info, "version").text = "1.0"

    publish_info = ET.SubElement(description_el, "publish-info")
    ET.SubElement(publish_info, "book-name").text = title
    ET.SubElement(publish_info, "publisher").text = "ficbook.net"

    body = ET.SubElement(fb2, "body")

    for i, (ch_title, ch_text) in enumerate(chapters):
        if not ch_text:
            continue
        section = ET.SubElement(body, "section")
        if ch_title:
            section_title = ET.SubElement(section, "title")
            p = ET.SubElement(section_title, "p")
            p.text = ch_title

        paragraphs = ch_text.split("\n\n")
        for para in paragraphs:
            para = para.strip()
            if para:
                p = ET.SubElement(section, "p")
                p.text = para

    binary = ET.SubElement(fb2, "binary", id="logo", content_type="image/png")

    xml_str = ET.tostring(fb2, encoding="unicode", xml_declaration=False)
    xml_str = '<?xml version="1.0" encoding="utf-8"?>\n' + xml_str

    pretty = minidom.parseString(xml_str).toprettyxml(indent="  ", encoding="utf-8")
    return pretty.decode("utf-8")


def fetch_ficbook(url_or_text: str) -> dict:
    fic_id = extract_fic_id(url_or_text)
    if not fic_id:
        raise ValueError(
            "Не удалось извлечь ID фанфика. "
            "Формат: https://ficbook.net/readfic/XXXXXXX"
        )

    scraper = _make_scraper()
    info = _parse_fic_info(scraper, fic_id)

    chapters = []
    total = len(info["chapter_links"])
    for i, link in enumerate(info["chapter_links"]):
        ch_title, ch_text = _parse_chapter(scraper, link)
        if ch_text:
            if not ch_title and total > 1:
                ch_title = f"Часть {i + 1}"
            chapters.append((ch_title, ch_text))

    if not chapters:
        raise ValueError("Не удалось извлечь текст фанфика. Возможно, нужна авторизация.")

    return {
        "title": info["title"],
        "author": info["author"],
        "description": info["description"],
        "chapters": chapters,
    }


def _safe_title(title: str, fic_id: str) -> str:
    safe = re.sub(r'[^\w\s\-]', '', title).strip().replace(" ", "_")
    return safe if safe else f"fic_{fic_id}"


def save_ficbook_fb2(fic_data: dict, fic_id: str, dest_dir: str) -> str:
    fb2_content = _build_fb2(
        fic_data["title"], fic_data["author"],
        fic_data["description"], fic_data["chapters"]
    )
    filename = f"{_safe_title(fic_data['title'], fic_id)}.fb2"
    filepath = os.path.join(dest_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(fb2_content)
    return filepath


def save_ficbook_pdf(fic_data: dict, fic_id: str, dest_dir: str) -> str:
    fb2_path = save_ficbook_fb2(fic_data, fic_id, dest_dir)
    pdf_path = fb2_path.replace(".fb2", ".pdf")

    result = subprocess.run(
        ["ebook-convert", fb2_path, pdf_path],
        capture_output=True, timeout=300
    )

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        raise RuntimeError(stderr or "ebook-convert failed")

    os.remove(fb2_path)
    return pdf_path


def download_ficbook_fb2_sync(url_or_text: str, dest_dir: str) -> str:
    fic_id = extract_fic_id(url_or_text)
    if not fic_id:
        raise ValueError("Не удалось извлечь ID фанфика.")
    data = fetch_ficbook(url_or_text)
    return save_ficbook_fb2(data, fic_id, dest_dir)


def download_ficbook_pdf_sync(url_or_text: str, dest_dir: str) -> str:
    fic_id = extract_fic_id(url_or_text)
    if not fic_id:
        raise ValueError("Не удалось извлечь ID фанфика.")
    data = fetch_ficbook(url_or_text)
    return save_ficbook_pdf(data, fic_id, dest_dir)


async def download_ficbook_fb2(url_or_text: str, dest_dir: str) -> str:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, download_ficbook_fb2_sync, url_or_text, dest_dir)


async def download_ficbook_pdf(url_or_text: str, dest_dir: str) -> str:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, download_ficbook_pdf_sync, url_or_text, dest_dir)