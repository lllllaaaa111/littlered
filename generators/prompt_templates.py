"""
Prompt 模板模块

集中管理所有 LLM 和 Stable Diffusion 的 Prompt 模板。
统一维护，方便迭代优化。
"""

from string import Template


# ===================================================
# 文案生成 Prompt 模板
# ===================================================

CONTENT_SYSTEM_PROMPT = """你是一位专业的小红书装修博主，擅长用真实、温暖、治愈的语气分享装修经验。
你的内容风格：亲切自然，有个人情感，包含实用信息，能引发共鸣。
严格遵守以下规则：
1. 标题长度 ≤ 20字
2. 正文总字数 ≤ 500字
3. 正文总行数 ≤ 30行
4. 正文不能有空白行
5. 包含 3~5 个话题标签（格式：#标签名）
6. 语气真实自然，像真实装修博主分享
7. 内容中可以包含费用参考、选材建议、空间处理技巧等实用信息"""

CONTENT_USER_PROMPT_TEMPLATE = Template("""请根据以下装修主题，生成一篇小红书装修分享内容。

装修主题：$topic

参考风格案例（可选择性参考，不要直接复制）：
$reference_examples

请按以下格式输出，不要添加任何额外说明：

标题：
[在这里写标题，≤20字]

正文：
[在这里写正文，≤500字，≤30行，无空白行]

[#话题标签1#话题标签2#话题标签3]
""")

# 内容重新生成提示（当内容不符合规则时使用）
CONTENT_RETRY_PROMPT_TEMPLATE = Template("""上一次生成的内容存在以下问题：$issues

请重新生成，严格遵守规则：
- 标题 ≤ 20字
- 正文 ≤ 500字
- 正文 ≤ 30行
- 正文无空白行
- 包含 3-5 个 #话题标签

装修主题：$topic

请按格式输出：

标题：
[标题内容]

正文：
[正文内容]

[#标签1#标签2#标签3]
""")


# ===================================================
# 图片生成 Prompt 模板（Stable Diffusion）
# ===================================================

# 风格映射到 SD 正面 Prompt 前缀
STYLE_TO_SD_PREFIX: dict = {
    "原木风": "cozy wooden interior, natural oak wood texture, warm wood tones",
    "法式风": "french country interior, elegant cream white walls, ornate moldings, romantic",
    "新中式": "new chinese style interior, dark wood furniture, ink wash painting elements, zen",
    "北欧风": "scandinavian interior, minimalist, white walls, clean lines, natural light",
    "现代简约": "modern minimalist interior, neutral tones, clean geometry, functional design",
}

# 空间类型映射
SPACE_KEYWORDS: dict = {
    "客厅": "living room, comfortable sofa, coffee table",
    "卧室": "bedroom, cozy bed, soft bedding",
    "厨房": "kitchen, cooking area, cabinet",
    "餐厅": "dining room, dining table, chairs",
    "书房": "study room, bookshelf, desk, reading area",
    "玄关": "entryway, hallway, entrance",
    "卫生间": "bathroom, sink, clean tiles",
    "阳台": "balcony, outdoor space, plants",
}

# SD 正面 Prompt 通用后缀（质量提升词）
SD_POSITIVE_SUFFIX = (
    "professional interior photography, high quality, realistic, "
    "8k resolution, beautiful lighting, magazine style, photorealistic, "
    "shot on Canon EOS R5, wide angle lens"
)

# SD 负面 Prompt（过滤不良图片）
SD_NEGATIVE_PROMPT = (
    "ugly, blurry, low quality, distorted, deformed, "
    "extra objects, cluttered, messy, dark, gloomy, "
    "watermark, text, signature, frame, border"
)


def build_sd_prompt(style_name: str, topic: str, index: int = 0) -> tuple[str, str]:
    """
    构建 Stable Diffusion 图片生成 Prompt

    Args:
        style_name: 装修风格名称
        topic     : 生成主题（用于提取空间类型）
        index     : 图片序号（0~3），不同序号生成不同角度

    Returns:
        (positive_prompt, negative_prompt) 正负 Prompt 元组
    """
    # 获取风格前缀
    style_prefix = STYLE_TO_SD_PREFIX.get(style_name, "modern interior design")

    # 从主题中提取空间关键词
    space_keyword = ""
    for space, kw in SPACE_KEYWORDS.items():
        if space in topic:
            space_keyword = kw
            break
    if not space_keyword:
        space_keyword = "interior space, home design"

    # 不同角度的描述（4张图用不同构图）
    angle_descriptions = [
        "wide angle shot, showing entire room layout",
        "close-up detail shot, focusing on key decorative elements",
        "natural daylight, window view, bright and airy",
        "evening mood lighting, warm ambient light, cozy atmosphere",
    ]
    angle = angle_descriptions[index % 4]

    positive_prompt = f"{style_prefix}, {space_keyword}, {angle}, {SD_POSITIVE_SUFFIX}"
    return positive_prompt, SD_NEGATIVE_PROMPT
