# 小红书自动运营 Agent 系统

基于 Python 3.11 构建的全自动小红书内容运营系统。根据装修风格自动生成文案和图片，自动发布帖子，自动采集数据并持续优化内容策略。**每天自动发布 30 篇原创帖子。**

---

## 目录

- [系统架构](#系统架构)
- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [数据库设计](#数据库设计)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [API 接口文档](#api-接口文档)
- [定时任务说明](#定时任务说明)
- [Agent 完整流程](#agent-完整流程)
- [内容规则说明](#内容规则说明)
- [模块详细说明](#模块详细说明)
- [常见问题](#常见问题)

---

## 系统架构

```
用户输入风格
     │
     ▼
┌─────────────────────────────────────────────────────┐
│                    Agent 核心流程                     │
│                                                     │
│  知识库检索  →  主题生成  →  文案生成  →  图片生成      │
│  (ChromaDB)   (加权随机)   (LLM API)   (SD API)     │
│                                                     │
│              内容校验 (自动修复/重试)                  │
│                    │                                │
│              发布帖子 (Playwright)                   │
│                    │                                │
│         数据采集 → 数据分析 → 策略优化                 │
└─────────────────────────────────────────────────────┘
     │
     ▼
PostgreSQL  ←→  Redis  ←→  ChromaDB
```

---

## 功能特性

| 模块 | 功能 |
|------|------|
| **主题生成** | 按风格查询主题库，加权随机组合，支持修饰词扩展，每日生成30个不重复主题 |
| **文案生成** | 调用 LLM API，生成符合小红书规则的标题+正文+标签，内置3次重试机制 |
| **图片生成** | 调用 Stable Diffusion API，每篇生成4张不同角度装修效果图，分辨率 ≥ 1024 |
| **内容校验** | 标题长度、正文字数/行数/空白行、标签数量全规则校验，支持 auto_fix 自动修复 |
| **自动发布** | Playwright 模拟浏览器，支持 Cookie 登录，自动上传图片、填写内容、点击发布 |
| **数据采集** | 每日定时爬取帖子浏览、点赞、收藏、评论数据并回写数据库 |
| **数据分析** | 计算帖子评分、识别高低表现内容、分析差评内容特征 |
| **策略优化** | 高表现主题权重 ×1.15，低表现主题权重 ×0.88，持续自我进化 |
| **定时调度** | APScheduler 驱动，每天4个定时任务全自动运行 |
| **HTTP API** | FastAPI 提供完整 REST 接口，支持手动触发任何流程 |

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.11 |
| Web 框架 | FastAPI 0.104 + Uvicorn |
| 数据库 | PostgreSQL + SQLAlchemy 2.x（异步） |
| 缓存/队列 | Redis 5.x + Celery |
| 向量数据库 | ChromaDB 0.4 |
| 任务调度 | APScheduler 3.10 |
| LLM | OpenAI 兼容 API（gpt-4o） |
| 图片生成 | Stable Diffusion WebUI API（A1111） |
| 浏览器自动化 | Playwright 1.40 |
| 图片处理 | Pillow |
| 日志 | Loguru |
| 重试机制 | Tenacity |

---

## 项目结构

```
xiaohongshu/
│
├── main.py                           # 主入口：FastAPI 服务 + CLI 模式
│
├── config/
│   └── config.yaml                   # 全局配置文件（数据库/Redis/LLM/SD/小红书账号）
│
├── database/
│   ├── __init__.py
│   ├── database.py                   # 异步数据库连接池、Session 工厂
│   ├── models.py                     # SQLAlchemy ORM 模型定义（4张表）
│   └── repository.py                 # 数据访问层（CRUD 封装）
│
├── knowledge/
│   ├── __init__.py
│   ├── style_repository.py           # 风格知识库管理（含内置种子数据）
│   └── vector_store.py               # ChromaDB 向量存储与语义检索
│
├── generators/
│   ├── __init__.py
│   ├── topic_generator.py            # 主题生成（加权随机 + 修饰词组合）
│   ├── content_generator.py          # 文案生成（LLM API 调用 + 解析）
│   └── prompt_templates.py           # 所有 Prompt 模板（LLM + SD）
│
├── image/
│   ├── __init__.py
│   └── image_generator.py            # 图片生成（SD API，每篇4张）
│
├── validation/
│   ├── __init__.py
│   └── content_validator.py          # 内容合规校验 + auto_fix 自动修复
│
├── publisher/
│   ├── __init__.py
│   └── xiaohongshu_publisher.py      # Playwright 自动化发布
│
├── analytics/
│   ├── __init__.py
│   ├── data_collector.py             # Playwright 数据采集（浏览/点赞/收藏/评论）
│   └── performance_analyzer.py       # 表现评分计算与差评内容分析
│
├── optimizer/
│   ├── __init__.py
│   └── strategy_optimizer.py         # 主题权重动态调整策略
│
├── scheduler/
│   ├── __init__.py
│   └── daily_job.py                  # APScheduler 每日4个定时任务
│
├── storage/                          # 自动创建
│   ├── images/                       # 生成图片存储目录
│   └── temp/                         # 临时文件目录
│
├── cookies/                          # 自动创建
│   └── xhs_cookies.json              # 小红书登录 Cookie（运行后自动保存）
│
├── chroma_data/                      # 自动创建（ChromaDB 持久化数据）
├── logs/                             # 自动创建（日志文件）
│
└── requirements.txt                  # 项目依赖
```

---

## 数据库设计

### style_category — 装修风格分类表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| style_name | VARCHAR(50) | 风格名称（唯一），如：原木风、法式风 |
| description | TEXT | 风格描述 |
| created_at | TIMESTAMP | 创建时间 |

### style_topics — 风格主题表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| style_id | INTEGER | 外键 → style_category.id |
| topic_keyword | VARCHAR(100) | 主题关键词，如：小户型原木客厅改造 |
| weight | FLOAT | 权重（0.0 ~ 5.0），影响被选中概率 |
| performance_score | FLOAT | 历史表现评分（由优化模块更新） |
| created_at | TIMESTAMP | 创建时间 |

### style_examples — 风格案例表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| style_id | INTEGER | 外键 → style_category.id |
| title | VARCHAR(50) | 案例标题 |
| content | TEXT | 案例正文 |
| image_prompt | TEXT | SD 图片生成提示词 |
| tags | JSON | 标签列表（JSON 数组） |
| performance_score | FLOAT | 案例表现评分 |
| post_records_id | INTEGER | 关联发布记录 ID（可选） |

### post_records — 帖子发布记录表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| style_id | INTEGER | 外键 → style_category.id |
| title | VARCHAR(50) | 帖子标题 |
| content | TEXT | 帖子正文 |
| images | JSON | 图片本地路径列表 |
| views | INTEGER | 浏览量（采集更新） |
| likes | INTEGER | 点赞数（采集更新） |
| favorites | INTEGER | 收藏数（采集更新） |
| comments | INTEGER | 评论数（采集更新） |
| publish_time | TIMESTAMP | 发布时间 |
| xhs_post_id | VARCHAR(100) | 小红书帖子 ID |
| performance_score | FLOAT | 表现评分（自动计算） |

---

## 快速开始

### 1. 环境要求

- Python 3.11+
- PostgreSQL 14+
- Redis 6+
- Stable Diffusion WebUI（本地或云端，A1111 兼容）
- 有效的 OpenAI API Key（或兼容接口）

### 2. 克隆项目 & 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器驱动
playwright install chromium
```

### 3. 初始化数据库

```bash
# 创建 PostgreSQL 数据库
psql -U postgres -c "CREATE DATABASE xiaohongshu_agent;"
```

### 4. 修改配置文件

编辑 `config/config.yaml`，填写以下必填项：

```yaml
database:
  password: "your_pg_password"        # PostgreSQL 密码

llm:
  api_key: "sk-xxxx"                  # OpenAI API Key
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"

stable_diffusion:
  api_url: "http://127.0.0.1:7860"    # SD WebUI 地址

xiaohongshu:
  username: "your_phone_number"       # 小红书手机号
  password: "your_password"           # 小红书密码
```

### 5. 启动服务

```bash
# FastAPI 服务模式（推荐，自带定时调度）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# CLI 单次测试模式（测试5篇，调试用）
python main.py cli
```

### 6. 访问 API 文档

启动后访问：[http://localhost:8000/docs](http://localhost:8000/docs)

---

## 配置说明

`config/config.yaml` 完整配置项说明：

```yaml
# ── 数据库 ──────────────────────────────────────────
database:
  host: "localhost"
  port: 5432
  name: "xiaohongshu_agent"
  user: "postgres"
  password: "your_password"       # 必填
  pool_size: 10                   # 连接池大小
  max_overflow: 20                # 最大溢出连接数

# ── Redis ────────────────────────────────────────────
redis:
  host: "localhost"
  port: 6379
  db: 0
  password: ""                    # 无密码留空

# ── LLM API（OpenAI 兼容）────────────────────────────
llm:
  api_key: "your_openai_api_key"  # 必填
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"                 # 支持任何 OpenAI 兼容模型
  max_tokens: 1024
  temperature: 0.8                # 创意度（0~1，越高越有创意）
  max_retries: 3

# ── Stable Diffusion API ─────────────────────────────
stable_diffusion:
  api_url: "http://127.0.0.1:7860"  # 必填：SD WebUI 地址
  steps: 30                          # 推理步数（越高质量越好，越慢）
  cfg_scale: 7                       # 提示词引导强度
  width: 1024                        # 图片宽度（≥1024）
  height: 1024                       # 图片高度（≥1024）
  sampler_name: "DPM++ 2M Karras"

# ── 小红书账号 ────────────────────────────────────────
xiaohongshu:
  username: "your_username"       # 手机号
  password: "your_password"       # 密码
  cookie_file: "./cookies/xhs_cookies.json"  # Cookie 文件路径
  publish_interval: 120           # 每篇发布间隔（秒），建议 ≥ 120

# ── 内容规则（不建议修改）─────────────────────────────
content_rules:
  title_max_length: 20
  body_max_chars: 500
  body_max_lines: 30
  images_per_post: 4
  image_min_resolution: 1024
  tags_min: 3
  tags_max: 5

# ── 定时调度 ──────────────────────────────────────────
scheduler:
  generate_time: "08:00"          # 生成内容时间
  publish_time: "09:00"           # 发布内容时间
  collect_time: "18:00"           # 采集数据时间
  optimize_time: "23:00"          # 优化策略时间
  daily_post_count: 30            # 每天发布数量

# ── 存储路径 ──────────────────────────────────────────
storage:
  image_dir: "./storage/images"
  temp_dir: "./storage/temp"
```

---

## API 接口文档

服务启动后完整文档访问：`http://localhost:8000/docs`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 系统健康检查 |
| GET | `/api/status` | 查看系统状态（调度器/帖子总数/风格列表） |
| POST | `/api/run-agent` | 手动触发完整 Agent 流程（生成 + 发布） |
| POST | `/api/generate` | 仅生成内容，缓存到 Redis，不发布 |
| POST | `/api/publish` | 发布 Redis 中已缓存的内容 |
| GET | `/api/report` | 获取帖子表现分析报告 |
| POST | `/api/optimize` | 手动触发策略优化 |
| GET | `/api/topics` | 查看指定风格的主题列表 |
| POST | `/api/collect-data` | 手动触发数据采集 |

### 请求示例

```bash
# 触发完整 Agent 流程（原木风，生成并发布30篇）
curl -X POST http://localhost:8000/api/run-agent \
  -H "Content-Type: application/json" \
  -d '{"style_name": "原木风", "post_count": 30}'

# 仅生成内容（不发布）
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"style_name": "法式风", "post_count": 5}'

# 查看数据分析报告
curl http://localhost:8000/api/report

# 查看主题列表
curl "http://localhost:8000/api/topics?style_name=原木风"
```

---

## 定时任务说明

系统启动后，APScheduler 自动按以下时间表执行任务（时区：Asia/Shanghai）：

```
08:00  ── 生成内容任务
         ├── 检索风格知识库（ChromaDB 向量检索）
         ├── 主题生成（加权随机，30个主题）
         ├── 文案生成（LLM API，每篇最多重试3次）
         ├── 图片生成（SD API，每篇4张，并发生成）
         ├── 内容校验（auto_fix + 重试）
         └── 缓存到 Redis（TTL 24小时）

09:00  ── 发布帖子任务
         ├── 从 Redis 读取生成内容
         ├── Playwright 逐篇发布（间隔120秒）
         └── 发布结果写入 post_records 表

18:00  ── 数据采集任务
         ├── 查询所有已发布帖子（含 xhs_post_id）
         ├── Playwright 访问帖子详情页
         └── 采集并更新 views/likes/favorites/comments

23:00  ── 策略优化任务
         ├── 计算所有帖子表现评分
         │   score = views×0.2 + likes×0.4 + favorites×0.4
         ├── 高表现主题（评分 ≥ 200）权重 × 1.15
         ├── 低表现主题（评分 < 50）权重 × 0.88
         └── 权重范围限制：[0.1, 5.0]
```

---

## Agent 完整流程

```
① 用户输入装修风格（如：原木风）
         │
② 向量检索相关案例（ChromaDB 语义检索）
         │
③ 主题生成
   ├── 查询 style_topics 表（按权重排序）
   ├── 加权随机抽样核心主题
   └── 修饰词组合扩展变体主题
         │
④ 文案生成（LLM API）
   ├── 系统 Prompt：小红书博主人设
   ├── 用户 Prompt：主题 + 参考案例
   └── 解析输出：标题 / 正文 / 标签
         │
⑤ 图片生成（Stable Diffusion API）
   ├── 构建 SD Prompt（风格前缀 + 空间 + 角度）
   ├── 并发生成4张图（4种光线/角度）
   └── 保存到 storage/images/
         │
⑥ 内容校验
   ├── 标题 ≤ 20 字
   ├── 正文 ≤ 500 字 / ≤ 30 行 / 无空白行
   ├── 标签 3~5 个
   ├── 图片 4 张
   └── 不合规 → auto_fix 修复 → 重试生成（最多3次）
         │
⑦ 发布帖子（Playwright）
   ├── Cookie 登录小红书创作者中心
   ├── 上传4张图片
   ├── 填写标题和正文
   └── 点击发布 → 获取帖子 ID
         │
⑧ 数据采集
   └── 爬取 views / likes / favorites / comments
         │
⑨ 数据分析
   ├── 计算评分：score = views×0.2 + likes×0.4 + favorites×0.4
   └── 识别高/低表现内容，分析差评特征
         │
⑩ 更新知识库
   └── 调整主题权重，优化后续内容方向
```

---

## 内容规则说明

系统内置小红书平台内容规则校验，所有生成内容发布前均经过严格检查：

| 规则项 | 限制 | 处理策略 |
|--------|------|----------|
| 标题长度 | ≤ 20 字 | auto_fix 自动截断 |
| 正文字数 | ≤ 500 字 | auto_fix 自动截断 |
| 正文行数 | ≤ 30 行 | auto_fix 去除多余行 |
| 空白行 | 禁止 | auto_fix 自动删除 |
| 话题标签 | 3 ~ 5 个 | 重新生成 |
| 图片数量 | 4 张 | 重新生成图片 |
| 图片分辨率 | ≥ 1024px | 自动放大补足 |

---

## 模块详细说明

### knowledge/style_repository.py — 风格知识库

内置5种装修风格的种子数据，系统首次启动时自动写入数据库：

| 风格 | 内置主题数 |
|------|-----------|
| 原木风 | 12 个 |
| 法式风 | 8 个 |
| 新中式 | 7 个 |
| 北欧风 | 6 个 |
| 现代简约 | 6 个 |

### generators/prompt_templates.py — Prompt 模板

**LLM 文案生成 Prompt 示例输出：**

```
标题：
法式原木客厅太治愈

正文：
最近刚完成的小户型客厅装修，整体做了法式原木风设计，
地板选择浅色橡木，搭配奶油白墙面，空间看起来非常温暖，
沙发选择低矮布艺，视觉更加开阔，小户型一定要控制家具尺寸，
整体花费30w左右，效果非常满意

#原木风装修#小户型客厅#法式装修
```

**SD 图片 Prompt 结构：**

```
{风格前缀}, {空间类型}, {角度描述},
professional interior photography, high quality, realistic,
8k resolution, beautiful lighting, magazine style, photorealistic
```

### analytics/performance_analyzer.py — 评分公式

```
score = views × 0.2 + likes × 0.4 + favorites × 0.4
```

| 评分范围 | 等级 | 处理策略 |
|----------|------|----------|
| ≥ 200 | 高表现 | 关联主题权重 × 1.15 |
| 50 ~ 200 | 中等 | 保持权重不变 |
| < 50 | 低表现 | 关联主题权重 × 0.88 |

---

## 常见问题

**Q：首次运行需要手动登录小红书吗？**

A：是的。首次运行时 Playwright 会打开浏览器等待手动登录（最多60秒）。登录成功后 Cookie 会自动保存到 `cookies/xhs_cookies.json`，后续运行自动使用 Cookie 登录，无需再次手动操作。

---

**Q：没有本地 Stable Diffusion，怎么使用图片生成？**

A：修改 `config/config.yaml` 中的 `stable_diffusion.api_url` 为云端 SD API 地址（需兼容 A1111 接口）。也可以自行修改 `image/image_generator.py` 对接其他图片生成服务（如 DALL-E、Midjourney API 等）。

---

**Q：支持国内 LLM（如 DeepSeek、Qwen）吗？**

A：支持所有 OpenAI 兼容接口。修改配置即可：

```yaml
llm:
  api_key: "your_deepseek_key"
  base_url: "https://api.deepseek.com/v1"
  model: "deepseek-chat"
```

---

**Q：如何添加新的装修风格？**

A：在 `knowledge/style_repository.py` 的 `SEED_STYLES` 列表中添加新风格数据，重启服务后自动写入数据库。或者直接调用数据库接口插入 `style_category` 和 `style_topics` 表。

---

**Q：如何调整每天发布时间？**

A：修改 `config/config.yaml` 中的 scheduler 配置：

```yaml
scheduler:
  generate_time: "07:00"   # 改为 7 点生成
  publish_time: "08:30"    # 改为 8:30 发布
  collect_time: "20:00"    # 改为 20 点采集
  optimize_time: "22:00"   # 改为 22 点优化
  daily_post_count: 20     # 改为每天发 20 篇
```

---

**Q：Playwright 发布时找不到页面元素怎么办？**

A：小红书页面结构可能随版本更新变化。请打开 `publisher/xiaohongshu_publisher.py`，根据实际页面的 HTML 结构更新 CSS 选择器。建议使用 `headless=False` 模式调试，通过浏览器开发者工具定位元素。

---

## License

MIT License
