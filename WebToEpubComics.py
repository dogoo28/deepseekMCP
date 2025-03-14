import os
import requests
from bs4 import BeautifulSoup
from ebooklib import epub
import logging
import re

# 設定 logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def fetch_manga_title(index_url):
    """從漫畫目錄頁面抓取漫畫名稱。"""
    try:
        response = requests.get(index_url)
        response.raise_for_status()  # 檢查 HTTP 錯誤
        soup = BeautifulSoup(response.content, 'html.parser')

        title_tag = soup.select_one('h1.comics-detail__title')
        if title_tag:
            return title_tag.text.strip()
        else:
            logging.warning(f"在 {index_url} 找不到漫畫標題")
            return "未知漫畫"
    except requests.exceptions.RequestException as e:
        logging.error(f"抓取漫畫標題失敗: {index_url}，錯誤: {e}")
        return "未知漫畫"


def fetch_manga_author(index_url):
    """從漫畫目錄頁面抓取作者名稱。"""
    try:
        response = requests.get(index_url)
        response.raise_for_status()  # 檢查 HTTP 錯誤
        soup = BeautifulSoup(response.content, 'html.parser')

        author_tag = soup.select_one('h2.comics-detail__author')
        if author_tag:
            return author_tag.text.strip()
        else:
            logging.warning(f"在 {index_url} 找不到漫畫作者")
            return "未知作者"
    except requests.exceptions.RequestException as e:
        logging.error(f"抓取漫畫作者失敗: {index_url}，錯誤: {e}")
        return "未知作者"


def fetch_chapter_links_and_titles(index_url):
    """從漫畫目錄頁面抓取所有章節連結和標題。"""
    try:
        response = requests.get(index_url)
        response.raise_for_status()  # 檢查 HTTP 錯誤
        soup = BeautifulSoup(response.content, 'html.parser')

        chapters = soup.select('a.comics-chapters__item')
        chapter_data = []
        for chapter in chapters:
            href = chapter.get('href')
            title = chapter.select_one('span').text if chapter.select_one('span') else "未知章節"
            if href:
                chapter_data.append((title, f"https://www.baozimh.com{href}"))
        return chapter_data
    except requests.exceptions.RequestException as e:
        logging.error(f"抓取章節連結失敗: {index_url}，錯誤: {e}")
        return []


def download_images(chapter_url, output_dir, session):
    """從章節頁面抓取所有圖片，支持多頁，並保存到指定資料夾。"""
    current_url = chapter_url
    image_paths = []

    while current_url:
        try:
            response = session.get(current_url)
            response.raise_for_status()  # 檢查 HTTP 錯誤
            soup = BeautifulSoup(response.content, 'html.parser')
            
            images = soup.find_all('img')
            image_urls = [
                img['data-src'] if 'data-src' in img.attrs else img['src']
                for img in images if 'src' in img.attrs or 'data-src' in img.attrs
            ]

            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            for idx, url in enumerate(image_urls, start=len(image_paths) + 1):
                try:
                    image_response = session.get(url)
                    image_response.raise_for_status()
                    file_path = os.path.join(output_dir, f"{idx:03}.jpg")
                    with open(file_path, 'wb') as f:
                        f.write(image_response.content)
                    image_paths.append(file_path)
                except requests.exceptions.RequestException as e:
                     logging.error(f"下載圖片失敗: {url}，錯誤: {e}")


            next_button = soup.find('a', string="點擊進入下一頁")
            if next_button and 'href' in next_button.attrs:
                current_url = f"https://www.baozimh.com{next_button['href']}"
            else:
                current_url = None
        except requests.exceptions.RequestException as e:
            logging.error(f"抓取章節頁面失敗: {current_url}，錯誤: {e}")
            current_url = None # 發生錯誤，停止繼續抓取下一頁

    return image_paths


def create_volume_epub(manga_title, volume_title, image_paths, output_dir):
    """根據單卷的圖片生成 EPUB 檔案，並保存到指定資料夾。"""
    book = epub.EpubBook()
    book.set_identifier(f"{manga_title}-{volume_title}")
    book.set_title(f"{manga_title} {volume_title}")
    book.set_language("zh")

    chapter = epub.EpubHtml(title=volume_title, file_name=f"{volume_title}.xhtml")
    content = ""
    for img_path in image_paths:
        img_tag = f'<img src="{os.path.basename(img_path)}" alt="{volume_title}" style="max-width:100%;"/>'
        content += img_tag + "<br>"

    chapter.content = content
    book.add_item(chapter)

    for image_path in image_paths:
        try:
             with open(image_path, 'rb') as img_file:
                image = epub.EpubItem(
                    uid=os.path.basename(image_path),
                    file_name=os.path.basename(image_path),
                    media_type="image/jpeg",
                    content=img_file.read()
                )
                book.add_item(image)
        except Exception as e:
            logging.error(f"載入圖片資源失敗: {image_path}，錯誤: {e}")
            
    book.toc = [epub.Link(chapter.file_name, chapter.title, chapter.title)]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav', chapter]

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    epub_file = os.path.join(output_dir, f"{manga_title}_{volume_title}.epub")
    try:
       epub.write_epub(epub_file, book)
       logging.info(f"EPUB saved as {epub_file}")
    except Exception as e:
         logging.error(f"生成 EPUB 失敗: {epub_file}，錯誤: {e}")


def slugify_filename(title):
    """
    將章節標題轉換為安全的檔案名稱。
    """
    # 移除不允許的字符並將空格轉換為底線
    title = re.sub(r'[<>:"/\\|?*]', '', title)
    title = re.sub(r'\s+', '_', title)
    return title


def download_manga(index_url):
    """主函數：下載整個漫畫並生成 EPUB 文件。"""
    manga_title = fetch_manga_title(index_url)
    manga_author = fetch_manga_author(index_url)
    logging.info(f"檢測到漫畫名稱：{manga_title}")
    logging.info(f"檢測到作者名稱：{manga_author}")

    OUTPUT_DIR = f"./{manga_title} - {manga_author}"

    chapters = fetch_chapter_links_and_titles(index_url)
    
    with requests.Session() as session:  # 使用 session
        for title, chapter_url in chapters:
            safe_title = slugify_filename(title)  # 安全的章節標題
            temp_image_dir = os.path.join(OUTPUT_DIR, "temp_images", safe_title)
            image_paths = download_images(chapter_url, temp_image_dir, session)
            create_volume_epub(manga_title, title, image_paths, OUTPUT_DIR)


if __name__ == "__main__":
    print("歡迎使用漫畫下載工具！")
    INDEX_URL = input("請輸入漫畫目錄頁的 URL：").strip()
    download_manga(INDEX_URL)