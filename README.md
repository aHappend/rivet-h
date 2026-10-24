<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/logo-dark.svg">
    <img src="brand/logo.svg" width="420" alt="Vulcan">
  </picture>
  <h1>Rivet-H · Cryptographic Hash & Message Authentication Silicon</h1>
  <p><strong>Synthesizable 100 MHz+ SHA-256, HMAC-SHA-256 Context Save/Restore & 4-Channel SHA-512 Accelerators · Intel Arria 10 GX HIL</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Platform-Intel_Arria_10_GX-0f766e?style=flat-square" alt="Platform">
    <img src="https://img.shields.io/badge/Quartus_17.1_STA-100_MHz%2B_Closed-0f766e?style=flat-square" alt="STA">
    <img src="https://img.shields.io/badge/PCIe_Gen3x8_HIL-100%25_Passed-1d4ed8?style=flat-square" alt="HIL">
    <img src="https://img.shields.io/badge/Author-Sufeng_Guo_(MSRA)-334155?style=flat-square" alt="Author">
    <img src="https://img.shields.io/badge/License-MIT-64748b?style=flat-square" alt="License">
  </p>
  <p>
    <a href="https://ahappend.github.io/vulcan/">Website</a> ·
    <a href="https://github.com/aHappend/vulcan-showcase">Vulcan Showcase</a> ·
    <a href="https://github.com/aHappend/anvil-q">Anvil-Q (LLM)</a> ·
    <a href="https://github.com/aHappend/anvil-e">Anvil-E (Embedding)</a> ·
    <a href="https://github.com/aHappend/billet-t">Billet-T (FFT/DSP)</a> ·
    <a href="https://github.com/aHappend/billet-f">Billet-F (FIR/IIR)</a> ·
    <a href="https://github.com/aHappend/rivet-a">Rivet-A (AES-GCM)</a> ·
    <a href="https://github.com/aHappend/rivet-h">Rivet-H (SHA/HMAC)</a> ·
    <a href="README.zh-CN.md"><strong>中文文档</strong></a>
  </p>
</div>

---

**Rivet-H** is the cryptographic hashing and message authentication series within Vulcan's **Rivet** silicon family, implementing FIPS 180-4 and RFC 2104/4231 hardware accelerators from streaming SHA-256 (`RIVET-H1`) to context-switchable HMAC-SHA-256 (`RIVET-H2`) and 4-channel SHA-256/SHA-512/HMAC (`RIVET-H3`).

## Silicon Signoff Matrix & Dual-Track Publications (`100 MHz+` Baseline)

| Gen | Accelerator | Architecture & Numerical Scope | Quartus 17.1 STA (`10.0 ns`) | Intel Arria 10 GX Utilization | PCIe Gen3x8 HIL | Academic & Developer Reports |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gen-1** | [**RIVET-H1**](rivet-h1/) | FIPS 180-4 Streaming SHA-256 · Full Message-Length Accounting & Automatic 1/2-Block Padding | `251.51 MHz` (`WNS +6.024 ns`) | `2,480 ALMs (0.58%) · 0 DSPs · 4 M20K` | **PASSED (3/3)** | [**Whitepaper PDF**](rivet-h1/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-h1/REPORT.pdf) |
| **Gen-2** | [**RIVET-H2**](rivet-h2/) | RFC 2104 / 4231 HMAC-SHA-256 · Long-Key Normalization & Mid-Stream Context Save/Restore | `251.51 MHz` (`WNS +6.024 ns`) | `4,320 ALMs (1.01%) · 0 DSPs · 12 M20K` | **PASSED (3/3)** | [**Whitepaper PDF**](rivet-h2/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-h2/REPORT.pdf) |
| **Gen-3** | [**RIVET-H3**](rivet-h3/) | 4-Channel Tagged SHA-256 / SHA-512 (80-Round 64-Bit) & HMAC Multi-Context Authenticator | `196.93 MHz` (`WNS +4.922 ns`) | `8,150 ALMs (1.91%) · 0 DSPs · 24 M20K` | **PASSED (3/3)** | [**Whitepaper PDF**](rivet-h3/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-h3/REPORT.pdf) |

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

## Vulcan Seven-Family Workshop Silicon Matrix

| Silicon Family | Workshop Metaphor | Domain & Series Repositories |
| :--- | :--- | :--- |
| **Anvil** *(Primary Focus)* | Heavy forge anvil bearing core compute loads | AI & Large-Model Compute — [**Anvil-Q** (Quantized LLMs)](https://github.com/aHappend/anvil-q) · [**Anvil-E** (Multimodal Embeddings)](https://github.com/aHappend/anvil-e) |
| **Billet** | Raw metal stock shaped and combined into systems | Digital Signal Processing — [**Billet-T** (FFT/Spectral)](https://github.com/aHappend/billet-t) · [**Billet-F** (FIR/SOS-IIR Filters)](https://github.com/aHappend/billet-f) |
| **Rivet** | Small, critical, rock-solid fasteners | Cryptography & Data Integrity — [**Rivet-A** (AES/GCM/DMA)](https://github.com/aHappend/rivet-a) · [**Rivet-H** (SHA-256/512/HMAC)](https://github.com/aHappend/rivet-h) |
| **Swage** | Die-forming tool shaping inputs into target forms | Image Processing & ISP — **Swage-S** (2D Scaler, 3×3 Spatial Filter, Bayer Demosaic, CSC) |
| **Bellows** | Expanding/contracting continuous airflow | Streaming Data Compression — **Bellows-L** (LZ4 Decompressor, Hash-Table Compressor, XXH32 DMA) |
| **Crucible** | Vessel fusing diverse materials into form | Graphics Processing & Rendering (Geometry, Texture & Lighting Fusion) |
| **Furnace** | Industrial furnace integrating multiple stages | Heterogeneous SoCs & Complete Multi-Engine Compute Subsystems |

---
<p align="center"><sub>Author: <strong>Sufeng Guo</strong> · Microsoft Research Asia · <a href="mailto:sufeng_guo@smail.nju.edu.cn">sufeng_guo@smail.nju.edu.cn</a> · <a href="LICENSE">MIT License</a></sub></p>
