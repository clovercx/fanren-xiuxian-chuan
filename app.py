"""凡人修仙传 - FastAPI 后端"""
import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from game_engine import (
    create_initial_state, apply_effect, can_advance_cultivation,
    advance_cultivation, check_choice_visible, check_conditions
)
from game_data import SCENES, GAME_TITLE, GAME_SUBTITLE, GAME_CHAPTERS

app = FastAPI(title=GAME_TITLE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SAVE_DIR = os.path.join(os.path.dirname(__file__), "saves")
os.makedirs(SAVE_DIR, exist_ok=True)


class ChoiceRequest(BaseModel):
    choice_index: int
    player_name: Optional[str] = None


class SaveRequest(BaseModel):
    slot: int = 1
    state: dict


@app.get("/api/info")
def get_game_info():
    return {
        "title": GAME_TITLE,
        "subtitle": GAME_SUBTITLE,
        "chapters": GAME_CHAPTERS,
        "total_chapters": len(GAME_CHAPTERS),
    }


@app.get("/api/init")
def init_new_game():
    state = create_initial_state()
    return {
        "state": state,
        "scene": _process_scene(SCENES["start"]),
        "can_advance": can_advance_cultivation(state),
    }


@app.get("/api/saves")
def list_saves():
    saves = {}
    for fname in sorted(os.listdir(SAVE_DIR)):
        if fname.endswith(".json"):
            slot = int(fname.replace("save_", "").replace(".json", ""))
            with open(os.path.join(SAVE_DIR, fname)) as f:
                data = json.load(f)
            saves[slot] = {
                "scene": data.get("current_scene", "unknown"),
                "cultivation": data.get("cultivation", "凡人"),
                "turn_count": data.get("turn_count", 0),
                "chapter": data.get("chapter", 1),
                "timestamp": os.path.getmtime(os.path.join(SAVE_DIR, fname)),
            }
    return {"saves": saves}


@app.get("/api/save/{slot}")
def load_save(slot: int):
    path = os.path.join(SAVE_DIR, f"save_{slot}.json")
    if not os.path.exists(path):
        raise HTTPException(404, "存档不存在")
    with open(path) as f:
        state = json.load(f)
    scene_id = state.get("current_scene", "start")
    scene = SCENES.get(scene_id) or SCENES["start"]
    return {
        "state": state,
        "scene": _process_scene(scene, state),
        "can_advance": can_advance_cultivation(state),
    }


@app.post("/api/save/{slot}")
def save_game(slot: int, data: dict = None):
    """保存游戏"""
    body = data or {}
    state = body.get("state")
    if not state:
        raise HTTPException(400, "需要提供游戏状态")
    path = os.path.join(SAVE_DIR, f"save_{slot}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return {"success": True, "slot": slot, "chapter": state.get("chapter", 1)}


@app.post("/api/state")
def handle_choice(req: ChoiceRequest):
    state = create_initial_state()  # will be replaced by actual state from body
    # We'll receive the full state from the frontend
    return {"error": "use POST /api/action instead"}


@app.post("/api/action")
def handle_action(data: dict):
    """Handle player choice and return new state + scene"""
    state = data.get("state", create_initial_state())
    choice_idx = data.get("choice_index", 0)
    scene_id = state.get("current_scene", "start")
    player_name = data.get("player_name", "")

    if player_name:
        state["name"] = player_name

    scene = SCENES.get(scene_id)
    if not scene:
        raise HTTPException(400, f"场景不存在: {scene_id}")

    choices = scene.get("choices", [])
    visible_choices = _get_visible_choices(choices, state)
    # Also filter by conditions
    filtered = []
    for c in visible_choices:
        conditions = c.get("conditions", None)
        if check_choice_visible(state, conditions):
            filtered.append(c)
    visible_choices = filtered

    if choice_idx < 0 or choice_idx >= len(visible_choices):
        raise HTTPException(400, f"无效的选择: {choice_idx}")

    choice = visible_choices[choice_idx]
    effects = choice.get("effects", {})
    state = apply_effect(state, effects)

    next_scene_id = choice.get("next", "start")
    state["current_scene"] = next_scene_id

    next_scene = SCENES.get(next_scene_id)
    if not next_scene:
        next_scene = SCENES["start"]
        state["current_scene"] = "start"

    # Auto-advance cultivation check (only if conditions met)
    next_realm = can_advance_cultivation(state)
    if next_realm and state.get("auto_advance", True):
        state = advance_cultivation(state)

    chapter = next_scene.get("chapter", 1)
    state["chapter"] = chapter

    return {
        "state": state,
        "scene": _process_scene(next_scene, state),
        "applied_effects": effects,
        "can_advance": can_advance_cultivation(state),
    }


@app.post("/api/advance")
def force_advance(data: dict):
    """强制突破境界"""
    state = data.get("state", create_initial_state())
    next_realm = can_advance_cultivation(state)
    if not next_realm:
        raise HTTPException(400, "当前无法突破")
    state = advance_cultivation(state)
    return {
        "state": state,
        "message": f"恭喜突破至【{next_realm}】！",
        "new_realm": next_realm,
        "can_advance": can_advance_cultivation(state),
    }


def _process_scene(scene, state=None):
    """为前端加工场景数据"""
    if not scene:
        return None
    choices = scene.get("choices", [])
    visible_choices = _get_visible_choices(choices, state or create_initial_state())
    return {
        "id": scene.get("id", ""),
        "chapter": scene.get("chapter", 1),
        "text": scene.get("text", []),
        "choices": visible_choices,
        "is_end": scene.get("is_end", False),
    }


def _get_visible_choices(choices, state):
    """过滤可见选项并加上索引"""
    result = []
    for i, c in enumerate(choices):
        conditions = c.get("conditions", None)
        if check_choice_visible(state, conditions):
            result.append({
                "index": i,
                "text": c["text"],
                "effects": c.get("effects", {}),
                "next": c.get("next", ""),
                "next_scene_name": SCENES.get(c.get("next", ""), {}).get("text", [""])[0] if c.get("next") else "",
            })
    return result


# 挂载静态文件
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    print(f"✨ {GAME_TITLE} 游戏服务器启动中...")
    print(f"🌐 http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
