# 部署｜Ubuntu + Docker

## 前置要求

- Ubuntu 22.04 / 24.04（其他支持 Docker 的 Linux 亦可）
- Docker Engine 27+ 与 Docker Compose v2
- 开放端口：`5173`（Web 工作台）、`8000`（后端 API，可仅内网）

```bash
# 安装 Docker（官方脚本）
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # 重新登录生效
docker compose version
```

## 1. 获取代码与配置

```bash
git clone <仓库地址> structure-swing-workbench
cd structure-swing-workbench
cp .env.example .env
```

编辑 `.env`，**必须修改数据库密码**：

```dotenv
APP_ENV=production
POSTGRES_DB=structure_swing
POSTGRES_USER=structure_swing
POSTGRES_PASSWORD=<强密码>
DATABASE_URL=postgresql+psycopg://structure_swing:<强密码>@postgres:5432/structure_swing
CORS_ORIGINS=http://<服务器IP或域名>:5173
```

> 永远不要提交真实 `.env`；备份时同步备份 `.env`。

## 2. 启动

```bash
docker compose up --build -d
docker compose ps          # 三个容器应为 running / healthy
docker compose logs -f backend
```

首次启动后执行数据库迁移：

```bash
docker compose exec backend alembic upgrade head
```

验证：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/health   # 经前端代理
```

浏览器访问 `http://<服务器IP>:5173` 进入工作台。

## 3. 行情依赖（可选）

AKShare 为后端可选依赖（`market` extra）。镜像默认不含它；需要行情/K 线时在
`backend/Dockerfile` 中加入：

```dockerfile
RUN pip install ".[market]"
```

或在后端容器内临时安装：`docker compose exec backend pip install akshare`。
未安装时 `/market/*` 返回 503 与中文原因，属预期行为，不是故障。

## 4. 数据备份与恢复

数据全部落在 `postgres_data` 卷。备份（建议 cron 每日执行）：

```bash
docker compose exec -T postgres pg_dump -U structure_swing structure_swing \
  | gzip > backup/structure_swing_$(date +%F).sql.gz
```

恢复：

```bash
gunzip -c backup/structure_swing_2026-11-15.sql.gz \
  | docker compose exec -T postgres psql -U structure_swing -d structure_swing
```

同步备份 `.env` 与备份文件到离线介质。恢复后执行
`alembic upgrade head` 确认版本一致。

## 5. 升级

```bash
git pull
docker compose up --build -d
docker compose exec backend alembic upgrade head
```

## 6. 常见问题

| 现象 | 处理 |
| --- | --- |
| backend 反复重启 | `docker compose logs backend`，多为 `DATABASE_URL` 与 `.env` 密码不一致 |
| 前端能开但接口 404 | 检查 `CORS_ORIGINS` 是否包含前端实际地址 |
| `/market/*` 返回 503 | 行情可选依赖未安装，见第 3 节 |
| 磁盘增长 | `docker system df`；定期 `docker image prune -f` |

## 7. 安全边界

- 系统不自动下单，也不对接实盘委托；泄露数据库只会暴露计划与记录。
- 不要将 `8000` 端口直接暴露公网；建议反向代理（Caddy/Nginx）+ HTTPS 后再对外。
- 单用户设计：第一版无登录鉴权，务必用防火墙/反向代理限制访问来源。
