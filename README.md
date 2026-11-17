# Rivet-H — Hashing and authentication RTL

[English](README.md) · [简体中文](README.zh-CN.md) · [Repository guide / 文件导航](REPOSITORY_GUIDE.md)

Documentation updated: 2026-11-17. This page describes a repository snapshot, not a live job dashboard.

## Overview

**Rivet-H** publishes chip RTL, technical reports and verification artifacts. SHA-2, HMAC, multichannel authentication and later SHA-3/post-quantum-oriented datapath research. Standard names do not imply external certification.

The chip project is public; Vulcan itself remains private and closed-source. Future public releases must be limited to chip technology and public reproducibility materials, excluding Vulcan internal architecture and operating materials. This refresh organizes documentation only; it is not a comprehensive disclosure audit of historical material and does not claim that the existing repository tree has undergone such clearance.

## Scope and evidence

Use the [exact-directory result index](REPOSITORY_GUIDE.md). Functional simulation, synthesis, standalone/virtual-pin timing, board-bridge probing, workload readback and system-software execution are different evidence scopes. A pass at one scope does not establish another. Existing historical results are retained; this documentation refresh neither upgrades nor invalidates them.

Read timing, utilization and performance values from their specific records and applicability conditions; results from differently located copies are not merged. This page makes no fleet-wide claim of physical-board completion, full-model inference, physical Linux boot or measured power/energy efficiency.

## Repository guide

The [repository guide](REPOSITORY_GUIDE.md) lists existing source, constraints, tests, reports and result paths. Hyphenated, underscored and `chips/` directories can be different publication copies; none is silently designated authoritative, moved or deleted.

Start reproduction from the selected chip’s public specification, test instructions and scripts. Tool, input and board requirements belong to that directory. Chip experiments were not rerun as part of this documentation update.

## Existing chip directories

| Chip / variant | Existing root paths | Public artifacts |
| --- | --- | --- |
| RIVET-H1 | [`rivet-h1/`](rivet-h1/) | [REPORT.md](rivet-h1/REPORT.md) · [REPORT.pdf](rivet-h1/REPORT.pdf) · [SHOWCASE_REPORT.pdf](rivet-h1/SHOWCASE_REPORT.pdf) · [SHOWCASE_REPORT.zh-CN.pdf](rivet-h1/SHOWCASE_REPORT.zh-CN.pdf) |
| RIVET-H2 | [`rivet-h2/`](rivet-h2/) | [REPORT.md](rivet-h2/REPORT.md) · [REPORT.pdf](rivet-h2/REPORT.pdf) · [SHOWCASE_REPORT.pdf](rivet-h2/SHOWCASE_REPORT.pdf) · [SHOWCASE_REPORT.zh-CN.pdf](rivet-h2/SHOWCASE_REPORT.zh-CN.pdf) |
| RIVET-H3 | [`rivet-h3/`](rivet-h3/) | [REPORT.md](rivet-h3/REPORT.md) · [REPORT.pdf](rivet-h3/REPORT.pdf) · [SHOWCASE_REPORT.pdf](rivet-h3/SHOWCASE_REPORT.pdf) · [SHOWCASE_REPORT.zh-CN.pdf](rivet-h3/SHOWCASE_REPORT.zh-CN.pdf) |
| RIVET-H4 | [`rivet-h4/`](rivet-h4/) · [`rivet_h4/`](rivet_h4/) | [REPORT.md](rivet-h4/REPORT.md) · [REPORT.pdf](rivet-h4/REPORT.pdf) · [SHOWCASE_REPORT.pdf](rivet-h4/SHOWCASE_REPORT.pdf) · [SHOWCASE_REPORT.zh-CN.pdf](rivet-h4/SHOWCASE_REPORT.zh-CN.pdf) |
| RIVET-H5 | [`rivet-h5/`](rivet-h5/) · [`rivet_h5/`](rivet_h5/) | [REPORT.md](rivet-h5/REPORT.md) · [REPORT.pdf](rivet-h5/REPORT.pdf) · [SHOWCASE_REPORT.pdf](rivet-h5/SHOWCASE_REPORT.pdf) · [SHOWCASE_REPORT.zh-CN.pdf](rivet-h5/SHOWCASE_REPORT.zh-CN.pdf) |

## Architecture catalog and publications

| Generation | Chip | Architecture / research scope | Record navigation | Reports |
| --- | --- | --- | --- | --- |
| **Gen-1** | [**RIVET-H1**](rivet-h1/) | FIPS 180-4 Streaming SHA-256 · Full Message-Length Accounting & Automatic 1/2-Block Padding | [Exact-directory records](REPOSITORY_GUIDE.md) | [**Whitepaper PDF**](rivet-h1/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-h1/REPORT.pdf) |
| **Gen-2** | [**RIVET-H2**](rivet-h2/) | RFC 2104 / 4231 HMAC-SHA-256 · Long-Key Normalization & Mid-Stream Context Save/Restore | [Exact-directory records](REPOSITORY_GUIDE.md) | [**Whitepaper PDF**](rivet-h2/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-h2/REPORT.pdf) |
| **Gen-3** | [**RIVET-H3**](rivet-h3/) | 4-Channel Tagged SHA-256 / SHA-512 (80-Round 64-Bit) & HMAC Multi-Context Authenticator | [Exact-directory records](REPOSITORY_GUIDE.md) | [**Whitepaper PDF**](rivet-h3/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-h3/REPORT.pdf) |

## Academic Product Whitepaper Visual Gallery

### RIVET-H1 · Academic Whitepaper Preview ([`rivet-h1/SHOWCASE_REPORT.pdf`](rivet-h1/SHOWCASE_REPORT.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="rivet-h1/SHOWCASE_REPORT.pdf"><img src="rivet-h1/showcase_figures/page-1.png" width="100%" alt="RIVET-H1 Page 1"></a><br><sub><strong>Page 1 · Architecture & KPI Summary</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-h1/SHOWCASE_REPORT.pdf"><img src="rivet-h1/showcase_figures/page-2.png" width="100%" alt="RIVET-H1 Page 2"></a><br><sub><strong>Page 2 · Experimental Benchmarks & Parity</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-h1/SHOWCASE_REPORT.pdf"><img src="rivet-h1/showcase_figures/page-3.png" width="100%" alt="RIVET-H1 Page 3"></a><br><sub><strong>Page 3 · Arria 10 STA, HIL & Scaling</strong></sub></td>
  </tr>
</table>

### RIVET-H2 · Academic Whitepaper Preview ([`rivet-h2/SHOWCASE_REPORT.pdf`](rivet-h2/SHOWCASE_REPORT.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="rivet-h2/SHOWCASE_REPORT.pdf"><img src="rivet-h2/showcase_figures/page-1.png" width="100%" alt="RIVET-H2 Page 1"></a><br><sub><strong>Page 1 · Architecture & KPI Summary</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-h2/SHOWCASE_REPORT.pdf"><img src="rivet-h2/showcase_figures/page-2.png" width="100%" alt="RIVET-H2 Page 2"></a><br><sub><strong>Page 2 · Experimental Benchmarks & Parity</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-h2/SHOWCASE_REPORT.pdf"><img src="rivet-h2/showcase_figures/page-3.png" width="100%" alt="RIVET-H2 Page 3"></a><br><sub><strong>Page 3 · Arria 10 STA, HIL & Scaling</strong></sub></td>
  </tr>
</table>

### RIVET-H3 · Academic Whitepaper Preview ([`rivet-h3/SHOWCASE_REPORT.pdf`](rivet-h3/SHOWCASE_REPORT.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="rivet-h3/SHOWCASE_REPORT.pdf"><img src="rivet-h3/showcase_figures/page-1.png" width="100%" alt="RIVET-H3 Page 1"></a><br><sub><strong>Page 1 · Architecture & KPI Summary</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-h3/SHOWCASE_REPORT.pdf"><img src="rivet-h3/showcase_figures/page-2.png" width="100%" alt="RIVET-H3 Page 2"></a><br><sub><strong>Page 2 · Experimental Benchmarks & Parity</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-h3/SHOWCASE_REPORT.pdf"><img src="rivet-h3/showcase_figures/page-3.png" width="100%" alt="RIVET-H3 Page 3"></a><br><sub><strong>Page 3 · Arria 10 STA, HIL & Scaling</strong></sub></td>
  </tr>
</table>

## Related projects

- AI / embeddings: [Anvil-Q](https://github.com/aHappend/anvil-q), [Anvil-E](https://github.com/aHappend/anvil-e), [Anvil-QN](https://github.com/aHappend/anvil-qn), [Anvil-EN](https://github.com/aHappend/anvil-en), [Anvil-D](https://github.com/aHappend/anvil-d).
- Systems: [Hammer-V](https://github.com/aHappend/hammer-v), [Furnace-X](https://github.com/aHappend/furnace-x).
- DSP / vision: [Billet-F](https://github.com/aHappend/billet-f), [Billet-T](https://github.com/aHappend/billet-t), [Swage-S](https://github.com/aHappend/swage-s).
- Data / security / graphics: [Bellows-L](https://github.com/aHappend/bellows-l), [Bellows-N](https://github.com/aHappend/bellows-n), [Rivet-A](https://github.com/aHappend/rivet-a), [Rivet-H](https://github.com/aHappend/rivet-h), [Crucible-G](https://github.com/aHappend/crucible-g), [SABLE](https://github.com/aHappend/sable).
- [Public fleet catalog](https://github.com/aHappend/vulcan-showcase). Related independent research: [ACE-2](https://github.com/aHappend/ace-2), [ACE-3](https://github.com/aHappend/ace-3); these retain their own provenance and acceptance boundaries.
- DSpark is a research direction, not a published chip delivery in this repository; no implementation or repository link is asserted here.
