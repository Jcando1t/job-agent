# 求职 Agent

一个逐步构建的个人求职工作台。第一阶段支持维护多个求职方向，并把数据保存在本地 SQLite 数据库。

## 本地运行

在 PyCharm 的项目终端中运行：

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

然后在浏览器打开 <http://127.0.0.1:8000>。按 `Ctrl+C` 停止服务。

求职方向数据写入项目的 `data/job_agent.db`，该目录已加入 `.gitignore`，不会提交到 Git。

## 当前功能

- 新增、查看、编辑、暂停、启用和删除多个求职方向
- 为每个方向填写岗位名称、搜索关键词和多个城市
- 北京、天津可直接选择，也可以填写其他城市
- 数据保存在本地，重新启动后仍然存在
