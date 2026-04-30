"""凡人修仙传 - 游戏引擎"""
import json
import random
from copy import deepcopy

# 修炼境界体系
REALMS = [
    ("凡人", 0),
    ("练气初期", 1), ("练气中期", 2), ("练气后期", 3),
    ("筑基初期", 4), ("筑基中期", 5), ("筑基后期", 6),
    ("结丹初期", 7), ("结丹中期", 8), ("结丹后期", 9),
    ("元婴初期", 10), ("元婴中期", 11), ("元婴后期", 12),
    ("化神初期", 13), ("化神中期", 14), ("化神后期", 15),
]

REALM_NAMES = [r[0] for r in REALMS]
REALM_LEVELS = {r[0]: r[1] for r in REALMS}


def create_initial_state():
    return {
        "name": "无名少年",
        "gender": "男",
        "hp": 100,
        "max_hp": 100,
        "spiritual_power": 0,
        "cultivation": "凡人",
        "spirit_stones": 0,
        "items": [],
        "techniques": [],
        "artifacts": [],
        "pills": [],
        "talent": 5,          # 根骨 (1-10)
        "comprehension": 5,   # 悟性 (1-10)
        "luck": 5,            # 气运 (1-10)
        "reputation": {},     # 各势力声望 {"七玄门": 0, ...}
        "current_scene": "start",
        "flags": {},          # 剧情标记
        "chapter": 1,
        "turn_count": 0,
        "alive": True,
    }


def apply_effect(state, effect):
    """应用选择效果到游戏状态"""
    if not effect:
        return state
    state = deepcopy(state)
    for key, value in effect.items():
        if key == "hp":
            state["hp"] = max(0, min(state["max_hp"], state["hp"] + value))
            if state["hp"] <= 0:
                state["alive"] = False
        elif key == "max_hp":
            state["max_hp"] = max(1, state["max_hp"] + value)
            state["hp"] = min(state["hp"], state["max_hp"])
        elif key == "spiritual_power":
            state["spiritual_power"] += value
        elif key == "spirit_stones":
            state["spirit_stones"] = max(0, state["spirit_stones"] + value)
        elif key == "talent":
            state["talent"] = max(1, min(10, state["talent"] + value))
        elif key == "comprehension":
            state["comprehension"] = max(1, min(10, state["comprehension"] + value))
        elif key == "luck":
            state["luck"] = max(1, min(10, state["luck"] + value))
        elif key == "add_item":
            if value not in state["items"]:
                state["items"].append(value)
        elif key == "remove_item":
            if value in state["items"]:
                state["items"].remove(value)
        elif key == "add_technique":
            if value not in state["techniques"]:
                state["techniques"].append(value)
        elif key == "add_artifact":
            if value not in state["artifacts"]:
                state["artifacts"].append(value)
        elif key == "add_pill":
            state["pills"].append(value)
        elif key == "cultivation":
            state["cultivation"] = value
        elif key == "set_flag":
            state["flags"][value] = True
        elif key == "clear_flag":
            state["flags"].pop(value, None)
        elif key in ["reputation"]:
            for faction, delta in value.items():
                state["reputation"][faction] = state["reputation"].get(faction, 0) + delta
    state["turn_count"] += 1
    return state


def can_advance_cultivation(state):
    """检查是否可以突破境界"""
    level = REALM_LEVELS.get(state["cultivation"], 0)
    if level >= len(REALMS) - 1:
        return None  # 已到最高境界
    next_realm = REALMS[level + 1][0]
    sp_needed = (level + 1) * 50
    talent_req = max(3, (level + 1) // 2)
    if state["spiritual_power"] >= sp_needed and state["talent"] >= talent_req:
        return next_realm
    return None


def advance_cultivation(state):
    """执行突破"""
    next_realm = can_advance_cultivation(state)
    if not next_realm:
        return state
    level = REALM_LEVELS.get(state["cultivation"], 0)
    sp_needed = (level + 1) * 50
    state = deepcopy(state)
    state["cultivation"] = next_realm
    state["spiritual_power"] -= sp_needed
    state["hp"] = state["max_hp"]  # 突破回满血
    state["max_hp"] += 20 * (level + 1)
    return state


def check_conditions(state, conditions):
    """检查场景进入条件"""
    if not conditions:
        return True
    for key, value in conditions.items():
        if key == "cultivation_min":
            if REALM_LEVELS.get(state["cultivation"], 0) < REALM_LEVELS.get(value, 0):
                return False
        elif key == "has_item":
            if value not in state["items"]:
                return False
        elif key == "has_technique":
            if value not in state["techniques"]:
                return False
        elif key == "flag":
            if not state["flags"].get(value):
                return False
        elif key == "no_flag":
            if state["flags"].get(value):
                return False
        elif key == "talent_min":
            if state["talent"] < value:
                return False
        elif key == "comprehension_min":
            if state["comprehension"] < value:
                return False
        elif key == "luck_min":
            if state["luck"] < value:
                return False
        elif key == "spirit_stones_min":
            if state["spirit_stones"] < value:
                return False
        elif key == "has_artifact":
            if value not in state["artifacts"]:
                return False
        elif key == "has_pill":
            if value not in state["pills"]:
                return False
        elif key == "chapter_min":
            if state["chapter"] < value:
                return False
    return True


def check_choice_visible(state, conditions):
    """检查选项是否可见"""
    return check_conditions(state, conditions)
