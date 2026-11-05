# RandomPocket 版本记录

## 版本规则
- 版本号格式：`${主版本号}.${次版本号}.${修订版本号}`，三个位置同步写在
  `randompocket_behavior/manifest.json` 与 `randompocket_resource/manifest.json`（含 dependencies）
- **每次修改包内容必须升版本号**：网易客户端对同 UUID 同版本的包会沿用旧缓存文件，不升号改动不生效
- 功能新增升次版本号，纯修复/迭代升修订版本号
- 构建：`python build.py`，产物为 `RandomPocket.mcaddon`、`RandomPocket.zip`、`pctest/`（PC 开发版）、`promo/`（宣传图）

---

## 版本汇总

| 版本 | 日期 | 更新内容 | 备注 |
| :--- | :--- | :--- | :--- |
| 1.3.2 | 2026-11-05 | 修复进世界瞬间手持口袋时按钮常亮不隐藏：HUD 创建前收到的显示通知没排 3 秒定时器，`_EnsureHud` 末尾补排 | 当前版本 |
| 1.3.1 | 2026-11-05 | 「打开」按钮默认位置上抬（offset -25→-33）；按钮改为**手持切到口袋时亮 3 秒**自动隐藏（服务端监听切换手持事件 + 每秒轻量轮询手持槽位）；修复奖池格子无图标（`_ItemIcon` 对齐 RandomBox：兼容 str/dict/tuple 返回值、双参/单参 `GetItemTexture` 都试、去掉误杀短路径的校验，并加原始返回值探测日志）；修复弹窗打开时口袋网格未隐藏（BFS 深度上限 8→12，grid 实际在 10 层） | 已验证可用 |
| 1.3.0 | 2026-11-05 | 新增 `/rp ui` 按钮调整模式（拖动调位置、＋/－调大小、完成保存，配置存 ExtraData 跨存档保留）；查看奖池重写为图标网格版（参考 RandomBox：物品图标、点图标看名称、每页 24 格，弹窗打开时隐藏口袋网格修掉数字置顶杂乱） | 格子无图标，已由 1.3.1 修复 |
| 1.2.0 | 2026-11-05 | 修复锚点断言：基岩版无 `bottom_center`，改 `bottom_middle`（此前引擎兜底到屏幕中心导致按钮偏高且渲染异常）；半透明贴图调亮（24%/39%/55%） | 已验证可用 |
| 1.1.9 | 2026-11-05 | HUD 按钮外观：缩小至 36×14（原 72×24 的一半）、文字改为「打开」、绿色贴图换成自生成半透明黑（35%/50%/63% 三态）、位置移到快捷栏正中上方 | 锚点断言崩溃 |
| 1.1.8 | 2026-11-05 | HUD 按钮显隐改为服务端驱动：客户端无 GetSelectSlotId/GetInvItem（服务端专用接口），改为服务端扫描快捷栏有口袋时下发 `rb_hud_state` | 已验证可用 |
| 1.1.7 | 2026-11-05 | HUD 按钮轮询诊断：拆掉静默 except，加一次性能力报告（carried/slot/invErr）+ 显隐变化日志 + 服务端按钮请求日志 | 定位用 |
| 1.1.6 | 2026-11-05 | 修复手机端无法右键打开口袋：手持口袋时 HUD 显示「打开口袋」按钮，点击由服务端打开容器 | 按钮未显示，诊断中 |
| 1.1.5 | 2026-10-31 | 测试按钮查找改为 BFS 按名遍历容器屏控件树（`GetChildByName`），不再硬编码 common 模板路径 | 测试中 |
| 1.1.4 | 2026-10-31 | 增加 `GetScreenName` / 结构探测诊断日志 | 定位用 |
| 1.1.3 | 2026-10-31 | 修复口袋物品重开后自动排序：内容存储改为「槽位→物品」字典，旧列表存档自动迁移 | 物品位置保持 |
| 1.1.2 | 2026-10-31 | 修正接口名：`GetTopPushedUI` → `GetTopUINode` | 修复运行时 AttributeError |
| 1.1.1 | 2026-10-31 | 测试按钮/奖池弹窗改为**内嵌容器屏 JSON**，用 `GetTopUINode` + `SetButtonTouchUpCallback` 挂回调（替代 CreateUI 独立面板） | 方案重写 |
| 1.1.0 | 2026-10-31 | 新增 `/rp test` 测试模式：打开口袋显示「查看奖池 / 刷新一天」；奖池弹窗支持中文名+ID 搜索、分页（每页 12 条）；奖池分块下发（150 条/块）；非测试模式完全不显示 | 功能新增 |
| 1.0.9 | 2026-10-31 | 修复按钮断言 `Control name could not be resolved: default`：引入 `netease_editor_template_namespace.json` 并内联按钮控件 | 修复卡死 |
| 1.0.0 ~ 1.0.8 | 2026-10-30 ~ 10-31 | 核心功能迭代：每日刷新、10 格容器、满态红色贴图、extraId+ExtraData 存储重构、奖池对照官网全物品动态生成（1445 个，剔除口袋自身/空气/流水/命令方块等特殊物品） | 见 git 提交记录 |

---

## 1.3.2（当前）

**发布日期**：2026-11-05

### 更新内容（相对 1.3.1）
1. **修复进世界瞬间手持口袋时「打开」按钮常亮**：日志实证——客户端收到 show=True 时 HUD 界面尚未创建（`OnHudState` 直接 return，3 秒隐藏定时器未排），`_EnsureHud` 点亮按钮后无人隐藏，按钮从进世界一直亮到下次切换手持（实测 32 秒）。修复：`_EnsureHud` 末尾若 `_hudWanted` 为 True 则补排 `_ScheduleHudHide`

### 日志确认的存疑观察点（未改）
- 启动时 `SetEntityItem (0,0) False`：世界加载瞬间物品栏未就绪导致首个口袋 extraId 写入失败，会话内靠 ExtraData + `_slotUid` 兜底无恙，但该口袋**重进世界后会重新分配 uid、原内容丢失**
- 口袋满后仍出现 `测试刷新 +1 (10/10)`：可能是「界面取出一个再点刷新」的正常操作，也可能多口袋状态串扰，待观察

---

## 1.3.1

**发布日期**：2026-11-05

### 更新内容（相对 1.3.0）
1. 「打开」按钮默认位置抬高：offset `[0,-25]` → `[0,-33]`（仍可用 `/rp ui` 自行调整）
2. **按钮显示逻辑改为「切到口袋时亮 3 秒」**：不再常驻。服务端监听 `OnCarriedNewItemChangedServerEvent`（切换手持立即响应）+ 每秒轻量轮询手持槽位（`GetSelectSlotId` + `GetPlayerItem`，接口失效自动停止轮询不刷屏）；客户端收到显示通知后 `AddTimer(3.0)` 自动隐藏，序号防旧定时器误隐藏
3. **修复奖池格子无图标**：`_ItemIcon` 对齐 RandomBox 写法——`GetItemTexture` 双参/单参两种调用都试，返回值兼容 str/dict/tuple（`_ParseTex` 统一抽取），删除会把短路径清空的 `"/" not in` 校验；新增前 6 次原始返回值探测日志（`icon raw <id> -> ...`）便于实证
4. **修复弹窗打开时口袋网格未隐藏**：`grid path -> None` 实证为 BFS 深度上限 8 截断了 grid 所在的 10 层路径（`root_panel/common_panel/bg_image/chest_panel/randompocket_panel_top_half/...`），上限提至 12

---

## 1.3.0

**发布日期**：2026-11-05

### 更新内容（相对 1.2.0）
1. **新增 `/rp ui` 按钮调整模式**：聊天输入 `/rp ui` 后「打开」按钮强制显示并进入调整状态——拖动按钮调位置（`SetPosition`），顶部 －/＋ 按钮调大小（`SetSize`，宽 24~96 步进 6、保持 36:14 比例），点「完成」退出并通过 `rb_ui_cfg_save` 存到服务端 ExtraData（`rb_ui_cfg`）；进世界首次扫描时经 `rb_ui_cfg` 下发恢复
2. **查看奖池图形化重写**（参考 RandomBox 设计）：
   - 列表文字行改为 6 列 × 4 行图标网格（每页 24 个，`pool_cell` 模板：button + icon image）
   - 图标由客户端 `GetItemTexture(name, 0)` 解析贴图路径、`SetSprite` 设置，回退 `GetItemBasicInfo` 的 iconPath，带缓存
   - 点图标在下方 name_label 显示「中文名 ID」
   - 打开弹窗时 `_SetGridVisible(False)` 隐藏口袋物品网格，修复格子数字置顶盖住弹窗的杂乱问题；关闭弹窗恢复
3. 已知限制：`SetButtonTouchMoveCallback` 仅触屏触发，PC 端不能拖动位置（可用 －/＋ 调大小；位置需改 json 默认 offset）

---

## 1.2.0

**发布日期**：2026-11-05

### 更新内容（相对 1.1.9）
1. **修复断言 `Unrecognized anchor or alignment value: bottom_center`**：基岩版合法锚点是 `bottom_middle`。锚点解析失败后引擎按屏幕中心兜底 → 按钮「太高」、渲染状态异常（看着不透明）
2. 半透明贴图不透明度调亮：默认 60/255（24%）、悬停 100/255、按下 140/255
3. 按钮位置/尺寸自助调整入口：[randompocket_hud.json](file:///c:/Data(E)/Trae/RandomPocket/randompocket_resource/ui/randompocket_hud.json) 的 `offset`（y 越负越靠上）与 `size`；透明度改 `textures/ui/rp_btn_*.png` 的 alpha

---

## 1.1.9

**发布日期**：2026-11-05

### 更新内容（相对 1.1.8）
1. 按钮尺寸 72×24 → **36×14**（约一半，适配两字文字）
2. 文字「打开口袋」→「**打开**」（小号字体）
3. 背景从引擎绿色贴图改为自生成**半透明黑**贴图（default/hover/pressed = 35%/50%/63% 不透明度，`textures/ui/rp_btn_*.png`）
4. 位置从右下角移到**快捷栏正中上方**（bottom_center, offset [0,-25]，正好落在心形/饱食度两条状态栏中间的空隙）

---

## 1.1.8

**发布日期**：2026-11-05

### 更新内容（相对 1.1.7）
1. **修复 HUD 按钮不显示**：诊断日志确认客户端 `ItemCompClient` 没有 `GetSelectSlotId` / `GetInvItem`（均为服务端专用接口），手持检测在客户端不可行
2. 改为服务端驱动：`_RefreshAll` 每 2 秒扫描玩家口袋时顺带判断「快捷栏（CARRIED）是否有口袋」，状态变化时 `NotifyToClient` 下发 `rb_hud_state`，客户端只做显隐
3. 显示条件从「手持口袋」放宽为「口袋在快捷栏」；客户端删除轮询定时器
4. 保留一次性 `dir()` 探测日志（`client item comp api: ...`），为以后恢复精确手持检测留资料

---

## 1.1.7

**发布日期**：2026-11-05

### 更新内容（相对 1.1.6）
1. HUD 按钮在 PC 模拟手机端不显示，定位为手持检测环节被静默 except 吞掉错误；改为分步捕获并输出：
   - 一次性能力报告 `hud caps: carried=.. slot=.. slotErr=.. invErr=..`（判断 CARRIED 枚举 / GetSelectSlotId / GetInvItem 哪个不可用）
   - 显隐变化日志 `hud button visible=..`
   - 服务端 `open request from hud button`（区分按钮触发与右键触发）
2. 功能逻辑不变

---

## 1.1.6

**发布日期**：2026-11-05

### 更新内容（相对 1.1.5）
1. **修复手机端打不开口袋**：口袋物品无使用行为，手机端（无右键）引擎不发使用事件。新增 HUD 方案——手持口袋时屏幕右下角显示「打开口袋」按钮（`randompocket_hud.json`，HUD 层，常态隐藏，客户端 0.3s 轮询手持物品控制显隐）
2. 点击按钮发送 `rb_open_request` 给服务端，优先打开手持的那个口袋（按 extraId 匹配），拿不到选中槽位时退化为身上第一个口袋
3. PC 端右键交互不变，两端可同时使用

### 技术要点
- HUD 用 `CreateUI + isHud:1`（容器未打开时不存在遮挡/吞输入问题），按钮回调用 `SetButtonTouchUpCallback`
- 按钮控件内联 default/hover/pressed/button_label 子控件（规避 common.button 模板断言）

---

## 1.1.5

**发布日期**：2026-10-31

### 更新内容（相对 1.1.3）
1. **测试按钮挂载改为控件树 BFS 搜索**：`common.inventory_screen_common` 的中间层名称不透明，硬编码路径全部探测失败；改为从容器屏根节点用 `GetChildByName` 按候选名集合逐层搜索 `test_buttons`，找到即用其父路径
2. 移除硬编码 `_PATH_CANDIDATES`
3. 保留 `GetScreenName` 诊断输出

### 已知问题
- 测试按钮在口袋界面的显示仍待实测验证；若 BFS 仍找不到，备选方案为「伪物品按钮」（容器扩格 + 引擎事件拦截）

---

## 1.1.3

**发布日期**：2026-10-31

### 更新内容
1. **口袋物品位置保持**：bag 存储由紧凑列表改为 `{槽位号: 物品}` 字典，关闭再打开不再自动排序到最前；旧列表格式存档读取时自动迁移
2. 新增 `_BagAdd`（放入第一个空槽）；`_PushBagToUI` / `_ReadUIContainer` / 每日刷新 / 测试刷新全部按槽位读写
3. 增加容器屏路径探测诊断日志

---

## 1.1.1 ~ 1.1.2

**发布日期**：2026-10-31

### 更新内容
1. 测试界面方案重写：PushScreen（吞掉容器输入）与 CreateUI（渲染在容器屏之下）均不可行，改为把测试按钮和奖池弹窗直接写进 `randompocket_container.json`（默认隐藏），容器打开后由客户端运行时接管
2. 删除独立的 `randompocketTestUI.json` / `randompocketTestUI.py`
3. 1.1.2 修正顶层界面获取接口为 `clientApi.GetTopUINode()`

---

## 1.1.0

**发布日期**：2026-10-31

### 更新内容
1. **测试指令 `/rp test`**（支持 `/rp test on|off`，会话内有效，退出重置）：
   - 打开口袋旁边显示「查看奖池」「刷新一天」两个按钮
   - 查看奖池：弹窗列出全部奖池物品，显示 ID + 本地化中文名（`GetItemBasicInfo`），支持按中文名/ID 搜索、分页浏览，用于核对是否覆盖全物品
   - 刷新一天：立即给第一个有空位的口袋 +1 随机物品
   - 非测试模式不显示任何测试界面，不影响正常游玩
2. 奖池数据分块下发（每块 150 条），客户端聚合缓存
3. 附带修复：manifest 写入改用无 BOM UTF-8（PowerShell `Set-Content` 会引入 BOM 导致引擎 `json.load` 失败）

---

## 1.0.9

**发布日期**：2026-10-31

### 更新内容
1. 修复使用 `common.button` 时的引擎断言 `Assertion failed: Control name could not be resolved: default`（按钮模板子控件属于 `netease_editor_template_namespace` 命名空间，官方示例包附带该 json，本包此前缺失）
2. 从官方示例包复制 `netease_editor_template_namespace.json` 并注册进 `_ui_defs.json`；按钮实例内联重写 default/hover/pressed/button_label 四个子控件

---

## 1.0.0 ~ 1.0.8（早期迭代）

**发布日期**：2026-10-30 ~ 2026-10-31

### 主要功能
- **每日随机刷新**：每过 1 个游戏日，给玩家身上第一个还有空位的口袋 +1 随机物品；全部满则当天不刷新
- **口袋容器**：右键打开 10 格宝箱式容器界面，自由存取
- **满态显示**：装满 10 格切换为红色贴图 `pocket_full`，显示名变为「随机口袋·已满」
- **存储方案**：口袋内容不依赖物品 NBT（引擎拒绝写入带自定义 userData 的物品），改为物品 extraId 存 `rb:<uid>` 短标识 + 玩家 ExtraData 存 `rb_<uid>` 内容，物品移动后仍可找回
- **全物品奖池**：对照官方文档动态生成（1445 个），剔除口袋自身、空气、流水、点燃状态、命令方块、结构方块、教育版化学、旧版兼容 ID 等
- 构建脚本 `build.py` 一键打包 mcaddon / zip / pctest / promo

### 备注
- 早期版本逐次升号主要是规避客户端同版本缓存问题，无独立功能说明；详见 git 提交记录
