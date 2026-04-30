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

STATS_FILE = os.path.join(SAVE_DIR, "stats.json")


def _load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"play_count": 0, "messages": []}


def _save_stats(stats):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


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


# ── 游玩统计 ──


@app.get("/api/stats")
def get_stats():
    stats = _load_stats()
    return {"play_count": stats.get("play_count", 0)}


@app.post("/api/stats/play")
def record_play():
    stats = _load_stats()
    stats["play_count"] = stats.get("play_count", 0) + 1
    _save_stats(stats)
    return {"play_count": stats["play_count"]}


# ── 留言板 ──


@app.get("/api/messages")
def get_messages(limit: int = 50):
    stats = _load_stats()
    msgs = stats.get("messages", [])
    # 按时间倒序返回
    msgs_sorted = sorted(msgs, key=lambda m: m.get("timestamp", 0), reverse=True)
    return {"messages": msgs_sorted[:limit]}


@app.post("/api/messages")
def add_message(data: dict):
    name = (data.get("name") or "匿名道友").strip()
    content = (data.get("content") or "").strip()
    if not content:
        raise HTTPException(400, "留言内容不能为空")
    if len(content) > 500:
        raise HTTPException(400, "留言内容不能超过500字")
    stats = _load_stats()
    msg = {
        "id": len(stats.get("messages", [])) + 1,
        "name": name[:10],
        "content": content[:500],
        "timestamp": __import__("time").time(),
    }
    stats.setdefault("messages", []).append(msg)
    _save_stats(stats)
    return {"success": True, "message": msg}


@app.get("/api/init")
def init_new_game():
    state = create_initial_state()
    return {
        "state": state,
        "scene": _process_scene(SCENES["start"]),
        "can_advance": can_advance_cultivation(state),
    }


@app.post("/api/scene")
def load_scene(data: dict):
    """加载指定场景，不做选择"""
    defaults = create_initial_state()
    state = data.get("state", {})
    # 合并默认值，确保所有字段存在
    merged = {**defaults, **state}
    scene_id = data.get("scene_id", merged.get("current_scene", "start"))
    merged["current_scene"] = scene_id
    scene = SCENES.get(scene_id)
    if not scene:
        scene = SCENES["start"]
    chapter = scene.get("chapter", 1)
    merged["chapter"] = chapter
    return {
        "state": merged,
        "scene": _process_scene(scene, merged),
        "can_advance": can_advance_cultivation(merged),
    }


AUTO_SAVE_PATH = os.path.join(SAVE_DIR, "save_auto.json")


def _merge_state(saved_state):
    """将保存的状态与默认值合并，确保所有字段存在"""
    defaults = create_initial_state()
    return {**defaults, **(saved_state or {})}


@app.get("/api/auto-save")
def get_auto_save():
    """检查是否存在自动存档"""
    if not os.path.exists(AUTO_SAVE_PATH):
        return {"exists": False}
    with open(AUTO_SAVE_PATH) as f:
        raw = json.load(f)
    state = _merge_state(raw)
    scene_id = state.get("current_scene", "start")
    scene = SCENES.get(scene_id) or SCENES["start"]
    return {
        "exists": True,
        "state": state,
        "scene": _process_scene(scene, state),
        "can_advance": can_advance_cultivation(state),
        "timestamp": os.path.getmtime(AUTO_SAVE_PATH),
    }


@app.post("/api/auto-save")
def save_auto(data: dict):
    """自动存档"""
    state = data.get("state")
    if not state:
        raise HTTPException(400, "需要提供游戏状态")
    os.makedirs(os.path.dirname(AUTO_SAVE_PATH), exist_ok=True)
    with open(AUTO_SAVE_PATH, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return {"success": True}


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

    # 检查是否死亡
    if not state.get("alive", True):
        """玩家死亡，进入死亡画面"""
        return {
            "state": state,
            "scene": {
                "id": "__death__",
                "chapter": state.get("chapter", 1),
                "text": ["☠️ 道途已断", "",
                         "你的伤势过重，最终倒在了修仙之路上……",
                         "修仙界少了一个求道者，多了一堆枯骨。",
                         "",
                         "但大道五十，天衍四九，人遁其一。",
                         "或许，你还有重来一次的机会？"],
                "choices": [],
                "is_end": True,
                "is_death": True,
            },
            "applied_effects": effects,
            "can_advance": None,
        }

    next_scene_id = choice.get("next", "start")
    state["current_scene"] = next_scene_id

    next_scene = SCENES.get(next_scene_id)
    if not next_scene:
        next_scene = SCENES["start"]
        state["current_scene"] = "start"

    # 设置章节
    chapter = next_scene.get("chapter", 1)
    state["chapter"] = chapter

    return {
        "state": state,
        "scene": _process_scene(next_scene, state),
        "applied_effects": effects,
        "can_advance": can_advance_cultivation(state),
    }


@app.post("/api/check-advance")
def check_advance(data: dict):
    """仅检查是否可以突破，不执行"""
    state = data.get("state", create_initial_state())
    next_realm = can_advance_cultivation(state)
    if next_realm:
        return {"new_realm": next_realm}
    return {"new_realm": None}


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
            choice_data = {
                "index": i,
                "text": c["text"],
                "effects": c.get("effects", {}),
                "next": c.get("next", ""),
                "next_scene_name": SCENES.get(c.get("next", ""), {}).get("text", [""])[0] if c.get("next") else "",
            }
            # 传递选项暗示提示
            if "hint" in c:
                choice_data["hint"] = c["hint"]
            # 传递条件信息（用于展示）
            if conditions:
                cond_labels = []
                for k, v in conditions.items():
                    if k == "talent_min":
                        cond_labels.append(f"根骨≥{v}")
                    elif k == "comprehension_min":
                        cond_labels.append(f"悟性≥{v}")
                    elif k == "luck_min":
                        cond_labels.append(f"气运≥{v}")
                    elif k == "spirit_stones_min":
                        cond_labels.append(f"灵石≥{v}")
                    elif k == "has_item":
                        cond_labels.append(f"需要：【{v}】")
                    elif k == "has_technique":
                        cond_labels.append(f"需要：【{v}】")
                    elif k == "has_pill":
                        cond_labels.append(f"需要：{v}")
                    elif k == "has_artifact":
                        cond_labels.append(f"需要：{v}")
                    elif k == "cultivation_min":
                        cond_labels.append(f"境界≥{v}")
                    elif k == "reputation_min":
                        if isinstance(v, dict):
                            for f, mv in v.items():
                                cond_labels.append(f"声望·{f}≥{mv}")
                        else:
                            cond_labels.append(f"七玄门声望≥{v}")
                    elif k == "flag" or k == "no_flag" or k == "chapter_min":
                        pass  # 剧情条件不显示给玩家
                if cond_labels:
                    choice_data["condition_label"] = " ".join(cond_labels)
            result.append(choice_data)
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
