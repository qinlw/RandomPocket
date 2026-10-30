# -*- coding: utf-8 -*-
"""RandomPocket 客户端系统

服务端没有“自定义容器界面关闭”事件，而 OpenNeteaseContainer 打开的界面
物品数据需要开发者自行维护。因此这里监听客户端引擎的：

    PushScreenEvent  界面创建
    PopScreenEvent   界面移除

把打开/关闭时机转发给服务端，由服务端在界面刚创建时填充口袋内容，
并在界面关闭后停止从界面回读数据（否则空界面会把口袋内容覆盖成空）。
"""

import mod.client.extraClientApi as clientApi

ClientSystem = clientApi.GetClientSystemCls()

try:
    _STRING_TYPES = (str, unicode)
except NameError:
    _STRING_TYPES = (str,)

SCREEN_PREFIX = "randompocket_container"
SCREEN_EVENT = "rb_screen_event"


class RandomPocketClientSystem(ClientSystem):
    def __init__(self, namespace, systemName):
        ClientSystem.__init__(self, namespace, systemName)
        engNs = clientApi.GetEngineNamespace()
        engSys = clientApi.GetEngineSystemName()
        for evtName in ("PushScreenEvent", "PopScreenEvent"):
            handler = getattr(self, evtName, None)
            if handler is None:
                continue
            try:
                self.ListenForEvent(engNs, engSys, evtName, self, handler)
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

    def PushScreenEvent(self, args):
        name = self._ScreenName(args)
        if name.startswith(SCREEN_PREFIX):
            self._NotifyServer("push", name)

    def PopScreenEvent(self, args):
        name = self._ScreenName(args)
        if name.startswith(SCREEN_PREFIX):
            self._NotifyServer("pop", name)
