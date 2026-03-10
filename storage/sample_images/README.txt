本地测试图片目录
====================

将任意装修风格的图片（PNG / JPG / JPEG / WEBP）放入此目录，
即可在 local / auto 模式下跳过 Stable Diffusion API。

使用方式
--------
1. 在 config/config.yaml 中设置：
     image:
       source: "local"

2. 将图片文件放入本目录（至少 1 张，推荐 4 张以上）

3. 启动服务，图片模块将随机抽取 4 张复制到 storage/images/

注意事项
--------
- 支持格式：.png  .jpg  .jpeg  .webp  .bmp
- 图片分辨率低于 1024px 时会自动等比放大
- 图片数量不足 4 张时允许重复抽样（会有 Warning 日志）
- 此目录内容不会被 git 追踪（.gitignore 中已排除 storage/）

三种模式对比
------------
  stable_diffusion  调用 SD WebUI API 实时生成（需 SD 服务运行）
  local             直接取本目录图片（无需 SD，适合测试其他环节）
  auto              优先 SD，SD 不可达时自动切换到本目录
