"""
内容校验模块

根据小红书内容规则对生成的文案进行合规性检查。
校验规则：
  - 标题长度 ≤ 20 字
  - 正文字符数 ≤ 500
  - 正文行数 ≤ 30 行
  - 正文不含空白行
  - 必须包含 3~5 个标签
  - 图片数量 = 4 张
"""

from dataclasses import dataclass, field
from typing import List, Optional

from loguru import logger


@dataclass
class ValidationResult:
    """校验结果数据结构"""
    is_valid: bool = True
    issues: List[str] = field(default_factory=list)  # 不合规问题列表

    def add_issue(self, msg: str) -> None:
        self.issues.append(msg)
        self.is_valid = False

    def issues_summary(self) -> str:
        """返回所有问题的摘要字符串"""
        return "；".join(self.issues)


class ContentValidator:
    """
    小红书内容合规校验器

    对文案内容进行全面检查，返回校验结果和具体问题列表，
    供 ContentGenerator 决定是否重新生成。
    """

    # 小红书规则常量
    TITLE_MAX_LEN: int = 20
    BODY_MAX_CHARS: int = 500
    BODY_MAX_LINES: int = 30
    IMAGES_REQUIRED: int = 4
    TAGS_MIN: int = 3
    TAGS_MAX: int = 5

    def validate_title(self, title: str) -> ValidationResult:
        """
        校验标题

        规则：
        - 不为空
        - 长度 ≤ 20 字
        """
        result = ValidationResult()

        if not title or not title.strip():
            result.add_issue("标题不能为空")
            return result

        title = title.strip()
        if len(title) > self.TITLE_MAX_LEN:
            result.add_issue(
                f"标题过长：当前 {len(title)} 字，限制 {self.TITLE_MAX_LEN} 字"
            )

        return result

    def validate_body(self, body: str) -> ValidationResult:
        """
        校验正文

        规则：
        - 不为空
        - 字符数 ≤ 500
        - 行数 ≤ 30
        - 不含空白行（连续换行或只有空格的行）
        """
        result = ValidationResult()

        if not body or not body.strip():
            result.add_issue("正文不能为空")
            return result

        body = body.strip()

        # 检查字符数（去除标签行后统计）
        char_count = len(body)
        if char_count > self.BODY_MAX_CHARS:
            result.add_issue(
                f"正文过长：当前 {char_count} 字，限制 {self.BODY_MAX_CHARS} 字"
            )

        # 检查行数
        lines = body.split("\n")
        non_empty_lines = [l for l in lines if l.strip()]
        if len(non_empty_lines) > self.BODY_MAX_LINES:
            result.add_issue(
                f"正文行数超限：当前 {len(non_empty_lines)} 行，限制 {self.BODY_MAX_LINES} 行"
            )

        # 检查空白行（只包含空格或换行的行）
        for i, line in enumerate(lines, 1):
            if line != "" and not line.strip():
                result.add_issue(f"第 {i} 行是空白行（只含空格），请删除")
                break  # 只报第一个，避免信息过多

        # 检查连续空行
        for i in range(len(lines) - 1):
            if lines[i].strip() == "" and lines[i + 1].strip() == "":
                result.add_issue(f"正文第 {i+1}~{i+2} 行存在连续空行")
                break

        return result

    def validate_tags(self, tags: List[str]) -> ValidationResult:
        """
        校验标签

        规则：
        - 数量在 3~5 个之间
        """
        result = ValidationResult()

        if not tags:
            result.add_issue(f"缺少标签，需要 {self.TAGS_MIN}~{self.TAGS_MAX} 个")
            return result

        if len(tags) < self.TAGS_MIN:
            result.add_issue(
                f"标签数量不足：当前 {len(tags)} 个，需要至少 {self.TAGS_MIN} 个"
            )
        elif len(tags) > self.TAGS_MAX:
            result.add_issue(
                f"标签数量过多：当前 {len(tags)} 个，最多 {self.TAGS_MAX} 个"
            )

        return result

    def validate_images(self, image_paths: List[str]) -> ValidationResult:
        """
        校验图片

        规则：
        - 数量必须为 4 张
        - 图片文件存在
        """
        import os
        result = ValidationResult()

        if len(image_paths) != self.IMAGES_REQUIRED:
            result.add_issue(
                f"图片数量错误：当前 {len(image_paths)} 张，需要 {self.IMAGES_REQUIRED} 张"
            )

        # 检查文件是否存在
        for path in image_paths:
            if not os.path.exists(path):
                result.add_issue(f"图片文件不存在: {path}")

        return result

    def validate_all(
        self,
        title: str,
        body: str,
        tags: List[str],
        image_paths: Optional[List[str]] = None,
    ) -> ValidationResult:
        """
        全量校验：标题 + 正文 + 标签 + 图片

        Args:
            title      : 帖子标题
            body       : 帖子正文
            tags       : 标签列表
            image_paths: 图片路径列表（可选）

        Returns:
            ValidationResult 对象
        """
        final_result = ValidationResult()

        # 逐项校验，收集所有问题
        for check_result in [
            self.validate_title(title),
            self.validate_body(body),
            self.validate_tags(tags),
        ]:
            final_result.issues.extend(check_result.issues)
            if not check_result.is_valid:
                final_result.is_valid = False

        # 图片校验（可选）
        if image_paths is not None:
            img_result = self.validate_images(image_paths)
            final_result.issues.extend(img_result.issues)
            if not img_result.is_valid:
                final_result.is_valid = False

        if final_result.is_valid:
            logger.debug(f"内容校验通过: 标题='{title}'")
        else:
            logger.warning(f"内容校验失败: {final_result.issues_summary()}")

        return final_result

    def auto_fix(self, title: str, body: str) -> tuple[str, str]:
        """
        自动修复明显问题（避免不必要的重新生成）

        修复策略：
        - 标题过长 → 截断到 20 字
        - 正文去除空白行
        - 正文过长 → 截断到 500 字

        Returns:
            (fixed_title, fixed_body)
        """
        # 修复标题
        fixed_title = title.strip()[:self.TITLE_MAX_LEN]

        # 修复正文：去除空白行
        lines = body.strip().split("\n")
        non_empty_lines = [l for l in lines if l.strip()]
        fixed_body = "\n".join(non_empty_lines)

        # 修复正文长度
        if len(fixed_body) > self.BODY_MAX_CHARS:
            fixed_body = fixed_body[:self.BODY_MAX_CHARS]
            # 尽量在句号/换行处截断
            for punct in ["。", "\n", "，"]:
                last_pos = fixed_body.rfind(punct)
                if last_pos > self.BODY_MAX_CHARS * 0.8:
                    fixed_body = fixed_body[:last_pos + 1]
                    break

        return fixed_title, fixed_body
