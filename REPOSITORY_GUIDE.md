# Rivet-H — Repository guide / 文件导航

[English](README.md) · [简体中文](README.zh-CN.md)

Documentation inventory checked on 2026-11-17, against repository base `265842063620628cdae7e577591462fe98532ecd`.

## Reading the inventory / 阅读方法

This is a path-level index, not a new experiment or a recertification. Each measurement belongs to the exact linked record and directory. Different copies of a chip can contain different source revisions and results. A recorded pass does not imply that another copy, model size, software stack or board image passed.

本页按实际路径列出交付物，不代表新实验或重新签核。同名芯片的多份目录可能有不同源码和结果；一份记录的通过不外推到其他副本、模型规模、软件栈或板卡镜像。

## Source, tests and reports / 源码、测试与报告

| Existing directory | Source / constraints | Public tests / technical documents | Reports |
| --- | --- | --- | --- |
| [`chips/rivet_h4/`](chips/rivet_h4/) | [`chips/rivet_h4/rtl/`](chips/rivet_h4/rtl/) | [`chips/rivet_h4/tests/`](chips/rivet_h4/tests/) · [`chips/rivet_h4/design/`](chips/rivet_h4/design/) | [`chips/rivet_h4/REPORT.md`](chips/rivet_h4/REPORT.md) · [`chips/rivet_h4/REPORT.pdf`](chips/rivet_h4/REPORT.pdf) · [`chips/rivet_h4/SHOWCASE_REPORT.pdf`](chips/rivet_h4/SHOWCASE_REPORT.pdf) · [`chips/rivet_h4/SHOWCASE_REPORT.zh-CN.pdf`](chips/rivet_h4/SHOWCASE_REPORT.zh-CN.pdf) |
| [`chips/rivet_h5/`](chips/rivet_h5/) | [`chips/rivet_h5/rtl/`](chips/rivet_h5/rtl/) | [`chips/rivet_h5/tests/`](chips/rivet_h5/tests/) · [`chips/rivet_h5/design/`](chips/rivet_h5/design/) | [`chips/rivet_h5/REPORT.md`](chips/rivet_h5/REPORT.md) · [`chips/rivet_h5/REPORT.pdf`](chips/rivet_h5/REPORT.pdf) · [`chips/rivet_h5/SHOWCASE_REPORT.pdf`](chips/rivet_h5/SHOWCASE_REPORT.pdf) · [`chips/rivet_h5/SHOWCASE_REPORT.zh-CN.pdf`](chips/rivet_h5/SHOWCASE_REPORT.zh-CN.pdf) |
| [`rivet-h1/`](rivet-h1/) | [`rivet-h1/rtl/`](rivet-h1/rtl/) | [`rivet-h1/tests/`](rivet-h1/tests/) · [`rivet-h1/design/`](rivet-h1/design/) · [`rivet-h1/README.md`](rivet-h1/README.md) | [`rivet-h1/REPORT.md`](rivet-h1/REPORT.md) · [`rivet-h1/REPORT.pdf`](rivet-h1/REPORT.pdf) · [`rivet-h1/SHOWCASE_REPORT.pdf`](rivet-h1/SHOWCASE_REPORT.pdf) · [`rivet-h1/SHOWCASE_REPORT.zh-CN.pdf`](rivet-h1/SHOWCASE_REPORT.zh-CN.pdf) |
| [`rivet-h2/`](rivet-h2/) | [`rivet-h2/rtl/`](rivet-h2/rtl/) | [`rivet-h2/tests/`](rivet-h2/tests/) · [`rivet-h2/design/`](rivet-h2/design/) · [`rivet-h2/README.md`](rivet-h2/README.md) | [`rivet-h2/REPORT.md`](rivet-h2/REPORT.md) · [`rivet-h2/REPORT.pdf`](rivet-h2/REPORT.pdf) · [`rivet-h2/SHOWCASE_REPORT.pdf`](rivet-h2/SHOWCASE_REPORT.pdf) · [`rivet-h2/SHOWCASE_REPORT.zh-CN.pdf`](rivet-h2/SHOWCASE_REPORT.zh-CN.pdf) |
| [`rivet-h3/`](rivet-h3/) | [`rivet-h3/rtl/`](rivet-h3/rtl/) | [`rivet-h3/tests/`](rivet-h3/tests/) · [`rivet-h3/design/`](rivet-h3/design/) · [`rivet-h3/README.md`](rivet-h3/README.md) | [`rivet-h3/REPORT.md`](rivet-h3/REPORT.md) · [`rivet-h3/REPORT.pdf`](rivet-h3/REPORT.pdf) · [`rivet-h3/SHOWCASE_REPORT.pdf`](rivet-h3/SHOWCASE_REPORT.pdf) · [`rivet-h3/SHOWCASE_REPORT.zh-CN.pdf`](rivet-h3/SHOWCASE_REPORT.zh-CN.pdf) |
| [`rivet-h4/`](rivet-h4/) | [`rivet-h4/rtl/`](rivet-h4/rtl/) | [`rivet-h4/tests/`](rivet-h4/tests/) · [`rivet-h4/design/`](rivet-h4/design/) | [`rivet-h4/REPORT.md`](rivet-h4/REPORT.md) · [`rivet-h4/REPORT.pdf`](rivet-h4/REPORT.pdf) · [`rivet-h4/SHOWCASE_REPORT.pdf`](rivet-h4/SHOWCASE_REPORT.pdf) · [`rivet-h4/SHOWCASE_REPORT.zh-CN.pdf`](rivet-h4/SHOWCASE_REPORT.zh-CN.pdf) |
| [`rivet-h5/`](rivet-h5/) | [`rivet-h5/rtl/`](rivet-h5/rtl/) | [`rivet-h5/tests/`](rivet-h5/tests/) · [`rivet-h5/design/`](rivet-h5/design/) | [`rivet-h5/REPORT.md`](rivet-h5/REPORT.md) · [`rivet-h5/REPORT.pdf`](rivet-h5/REPORT.pdf) · [`rivet-h5/SHOWCASE_REPORT.pdf`](rivet-h5/SHOWCASE_REPORT.pdf) · [`rivet-h5/SHOWCASE_REPORT.zh-CN.pdf`](rivet-h5/SHOWCASE_REPORT.zh-CN.pdf) |
| [`rivet_h4/`](rivet_h4/) | [`rivet_h4/rtl/`](rivet_h4/rtl/) | [`rivet_h4/tests/`](rivet_h4/tests/) · [`rivet_h4/design/`](rivet_h4/design/) | [`rivet_h4/REPORT.md`](rivet_h4/REPORT.md) · [`rivet_h4/REPORT.pdf`](rivet_h4/REPORT.pdf) · [`rivet_h4/SHOWCASE_REPORT.pdf`](rivet_h4/SHOWCASE_REPORT.pdf) · [`rivet_h4/SHOWCASE_REPORT.zh-CN.pdf`](rivet_h4/SHOWCASE_REPORT.zh-CN.pdf) |
| [`rivet_h5/`](rivet_h5/) | [`rivet_h5/rtl/`](rivet_h5/rtl/) | [`rivet_h5/tests/`](rivet_h5/tests/) · [`rivet_h5/design/`](rivet_h5/design/) | [`rivet_h5/REPORT.md`](rivet_h5/REPORT.md) · [`rivet_h5/REPORT.pdf`](rivet_h5/REPORT.pdf) · [`rivet_h5/SHOWCASE_REPORT.pdf`](rivet_h5/SHOWCASE_REPORT.pdf) · [`rivet_h5/SHOWCASE_REPORT.zh-CN.pdf`](rivet_h5/SHOWCASE_REPORT.zh-CN.pdf) |

## Public result records / 公开结果记录

Status and numbers below are transcribed only from the linked record. Functional simulation, generic synthesis, standalone/virtual-pin timing, bridge connectivity, workload readback and system-software execution are separate scopes. Missing entries mean that this index found no matching public record at that path, not that an experiment failed or never occurred.

下表状态与数值只来自对应文件。功能仿真、通用综合、独立 IP／虚拟引脚时序、桥接连通性、工作负载读回和系统软件执行分别解释；未列出不等于判定失败或从未做过。

| Exact directory | Record | Recorded result and scope |
| --- | --- | --- |
| `chips/rivet_h4` | — | Use the public technical reports and tests above; no matching standalone record indexed here. |
| `chips/rivet_h5` | — | Use the public technical reports and tests above; no matching standalone record indexed here. |
| `rivet-h1` | [`rivet-h1/STATUS.json`](rivet-h1/STATUS.json) | recorded engineering acceptance: `true` |
| `rivet-h2` | [`rivet-h2/STATUS.json`](rivet-h2/STATUS.json) | recorded engineering acceptance: `true` |
| `rivet-h3` | [`rivet-h3/STATUS.json`](rivet-h3/STATUS.json) | recorded engineering acceptance: `true` |
| `rivet-h4` | — | Use the public technical reports and tests above; no matching standalone record indexed here. |
| `rivet-h5` | — | Use the public technical reports and tests above; no matching standalone record indexed here. |
| `rivet_h4` | — | Use the public technical reports and tests above; no matching standalone record indexed here. |
| `rivet_h5` | — | Use the public technical reports and tests above; no matching standalone record indexed here. |

## File-management policy / 文件管理约定

- Keep RTL, constraints, tests and result originals in their existing locations. This documentation refresh does not move or delete them.
- Hyphenated, underscored and `chips/` directories are separate existing trees, not interchangeable aliases. The index lists all of them without declaring one authoritative.
- Preserve dated reports as publications. Update the README and this guide when the public source/evidence changes; do not silently rewrite an old result.
- Keep chip artifacts separate from the private Vulcan implementation. Public reproducibility instructions must not require private framework code or internal operation traces.

保留现有源码、约束、测试和原始证据路径；连字符、下划线和 `chips/` 多份目录不自动视为等价。历史报告保留其发表时范围，公开复现不得依赖私有框架实现。
