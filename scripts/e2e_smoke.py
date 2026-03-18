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
    # format example:
    # 1階 いま選んでいるもの: デスク / 場所 120,150cm / 大きさ 120x60cm / 向き 0°
    # 1階 選択中: デスク / 位置 120,150cm / サイズ 120x60cm / 角度 0°
    m = re.search(
        r"(?:位置|場所)\s*(\d+),(\d+)cm\s*/\s*(?:サイズ|大きさ)\s*(\d+)x(\d+)cm\s*/\s*(?:角度|向き)\s*(-?\d+)°",
        text,
    )
    if not m:
        return None
    x, y, w, h, a = map(int, m.groups())
    return {"x": x, "y": y, "w": w, "h": h, "angle": a}


def parse_wall_info(text: str):
    # format example:
    # 1階 いま選んでいるもの: 引き戸 / 上の壁 / はしから 140cm / 長さ 90cm / 向き 0°
    # 1階 選択中: 引き戸 / 上壁 / 開始 140cm / 長さ 90cm / 角度 0°
    m = re.search(r"/\s*(上|右|下|左)(?:の壁|壁)\s*/\s*(?:開始|はしから)\s*(\d+)cm\s*/\s*長さ\s*(\d+)cm", text)
    if not m:
        return None
    side_map = {"上": "top", "右": "right", "下": "bottom", "左": "left"}
    return {"wall": side_map[m.group(1)], "pos": int(m.group(2)), "len": int(m.group(3))}


def canvas_point_for_item(page, item):
    data = page.evaluate(
        """
        ({x,y,w,h}) => {
          const canvas = document.getElementById('room');
          const activeId = state.activeBlockId;
          const viewport = viewportByBlockId(activeId);
          const metrics = getMetrics(viewport);
          const attrW = canvas.width;
          const attrH = canvas.height;
          const scale = metrics.scale;
          const left = metrics.left;
          const top = metrics.top;
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
          const activeId = state.activeBlockId;
          const viewport = viewportByBlockId(activeId);
          const metrics = getMetrics(viewport);
          const attrW = canvas.width;
          const attrH = canvas.height;
          const scale = metrics.scale;
          const widthPx = metrics.widthPx;
          const heightPx = metrics.heightPx;
          const left = metrics.left;
          const top = metrics.top;

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

    # kitchenette presets exist and can be selected
    kitchen_value = page.eval_on_selector(
        "#preset",
        """(sel) => {
          const opt = [...sel.options].find(o => o.textContent.includes(' / ミニキッチン ('));
          return opt ? opt.value : null;
        }""",
    )
    sink_value = page.eval_on_selector(
        "#preset",
        """(sel) => {
          const opt = [...sel.options].find(o => o.textContent.includes(' / 流し台 ('));
          return opt ? opt.value : null;
        }""",
    )
    assert kitchen_value is not None, "ミニキッチン option not found"
    assert sink_value is not None, "流し台 option not found"

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
    assert ("固定" in st) or ("ロック" in st), f"lock status not shown: {st}"

    # unlock and ensure add works
    lock_checkbox.uncheck()
    expect(page.locator("#add")).to_be_enabled()
    page.click("#add")
    assert page.locator(".list .item").count() >= 3

    # wall elements: non-window types should be draggable
    wall_types = ["引き戸", "スライドドア", "コンセント", "テレビのコンセント", "物置", "クローゼット"]
    initial_item_count = page.locator(".list .item").count()
    for index, wall_label in enumerate(wall_types):
        page.select_option("#wallType", label=wall_label)
        if wall_label in ["コンセント", "テレビのコンセント"]:
            page.fill("#wallLen", "24")
        elif wall_label == "物置":
            page.fill("#wallLen", "100")
        elif wall_label == "クローゼット":
            page.fill("#wallLen", "180")
        else:
            page.fill("#wallLen", "90")
        page.select_option("#wallSide", value="top")
        page.click("#addWall")
        st2 = wait_status(page)
        assert "固定中" not in st2 and "ロック中" not in st2, f"unexpected lock state while adding wall: {st2}"
        wall_before = parse_wall_info(text(page.locator("#selectionInfo")))
        assert wall_before is not None, f"wall selection parse failed for {wall_label}"
        if wall_label in ["コンセント", "テレビのコンセント", "物置", "クローゼット"]:
            page.keyboard.press("ArrowRight")
            wall_after = parse_wall_info(text(page.locator("#selectionInfo")))
            assert wall_after is not None, f"wall selection lost during nudge for {wall_label}"
            assert wall_after["pos"] != wall_before["pos"], (
                f"{wall_label} keyboard move failed: {wall_before} -> {wall_after}"
            )
            assert page.locator(".list .item").count() >= initial_item_count + index + 1
            continue
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(100)
        # keep offset inside expanded interaction zone for non-window wall elements
        offset_cm = 35 if wall_label in ["引き戸", "スライドドア", "物置"] else 20
        wx, wy = canvas_point_for_wall(page, wall_before, offset_cm=offset_cm)
        page.mouse.move(wx, wy)
        page.mouse.down()
        page.mouse.move(wx + 110, wy, steps=8)
        page.mouse.up()
        wall_after = parse_wall_info(text(page.locator("#selectionInfo")))
        assert wall_after is not None, f"wall selection lost during drag for {wall_label}"
        assert wall_after["pos"] != wall_before["pos"], (
            f"{wall_label} drag failed: {wall_before} -> {wall_after}"
        )
        assert page.locator(".list .item").count() >= initial_item_count + index + 1

    # warnings for door threshold / trajectory (only sliding door types)
    page.once("dialog", lambda d: d.accept())
    page.click("#clear")
    page.select_option("#wallType", label="引き戸")
    page.select_option("#wallSide", value="top")
    page.fill("#wallLen", "90")
    page.click("#addWall")
    warning_wall = parse_wall_info(text(page.locator("#selectionInfo")))
    assert warning_wall is not None
    page.fill("#w", "60")
    page.fill("#h", "60")
    page.click("#add")
    page.fill("#selX", str(warning_wall["pos"]))
    page.fill("#selY", "0")
    page.click("#applySelection")
    warning_status = wait_status(page)
    assert ("可動軌道" in warning_status) or ("敷居" in warning_status), (
        f"door warning not shown: {warning_status}"
    )

    # non-door wall elements should not trigger the same warning
    page.once("dialog", lambda d: d.accept())
    page.click("#clear")
    page.select_option("#wallType", label="窓")
    page.select_option("#wallSide", value="top")
    page.fill("#wallLen", "90")
    page.click("#addWall")
    non_warning_wall = parse_wall_info(text(page.locator("#selectionInfo")))
    assert non_warning_wall is not None
    page.fill("#w", "60")
    page.fill("#h", "60")
    page.click("#add")
    page.fill("#selX", str(non_warning_wall["pos"]))
    page.fill("#selY", "0")
    page.click("#applySelection")
    non_warning_status = wait_status(page)
    assert ("可動軌道" not in non_warning_status) and ("敷居" not in non_warning_status), (
        f"non-door warning should not appear: {non_warning_status}"
    )

    # room size change affects validation (shrink then oversize add blocked)
    page.fill("#roomW", "180")
    page.fill("#roomH", "180")
    page.click("#applyRoom")
    page.fill("#w", "220")
    page.fill("#h", "100")
    page.click("#add")
    st3 = wait_status(page)
    assert (
        "部屋サイズを超える家具は追加できません" in st3
        or "家具が大きすぎる" in st3
    ), f"room size validation failed: {st3}"

    # grow again and add succeeds
    page.fill("#roomW", "360")
    page.fill("#roomH", "360")
    page.click("#applyRoom")
    page.fill("#w", "220")
    page.fill("#h", "100")
    before_count = page.locator(".list .item").count()
    page.click("#add")
    assert page.locator(".list .item").count() == before_count + 1

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
