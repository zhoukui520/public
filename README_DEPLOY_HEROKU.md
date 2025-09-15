部署到 Heroku - 快速指南

前提：已安装 git、Heroku CLI，已有 Heroku 账号。

1. 在项目根目录（包含 py/）初始化 git 仓库（如果已存在可跳过）

   git init
   git add .
   git commit -m "prepare heroku deployment"

2. 登录 Heroku CLI

   heroku login

3. 创建 Heroku app（或使用已有）

   heroku create your-app-name

4. 推送代码到 Heroku

   git push heroku main

   # 如果你的默认分支是 master
   git push heroku master

5. 打开应用

   heroku open

6. 日志查看

   heroku logs --tail

说明：
- 该目录下包含示例的 requirements.txt、Procfile、runtime.txt。确保这些文件位于仓库根或 Heroku 能识别的路径（Heroku 会从仓库根读取这些文件）。
- 若你希望把 deploy/heroku 下的文件移到根目录，可手动复制或在部署前把文件移动。
