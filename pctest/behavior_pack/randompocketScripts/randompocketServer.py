# -*- coding: utf-8 -*-
"""RandomPocket 服务端系统

口袋数据不依赖物品 NBT（引擎会拒绝写入带自定义 userData 的物品），
改为：
    - 口袋物品的 extraId 只存一个短标识：rb:<uid>
    - 口袋内容（刷新日 / 物品列表）存在玩家 ExtraData：rb_<uid>
这样既保证引擎一定能写入，物品移动后也仍能通过 uid 找回自己的内容。

功能：
1. 每过 1 个游戏日，只给该玩家身上【第一个还有空余容量】的口袋加入 1 个随机物品；
   其余口袋当天不刷新；全部满了则当天不刷新。
2. 口袋装满 10 格时切换为 pocket_full（红色贴图），显示名变为“随机口袋·已满”。
3. 右键口袋打开 10 格宝箱式容器界面，可自由存放/取出。
"""

import json
import random
import time

import mod.server.extraServerApi as serverApi

import randompocketScripts.loot_pool as loot_pool

ServerSystem = serverApi.GetServerSystemCls()
CompFactory = serverApi.GetEngineCompFactory()

try:
    _STRING_TYPES = (str, unicode)
except NameError:
    _STRING_TYPES = (str,)

# ============ 可配置项 ============
POCKET_ITEM = "randompocket:pocket"
POCKET_FULL_ITEM = "randompocket:pocket_full"
POCKET_ITEMS = (POCKET_ITEM, POCKET_FULL_ITEM)

ITEMS_PER_DAY = 1
MAX_POCKET_SLOTS = 10
DAY_TICKS = 24000
GRANT_KEY = "randompocket_granted"

CONTAINER_SCREEN = "randompocket_container.randompocket_container_screen"
CONTAINER_TITLE = "随机口袋"
UI_COLLECTION_TYPE = "netease_ui_container"

UID_TAG = "rb:"
STATE_PREFIX = "rb_"

MOD_NAMESPACE = "randompocket"
CLIENT_SYSTEM = "RandomPocketClientSystem"
SERVER_SYSTEM = "RandomPocketServerSystem"
SCREEN_EVENT = "rb_screen_event"

# 测试模式（/rp test 开启；会话内有效，退出后重置）
TEST_STATE_EVENT = "rb_test_state"
TEST_POOL_CHUNK_EVENT = "rb_test_pool_chunk"
TEST_POOL_REQUEST_EVENT = "rb_test_pool_request"
TEST_REFRESH_EVENT = "rb_test_refresh"
TEST_POOL_CHUNK_SIZE = 150
# 手机端无右键：客户端 HUD「打开口袋」按钮发来的打开请求
OPEN_REQUEST_EVENT = "rb_open_request"
# 服务端扫描后下发的按钮显隐状态（快捷栏有口袋则显示）
HUD_STATE_EVENT = "rb_hud_state"
# /rp ui 按钮调整模式：下发调整指令、下发/保存按钮位置大小配置
UI_ADJUST_EVENT = "rb_ui_adjust"
UI_CFG_EVENT = "rb_ui_cfg"
UI_CFG_SAVE_EVENT = "rb_ui_cfg_save"
UI_CFG_KEY = "rb_ui_cfg"
# ==================================

_levelId = None


def _LevelId():
    global _levelId
    if _levelId is None:
        _levelId = serverApi.GetLevelId()
    return _levelId


def _ItemName(it):
    """兼容 newItemName / itemName 两种物品字典键"""
    if not isinstance(it, dict):
        return ""
    return it.get("newItemName") or it.get("itemName") or ""


def _Nbt(value):
    """把引擎返回的 NBT 包装值还原成普通 Python 值"""
    if isinstance(value, dict):
        if "__type__" in value:
            inner = value.get("__value__")
            if value.get("__type__") in (9, 10):
                return _Nbt(inner)
            return inner
        return dict((k, _Nbt(v)) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return [_Nbt(v) for v in value]
    return value


def _LegacyState(item):
    """兼容旧版本写在 userData 里的 rb_uid / rb_day / rb_bag"""
    ud = item.get("userData")
    if not isinstance(ud, dict):
        return {}
    if "rb_day" in ud or "rb_bag" in ud or "rb_uid" in ud:
        return {
            "uid": _Nbt(ud.get("rb_uid")),
            "day": _Nbt(ud.get("rb_day")),
            "bag": _Nbt(ud.get("rb_bag")),
        }
    return {}


class RandomPocketServerSystem(ServerSystem):
    def __init__(self, namespace, systemName):
        ServerSystem.__init__(self, namespace, systemName)
        self._booted = set()
        self._warned = set()
        self._slotUid = {}         # (playerId, posType, slot) -> 兜底 uid
        self._extraIdFailed = set()
        self._lastDay = None
        self._lastScan = 0.0
        self._prevTicks = None
        self._wrapBonus = 0
        self._rtBase = None
        self._rtBaseDay = 0
        self._openPocket = {}      # playerId -> 当前打开的口袋 uid
        self._syncPending = set()
        self._useGuard = {}
        self._timerId = None
        self._pool = []            # 运行时物品奖池
        self._stackCache = {}      # 物品最大堆叠数缓存
        self._nameCache = {}       # 物品本地化名称缓存（测试面板用）
        self._testMode = set()     # 处于测试模式的玩家
        self._hudState = {}        # playerId -> 是否已通知客户端显示打开按钮
        self._cfgSent = set()      # 已下发过按钮配置的玩家
        self._slotBroken = False   # GetSelectSlotId 不可用时置 True，停止轮询手持

        # 任何一步失败都不能影响系统注册，否则所有事件和定时器都不会生效
        try:
            self._ListenEngineEvents()
        except Exception as e:
            print("[RandomPocket] listen error:", e)

        # 定时器：优先 Game 组件，失败再退回 ServerSystem 自带接口
        try:
            self._timerId = CompFactory.CreateGame(_LevelId()).AddRepeatedTimer(
                1.0, self.OnSecondTimer)
            print("[RandomPocket] timer(started) game comp")
        except Exception as e:
            print("[RandomPocket] game comp timer error:", e)
            try:
                self._timerId = self.AddRepeatedTimer(1.0, self.OnSecondTimer)
                print("[RandomPocket] timer(started) system")
            except Exception as e2:
                print("[RandomPocket] system timer error:", e2)
        try:
            self._EnsurePool()
        except Exception as e:
            print("[RandomPocket] pool init error:", e)
        print("[RandomPocket] server system started")

    def _ListenEngineEvents(self):
        engNs = serverApi.GetEngineNamespace()
        engSys = serverApi.GetEngineSystemName()
        for evtName in ("ServerItemTryUseEvent", "ServerItemUseOnEvent",
                        "ServerChatEvent", "CommandEvent",
                        "OnCarriedNewItemChangedServerEvent",
                        "PlayerTryAddCustomContainerItemServerEvent",
                        "PlayerTryPutCustomContainerItemServerEvent",
                        "PlayerTryRemoveCustomContainerItemServerEvent"):
            handler = getattr(self, evtName, None)
            if handler is not None:
                try:
                    self.ListenForEvent(engNs, engSys, evtName, self, handler)
                except Exception as e:
                    print("[RandomPocket] listen %s error: %s" % (evtName, e))
        try:
            serverApi.GetUserDataInEvent("ServerItemTryUseEvent")
        except Exception:
            pass
        try:
            serverApi.GetUserDataInEvent("ServerItemUseOnEvent")
        except Exception:
            pass
        # 客户端转发过来的界面打开/关闭事件
        try:
            self.ListenForEvent(MOD_NAMESPACE, CLIENT_SYSTEM, SCREEN_EVENT,
                                self, self.OnScreenEvent)
        except Exception as e:
            print("[RandomPocket] listen screen event error: %s" % e)
        # 测试面板请求 + 手机端打开请求
        for evtName, handler in ((TEST_POOL_REQUEST_EVENT, self.OnTestPoolRequest),
                                 (TEST_REFRESH_EVENT, self.OnTestRefresh),
                                 (OPEN_REQUEST_EVENT, self.OnOpenRequest),
                                 (UI_CFG_SAVE_EVENT, self.OnUiCfgSave)):
            try:
                self.ListenForEvent(MOD_NAMESPACE, CLIENT_SYSTEM, evtName,
                                    self, handler)
            except Exception as e:
                print("[RandomPocket] listen %s error: %s" % (evtName, e))

    def Destroy(self):
        try:
            if self._timerId:
                CompFactory.CreateGame(_LevelId()).CancelTimer(self._timerId)
        except Exception:
            pass
        try:
            ServerSystem.Destroy(self)
        except Exception:
            pass

    # ---------- 世界时间 ----------
    def _WorldClock(self):
        """返回 (day, ticks)；取不到返回 (None, None)"""
        try:
            raw = CompFactory.CreateTime(_LevelId()).GetTime()
        except Exception as e:
            print("[RandomPocket] GetTime error:", e)
            return None, None
        if isinstance(raw, (tuple, list)):
            print("[RandomPocket] GetTime tuple=%r" % (raw,))
            vals = []
            for v in raw:
                try:
                    vals.append(int(v))
                except Exception:
                    vals.append(0)
            if not vals:
                return None, None
            if len(vals) == 1:
                ticks = vals[0]
                return ticks // DAY_TICKS, ticks
            day, tod = vals[0], vals[1]
            if tod < 0 or tod >= DAY_TICKS:
                ticks = max(day, tod)
                return ticks // DAY_TICKS, ticks
            return day, day * DAY_TICKS + tod
        try:
            ticks = int(raw)
        except Exception as e:
            print("[RandomPocket] GetTime invalid:", e, repr(raw))
            return None, None
        return ticks // DAY_TICKS, ticks

    def _ClockDay(self):
        """综合世界时间与真实时间算出当前游戏日；完全取不到时返回 None"""
        now = time.time()
        day, ticks = self._WorldClock()
        if day is not None:
            if self._prevTicks is not None and ticks < self._prevTicks - DAY_TICKS // 6:
                self._wrapBonus += 1
            self._prevTicks = ticks
            day += self._wrapBonus
        if self._rtBase is None and day is not None:
            self._rtBase = now
            self._rtBaseDay = day
        if self._rtBase is not None:
            # 兜底：即使世界时间读不到或停住，每 20 分钟真实时间也推进一天
            rtDay = self._rtBaseDay + int((now - self._rtBase) / 1200.0)
            day = rtDay if day is None else max(day, rtDay)
        return day

    # ---------- 每秒轮询 ----------
    def OnSecondTimer(self, *args):
        try:
            # 轻量手持检测：切到口袋时让「打开」按钮亮 3 秒
            for pid in serverApi.GetPlayerList():
                self._CheckHeldPocket(pid)
            day = self._ClockDay()
            if day is None:
                return
            now = time.time()
            if day == self._lastDay and now - self._lastScan < 2.0:
                return
            self._lastDay = day
            self._lastScan = now
            self._RefreshAll(day)
        except Exception as e:
            print("[RandomPocket] timer error:", e)

    # ---------- 口袋身份与内容存储 ----------
    def _LoadState(self, playerId, uid):
        try:
            raw = CompFactory.CreateExtraData(playerId).GetExtraData(STATE_PREFIX + uid)
        except Exception as e:
            print("[RandomPocket] GetExtraData error:", e)
            return {}
        if isinstance(raw, _STRING_TYPES) and raw:
            try:
                data = json.loads(raw)
            except Exception as e:
                print("[RandomPocket] state json error:", e, repr(raw))
                return {}
            return data if isinstance(data, dict) else {}
        return {}

    def _StoreState(self, playerId, uid, state):
        try:
            ok = CompFactory.CreateExtraData(playerId).SetExtraData(
                STATE_PREFIX + uid, json.dumps(state))
        except Exception as e:
            print("[RandomPocket] SetExtraData error:", e)
            return False
        if not ok:
            print("[RandomPocket] SetExtraData returned False")
        return bool(ok)

    def _PocketUid(self, playerId, pt, slot, item):
        """优先读物品 extraId；读不到时分配一个并在本次游戏内缓存"""
        eid = item.get("extraId")
        if isinstance(eid, _STRING_TYPES) and eid.startswith(UID_TAG):
            return eid[len(UID_TAG):]
        key = (playerId, pt, slot)
        uid = self._slotUid.get(key)
        if not uid:
            uid = "%d%04d" % (int(time.time() * 1000), random.randint(0, 9999))
            self._slotUid[key] = uid
            print("[RandomPocket] assign uid %s to %s/%s" % (uid, pt, slot))
        self._WriteExtraId(playerId, pt, slot, item, uid)
        return uid

    def _WriteExtraId(self, playerId, pt, slot, item, uid):
        """把口袋的短标识写进物品 extraId（官方推荐 GetEntityItem + SetEntityItem）"""
        key = (playerId, pt, slot)
        if key in self._extraIdFailed:
            return False
        comp = CompFactory.CreateItem(playerId)
        tag = UID_TAG + uid

        # 以当前真实物品为基础改写，避免覆盖掉堆叠数等原有属性
        out = self._NormalizeItem(item)
        try:
            cur = comp.GetEntityItem(pt, slot, True)
            if isinstance(cur, dict) and cur:
                out = self._NormalizeItem(cur)
        except Exception as e:
            print("[RandomPocket] GetEntityItem extraId error:", e)
        out["extraId"] = tag

        try:
            if comp.SetEntityItem(pt, out, slot):
                return True
            print("[RandomPocket] SetEntityItem extraId returned False")
        except Exception as e:
            print("[RandomPocket] SetEntityItem extraId error:", e)
        try:
            if comp.ChangePlayerItemTipsAndExtraId(pt, slot, "", tag):
                return True
        except Exception as e:
            print("[RandomPocket] ChangePlayerItemTipsAndExtraId error:", e)
        self._extraIdFailed.add(key)
        print("[RandomPocket] extraId write failed %s/%s" % (pt, slot))
        return False

    def _State(self, playerId, pt, slot, item):
        """取出口袋状态（uid / day / bag），必要时迁移旧数据"""
        uid = self._PocketUid(playerId, pt, slot, item)
        state = self._LoadState(playerId, uid)
        if not state:
            legacy = _LegacyState(item)
            if legacy:
                legacy["uid"] = uid
                state = legacy
                self._StoreState(playerId, uid, state)
        if not state:
            state = {"uid": uid}
        state["uid"] = uid
        return state

    @staticmethod
    def _Bag(state):
        """口袋内容：dict，键为槽位号字符串，值为物品字典；旧版 list 自动迁移"""
        bag = state.get("bag")
        if isinstance(bag, dict):
            return bag
        if isinstance(bag, list):
            out = {}
            for i, it in enumerate(bag):
                if isinstance(it, dict) and _ItemName(it):
                    out[str(i)] = it
            return out
        return {}

    @staticmethod
    def _BagAdd(bag, item):
        """把物品放入第一个空槽位；满则返回 False"""
        for slot in range(MAX_POCKET_SLOTS):
            if str(slot) not in bag:
                bag[str(slot)] = item
                return True
        return False

    @staticmethod
    def _HandledToday(state, day):
        rbDay = state.get("day")
        if rbDay is None:
            return False
        try:
            return day <= int(rbDay)
        except Exception:
            return False

    @staticmethod
    def _CleanItem(it):
        return {
            "newItemName": _ItemName(it),
            "newAuxValue": it.get("newAuxValue", it.get("auxValue", 0)),
            "count": it.get("count", 1),
        }

    @staticmethod
    def _NormalizeItem(it):
        """把引擎返回的物品字典统一成写回槽位需要的格式"""
        out = {
            "newItemName": _ItemName(it),
            "newAuxValue": it.get("newAuxValue", it.get("auxValue", 0)),
            "count": it.get("count", 1),
        }
        eid = it.get("extraId")
        if isinstance(eid, _STRING_TYPES):
            out["extraId"] = eid
        return out

    # ---------- 奖池 ----------
    def _EnsurePool(self):
        """运行时读取当前游戏与已加载模组的物品，过滤后缓存为奖池"""
        if self._pool:
            return self._pool
        comp = CompFactory.CreateItem(_LevelId())
        # 优先创造栏物品（列表干净），取不到再退回全部已加载物品
        for flag, label in ((False, "creative"), (True, "all")):
            try:
                ids = comp.GetLoadItems(flag)
            except Exception as e:
                print("[RandomPocket] GetLoadItems(%s) error: %s" % (flag, e))
                continue
            pool = loot_pool.BuildPool(ids)
            if pool:
                self._pool = sorted(pool)
                print("[RandomPocket] pool %s items=%d" % (label, len(pool)))
                return self._pool
        self._pool = list(loot_pool.POOL)
        print("[RandomPocket] pool fallback items=%d" % len(self._pool))
        return self._pool

    def _MaxStack(self, name):
        """取物品最大堆叠数（带缓存），取不到返回 0"""
        if name in self._stackCache:
            return self._stackCache[name]
        limit = 0
        try:
            info = CompFactory.CreateItem(_LevelId()).GetItemBasicInfo(name, 0)
            if isinstance(info, dict):
                limit = int(info.get("maxStackSize") or 0)
        except Exception as e:
            print("[RandomPocket] GetItemBasicInfo error:", e)
        self._stackCache[name] = limit
        return limit

    def _RollItem(self):
        return loot_pool.RollItem(self._EnsurePool(), self._MaxStack)

    # ---------- 测试模式 ----------
    def ServerChatEvent(self, args):
        """聊天指令：/rp test、#rp test"""
        try:
            if not isinstance(args, dict):
                return
            if not self._HandleTestCommand(args.get("playerId"),
                                           args.get("message")):
                return
            args["cancel"] = True
        except Exception as e:
            print("[RandomPocket] chat event error:", e)

    def CommandEvent(self, args):
        """指令 Hook：/rp test"""
        try:
            if not isinstance(args, dict):
                return
            playerId = args.get("entityId") or args.get("playerId")
            raw = args.get("command")
            if isinstance(raw, _STRING_TYPES) and raw[:1] not in ("/", "#", "!", "！"):
                raw = "/" + raw
            if not self._HandleTestCommand(playerId, raw):
                return
            args["cancel"] = True
        except Exception as e:
            print("[RandomPocket] command event error:", e)

    def _HandleTestCommand(self, playerId, raw):
        """解析 /rp test [on|off]；匹配时返回 True 并已处理"""
        if not playerId or not isinstance(raw, _STRING_TYPES):
            return False
        text = raw.strip()
        if not text or text[0] not in ("/", "#", "!", "！"):
            return False
        words = text[1:].split()
        if not words or words[0].lower() != "rp":
            return False
        sub = [w.lower() for w in words[1:]]
        if sub and sub[0] == "ui":
            try:
                self.NotifyToClient(playerId, UI_ADJUST_EVENT, {})
            except Exception as e:
                print("[RandomPocket] ui adjust notify error:", e)
            self._Notify(playerId,
                         "[随机口袋] 按钮调整模式：拖动调位置，＋/－调大小，点「完成」保存")
            return True
        if sub and sub[0] != "test":
            return False
        want = None
        if len(sub) >= 2:
            if sub[1] in ("on", "true", "1", "开"):
                want = True
            elif sub[1] in ("off", "false", "0", "关"):
                want = False
        self._SetTestMode(playerId, want)
        return True

    def _SetTestMode(self, playerId, want=None):
        enabled = (playerId not in self._testMode) if want is None else bool(want)
        if enabled:
            self._testMode.add(playerId)
            self._Notify(playerId, "[随机口袋] 测试模式已开启：打开口袋后可查看奖池 / 刷新一天")
            self._SendTestState(playerId, True)
            self._SendPoolChunks(playerId)
        else:
            self._testMode.discard(playerId)
            self._Notify(playerId, "[随机口袋] 测试模式已关闭")
            self._SendTestState(playerId, False)
        print("[RandomPocket] test mode %s for %s" % (enabled, playerId))

    def _SendTestState(self, playerId, enabled):
        try:
            self.NotifyToClient(playerId, TEST_STATE_EVENT,
                                {"enabled": bool(enabled)})
        except Exception as e:
            print("[RandomPocket] notify test state error:", e)

    def _PoolEntry(self, name):
        """奖池条目：物品 ID + 本地化名称（GetItemBasicInfo 的 itemName），带缓存"""
        cn = self._nameCache.get(name)
        if cn is None:
            cn = ""
            try:
                info = CompFactory.CreateItem(_LevelId()).GetItemBasicInfo(name, 0)
                if isinstance(info, dict):
                    cn = info.get("itemName") or ""
            except Exception:
                pass
            self._nameCache[name] = cn
        return {"id": name, "name": cn}

    def _SendPoolChunks(self, playerId):
        pool = self._EnsurePool()
        size = TEST_POOL_CHUNK_SIZE
        total = max(1, (len(pool) + size - 1) // size)
        for index in range(total):
            try:
                part = pool[index * size:(index + 1) * size]
                self.NotifyToClient(playerId, TEST_POOL_CHUNK_EVENT, {
                    "index": index,
                    "total": total,
                    "items": [self._PoolEntry(n) for n in part],
                })
            except Exception as e:
                print("[RandomPocket] send pool chunk error:", e)
                return
        print("[RandomPocket] send pool to %s: %d items / %d chunks"
              % (playerId, len(pool), total))

    def OnTestPoolRequest(self, args):
        try:
            playerId = args.get("playerId")
            if playerId and playerId in self._testMode:
                self._SendPoolChunks(playerId)
        except Exception as e:
            print("[RandomPocket] test pool request error:", e)

    def OnTestRefresh(self, args):
        try:
            playerId = args.get("playerId")
            if playerId and playerId in self._testMode:
                self._TestRefresh(playerId)
        except Exception as e:
            print("[RandomPocket] test refresh error:", e)

    # ---------- 手机端 HUD「打开口袋」按钮 ----------
    def OnOpenRequest(self, args):
        """客户端点「打开口袋」按钮：优先打开手持的那个口袋，否则开身上第一个"""
        try:
            playerId = args.get("playerId") if isinstance(args, dict) else None
            if not playerId:
                return
            eid = args.get("extraId")
            if not isinstance(eid, _STRING_TYPES):
                eid = ""
            print("[RandomPocket] open request from hud button, eid=%r" % eid)
            entry = self._FindPocket(playerId, {"extraId": eid})
            if entry is None:
                self._Notify(playerId, "[随机口袋] 你身上没有口袋")
                return
            self._OpenPocket(playerId, entry)
        except Exception as e:
            print("[RandomPocket] open request error:", e)

    def _TestRefresh(self, playerId):
        """立即模拟一次每日刷新：给第一个还有空位的口袋加 1 件物品"""
        pockets = self._ScanPockets(playerId)
        if not pockets:
            self._Notify(playerId, "[随机口袋] 测试：身上没有口袋")
            return
        for pt, slot, item in pockets:
            state = self._State(playerId, pt, slot, item)
            bag = self._Bag(state)
            if len(bag) >= MAX_POCKET_SLOTS:
                continue
            self._BagAdd(bag, self._RollItem())
            state["bag"] = bag
            self._SaveState(playerId, pt, slot, item, state)
            self._Notify(playerId, "[随机口袋] 测试刷新 +1 (%d/%d)" %
                         (len(bag), MAX_POCKET_SLOTS))
            if self._openPocket.get(playerId) == state["uid"]:
                self._PushBagToUI(playerId, bag)
            return
        self._Notify(playerId, "[随机口袋] 测试：口袋已满")

    # ---------- 按钮调整模式（/rp ui）：保存/下发按钮位置大小 ----------
    def OnUiCfgSave(self, args):
        """客户端在调整模式点「完成」：把按钮 offset/size 存进 ExtraData"""
        try:
            playerId = args.get("playerId") if isinstance(args, dict) else None
            if not playerId:
                return
            cfg = {}
            offset = args.get("offset")
            size = args.get("size")
            if isinstance(offset, (list, tuple)) and len(offset) == 2:
                cfg["offset"] = [float(offset[0]), float(offset[1])]
            if isinstance(size, (list, tuple)) and len(size) == 2:
                cfg["size"] = [float(size[0]), float(size[1])]
            CompFactory.CreateExtraData(playerId).SetExtraData(
                UI_CFG_KEY, json.dumps(cfg))
            self._Notify(playerId, "[随机口袋] 按钮位置大小已保存")
            print("[RandomPocket] ui cfg saved for %s: %r" % (playerId, cfg))
        except Exception as e:
            print("[RandomPocket] ui cfg save error:", e)

    def _SendUiCfg(self, playerId):
        """进世界后下发已保存的按钮配置（没有则发空 dict，客户端用默认）"""
        cfg = {}
        try:
            raw = CompFactory.CreateExtraData(playerId).GetExtraData(UI_CFG_KEY)
            if isinstance(raw, _STRING_TYPES) and raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    cfg = data
        except Exception as e:
            print("[RandomPocket] ui cfg load error:", e)
        try:
            self.NotifyToClient(playerId, UI_CFG_EVENT, cfg)
            print("[RandomPocket] ui cfg -> %s: %r" % (playerId, cfg))
        except Exception as e:
            print("[RandomPocket] ui cfg notify error:", e)

    # ---------- HUD「打开」按钮：手持切到口袋时亮 3 秒 ----------
    def OnCarriedNewItemChangedServerEvent(self, args):
        """切换手持物品时立即检测（事件参数不稳定，只取玩家ID再自查）"""
        try:
            playerId = None
            if isinstance(args, dict):
                playerId = args.get("playerId") or args.get("entityId")
            if playerId:
                self._CheckHeldPocket(playerId)
        except Exception as e:
            print("[RandomPocket] carried change error:", e)

    def _HeldIsPocket(self, playerId):
        """当前手持槽位是不是口袋；接口不可用时返回 None（保持原状态）"""
        if self._slotBroken:
            return None
        try:
            itemComp = CompFactory.CreateItem(playerId)
            enum = serverApi.GetMinecraftEnum()
            carried = getattr(getattr(enum, "ItemPosType", None),
                              "CARRIED", None)
            if carried is None:
                raise Exception("no CARRIED enum")
            try:
                slot = itemComp.GetSelectSlotId()
            except Exception:
                slot = itemComp.GetSelectSlotId(playerId)
            it = itemComp.GetPlayerItem(carried, slot)
            return isinstance(it, dict) and _ItemName(it) in POCKET_ITEMS
        except Exception as e:
            self._slotBroken = True
            print("[RandomPocket] held check disabled: %s" % e)
            return None

    def _CheckHeldPocket(self, playerId):
        """手持口袋状态变化时通知客户端；客户端显示 3 秒后自行隐藏"""
        held = self._HeldIsPocket(playerId)
        if held is None or self._hudState.get(playerId) == held:
            return
        self._hudState[playerId] = held
        try:
            self.NotifyToClient(playerId, HUD_STATE_EVENT, {"show": held})
            print("[RandomPocket] hud state -> %s for %s" % (held, playerId))
        except Exception as e:
            print("[RandomPocket] hud state notify error: %s" % e)

    # ---------- 扫描玩家身上的口袋 ----------
    def _ScanPockets(self, playerId):
        """按真实槽位逐个读取，避免 GetPlayerAllItems 的槽位信息不可靠"""
        result = []
        itemComp = CompFactory.CreateItem(playerId)
        enum = serverApi.GetMinecraftEnum()
        posType = getattr(enum, "ItemPosType", None)
        if posType is None:
            print("[RandomPocket] no ItemPosType enum")
            return result
        ranges = (("CARRIED", range(0, 9)),
                  ("INVENTORY", range(0, 36)),
                  ("OFFHAND", range(0, 1)))
        for posName, slots in ranges:
            pt = getattr(posType, posName, None)
            if pt is None:
                continue
            for slot in slots:
                it = None
                try:
                    it = itemComp.GetPlayerItem(pt, slot, True)
                except Exception:
                    try:
                        it = itemComp.GetPlayerItem(pt, slot)
                    except Exception as e:
                        print("[RandomPocket] GetPlayerItem %s/%d error: %s" %
                              (posName, slot, e))
                        continue
                if not isinstance(it, dict) or _ItemName(it) not in POCKET_ITEMS:
                    continue
                result.append((pt, slot, self._NormalizeItem(it)))
        return result

    # ---------- 写回状态（内容存 ExtraData，物品只负责满态显示） ----------
    def _SaveState(self, playerId, pt, slot, item, state):
        uid = state.get("uid")
        self._StoreState(playerId, uid, state)

        bag = self._Bag(state)
        want = POCKET_FULL_ITEM if len(bag) >= MAX_POCKET_SLOTS else POCKET_ITEM
        tag = UID_TAG + uid
        if _ItemName(item) == want and item.get("extraId") == tag:
            return True

        out = {
            "newItemName": want,
            "newAuxValue": 0,
            "count": 1,
            "extraId": tag,
        }
        try:
            if CompFactory.CreateItem(playerId).SetEntityItem(pt, out, slot):
                return True
            print("[RandomPocket] SetEntityItem returned False")
        except Exception as e:
            print("[RandomPocket] SetEntityItem error:", e)
        try:
            res = CompFactory.CreateItem(playerId).SetPlayerAllItems({(pt, slot): out})
            if res and res.get((pt, slot), False):
                return True
            print("[RandomPocket] SetPlayerAllItems result:", res)
        except Exception as e:
            print("[RandomPocket] SetPlayerAllItems error:", e)
        return self._StoreState(playerId, uid, state)

    # ---------- 每日刷新 ----------
    def _RefreshAll(self, day):
        count = 0
        for playerId in serverApi.GetPlayerList():
            try:
                self._GrantPocket(playerId)
                pockets = self._ScanPockets(playerId)
                self._CheckHeldPocket(playerId)
                if playerId not in self._cfgSent:
                    self._cfgSent.add(playerId)
                    self._SendUiCfg(playerId)
                if not pockets:
                    print("[RandomPocket] player %s has no pocket" % playerId)
                    continue

                # 每个玩家每天只挑一个“还有空位且今天没刷过”的口袋
                targetIdx = -1
                for idx, (pt, slot, item) in enumerate(pockets):
                    state = self._State(playerId, pt, slot, item)
                    if self._HandledToday(state, day):
                        continue
                    if len(self._Bag(state)) < MAX_POCKET_SLOTS:
                        targetIdx = idx
                        break

                print("[RandomPocket] day=%d player=%s pockets=%d target=%d" %
                      (day, playerId, len(pockets), targetIdx))

                if playerId not in self._booted:
                    self._booted.add(playerId)
                    first = pockets[0]
                    state = self._State(playerId, first[0], first[1], first[2])
                    self._Notify(playerId, "[随机口袋] 第%d天 / 共%d个物品" %
                                 (day, len(self._Bag(state))))

                for idx, (pt, slot, item) in enumerate(pockets):
                    state = self._State(playerId, pt, slot, item)
                    if self._HandledToday(state, day):
                        continue
                    state["day"] = day
                    bag = self._Bag(state)
                    got = 0
                    if idx == targetIdx:
                        while len(bag) < MAX_POCKET_SLOTS and got < ITEMS_PER_DAY:
                            self._BagAdd(bag, self._RollItem())
                            got += 1
                        state["bag"] = bag
                    self._SaveState(playerId, pt, slot, item, state)

                    if got > 0:
                        count += 1
                        self._Notify(playerId, "[随机口袋] +%d个物品 (%d/%d)" %
                                     (got, len(bag), MAX_POCKET_SLOTS))
                    if self._openPocket.get(playerId) == state["uid"]:
                        self._PushBagToUI(playerId, bag)
            except Exception as e:
                print("[RandomPocket] refresh player error:", e)
        return count

    # ---------- 首次进服赠送一个口袋 ----------
    def _GrantPocket(self, playerId):
        try:
            ed = CompFactory.CreateExtraData(playerId)
            if ed.GetExtraData(GRANT_KEY):
                return
            ed.SetExtraData(GRANT_KEY, True)
        except Exception as e:
            print("[RandomPocket] extradata error:", e)
        if self._ScanPockets(playerId):
            return
        try:
            ok = CompFactory.CreateItem(playerId).SpawnItemToPlayerInv(
                {"newItemName": POCKET_ITEM, "newAuxValue": 0, "count": 1}, playerId)
            print("[RandomPocket] grant pocket to %s -> %s" % (playerId, ok))
            if ok:
                self._Notify(playerId, "[随机口袋] 获得一个随机口袋")
        except Exception as e:
            print("[RandomPocket] grant error:", e)

    # ---------- 右键口袋 -> 打开容器 ----------
    def ServerItemTryUseEvent(self, args):
        self._OnUse(args)

    def ServerItemUseOnEvent(self, args):
        self._OnUse(args)

    def _OnUse(self, args):
        try:
            itemDict = args.get("itemDict")
            playerId = args.get("playerId")
            if not itemDict or not playerId:
                return
            if _ItemName(itemDict) not in POCKET_ITEMS:
                return
            try:
                args["cancel"] = True
            except Exception:
                pass
            try:
                args["ret"] = True
            except Exception:
                pass

            now = time.time()
            if now - self._useGuard.get(playerId, 0) < 0.4:
                return
            self._useGuard[playerId] = now

            entry = self._FindPocket(playerId, itemDict)
            if entry is None:
                print("[RandomPocket] used pocket but not found in inventory")
                return
            self._OpenPocket(playerId, entry)
        except Exception as e:
            print("[RandomPocket] use event error:", e)

    def _FindPocket(self, playerId, itemDict):
        pockets = self._ScanPockets(playerId)
        if not pockets:
            return None
        eid = itemDict.get("extraId")
        if isinstance(eid, _STRING_TYPES) and eid.startswith(UID_TAG):
            for entry in pockets:
                if entry[2].get("extraId") == eid:
                    return entry
        return pockets[0]

    def _OpenPocket(self, playerId, entry):
        pt, slot, item = entry
        state = self._State(playerId, pt, slot, item)
        bag = self._Bag(state)
        # 每个口袋只在第一次打开时补一个初始物品，保证第一个游戏日一定有内容；
        # 用 seeded 标记避免玩家主动清空口袋后又被重新填满。
        if not bag and not state.get("seeded"):
            self._BagAdd(bag, self._RollItem())
            state["seeded"] = True
            if state.get("day") is None:
                state["day"] = self._ClockDay() or 0
            self._Notify(playerId, "[随机口袋] +1个物品 (1/%d)" % MAX_POCKET_SLOTS)
        state["bag"] = bag
        self._SaveState(playerId, pt, slot, item, state)

        self._PushBagToUI(playerId, bag)
        self._openPocket[playerId] = state["uid"]

        try:
            CompFactory.CreatePlayer(playerId).OpenNeteaseContainer(
                CONTAINER_SCREEN, CONTAINER_TITLE)
            print("[RandomPocket] open pocket %s (%d items) for %s" %
                  (state["uid"], len(bag), playerId))
        except Exception as e:
            print("[RandomPocket] OpenNeteaseContainer error:", e)
            self._Notify(playerId, "[随机口袋] 打开失败 (当前%d个物品)" % len(bag))
            return

        # 界面打开时引擎可能清空预先写入的槽位，打开后再补推一次
        try:
            CompFactory.CreateGame(_LevelId()).AddTimer(
                0.4, self._PushAfterOpen, playerId)
        except Exception as e:
            print("[RandomPocket] push timer error:", e)

    def _PushAfterOpen(self, playerId):
        uid = self._openPocket.get(playerId)
        if not uid:
            return
        for pt, slot, item in self._ScanPockets(playerId):
            state = self._State(playerId, pt, slot, item)
            if state.get("uid") == uid:
                self._PushBagToUI(playerId, self._Bag(state))
                print("[RandomPocket] push after open %s" % uid)
                return

    def OnScreenEvent(self, args):
        """客户端上报的界面打开/关闭：关闭后不再从界面读数据，避免把空界面当成空口袋"""
        try:
            action = args.get("action")
            playerId = args.get("playerId")
            if not playerId:
                return
            if action == "push":
                # 界面刚创建时引擎会重置格子，此时补推一次最可靠
                self._PushAfterOpen(playerId)
                print("[RandomPocket] screen push for %s" % playerId)
            elif action == "pop":
                # 界面已关闭，丢弃未执行的同步与打开状态
                self._openPocket.pop(playerId, None)
                self._syncPending.discard(playerId)
                print("[RandomPocket] screen pop for %s" % playerId)
        except Exception as e:
            print("[RandomPocket] screen event error:", e)

    # ---------- 容器界面数据维护 ----------
    def _PushBagToUI(self, playerId, bag):
        comp = CompFactory.CreateItem(playerId)
        for slot in range(MAX_POCKET_SLOTS):
            it = None
            src = bag.get(str(slot)) if isinstance(bag, dict) else None
            if isinstance(src, dict) and _ItemName(src):
                it = self._CleanItem(src)
            try:
                comp.SetPlayerUIItem(playerId, slot, it, False, True)
            except Exception as e:
                print("[RandomPocket] SetPlayerUIItem error:", e)
                return False
        return True

    def _ReadUIContainer(self, playerId):
        comp = CompFactory.CreateItem(playerId)
        bag = {}
        for slot in range(MAX_POCKET_SLOTS):
            try:
                it = comp.GetPlayerUIItem(playerId, slot, True, True)
            except Exception as e:
                print("[RandomPocket] GetPlayerUIItem error:", e)
                return None
            if isinstance(it, dict) and _ItemName(it):
                try:
                    count = int(it.get("count", 1))
                except Exception:
                    count = 1
                if count > 0:
                    bag[str(slot)] = self._CleanItem(it)
        return bag

    def _SyncOpenContainer(self, playerId):
        uid = self._openPocket.get(playerId)
        if not uid:
            return
        bag = self._ReadUIContainer(playerId)
        if bag is None:
            return
        for pt, slot, item in self._ScanPockets(playerId):
            state = self._State(playerId, pt, slot, item)
            if state.get("uid") != uid:
                continue
            state["bag"] = bag
            self._SaveState(playerId, pt, slot, item, state)
            return

    def _RequestSync(self, playerId, delay=0.25):
        if playerId in self._syncPending:
            return
        self._syncPending.add(playerId)
        try:
            CompFactory.CreateGame(_LevelId()).AddTimer(delay, self._DoSync, playerId)
        except Exception as e:
            self._syncPending.discard(playerId)
            print("[RandomPocket] AddTimer error:", e)

    def _DoSync(self, playerId):
        self._syncPending.discard(playerId)
        try:
            self._SyncOpenContainer(playerId)
        except Exception as e:
            print("[RandomPocket] sync error:", e)

    def _OnContainerChanged(self, args):
        try:
            ctype = args.get("collectionType")
            if ctype and ctype != UI_COLLECTION_TYPE:
                return
            playerId = args.get("playerId")
            if not playerId:
                return
            if not self._openPocket.get(playerId):
                return
            self._RequestSync(playerId)
        except Exception as e:
            print("[RandomPocket] container event error:", e)

    def PlayerTryAddCustomContainerItemServerEvent(self, args):
        self._OnContainerChanged(args)

    def PlayerTryPutCustomContainerItemServerEvent(self, args):
        self._OnContainerChanged(args)

    def PlayerTryRemoveCustomContainerItemServerEvent(self, args):
        self._OnContainerChanged(args)

    # ---------- 消息 ----------
    def _Notify(self, playerId, msg):
        print("[RandomPocket] notify: %s" % msg)
        gameComp = CompFactory.CreateGame(_LevelId())
        try:
            gameComp.NotifyOneMessage(playerId, msg)
            return
        except Exception:
            pass
        try:
            gameComp.SetTipMessage(msg)
        except Exception:
            pass
