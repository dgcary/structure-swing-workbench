# 家中手机与电脑共用工作台（待实机验收）

工作台是运行在一台常开设备上的网页程序。推荐先用 Ubuntu 台式机；若 NAS 能运行 Docker Compose，同一套配置也可迁移过去。手机和电脑在家中同一网络访问 `https://<设备的固定内网 IP>`，共同读写服务器里的手工台账。当前仅提供配置与代码，**尚未在用户设备上部署或通过手机 Safari 验收**。

## 首次准备

1. 在运行设备上安装 Docker Engine 与 Docker Compose 插件，并给该设备设定固定的家庭内网 IPv4 地址（或在路由器中保留地址）。不要配置路由器端口转发。
2. 在仓库根目录将 `.env.home.example` 复制为 `.env.home`。填写固定内网 IP，并分别生成数据库密码和手工台账口令，例如各用一次 `openssl rand -hex 32`。不要复用两个值，不要将 `.env.home` 传到 GitHub。
3. 选择一个单独的网页登录密码。运行 `docker run --rm -it caddy:2-alpine caddy hash-password`，在提示下输入密码，将输出的完整 bcrypt 哈希填入 `.env.home` 的 `HOME_PASSWORD_HASH`，保留外层单引号和内部所有 `$`。网页登录用户名固定为 `owner`。不要把明文密码填入配置文件。
4. 运行 `docker compose --env-file .env.home -f docker-compose.home.yml config`，核对只发布固定内网 IP 的 443 端口，且数据库、后端没有 `ports`。该命令可能显示配置中的密码和口令，不要分享其输出。
5. 运行 `docker compose --env-file .env.home -f docker-compose.home.yml up -d --build`。第一次会建立 PostgreSQL 数据卷、执行数据库迁移，再启动后端与加密网页入口。用 `docker compose --env-file .env.home -f docker-compose.home.yml ps` 核对状态。

这套家庭配置与现有 `docker-compose.yml` 开发配置独立。网页入口使用全站登录、内部 CA 颁发的 HTTPS 证书，只有 443 端口绑定到指定家庭内网 IP；后端和数据库不发布宿主机端口。正式账户读取、正式动作日期写入及本机 PDF 检查保持关闭。手工台账需要网页登录后再输入独立台账口令；后者仅保留在当前网页内存。

## 让手机信任家庭证书

启动后，在运行设备上导出 Caddy 的**公用根证书**：

```sh
docker compose --env-file .env.home -f docker-compose.home.yml cp web:/data/caddy/pki/authorities/local/root.crt ./structure-swing-home-root.crt
```

只在自己设备之间传送该 `root.crt`，核对它来自本次运行的 Caddy 数据卷。将证书安装到 iPhone 后，在“设置 → 通用 → 关于本机 → 证书信任设置”中为其开启完全信任。随后使用 Safari 打开与证书一致的 `https://<固定内网 IP>`；不要点过证书错误继续。电脑也需要信任同一根证书。**信任根证书会信任这台 Caddy 所签发的证书**，因此不要向他人散发根证书，更不能导出或分享 `/data/caddy/pki/authorities/local/root.key`。更换家庭 IP、重建 Caddy 数据卷或重装手机后，须重新核对证书。

## 首次录入与日常使用

- 第一次先从东吴秀财核对当前资金与每批持仓，录入证券代码、数量、可知的买入时间和投入金额。未知项留空。保存后，手机和电脑会读取同一份版本记录。
- 此后在“录入买卖”填写方向、证券、成交时间、数量、价格；买入自动新增一批，卖出填写每批扣减量并自动减量，一笔可跨多批。费用、操作后可用资金和权益可手工填写；未知时留空，不推算成券商事实。若事后补录多笔，请按成交时间从早到晚录完再核对最终仓位。
- 两台设备同时修改同一版本时，后提交者收到冲突提示。先核对最新版本，再重新填写。每次操作后展开最近记录确认数量。

## 维护与边界

- PostgreSQL 数据卷保存手工记录，Caddy 数据卷保存家庭证书。升级前分别备份这两份数据和 `.env.home`，并保管网页密码与台账口令；不要使用 `docker compose down -v` 删除卷。
- 仅家中同网使用；运行设备关机、休眠或离开网络时，手机无法连接。要改用 NAS，先在 Ubuntu 上验证，再迁移数据库与证书数据。
- 此部署不会连接东吴证券，也不会实时获取持仓、股价或可卖数量。手工记录不进入正式审计与交易许可。M8 总体验收仍不通过。

配置依据：[Docker Compose 启动顺序](https://docs.docker.com/compose/how-tos/startup-order/)、[Caddy 全站登录](https://caddyserver.com/docs/caddyfile/directives/basic_auth)、[Caddy 内部证书](https://caddyserver.com/docs/caddyfile/directives/tls)、[Apple 证书信任](https://support.apple.com/en-gb/102390)。
