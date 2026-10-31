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
| 1.1.5 | 2026-10-31 | 测试按钮查找改为 BFS 按名遍历容器屏控件树（`GetChildByName`），不再硬编码 common 模板路径 | 当前版本，测试中 |
| 1.1.4 | 2026-10-31 | 增加 `GetScreenName` / 结构探测诊断日志 | 定位用 |
| 1.1.3 | 2026-10-31 | 修复口袋物品重开后自动排序：内容存储改为「槽位→物品」字典，旧列表存档自动迁移 | 物品位置保持 |
| 1.1.2 | 2026-10-31 | 修正接口名：`GetTopPushedUI` → `GetTopUINode` | 修复运行时 AttributeError |
| 1.1.1 | 2026-10-31 | 测试按钮/奖池弹窗改为**内嵌容器屏 JSON**，用 `GetTopUINode` + `SetButtonTouchUpCallback` 挂回调（替代 CreateUI 独立面板） | 方案重写 |
| 1.1.0 | 2026-10-31 | 新增 `/rp test` 测试模式：打开口袋显示「查看奖池 / 刷新一天」；奖池弹窗支持中文名+ID 搜索、分页（每页 12 条）；奖池分块下发（150 条/块）；非测试模式完全不显示 | 功能新增 |
| 1.0.9 | 2026-10-31 | 修复按钮断言 `Control name could not be resolved: default`：引入 `netease_editor_template_namespace.json` 并内联按钮控件 | 修复卡死 |
| 1.0.0 ~ 1.0.8 | 2026-10-30 ~ 10-31 | 核心功能迭代：每日刷新、10 格容器、满态红色贴图、extraId+ExtraData 存储重构、奖池对照官网全物品动态生成（1445 个，剔除口袋自身/空气/流水/命令方块等特殊物品） | 见 git 提交记录 |

---

## 1.1.5（当前）

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
