import re
import html as html_mod
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from xml.dom import minidom
from playwright.sync_api import sync_playwright

FICBOOK_URL_RE = re.compile(
    r"ficbook\.net/readfic/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+)",
    re.IGNORECASE
)


def extract_fic_id(text: str) -> str | None:
    m = FICBOOK_URL_RE.search(text)
    return m.group(1) if m else None


def _clean(text: str) -> str:
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = html_mod.unescape(text)
    text = text.replace('\xa0', ' ')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def fetch_ficbook(url_or_text: str) -> dict:
    fic_id = extract_fic_id(url_or_text)
    if not fic_id:
        raise ValueError("Не удалось извлечь ID. Формат: https://ficbook.net/readfic/XXXXXXX")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="ru-RU",
        )
        page = ctx.new_page()

        page.goto(f"https://ficbook.net/readfic/{fic_id}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        title = page.evaluate("""() => {
            let el = document.querySelector('h1.heading a') || document.querySelector('h1') || document.querySelector('[itemprop="name"]');
            return el ? el.innerText.trim() : '';
        }""") or f"fic_{fic_id}"

        author = page.evaluate("""() => {
            let el = document.querySelector('[itemprop="author"]') || document.querySelector('.author a') || document.querySelector('.author');
            return el ? el.innerText.trim() : 'Unknown';
        }""")

        description = page.evaluate("""() => {
            let el = document.querySelector('[itemprop="description"]') || document.querySelector('.part-description');
            return el ? el.innerText.trim() : '';
        }""")

        chapter_links = page.evaluate("""(ficId) => {
            let links = document.querySelectorAll(`a[href*="/readfic/${ficId}/"]`);
            let result = [];
            let seen = new Set();
            links.forEach(a => {
                let href = a.getAttribute('href');
                if (href && !seen.has(href)) {
                    seen.add(href);
                    result.push(href);
                }
            });
            return result;
        }""", fic_id)

        if not chapter_links:
            chapter_links = [f"/readfic/{fic_id}"]

        chapters = []
        total = len(chapter_links)

        for i, link in enumerate(chapter_links):
            full_url = f"https://ficbook.net{link}" if link.startswith("/") else f"https://ficbook.net/{link}"
            page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            ch_title = page.evaluate("""() => {
                let el = document.querySelector('.part-title') || document.querySelector('h2');
                return el ? el.innerText.trim() : '';
            }""")

            ch_text = page.evaluate("""() => {
                let el = document.querySelector('#content') ||
                         document.querySelector('.js-part-text') ||
                         document.querySelector('[itemprop="articleBody"]') ||
                         document.querySelector('.text');
                return el ? el.innerText.trim() : '';
            }""")

            if ch_text:
                if not ch_title and total > 1:
                    ch_title = f"Часть {i + 1}"
                chapters.append((ch_title, ch_text))

        browser.close()

    if not chapters:
        raise ValueError("Не удалось извлечь текст. Возможно, фанфик требует авторизацию или закрыт.")

    return {
        "title": title,
        "author": author,
        "description": description,
        "chapters": chapters,
    }


def _build_fb2(title: str, author: str, description: str, chapters: list[tuple[str, str]]) -> str:
    ns = "http://www.gribuser.ru/xml/fictionbook/2.0"
    fb2 = ET.Element("FictionBook", xmlns=ns)

    ET.SubElement(fb2, "stylesheet").text = "p { text-indent: 1.5em; margin: 0; }"

    desc_el = ET.SubElement(fb2, "description")
    ti = ET.SubElement(desc_el, "title-info")
    ET.SubElement(ti, "genre").text = "fanfiction"
    ET.SubElement(ti, "book-title").text = title

    a = ET.SubElement(ti, "author")
    ET.SubElement(a, "first-name").text = author
    ET.SubElement(a, "nickname").text = author

    if description:
        ann = ET.SubElement(ti, "annotation")
        for para in description.split("\n\n"):
            if para.strip():
                p = ET.SubElement(ann, "p")
                p.text = para.strip()

    ET.SubElement(ti, "lang").text = "ru"

    di = ET.SubElement(desc_el, "document-info")
    ET.SubElement(di, "program-used").text = "Book Converter Bot"
    da = ET.SubElement(di, "author")
    ET.SubElement(da, "nickname").text = "BookConverterBot"
    ET.SubElement(di, "id").text = f"ficbook-{title}"
    ET.SubElement(di, "version").text = "1.0"

    pi = ET.SubElement(desc_el, "publish-info")
    ET.SubElement(pi, "book-name").text = title
    ET.SubElement(pi, "publisher").text = "ficbook.net"

    body = ET.SubElement(fb2, "body")
    for ch_title, ch_text in chapters:
        if not ch_text:
            continue
        section = ET.SubElement(body, "section")
        if ch_title:
            st = ET.SubElement(section, "title")
            p = ET.SubElement(st, "p")
            p.text = ch_title
        for para in ch_text.split("\n\n"):
            if para.strip():
                p = ET.SubElement(section, "p")
                p.text = para.strip()

    ET.SubElement(fb2, "binary", id="logo", content_type="image/png")

    xml_str = ET.tostring(fb2, encoding="unicode", xml_declaration=False)
    xml_str = '<?xml version="1.0" encoding="utf-8"?>\n' + xml_str
    return minidom.parseString(xml_str).toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def _safe_title(title: str, fic_id: str) -> str:
    safe = re.sub(r'[^\w\s\-]', '', title).strip().replace(" ", "_")
    return safe if safe else f"fic_{fic_id}"


def save_ficbook_fb2(fic_data: dict, fic_id: str, dest_dir: str) -> str:
    fb2 = _build_fb2(fic_data["title"], fic_data["author"], fic_data["description"], fic_data["chapters"])
    filename = f"{_safe_title(fic_data['title'], fic_id)}.fb2"
    filepath = os.path.join(dest_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(fb2)
    return filepath


def save_ficbook_pdf(fic_data: dict, fic_id: str, dest_dir: str) -> str:
    fb2_path = save_ficbook_fb2(fic_data, fic_id, dest_dir)
    pdf_path = fb2_path.replace(".fb2", ".pdf")
    result = subprocess.run(["ebook-convert", fb2_path, pdf_path], capture_output=True, timeout=300)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        raise RuntimeError(stderr or "ebook-convert failed")
    os.remove(fb2_path)
    return pdf_path
