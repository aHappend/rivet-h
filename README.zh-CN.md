<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="brand/logo-dark.svg"><img src="brand/logo.svg" width="480" alt="Vulcan"></picture></p>

<h1 align="center">RIVET-H · Hash and message-authentication silicon, forged with Vulcan.</h1>

[Vulcan](https://ahappend.github.io/vulcan/) · [Showcase](https://github.com/aHappend/vulcan-showcase) · [Anvil-E](https://github.com/aHappend/anvil-e) · [RIVET-A](https://github.com/aHappend/rivet-a) · [BILLET-T](https://github.com/aHappend/billet-t)

[English](README.md)

**密码计算芯片家族 · 哈希与消息认证产品线**。RIVET 是独立家族，RIVET-H 是其中的产品线，不隶属于 Anvil。

## 代际路线与实际状态

| Generation | Design | Scope | Engineering status | Product report |
|---|---|---|---|---|
| 1 | [RIVET-H1](rivet-h1/) | SHA-256 streaming hash, message length, padding and digest output | Engineering accepted | [PDF](rivet-h1/REPORT.pdf) |
| 2 | [RIVET-H2](rivet-h2/) | HMAC-SHA-256 and context save/restore | Engineering accepted | [PDF](rivet-h2/REPORT.pdf) |
| 3 | [RIVET-H3](rivet-h3/) | SHA-512 and multichannel hash/message authentication | Not accepted (interrupted) | Pending |

`Engineering accepted` 表示原生工程验收已通过；`Not accepted` 表示尚未验收；`Pending` 表示报告尚未发布。规划不算成果，后续代际不覆盖前代目录。

验收后发布规格、RTL、可执行验证程序；报告在实际渲染产物获批后追加。各代目录含复现命令和精简检查状态，不发布账号、模型对话、私有经验、框架状态或内部原始日志。已验收的产品 README 按原字节保留；存在原 README 时，生成的发布说明和复现命令另存于该代的 `DELIVERY.md`。报告中的内部相对证据路径仅作溯源，相关内部文件不随公开包提供；用户可运行验证程序生成自己的证据。

当前结果不等于流片、实测 PPA、侧信道认证或板级实时性能。发布流程见 [PUBLISHING.md](PUBLISHING.md)。

## 许可证

[MIT](LICENSE)，与 Anvil 成果仓库一致。
