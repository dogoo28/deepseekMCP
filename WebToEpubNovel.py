import requests
from bs4 import BeautifulSoup
from ebooklib import epub
import opencc
import time
import random
import re
import cloudscraper

# 初始化簡體轉繁體的轉換
cc = opencc.OpenCC('s2t')

# 動態輸入小說編號
novel_id = input("請輸入小說編號：").strip()
base_url = "https://uukanshu.cc"
novel_url = f"{base_url}/book/{novel_id}/"

scraper = cloudscraper.create_scraper()

try:
    # 嘗試抓取小說主頁面
    response = scraper.get(novel_url)
    response.raise_for_status()  # 確保請求成功，否則引發例外
except requests.exceptions.RequestException as e:
    print(f"無法連接到網站或抓取內容，請檢查小說編號是否正確。\n錯誤詳情：{e}")
    exit()

soup = BeautifulSoup(response.content, 'html.parser')

# 1. 抓取小說標題
try:
    title = soup.find('h1', class_='booktitle').text
    title = cc.convert(title)  # 轉換為繁體中文
except AttributeError:
    print("無法找到小說標題，請檢查小說編號是否正確。")
    exit()

# 2. 抓取作者
try:
    author = soup.find('a', class_='red').text
    author = cc.convert(author)
except AttributeError:
    print("無法找到作者資訊，請檢查小說編號是否正確。")
    exit()

# 3. 抓取封面圖片 URL
try:
    cover_url = soup.find('img', class_='thumbnail')['src']
    cover_url = f"{cover_url}"
except (AttributeError, KeyError):
    print("無法找到封面圖片 URL，請檢查小說編號是否正確。")
    exit()

# 4. 抓取小說簡介
try:
    intro_paragraph = soup.find('p', class_='bookintro')
    intro = intro_paragraph.text.strip()
    intro = cc.convert(intro)
except AttributeError:
    print("無法找到小說簡介，請檢查小說編號是否正確。")
    exit()

# 建立 EPUB 書籍
book = epub.EpubBook()
book.set_identifier('id123456')
book.set_title(title)
book.set_language('zh-tw')  # 設定為繁體中文（台灣地區語系）
book.add_author(author)

# 下載封面圖片並添加至 EPUB
cover_response = requests.get(cover_url)
cover_content = cover_response.content
book.set_cover("cover.jpg", cover_content)

# 添加簡介章節
intro_chapter = epub.EpubHtml(title='簡介', file_name='intro.xhtml', lang='zh-tw')
intro_chapter.content = f'<h1>簡介</h1><p>{intro}</p>'
book.add_item(intro_chapter)

# 5. 抓取章節列表
chapter_links = soup.find_all('dd')
total_chapters = len(chapter_links)
progress_interval = max(total_chapters // 20, 1)  # 每 5% 進度顯示一次，至少為 1

print(f"開始抓取章節內容，共有 {total_chapters} 章。")

chapters = []
for index, dd in enumerate(chapter_links, start=1):
    link = dd.find('a')
    if link and link['href']:
        chapter_title = cc.convert(link.text.strip())
        chapter_url = base_url + link['href']

        # 抓取每章內容
        def fetch_chapter_content(chapter_url, cc, max_retries=50):
            chapter_content = ""
            retries = 0
            while chapter_content == "" and retries < max_retries:
                chapter_response = scraper.get(chapter_url)

                # 檢查請求是否成功
                if chapter_response.status_code == 200:
                    chapter_soup = BeautifulSoup(chapter_response.content, 'html.parser')
                    chapter_content_tag = chapter_soup.select_one('div.readcotent.bbb.font-normal')

                    # 確認是否抓到章節內容
                    chapter_content = chapter_content_tag.text.strip() if chapter_content_tag else ""

                # 若內容為空，隨機延遲後重試
                if chapter_content == "":
                    time.sleep(random.uniform(1, 3))  # 延遲 1 到 3 秒
                    retries += 1  # 計算重試次數

            # 內容抓取成功後，轉換為正體中文
            if chapter_content:
                chapter_content = cc.convert(chapter_content)
            else:
                print(f"無法抓取 {chapter_url} 的章節內容，超出重試次數。")

            return chapter_content

        chapter_content = fetch_chapter_content(chapter_url, cc, max_retries=50)

        # 替換換行符號為段落
        formatted_content = re.sub(r'(\n)+', '</p><p>', chapter_content.replace("\n\r\n\u2003\u2003", "</p><p>"))

        # 創建章節並加入 EPUB
        chapter = epub.EpubHtml(title=chapter_title, file_name=f"{chapter_title}.xhtml", lang='zh-tw')
        chapter.content = f'<h1>{chapter_title}</h1><p>{formatted_content}</p>'
book.add_item(chapter)
        chapters.append(chapter)

        # 每隔進度間隔顯示一次進度
        if index % progress_interval == 0 or index == total_chapters:
            percent = (index / total_chapters) * 100
            print(f"已完成 {index}/{total_chapters} 章 ({percent:.2f}%)")

# 添加章節到書籍並生成目錄
book.toc = (epub.Link('intro.xhtml', '簡介', 'intro'), (epub.Section('章節列表'), chapters))
book.spine = ['nav', intro_chapter] + chapters

# 添加導航文件
book.add_item(epub.EpubNcx())
book.add_item(epub.EpubNav())

# 儲存 EPUB 文件
epub_file_name = f'{author} - {title}.epub'
epub.write_epub(epub_file_name, book, {})
print(f"EPUB 文件 '{epub_file_name}' 已成功生成！")
