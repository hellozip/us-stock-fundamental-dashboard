# 美股基本面研究驾驶舱

这是一个前后端一体的交互式研究网页，把本地 `D:\美股基本面分析` 中的 Word、PDF、视频、图片、CSV 和 Excel 资料整理成可筛选、可搜索、可画图的研究终端。

## 当前内容

- 覆盖 47 个资料文件，约 630MB。
- 覆盖 6 个主题：AI Agent、AI PC、网络安全、商业航空、机器人、交易记录。
- 自动抽取 Word 中的段落摘要、财务表格、关键指标、风险提示，并生成中文评分。
- 前端包含主题地图、公司深研、动态图表、资料库、PDF/Word/视频入口。
- 后端提供 `/api/catalog` 和 `/api/rebuild`，点击网页右上角“更新”即可重新扫描资料源。

## 本地运行

```powershell
cd C:\Users\14446\Documents\美股分析\fundamental_dashboard_fullstack
C:\Users\14446\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe app.py
```

打开：

```text
http://127.0.0.1:8088
```

## 更新资料

把新的 Word/PDF/视频/图片/CSV/Excel 放进 `D:\美股基本面分析`，然后在网页点击“更新”，或者命令行运行：

```powershell
C:\Users\14446\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\build_data.py --source D:\美股基本面分析
```

## 部署说明

GitHub Pages 可以直接展示静态页面、已生成的数据和已复制的资料资产，但不能运行后端更新接口。  
Render、Railway、Fly.io 等 Python Web 服务可以运行后端 API；但如果公网服务器没有访问原始资料目录，更新按钮只能返回错误，不会凭空读到你电脑上的 `D:\美股基本面分析`。

公网持续更新的推荐流程：

1. 本地把新资料放入 `D:\美股基本面分析`。
2. 本地运行 `tools\build_data.py` 或点击本地网页“更新”。
3. 把更新后的 `static/data/catalog.json` 和 `static/assets` 提交到 GitHub。
4. Render 或 GitHub Pages 自动展示新内容。

本仓库为了绕开 GitHub 普通文件 API 对大视频的限制，MP4 文件发布在 GitHub Release `media-v1`，`catalog.json` 中的视频链接会指向 Release 下载地址。PDF、Word、图片、表格和网页代码保留在仓库内。

Render 配置文件已包含在 `render.yaml` 中。
