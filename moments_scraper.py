"""
moments_scraper - Periodically scrape WeChat Moments.

Browses the Moments feed, extracts text / metadata, downloads images
via the UI-automation layer in *moments_ui*, and stores everything to
a local JSON file + media folder.  Supports checkpoint-based resume.
"""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import os
import re
import json
import time
import hashlib
import logging
from datetime import datetime

from wxauto import WeChat
from wxauto import uiautomation as uia
import moments_ui as mui

# -- Configuration -----------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = os.path.join(BASE_DIR, 'moments_data')
LOG_FILE = os.path.join(SAVE_DIR, 'scraper.log')
DATA_FILE = os.path.join(SAVE_DIR, 'moments.json')
CHECKPOINT_FILE = os.path.join(SAVE_DIR, 'checkpoint.json')
MEDIA_DIR = os.path.join(SAVE_DIR, 'media')
INTERVAL = 60
MAX_CONSECUTIVE_EXISTING = 3

os.makedirs(MEDIA_DIR, exist_ok=True)

# -- Parsing patterns (compiled once) ----------------------------------------
_DATE_PAT = re.compile(r"\d{4}\u5e74\d{1,2}\u6708\d{1,2}\u65e5")  # YYYY年M月D日
_IMAGE_PAT = re.compile(r"\u5305\u542b(\d+)\u5f20\u56fe\u7247")    # 包含N张图片

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger('moments')


# -- Storage -------------------------------------------------------------
def make_id(author, text, image_count):
    """Stable ID from author + text + image_count (not relative time)."""
    return hashlib.md5(f"{author}|{text}|{image_count}".encode('utf-8')).hexdigest()


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()


def save_checkpoint(ids):
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(ids), f, ensure_ascii=False)


def append_moment(record):
    data = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except Exception:
                data = []
    data.append(record)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# -- Parsing -------------------------------------------------------------
def parse_moment(item):
    raw_name = item.Name
    if not raw_name or not raw_name.strip():
        return None
    uia.SetGlobalSearchTimeout(0)
    try:
        author_btn = item.ButtonControl()
        author = author_btn.Name if author_btn.Exists(0.1) else ''
        text_parts, time_str, image_count, video_count = [], '', 0, 0
        lines = [l.strip() for l in raw_name.split('\n') if l.strip()]
        if not lines:
            return None
        if lines[0].endswith(':'):
            author = lines[0][:-1]
            lines = lines[1:]
        for i in range(len(lines) - 1, -1, -1):
            if _DATE_PAT.search(lines[i]) or '前' in lines[i] or '昨天' in lines[i]:
                time_str = lines[i]
                lines = lines[:i]
                break
        for l in lines:
            m = _IMAGE_PAT.match(l)
            if m:
                image_count = int(m.group(1))
            elif '视频' in l:
                video_count = 1
            else:
                text_parts.append(l)
        return {
            'author': author, 'text': '\n'.join(text_parts), 'time': time_str,
            'image_count': image_count, 'video_count': video_count,
        }
    except Exception as e:
        log.warning(f"Failed to parse moment: {e}")
        return None
    finally:
        uia.SetGlobalSearchTimeout(10.0)


# -- Image saving -------------------------------------------------------
def save_images(item, moment_id, image_count, feed_list, sns_hwnd=None):
    if image_count == 0:
        return []
    media_dir = os.path.join(MEDIA_DIR, moment_id)
    os.makedirs(media_dir, exist_ok=True)
    saved = []
    try:
        uia.SetGlobalSearchTimeout(0)
        img_buttons = mui.find_img_buttons(item)
        uia.SetGlobalSearchTimeout(10.0)
        if not img_buttons:
            return saved
        log.info(f"Found {len(img_buttons)} image(s) for {moment_id}")
        for idx, btn in enumerate(img_buttons):
            try:
                preview = mui.open_image_preview(btn, feed_list, sns_hwnd)
                if not preview:
                    continue
                dlg = mui.click_save_as(preview)
                if not dlg:
                    mui.close_preview()
                    continue
                filepath = os.path.join(media_dir, f"{idx + 1}.jpg")
                mui.save_file_dialog(dlg, filepath)
                saved.append(os.path.relpath(filepath, SAVE_DIR))
                log.info(f"Saved: {filepath}")
                mui.close_preview()
            except Exception as e:
                log.warning(f"Failed to save image {idx+1}: {e}")
                mui.close_dialog()
                mui.close_preview()
    except Exception as e:
        log.warning(f"Failed to process images: {e}")
    return saved


# -- Scraper loop --------------------------------------------------------
def scrape_one_round(wx, scraped_ids):
    log.info("Opening moments...")
    old = uia.WindowControl(ClassName="SnsWnd", searchDepth=1)
    if old.Exists(0.5):
        old.SendKeys("{Escape}")
        time.sleep(1)
    wx.A_MomentsIcon.Click(simulateMove=False)
    time.sleep(3)
    sns_wnd = uia.WindowControl(ClassName="SnsWnd", searchDepth=1)
    if not sns_wnd.Exists(5):
        log.error("Cannot find moments window!")
        return 0
    feed_list = sns_wnd.ListControl()
    sns_hwnd = sns_wnd.NativeWindowHandle
    consecutive_existing = 0
    new_count = 0
    for _ in range(100):
        items = feed_list.GetChildren()
        for li in items:
            if li.ControlTypeName != 'ListItemControl':
                continue
            parsed = parse_moment(li)
            if parsed is None:
                continue
            mid = make_id(parsed['author'], parsed['text'], parsed['image_count'])
            if mid in scraped_ids:
                consecutive_existing += 1
                if consecutive_existing >= MAX_CONSECUTIVE_EXISTING:
                    log.info(f"Hit {MAX_CONSECUTIVE_EXISTING} consecutive known posts, stopping.")
                    mui.close_dialog()
                    mui.close_preview()
                    sns_wnd.SendKeys('{Escape}')
                    return new_count
                continue
            consecutive_existing = 0
            saved_media = save_images(li, mid, parsed['image_count'], feed_list, sns_hwnd)
            record = {
                'id': mid, 'author': parsed['author'], 'text': parsed['text'],
                'time': parsed['time'], 'image_count': parsed['image_count'],
                'video_count': parsed['video_count'], 'media': saved_media,
                'scraped_at': datetime.now().isoformat(),
            }
            append_moment(record)
            scraped_ids.add(mid)
            new_count += 1
            log.info(f"New: {parsed['author']} - {parsed['text'][:30]} ({parsed['time']})")
        feed_list.WheelDown(wheelTimes=5)
        time.sleep(1.5)
    mui.close_dialog()
    mui.close_preview()
    sns_wnd.SendKeys("{Escape}")
    return new_count


def main():
    log.info("=== Moments Scraper Started ===")
    mui.activate_desktop()
    wx = WeChat()
    scraped_ids = load_checkpoint()
    log.info(f"Loaded {len(scraped_ids)} known moment IDs")
    round_num = 0
    while True:
        round_num += 1
        log.info(f"=== Round {round_num} ===")
        try:
            new_count = scrape_one_round(wx, scraped_ids)
            save_checkpoint(scraped_ids)
            log.info(f"Round {round_num} done: {new_count} new, {len(scraped_ids)} total")
        except Exception as e:
            log.error(f"Round {round_num} failed: {e}", exc_info=True)
        log.info(f"Sleeping {INTERVAL}s...")
        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()
