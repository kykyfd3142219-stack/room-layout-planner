import json
import os
import re
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:18080/index.html"


def start_server():
    proc = subprocess.Popen(
        ["python3", "-m", "http.server", "18080", "--bind", "127.0.0.1"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # wait for server
    for _ in range(30):
        time.sleep(0.2)
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(f"server exited: {out}")
        try:
            import urllib.request

            urllib.request.urlopen(URL, timeout=0.5)
            return proc
        except Exception:
            continue
    raise RuntimeError("server did not start in time")


def parse_selection_info(text: str):
    # format example: 1階 選択中: デスク / 位置 120,150cm / サイズ 120x60cm / 角度 0°
    m = re.search(r"位置\s*(\d+),(\d+)cm\s*/\s*サイズ\s*(\d+)x(\d+)cm\s*/\s*角度\s*(-?\d+)°", text)
    if not m:
        return None
    x, y, w, h, a = map(int, m.groups())
    return {"x": x, "y": y, "w": w, "h": h, "angle": a}


def parse_wall_info(text: str):
    # format example: 1階 選択中: 引き戸 / 上壁 / 開始 140cm / 長さ 90cm / 角度 0°
    m = re.search(r"/\s*(上|右|下|左)壁\s*/\s*開始\s*(\d+)cm\s*/\s*長さ\s*(\d+)cm", text)
    if not m:
        return None
    side_map = {"上": "top", "右": "right", "下": "bottom", "左": "left"}
    return {"wall": side_map[m.group(1)], "pos": int(m.group(2)), "len": int(m.group(3))}


def canvas_point_for_item(page, item):
    data = page.evaluate(
        """
        ({x,y,w,h}) => {
          const canvas = document.getElementById('room');
          const roomW = Number(document.getElementById('roomW').value);
          const roomH = Number(document.getElementById('roomH').value);
          const attrW = canvas.width;
          const attrH = canvas.height;
          const pad = 28;
          const scale = Math.min((attrW - pad * 2) / roomW, (attrH - pad * 2) / roomH);
          const widthPx = roomW * scale;
          const heightPx = roomH * scale;
          const left = (attrW - widthPx) / 2;
          const top = (attrH - heightPx) / 2;
          const cx = left + (x + w / 2) * scale;
          const cy = top + (y + h / 2) * scale;
          const rect = canvas.getBoundingClientRect();
          const fx = rect.left + (cx / attrW) * rect.width;
          const fy = rect.top + (cy / attrH) * rect.height;
          return {fx, fy};
        }
        """,
        item,
    )
    return data["fx"], data["fy"]


def canvas_point_for_wall(page, wall, offset_cm=35):
    data = page.evaluate(
        """
        ({wall, pos, len, offsetCm}) => {
          const canvas = document.getElementById('room');
          const roomW = Number(document.getElementById('roomW').value);
          const roomH = Number(document.getElementById('roomH').value);
          const attrW = canvas.width;
          const attrH = canvas.height;
          const pad = 28;
          const scale = Math.min((attrW - pad * 2) / roomW, (attrH - pad * 2) / roomH);
          const widthPx = roomW * scale;
          const heightPx = roomH * scale;
          const left = (attrW - widthPx) / 2;
          const top = (attrH - heightPx) / 2;

          let cx = left;
          let cy = top;
          if (wall === 'top') {
            cx = left + (pos + len / 2) * scale;
            cy = top + offsetCm * scale;
          } else if (wall === 'bottom') {
            cx = left + (pos + len / 2) * scale;
            cy = top + heightPx - offsetCm * scale;
          } else if (wall === 'left') {
            cx = left + offsetCm * scale;
            cy = top + (pos + len / 2) * scale;
          } else {
            cx = left + widthPx - offsetCm * scale;
            cy = top + (pos + len / 2) * scale;
          }

          const rect = canvas.getBoundingClientRect();
          const fx = rect.left + (cx / attrW) * rect.width;
          const fy = rect.top + (cy / attrH) * rect.height;
          return {fx, fy};
        }
        """,
        {"wall": wall["wall"], "pos": wall["pos"], "len": wall["len"], "offsetCm": offset_cm},
    )
    return data["fx"], data["fy"]


def text(locator):
    return locator.inner_text().strip()


def wait_status(page):
    page.wait_for_timeout(100)
    return text(page.locator("#status"))


def run_checks(page):
    # Fresh start
    page.goto(URL, wait_until="domcontentloaded")
    # close tutorial if shown
    tutorial_btn = page.locator("#closeTutorial")
    if tutorial_btn.is_visible(timeout=500):
        tutorial_btn.click()

    # sanity: top guide and file bar
    expect(page.locator(".steps-title")).to_have_text("使い始めの3ステップ")
    expect(page.locator("#toggleTopBar")).to_be_visible()

    # room size apply check
    page.fill("#roomW", "300")
    page.fill("#roomH", "320")
    page.click("#applyRoom")
    assert page.input_value("#roomW") == "300"
    assert page.input_value("#roomH") == "320"

    # add furniture and verify selection info
    desk_value = page.eval_on_selector(
        "#preset",
        """(sel) => {
          const opt = [...sel.options].find(o => o.textContent.includes(' / デスク ('));
          return opt ? opt.value : null;
        }""",
    )
    assert desk_value is not None, "デスク option not found"
    page.select_option("#preset", value=str(desk_value))
    page.click("#add")
    info = text(page.locator("#selectionInfo"))
    parsed = parse_selection_info(info)
    assert parsed is not None, f"selection info parse failed: {info}"

    # keyboard movement
    before = parsed.copy()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowDown")
    info2 = text(page.locator("#selectionInfo"))
    parsed2 = parse_selection_info(info2)
    assert parsed2 is not None
    assert parsed2["x"] != before["x"] or parsed2["y"] != before["y"], (
        f"keyboard move failed before={before} after={parsed2}"
    )

    # drag movement
    x1, y1 = canvas_point_for_item(page, parsed2)
    page.mouse.move(x1, y1)
    page.mouse.down()
    page.mouse.move(x1 + 80, y1 + 50, steps=8)
    page.mouse.up()
    info3 = text(page.locator("#selectionInfo"))
    parsed3 = parse_selection_info(info3)
    assert parsed3 is not None
    assert parsed3["x"] != parsed2["x"] or parsed3["y"] != parsed2["y"], (
        f"drag move failed before={parsed2} after={parsed3}"
    )

    # selection size edit reflect
    page.fill("#selW", "140")
    page.fill("#selH", "70")
    page.click("#applySelection")
    info4 = text(page.locator("#selectionInfo"))
    parsed4 = parse_selection_info(info4)
    assert parsed4 is not None
    assert parsed4["w"] == 140 and parsed4["h"] == 70, (
        f"selection size apply failed: {parsed4}"
    )

    # duplicate works
    page.click("#duplicateSelected")
    items = page.locator(".list .item")
    assert items.count() >= 2, "duplicate did not add second item"

    # grid toggle and no-snap movement should still move by 1 cm-ish through selection edit
    page.uncheck("#snapToggle")
    page.fill("#selX", str(parsed4["x"] + 1))
    page.fill("#selY", str(parsed4["y"] + 1))
    page.click("#applySelection")
    info5 = text(page.locator("#selectionInfo"))
    parsed5 = parse_selection_info(info5)
    assert parsed5 is not None
    assert parsed5["x"] == parsed4["x"] + 1 and parsed5["y"] == parsed4["y"] + 1, (
        f"no-snap coordinate apply failed: {parsed4} -> {parsed5}"
    )

    # lock blocks edits
    lock_checkbox = page.locator("#blockList .block-item.active input[type='checkbox']").nth(1)
    lock_checkbox.check()
    expect(page.locator("#add")).to_be_disabled()
    st = wait_status(page)
    assert "ロック" in st, f"lock status not shown: {st}"

    # unlock and ensure add works
    lock_checkbox.uncheck()
    expect(page.locator("#add")).to_be_enabled()
    page.click("#add")
    assert page.locator(".list .item").count() >= 3

    # wall elements: sliding door and slide door selectable and addable
    page.select_option("#wallType", label="引き戸")
    page.click("#addWall")
    st2 = wait_status(page)
    assert "編集中" in st2 or "重な" in st2 or "ロック中" not in st2
    wall_before = parse_wall_info(text(page.locator("#selectionInfo")))
    assert wall_before is not None, "wall selection parse failed"
    wx, wy = canvas_point_for_wall(page, wall_before, offset_cm=35)
    page.mouse.move(wx, wy)
    page.mouse.down()
    if wall_before["wall"] in ["top", "bottom"]:
        page.mouse.move(wx + 110, wy, steps=8)
    else:
        page.mouse.move(wx, wy + 110, steps=8)
    page.mouse.up()
    wall_after = parse_wall_info(text(page.locator("#selectionInfo")))
    assert wall_after is not None, "wall selection lost during drag"
    assert wall_after["pos"] != wall_before["pos"], f"wall drag failed: {wall_before} -> {wall_after}"

    page.select_option("#wallType", label="スライドドア")
    page.click("#addWall")
    assert page.locator(".list .item").count() >= 5

    # room size change affects validation (shrink then oversize add blocked)
    page.fill("#roomW", "180")
    page.fill("#roomH", "180")
    page.click("#applyRoom")
    page.fill("#w", "220")
    page.fill("#h", "100")
    page.click("#add")
    st3 = wait_status(page)
    assert "部屋サイズを超える家具は追加できません" in st3, f"room size validation failed: {st3}"

    # grow again and add succeeds
    page.fill("#roomW", "360")
    page.fill("#roomH", "360")
    page.click("#applyRoom")
    page.fill("#w", "220")
    page.fill("#h", "100")
    page.click("#add")
    assert page.locator(".list .item").count() >= 6

    # regression: existing oversized furniture should be auto-fitted and remain movable
    page.fill("#w", "220")
    page.fill("#h", "100")
    page.click("#add")
    info_big = text(page.locator("#selectionInfo"))
    parsed_big = parse_selection_info(info_big)
    assert parsed_big is not None and parsed_big["w"] == 220

    page.fill("#roomW", "180")
    page.fill("#roomH", "180")
    page.click("#applyRoom")
    info_fit = text(page.locator("#selectionInfo"))
    parsed_fit = parse_selection_info(info_fit)
    assert parsed_fit is not None
    assert parsed_fit["w"] <= 180 and parsed_fit["h"] <= 180, f"oversized item not fitted: {parsed_fit}"

    before_move = parsed_fit.copy()
    moved = False
    for key in ["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown"]:
        page.keyboard.press(key)
        after_move_info = text(page.locator("#selectionInfo"))
        after_move = parse_selection_info(after_move_info)
        assert after_move is not None
        if after_move["x"] != before_move["x"] or after_move["y"] != before_move["y"]:
            moved = True
            break
    assert moved, f"fitted item still immovable before={before_move} after={after_move}"



def main():
    server = start_server()
    out = {"ok": False, "error": None}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 980})
            page = context.new_page()
            try:
                run_checks(page)
                out["ok"] = True
            except Exception as e:
                out["error"] = str(e)
                page.screenshot(path=str(ROOT / "debug-failure.png"), full_page=True)
                html = page.content()
                (ROOT / "debug-failure.html").write_text(html, encoding="utf-8")
                raise
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
