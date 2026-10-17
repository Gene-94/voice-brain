# Device Specs

## Machine
**Apple MacBook Pro 16" (2019) — T2 Linux**

Running Omarchy (Arch-based) with a custom T2 kernel patch.

---

## Operating System

| Property | Value |
|----------|-------|
| **Distro** | Omarchy 4.0.4 |
| **Base** | Arch Linux |
| **Kernel** | `7.2.7-arch1-Watanare-T2-2-t2` |
| **Architecture** | x86_64 |

---

## CPU

| Property | Value |
|----------|-------|
| **Model** | Intel Core i7-9750H |
| **Cores / Threads** | 6 / 12 |
| **Base Clock** | 2.60 GHz |
| **Max Turbo** | 4.50 GHz |
| **L3 Cache** | 12 MB |
| **Virtualization** | VT-x (enabled) |

---

## Memory

| Property | Value |
|----------|-------|
| **Total RAM** | 32 GB |
| **Used** | ~7.9 GB |
| **Available** | ~23 GB |
| **Swap** | 62 GB |

---

## Graphics

| Property | Value |
|----------|-------|
| **iGPU** | Intel UHD Graphics 630 |
| **dGPU** | AMD Radeon Pro 5500M (Navi 14) |
| **NVIDIA** | Not available / no driver loaded |

> **Note:** The AMD dGPU is a Navi 14 chip (4GB VRAM on the base config, 8GB on the higher-end config). ROCm support for this GPU is limited — most local LLM inference will run on CPU or Intel iGPU via OpenCL/oneAPI.

---

## Storage

| Property | Value |
|----------|-------|
| **Total** | ~464 GB |
| **Used** | ~97 GB (21%) |
| **Free** | ~367 GB |

---

## Battery

| Property | Value |
|----------|-------|
| **Charge** | 23% |
| **Status** | Charging |

---

## Implications for Local LLM Inference

| Model Size | Feasibility | Notes |
|------------|-------------|-------|
| **Gemma 4 1B/2B/4B** | ✅ Excellent | Runs fast on CPU with plenty of RAM to spare |
| **Gemma 4 9B** | ✅ Good | CPU inference is totally viable; 32GB RAM handles Q4_K_M easily |
| **Gemma 4 12B / 27B** | ⚠️ Marginal | 27B Q4 needs ~18GB RAM — fits, but slower on this CPU |
| **Vision models** | ✅ Good | 4B-9B vision variants work well; no NVIDIA means no CUDA, but CPU fallback is fine |
| **1M context** | ✅ Good | 32GB RAM means you can actually use the full (or near-full) 1M token context window on smaller models |
| **GPU offload** | ⚠️ Limited | ROCm on Navi 14/5500M is experimental; expect to run via llama.cpp CPU backend or Vulkan/OpenCL |

### Recommended Setup for Gemma 4

```bash
# Best bang-for-buck on this machine
ollama run gemma3:4b         # Fast, responsive for daily tasks
ollama run gemma3:9b         # Best quality on this hardware
ollama run gemma3:4b-it-q8_0 # Higher quality 4B without the 9B latency

# For the 1M context experiments
ollama run gemma3:4b         # 1M ctx on 4B = ~2GB RAM even at 1M tokens
```
