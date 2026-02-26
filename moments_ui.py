"""
moments_ui.py - WeChat Moments UI automation primitives.

Handles all low-level interaction with the WeChat desktop client:
desktop activation, mouse clicks, image preview, save-as dialogs.
"""

import time
import os
import ctypes
import logging
import subprocess

import win32api
import win32con
from wxauto import uiautomation as uia

log = logging.getLogger("moments")

# -- Win32 constants ---------------------------------------------------------
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP   = 0x0202
MK_LBUTTON     = 0x0001
CF_UNICODETEXT  = 13
GMEM_MOVEABLE   = 0x0002

# -- WeChat control names ----------------------------------------------------
IMG_BUTTON_NAME  = "\u56fe\u7247"           # "图片"
SAVE_AS_BTN_NAME = "\u53e6\u5b58\u4e3a..."  # "另存为..."
PREVIEW_CLASS    = "ImagePreviewWnd"
MOMENTS_CLASS    = "SnsWnd"
SAVE_DLG_CLASS   = "#32770"

# -- ctypes setup (once at module load) --------------------------------------
_user32  = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_kernel32.GlobalAlloc.restype  = ctypes.c_void_p
_kernel32.GlobalLock.restype   = ctypes.c_void_p
_kernel32.GlobalLock.argtypes  = [ctypes.c_void_p]
_kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
_user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


# ===========================================================================
#  Desktop activation (for Docker / headless Windows VMs)
# ===========================================================================

def activate_desktop():
    """Redirect the current RDP session to the console display via tscon.

    In Docker-hosted Windows VMs the desktop is disconnected by default,
    causing SetCursorPos / SendInput to fail.  ``tscon <sid> /dest:console``
    reconnects the session to the QEMU virtual display so that mouse
    automation works normally.
    """
    sid = ctypes.c_ulong(0)
    ctypes.windll.kernel32.ProcessIdToSessionId(
        os.getpid(), ctypes.byref(sid),
    )
    try:
        r = subprocess.run(
            ["tscon", str(sid.value), "/dest:console"],
            capture_output=True, timeout=10,
        )
        log.info("tscon session %d -> console (exit=%d)", sid.value, r.returncode)
    except Exception as e:
        log.warning("tscon failed: %s", e)

    time.sleep(2)

    try:
        win32api.SetCursorPos((100, 100))
        log.info("SetCursorPos OK - desktop is active")
        return True
    except Exception:
        log.warning("SetCursorPos still fails after tscon")
        return False


# ===========================================================================
#  Low-level click helpers
# ===========================================================================

def mouse_click(x, y):
    """Move cursor and perform a left click via win32api."""
    win32api.SetCursorPos((x, y))
    time.sleep(0.15)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def msg_click(hwnd, screen_x, screen_y):
    """Click by posting WM_LBUTTONDOWN/UP to *hwnd* (no cursor movement)."""
    pt = POINT(screen_x, screen_y)
    _user32.ScreenToClient(hwnd, ctypes.byref(pt))
    lp = ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)
    _user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    time.sleep(0.05)
    _user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)


def smart_click(x, y, fallback_hwnd=None):
    """Try mouse_click first; fall back to msg_click on failure."""
    try:
        mouse_click(x, y)
    except Exception:
        if fallback_hwnd:
            log.info("SetCursorPos failed, falling back to PostMessage")
            msg_click(fallback_hwnd, x, y)
        else:
            raise


# ===========================================================================
#  UIA geometry helpers
# ===========================================================================

def btn_center(ctrl):
    """Return (cx, cy) of a control's bounding rectangle."""
    r = ctrl.BoundingRectangle
    return (r.left + r.right) // 2, (r.top + r.bottom) // 2


def scroll_into_view(btn, feed_list, margin=50, max_tries=10):
    """Scroll *feed_list* until *btn* is visible; return its center."""
    fr = feed_list.BoundingRectangle
    for _ in range(max_tries):
        cx, cy = btn_center(btn)
        if fr.top + margin <= cy <= fr.bottom - margin:
            return cx, cy
        if cy < fr.top + margin:
            feed_list.WheelUp(wheelTimes=3)
        else:
            feed_list.WheelDown(wheelTimes=3)
        time.sleep(0.8)
    return btn_center(btn)


# ===========================================================================
#  Image button discovery
# ===========================================================================

def find_img_buttons(control, _depth=0, _max=10):
    """Recursively collect all ButtonControls named '图片' under *control*."""
    if _depth > _max:
        return []
    results = []
    try:
        for child in control.GetChildren():
            if child.ControlTypeName == "ButtonControl" and child.Name == IMG_BUTTON_NAME:
                results.append(child)
            else:
                results.extend(find_img_buttons(child, _depth + 1, _max))
    except Exception:
        pass
    return results


# ===========================================================================
#  Image preview lifecycle
# ===========================================================================

def open_image_preview(btn, feed_list=None, sns_hwnd=None):
    """Click an image thumbnail and wait for the preview window (with retry)."""
    for attempt in range(2):
        if feed_list:
            cx, cy = scroll_into_view(btn, feed_list)
        else:
            cx, cy = btn_center(btn)
        log.info("Img btn at (%d,%d) attempt=%d", cx, cy, attempt + 1)
        if attempt > 0 and sns_hwnd:
            _user32.SetForegroundWindow(sns_hwnd)
            time.sleep(0.5)
        smart_click(cx, cy, sns_hwnd)
        time.sleep(3)
        preview = uia.WindowControl(ClassName=PREVIEW_CLASS, searchDepth=1)
        if preview.Exists(5):
            return preview
        log.warning("Preview not found (attempt %d)", attempt + 1)
    return None


def close_preview():
    """Close the image preview if it is open."""
    try:
        p = uia.WindowControl(ClassName=PREVIEW_CLASS, searchDepth=1)
        if p.Exists(0.5):
            p.SendKeys("{Escape}")
            for _ in range(10):
                time.sleep(0.5)
                if not uia.WindowControl(ClassName=PREVIEW_CLASS, searchDepth=1).Exists(0.3):
                    break
            time.sleep(0.5)
    except Exception:
        pass


def close_dialog():
    """Dismiss any open standard dialog (#32770)."""
    try:
        d = uia.WindowControl(ClassName=SAVE_DLG_CLASS, searchDepth=1)
        if d.Exists(0.3):
            d.SendKeys("{Escape}")
            time.sleep(0.3)
    except Exception:
        pass


# ===========================================================================
#  Clipboard helper
# ===========================================================================

def clipboard_set(text):
    """Write *text* to the system clipboard (CF_UNICODETEXT)."""
    _user32.OpenClipboard(0)
    _user32.EmptyClipboard()
    data = text.encode("utf-16-le") + b"\x00\x00"
    h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    p = _kernel32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    _kernel32.GlobalUnlock(h)
    _user32.SetClipboardData(CF_UNICODETEXT, h)
    _user32.CloseClipboard()


# ===========================================================================
#  Save-As flow
# ===========================================================================

def click_save_as(preview):
    """Click the toolbar '另存为...' button and return the save dialog.

    WeChat hosts the save dialog as a *child window* of the preview,
    so we search both the desktop level and inside the preview tree.
    """
    time.sleep(3)
    try:
        preview.SetFocus()
    except Exception:
        pass
    time.sleep(0.5)

    save_btn = preview.ButtonControl(Name=SAVE_AS_BTN_NAME)
    if not save_btn.Exists(2):
        log.warning("'%s' button not found in preview", SAVE_AS_BTN_NAME)
        return None

    cx, cy = btn_center(save_btn)
    log.info("SaveAs toolbar btn at (%d,%d)", cx, cy)
    smart_click(cx, cy, preview.NativeWindowHandle)
    time.sleep(3)

    # Strategy 1: top-level dialog
    dlg = uia.WindowControl(ClassName=SAVE_DLG_CLASS, searchDepth=1)
    if dlg.Exists(3):
        log.info("Save dialog found at desktop level")
        return dlg

    # Strategy 2: named child window of the preview
    dlg = preview.WindowControl(Name=SAVE_AS_BTN_NAME)
    if dlg.Exists(3):
        log.info("Save dialog found as child of preview")
        return dlg

    # Strategy 3: scan direct children by name / class
    for ch in preview.GetChildren():
        if ch.ControlTypeName == "WindowControl":
            name = ch.Name or ""
            cls = ch.ClassName or ""
            if "\u53e6\u5b58" in name or SAVE_DLG_CLASS in cls:
                log.info("Save dialog child: [%s]", name)
                return ch

    log.warning("Save dialog did not appear")
    return None


def save_file_dialog(dlg, filepath):
    """Fill in the Windows Save dialog and confirm.

    Uses clipboard paste to avoid keyboard-layout issues with CJK paths.
    """
    clipboard_set(filepath)
    time.sleep(0.3)
    dlg.SendKeys("{Alt}n")        # focus filename field
    time.sleep(0.3)
    dlg.SendKeys("{Ctrl}a")       # select all
    time.sleep(0.1)
    dlg.SendKeys("{Ctrl}v")       # paste path from clipboard
    time.sleep(0.3)
    dlg.SendKeys("{Alt}s")        # click Save
    time.sleep(1.5)

    # handle "overwrite?" confirmation
    confirm = uia.WindowControl(ClassName=SAVE_DLG_CLASS, searchDepth=1)
    if confirm.Exists(0.5) and confirm.Name != SAVE_AS_BTN_NAME:
        confirm.SendKeys("{Alt}y")
        time.sleep(0.5)
