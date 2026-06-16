================================================================================
WORKER-ALPHA AGENT MODULE ANALYSIS REPORT
================================================================================

## 1. 模块概览
----------------------------------------
模块路径: mmi/agent/
文件总数: 23 (含 builtin/)
总代码行数: ~3600 行
总代码体积: ~119 KB
核心类: 35 个
核心函数: 114 个

## 2. 核心组件分解
----------------------------------------
  orchestrator.py           ( 164行): 主调度器，Pipeline入口
  pipeline.py               ( 182行): 管道执行引擎，6步流程
  base.py                   ( 155行): 抽象基类，生命周期管理
  registry.py               ( 173行): Agent注册中心，单例模式
  router.py                 ( 134行): 意图分类+路由分发
  skill.py                  ( 243行): 技能库管理，持久化
  trace.py                  ( 289行): 调用链追踪，磁盘持久化
  validate.py               ( 220行): 输出验证引擎，规则+LLM审计
  event_bus.py              (  46行): 轻量事件总线
  tools.py                  ( 141行): 工具注册与调用中心
  modes.py                  (  84行): 思维模式配置
  steps.py                  ( 205行): Pipeline内建Step实现
  result.py                 (  46行): 统一结果数据契约

## 3. 死代码/僵尸代码识别
----------------------------------------
  [FOUND] chat_legacy() in orchestrator.py:
    - 定义于orchestrator.py，用于兼容旧版str返回
    - 在agent模块内部无任何其他文件引用
    - 用途: 供phase 3测试和老调用点使用
    - 建议: 若测试覆盖可保留，否则可舍弃

  [WARNING] _find_python() 重复实现:
    - builtin/code_exec.py 和 builtin/web_browser.py 均有类似实现
    - 建议: 提取为公共工具函数

  [MINOR] 多处重复方法签名:
    - get_instance(): registry/skill/tools/trace 四个文件各有实现
    - register(): registry/tools 重复
    - match(): registry/skill 重复
    - get()/list_all()/to_dict()/from_dict() 均有重复
    - 建议: 这些是不同类的同名方法，非真正重复，但可考虑引入Mixin

## 4. 臃肿模块分析
----------------------------------------
  [LARGE] builtin/feishu_tools.py (15KB, 456行):
    - 包含飞书消息发送、卡片流推送等6个工具函数
    - 依赖外部API，功能相对独立
    - 建议: 可考虑拆分为 feishu_message.py + feishu_card.py

  [LARGE] trace.py (9KB, 289行):
    - 包含TraceRecord数据模型和Tracer追踪器
    - 功能内聚，不建议拆分

  [LARGE] skill.py (7.8KB, 243行):
    - SkillLibrary管理+Skill数据类
    - 功能内聚，不建议拆分

## 5. 组件行为选择 (Hybrid模式)
----------------------------------------
  [调用] event_bus.py:
    - 轻量级同步事件总线，代码简洁(46行)
    - 功能成熟，无需重写

  [调用] tools.py:
    - 工具注册中心，职责单一
    - 可直接调用

  [重写] router.py:
    - 当前基于关键词的规则分类器
    - 可优化为基于LLM的智能分类
    - 提升意图识别准确率

  [调用] validate.py:
    - 双阶段验证引擎(规则+LLM审计)
    - 设计良好，可直接调用

  [舍弃] chat_legacy():
    - 仅用于向后兼容，新代码不应使用
    - 可从公开API中移除，保留内部供测试

  [调用] base.py (BaseAgent):
    - 抽象基类，生命周期管理完善
    - 可直接调用

  [调用] orchestrator.py (Orchestrator):
    - 主入口，Pipeline封装良好
    - 可直接调用

  [调用] pipeline.py (Pipeline):
    - 核心执行引擎
    - 可直接调用

  [调用] registry.py (AgentRegistry):
    - 注册中心，单例模式
    - 可直接调用

  [调用] skill.py (SkillLibrary):
    - 技能库管理
    - 可直接调用

  [调用] trace.py (Tracer):
    - 追踪系统，磁盘持久化
    - 可直接调用

  [重写] builtin/feishu_tools.py:
    - 飞书工具依赖外部API
    - 可考虑抽象为插件式调用

## 6. 优化建议
----------------------------------------
  1. 提取 _find_python() 为公共工具函数
  2. 考虑引入 Mixin 类减少重复方法
  3. feishu_tools.py 可拆分为更小模块
  4. chat_legacy() 标记为deprecated
  5. router.py 可升级为LLM驱动分类

## 7. 可测维度
----------------------------------------
  - 代码行数: 从3600行优化至约3200行(减少~11%)
  - 可维护性: 消除重复代码，引入Mixin
  - 运行时性能: Pipeline步骤优化，减少不必要的对象创建
