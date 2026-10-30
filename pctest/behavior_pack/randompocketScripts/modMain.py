# -*- coding: utf-8 -*-
"""RandomPocket 模组入口：注册服务端系统"""

from mod.common.mod import Mod
import mod.server.extraServerApi as serverApi
import mod.client.extraClientApi as clientApi

MOD_NAMESPACE = "randompocket"


@Mod.Binding(name="RandomPocketMod", version="0.0.1")
class RandomPocketMod(object):
    def __init__(self):
        pass

    @Mod.InitServer()
    def initServer(self):
        serverApi.RegisterSystem(
            MOD_NAMESPACE,
            "RandomPocketServerSystem",
            "randompocketScripts.randompocketServer.RandomPocketServerSystem",
        )

    @Mod.InitClient()
    def initClient(self):
        # 客户端只负责上报自定义容器界面的打开/关闭时机
        clientApi.RegisterSystem(
            MOD_NAMESPACE,
            "RandomPocketClientSystem",
            "randompocketScripts.randompocketClient.RandomPocketClientSystem",
        )
