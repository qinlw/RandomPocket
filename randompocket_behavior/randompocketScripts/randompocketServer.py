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
SCREEN_EVENT = "rb_screen_event"
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
        print("[RandomPocket] server system started")

    def _ListenEngineEvents(self):
        engNs = serverApi.GetEngineNamespace()
        engSys = serverApi.GetEngineSystemName()
        for evtName in ("ServerItemTryUseEvent", "ServerItemUseOnEvent",
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
        bag = state.get("bag")
        if not isinstance(bag, list):
            bag = []
        return bag

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
                            bag.append(loot_pool.RollItem())
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
            bag.append(loot_pool.RollItem())
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
            if slot < len(bag):
                src = bag[slot]
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
        bag = []
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
                    bag.append(self._CleanItem(it))
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
