# -*- coding: utf-8 -*-
"""RandomPocket 客户端系统

服务端没有“自定义容器界面关闭”事件，而 OpenNeteaseContainer 打开的界面
物品数据需要开发者自行维护。因此这里监听客户端引擎的：

    PushScreenEvent  界面创建
    PopScreenEvent   界面移除

把打开/关闭时机转发给服务端，由服务端在界面刚创建时填充口袋内容，
并在界面关闭后停止从界面回读数据（否则空界面会把口袋内容覆盖成空）。

另外负责测试模式：
    - 服务端通过 rb_test_state 下发测试开关；
    - 测试按钮与奖池弹窗直接写在容器界面 randompocket_container.json 里
      （CreateUI/PushScreen 的界面要么被容器屏盖住、要么吞掉容器输入），
      容器屏打开后用 GetTopUINode 拿到界面节点，SetVisible 显示按钮，
      并用 AddTouchEventParams + SetButtonTouchUpCallback 挂点击回调；
    - 奖池数据由服务端分块下发，缓存后供面板展示 / 搜索。
"""

import mod.client.extraClientApi as clientApi

ClientSystem = clientApi.GetClientSystemCls()

try:
    _STRING_TYPES = (str, unicode)
except NameError:
    _STRING_TYPES = (str,)

MOD_NAMESPACE = "randompocket"
SERVER_SYSTEM = "RandomPocketServerSystem"
CLIENT_SYSTEM = "RandomPocketClientSystem"

SCREEN_PREFIX = "randompocket_container"
SCREEN_EVENT = "rb_screen_event"

TEST_STATE_EVENT = "rb_test_state"
POOL_CHUNK_EVENT = "rb_test_pool_chunk"
POOL_REQUEST_EVENT = "rb_test_pool_request"
REFRESH_EVENT = "rb_test_refresh"

# 手机端没有右键：快捷栏有口袋时 HUD 显示「打开口袋」按钮。
# 客户端物品组件没有 GetSelectSlotId/GetInvItem（服务端专用），
# 显隐由服务端扫描后通过 rb_hud_state 下发。
HUD_UI_NAME = "RandomPocketHud"
HUD_UI_JSON = "randompocket_hud.main"
OPEN_REQUEST_EVENT = "rb_open_request"
HUD_STATE_EVENT = "rb_hud_state"
# /rp ui 进入按钮调整模式（拖动调位置、＋/－调大小、完成保存）；
# 配置存服务端 ExtraData，进世界时经 rb_ui_cfg 下发
UI_ADJUST_EVENT = "rb_ui_adjust"
UI_CFG_EVENT = "rb_ui_cfg"
UI_CFG_SAVE_EVENT = "rb_ui_cfg_save"

POOL_CELLS = 24  # 奖池弹窗图标格数（6 列 x 4 行）

try:
    from mod.client.ui.screenNode import ScreenNode
except Exception:
    ScreenNode = object


class RandomPocketHudScreen(ScreenNode):
    """HUD 层界面节点（打开口袋按钮），无需额外逻辑，回调走 API"""

    def Create(self):
        pass

    def Destroy(self):
        pass


class RandomPocketClientSystem(ClientSystem):
    def __init__(self, namespace, systemName):
        ClientSystem.__init__(self, namespace, systemName)
        self._testMode = False
        self._pocketOpen = False
        self._testNode = None       # 容器屏节点（测试控件所在界面）
        self._testBase = None       # 测试控件路径前缀
        self._pool = []
        self._poolChunks = {}
        self._poolTotal = 0
        self._poolFilter = ""
        self._poolPage = 0
        self._hudUI = None          # HUD 界面节点（打开口袋按钮）
        self._hudWanted = False     # 服务端下发的按钮显隐状态
        self._iconCache = {}        # 物品ID -> 图标贴图路径
        self._gridPath = None       # 口袋物品网格控件路径（弹窗打开时隐藏）
        self._pageEntries = []      # 当前页的 (物品ID, 中文名)
        self._adjust = False        # 按钮调整模式
        self._dragStart = None      # 拖动起点 (touchX, touchY, 原始position)
        self._pendingCfg = None     # HUD 创建前收到的按钮配置
        self._hudHideSeq = 0        # 按钮 3 秒自动隐藏的序号（防旧定时器误隐藏）
        self._iconDebug = 0         # 图标贴图接口原始返回值探测计数
        self._iconErr = 0           # SetSprite 报错计数（限流）

        engNs = clientApi.GetEngineNamespace()
        engSys = clientApi.GetEngineSystemName()
        handlers = ("PushScreenEvent", "PopScreenEvent", "UiInitFinished")
        for evtName in handlers:
            handler = getattr(self, evtName, None)
            if handler is None:
                continue
            try:
                self.ListenForEvent(engNs, engSys, evtName, self, handler)
            except Exception as e:
                print("[RandomPocket] client listen %s error: %s" % (evtName, e))

        for evtName, handler in ((TEST_STATE_EVENT, self.OnTestState),
                                 (POOL_CHUNK_EVENT, self.OnPoolChunk),
                                 (HUD_STATE_EVENT, self.OnHudState),
                                 (UI_ADJUST_EVENT, self.OnUiAdjust),
                                 (UI_CFG_EVENT, self.OnUiCfg)):
            try:
                self.ListenForEvent(MOD_NAMESPACE, SERVER_SYSTEM, evtName,
                                    self, handler)
            except Exception as e:
                print("[RandomPocket] client listen %s error: %s" % (evtName, e))
        print("[RandomPocket] client system started")

    def _ScreenName(self, args):
        name = args.get("screenName") if isinstance(args, dict) else None
        if isinstance(name, _STRING_TYPES):
            return name
        return ""

    def _NotifyServer(self, action, screenName):
        try:
            self.NotifyToServer(SCREEN_EVENT, {
                "action": action,
                "playerId": clientApi.GetLocalPlayerId(),
                "screenName": screenName,
            })
        except Exception as e:
            print("[RandomPocket] notify %s error: %s" % (action, e))

    # ---------- 口袋界面开闭 ----------
    def PushScreenEvent(self, args):
        name = self._ScreenName(args)
        if name.startswith(SCREEN_PREFIX):
            self._pocketOpen = True
            self._NotifyServer("push", name)
            if self._testMode:
                self._ShowTestUI()

    def PopScreenEvent(self, args):
        name = self._ScreenName(args)
        if name.startswith(SCREEN_PREFIX):
            self._pocketOpen = False
            self._NotifyServer("pop", name)
            self._HideTestUI()

    # ---------- 测试面板（控件内嵌在容器屏里，运行时接管） ----------
    def UiInitFinished(self, args):
        self._EnsureHud()

    # ---------- 手机端「打开口袋」HUD 按钮 ----------
    def _EnsureHud(self):
        if self._hudUI:
            return
        try:
            clientApi.RegisterUI(
                MOD_NAMESPACE, HUD_UI_NAME,
                "randompocketScripts.randompocketClient.RandomPocketHudScreen",
                HUD_UI_JSON)
        except Exception as e:
            print("[RandomPocket] register hud error: %s" % e)
        try:
            self._hudUI = clientApi.CreateUI(
                MOD_NAMESPACE, HUD_UI_NAME, {"isHud": 1})
        except Exception as e:
            print("[RandomPocket] create hud error: %s" % e)
            return
        if not self._hudUI:
            print("[RandomPocket] create hud returned None")
            return
        try:
            btn = self._hudUI.GetBaseUIControl("/open_button").asButton()
            btn.AddTouchEventParams({"isSwallow": True})
            btn.SetButtonTouchUpCallback(self._OnOpenPressed)
            # 调整模式下拖动按钮（仅触屏会触发 Move 回调）
            btn.SetButtonTouchDownCallback(self._OnBtnDown)
            btn.SetButtonTouchMoveCallback(self._OnBtnMove)
            self._hudUI.GetBaseUIControl(
                "/open_button").SetVisible(self._hudWanted)
        except Exception as e:
            print("[RandomPocket] wire hud button error: %s" % e)
        for path, handler in (("/adjust_panel/btn_smaller", self._OnSmaller),
                              ("/adjust_panel/btn_bigger", self._OnBigger),
                              ("/adjust_panel/btn_done", self._OnAdjustDone)):
            try:
                b = self._hudUI.GetBaseUIControl(path).asButton()
                b.AddTouchEventParams({"isSwallow": True})
                b.SetButtonTouchUpCallback(handler)
            except Exception as e:
                print("[RandomPocket] wire %s error: %s" % (path, e))
        if self._pendingCfg:
            self._ApplyBtnCfg(self._pendingCfg)
            self._pendingCfg = None

    def OnHudState(self, args):
        """手持切到口袋时服务端发来 show=True：显示按钮，3 秒后自动隐藏"""
        show = bool(args.get("show")) if isinstance(args, dict) else False
        self._hudWanted = show
        self._hudHideSeq += 1
        print("[RandomPocket] hud button visible=%s" % show)
        if not self._hudUI:
            return
        try:
            self._hudUI.GetBaseUIControl("/open_button").SetVisible(show)
        except Exception as e:
            print("[RandomPocket] hud set visible error: %s" % e)
        if show:
            self._ScheduleHudHide(self._hudHideSeq)

    def _ScheduleHudHide(self, seq):
        """3 秒后隐藏按钮；期间状态刷新或进入调整模式则取消"""
        def _hide():
            if seq != self._hudHideSeq or self._adjust:
                return
            try:
                if self._hudUI:
                    self._hudUI.GetBaseUIControl(
                        "/open_button").SetVisible(False)
            except Exception:
                pass
        try:
            clientApi.GetEngineCompFactory().CreateGame(
                clientApi.GetLevelId()).AddTimer(3.0, _hide)
        except Exception as e:
            print("[RandomPocket] hud hide timer error: %s" % e)

    def _OnOpenPressed(self, args):
        if self._adjust:
            return  # 调整模式下点击不触发打开
        try:
            self.NotifyToServer(OPEN_REQUEST_EVENT, {
                "playerId": clientApi.GetLocalPlayerId(),
            })
        except Exception as e:
            print("[RandomPocket] open request error: %s" % e)

    # ---------- 按钮调整模式（/rp ui） ----------
    def OnUiAdjust(self, args):
        """进入调整模式：强制显示按钮，可拖动；顶部出现 －/完成/＋"""
        self._adjust = True
        self._dragStart = None
        print("[RandomPocket] enter ui adjust mode")
        if not self._hudUI:
            return
        try:
            self._hudUI.GetBaseUIControl("/open_button").SetVisible(True)
            self._hudUI.GetBaseUIControl("/adjust_panel").SetVisible(True)
        except Exception as e:
            print("[RandomPocket] show adjust panel error: %s" % e)

    def OnUiCfg(self, args):
        """服务端下发的已保存按钮配置"""
        if not isinstance(args, dict):
            return
        if not self._hudUI:
            self._pendingCfg = args
            return
        self._ApplyBtnCfg(args)

    def _ApplyBtnCfg(self, cfg):
        offset = cfg.get("offset")
        size = cfg.get("size")
        try:
            btn = self._hudUI.GetBaseUIControl("/open_button")
            if (isinstance(offset, (list, tuple)) and len(offset) == 2):
                btn.SetPosition((float(offset[0]), float(offset[1])))
            if (isinstance(size, (list, tuple)) and len(size) == 2):
                btn.SetSize((float(size[0]), float(size[1])), True)
            print("[RandomPocket] button cfg applied offset=%r size=%r" %
                  (offset, size))
        except Exception as e:
            print("[RandomPocket] apply cfg error: %s" % e)

    def _OnBtnDown(self, args):
        if not self._adjust:
            return
        try:
            pos = self._hudUI.GetBaseUIControl("/open_button").GetPosition()
            self._dragStart = (float(args.get("TouchPosX", 0)),
                               float(args.get("TouchPosY", 0)),
                               (float(pos[0]), float(pos[1])))
        except Exception as e:
            print("[RandomPocket] drag start error: %s" % e)
            self._dragStart = None

    def _OnBtnMove(self, args):
        if not self._adjust or not self._dragStart:
            return
        try:
            x0, y0, pos0 = self._dragStart
            x = float(args.get("TouchPosX", x0))
            y = float(args.get("TouchPosY", y0))
            self._hudUI.GetBaseUIControl("/open_button").SetPosition(
                (pos0[0] + x - x0, pos0[1] + y - y0))
        except Exception as e:
            print("[RandomPocket] drag move error: %s" % e)

    def _ResizeButton(self, delta):
        try:
            btn = self._hudUI.GetBaseUIControl("/open_button")
            w, h = btn.GetSize()
            w = min(96.0, max(24.0, float(w) + delta * 6.0))
            h = max(10.0, round(w * 7.0 / 18.0))  # 保持 36:14 比例
            btn.SetSize((w, h), True)
            print("[RandomPocket] button size -> %dx%d" % (w, h))
        except Exception as e:
            print("[RandomPocket] resize error: %s" % e)

    def _OnSmaller(self, args):
        self._ResizeButton(-1)

    def _OnBigger(self, args):
        self._ResizeButton(1)

    def _OnAdjustDone(self, args):
        """保存配置并退出调整模式"""
        try:
            btn = self._hudUI.GetBaseUIControl("/open_button")
            pos = btn.GetPosition()
            size = btn.GetSize()
            self.NotifyToServer(UI_CFG_SAVE_EVENT, {
                "playerId": clientApi.GetLocalPlayerId(),
                "offset": [float(pos[0]), float(pos[1])],
                "size": [float(size[0]), float(size[1])],
            })
            print("[RandomPocket] button cfg saved offset=%r size=%r" %
                  (pos, size))
        except Exception as e:
            print("[RandomPocket] save cfg error: %s" % e)
        self._adjust = False
        self._dragStart = None
        try:
            self._hudUI.GetBaseUIControl("/adjust_panel").SetVisible(False)
            self._hudUI.GetBaseUIControl(
                "/open_button").SetVisible(self._hudWanted)
            if self._hudWanted:
                self._hudHideSeq += 1
                self._ScheduleHudHide(self._hudHideSeq)
        except Exception as e:
            print("[RandomPocket] exit adjust error: %s" % e)

    def _ShowTestUI(self):
        # 界面刚 Push，延迟一点等节点就绪后再拿
        try:
            clientApi.GetEngineCompFactory().CreateGame(
                clientApi.GetLevelId()).AddTimer(0.1, self._AttachTestUI)
        except Exception:
            self._AttachTestUI()

    # 容器屏继承了 common 模板，中间层名称不透明；用已知候选名做 BFS，
    # 在整棵控件树里按名字找到 test_buttons，父路径即为 base
    _TREE_NAMES = (
        "variables_button_mappings_and_controls",
        "safezone_screen_matrix", "inner_matrix", "safezone_screen_panel",
        "root_screen_panel", "randompocket_panel", "screen_content",
        "content", "content_panel", "root_panel", "main", "panel",
        "container_panel", "base_panel", "body", "root",
        # 口袋物品网格所在分支（common.root_panel 模板内部层级）
        "common_panel", "bg_image", "chest_panel",
        "randompocket_panel_top_half",
    )

    def _FindByName(self, node, target):
        """在控件树里按名字 BFS，返回控件完整路径（不含节点本身）"""
        queue = [""]
        seen = set()
        while queue:
            path = queue.pop(0)
            if path in seen or path.count("/") > 12:
                continue
            seen.add(path)
            try:
                ctrl = node.GetBaseUIControl(path + "/" + target)
            except Exception:
                ctrl = None
            if ctrl:
                return path + "/" + target
            parent = None
            if path:
                try:
                    parent = node.GetBaseUIControl(path)
                except Exception:
                    parent = None
                if not parent:
                    continue
            for name in self._TREE_NAMES:
                child = None
                try:
                    if parent is not None:
                        child = parent.GetChildByName(name)
                    else:
                        child = node.GetBaseUIControl("/" + name)
                except Exception:
                    child = None
                if child:
                    queue.append(path + "/" + name)
        return None

    def _FindBase(self, node):
        found = self._FindByName(node, "test_buttons")
        if found is None:
            return None
        return found[: -len("/test_buttons")]

    def _AttachTestUI(self):
        if not self._pocketOpen:
            return
        try:
            node = clientApi.GetTopUINode()
        except Exception as e:
            print("[RandomPocket] GetTopUINode error: %s" % e)
            return
        if not node:
            print("[RandomPocket] no top ui node")
            return
        try:
            print("[RandomPocket] top node screen: %r" % node.GetScreenName())
        except Exception:
            pass
        base = self._FindBase(node)
        if base is None:
            print("[RandomPocket] test controls not found in top screen")
            return
        print("[RandomPocket] test controls found, base=%r" % (base,))
        self._testNode = node
        self._testBase = base
        # 记录口袋物品网格路径：弹窗打开时隐藏，避免格子的数字/图标盖住弹窗
        self._gridPath = self._FindByName(node, "randompocket_grid1")
        print("[RandomPocket] grid path -> %r" % (self._gridPath,))
        # 显示/隐藏测试按钮
        try:
            node.GetBaseUIControl(base + "/test_buttons").SetVisible(
                bool(self._testMode))
        except Exception as e:
            print("[RandomPocket] show test buttons error: %s" % e)
        if not self._testMode:
            return
        # 挂按钮回调（button_mappings 已在 JSON 里清空，回调走 API）
        wiring = [
            ("/test_buttons/btn_pool", self._OnBtnPool),
            ("/test_buttons/btn_refresh", self._OnBtnRefresh),
            ("/pool_dialog/btn_search", self._OnBtnSearch),
            ("/pool_dialog/btn_prev", self._OnBtnPrev),
            ("/pool_dialog/btn_next", self._OnBtnNext),
            ("/pool_dialog/btn_close", self._OnBtnClose),
        ]
        for i in range(POOL_CELLS):
            wiring.append(
                ("/pool_dialog/cell_%d" % i, self._MakeCellHandler(i)))
        for path, handler in wiring:
            try:
                btn = node.GetBaseUIControl(base + path).asButton()
                btn.AddTouchEventParams({"isSwallow": True})
                btn.SetButtonTouchUpCallback(handler)
            except Exception as e:
                print("[RandomPocket] wire %s error: %s" % (path, e))
        print("[RandomPocket] test controls attached, base=%r" % (base,))

    def _HideTestUI(self):
        self._testNode = None
        self._testBase = None
        self._poolFilter = ""
        self._poolPage = 0

    def OnTestState(self, args):
        enabled = bool(args.get("enabled")) if isinstance(args, dict) else False
        self._testMode = enabled
        if enabled:
            self._pool = []
            self._poolChunks = {}
            self._poolTotal = 0
            self._poolFilter = ""
            self._poolPage = 0
            if self._pocketOpen and self._testNode:
                self._AttachTestUI()
            elif self._pocketOpen:
                self._ShowTestUI()
        else:
            node, base = self._testNode, self._testBase
            if node and base is not None:
                try:
                    node.GetBaseUIControl(base + "/test_buttons").SetVisible(False)
                    node.GetBaseUIControl(base + "/pool_dialog").SetVisible(False)
                except Exception:
                    pass
        print("[RandomPocket] test mode: %s" % enabled)

    # ---------- 测试按钮回调 ----------
    def _SetGridVisible(self, show):
        """弹窗打开时隐藏口袋物品网格，防止格子数字/图标盖住弹窗"""
        node = self._testNode
        if not node or not self._gridPath:
            return
        try:
            node.GetBaseUIControl(self._gridPath).SetVisible(bool(show))
        except Exception as e:
            print("[RandomPocket] grid visible error: %s" % e)

    def _OnBtnPool(self, args):
        node, base = self._testNode, self._testBase
        if not node or base is None:
            return
        try:
            node.GetBaseUIControl(base + "/pool_dialog").SetVisible(True)
        except Exception as e:
            print("[RandomPocket] open pool dialog error: %s" % e)
        self._SetGridVisible(False)
        self._SetLabel("/pool_dialog/name_label", "点图标查看名称")
        if not self._pool:
            self.RequestPool()
        self.RefreshPool()

    def _OnBtnRefresh(self, args):
        self.RequestRefresh()

    def _OnBtnSearch(self, args):
        node, base = self._testNode, self._testBase
        if not node or base is None:
            return
        text = ""
        try:
            text = node.GetBaseUIControl(
                base + "/pool_dialog/search_box").asTextEditBox().GetEditText()
        except Exception as e:
            print("[RandomPocket] read search box error: %s" % e)
        self._poolFilter = (text or "").strip()
        self._poolPage = 0
        self.RefreshPool()

    def _OnBtnPrev(self, args):
        if self._poolPage > 0:
            self._poolPage -= 1
            self.RefreshPool()

    def _OnBtnNext(self, args):
        self._poolPage += 1
        self.RefreshPool()

    def _OnBtnClose(self, args):
        node, base = self._testNode, self._testBase
        if not node or base is None:
            return
        try:
            node.GetBaseUIControl(base + "/pool_dialog").SetVisible(False)
        except Exception:
            pass
        self._SetGridVisible(True)

    def _MakeCellHandler(self, i):
        def _Handler(args):
            self._OnCellTap(i)
        return _Handler

    def _OnCellTap(self, i):
        """点格子：在下方显示该物品的名称与 ID"""
        if i >= len(self._pageEntries):
            return
        iid, cn = self._pageEntries[i]
        text = ("%s %s" % (cn, iid)) if cn else iid
        self._SetLabel("/pool_dialog/name_label", text)

    # ---------- 奖池弹窗内容 ----------
    def _SetLabel(self, path, text):
        node, base = self._testNode, self._testBase
        if not node or base is None:
            return
        try:
            node.GetBaseUIControl(base + path).asLabel().SetText(text)
        except Exception as e:
            print("[RandomPocket] set label %s error: %s" % (path, e))

    def _ParseTex(self, val):
        """GetItemTexture 返回值可能是 str / dict / tuple，统一抽出贴图路径"""
        if isinstance(val, _STRING_TYPES) and val:
            return val
        if isinstance(val, dict):
            for k in ("texturePath", "texture", "icon", "iconPath", "path"):
                v = val.get(k)
                if isinstance(v, _STRING_TYPES) and v:
                    return v
        if isinstance(val, (list, tuple)):
            for v in val:
                r = self._ParseTex(v)
                if r:
                    return r
        return ""

    def _ItemIcon(self, name):
        """物品 ID -> 贴图路径；优先引擎 GetItemTexture，失败回退 GetItemBasicInfo"""
        cached = self._iconCache.get(name)
        if cached is not None:
            return cached or None
        tex = ""
        cf = clientApi.GetEngineCompFactory()
        for pid in (clientApi.GetLocalPlayerId(), clientApi.GetLevelId()):
            if not pid:
                continue
            comp = None
            try:
                comp = cf.CreateItem(pid)
            except Exception:
                continue
            if comp is None:
                continue
            for call in (lambda: comp.GetItemTexture(name, 0),
                         lambda: comp.GetItemTexture(name)):
                try:
                    got = call()
                except Exception:
                    got = None
                if self._iconDebug < 6:
                    self._iconDebug += 1
                    print("[RandomPocket] icon raw %s -> %r" % (name, got))
                tex = self._ParseTex(got)
                if tex:
                    break
            if tex:
                break
            try:
                info = comp.GetItemBasicInfo(name, 0)
            except Exception:
                info = None
            if self._iconDebug < 6 and info is not None:
                self._iconDebug += 1
                print("[RandomPocket] icon info %s -> %r" % (name, info))
            if isinstance(info, dict):
                for key in ("iconPath", "texture", "texturePath",
                            "icon", "itemTexture"):
                    tex = self._ParseTex(info.get(key))
                    if tex:
                        break
            if tex:
                break
        if tex and not tex.startswith("textures/"):
            tex = "textures/" + tex
        self._iconCache[name] = tex or ""
        return tex or None

    def _SetIcon(self, path, iid):
        node = self._testNode
        if not node:
            return
        try:
            img = node.GetBaseUIControl(path).asImage()
            if not iid:
                img.SetVisible(False)
                return
            tex = self._ItemIcon(iid)
            if tex:
                img.SetSprite(tex)
                img.SetVisible(True)
            else:
                img.SetVisible(False)
        except Exception as e:
            if self._iconErr < 6:
                self._iconErr += 1
                print("[RandomPocket] set icon %s error: %s" % (path, e))

    def RefreshPool(self):
        if not self._testNode or self._testBase is None:
            return
        entries = []
        for it in self._pool:
            if isinstance(it, dict):
                iid = it.get("id") or ""
                cn = it.get("name") or ""
            else:
                iid, cn = str(it), ""
            entries.append((iid, cn))
        kw = self._poolFilter.lower()
        if kw:
            entries = [e for e in entries
                       if kw in e[0].lower() or kw in e[1].lower()]
        total = len(self._pool)
        matched = len(entries)
        pages = max(1, (matched + POOL_CELLS - 1) // POOL_CELLS)
        if self._poolPage >= pages:
            self._poolPage = pages - 1
        start = self._poolPage * POOL_CELLS
        self._pageEntries = entries[start:start + POOL_CELLS]
        for i in range(POOL_CELLS):
            iid = self._pageEntries[i][0] if i < len(self._pageEntries) else None
            self._SetIcon(
                self._testBase + "/pool_dialog/cell_%d/icon" % i, iid)
        self._SetLabel("/pool_dialog/title_label",
                       "奖池：共 %d 个（匹配 %d）" % (total, matched))
        self._SetLabel("/pool_dialog/page_label",
                       "%d/%d" % (self._poolPage + 1, pages))

    # ---------- 奖池数据 ----------
    def OnPoolChunk(self, args):
        if not isinstance(args, dict):
            return
        try:
            index = int(args.get("index", 0))
            total = int(args.get("total", 1))
        except Exception:
            return
        items = args.get("items") or []
        if not isinstance(items, list):
            return
        self._poolChunks[index] = items
        self._poolTotal = total
        if len(self._poolChunks) < total:
            return
        pool = []
        for i in range(total):
            pool.extend(self._poolChunks.get(i, []))
        self._pool = pool
        self._poolChunks = {}
        print("[RandomPocket] pool received items=%d" % len(pool))
        self.RefreshPool()

    def GetPool(self):
        return self._pool

    def RequestPool(self):
        try:
            self.NotifyToServer(POOL_REQUEST_EVENT, {
                "playerId": clientApi.GetLocalPlayerId()})
        except Exception as e:
            print("[RandomPocket] request pool error: %s" % e)

    def RequestRefresh(self):
        try:
            self.NotifyToServer(REFRESH_EVENT, {
                "playerId": clientApi.GetLocalPlayerId()})
        except Exception as e:
            print("[RandomPocket] request refresh error: %s" % e)
